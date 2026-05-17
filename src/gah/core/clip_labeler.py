"""CLIP zero-shot label scorer.

Two backends live behind a common ``ClipBackend`` Protocol:

* :class:`FakeBackend` — deterministic hash-based vectors.  No model
  download.  Used by the entire unit test suite.
* :class:`OpenClipBackend` — real ``open_clip_torch`` model.  Lazy
  weight load; uses CUDA when available, falls back to CPU
  automatically (memory ``project_distribution_torch_strategy.md``).

The :class:`ClipLabeler` orchestrates the backend + the
``clip_label_cache`` SQLite table so text embeddings for the label
vocabulary are computed at most once per (label, model) pair.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Protocol

import numpy as np

if TYPE_CHECKING:
    from .labels import LabelRegistry
    from .store import Store

log = logging.getLogger(__name__)


# ── backend protocol + fakes ────────────────────────────────────────


class ClipBackend(Protocol):
    """Minimal CLIP backend surface — both image and text → ndarray."""

    model_id: str  # e.g. 'ViT-B-32:openai'
    dim: int

    def encode_text(self, texts: list[str]) -> np.ndarray: ...
    def encode_image(self, image_path: Path) -> np.ndarray: ...


class FakeBackend:
    """Deterministic CLIP stand-in for unit tests.

    Vectors are derived from sha256(text) / sha256(image bytes) so the
    same inputs always produce the same outputs without any model
    download.  Provides a ``encode_text_call_count`` counter so tests
    can assert caching behaviour.
    """

    def __init__(self, dim: int = 64,
                 model_id: str = "fake-clip:test") -> None:
        self.dim = dim
        self.model_id = model_id
        self.encode_text_call_count = 0
        self.encode_image_call_count = 0

    def _hash_to_vec(self, payload: bytes) -> np.ndarray:
        # Stretch a sha256 hash to the requested dimension via repeated digest.
        out = bytearray()
        i = 0
        while len(out) < self.dim * 4:
            out.extend(
                hashlib.sha256(payload + i.to_bytes(4, "little")).digest()
            )
            i += 1
        raw = bytes(out[: self.dim * 4])
        # Map u8 bytes → [-1, 1] floats so cosine has a meaningful range.
        u8 = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        arr = (u8 / 127.5) - 1.0
        return arr

    def encode_text(self, texts: list[str]) -> np.ndarray:
        self.encode_text_call_count += 1
        return np.stack([self._hash_to_vec(t.encode("utf-8")) for t in texts])

    def encode_image(self, image_path: Path) -> np.ndarray:
        self.encode_image_call_count += 1
        data = Path(image_path).read_bytes() if Path(image_path).exists() else b""
        return self._hash_to_vec(b"img:" + data)


# ── real backend (open_clip_torch) ──────────────────────────────────


class OpenClipBackend:
    """Real CLIP backed by ``open_clip_torch``.

    Lazy-loads the model on first use so simply constructing the
    object during boot does not trigger a 600 MB download.  Honours
    ``torch.cuda.is_available()`` to pick the device — works on both
    GPU-equipped developer PCs and CPU-only end-user machines.
    """

    def __init__(
        self,
        *,
        model: str = "ViT-B-32",
        pretrained: str = "openai",
        cache_dir: Path | None = None,
    ) -> None:
        self.model_id = f"{model}:{pretrained}"
        self._model_name = model
        self._pretrained = pretrained
        self._cache_dir = cache_dir
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._device: str | None = None
        self._dim: int | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._ensure_loaded()
        assert self._dim is not None
        return self._dim

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import open_clip  # type: ignore[import-untyped]
        import torch

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info("CLIP backend initialized on device=%s", self._device)
        cache_kw = {}
        if self._cache_dir is not None:
            cache_kw["cache_dir"] = str(self._cache_dir)
        model, _, preprocess = open_clip.create_model_and_transforms(
            self._model_name, pretrained=self._pretrained, **cache_kw,
        )
        model.eval()
        model.to(self._device)
        self._model = model
        self._preprocess = preprocess
        self._tokenizer = open_clip.get_tokenizer(self._model_name)
        # determine output dim by a tiny probe
        with torch.no_grad():
            tokens = self._tokenizer(["probe"]).to(self._device)
            vec = model.encode_text(tokens)
        self._dim = int(vec.shape[-1])

    def encode_text(self, texts: list[str]) -> np.ndarray:
        self._ensure_loaded()
        import torch

        with torch.no_grad():
            tokens = self._tokenizer(texts).to(self._device)
            features = self._model.encode_text(tokens)
            features = features / features.norm(dim=-1, keepdim=True)
        return features.detach().cpu().numpy().astype(np.float32)

    def encode_image(self, image_path: Path) -> np.ndarray:
        self._ensure_loaded()
        import torch
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        tensor = self._preprocess(img).unsqueeze(0).to(self._device)
        with torch.no_grad():
            features = self._model.encode_image(tensor)
            features = features / features.norm(dim=-1, keepdim=True)
        return features.detach().cpu().numpy().astype(np.float32)[0]


# ── ClipLabeler ─────────────────────────────────────────────────────


class ClipLabeler:
    def __init__(
        self,
        *,
        backend: ClipBackend,
        store: "Store",
        registry: "LabelRegistry",
        enabled: bool = True,
    ) -> None:
        self.backend = backend
        self.store = store
        self.registry = registry
        self.enabled = enabled
        # torch CLIP 모델 forward 는 thread-safe 가 아니다 — 워커 N 개가 동시에
        # encode_image 를 부르면 비결정 결과·CUDA OOM 위험. 단일 lock 으로 직렬화.
        self._lock = threading.Lock()

    # -- text-side cache ---------------------------------------------

    def warmup(self, labels: Iterable[str] | None = None) -> None:
        """Pre-compute and persist text embeddings for ``labels``.

        ``labels=None`` resolves the 14 visual axes from the registry
        (sound axes are deliberately excluded; their labels are Gemma-
        only).
        """
        if not self.enabled:
            return
        with self._lock:
            targets = self._resolve_labels(labels)
            missing = [t for t in targets if self._cache_get(t) is None]
            if not missing:
                return
            vectors = self.backend.encode_text(missing)
            dim = int(vectors.shape[-1])
            for label, vec in zip(missing, vectors):
                self._cache_put(label, dim, vec)

    def _resolve_labels(self, labels: Iterable[str] | None) -> list[str]:
        if labels is not None:
            return list(labels)
        # 시각 14축의 활성 라벨 모두 수집 (사운드 4축 제외)
        visual_axes = (
            "category", "style", "mood", "palette", "color", "view",
            "material", "lighting", "time_of_day", "weather", "theme",
            "size_hint", "domain", "animation",
        )
        out: list[str] = []
        for axis in visual_axes:
            out.extend(self.registry.list_labels(axis=axis))
        # 중복 제거 (같은 토큰이 다른 축에 있을 수 있음 — 한 번만 임베딩)
        return sorted(set(out))

    # -- scoring ------------------------------------------------------

    def score_image(
        self,
        image_path: Path,
        labels: Iterable[str] | None = None,
    ) -> dict[str, float]:
        if not self.enabled:
            return {}
        with self._lock:
            targets = self._resolve_labels(labels)
            if not targets:
                return {}

            # 라벨 임베딩을 확보 (missing 인 것만 계산)
            missing = [t for t in targets if self._cache_get(t) is None]
            if missing:
                vectors = self.backend.encode_text(missing)
                dim_text = int(vectors.shape[-1])
                for label, vec in zip(missing, vectors):
                    self._cache_put(label, dim_text, vec)

            label_vecs = np.stack(
                [self._cache_get(t) for t in targets]  # type: ignore[list-item]
            )
            img_vec = self.backend.encode_image(image_path)
            img_vec = img_vec.reshape(-1)

            # 코사인 유사도 = (L @ img) / (||L|| ||img||)
            img_norm = np.linalg.norm(img_vec)
            label_norms = np.linalg.norm(label_vecs, axis=1)
            denom = label_norms * img_norm + 1e-12
            scores = (label_vecs @ img_vec) / denom
            # 음수 코사인은 의미 없는 신호 — 0 으로 클램프
            scores = np.clip(scores, 0.0, 1.0)
            return {label: float(s) for label, s in zip(targets, scores)}

    # -- cache helpers -----------------------------------------------

    def _cache_get(self, label: str) -> np.ndarray | None:
        blob = self.store.clip_label_cache_get(label, self.backend.model_id)
        if blob is None:
            return None
        arr = np.frombuffer(blob, dtype=np.float32)
        return arr

    def _cache_put(self, label: str, dim: int, vector: np.ndarray) -> None:
        self.store.clip_label_cache_put(
            label, self.backend.model_id, dim,
            np.asarray(vector, dtype=np.float32).tobytes(),
        )
