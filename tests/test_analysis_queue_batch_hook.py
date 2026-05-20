"""Task 3.5 — AnalysisQueue.pending_by_modality 테스트."""


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
