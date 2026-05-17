"""Config tests for M2.1 parallelization fields.

* ``ollama_parallel`` is brand new — caps concurrent Ollama HTTP calls.
* ``analysis_concurrency`` default changes from 1 → 3 so the analysis
  queue actually drives the pool.
"""

from __future__ import annotations

from gah.config import Config, load_config, save_config


def test_default_parallel_is_two() -> None:
    cfg = Config()
    assert cfg.ollama_parallel == 2


def test_default_concurrency_is_three() -> None:
    cfg = Config()
    assert cfg.analysis_concurrency == 3


def test_parallel_clamps_zero_and_negative_to_one() -> None:
    # 0 또는 음수는 시스템을 멈춰버리므로 1 로 클램프된다.
    cfg = Config.from_mapping({"ollama_parallel": 0})
    assert cfg.ollama_parallel == 1
    cfg2 = Config.from_mapping({"ollama_parallel": -5})
    assert cfg2.ollama_parallel == 1


def test_toml_roundtrip_preserves_new_field(tmp_path) -> None:
    cfg = Config(ollama_parallel=4, analysis_concurrency=6)
    config_path = tmp_path / "config.toml"
    save_config(cfg, config_path)
    restored = load_config(config_path)
    assert restored.ollama_parallel == 4
    assert restored.analysis_concurrency == 6


def test_forward_compat_old_config_without_parallel(tmp_path) -> None:
    """Older config.toml (no ollama_parallel) loads with the new default."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        # M2 시점에는 ollama_parallel 키가 없었다 — 이 상태에서도 안전하게 load 돼야
        "analysis_concurrency = 2\n"
        "ollama_url = \"http://127.0.0.1:11434\"\n",
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    assert cfg.ollama_parallel == 2  # 신규 default 가 채워짐
    assert cfg.analysis_concurrency == 2  # 기존 값 보존
