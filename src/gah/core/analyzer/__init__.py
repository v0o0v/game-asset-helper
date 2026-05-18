"""M2 analyzers (sprite + sound) and the shared analyzer base types.

This package is intentionally empty at import time — the concrete
``SpriteAnalyzer`` / ``SoundAnalyzer`` classes are imported lazily by
``gah.core.analysis_queue`` to keep heavy dependencies (Pillow, librosa,
torch) out of the import path for callers that only need M1 features.
"""

from .sound import SoundAnalyzer
from .sprite import SpriteAnalyzer
from .spritesheet import SpritesheetAnalyzer

__all__ = ["SoundAnalyzer", "SpriteAnalyzer", "SpritesheetAnalyzer"]
