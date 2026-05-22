"""M11 후속 — 3 backend (ollama/gemini/openai) help partial 6 파일이 모두 존재.

M11.9: claude/openrouter/huggingface 6 partial 삭제 후 잔존 3 backend × 2 lang = 6.
"""

from __future__ import annotations

from pathlib import Path


_TEMPLATES_DIR = (
    Path(__file__).parent.parent / "src" / "assetcache" / "web" / "templates" / "settings"
)

_BACKENDS = ("ollama", "gemini", "openai")
_LANGS = ("ko", "en")


def test_settings_partial_dir_exists():
    assert _TEMPLATES_DIR.is_dir(), f"{_TEMPLATES_DIR} not found"


def test_all_6_partials_exist():
    missing = []
    for name in _BACKENDS:
        for lang in _LANGS:
            partial = _TEMPLATES_DIR / f"help_{name}_{lang}.html"
            if not partial.is_file():
                missing.append(partial.name)
    assert not missing, f"missing partials: {missing}"


def test_partials_have_disclaimer_class_when_external():
    """external provider (ollama 제외 — gemini/openai) partial 은 disclaimer 문구 포함."""
    for name in ("gemini", "openai"):
        for lang in _LANGS:
            partial = _TEMPLATES_DIR / f"help_{name}_{lang}.html"
            content = partial.read_text(encoding="utf-8")
            assert (
                'class="disclaimer"' in content
            ), f"{partial.name} missing disclaimer class"
