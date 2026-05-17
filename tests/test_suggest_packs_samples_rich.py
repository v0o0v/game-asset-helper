"""M4 — `suggest_packs.samples` 풍부화 (`thumbnail_path` + `preview_blurb`).

v1 정책 (M5+ 가 description 통합 시 갱신):
- sprite sample → `thumbnail_path` = lazy 256×256 PNG 캐시
- sound/spritesheet sample → `thumbnail_path = None`
- `preview_blurb` 는 top-2 라벨 (`"axis=label · axis=label"`) — description
  추출은 v1 범위 밖.
- `include_thumbnails=false` → `thumbnail_path` 안 채움.
- 캐시 디렉터리 자동 생성.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _enrich(populated_store, tmp_thumbnail_cache,
            *, include_thumbnails=True, sprite=True, library_root: "Path | None" = None):
    """`enrich_sample(asset_row, store, cache_dir, library_root, include_thumbnails)` 결과 dict.

    library_root 기본값: tmp_thumbnail_cache.parent.parent (tmp_path).
    sprite_file_on_disk fixture 가 asset.path 를 절대경로로 업데이트하므로
    library_root / absolute_path → absolute_path (pathlib Windows 동작).
    """
    from gah.core.suggest_packs import enrich_sample

    store, ids = populated_store
    aid = ids["hero"] if sprite else ids["bgm_loop"]
    asset_row = store.get_asset_by_id(aid)
    root = library_root or tmp_thumbnail_cache.parent.parent
    return enrich_sample(asset_row, store, tmp_thumbnail_cache,
                         library_root=root,
                         include_thumbnails=include_thumbnails), aid, store


@pytest.fixture
def tmp_thumbnail_cache(tmp_path: Path) -> Path:
    """임시 thumbnail 캐시 디렉터리 (존재하지 않는 상태)."""
    return tmp_path / "cache" / "thumbnails"


@pytest.fixture
def sprite_file_on_disk(populated_store, tmp_path: Path):
    """populated_store 의 hero.png 가 실제 디스크 파일이 되도록 셋업.

    `populated_store` 는 path 만 박아둔 in-DB 시드라 thumbnail 생성에 필요한
    실제 PNG 파일이 없다.  여기서 그 path 위치에 32×32 PNG 를 생성한다.
    """
    from PIL import Image

    store, ids = populated_store
    asset = store.get_asset_by_id(ids["hero"])
    target = tmp_path / asset.path
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (256, 256), color=(120, 200, 60)).save(target, "PNG")
    # store 의 path 가 상대라면 작업 디렉터리 변경이 까다로움 — 절대로 박는다.
    store.conn.execute(
        "UPDATE assets SET path = ? WHERE id = ?",
        (str(target), ids["hero"]),
    )
    store.conn.commit()
    return target


def test_sprite_sample_has_thumbnail_path(
    populated_store, tmp_thumbnail_cache, sprite_file_on_disk
) -> None:
    out, _, _ = _enrich(populated_store, tmp_thumbnail_cache,
                         include_thumbnails=True, sprite=True)
    assert out["thumbnail_path"] is not None
    assert Path(out["thumbnail_path"]).exists()


def test_sound_sample_has_null_thumbnail_with_blurb(
    populated_store, tmp_thumbnail_cache
) -> None:
    out, _, _ = _enrich(populated_store, tmp_thumbnail_cache,
                         include_thumbnails=True, sprite=False)
    # 사운드 → 썸네일 없음.
    assert out["thumbnail_path"] is None
    # blurb 는 top-2 라벨 (sound_category=bgm · sound_mood=calm 등) — 비지 않아야.
    assert out["preview_blurb"]
    assert isinstance(out["preview_blurb"], str)


def test_blurb_is_top2_labels(populated_store, tmp_thumbnail_cache) -> None:
    """blurb 가 top-2 라벨 형식 `axis=label · axis=label` 인지."""
    out, _, _ = _enrich(populated_store, tmp_thumbnail_cache,
                         include_thumbnails=False, sprite=False)
    blurb = out["preview_blurb"] or ""
    # bgm_loop 는 sound_category=bgm + sound_mood=calm 두 라벨.
    # blurb 에 axis=label 포맷이 적어도 한 쌍 등장.
    assert "=" in blurb
    # 두 라벨이 있으면 ' · ' 구분자 존재.
    if " · " in blurb:
        parts = blurb.split(" · ")
        assert all("=" in p for p in parts)


def test_blurb_format_is_axis_equals_label_separator(
    populated_store, tmp_thumbnail_cache
) -> None:
    """단일 라벨만 있는 자산 — blurb = `axis=label` 한 쌍."""
    from gah.core.suggest_packs import enrich_sample

    store, ids = populated_store
    # jump 자산은 sound_category=sfx 1 라벨 — 단일 페어 케이스.
    asset_row = store.get_asset_by_id(ids["jump"])
    root = tmp_thumbnail_cache.parent.parent
    out = enrich_sample(asset_row, store, tmp_thumbnail_cache,
                        library_root=root,
                        include_thumbnails=False)
    blurb = out["preview_blurb"] or ""
    assert "=" in blurb
    assert "sound_category" in blurb or "sfx" in blurb


def test_include_thumbnails_false_skips_thumbnail_generation(
    populated_store, tmp_thumbnail_cache, sprite_file_on_disk
) -> None:
    """`include_thumbnails=False` → `thumbnail_path` 안 채움 + 캐시 파일 미생성."""
    out, _, _ = _enrich(populated_store, tmp_thumbnail_cache,
                         include_thumbnails=False, sprite=True)
    assert out["thumbnail_path"] is None
    # 캐시 디렉터리도 만들어지지 않음 (lazy 정책).
    assert not tmp_thumbnail_cache.exists() or not any(tmp_thumbnail_cache.iterdir())


def test_thumbnail_cache_directory_auto_created(
    populated_store, tmp_thumbnail_cache, sprite_file_on_disk
) -> None:
    """include_thumbnails=True 첫 호출 시 캐시 디렉터리 없으면 자동 생성."""
    assert not tmp_thumbnail_cache.exists()
    _, _, _ = _enrich(populated_store, tmp_thumbnail_cache,
                       include_thumbnails=True, sprite=True)
    assert tmp_thumbnail_cache.is_dir()
