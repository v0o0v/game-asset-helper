"""BackendRegistry — config 의 [backends.*] + [chains] → BackendChain 구성."""

from __future__ import annotations

from assetcache.config import Config
from assetcache.core.llm.base import (
    BackendCapabilities,
    BackendInfo,
)
from assetcache.core.llm.registry import BackendRegistry


class _FakeBackend:
    def __init__(self, name, *, img=True, aud=True, emb=True):
        self.info = BackendInfo(
            name=name,
            display_name=name,
            homepage="",
            capabilities=BackendCapabilities(img, aud, emb, embed_dim=None),
        )

    def chat(self, *a, **kw):
        return {"backend": self.info.name}

    def embed(self, *a, **kw):
        return [0.0]

    def test_connection(self):
        return True


def test_registry_builds_ollama_default_chain():
    """기본 Config — ollama 1개만 enabled → 모든 chain 이 ollama 하나."""
    cfg = Config()
    reg = BackendRegistry.from_config(cfg)
    chain = reg.get_chain("chat_image")
    assert len(chain.backends) == 1
    assert chain.backends[0].info.name == "ollama"

    audio_chain = reg.get_chain("chat_audio")
    assert len(audio_chain.backends) == 1
    assert audio_chain.backends[0].info.name == "ollama"

    embed_chain = reg.get_chain("text_embed")
    assert len(embed_chain.backends) == 1
    assert embed_chain.backends[0].info.name == "ollama"


def test_registry_skips_disabled_backend():
    """gemini enabled + ollama disabled → chain 에 gemini 만."""
    cfg = Config()
    cfg.backends["ollama"]["enabled"] = False
    cfg.backends["gemini"]["enabled"] = True
    cfg.backends["gemini"]["api_key"] = "AIzaTest"
    cfg.chains["chat_image"] = ["ollama", "gemini"]

    reg = BackendRegistry.from_config(
        cfg, gemini_factory=lambda settings, cfg: _FakeBackend("gemini"),
    )
    names = [b.info.name for b in reg.get_chain("chat_image").backends]
    assert "ollama" not in names
    assert "gemini" in names


def test_registry_get_backend_returns_instance():
    cfg = Config()
    reg = BackendRegistry.from_config(cfg)
    backend = reg.get_backend("ollama")
    assert backend is not None
    assert backend.info.name == "ollama"


def test_registry_get_backend_returns_none_for_disabled():
    cfg = Config()
    reg = BackendRegistry.from_config(cfg)
    # gemini disabled by default → not instantiated
    assert reg.get_backend("gemini") is None


def test_registry_factory_failure_logged_not_raised(caplog):
    """factory 가 예외 던져도 registry instantiation 은 계속."""
    import logging
    caplog.set_level(logging.WARNING)
    cfg = Config()
    cfg.backends["gemini"]["enabled"] = True
    cfg.backends["gemini"]["api_key"] = "AIzaTest"

    def boom(*a, **kw):
        raise RuntimeError("intentional")

    reg = BackendRegistry.from_config(cfg, gemini_factory=boom)
    # gemini 는 빠지지만 ollama 는 여전히 chain 에 있어야
    assert reg.get_backend("ollama") is not None
    assert reg.get_backend("gemini") is None
    assert any("gemini" in r.message and "intentional" in r.message
                for r in caplog.records)


def test_registry_chain_preserves_priority_order():
    cfg = Config()
    cfg.backends["gemini"]["enabled"] = True
    cfg.backends["gemini"]["api_key"] = "AIzaTest"
    cfg.chains["chat_image"] = ["gemini", "ollama"]
    reg = BackendRegistry.from_config(
        cfg, gemini_factory=lambda settings, cfg: _FakeBackend("gemini"),
    )
    chain = reg.get_chain("chat_image")
    assert [b.info.name for b in chain.backends] == ["gemini", "ollama"]


def test_registry_gemini_via_default_factory(monkeypatch):
    """gemini_factory 미지정 시 _default_gemini_factory 로 chain 구성."""
    cfg = Config()
    cfg.backends["gemini"]["enabled"] = True
    cfg.backends["gemini"]["api_key"] = "AIzaTest"
    cfg.chains["chat_image"] = ["gemini"]

    # 실 google-genai 호출 회피 — _default_gemini_factory monkeypatch
    from assetcache.core.llm import registry as reg_mod

    monkeypatch.setattr(
        reg_mod,
        "_default_gemini_factory",
        lambda settings, cfg: _FakeBackend("gemini"),
    )
    reg = BackendRegistry.from_config(cfg)
    chain = reg.get_chain("chat_image")
    assert len(chain.backends) == 1
    assert chain.backends[0].info.name == "gemini"


def test_default_gemini_factory_reads_env_for_api_key(monkeypatch):
    """settings.api_key 비어있어도 GEMINI_API_KEY env 가 있으면 사용."""
    from assetcache.core.llm import registry as reg_mod

    captured = {}

    class _StubGemini:
        info = None

        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.GeminiBackend", _StubGemini
    )
    monkeypatch.setenv("GEMINI_API_KEY", "env-key-AAA")

    cfg = Config()
    settings = dict(cfg.backends["gemini"])
    settings["api_key"] = ""  # blank → env fallback
    reg_mod._default_gemini_factory(settings=settings, cfg=cfg)
    assert captured["api_key"] == "env-key-AAA"
    assert captured["model_image"] == cfg.backends["gemini"]["model_image"]
    assert captured["timeout"] == cfg.analysis_timeout_seconds


def test_default_gemini_factory_settings_api_key_wins(monkeypatch):
    """settings.api_key 값이 있으면 env 보다 우선."""
    from assetcache.core.llm import registry as reg_mod

    captured = {}

    class _StubGemini:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.GeminiBackend", _StubGemini
    )
    monkeypatch.setenv("GEMINI_API_KEY", "env-key-BBB")

    cfg = Config()
    settings = dict(cfg.backends["gemini"])
    settings["api_key"] = "explicit-AIza"
    reg_mod._default_gemini_factory(settings=settings, cfg=cfg)
    assert captured["api_key"] == "explicit-AIza"


# ---- Claude (Phase 2) ----


def test_registry_claude_via_default_factory(monkeypatch):
    """claude_factory 미지정 시 _default_claude_factory 로 chain 구성."""
    cfg = Config()
    cfg.backends["claude"]["enabled"] = True
    cfg.backends["claude"]["api_key"] = "sk-ant-test"
    cfg.chains["chat_image"] = ["claude"]

    from assetcache.core.llm import registry as reg_mod

    monkeypatch.setattr(
        reg_mod,
        "_default_claude_factory",
        lambda settings, cfg: _FakeBackend("claude", aud=False, emb=False),
    )
    reg = BackendRegistry.from_config(cfg)
    chain = reg.get_chain("chat_image")
    assert len(chain.backends) == 1
    assert chain.backends[0].info.name == "claude"


def test_default_claude_factory_reads_env_for_api_key(monkeypatch):
    """settings.api_key 비어있어도 ANTHROPIC_API_KEY env 있으면 사용."""
    from assetcache.core.llm import registry as reg_mod

    captured = {}

    class _StubClaude:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.ClaudeBackend", _StubClaude
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-CLD")

    cfg = Config()
    settings = dict(cfg.backends["claude"])
    settings["api_key"] = ""
    reg_mod._default_claude_factory(settings=settings, cfg=cfg)
    assert captured["api_key"] == "env-key-CLD"
    assert captured["model_image"] == cfg.backends["claude"]["model_image"]
    assert captured["timeout"] == cfg.analysis_timeout_seconds


def test_default_claude_factory_settings_api_key_wins(monkeypatch):
    """settings.api_key 값이 있으면 env 보다 우선."""
    from assetcache.core.llm import registry as reg_mod

    captured = {}

    class _StubClaude:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.ClaudeBackend", _StubClaude
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-DDD")

    cfg = Config()
    settings = dict(cfg.backends["claude"])
    settings["api_key"] = "sk-ant-explicit"
    reg_mod._default_claude_factory(settings=settings, cfg=cfg)
    assert captured["api_key"] == "sk-ant-explicit"


# ---- OpenAI (Phase 3) ----


def test_registry_openai_via_default_factory(monkeypatch):
    """openai_factory 미지정 시 _default_openai_factory 로 chain 구성."""
    cfg = Config()
    cfg.backends["openai"]["enabled"] = True
    cfg.backends["openai"]["api_key"] = "sk-test"
    cfg.chains["chat_image"] = ["openai"]

    from assetcache.core.llm import registry as reg_mod

    monkeypatch.setattr(
        reg_mod,
        "_default_openai_factory",
        lambda settings, cfg: _FakeBackend("openai"),
    )
    reg = BackendRegistry.from_config(cfg)
    chain = reg.get_chain("chat_image")
    assert len(chain.backends) == 1
    assert chain.backends[0].info.name == "openai"


def test_default_openai_factory_reads_env_for_api_key(monkeypatch):
    """settings.api_key 비어있어도 OPENAI_API_KEY env 있으면 사용."""
    from assetcache.core.llm import registry as reg_mod

    captured = {}

    class _StubOpenAI:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAIBackend", _StubOpenAI
    )
    monkeypatch.setenv("OPENAI_API_KEY", "env-key-OAI")

    cfg = Config()
    settings = dict(cfg.backends["openai"])
    settings["api_key"] = ""
    reg_mod._default_openai_factory(settings=settings, cfg=cfg)
    assert captured["api_key"] == "env-key-OAI"
    assert captured["model_image"] == cfg.backends["openai"]["model_image"]
    assert captured["model_audio"] == cfg.backends["openai"]["model_audio"]
    assert captured["model_embed"] == cfg.backends["openai"]["model_embed"]
    assert captured["timeout"] == cfg.analysis_timeout_seconds


def test_default_openai_factory_settings_api_key_wins(monkeypatch):
    """settings.api_key 값이 있으면 env 보다 우선."""
    from assetcache.core.llm import registry as reg_mod

    captured = {}

    class _StubOpenAI:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAIBackend", _StubOpenAI
    )
    monkeypatch.setenv("OPENAI_API_KEY", "env-key-XXX")

    cfg = Config()
    settings = dict(cfg.backends["openai"])
    settings["api_key"] = "sk-explicit"
    reg_mod._default_openai_factory(settings=settings, cfg=cfg)
    assert captured["api_key"] == "sk-explicit"


# ---- OpenRouter (Phase 4) ----


def test_registry_openrouter_via_default_factory(monkeypatch):
    cfg = Config()
    cfg.backends["openrouter"]["enabled"] = True
    cfg.backends["openrouter"]["api_key"] = "sk-or-test"
    cfg.chains["chat_image"] = ["openrouter"]

    from assetcache.core.llm import registry as reg_mod

    monkeypatch.setattr(
        reg_mod,
        "_default_openrouter_factory",
        lambda settings, cfg: _FakeBackend("openrouter", aud=False, emb=False),
    )
    reg = BackendRegistry.from_config(cfg)
    chain = reg.get_chain("chat_image")
    assert len(chain.backends) == 1
    assert chain.backends[0].info.name == "openrouter"


def test_default_openrouter_factory_reads_env_for_api_key(monkeypatch):
    from assetcache.core.llm import registry as reg_mod

    captured = {}

    class _Stub:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(
        "assetcache.core.llm.backends.openrouter.OpenRouterBackend", _Stub
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key-OR")

    cfg = Config()
    settings = dict(cfg.backends["openrouter"])
    settings["api_key"] = ""
    reg_mod._default_openrouter_factory(settings=settings, cfg=cfg)
    assert captured["api_key"] == "env-key-OR"
    assert captured["model_image"] == cfg.backends["openrouter"]["model_image"]
    assert captured["timeout"] == cfg.analysis_timeout_seconds


def test_default_openrouter_factory_settings_api_key_wins(monkeypatch):
    from assetcache.core.llm import registry as reg_mod

    captured = {}

    class _Stub:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(
        "assetcache.core.llm.backends.openrouter.OpenRouterBackend", _Stub
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-x")

    cfg = Config()
    settings = dict(cfg.backends["openrouter"])
    settings["api_key"] = "sk-or-explicit"
    reg_mod._default_openrouter_factory(settings=settings, cfg=cfg)
    assert captured["api_key"] == "sk-or-explicit"


# ---- HuggingFace (Phase 4) ----


def test_registry_huggingface_via_default_factory(monkeypatch):
    cfg = Config()
    cfg.backends["huggingface"]["enabled"] = True
    cfg.backends["huggingface"]["api_key"] = "hf_test"
    cfg.chains["chat_image"] = ["huggingface"]

    from assetcache.core.llm import registry as reg_mod

    monkeypatch.setattr(
        reg_mod,
        "_default_huggingface_factory",
        lambda settings, cfg: _FakeBackend("huggingface"),
    )
    reg = BackendRegistry.from_config(cfg)
    chain = reg.get_chain("chat_image")
    assert len(chain.backends) == 1
    assert chain.backends[0].info.name == "huggingface"


def test_default_huggingface_factory_reads_env_for_api_key(monkeypatch):
    from assetcache.core.llm import registry as reg_mod

    captured = {}

    class _Stub:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.HuggingFaceBackend", _Stub
    )
    # HF_TOKEN 우선 (huggingface 공식 env name)
    monkeypatch.setenv("HF_TOKEN", "env-hf-token")

    cfg = Config()
    settings = dict(cfg.backends["huggingface"])
    settings["api_key"] = ""
    reg_mod._default_huggingface_factory(settings=settings, cfg=cfg)
    assert captured["api_key"] == "env-hf-token"
    assert captured["model_image"] == cfg.backends["huggingface"]["model_image"]
    assert captured["timeout"] == cfg.analysis_timeout_seconds


def test_default_huggingface_factory_settings_api_key_wins(monkeypatch):
    from assetcache.core.llm import registry as reg_mod

    captured = {}

    class _Stub:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.HuggingFaceBackend", _Stub
    )
    monkeypatch.setenv("HF_TOKEN", "env-x")

    cfg = Config()
    settings = dict(cfg.backends["huggingface"])
    settings["api_key"] = "hf_explicit"
    reg_mod._default_huggingface_factory(settings=settings, cfg=cfg)
    assert captured["api_key"] == "hf_explicit"


def test_registry_claude_audio_chain_falls_back_to_ollama(monkeypatch):
    """claude+ollama enabled, chat_audio=[claude, ollama] → audio 호출은 ollama."""
    from assetcache.core.llm import registry as reg_mod

    cfg = Config()
    cfg.backends["claude"]["enabled"] = True
    cfg.backends["claude"]["api_key"] = "sk-ant-test"
    cfg.chains["chat_audio"] = ["claude", "ollama"]

    monkeypatch.setattr(
        reg_mod,
        "_default_claude_factory",
        lambda settings, cfg: _FakeBackend("claude", aud=False, emb=False),
    )
    # ollama 도 stub — 실 HTTP 호출 회피 (테스트 환경에 ollama 없을 수 있음)
    reg = BackendRegistry.from_config(
        cfg,
        ollama_factory=lambda settings, cfg: _FakeBackend("ollama"),
    )
    chain = reg.get_chain("chat_audio")
    # claude 가 capability audio=False 이므로 chain.chat 호출 시 skip
    from assetcache.core.llm.base import ChatMessage

    _, used = chain.chat([ChatMessage("user", "hi")])
    assert used == "ollama"
