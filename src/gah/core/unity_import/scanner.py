"""M7 — Unity Asset Store 캐시 디렉터리 스캐너 (D2, D17)."""

from __future__ import annotations

import fnmatch
import time
from pathlib import Path
from typing import Iterable

from gah.core.unity_import.types import UnityPackagePath, UnityScanResult


def _publisher_category(p: Path, cache_root: Path) -> tuple[str | None, str | None]:
    try:
        rel = p.relative_to(cache_root)
    except ValueError:
        return (None, None)
    parts = rel.parts
    if len(parts) >= 3:
        return (parts[0], parts[1])
    if len(parts) == 2:
        return (parts[0], None)
    return (None, None)


def _scan_cache(cache_root: Path) -> Iterable[UnityPackagePath]:
    for p in cache_root.rglob("*.unitypackage"):
        try:
            st = p.stat()
            publisher, category = _publisher_category(p, cache_root)
            yield UnityPackagePath(
                abs_path=p,
                publisher=publisher,
                category=category,
                asset_name=p.stem,
                size=st.st_size,
                mtime=int(st.st_mtime),
            )
        except OSError:
            continue


class UnityAssetStoreScanner:
    """Unity Asset Store 캐시 디렉터리를 scan 해 unity_imports DB 와 동기화한다.

    state 머신 (D17):
    - 신규 → INSERT state='discovered'
    - mtime 동일 + force=False → touch (unchanged)
    - force=True → upsert (updated)
    - imported/skipped/previewed + mtime 변경 → state='discovered' + preview_* NULL (updated)
    - 그 외 state + mtime 변경 → upsert (updated)
    - 캐시에서 사라짐 → removed 카운트만 (DB row 유지)
    """

    def __init__(self, store) -> None:
        self._store = store

    def run_once(
        self,
        cache_path: Path,
        *,
        force: bool = False,
        publisher_glob: str | None = None,
        asset_name_glob: str | None = None,
    ) -> UnityScanResult:
        """캐시 디렉터리 walk → DB 비교 → state 머신.

        Args:
            cache_path: Unity Asset Store 캐시 루트 디렉터리.
            force: True 이면 mtime 변경 여부와 무관하게 모두 upsert (updated).
            publisher_glob: fnmatch 패턴 — publisher 이름 필터. None 이면 전체 통과.
            asset_name_glob: fnmatch 패턴 — asset_name(파일 stem) 필터.

        Returns:
            UnityScanResult — new/updated/unchanged/removed 카운트 + warnings.
        """
        warnings: list[str] = []

        if not cache_path or not cache_path.is_dir():
            return UnityScanResult(
                scanned=0,
                new=0,
                updated=0,
                unchanged=0,
                removed=0,
                cache_path=cache_path or Path(""),
                warnings=("cache directory missing",),
            )

        try:
            packages = list(_scan_cache(cache_path))
        except PermissionError as e:
            return UnityScanResult(
                scanned=0,
                new=0,
                updated=0,
                unchanged=0,
                removed=0,
                cache_path=cache_path,
                warnings=(f"permission denied: {e}",),
            )

        # glob 필터 적용
        if publisher_glob:
            packages = [
                p for p in packages
                if p.publisher and fnmatch.fnmatch(p.publisher, publisher_glob)
            ]
        if asset_name_glob:
            packages = [
                p for p in packages
                if fnmatch.fnmatch(p.asset_name, asset_name_glob)
            ]

        # DB 기존 row 로드 (path → record 맵)
        existing_by_path: dict[Path, object] = {
            r.package_path: r for r in self._store.list_unity_imports()
        }
        seen_paths: set[Path] = set()
        new = 0
        updated = 0
        unchanged = 0
        now = int(time.time())

        for pkg in packages:
            seen_paths.add(pkg.abs_path)
            existing = existing_by_path.get(pkg.abs_path)

            if existing is None:
                # 신규 → INSERT state='discovered'
                self._store.insert_unity_import(
                    pkg, first_seen_at=now, last_scanned_at=now
                )
                new += 1
                continue

            if not force and existing.package_mtime == pkg.mtime:
                # mtime 동일 + force=False → unchanged
                self._store.touch_unity_import(existing.id, last_scanned_at=now)
                unchanged += 1
            else:
                # mtime 변경 혹은 force=True
                if existing.import_state in ("imported", "skipped", "previewed"):
                    # 완료 상태 → discovered 되돌림 + preview_* NULL
                    self._store.update_unity_state(
                        existing.id,
                        "discovered",
                        reset_preview=True,
                        new_mtime=pkg.mtime,
                        new_size=pkg.size,
                        last_scanned_at=now,
                    )
                else:
                    # discovered/import_pending/failed → 그냥 upsert
                    self._store.upsert_unity_import(pkg, last_scanned_at=now)
                updated += 1

        # 캐시에서 사라진 파일 카운트 (DB row 유지, state 변경 X)
        removed = sum(1 for path in existing_by_path if path not in seen_paths)

        return UnityScanResult(
            scanned=len(packages),
            new=new,
            updated=updated,
            unchanged=unchanged,
            removed=removed,
            cache_path=cache_path,
            warnings=tuple(warnings),
        )
