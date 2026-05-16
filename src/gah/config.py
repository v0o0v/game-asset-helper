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

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Config":
        # ignore unknown keys for forward-compat with later milestones
        allowed = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in allowed}
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
