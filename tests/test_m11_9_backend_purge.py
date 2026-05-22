"""M11.9 — 6 backend → 3 backend (ollama/gemini/openai) full purge 마이그 검증.

red phase: claude/openrouter/huggingface 백엔드 모듈 + factory + config 키 +
UI 배열 + i18n msgid + help partial + test import 가 모두 잔존하면 fail.
green phase: M11.9 PR 머지 후 9 케이스 PASSED.

본 파일은 회귀 보호용 — M11.9 머지 후에도 잔존해 backend 재추가/실수 차단.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _REPO_ROOT / "src" / "assetcache"
_TEMPLATES_DIR = _SRC_ROOT / "web" / "templates" / "settings"
_LOCALE_DIR = _SRC_ROOT / "web" / "locale"
_TESTS_DIR = _REPO_ROOT / "tests"

_REMOVED = ("claude", "openrouter", "huggingface")
_SURVIVING = ("ollama", "gemini", "openai")


# ---- Phase 1: 코드 + config + registry ----


def test_known_backends_is_three():
    """config._KNOWN_BACKENDS 가 정확히 3 keys."""
    from assetcache.config import _KNOWN_BACKENDS

    assert set(_KNOWN_BACKENDS) == set(_SURVIVING), (
        f"expected {_SURVIVING}, got {_KNOWN_BACKENDS}"
    )


def test_default_backends_keys_three():
    """_default_backends() 가 3 키만 반환 (claude/openrouter/huggingface 부재)."""
    from assetcache.config import _default_backends

    keys = set(_default_backends().keys())
    assert keys == set(_SURVIVING), f"expected {_SURVIVING}, got {keys}"


def test_default_chains_no_removed_refs():
    """_default_chains() 의 어떤 modality 도 제거된 backend 를 참조 안 함."""
    from assetcache.config import _default_chains

    for modality, order in _default_chains().items():
        for backend_name in order:
            assert backend_name not in _REMOVED, (
                f"chain {modality} references removed backend {backend_name}"
            )


def test_registry_no_removed_factories():
    """registry 모듈에 _default_{claude,openrouter,huggingface}_factory 부재."""
    from assetcache.core.llm import registry as reg_mod

    for name in _REMOVED:
        attr = f"_default_{name}_factory"
        assert not hasattr(reg_mod, attr), (
            f"registry still exposes {attr} — Phase 1-C purge incomplete"
        )


def test_backends_package_no_removed_modules():
    """backends.{claude,openrouter,huggingface} import 시 ModuleNotFoundError."""
    for name in _REMOVED:
        modname = f"assetcache.core.llm.backends.{name}"
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(modname)


# ---- Phase 2: UI + i18n + help partials + test imports ----


def test_settings_template_backend_order_is_three():
    """settings.html 의 backend 배열 (Jinja loop + JS) 에 제거 backend 부재."""
    settings_html = _SRC_ROOT / "web" / "templates" / "settings.html"
    body = settings_html.read_text(encoding="utf-8")

    # 제거된 backend 이름이 settings.html 어디에도 등장하면 안 됨 (Jinja loop /
    # JS backendOrder / setupUrls / setupLinkLabels 4 위치).
    for removed in _REMOVED:
        # 단어 경계로 매칭 — `claude_pick` (M5 enum) false positive 방지
        pattern = rf"\b{re.escape(removed)}\b"
        matches = re.findall(pattern, body)
        assert not matches, (
            f"settings.html still references removed backend {removed!r} "
            f"({len(matches)} matches) — Phase 2-F purge incomplete"
        )


def test_locale_po_no_removed_backend_strings():
    """messages.po (ko / en) 의 제거 backend setup link msgid 부재."""
    forbidden_msgids = (
        "Get key from Anthropic Console",
        "Get key from OpenRouter Settings",
        "Get token from HuggingFace",
    )
    for lang in ("ko", "en"):
        po_path = _LOCALE_DIR / lang / "LC_MESSAGES" / "messages.po"
        if not po_path.is_file():
            pytest.skip(f"{po_path} not found")
        body = po_path.read_text(encoding="utf-8")
        for msgid in forbidden_msgids:
            assert msgid not in body, (
                f"{po_path.name} still has msgid {msgid!r} — Phase 2-H purge incomplete"
            )


def test_help_partials_three_backends_only():
    """help_*.html 6 partial (ollama/gemini/openai × ko/en) 만 잔존."""
    expected = {
        f"help_{name}_{lang}.html"
        for name in _SURVIVING
        for lang in ("ko", "en")
    }
    forbidden = {
        f"help_{name}_{lang}.html"
        for name in _REMOVED
        for lang in ("ko", "en")
    }
    found = {p.name for p in _TEMPLATES_DIR.glob("help_*.html")}
    missing = expected - found
    leftover = found & forbidden
    assert not missing, f"missing surviving partials: {missing}"
    assert not leftover, (
        f"leftover removed partials: {leftover} — Phase 2-G purge incomplete"
    )


def test_no_backend_module_imports_in_tests():
    """tests/**.py 가 backends.{claude,openrouter,huggingface} 모듈을 import 안 함."""
    patterns = [
        re.compile(
            rf"from\s+assetcache\.core\.llm\.backends\.{name}\b"
        )
        for name in _REMOVED
    ] + [
        re.compile(
            rf"import\s+assetcache\.core\.llm\.backends\.{name}\b"
        )
        for name in _REMOVED
    ] + [
        # monkeypatch 의 string-path 매칭 — 'assetcache.core.llm.backends.claude.X'
        re.compile(
            rf"['\"]assetcache\.core\.llm\.backends\.{name}\."
        )
        for name in _REMOVED
    ]
    offenders: list[tuple[str, int, str]] = []
    for test_file in _TESTS_DIR.rglob("*.py"):
        if test_file.name == "test_m11_9_backend_purge.py":
            continue  # 자기 자신 (위 패턴은 string literal 안 — 매칭 안 되지만 방어적 skip)
        try:
            lines = test_file.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(lines, 1):
            for pat in patterns:
                if pat.search(line):
                    offenders.append((test_file.name, lineno, line.strip()))
                    break
    assert not offenders, (
        f"tests still import removed backend modules: {offenders[:5]}"
        f" (total {len(offenders)}) — Phase 2-B purge incomplete"
    )
