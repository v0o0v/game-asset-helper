"""Config — [backends.*] / [chains] migration (M11 spec §6.2)."""

from __future__ import annotations

import textwrap

from assetcache.config import Config, load_config, save_config


def test_legacy_only_config_migrates_to_backends_ollama(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""
        ollama_url = "http://1.2.3.4:11434"
        model_image = "gemma3:7b"
        model_audio = "gemma3:7b"
        model_embed = "nomic-embed-text"
    """).lstrip())
    cfg = load_config(p)
    assert cfg.backends["ollama"]["enabled"] is True
    assert cfg.backends["ollama"]["base_url"] == "http://1.2.3.4:11434"
    assert cfg.backends["ollama"]["model_image"] == "gemma3:7b"
    assert cfg.backends["ollama"]["model_audio"] == "gemma3:7b"
    assert cfg.backends["ollama"]["model_embed"] == "nomic-embed-text"
    assert cfg.chains["chat_image"] == ["ollama"]
    assert cfg.chains["chat_audio"] == ["ollama"]
    assert cfg.chains["text_embed"] == ["ollama"]


def test_new_keys_only_preserved(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""
        [backends.ollama]
        enabled = true
        base_url = "http://5.6.7.8:11434"
        model_image = "gemma3:7b"
        model_audio = "gemma3:7b"
        model_embed = "nomic-embed-text"

        [backends.gemini]
        enabled = true
        api_key = "AIzaSecret"
        model_image = "gemini-2.5-flash"
        model_audio = "gemini-2.5-flash"
        model_embed = "gemini-embedding-001"

        [chains]
        chat_image = ["gemini", "ollama"]
        chat_audio = ["ollama"]
        text_embed = ["ollama"]
    """).lstrip())
    cfg = load_config(p)
    assert cfg.backends["ollama"]["base_url"] == "http://5.6.7.8:11434"
    assert cfg.backends["gemini"]["api_key"] == "AIzaSecret"
    assert cfg.chains["chat_image"] == ["gemini", "ollama"]


def test_default_config_has_all_three_backends(tmp_path):
    """Config() 인스턴스화만으로 3 backend 모두 사전 등록 — disabled 기본 (ollama 외).

    M11.9: claude/openrouter/huggingface 제거 후 3 backend 만.
    """
    cfg = Config()
    for name in ("ollama", "gemini", "openai"):
        assert name in cfg.backends, f"backend {name} missing from defaults"
    # ollama 만 enabled 기본
    assert cfg.backends["ollama"]["enabled"] is True
    for name in ("gemini", "openai"):
        assert cfg.backends[name]["enabled"] is False
    # M11.9 — 제거된 backend 는 부재
    for removed in ("claude", "openrouter", "huggingface"):
        assert removed not in cfg.backends, (
            f"removed backend {removed} should not be in defaults"
        )


def test_default_gemini_model_is_3_1_flash_lite(tmp_path):
    """Gemini default chat 모델 = gemini-3.1-flash-lite (GA 2026-03, 비용 -40% vs 2.5-flash).

    cfg default 만 변경 — 기존 사용자의 cfg.toml 은 영향 없음 (각자의 model_image
    값 유지). 신규 install / 새 cfg 생성 시 적용.
    """
    cfg = Config()
    assert cfg.backends["gemini"]["model_image"] == "gemini-3.1-flash-lite"
    assert cfg.backends["gemini"]["model_audio"] == "gemini-3.1-flash-lite"
    # embedding 모델은 별도 (gemini-embedding-001 그대로 — embedding 은 별도 family)
    assert cfg.backends["gemini"]["model_embed"] == "gemini-embedding-001"


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "config.toml"
    cfg = Config()
    save_config(cfg, p)
    cfg2 = load_config(p)
    assert cfg2.backends["ollama"]["enabled"] is True
    assert "gemini" in cfg2.backends
    assert "openai" in cfg2.backends
    # M11.9 — 제거된 backend 는 부재
    assert "claude" not in cfg2.backends
    assert "openrouter" not in cfg2.backends
    assert "huggingface" not in cfg2.backends
    # M11.2 — chat_spritesheet modality 신설.  default 는 chat_image 와 동일 ["ollama"].
    assert cfg2.chains == {
        "chat_image": ["ollama"],
        "chat_spritesheet": ["ollama"],
        "chat_audio": ["ollama"],
        "text_embed": ["ollama"],
    }


def test_unknown_chain_modality_dropped(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""
        [chains]
        bogus_modality = ["x"]
        chat_image = ["ollama"]
    """).lstrip())
    cfg = load_config(p)
    assert "bogus_modality" not in cfg.chains
    assert cfg.chains["chat_image"] == ["ollama"]


def test_unknown_backend_in_data_dropped(tmp_path):
    """모르는 backend 키는 무시 (forward-compat)."""
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""
        [backends.future_backend_X]
        enabled = true
        api_key = "irrelevant"

        [backends.gemini]
        enabled = true
        api_key = "AIzaTest"
    """).lstrip())
    cfg = load_config(p)
    assert "future_backend_X" not in cfg.backends
    assert cfg.backends["gemini"]["api_key"] == "AIzaTest"


def test_legacy_keys_dont_override_new_section(tmp_path):
    """[backends.ollama] 가 있으면 legacy 키는 무시."""
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""
        ollama_url = "http://legacy:11434"
        model_image = "legacy_model"

        [backends.ollama]
        enabled = true
        base_url = "http://new:11434"
        model_image = "new_model"
        model_audio = "gemma3:7b"
        model_embed = "nomic-embed-text"
    """).lstrip())
    cfg = load_config(p)
    assert cfg.backends["ollama"]["base_url"] == "http://new:11434"
    assert cfg.backends["ollama"]["model_image"] == "new_model"
