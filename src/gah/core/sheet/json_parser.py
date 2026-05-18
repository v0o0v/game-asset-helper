"""M6 — Aseprite + TexturePacker JSON 파서.

자동 형식 판별: meta.app 키워드 → Aseprite/TexturePacker. frames 가 dict
(hash 모드) 면 자연 정렬 후 array 화. duration 평균에서 fps_hint 역산.
M6 spec §4.7 / §4.9.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .types import AnimationSpec, AsepriteAtlas, FrameSpec, TexturePackerAtlas

log = logging.getLogger(__name__)

_DEFAULT_FPS = 12

_NATURAL_RE = re.compile(r"(\d+)|(\D+)")


def _natural_key(s: str) -> list[tuple]:
    """'hero 10' 이 'hero 2' 뒤로 가도록 숫자 부분을 int 로 비교."""
    out: list = []
    for m in _NATURAL_RE.finditer(s):
        digits, text = m.group(1), m.group(2)
        if digits is not None:
            out.append((0, int(digits)))
        else:
            out.append((1, text))
    return out


def _avg_fps_from_durations(durations: list[int]) -> int:
    positives = [d for d in durations if d > 0]
    if not positives:
        return _DEFAULT_FPS
    avg_ms = sum(positives) / len(positives)
    if avg_ms <= 0:
        return _DEFAULT_FPS
    return max(1, round(1000.0 / avg_ms))


def parse(json_path: Path) -> "AsepriteAtlas | TexturePackerAtlas | None":
    """JSON 파일을 읽어 Aseprite 또는 TexturePacker atlas 로 파싱.

    포맷을 판별 못 하거나 frames 가 비어 있으면 None.
    """
    try:
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("sheet JSON load failed: %s — %s", json_path, e)
        return None

    app = ""
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    if isinstance(meta.get("app"), str):
        app = meta["app"].lower()

    frames_field = data.get("frames")
    if not frames_field:
        return None

    # 1) TexturePacker 우선 (frames=list, meta.app 명시)
    if "texturepacker" in app:
        return _parse_texture_packer(frames_field)

    # 2) Aseprite (meta.app 명시 또는 frameTags 존재 또는 모르면 시도)
    if "aseprite" in app or isinstance(meta.get("frameTags"), list):
        return _parse_aseprite(frames_field, meta)

    # 3) meta.app 미명시지만 frames 형태가 Aseprite 와 같으면 시도, 실패 시 None
    try:
        atlas = _parse_aseprite(frames_field, meta)
        if atlas and atlas.frames:
            return atlas
    except (KeyError, TypeError, ValueError):
        pass

    return None


def _parse_aseprite(frames_field: dict | list, meta: dict) -> "AsepriteAtlas | None":
    if isinstance(frames_field, dict):
        ordered_keys = sorted(frames_field.keys(), key=_natural_key)
        frame_items = [(k, frames_field[k]) for k in ordered_keys]
    elif isinstance(frames_field, list):
        frame_items = [(item.get("filename", str(i)), item)
                       for i, item in enumerate(frames_field)]
    else:
        return None

    frames: list[FrameSpec] = []
    for name, item in frame_items:
        f = item.get("frame")
        if not isinstance(f, dict):
            return None
        try:
            frames.append(FrameSpec(
                x=int(f["x"]), y=int(f["y"]),
                w=int(f["w"]), h=int(f["h"]),
                duration_ms=int(item.get("duration", 0) or 0),
                name=str(name),
            ))
        except (KeyError, TypeError, ValueError):
            return None

    if not frames:
        return None

    tags_field = meta.get("frameTags") if isinstance(meta, dict) else None
    tags: list[AnimationSpec] = []
    if isinstance(tags_field, list):
        for t in tags_field:
            if not isinstance(t, dict):
                continue
            try:
                start = int(t["from"])
                end = int(t["to"])
            except (KeyError, TypeError, ValueError):
                continue
            range_durations = [frames[i].duration_ms
                               for i in range(start, min(end + 1, len(frames)))]
            tags.append(AnimationSpec(
                name=str(t.get("name") or "unnamed"),
                start_frame=start,
                end_frame=end,
                fps_hint=_avg_fps_from_durations(range_durations),
                source="json_tag",
            ))

    return AsepriteAtlas(frames=frames, tags=tags)


def _parse_texture_packer(frames_field: dict | list) -> "TexturePackerAtlas | None":
    if isinstance(frames_field, dict):
        ordered_keys = sorted(frames_field.keys(), key=_natural_key)
        frame_items = [(k, frames_field[k]) for k in ordered_keys]
    elif isinstance(frames_field, list):
        frame_items = [(item.get("filename", str(i)), item)
                       for i, item in enumerate(frames_field)]
    else:
        return None

    frames: list[FrameSpec] = []
    for name, item in frame_items:
        f = item.get("frame")
        if not isinstance(f, dict):
            return None
        try:
            frames.append(FrameSpec(
                x=int(f["x"]), y=int(f["y"]),
                w=int(f["w"]), h=int(f["h"]),
                duration_ms=0,
                name=str(name),
            ))
        except (KeyError, TypeError, ValueError):
            return None

    if not frames:
        return None
    return TexturePackerAtlas(frames=frames)
