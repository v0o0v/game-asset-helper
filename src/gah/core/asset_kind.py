"""Extension-based classification of library files.

Returns the coarse ``kind`` used in the ``assets.kind`` column of the
schema (``DESIGN.md §5.1``).  M1 only distinguishes ``sprite`` from
``sound`` — the spritesheet split happens in M4 when the analyzer can
look at the pixels.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

SUPPORTED_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".png", ".webp", ".jpg", ".jpeg"})
SUPPORTED_AUDIO_EXTENSIONS: frozenset[str] = frozenset({".wav", ".ogg", ".mp3"})


def classify(path: Path) -> Optional[str]:
    """Return ``"sprite"``, ``"sound"`` or ``None`` for ``path``.

    Classification is by lowercased extension only; the file does not
    have to exist.
    """
    ext = path.suffix.lower()
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        return "sprite"
    if ext in SUPPORTED_AUDIO_EXTENSIONS:
        return "sound"
    return None
