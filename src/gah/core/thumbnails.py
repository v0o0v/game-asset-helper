"""M4 — lazy 256×256 PNG 썸네일 캐시 (sprite 자산만).

`suggest_packs.samples[].thumbnail_path` 가 가리키는 파일을 lazy 로 생성.
같은 asset_id 두 번 호출 시 캐시 hit (재생성 없음).  사운드/시트는 None.

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
) -> Path | None:
    """sprite 자산만 256×256 PNG 생성.  sound/spritesheet → None.

    캐시 hit (`<cache_dir>/<asset_id>.png` 존재) 시 즉시 반환.
    실패 시 (Pillow 에러 / 파일 미존재) None + log.exception.
    """
    if kind not in ("sprite",):
        return None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.exception("thumbnail cache dir creation failed: %s", cache_dir)
        return None
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
