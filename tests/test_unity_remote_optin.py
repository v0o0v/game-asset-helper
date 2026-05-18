"""M7 — UnityRemoteOptInClient skeleton 회귀 (D10)."""
from __future__ import annotations

import pytest

from gah.config import Config
from gah.core.unity_import.remote_optin import UnityRemoteOptInClient


def test_is_enabled_default_false():
    cfg = Config()
    client = UnityRemoteOptInClient(config=cfg)
    assert client.is_enabled() is False


def test_is_enabled_when_toggled():
    cfg = Config(unity_remote_optin_enabled=True)
    client = UnityRemoteOptInClient(config=cfg)
    assert client.is_enabled() is True


def test_fetch_owned_assets_raises_notimplemented():
    cfg = Config(unity_remote_optin_enabled=True)
    client = UnityRemoteOptInClient(config=cfg)
    with pytest.raises(NotImplementedError):
        client.fetch_owned_assets()
