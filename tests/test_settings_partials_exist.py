"""M11 후속 — 12 backend help partial 파일이 모두 존재."""

from __future__ import annotations

from pathlib import Path


_TEMPLATES_DIR = (
    Path(__file__).parent.parent / "src" / "assetcache" / "web" / "templates" / "settings"
)

_BACKENDS = ("ollama", "gemini", "claude", "openai", "openrouter", "huggingface")
_LANGS = ("ko", "en")


def test_settings_partial_dir_exists():
    assert _TEMPLATES_DIR.is_dir(), f"{_TEMPLATES_DIR} not found"


def test_all_12_partials_exist():
    missing = []
    for name in _BACKENDS:
        for lang in _LANGS:
            partial = _TEMPLATES_DIR / f"help_{name}_{lang}.html"
            if not partial.is_file():
                missing.append(partial.name)
    assert not missing, f"missing partials: {missing}"


def test_partials_have_disclaimer_class_when_external():
    """external provider (ollama 제외 5개) partial 은 disclaimer 문구 포함."""
    for name in ("gemini", "claude", "openai", "openrouter", "huggingface"):
        for lang in _LANGS:
            partial = _TEMPLATES_DIR / f"help_{name}_{lang}.html"
            content = partial.read_text(encoding="utf-8")
            assert (
                'class="disclaimer"' in content
            ), f"{partial.name} missing disclaimer class"
