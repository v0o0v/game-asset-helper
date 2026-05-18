"""AnalysisQueue tests with FakeAnalyzer (no real Ollama / CLIP)."""

from __future__ import annotations

import time
from dataclasses import replace

import pytest

from gah.core.analysis_queue import AnalysisQueue
from gah.core.analyzer.base import AnalyzerInput, AnalyzerResult, SearchableTexts
from gah.core.manifest import PackManifest
from gah.core.store import LabelScore, SoundMeta, SpriteMeta, Store


def _make_pack_with_assets(
    store: Store, paths: list[str], kind: str = "sprite"
) -> tuple[int, list[int]]:
    pack_id = store.upsert_pack(
        "p1", PackManifest(None, None, None, None, None),
        scanned_at=int(time.time()),
    )
    asset_ids = []
    for path in paths:
        a = store.upsert_asset(
            pack_id, path, kind, f"h_{path}", 1,
            added_at=int(time.time()),
        )
        asset_ids.append(a)
    return pack_id, asset_ids


class _FakeSprite:
    """Returns a deterministic sprite AnalyzerResult, optionally raising/delaying."""

    def __init__(self, *, fail: bool = False, delay: float = 0.0) -> None:
        self.fail = fail
        self.delay = delay
        self.calls = 0

    def analyze(self, inp: AnalyzerInput) -> AnalyzerResult:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("boom")
        return AnalyzerResult(
            kind="sprite", state="ok", error=None,
            sprite_meta=SpriteMeta(32, 32, True, True, ["#ff0000"]),
            sound_meta=None,
            labels=[LabelScore("style", "pixel_art", 0.9,
                               "gemma", "primary")],
            searchable=SearchableTexts(for_fts="x", for_embed="y"),
            embedding_vector=b"\x00" * 4, embedding_dim=1,
            embedding_model="nomic-embed-text",
            description="test",
        )


class _FakeSound(_FakeSprite):
    def analyze(self, inp: AnalyzerInput) -> AnalyzerResult:
        res = super().analyze(inp)
        return replace(
            res, kind="sound", sprite_meta=None,
            sound_meta=SoundMeta(
                duration_ms=1000, sample_rate=16000, channels=1,
                loudness_db=-20.0, bpm=None, category="sfx",
                loopable=False, instruments=None, tempo=None,
                intensity=None, genre=None, voice_type=None,
                audio_path_used="native",
            ),
        )


class _FakeSpritesheet(_FakeSprite):
    """M6 — SpritesheetAnalyzer mock. 기본은 _FakeSprite 위임 (시트 검출 실패 케이스).

    calls 는 이 클래스 자신이 analyze() 를 받은 횟수를 샌다.
    sprite 인자를 받으면 내부에서 sprite.analyze() 도 호출해 위임한다.
    """

    def __init__(self, *, sprite=None, fail: bool = False, delay: float = 0.0) -> None:
        super().__init__(fail=fail, delay=delay)
        self._sprite = sprite

    def analyze(self, inp: AnalyzerInput) -> AnalyzerResult:
        if self._sprite is not None:
            return self._sprite.analyze(inp)
        return super().analyze(inp)


def _wait_until(predicate, *, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)


# ── 큐 라우팅 ───────────────────────────────────────────────────────


def test_enqueue_asset_processes_via_correct_analyzer(store, tmp_path) -> None:
    sprite, sound = _FakeSprite(), _FakeSound()
    pack_id, [a1] = _make_pack_with_assets(store, ["a.png"], kind="sprite")
    # M6: sprite kind 는 spritesheet analyzer 를 거쳐 sprite 로 위임
    q = AnalysisQueue(store, sprite=sprite, spritesheet=_FakeSpritesheet(sprite=sprite), sound=sound, concurrency=1)
    q.start()
    try:
        q.enqueue_asset(a1)
        _wait_until(lambda: sprite.calls >= 1)
        assert sprite.calls == 1
        assert sound.calls == 0
    finally:
        q.stop()


def test_enqueue_pack_drains_all_pending_in_pack(store, tmp_path) -> None:
    sprite, sound = _FakeSprite(), _FakeSound()
    pack_id, ids = _make_pack_with_assets(store, ["a.png", "b.png", "c.png"])
    q = AnalysisQueue(store, sprite=sprite, spritesheet=_FakeSpritesheet(sprite=sprite), sound=sound, concurrency=1)
    q.start()
    try:
        q.enqueue_pack(pack_id)
        _wait_until(lambda: sprite.calls >= 3)
        assert sprite.calls == 3
    finally:
        q.stop()


def test_drain_pending_picks_up_existing_pending_rows_on_boot(
    store, tmp_path
) -> None:
    sprite, sound = _FakeSprite(), _FakeSound()
    pack_id, ids = _make_pack_with_assets(store, ["a.png", "b.png"])
    q = AnalysisQueue(store, sprite=sprite, spritesheet=_FakeSpritesheet(sprite=sprite), sound=sound, concurrency=1)
    enqueued = q.drain_pending()
    assert enqueued == 2
    q.start()
    try:
        _wait_until(lambda: sprite.calls >= 2)
        assert sprite.calls == 2
    finally:
        q.stop()


def test_concurrency_one_processes_serially(store, tmp_path) -> None:
    sprite = _FakeSprite(delay=0.2)
    sound = _FakeSound()
    pack_id, ids = _make_pack_with_assets(store, ["a.png", "b.png", "c.png"])
    q = AnalysisQueue(store, sprite=sprite, spritesheet=_FakeSpritesheet(sprite=sprite), sound=sound, concurrency=1)
    q.start()
    try:
        start = time.monotonic()
        q.enqueue_pack(pack_id)
        _wait_until(lambda: sprite.calls >= 3, timeout=4.0)
        elapsed = time.monotonic() - start
        # 3 회 × 0.2s 시리얼 → 이론상 ~0.6s. Windows time.sleep 정밀도
        # 누적 오차 + 워커 polling 간격(0.2s) 영향을 감안해 임계는 0.3s.
        # 핵심은 "비-병렬화" 입증: 동시 처리였다면 0.2s 근처에 끝났을 것.
        assert elapsed >= 0.3
    finally:
        q.stop()


def test_failed_analyzer_marks_state_failed_without_killing_worker(
    store, tmp_path
) -> None:
    sprite = _FakeSprite(fail=True)
    sound = _FakeSound()
    pack_id, [a1, a2] = _make_pack_with_assets(store, ["a.png", "b.png"])
    q = AnalysisQueue(store, sprite=sprite, spritesheet=_FakeSpritesheet(sprite=sprite), sound=sound, concurrency=1)
    q.start()
    try:
        q.enqueue_pack(pack_id)
        _wait_until(lambda: sprite.calls >= 2)
        rows = store.conn.execute(
            "SELECT analysis_state FROM assets WHERE pack_id=?", (pack_id,)
        ).fetchall()
        assert all(r[0] == "failed" for r in rows)
    finally:
        q.stop()


def test_signal_emitted_for_each_finished_asset(store, tmp_path) -> None:
    from PySide6.QtCore import Qt

    sprite, sound = _FakeSprite(), _FakeSound()
    pack_id, ids = _make_pack_with_assets(store, ["a.png", "b.png"])
    q = AnalysisQueue(store, sprite=sprite, spritesheet=_FakeSpritesheet(sprite=sprite), sound=sound, concurrency=1)
    finished: list[int] = []
    # 워커 스레드에서 emit 되는 시그널을 메인 스레드 이벤트 루프 없이 잡기 위해
    # DirectConnection 사용 — 실서비스는 GUI 의 QueuedConnection 으로 받는다.
    q.analysisFinished.connect(
        lambda aid: finished.append(aid), Qt.DirectConnection,
    )
    q.start()
    try:
        q.enqueue_pack(pack_id)
        _wait_until(lambda: len(finished) >= 2)
        assert set(finished) == set(ids)
    finally:
        q.stop()


def test_stop_waits_for_in_flight_analyzer_to_finish(store, tmp_path) -> None:
    sprite = _FakeSprite(delay=0.3)
    sound = _FakeSound()
    pack_id, [a1] = _make_pack_with_assets(store, ["a.png"])
    q = AnalysisQueue(store, sprite=sprite, spritesheet=_FakeSpritesheet(sprite=sprite), sound=sound, concurrency=1)
    q.start()
    q.enqueue_asset(a1)
    time.sleep(0.05)  # 워커가 일을 시작할 시간 확보
    q.stop(timeout=1.0)
    assert sprite.calls == 1


def test_pack_completion_triggers_aggregate_update(store, tmp_path) -> None:
    sprite, sound = _FakeSprite(), _FakeSound()
    pack_id, ids = _make_pack_with_assets(store, ["a.png", "b.png"])
    q = AnalysisQueue(store, sprite=sprite, spritesheet=_FakeSpritesheet(sprite=sprite), sound=sound, concurrency=1)
    q.start()
    try:
        q.enqueue_pack(pack_id)
        _wait_until(lambda: sprite.calls >= 2)
        # 팩의 마지막 분석이 끝나면 aggregate_meta 채워짐
        _wait_until(lambda: store.conn.execute(
            "SELECT aggregate_meta FROM packs WHERE id=?", (pack_id,)
        ).fetchone()[0] is not None)
        row = store.conn.execute(
            "SELECT aggregate_meta FROM packs WHERE id=?", (pack_id,)
        ).fetchone()
        assert row[0] is not None
    finally:
        q.stop()
