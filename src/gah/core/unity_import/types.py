"""M7 — Unity Asset Store 임포트 관련 frozen dataclass 7종.

로직 없이 데이터 구조 정의만 담는다.  모든 클래스는 frozen=True 이므로
hash 가 보장되고 dict key 나 set 원소로 쓸 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class UnityPackagePath:
    """캐시 디렉터리에서 발견된 .unitypackage 파일 하나를 나타낸다.

    publisher / category 는 캐시 경로 구조에서 추론되며,
    경로 형태에 따라 None 이 될 수 있다.
    """

    abs_path: Path
    publisher: str | None
    category: str | None
    asset_name: str
    size: int          # 바이트
    mtime: int         # Unix timestamp


@dataclass(frozen=True)
class UnityPackageEntry:
    """패키지 내부 GUID 하나에 해당하는 에셋 엔트리.

    internal_kind 은 ``asset_kind.py`` 의 sprite/sound 분류와 달리
    패키지 내부 분류('image' | 'sound') 를 나타낸다.
    """

    guid: str
    pathname: str                              # 예: "Assets/Sprites/idle.png"
    internal_kind: Literal["image", "sound"]
    size: int


@dataclass(frozen=True)
class UnityPackagePreview:
    """패키지 전체 내용을 파싱하지 않고 빠르게 미리보기한 요약.

    sample_pathnames 는 최대 N 개의 대표 경로 샘플이다.
    """

    asset_count: int
    image_count: int
    sound_count: int
    sample_pathnames: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnityScanResult:
    """캐시 디렉터리 스캔 한 회의 결과.

    불변식: new + updated + unchanged + removed == scanned.
    """

    scanned: int
    new: int
    updated: int
    unchanged: int
    removed: int
    cache_path: Path
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnityImportResult:
    """패키지 한 개를 GAH 라이브러리로 임포트한 결과."""

    pack_id: int | None   # 성공 시 생성된 팩 ID, 실패 시 None
    pack_name: str
    asset_count: int
    state: Literal["imported", "failed"]
    error: str | None = None


@dataclass(frozen=True)
class ExtractResult:
    """패키지에서 파일을 추출한 결과 통계."""

    files_extracted: int
    bytes_written: int


@dataclass(frozen=True)
class UnityImportRecord:
    """``unity_imports`` DB 테이블 한 행을 나타내는 read 전용 뷰.

    import_state 전이:
        discovered → previewed → import_pending → imported
                                                 ↘ failed
                                  → skipped
    """

    id: int
    package_path: Path
    publisher: str | None
    category: str | None
    asset_name: str
    package_size: int
    package_mtime: int
    preview_asset_count: int | None
    preview_image_count: int | None
    preview_sound_count: int | None
    preview_inspected_at: int | None
    pack_id: int | None
    import_state: Literal[
        "discovered",
        "previewed",
        "import_pending",
        "imported",
        "failed",
        "skipped",
    ]
    import_error: str | None
    imported_at: int | None
    first_seen_at: int
    last_scanned_at: int
