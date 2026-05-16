"""Pack manifest parsing + vendor heuristics.

The manifest schema is documented in ``DESIGN.md §5.2``.  M1 only
consumes the five fields that map onto columns in the ``packs`` table;
future-only fields (``tags``, ``style_hint``, ...) are intentionally
ignored so that adding them later cannot crash an older runtime.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:  # 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]


log = logging.getLogger(__name__)

# Folder-name prefixes we recognise without a manifest.
_VENDOR_PREFIXES: tuple[tuple[str, str], ...] = (
    ("kenney_", "kenney"),
    ("kaykit_", "kaykit"),
    ("craftpix_", "craftpix"),
)


@dataclass(frozen=True)
class PackManifest:
    display_name: Optional[str]
    vendor: Optional[str]
    source_url: Optional[str]
    license: Optional[str]
    description: Optional[str]


def _infer_vendor(folder_name: str) -> Optional[str]:
    lowered = folder_name.lower()
    for prefix, vendor in _VENDOR_PREFIXES:
        if lowered.startswith(prefix):
            return vendor
    return None


def _from_mapping(data: dict, folder_name: str) -> PackManifest:
    vendor = data.get("vendor")
    if vendor is None:
        vendor = _infer_vendor(folder_name)
    return PackManifest(
        display_name=data.get("name"),
        vendor=vendor,
        source_url=data.get("source_url"),
        license=data.get("license"),
        description=data.get("description"),
    )


def load_manifest(pack_dir: Path) -> PackManifest:
    """Load a manifest from ``pack_dir`` falling back to folder-name heuristics.

    Precedence: ``pack.json`` > ``pack.toml`` > heuristic.  A malformed
    manifest is logged and downgraded to the heuristic, never raised.
    """
    folder_name = pack_dir.name

    pj = pack_dir / "pack.json"
    if pj.exists():
        try:
            with pj.open("rb") as fh:
                data = json.loads(fh.read().decode("utf-8"))
            if isinstance(data, dict):
                return _from_mapping(data, folder_name)
            log.warning("pack.json in %s is not a JSON object; falling back to heuristic", pack_dir)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            log.warning("failed to parse %s (%s); falling back to heuristic", pj, exc)

    pt = pack_dir / "pack.toml"
    if pt.exists():
        try:
            with pt.open("rb") as fh:
                data = tomllib.load(fh)
            if isinstance(data, dict):
                return _from_mapping(data, folder_name)
            log.warning("pack.toml in %s is not a TOML table; falling back to heuristic", pack_dir)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            log.warning("failed to parse %s (%s); falling back to heuristic", pt, exc)

    return PackManifest(
        display_name=None,
        vendor=_infer_vendor(folder_name),
        source_url=None,
        license=None,
        description=None,
    )
