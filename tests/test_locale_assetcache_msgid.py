"""ko/en .po catalog 의 M10 Phase 2.7 (PyPI 신버전 알림) msgid 정합성 검사.

신규 msgid 가 한쪽 언어에만 추가되거나 컴파일이 누락된 회귀를 빠르게 잡는다.
Phase 1.7 (마이그레이션 배너) msgid 3건은 v0.1.1 yagni-clean 에서 제거됨.
"""
from __future__ import annotations

from pathlib import Path

import pytest

LOCALE_ROOT = (
    Path(__file__).parent.parent / "src" / "assetcache" / "web" / "locale"
)

NEW_MSGIDS = [
    # Phase 2.7 (PyPI 신버전 알림) — 영어 msgid 3건
    "available",
    "Copy",
    "Upgrade command copied to clipboard",
]


def _load_po(path: Path) -> set[str]:
    """Single-line `msgid "..."` 항목만 추출.

    검사 대상 msgid 는 모두 single-line 이라 본 단순 파서로 충분하다.
    multi-line msgid 가 필요한 시점에는 babel.messages.pofile 로 보강한다.
    """
    msgids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith('msgid "') and line.endswith('"'):
            msgid = line[len('msgid "'):-1]
            if msgid:  # header (msgid "") 제외
                msgids.add(msgid)
    return msgids


@pytest.mark.parametrize("lang", ["ko", "en"])
@pytest.mark.parametrize("msgid", NEW_MSGIDS)
def test_msgid_present_in_locale(lang: str, msgid: str) -> None:
    po = LOCALE_ROOT / lang / "LC_MESSAGES" / "messages.po"
    assert po.exists(), f"{po} 가 존재하지 않습니다."
    msgids = _load_po(po)
    assert (
        msgid in msgids
    ), f"신규 msgid {msgid!r} 가 {lang}/messages.po 에 누락됨."
