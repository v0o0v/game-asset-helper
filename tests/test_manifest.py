"""Tests for gah.core.manifest — pack manifest parsing + vendor heuristics."""

from __future__ import annotations

import json
from pathlib import Path

import tomli_w


def test_pack_json_is_parsed_fully(tmp_path: Path) -> None:
    from gah.core.manifest import load_manifest

    pack_dir = tmp_path / "demo_pack"
    pack_dir.mkdir()
    payload = {
        "name": "Demo Pack",
        "vendor": "kenney",
        "source_url": "https://kenney.nl/assets/demo",
        "license": "CC0",
        "description": "측면 스크롤 데모용 에셋",
    }
    (pack_dir / "pack.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    manifest = load_manifest(pack_dir)
    assert manifest.display_name == "Demo Pack"
    assert manifest.vendor == "kenney"
    assert manifest.source_url == "https://kenney.nl/assets/demo"
    assert manifest.license == "CC0"
    assert manifest.description == "측면 스크롤 데모용 에셋"


def test_pack_toml_is_parsed_fully(tmp_path: Path) -> None:
    from gah.core.manifest import load_manifest

    pack_dir = tmp_path / "demo_toml_pack"
    pack_dir.mkdir()
    payload = {
        "name": "Demo TOML",
        "vendor": "kaykit",
        "source_url": "https://kaykit.example/demo",
        "license": "CC-BY",
        "description": "TOML 매니페스트",
    }
    (pack_dir / "pack.toml").write_bytes(tomli_w.dumps(payload).encode("utf-8"))

    manifest = load_manifest(pack_dir)
    assert manifest.display_name == "Demo TOML"
    assert manifest.vendor == "kaykit"
    assert manifest.license == "CC-BY"


def test_pack_json_preferred_when_both_present(tmp_path: Path) -> None:
    from gah.core.manifest import load_manifest

    pack_dir = tmp_path / "demo_dual"
    pack_dir.mkdir()
    (pack_dir / "pack.json").write_text(
        json.dumps({"name": "From JSON", "vendor": "kenney"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (pack_dir / "pack.toml").write_bytes(
        tomli_w.dumps({"name": "From TOML", "vendor": "kaykit"}).encode("utf-8")
    )

    manifest = load_manifest(pack_dir)
    assert manifest.display_name == "From JSON"
    assert manifest.vendor == "kenney"


def test_missing_manifest_uses_heuristic_kenney_prefix(tmp_path: Path) -> None:
    from gah.core.manifest import load_manifest

    pack_dir = tmp_path / "kenney_platformer_redux"
    pack_dir.mkdir()

    manifest = load_manifest(pack_dir)
    assert manifest.vendor == "kenney"
    assert manifest.display_name is None
    assert manifest.license is None


def test_missing_manifest_uses_heuristic_kaykit_prefix(tmp_path: Path) -> None:
    from gah.core.manifest import load_manifest

    pack_dir = tmp_path / "kaykit_dungeon_remastered"
    pack_dir.mkdir()

    manifest = load_manifest(pack_dir)
    assert manifest.vendor == "kaykit"


def test_missing_manifest_unknown_prefix_returns_none_vendor(tmp_path: Path) -> None:
    from gah.core.manifest import load_manifest

    pack_dir = tmp_path / "my_custom_sfx"
    pack_dir.mkdir()

    manifest = load_manifest(pack_dir)
    assert manifest.vendor is None
    assert manifest.display_name is None


def test_malformed_pack_json_falls_back_to_heuristic(tmp_path: Path) -> None:
    from gah.core.manifest import load_manifest

    pack_dir = tmp_path / "craftpix_broken"
    pack_dir.mkdir()
    (pack_dir / "pack.json").write_text("{this is not, valid: json", encoding="utf-8")

    manifest = load_manifest(pack_dir)
    # falls back to folder-name heuristic
    assert manifest.vendor == "craftpix"
    assert manifest.display_name is None


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    from gah.core.manifest import load_manifest

    pack_dir = tmp_path / "ignored_keys_pack"
    pack_dir.mkdir()
    (pack_dir / "pack.json").write_text(
        json.dumps(
            {
                "name": "Has Extras",
                "vendor": "kenney",
                "tags": ["platformer", "tiles"],  # future field, M1 ignores
                "style_hint": ["vector"],  # future field
                "completely_made_up": 42,
            }
        ),
        encoding="utf-8",
    )

    manifest = load_manifest(pack_dir)
    assert manifest.display_name == "Has Extras"
    assert manifest.vendor == "kenney"
    # the extras should not be exposed as fields
    assert not hasattr(manifest, "tags")
    assert not hasattr(manifest, "completely_made_up")
