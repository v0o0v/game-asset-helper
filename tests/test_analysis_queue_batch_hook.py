"""Task 3.5 — AnalysisQueue.pending_by_modality 테스트.
Task 3.6 — dequeue_assets + _skip_ids worker skip 테스트.
"""


def test_pending_by_modality_combines_queue_and_db():
    from assetcache.core.analysis_queue import AnalysisQueue
    from unittest.mock import MagicMock

    store = MagicMock()
    store.count_pending_by_modality.return_value = 5
    q = AnalysisQueue(
        store=store, sprite=MagicMock(),
        spritesheet=MagicMock(), sound=MagicMock(),
    )
    # 큐에 직접 push (실제로는 enqueue_asset 거치는데 단순 test)
    q._queue.put(101)
    q._queue.put(102)
    n = q.pending_by_modality("chat_image")
    assert n == 5 + 2


def test_dequeue_assets_adds_to_skip_ids():
    from assetcache.core.analysis_queue import AnalysisQueue
    from unittest.mock import MagicMock
    q = AnalysisQueue(
        store=MagicMock(), sprite=MagicMock(),
        spritesheet=MagicMock(), sound=MagicMock(),
    )
    count = q.dequeue_assets([1, 2, 3])
    assert count == 3
    assert q._skip_ids == {1, 2, 3}


def test_dequeue_empty_noop():
    from assetcache.core.analysis_queue import AnalysisQueue
    from unittest.mock import MagicMock
    q = AnalysisQueue(
        store=MagicMock(), sprite=MagicMock(),
        spritesheet=MagicMock(), sound=MagicMock(),
    )
    assert q.dequeue_assets([]) == 0
    assert q._skip_ids == set()


def test_enqueue_asset_calls_try_batch_submit():
    from assetcache.core.analysis_queue import AnalysisQueue
    from unittest.mock import MagicMock
    bm = MagicMock()
    q = AnalysisQueue(
        store=MagicMock(), sprite=MagicMock(),
        spritesheet=MagicMock(), sound=MagicMock(),
    )
    q.set_batch_manager(bm)
    q.enqueue_asset(42)
    # M11.2 — 4 modality try_submit (chat_spritesheet 신설)
    modalities = [c.args[0] for c in bm.try_submit.call_args_list]
    assert set(modalities) == {"chat_image", "chat_spritesheet", "chat_audio", "text_embed"}


def test_try_batch_submit_dispatches_in_order():
    """M11.2 — chat_spritesheet 이 chat_image 다음, chat_audio 앞에 위치."""
    from assetcache.core.analysis_queue import AnalysisQueue
    from unittest.mock import MagicMock
    bm = MagicMock()
    q = AnalysisQueue(
        store=MagicMock(), sprite=MagicMock(),
        spritesheet=MagicMock(), sound=MagicMock(),
    )
    q.set_batch_manager(bm)
    q._try_batch_submit()
    modalities = [c.args[0] for c in bm.try_submit.call_args_list]
    assert modalities == ["chat_image", "chat_spritesheet", "chat_audio", "text_embed"]


def test_enqueue_pack_calls_try_batch_submit():
    from assetcache.core.analysis_queue import AnalysisQueue
    from unittest.mock import MagicMock
    store = MagicMock()
    store.pending_assets_for_pack.return_value = []
    bm = MagicMock()
    q = AnalysisQueue(
        store=store, sprite=MagicMock(),
        spritesheet=MagicMock(), sound=MagicMock(),
    )
    q.set_batch_manager(bm)
    q.enqueue_pack(99)
    # M11.2 — 4 modality (chat_spritesheet 신설)
    # M11.10 — race 차단 위해 enqueue_pack 가 큐 push 전/후 두 번 _try_batch_submit
    # 호출 → 4 modality × 2 = 8 try_submit
    assert bm.try_submit.call_count == 8


def test_try_batch_submit_swallows_exceptions():
    """1 modality 실패 → 다른 modality 계속 시도."""
    from assetcache.core.analysis_queue import AnalysisQueue
    from unittest.mock import MagicMock
    bm = MagicMock()
    # M11.2 — 4 modality, 첫 번째만 예외 던지고 나머지 3개는 계속 시도
    bm.try_submit.side_effect = [RuntimeError("oops"), 1, 2, 3]
    q = AnalysisQueue(
        store=MagicMock(), sprite=MagicMock(),
        spritesheet=MagicMock(), sound=MagicMock(),
    )
    q.set_batch_manager(bm)
    q.enqueue_asset(1)  # 예외 안 던짐
    assert bm.try_submit.call_count == 4


def test_no_batch_manager_noop():
    """batch_manager 가 None 이면 try_submit 호출 안 됨."""
    from assetcache.core.analysis_queue import AnalysisQueue
    from unittest.mock import MagicMock
    q = AnalysisQueue(
        store=MagicMock(), sprite=MagicMock(),
        spritesheet=MagicMock(), sound=MagicMock(),
    )
    # batch_manager 안 주입
    q.enqueue_asset(1)  # 예외 없음
    # _batch_manager 가 None 인지 확인
    assert q._batch_manager is None


def test_worker_loop_skips_dequeued_assets(monkeypatch):
    """Worker 가 큐에서 pop 한 asset_id 가 _skip_ids 에 있으면 _handle_one 안 호출 + set 에서 제거."""
    from assetcache.core.analysis_queue import AnalysisQueue
    from unittest.mock import MagicMock
    q = AnalysisQueue(
        store=MagicMock(), sprite=MagicMock(),
        spritesheet=MagicMock(), sound=MagicMock(),
    )
    # 큐에 3개 push
    q._queue.put(1)
    q._queue.put(2)
    q._queue.put(3)
    q.dequeue_assets([1, 3])  # 1, 3 skip
    handled: list[int] = []
    monkeypatch.setattr(q, "_handle_one", lambda aid: handled.append(aid))
    # 워커 한 사이클 시뮬 — _stop_event 가 한 번 돌고 set 되도록
    iterations = [0]
    def is_set_mock():
        iterations[0] += 1
        return iterations[0] > 4  # 4번 iter 후 break (3 asset + 1 추가 안전망)
    monkeypatch.setattr(q._stop_event, "is_set", is_set_mock)
    q._worker_loop()
    assert handled == [2]  # 1, 3 skip / 2 만 handle
    assert q._skip_ids == set()  # 모두 처리됨
