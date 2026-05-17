"""Build the two searchable-text strings for an analyzed asset.

FTS5 wants a verbose text (label/axis prefixed tokens + free-form
descriptions + path/meta) because BM25 thrives on extra words.  The
embedding model wants a *short* semantic summary — top-N labels plus
the asset's own description, capped at ~256 whitespace tokens.

Both texts are derived from the same inputs in one pass so the
analyzer doesn't run the formatting twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Mapping

if TYPE_CHECKING:
    from .store import LabelScore, SoundMeta, SpriteMeta


@dataclass(frozen=True)
class SearchableTexts:
    for_fts: str
    for_embed: str


# 의미 압축 텍스트의 토큰 상한 (공백 단위).
_EMBED_TOKEN_BUDGET = 256
# 임베딩 텍스트에 포함할 라벨 수 — 너무 많으면 의미 평균이 무뎌짐.
_EMBED_TOP_N_LABELS = 5
# 임베딩 노이즈를 줄이려고 점수가 낮은 라벨은 제외.
_EMBED_MIN_SCORE = 0.4


def build_searchable(
    *,
    meta: "SpriteMeta | SoundMeta | None",
    labels: Iterable["LabelScore"],
    label_descriptions: Mapping[tuple[str, str], str],
    description: str,
    rel_path: str,
) -> SearchableTexts:
    labels = list(labels)

    fts_parts: list[str] = []
    embed_parts: list[str] = []

    # ── 경로 + 기술 메타 (FTS 전용) ─────────────────────────────────
    fts_parts.append(f"path:{rel_path}")
    if rel_path:
        # 경로 세그먼트를 별도 토큰으로도 색인 (예: kenney_hero)
        for seg in rel_path.replace("\\", "/").split("/"):
            if seg:
                fts_parts.append(seg)

    if meta is not None:
        for key, value in _meta_tokens(meta):
            fts_parts.append(f"{key}:{value}")

    # ── 축별 라벨 토큰 (FTS) ────────────────────────────────────────
    seen_axes_label: set[tuple[str, str]] = set()
    for lbl in labels:
        key = (lbl.axis, lbl.label)
        if key in seen_axes_label:
            continue
        seen_axes_label.add(key)
        fts_parts.append(f"{lbl.axis}:{lbl.label}")
        fts_parts.append(f"label:{lbl.label}")

    # ── 라벨 description (FTS — BM25 가 자연어 쿼리와 매칭) ──────
    desc_seen: set[tuple[str, str]] = set()
    for lbl in labels:
        key = (lbl.axis, lbl.label)
        if key in desc_seen:
            continue
        desc_seen.add(key)
        desc = label_descriptions.get(key)
        if desc:
            fts_parts.append(f"'{desc}'")

    # ── 에셋 description (양쪽 모두) ────────────────────────────────
    if description:
        fts_parts.append(description)

    # ── 임베딩용 텍스트: 상위 N 라벨 + description ─────────────────
    top_labels = _select_top_labels(labels, n=_EMBED_TOP_N_LABELS)
    if top_labels:
        embed_parts.append(" ".join(lbl.label for lbl in top_labels))
    for lbl in top_labels:
        desc = label_descriptions.get((lbl.axis, lbl.label))
        if desc:
            embed_parts.append(desc)
    if description:
        embed_parts.append(description)

    for_fts = " ".join(p for p in fts_parts if p)
    for_embed = _truncate_tokens(" ".join(embed_parts), _EMBED_TOKEN_BUDGET)
    return SearchableTexts(for_fts=for_fts, for_embed=for_embed)


def _meta_tokens(meta) -> list[tuple[str, str]]:
    from .store import SoundMeta, SpriteMeta  # 지역 import — 순환 회피

    out: list[tuple[str, str]] = []
    if isinstance(meta, SpriteMeta):
        out.append(("width", str(meta.width)))
        out.append(("height", str(meta.height)))
        out.append(("size", str(meta.width)))  # 두 번째 토큰으로도 색인
        if meta.has_alpha:
            out.append(("alpha", "true"))
        if meta.is_pixel_art:
            out.append(("style", "pixel_art_meta"))
    elif isinstance(meta, SoundMeta):
        out.append(("duration_ms", str(meta.duration_ms)))
        out.append(("duration_s", str(meta.duration_ms // 1000)))
        if meta.loopable:
            out.append(("loopable", "true"))
        if meta.bpm:
            out.append(("bpm", str(int(meta.bpm))))
        if meta.tempo:
            out.append(("tempo", meta.tempo))
        if meta.intensity:
            out.append(("intensity", meta.intensity))
    return out


def _select_top_labels(labels: list, n: int) -> list:
    """상위 score 라벨 N개 — 같은 (axis,label) 중복은 한 번만.

    임베딩 텍스트는 의미 압축이 목적이라 자신감 낮은 라벨을 그대로 넣으면
    벡터가 무뎌진다.  ``_EMBED_MIN_SCORE`` 미만은 잘라낸다.
    """
    seen: set[tuple[str, str]] = set()
    candidates = sorted(
        (l for l in labels if l.score >= _EMBED_MIN_SCORE),
        key=lambda l: l.score, reverse=True,
    )
    picked: list = []
    for lbl in candidates:
        key = (lbl.axis, lbl.label)
        if key in seen:
            continue
        seen.add(key)
        picked.append(lbl)
        if len(picked) >= n:
            break
    return picked


def _truncate_tokens(text: str, budget: int) -> str:
    tokens = text.split()
    if len(tokens) <= budget:
        return text
    return " ".join(tokens[:budget])


def build_query_text(query: str, kind: str | None = None) -> str:
    """M3 검색 쿼리를 임베딩용 짧은 텍스트로 빌드.

    파일명·라벨 prefix 없이 자연어만 — 자산 임베딩의 `for_embed` 와 같은
    벡터 공간에서 비교 가능하도록 형식을 맞춘다.
    """
    parts: list[str] = []
    if query:
        parts.append(query.strip())
    if kind:
        parts.append(kind)
    return _truncate_tokens(" ".join(parts), _EMBED_TOKEN_BUDGET)
