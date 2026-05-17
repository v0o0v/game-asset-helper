"""Config tests for the 9 new M2 fields."""

from __future__ import annotations

from gah.config import Config, load_config, save_config


def test_new_fields_have_documented_defaults() -> None:
    cfg = Config()
    assert cfg.analysis_timeout_seconds == 60.0
    # M2.1 patch: default raised 1 → 3 to drive the worker pool. See M2.1_plan §3.1.
    assert cfg.analysis_concurrency == 3
    assert cfg.analysis_max_retries == 3
    assert cfg.description_language == "ko"
    assert cfg.clip_model == "ViT-B-32"
    assert cfg.clip_pretrained == "openai"
    assert cfg.clip_enable is True
    assert cfg.audio_max_seconds == 30
    assert cfg.audio_chunk_strategy == "smart"


def test_from_mapping_ignores_unknown_keys_still() -> None:
    cfg = Config.from_mapping({
        "unknown_future_key": 123,
        "analysis_concurrency": 4,
    })
    assert cfg.analysis_concurrency == 4


def test_toml_roundtrip_preserves_new_fields(tmp_path) -> None:
    cfg = Config(
        analysis_concurrency=2,
        clip_enable=False,
        audio_chunk_strategy="rms_peak",
    )
    config_path = tmp_path / "config.toml"
    save_config(cfg, config_path)
    restored = load_config(config_path)
    assert restored.analysis_concurrency == 2
    assert restored.clip_enable is False
    assert restored.audio_chunk_strategy == "rms_peak"


def test_description_language_validates_known_values() -> None:
    """Unknown language → falls back to default 'ko'."""
    cfg = Config.from_mapping({"description_language": "fr"})
    assert cfg.description_language == "ko"


def test_clip_enable_can_be_disabled() -> None:
    cfg = Config(clip_enable=False)
    assert cfg.clip_enable is False
