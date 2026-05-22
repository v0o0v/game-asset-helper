"""M11.8 — mood 시드 neutral/minimalist 비활성화 마이그.

`LabelRegistry.bootstrap()` 가 `DISABLED_BY_DEFAULT` 에 등록된 토큰을 자동으로
`is_enabled=0` 으로 마크하되, 사용자가 명시적으로 재활성한 토큰은 그대로
존중한다.  `meta` 테이블의 `disabled_by_default_seen:{axis}:{label}` 마커로
"한 번이라도 본 (axis, label)" 을 추적해 idempotent + user override 보존.

⚠️ `palette.neutral` 은 M11.6 tone group enum 의 핵심 토큰이므로 절대 비활성화
대상이 아님 — axis 격리.
"""
from __future__ import annotations

from assetcache.core.labels import DISABLED_BY_DEFAULT, LabelRegistry
from assetcache.core.store import Store


# ── 상수 자체 ────────────────────────────────────────────────────────


def test_disabled_by_default_targets_mood_neutral_and_minimalist() -> None:
    """`DISABLED_BY_DEFAULT` 는 mood.neutral + mood.minimalist 만 등록.

    palette.neutral 은 M11.6 tone group 핵심이므로 절대 포함되면 안 된다.
    """
    assert DISABLED_BY_DEFAULT == {"mood": {"neutral", "minimalist"}}


# ── fresh DB bootstrap ─────────────────────────────────────────────────


def test_bootstrap_disables_mood_neutral_on_fresh_db(store: Store) -> None:
    """fresh DB bootstrap → mood.neutral `is_enabled=0`."""
    LabelRegistry(store).bootstrap()
    row = store.conn.execute(
        "SELECT enabled FROM labels WHERE axis = 'mood' AND label = 'neutral'"
    ).fetchone()
    assert row is not None, "mood.neutral 시드 누락"
    assert row[0] == 0


def test_bootstrap_disables_mood_minimalist_on_fresh_db(store: Store) -> None:
    """fresh DB bootstrap → mood.minimalist `is_enabled=0`."""
    LabelRegistry(store).bootstrap()
    row = store.conn.execute(
        "SELECT enabled FROM labels WHERE axis = 'mood' AND label = 'minimalist'"
    ).fetchone()
    assert row is not None, "mood.minimalist 시드 누락"
    assert row[0] == 0


def test_bootstrap_keeps_palette_neutral_enabled(store: Store) -> None:
    """⚠️ `palette.neutral` 은 절대 비활성화 X — M11.6 tone group enum 핵심.

    `DISABLED_BY_DEFAULT` 가 axis 단위로 격리돼야 함을 검증.
    """
    LabelRegistry(store).bootstrap()
    row = store.conn.execute(
        "SELECT enabled FROM labels WHERE axis = 'palette' AND label = 'neutral'"
    ).fetchone()
    assert row is not None, "palette.neutral 시드 누락"
    assert row[0] == 1, "palette.neutral 비활성화 → M11.6 tone group enum 파괴 위험"


def test_bootstrap_keeps_other_mood_tokens_enabled(store: Store) -> None:
    """mood axis 의 다른 토큰 (heroic/dark/playful 등) 은 영향 없음."""
    LabelRegistry(store).bootstrap()
    rows = store.conn.execute(
        "SELECT label, enabled FROM labels WHERE axis = 'mood' AND label IN "
        "('heroic', 'dark', 'playful', 'calm', 'mysterious', 'intense')"
    ).fetchall()
    assert len(rows) == 6, "M11.8 회귀: prompt enum 6 mood 토큰 누락"
    for _label, enabled in rows:
        assert enabled == 1


# ── idempotency + user override 보존 ──────────────────────────────────


def test_bootstrap_preserves_user_reenable_on_second_call(store: Store) -> None:
    """사용자가 `mood.neutral` 을 `enable=1` 로 복원 후 bootstrap 재호출 시
    user override 가 보존돼야 함 (마커 기반 idempotency).
    """
    registry = LabelRegistry(store)
    registry.bootstrap()

    # 사용자가 mood.neutral 을 명시적으로 enable=1 로 복원
    registry.set_enabled("mood", "neutral", True)
    enabled_after_user = store.conn.execute(
        "SELECT enabled FROM labels WHERE axis='mood' AND label='neutral'"
    ).fetchone()[0]
    assert enabled_after_user == 1

    # bootstrap 재호출 — 마커가 이미 있으므로 disable 안 함
    registry.bootstrap()
    enabled_after_second_bootstrap = store.conn.execute(
        "SELECT enabled FROM labels WHERE axis='mood' AND label='neutral'"
    ).fetchone()[0]
    assert enabled_after_second_bootstrap == 1, (
        "user reenable must survive subsequent bootstrap calls"
    )


def test_bootstrap_disables_on_existing_db_first_run(store: Store) -> None:
    """기존 DB 에 시드만 있고 마커가 없는 상태 (M11.7 이전 상태) 에서
    `bootstrap()` 호출 시 DISABLED_BY_DEFAULT 토큰이 `is_enabled=0` 으로
    마이그된다.

    bootstrap 의 "table not empty → return 0" 조기 종료 분기와 별개로
    disable 패스는 항상 한 번은 돌아야 함.
    """
    # M11.7 상태 시뮬: 시드만 들어 있고 disable 패스 안 돈 상태를 만들기
    # 위해 raw INSERT 로 mood.neutral 을 enabled=1 로 박는다.
    import time

    now = int(time.time())
    store.conn.execute(
        "INSERT INTO labels (axis, label, description, source, enabled,"
        " created_at, updated_at)"
        " VALUES ('mood', 'neutral', 'pre-M11.8 row', 'seed', 1, ?, ?)",
        (now, now),
    )
    # 이 단계에선 마커가 없으므로 disable 패스가 동작해야 함.

    LabelRegistry(store).bootstrap()
    row = store.conn.execute(
        "SELECT enabled FROM labels WHERE axis='mood' AND label='neutral'"
    ).fetchone()
    assert row is not None
    assert row[0] == 0, (
        "기존 DB 의 M11.7 이전 mood.neutral 행도 첫 M11.8 bootstrap 에서 "
        "disable 돼야 한다"
    )
