"""Configuration and filesystem paths for Game Asset Helper.

The shape and defaults are referenced from DESIGN.md §3, §5 and §10.
M0 only wires up enough fields to boot the tray app; later milestones
extend the Config dataclass without breaking on-disk compatibility
(unknown keys are ignored on load, new defaults filled in on save).
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import asdict, dataclass, field

if sys.version_info >= (3, 11):
    import tomllib
else:  # 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]
from pathlib import Path
from typing import Any

import tomli_w
from platformdirs import user_data_dir


APP_NAME = "GameAssetHelper"


class ConfigError(Exception):
    """Raised when the on-disk config is unrecoverable."""


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    library_dir: Path
    cache_dir: Path
    db_path: Path
    config_path: Path
    log_path: Path
    lock_path: Path

    def ensure_dirs(self) -> None:
        """Create every directory needed at runtime. Idempotent."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "thumbnails").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "spectrograms").mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)


def _resolve_data_root(override: str | os.PathLike[str] | None = None) -> Path:
    """Determine the on-disk root for GAH data.

    Precedence: explicit argument > GAH_DATA_DIR env > platformdirs (Roaming on Windows).
    """
    if override is not None:
        return Path(override).expanduser().resolve()
    env = os.environ.get("GAH_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    # `roaming=True` matches the spec'd %APPDATA% location on Windows.
    return Path(user_data_dir(APP_NAME, appauthor=False, roaming=True)).resolve()


def default_app_paths(data_root: str | os.PathLike[str] | None = None) -> AppPaths:
    root = _resolve_data_root(data_root)
    return AppPaths(
        data_dir=root,
        library_dir=root / "library",
        cache_dir=root / "cache",
        db_path=root / "metadata.db",
        config_path=root / "config.toml",
        log_path=root / "logs" / "gah.log",
        lock_path=root / "gah.lock",
    )


_VALID_DESCRIPTION_LANGUAGES = ("ko", "en")
_VALID_AUDIO_CHUNK_STRATEGIES = ("smart", "first", "rms_peak")


@dataclass
class Config:
    ollama_url: str = "http://127.0.0.1:11434"
    model_image: str = "gemma4:e4b"
    model_audio: str = "gemma4:e4b"
    model_embed: str = "nomic-embed-text"
    mcp_port: int = 9874
    consistency_weight: float = 0.20
    autostart: bool = False
    # M1 fields
    watch_debounce_seconds: float = 2.0
    library_dir_override: str | None = None
    # M2 fields
    # 60s: CPU 환경에서 gemma4:e4b 오디오 1청크 호출이 ~36s 측정 (Windows/CPU only).
    # 30s 면 매번 timeout → native/spectrogram 둘 다 실패 → 휴리스틱 폴백으로 강등된다.
    # GPU 환경에서는 훨씬 빠르지만 default 는 양쪽 모두 안전한 값으로 둔다.
    analysis_timeout_seconds: float = 60.0
    # M2.1 patch: 1 → 3. 분석 시간의 90%+ 가 Ollama 호출 대기라 CPU idle —
    # 워커풀 3 으로 throughput 2~2.5x. 충돌 지점 4 가지(Ollama OOM / CLIP
    # thread-unsafe / SQLite 경합 / GUI refresh 폭주) 는 함께 봉합됐다.
    analysis_concurrency: int = 3
    analysis_max_retries: int = 3
    # 동시 Ollama 호출 cap — analysis_concurrency 와 별개. 같은 모델 슬롯에
    # N 개가 동시에 두드리면 GGML crash/OOM 위험이 있어 backend-level cap.
    ollama_parallel: int = 2
    description_language: str = "ko"   # "ko" | "en" — anything else falls back to "ko"
    clip_model: str = "ViT-B-32"
    clip_pretrained: str = "openai"
    clip_enable: bool = True
    audio_max_seconds: int = 30
    audio_chunk_strategy: str = "smart"  # "smart" | "first" | "rms_peak"
    # M3 fields — 검색 가중합 + 통일성 임계 + MCP 옵션
    # M4 가 가중치를 5채널 → 6채널로 확장 + 기본값 재배분 (semantic 0.40→0.35,
    # keyword 0.15→0.10, feedback 0.10 신규). 합 1.00 유지.
    # label_match=0 케이스(자유 쿼리) 에서도 다른 채널 재정규화 없음 — 의도적으로 max 0.90.
    weight_semantic: float = 0.35
    weight_keyword: float = 0.10
    weight_label_match: float = 0.20
    weight_consistency: float = 0.20
    weight_recency: float = 0.05
    weight_feedback: float = 0.10                  # M4 신규
    # 통일성 "굳음" 판정 임계: distinct pack ≤ max AND uses ≥ min.
    consistency_locked_max_packs: int = 2
    consistency_locked_min_uses: int = 5
    # 팔레트 ΔE (LAB 평균 유클리드) 임계 — 이하면 "팔레트 근접" 보너스 +0.1.
    palette_delta_e_threshold: float = 30.0
    # 암묵 top1 추정. 기본 OFF — record_asset_use 명시 호출 권장 (MCP instructions 참조).
    implicit_top1_enabled: bool = False
    # MCP find_asset count 디폴트 (사용자가 명시 안 했을 때).
    mcp_search_default_count: int = 5
    # recency 채널의 지수 감쇠 윈도우 (초). 30일.
    recency_window_seconds: int = 2_592_000
    # M4 fields — 다양성 + 페널티 학습
    # 결과 다양성 알고리즘 default. "none" (M3 호환) / "mmr" / "round_robin".
    diversity_default: str = "none"
    # mmr 의 score↔다양성 trade-off (0.0 = 다양성만, 1.0 = score만). 0.7 권장.
    diversity_mmr_lambda: float = 0.7
    # report_feedback reason 별 signed weight. 검색 시 윈도우 내 합산 후
    # weight_feedback 적용해 채널 점수로 변환.
    feedback_negative_weight: float = -0.5
    feedback_positive_weight: float = 0.3
    feedback_irrelevant_weight: float = -0.3
    # pack-level penalty: 같은 팩에 negative 자산이 임계 이상이면 팩 전체에
    # 추가 페널티를 부여 — 자산 단위와 별개.
    feedback_pack_threshold: int = 3
    feedback_pack_penalty: float = -0.1
    # 페널티 윈도우 (초). 윈도우 밖 행은 검색 가중치에 반영 안 함. 30일.
    feedback_window_seconds: int = 2_592_000

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Config":
        # ignore unknown keys for forward-compat with later milestones
        allowed = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in allowed}
        # Validate enum-like fields; fall back to defaults on unknown values
        # so a typo in config.toml can't crash boot.
        lang = filtered.get("description_language")
        if lang is not None and lang not in _VALID_DESCRIPTION_LANGUAGES:
            filtered.pop("description_language")
        strat = filtered.get("audio_chunk_strategy")
        if strat is not None and strat not in _VALID_AUDIO_CHUNK_STRATEGIES:
            filtered.pop("audio_chunk_strategy")
        # 0/음수는 분석 자체를 멈춰버리므로 1 로 클램프.
        parallel = filtered.get("ollama_parallel")
        if parallel is not None:
            try:
                filtered["ollama_parallel"] = max(1, int(parallel))
            except (TypeError, ValueError):
                filtered.pop("ollama_parallel")
        return cls(**filtered)

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


def _atomic_write(path: Path, payload: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def save_config(cfg: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # TOML has no null type — drop None-valued keys; load_config restores defaults for them.
    mapping = {k: v for k, v in cfg.to_mapping().items() if v is not None}
    payload = tomli_w.dumps(mapping).encode("utf-8")
    _atomic_write(path, payload)


def load_config(path: Path) -> Config:
    """Load config from disk; create with defaults if missing; back up if corrupt."""
    if not path.exists():
        cfg = Config()
        save_config(cfg, path)
        return cfg
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError:
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        # overwrite the bad file with defaults so the next boot is clean
        cfg = Config()
        save_config(cfg, path)
        return cfg
    return Config.from_mapping(data)
