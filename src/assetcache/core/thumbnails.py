"""M4/M6 — lazy 256×256 PNG 썸네일 캐시 (이미지 자산).

`suggest_packs.samples[].thumbnail_path` 가 가리키는 파일을 lazy 로 생성.
같은 asset_id 두 번 호출 시 캐시 hit (재생성 없음).  사운드는 None.

M6: sprite + spritesheet 모두 썸네일 생성 (시트는 전체를 256 안에 축소).

DESIGN §6.5: 스프라이트 샘플은 `cache/thumbnails/<asset_id>.png` (256×256
사전 생성)을 가리키는 절대 경로를 돌려준다.  M4 v1 은 사전 생성 대신 lazy.
"""

from __future__ import annotations

import logging
from pathlib import Path


log = logging.getLogger(__name__)


def ensure_thumbnail(
    asset_path: Path,
    kind: str,
    cache_dir: Path,
    asset_id: int,
    *,
    max_size: int = 256,
    file_hash: str | None = None,
) -> Path | None:
    """sprite + spritesheet 자산 256×256 PNG 생성.  sound → None.

    M11.10 — cache key 에 ``file_hash`` 의 첫 12자 포함.  같은 asset_id 가
    다른 file 을 가리키게 된 경우 (DB reset / re-import) stale cache 차단.
    file_hash=None 이면 legacy ``<asset_id>.png`` path 유지 (backward compat).

    실패 시 (Pillow 에러 / 파일 미존재) None + log.exception.
    """
    if kind not in ("sprite", "spritesheet"):
        return None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.exception("thumbnail cache dir creation failed: %s", cache_dir)
        return None
    if file_hash:
        out = cache_dir / f"{asset_id}_{file_hash[:12]}.png"
    else:
        out = cache_dir / f"{asset_id}.png"
    if out.exists():
        return out
    try:
        from PIL import Image
        with Image.open(asset_path) as img:
            img.thumbnail((max_size, max_size))
            img.save(out, "PNG")
        return out
    except Exception:
        log.exception("thumbnail generation failed: asset_id=%s path=%s",
                      asset_id, asset_path)
        return None
