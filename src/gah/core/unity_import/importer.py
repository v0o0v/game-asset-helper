"""M7 — UnityImporter (D5).

선택된 .unitypackage 를 library/<pack_name>/<원본 Unity 경로>/ 로 물리 복사.
pack.json 자동 생성. 워처가 새 디렉터리 감지하면 일반 인테이크 흐름 진입.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from gah.core.unity_import.types import UnityImportResult
from gah.core.unity_import.unitypackage import extract_targets, parse_pathnames


def _normalize_pack_name(asset_name: str) -> str:
    """공백·특수문자 → _, 소문자."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", asset_name).strip("_").lower()
    return s or "unity_pack"


class UnityImporter:
    def __init__(self, store, library_root: Path):
        self._store = store
        self._library_root = library_root

    def import_package(self, unity_import_id: int) -> UnityImportResult:
        """선택된 .unitypackage 를 library/<pack_name>/<원본 Unity 경로>/ 로 물리 복사.
        pack.json 자동 생성. 워처가 새 디렉터리 감지하면 일반 인테이크 흐름 진입.

        - 패키지 row 가 이미 imported 이고 pack_id 가 있으면 → idempotent (그대로 반환)
        - parse_pathnames + extract_targets 호출
        - pack.json 작성
        - update_unity_state(state='imported', imported_at=now)
        - 실패 시 update_unity_state(state='failed', import_error=str(e))
        """
        row = self._store.get_unity_import_by_id(unity_import_id)
        if row is None:
            return UnityImportResult(
                pack_id=None, pack_name="", asset_count=0,
                state="failed",
                error=f"unity_import id={unity_import_id} not found",
            )
        if row.import_state == "imported" and row.pack_id is not None:
            return UnityImportResult(
                pack_id=row.pack_id,
                pack_name=_normalize_pack_name(row.asset_name),
                asset_count=row.preview_asset_count or 0,
                state="imported",
                error=None,
            )

        pack_name = _normalize_pack_name(row.asset_name)
        dest = self._library_root / pack_name

        try:
            entries = parse_pathnames(row.package_path)
            target_guids = list(entries.keys())
            # M7 patch — 지원 자산 (png/jpg/webp/wav/ogg/mp3) 이 0개면 임포트
            # 자체가 무의미 (라이브러리에 빈 팩 생성). 명확한 실패 메시지.
            if not target_guids:
                msg = "지원되는 자산 (png/jpg/webp/wav/ogg/mp3) 이 없습니다"
                self._store.update_unity_state(
                    unity_import_id, "failed", import_error=msg,
                )
                return UnityImportResult(
                    pack_id=None, pack_name=pack_name, asset_count=0,
                    state="failed", error=msg,
                )
            result = extract_targets(row.package_path, dest, target_guids)
            self._write_manifest(dest, row)
            now = int(time.time())
            # M7 patch — 미리보기 버튼 제거 후, 임포트 성공 시 자산 카운트가
            # preview 컬럼에 자동으로 채워지도록 (사용자가 임포트 후 표에서
            # 🖼 N · 🔊 N 확인 가능).
            self._store.update_unity_preview(
                unity_import_id,
                asset_count=len(entries),
                image_count=sum(1 for e in entries.values() if e.internal_kind == "image"),
                sound_count=sum(1 for e in entries.values() if e.internal_kind == "sound"),
            )
            self._store.update_unity_state(
                unity_import_id,
                "imported",
                imported_at=now,
            )
            return UnityImportResult(
                pack_id=None,  # 워처가 PackManager 통해 채움
                pack_name=pack_name,
                asset_count=result.files_extracted,
                state="imported",
                error=None,
            )
        except Exception as e:
            self._store.update_unity_state(
                unity_import_id,
                "failed",
                import_error=str(e),
            )
            return UnityImportResult(
                pack_id=None, pack_name=pack_name, asset_count=0,
                state="failed", error=str(e),
            )

    def _write_manifest(self, dest: Path, row) -> None:
        manifest = {
            "name": row.asset_name,
            "vendor": row.publisher or "",
            "license": "Unity Asset Store EULA",
            "source": "unity_asset_store_cache",
            "source_path": str(row.package_path),
            "imported_at": int(time.time()),
            "package_mtime": row.package_mtime,
        }
        (dest / "pack.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
