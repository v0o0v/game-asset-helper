"""M7 — Unity Asset Store 비공식 publisher 패널 API skeleton (D10, v2).

v1 기본 비활성. is_enabled() 만 Config 토글 읽고, 실제 HTTP 요청은
v2 에서 구현. ToS 회색지대 — 사용자가 명시적으로 켜야 동작.
"""

from __future__ import annotations

from gah.config import Config


class UnityRemoteOptInClient:
    def __init__(self, config: Config):
        self._config = config

    def is_enabled(self) -> bool:
        return self._config.unity_remote_optin_enabled

    def fetch_owned_assets(self):
        """v2 에서 kharma_session 쿠키 기반 비공식 엔드포인트 호출."""
        raise NotImplementedError(
            "publisher panel API is v2 — see DESIGN.md §4.9.2"
        )
