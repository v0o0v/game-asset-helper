"""M7 — .unitypackage 파서 + 추출 (D4, D5).

.unitypackage = gzip tar. 각 GUID 디렉터리에:
  <guid>/asset      — 실제 자산 바이트
  <guid>/asset.meta — Unity 메타 (YAML, v1 미사용)
  <guid>/pathname   — 원본 Unity 내부 경로 (텍스트)

parse_pathnames(): pathname 만 읽어 GUID → UnityPackageEntry 매핑.
                   이미지/사운드 6 확장자만 필터.
extract_targets(): 선택된 GUID 의 asset 파일을 dest_dir 안 pathname
                   경로로 복원 (물리 복사).
"""

from __future__ import annotations

import tarfile
from pathlib import Path

from gah.core.unity_import.types import ExtractResult, UnityPackageEntry

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_SOUND_EXTS = {".wav", ".ogg", ".mp3"}


def _classify(pathname: str) -> str | None:
    ext = Path(pathname).suffix.lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _SOUND_EXTS:
        return "sound"
    return None


def _read_member_text(tar: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    """pathname 텍스트 읽기. Unity 가 일부 패키지에서 "<경로>\\n<flag>" 형식
    으로 저장 (둘째 줄에 "00" 같은 메타) — 첫 줄만 가져옴. 그러지 않으면
    suffix 가 ".png\\n00" 같은 형태가 되어 확장자 매칭 실패."""
    f = tar.extractfile(member)
    if f is None:
        return ""
    text = f.read().decode("utf-8", errors="replace")
    # 첫 줄만 — Unity 일부 패키지의 "경로\nflag" 패턴 회피.
    return text.split("\n", 1)[0].strip()


def parse_pathnames(package_path: Path) -> dict[str, UnityPackageEntry]:
    """GUID → UnityPackageEntry. 이미지/사운드 6 확장자만 필터링."""
    entries: dict[str, UnityPackageEntry] = {}
    pathnames: dict[str, str] = {}
    asset_sizes: dict[str, int] = {}
    with tarfile.open(package_path, mode="r:gz") as tar:
        for member in tar:
            parts = member.name.split("/")
            if len(parts) != 2:
                continue
            guid, leaf = parts
            if leaf == "pathname":
                pathnames[guid] = _read_member_text(tar, member)
            elif leaf == "asset":
                asset_sizes[guid] = member.size
    for guid, pathname in pathnames.items():
        kind = _classify(pathname)
        if kind is None:
            continue
        if guid not in asset_sizes:
            continue
        entries[guid] = UnityPackageEntry(
            guid=guid,
            pathname=pathname,
            internal_kind=kind,  # type: ignore[arg-type]
            size=asset_sizes[guid],
        )
    return entries


def extract_targets(
    package_path: Path,
    dest_dir: Path,
    target_guids: list[str],
) -> ExtractResult:
    """target_guids 의 asset 파일을 dest_dir/<pathname> 으로 물리 복사."""
    if not target_guids:
        return ExtractResult(files_extracted=0, bytes_written=0)
    target_set = set(target_guids)
    dest_dir.mkdir(parents=True, exist_ok=True)
    # pathname 먼저 수집
    pathnames: dict[str, str] = {}
    with tarfile.open(package_path, mode="r:gz") as tar:
        for member in tar:
            parts = member.name.split("/")
            if len(parts) != 2 or parts[0] not in target_set:
                continue
            if parts[1] == "pathname":
                pathnames[parts[0]] = _read_member_text(tar, member)
    files_extracted = 0
    bytes_written = 0
    with tarfile.open(package_path, mode="r:gz") as tar:
        for member in tar:
            parts = member.name.split("/")
            if len(parts) != 2 or parts[0] not in target_set or parts[1] != "asset":
                continue
            guid = parts[0]
            pathname = pathnames.get(guid)
            if pathname is None or _classify(pathname) is None:
                continue
            out_path = dest_dir / pathname
            out_path.parent.mkdir(parents=True, exist_ok=True)
            f = tar.extractfile(member)
            if f is None:
                continue
            data = f.read()
            out_path.write_bytes(data)
            files_extracted += 1
            bytes_written += len(data)
    return ExtractResult(files_extracted=files_extracted, bytes_written=bytes_written)
