"""Sound analyzer with 1-2-3 fallback chain.

1. **Native audio** — base64-encoded 16 kHz mono WAV clip(s) sent
   straight to Gemma 4.  Verified to work via the Ollama native
   ``/api/chat`` ``images`` array (memory
   ``project_ollama_multimodal_api_shape``).
2. **Mel-spectrogram vision fallback** — if the native call times
   out / crashes / returns invalid JSON, we render a mel
   spectrogram as PNG and resubmit to the same model as an image.
3. **Heuristic** — if both Gemma paths fail, classify by filename
   keywords (``bgm``/``loop``/``voice``/``ui``…) and mark the row
   as ``state='partial'``.

The result records ``audio_path_used`` so downstream consumers can
trust the analysis quality.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..llm import unwrap_chat_result
from ..llm.base import BackendError
from ..ollama_client import ChatMessage, OllamaError, encode_audio_clip, encode_image
from ..searchable import build_searchable
from ..store import LabelScore, SoundMeta
from .base import AnalyzerInput, AnalyzerResult

if TYPE_CHECKING:
    from ..embedding import EmbeddingEncoder
    from ..labels import LabelRegistry
    from ..ollama_client import OllamaClient

log = logging.getLogger(__name__)


_SOUND_AXES = (
    "sound_category", "sound_mood", "sound_timbre", "sound_environment",
    "sound_instrument", "sound_tempo", "sound_intensity", "sound_use",
    "sound_genre", "sound_voice_type",
)
_MULTI_AXES = (
    ("sound_mood", "mood"),
    ("sound_timbre", "timbre"),
    ("sound_environment", "environment"),
    ("sound_instrument", "instruments"),
    ("sound_use", "use"),
)
_SINGLE_AXES = (
    ("sound_category", "category"),
    ("sound_tempo", "tempo"),
    ("sound_intensity", "intensity"),
    ("sound_genre", "genre"),
    ("sound_voice_type", "voice_type"),
)
_MUSIC_CATEGORIES = {"bgm", "jingle", "cinematic"}


class SoundAnalyzer:
    def __init__(
        self,
        *,
        ollama: "OllamaClient",
        embedder: "EmbeddingEncoder",
        registry: "LabelRegistry",
        spectrogram_cache_dir: Path,
        max_clip_seconds: int = 30,
        chunk_strategy: str = "smart",
    ) -> None:
        self.ollama = ollama
        self.embedder = embedder
        self.registry = registry
        self.spectrogram_cache_dir = Path(spectrogram_cache_dir)
        self.max_clip_seconds = max_clip_seconds
        self.chunk_strategy = chunk_strategy

    # -- public API ---------------------------------------------------

    def analyze(self, inp: AnalyzerInput) -> AnalyzerResult:
        import librosa
        import soundfile as sf

        # ── 1. 기술 특성 ─────────────────────────────────────────────
        info = sf.info(str(inp.abs_path))
        channels = int(info.channels)
        sr_native = int(info.samplerate)

        samples_mono, _ = librosa.load(
            str(inp.abs_path), sr=16000, mono=True
        )
        duration_ms = int(len(samples_mono) / 16000 * 1000)
        rms = float(((samples_mono ** 2).mean()) ** 0.5)
        loudness_db = 20.0 * math.log10(max(rms, 1e-9))
        try:
            bpm, _ = librosa.beat.beat_track(y=samples_mono, sr=16000)
            bpm_val: float | None = float(bpm) if bpm > 0 else None
        except Exception:
            bpm_val = None

        # ── 2~4. Gemma 호출 (3 단 폴백) ─────────────────────────────
        payload, path_used, state, error, audio_backend = self._gemma_with_fallback(
            samples_mono, duration_ms=duration_ms,
            asset_id=inp.asset_id, rel_path=inp.rel_path,
            language=inp.language,
        )

        # ── 5. 라벨 통합 ─────────────────────────────────────────────
        labels = self._payload_to_labels(payload)

        # ── 6. 메타 + searchable + 임베딩 ────────────────────────────
        sound_meta = SoundMeta(
            duration_ms=duration_ms,
            sample_rate=sr_native,
            channels=channels,
            loudness_db=loudness_db,
            bpm=bpm_val,
            category=payload.get("category"),
            loopable=payload.get("loopable"),
            instruments=payload.get("instruments") or None,
            tempo=payload.get("tempo"),
            intensity=payload.get("intensity"),
            genre=payload.get("genre"),
            voice_type=payload.get("voice_type"),
            audio_path_used=path_used,
        )

        label_descs = self._collect_label_descriptions(labels)
        searchable = build_searchable(
            meta=sound_meta, labels=labels, label_descriptions=label_descs,
            description=payload.get("description", "") or "",
            rel_path=inp.rel_path,
        )
        embed_backend: str | None = None
        try:
            blob, dim = self.embedder.encode_text(searchable.for_embed)
            embed_backend = self.embedder.last_backend_name
        except OllamaError:
            blob, dim = b"", 0
            if state == "ok":
                state = "partial"

        backend_used: dict = {}
        if audio_backend:
            backend_used["audio"] = audio_backend
        if embed_backend:
            backend_used["embed"] = embed_backend

        return AnalyzerResult(
            kind="sound", state=state, error=error,
            sprite_meta=None, sound_meta=sound_meta,
            labels=labels, searchable=searchable,
            embedding_vector=blob, embedding_dim=dim,
            embedding_model=self.embedder.model,
            description=payload.get("description", "") or "",
            backend_used=backend_used,
        )

    # -- Gemma orchestration ----------------------------------------

    def _gemma_with_fallback(
        self,
        samples_mono,
        *,
        duration_ms: int,
        asset_id: int,
        rel_path: str,
        language: str,
    ):
        """3-stage fallback. Returns (payload, path_used, state, error, backend_name).

        M11.1 Task 1.5 — 5번째 반환값으로 실제 호출된 audio backend 이름 노출.
        heuristic 경로는 backend 없으므로 None 반환.
        """
        # 1차: 네이티브 오디오 — 최대 3 회까지 retry (whitelist 위반 검출 시).
        last_fixed: dict | None = None
        last_err: str | None = None
        last_backend: str | None = None
        for _ in range(3):
            try:
                payload, last_backend = self._call_gemma_audio(
                    samples_mono, language=language,
                    duration_ms=duration_ms,
                )
            except (OllamaError, BackendError) as e:
                # M11 — chain 호환 (BackendError 도 catch) + 정확한 backend 이름 표기.
                backend_name = getattr(e, "backend", None) or "chat"
                last_err = f"chat backend ({backend_name}): {e}"
                payload = None
                break
            except Exception as e:  # noqa: BLE001
                log.debug("native audio path crashed: %s", e)
                payload = None
                break
            if payload is None:
                last_err = "native path returned no payload"
                break
            ok, fixed, err = self._validate(payload)
            if ok:
                return fixed, "native", "ok", None, last_backend
            last_fixed, last_err = fixed, err
        if last_fixed is not None:
            # JSON 자체는 받았지만 enum 위반이 끝까지 풀리지 않은 경우 — partial 로 native 결과 채택.
            return last_fixed, "native", "partial", last_err, last_backend

        # 2차: 멜 스펙트로그램 비전 — 동일하게 최대 3 회 retry.
        try:
            spec_path = self._render_spectrogram(
                samples_mono, asset_id=asset_id,
            )
        except Exception as e:  # noqa: BLE001
            log.debug("spectrogram render failed: %s", e)
            spec_path = None

        if spec_path is not None:
            last_fixed = None
            last_backend = None
            for _ in range(3):
                try:
                    payload, last_backend = self._call_gemma_image(
                        spec_path, language=language
                    )
                except (OllamaError, BackendError) as e:
                    backend_name = getattr(e, "backend", None) or "chat"
                    last_err = f"chat backend ({backend_name}): {e}"
                    payload = None
                    break
                if payload is None:
                    last_err = "spectrogram path returned no payload"
                    break
                ok, fixed, err = self._validate(payload)
                if ok:
                    return fixed, "spectrogram", "ok", None, last_backend
                last_fixed, last_err = fixed, err
            if last_fixed is not None:
                return last_fixed, "spectrogram", "partial", last_err, last_backend

        # 3차: 휴리스틱
        heuristic = self._heuristic_payload(rel_path=rel_path,
                                            duration_ms=duration_ms)
        return heuristic, "heuristic", "partial", "both gemma paths failed", None

    def _call_gemma_audio(self, samples_mono, *, language: str,
                          duration_ms: int):
        """Returns (merged_payload, backend_name). backend_name from first successful clip."""
        clips = self._select_clips(samples_mono, strategy=self.chunk_strategy,
                                    duration_ms=duration_ms)
        merged_payload: dict | None = None
        first_backend: str | None = None
        for clip_samples in clips:
            b64 = encode_audio_clip(clip_samples, sample_rate=16000)
            msgs = [
                ChatMessage(role="system",
                            content=self._build_prompt(language=language)),
                ChatMessage(role="user",
                            content="Analyse this audio clip.",
                            audio_b64=[(b64, "audio/wav")]),
            ]
            try:
                raw = self.ollama.chat(msgs, force_json=True, num_ctx=8000)
                # BackendChain → (dict, str), OllamaClient → dict
                if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], str):
                    resp, backend_name = raw[0], raw[1]
                else:
                    resp, backend_name = raw, None
            except (OllamaError, BackendError):
                continue
            if not isinstance(resp, dict):
                continue
            if first_backend is None:
                first_backend = backend_name
            merged_payload = self._merge_payloads(merged_payload, resp)
        return merged_payload, first_backend

    def _call_gemma_image(self, spec_path: Path, *, language: str):
        """Returns (payload, backend_name). Both None on failure."""
        b64 = encode_image(spec_path)
        msgs = [
            ChatMessage(role="system",
                        content=self._build_prompt(language=language)),
            ChatMessage(role="user",
                        content="Mel-spectrogram fallback for an audio clip.",
                        images_b64=[b64]),
        ]
        try:
            raw = self.ollama.chat(msgs, force_json=True, num_ctx=8000)
            # BackendChain → (dict, str), OllamaClient → dict
            if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], str):
                resp, backend_name = raw[0], raw[1]
            else:
                resp, backend_name = raw, None
        except (OllamaError, BackendError):
            return None, None
        if not isinstance(resp, dict):
            return None, None
        return resp, backend_name

    def _build_prompt(self, *, language: str) -> str:
        slots = {
            "sound_category_enum":
                ", ".join(self.registry.list_labels("sound_category")),
            "sound_mood_enum":
                ", ".join(self.registry.list_labels("sound_mood")),
            "sound_timbre_enum":
                ", ".join(self.registry.list_labels("sound_timbre")),
            "sound_environment_enum":
                ", ".join(self.registry.list_labels("sound_environment")),
            "sound_instrument_enum":
                ", ".join(self.registry.list_labels("sound_instrument")),
            "sound_tempo_enum":
                ", ".join(self.registry.list_labels("sound_tempo")),
            "sound_intensity_enum":
                ", ".join(self.registry.list_labels("sound_intensity")),
            "sound_use_enum":
                ", ".join(self.registry.list_labels("sound_use")),
            "sound_genre_enum":
                ", ".join(self.registry.list_labels("sound_genre")),
            "sound_voice_type_enum":
                ", ".join(self.registry.list_labels("sound_voice_type")),
            "language": language,
        }
        return (
            "You are a game audio metadata generator. Respond ONLY with valid"
            " JSON.\n\n"
            "Schema:\n"
            "- category: one of [{sound_category_enum}]\n"
            "- mood: array (0..3) from [{sound_mood_enum}]\n"
            "- timbre: array (0..3) from [{sound_timbre_enum}]\n"
            "- environment: array (0..2) from [{sound_environment_enum}]\n"
            "- instruments: array (0..4) from [{sound_instrument_enum}]\n"
            "- tempo: one of [{sound_tempo_enum}] or null\n"
            "- intensity: one of [{sound_intensity_enum}]\n"
            "- use: array (0..3) from [{sound_use_enum}]\n"
            "- genre: one of [{sound_genre_enum}] or null if not music\n"
            "- voice_type: one of [{sound_voice_type_enum}] or null"
            " if not voice\n"
            "- loopable: boolean\n"
            "- transcript: 발화 내용 in {language} if category=voice, else \"\"\n"
            "- description: one sentence (<= 30 words) in {language}\n"
            "- confidence: float 0..1\n"
        ).format(**slots)

    # -- merge / validation -----------------------------------------

    @staticmethod
    def _merge_payloads(a: dict | None, b: dict) -> dict:
        if a is None:
            return dict(b)
        out = dict(a)
        # 다중 필드: 합집합
        for key in ("mood", "timbre", "environment", "instruments", "use"):
            merged = list(a.get(key) or [])
            for val in b.get(key) or []:
                if val and val not in merged:
                    merged.append(val)
            out[key] = merged
        # 단일 필드: 첫 결과 유지하되 없으면 채움
        for key in ("category", "tempo", "intensity", "genre", "voice_type",
                    "description", "transcript"):
            if not out.get(key):
                out[key] = b.get(key)
        if "loopable" not in out or out["loopable"] is None:
            out["loopable"] = b.get("loopable")
        if "confidence" not in out:
            out["confidence"] = b.get("confidence", 0.5)
        return out

    def _validate(self, payload: dict) -> tuple[bool, dict, str | None]:
        fixed = dict(payload)
        violations: list[str] = []

        def _squash_single(key: str) -> object:
            """Gemma 가 단일 enum 필드를 list 로 돌려주는 경우가 있다 —
            첫 요소만 채택하고 그 외는 위반으로 기록한다."""
            value = fixed.get(key)
            if isinstance(value, list):
                violations.append(f"{key}_was_list={value!r}")
                value = value[0] if value else None
                fixed[key] = value
            return value

        cat_allowed = set(self.registry.list_labels("sound_category"))
        cat = _squash_single("category")
        if cat not in cat_allowed:
            violations.append(f"category={cat!r}")
            fixed["category"] = "sfx" if "sfx" in cat_allowed else next(iter(cat_allowed), None)

        for axis_key, payload_key in _MULTI_AXES:
            allowed = set(self.registry.list_labels(axis_key))
            arr = fixed.get(payload_key) or []
            if not isinstance(arr, list):
                violations.append(f"{payload_key}_not_list={arr!r}")
                arr = [arr]
            cleaned = [t for t in arr if isinstance(t, str) and t in allowed]
            if len(cleaned) != len(arr):
                violations.append(f"{payload_key}={arr!r}")
            fixed[payload_key] = cleaned

        for axis_key, payload_key in (
            ("sound_tempo", "tempo"),
            ("sound_intensity", "intensity"),
        ):
            allowed = set(self.registry.list_labels(axis_key))
            val = _squash_single(payload_key)
            if val is not None and val not in allowed:
                violations.append(f"{payload_key}={val!r}")
                fixed[payload_key] = None

        # 조건부 단일 필드: genre / voice_type
        genre_allowed = set(self.registry.list_labels("sound_genre"))
        genre = _squash_single("genre")
        if fixed.get("category") in _MUSIC_CATEGORIES:
            if genre is not None and genre not in genre_allowed:
                violations.append(f"genre={genre!r}")
                fixed["genre"] = None
        else:
            # 음악 카테고리 아닌데 genre 채워졌으면 위반 — null 강제
            if genre is not None:
                violations.append(f"genre when category={fixed.get('category')}")
                fixed["genre"] = None

        voice_allowed = set(self.registry.list_labels("sound_voice_type"))
        vt = _squash_single("voice_type")
        if fixed.get("category") == "voice":
            if vt is not None and vt not in voice_allowed:
                violations.append(f"voice_type={vt!r}")
                fixed["voice_type"] = None
        else:
            if vt is not None:
                violations.append("voice_type when category not voice")
                fixed["voice_type"] = None

        return (not violations), fixed, ("violations: " + ", ".join(violations)
                                          if violations else None)

    # -- heuristic + chunking + spectrogram --------------------------

    @staticmethod
    def _heuristic_payload(*, rel_path: str, duration_ms: int) -> dict:
        path_lower = rel_path.lower()
        if re.search(r"(bgm|loop|music)", path_lower):
            category = "bgm"
        elif re.search(r"(voice|vo[_/]|line)", path_lower):
            category = "voice"
        elif re.search(r"(ui|click|hover)", path_lower):
            category = "ui_sound"
        elif duration_ms >= 10_000:
            category = "bgm"
        else:
            category = "sfx"
        return {
            "category": category,
            "mood": [], "timbre": [], "environment": [],
            "instruments": [], "use": [],
            "tempo": None, "intensity": None, "genre": None,
            "voice_type": None,
            "loopable": "loop" in path_lower,
            "transcript": "",
            "description": "",
            "confidence": 0.3,
        }

    def _select_clips(self, samples_mono, *, strategy: str,
                      duration_ms: int) -> list:
        import numpy as np

        sr = 16000
        max_samples = self.max_clip_seconds * sr
        total = len(samples_mono)
        if total <= max_samples:
            return [samples_mono]

        if strategy == "first":
            return [samples_mono[:max_samples]]
        if strategy == "rms_peak":
            # 30s 윈도우 슬라이딩 — RMS 최고 구간 1개
            window = max_samples
            step = max(1, window // 4)
            best_rms = -1.0
            best_start = 0
            for start in range(0, total - window, step):
                chunk = samples_mono[start:start + window]
                rms = float((chunk ** 2).mean() ** 0.5)
                if rms > best_rms:
                    best_rms = rms
                    best_start = start
            return [samples_mono[best_start:best_start + window]]

        # smart: 시작 5s + 중앙 15s + 끝 5s 세 청크
        head = samples_mono[: 5 * sr]
        mid_start = max(0, total // 2 - (15 * sr) // 2)
        mid = samples_mono[mid_start: mid_start + 15 * sr]
        tail = samples_mono[-5 * sr:]
        return [head, mid, tail]

    def _render_spectrogram(self, samples_mono, *, asset_id: int) -> Path:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        import librosa
        import numpy as np

        self.spectrogram_cache_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.spectrogram_cache_dir / f"{asset_id}.png"
        S = librosa.feature.melspectrogram(
            y=samples_mono[: 30 * 16000], sr=16000, n_mels=128, hop_length=512
        )
        S_db = librosa.power_to_db(S, ref=np.max)
        fig, ax = plt.subplots(figsize=(4, 2), dpi=128)
        librosa.display.specshow(S_db, sr=16000, hop_length=512, ax=ax)
        fig.tight_layout()
        fig.savefig(out_path, bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        return out_path

    # -- label assembly ---------------------------------------------

    def _payload_to_labels(self, payload: dict) -> list[LabelScore]:
        labels: list[LabelScore] = []
        confidence = float(payload.get("confidence") or 0.5)

        for axis, payload_key in _SINGLE_AXES:
            value = payload.get(payload_key)
            if value:
                labels.append(LabelScore(
                    axis=axis, label=value, score=confidence,
                    source="gemma", weight="primary",
                ))

        for axis, payload_key in _MULTI_AXES:
            for i, value in enumerate(payload.get(payload_key) or []):
                if not value:
                    continue
                weight = (
                    "primary" if i == 0
                    else "secondary" if i == 1
                    else "tertiary"
                )
                labels.append(LabelScore(
                    axis=axis, label=value, score=confidence,
                    source="gemma", weight=weight,
                ))
        return labels

    def _collect_label_descriptions(
        self, labels: list[LabelScore]
    ) -> dict[tuple[str, str], str]:
        wanted: dict[tuple[str, str], str] = {}
        for lbl in labels:
            key = (lbl.axis, lbl.label)
            if key in wanted:
                continue
            for row in self.registry.list_labels(
                axis=lbl.axis, with_description=True
            ):
                if row.label == lbl.label and row.description:
                    wanted[key] = row.description
                    break
        return wanted
