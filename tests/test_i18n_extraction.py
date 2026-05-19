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
    """Task 6 후: 영어 msgid 들이 .pot 에 들어 있어야 한다."""
    pot = REPO_ROOT / "src" / "assetcache" / "web" / "locale" / "messages.pot"
    if not pot.exists():
        pytest.skip(".pot 미생성 — pybabel extract 실행 필요")
    body = pot.read_text(encoding="utf-8")
    # Task 6 후: 영어 msgid 들이 들어 있어야 한다.
    for expected in ("Library", "Packs", "Projects", "AssetCacheMCP"):
        assert expected in body, f"msgid 누락: {expected}"
    # 한국어 msgid 가 남아 있으면 Task 6 미완.
    import re
    korean_msgids = re.findall(r'^msgid "[^"]*[가-힣][^"]*"', body, re.MULTILINE)
    assert not korean_msgids, f"한국어 msgid 가 남아 있음: {korean_msgids[:5]}"
