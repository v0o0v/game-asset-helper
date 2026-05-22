"""Multi-backend LLM 추상화 (M11).

backend abstraction (Protocol + Chain + Registry) + 3 backend wrappers.
spec: docs/superpowers/specs/2026-05-20-m11-multi-backend-llm-design.md
"""

from __future__ import annotations

from typing import Any


def unwrap_chat_result(result: Any) -> dict:
    """BackendChain.chat → (dict, name) / OllamaClient.chat → dict 양쪽 흡수.

    Phase 0 의 transitional 흡수. Phase 6 에서 analyzer 시그니처가 chain 만 받도록
    바뀌면 호출자가 (dict, name) 으로 풀어서 backend_name 메타데이터에 활용.
    """
    if (
        isinstance(result, tuple)
        and len(result) == 2
        and isinstance(result[1], str)
    ):
        return result[0]
    return result

