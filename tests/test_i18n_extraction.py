"""M8 — pybabel extract 가 주요 키를 잡아내는지 smoke."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    subprocess.run(
        [sys.executable, "-c", "import babel"],
        capture_output=True,
    ).returncode != 0,
    reason="Babel 미설치 환경",
)
def test_babel_cfg_exists():
    assert (REPO_ROOT / "babel.cfg").exists()


def test_pot_has_known_msgids(tmp_path):
    """현재 hardcode 된 핵심 한국어가 .pot 에 들어가는지.

    Task 6 이 끝나면 영어 msgid 로 바뀌므로 이 테스트도 그때 갱신한다.
    """
    pot = REPO_ROOT / "src" / "gah" / "web" / "locale" / "messages.pot"
    if not pot.exists():
        pytest.skip(".pot 미생성 — pybabel extract 실행 필요")
    body = pot.read_text(encoding="utf-8")
    # Task 5 시점: 한국어 msgid 가 다수 — Task 6 후 'Library' 등 영어 msgid 로 교체됨.
    # 둘 중 하나가 있으면 통과.
    assert "라이브러리" in body or "Library" in body
