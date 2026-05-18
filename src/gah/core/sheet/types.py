"""M6 — sheet 검출·파싱 결과 데이터클래스.

비기록 후속 분석기 / MCP 도구 / 테스트가 공유. ``frozen=True`` 로 불변
보장. M6 spec §4.3 / §4.9.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameSpec:
    """단일 프레임의 픽셀 박스 + (옵션) 표시 시간 + 원본 이름."""

    x: int
    y: int
    w: int
    h: int
    duration_ms: int  # 0 이면 정보 없음 — fps_hint 평균 계산에서 제외
    name: str  # Aseprite hash 모드의 원본 키 또는 array 모드 인덱스 문자열


@dataclass(frozen=True)
class AnimationSpec:
    """이름 붙은 애니메이션 = 시트 내 프레임 range."""

    name: str  # animation 라벨 (walk/idle/...)
    start_frame: int
    end_frame: int  # inclusive
    fps_hint: int  # 1 이상
    source: str  # 'json_tag' | 'gemma_inferred' | 'user'


@dataclass(frozen=True)
class GridLayout:
    """균일 격자 시트의 행·열·프레임 크기."""

    rows: int
    cols: int
    frame_w: int
    frame_h: int

    @property
    def frame_count(self) -> int:
        return self.rows * self.cols


@dataclass(frozen=True)
class AsepriteAtlas:
    """Aseprite export 파싱 결과 — frames + (선택) frameTags."""

    frames: list[FrameSpec]
    tags: list[AnimationSpec]


@dataclass(frozen=True)
class TexturePackerAtlas:
    """TexturePacker export — frames 만."""

    frames: list[FrameSpec]
