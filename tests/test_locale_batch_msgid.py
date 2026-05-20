"""Phase 5 task 5.5 — batch 18 msgid 가 ko/en .po 양쪽에 존재 검증."""

import pytest
from pathlib import Path


BATCH_MSGIDS = [
    "Batch analysis",
    "Threshold",
    "Polling interval",
    "In-progress batch jobs",
    "Submitted %d minutes ago",
    "image chain first is %s — batch enabled",
    "image chain first is %s — batch disabled. Set chain[image][0] to gemini.",
    "Cancel all",
    "Auto",
    "Forced on",
    "Forced off",
    "Batch mode (Gemini): %s",
    "Analysis progress",
    "Summary",
    "Interactive queue",
    "Batch jobs",
    "Recent failures",
    "Worker #%d (%.1fs elapsed)",
]


@pytest.mark.parametrize("lang", ["ko", "en"])
@pytest.mark.parametrize("msgid", BATCH_MSGIDS)
def test_msgid_present(lang, msgid):
    p = Path("src/assetcache/web/locale") / lang / "LC_MESSAGES" / "messages.po"
    content = p.read_text(encoding="utf-8")
    assert f'msgid "{msgid}"' in content, f"missing in {lang}: {msgid}"
