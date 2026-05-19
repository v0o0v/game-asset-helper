"""v0.0.1 데이터 폴더 마이그레이션 helper.

%APPDATA%\\GameAssetHelper\\ → %APPDATA%\\AssetCacheMCP\\
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from assetcache.config import AppPaths

MIGRATION_MARKER = ".migrated_from_v001"


@dataclass(frozen=True)
class MigrationCandidate:
    source: Path
    target: Path
    total_files: int
    total_bytes: int
    has_db: bool
    has_library: bool


def is_already_migrated(target: Path) -> bool:
    """target 안에 마이그레이션 완료 마커가 있는지."""
    return (target / MIGRATION_MARKER).exists()


def _is_empty_dir(p: Path) -> bool:
    if not p.exists():
        return True
    return not any(p.iterdir())


def _count_files(root: Path) -> tuple[int, int]:
    n = 0
    sz = 0
    for f in root.rglob("*"):
        if f.is_file():
            n += 1
            try:
                sz += f.stat().st_size
            except OSError:
                pass
    return n, sz


def detect_v001_candidate(paths: AppPaths) -> Optional[MigrationCandidate]:
    """새 폴더가 비어있고 구 폴더에 데이터가 있으면 MigrationCandidate 반환."""
    if paths.legacy_data_dir is None:
        return None

    new_dir = paths.data_dir
    old_dir = paths.legacy_data_dir

    if is_already_migrated(new_dir):
        return None

    if not _is_empty_dir(new_dir):
        return None

    if not old_dir.exists():
        return None

    has_db = (old_dir / "metadata.db").exists()
    has_library = (old_dir / "library").exists()

    if not has_db and not has_library:
        return None

    total_files, total_bytes = _count_files(old_dir)

    return MigrationCandidate(
        source=old_dir,
        target=new_dir,
        total_files=total_files,
        total_bytes=total_bytes,
        has_db=has_db,
        has_library=has_library,
    )
