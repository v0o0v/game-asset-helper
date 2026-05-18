"""M7 테스트용 .unitypackage fixture 생성 helper.

``make_fixture_unitypackage`` 는 3 GUID 디렉터리를 가진 최소 tar.gz 파일을
생성한다.  각 GUID 폴더 내에는 ``asset``, ``asset.meta``, ``pathname`` 세 파일이
있어 실제 Unity Asset Store 캐시 구조를 모방한다.

PNG_BYTES: 1×1 px RGBA PNG (유효 최소 포맷, Pillow 가 읽을 수 있음)
WAV_BYTES: PCM16 mono 44100Hz 0-sample WAV (유효 최소 포맷, soundfile 이 읽을 수 있음)
PSD_BYTES: 최소 PSD 헤더 (Photoshop 서명 "8BPS" + padding)
"""

from __future__ import annotations

import io
import tarfile
import time
from pathlib import Path

# ── 최소 유효 바이트 ──────────────────────────────────────────────────

# 1×1 RGBA PNG (Pillow 호환)
PNG_BYTES = bytes.fromhex(
    "89504E470D0A1A0A"                        # PNG signature
    "0000000D49484452"                        # IHDR chunk length + type
    "00000001"                                # width = 1
    "00000001"                                # height = 1
    "08060000001F15C489"                      # bit depth=8, RGBA, CRC
    "0000000A49444154789C6300010000000500"    # IDAT chunk (zlib compressed)
    "010D0A2DB4"                              # CRC
    "0000000049454E44AE426082"               # IEND chunk
)

# PCM16 mono 44100Hz 0 samples WAV
WAV_BYTES = (
    b"RIFF\x24\x00\x00\x00"   # RIFF header (36 bytes 이후 = 헤더만)
    b"WAVE"                    # format
    b"fmt \x10\x00\x00\x00"   # fmt chunk (16 bytes)
    b"\x01\x00"               # PCM
    b"\x01\x00"               # mono
    b"\x44\xac\x00\x00"       # 44100 Hz
    b"\x88\x58\x01\x00"       # byte rate = 44100 * 1 * 2
    b"\x02\x00"               # block align
    b"\x10\x00"               # bits per sample = 16
    b"data\x00\x00\x00\x00"   # data chunk, 0 bytes
)

# 최소 PSD 헤더 (8BPS v1 서명)
PSD_BYTES = b"8BPS\x00\x01" + b"\x00" * 20


# ── helper ────────────────────────────────────────────────────────────


def _write_member(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    """data 를 name 경로로 tar 아카이브에 추가."""
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = int(time.time())
    tar.addfile(info, io.BytesIO(data))


def make_fixture_unitypackage(dest: Path, *, include_psd: bool = True) -> Path:
    """dest 경로에 테스트용 .unitypackage 파일을 생성하고 경로를 반환.

    생성 구조::

        abc123/asset          ← PNG 바이트
        abc123/asset.meta     ← 빈 meta 텍스트
        abc123/pathname       ← "Assets/Sprites/idle.png"
        def456/asset          ← WAV 바이트
        def456/asset.meta     ← 빈 meta 텍스트
        def456/pathname       ← "Assets/Sounds/jump.wav"
        psd789/asset          ← PSD 바이트  (include_psd=True 일 때만)
        psd789/asset.meta     ← 빈 meta 텍스트  (include_psd=True 일 때만)
        psd789/pathname       ← "Assets/Sprites/source.psd"  (include_psd=True 일 때만)

    Args:
        dest: 생성할 .unitypackage 파일 경로 (부모 디렉터리는 미리 존재해야 함).
        include_psd: True 이면 psd789 GUID 폴더를 포함 (필터 검증용).

    Returns:
        생성된 파일의 절대 경로.
    """
    entries = [
        ("abc123", PNG_BYTES, "Assets/Sprites/idle.png"),
        ("def456", WAV_BYTES, "Assets/Sounds/jump.wav"),
    ]
    if include_psd:
        entries.append(("psd789", PSD_BYTES, "Assets/Sprites/source.psd"))

    with tarfile.open(str(dest), mode="w:gz") as tar:
        for guid, asset_bytes, pathname in entries:
            _write_member(tar, f"{guid}/asset", asset_bytes)
            _write_member(tar, f"{guid}/asset.meta", b"fileFormatVersion: 2\n")
            _write_member(tar, f"{guid}/pathname", pathname.encode("utf-8"))

    return dest.resolve()
