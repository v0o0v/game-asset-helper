"""M6 — 8칸 1행 합성 미리보기."""
from __future__ import annotations

from PIL import Image

from gah.core.sheet.preview import make_preview_composite, sample_indices
from gah.core.sheet.types import FrameSpec


def _sheet_with_frames(frame_count: int, fw: int = 32, fh: int = 32) -> tuple[Image.Image, list[FrameSpec]]:
    img = Image.new("RGBA", (frame_count * fw, fh), (0, 0, 0, 0))
    frames: list[FrameSpec] = []
    for i in range(frame_count):
        tile = Image.new("RGBA", (fw, fh),
                         (((i * 30) % 255), 100, 50, 255))
        img.paste(tile, (i * fw, 0))
        frames.append(FrameSpec(x=i * fw, y=0, w=fw, h=fh,
                                duration_ms=100, name=str(i)))
    return img, frames


def test_8_frames_used_as_is():
    img, frames = _sheet_with_frames(8)
    composite = make_preview_composite(img, frames, max_size=512)
    # 8 × 32 = 256 wide × 32 high
    assert composite.size == (8 * 32, 32)


def test_16_frames_linear_stride():
    indices = sample_indices(16, 8)
    assert indices == [0, 2, 4, 6, 9, 11, 13, 15]


def test_4_frames_used_as_is():
    img, frames = _sheet_with_frames(4)
    composite = make_preview_composite(img, frames, max_size=512)
    assert composite.size == (4 * 32, 32)


def test_composite_respects_max_size():
    # 32 프레임 × 512px 가로폭 = 너무 큼 → max=200 으로 축소
    img, frames = _sheet_with_frames(32, fw=64, fh=64)
    composite = make_preview_composite(img, frames, max_size=200)
    assert max(composite.size) <= 200


def test_rgba_preserved():
    img, frames = _sheet_with_frames(8)
    composite = make_preview_composite(img, frames, max_size=512)
    assert composite.mode in ("RGBA", "RGB")


def test_sample_indices_k_equals_1():
    # k=1 은 첫 프레임만 — formula 의 0 나눗셈 회피
    assert sample_indices(10, 1) == [0]
    assert sample_indices(1, 1) == [0]
    assert sample_indices(0, 1) == []


def test_sample_indices_k_zero_or_negative():
    assert sample_indices(10, 0) == []
    assert sample_indices(10, -3) == []
