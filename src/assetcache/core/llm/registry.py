"""config → BackendChain 의 변환 한곳.

Phase 0: ollama 만 인식. Phase 1~4 에서 각 backend factory 추가.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Literal

from ...config import Config
from ..ollama_client import OllamaClient
from .base import LLMBackend
from .backends.ollama import OllamaBackend
from .chain import BackendChain

log = logging.getLogger(__name__)

Modality = Literal["chat_image", "chat_spritesheet", "chat_audio", "text_embed"]
BackendFactory = Callable[..., LLMBackend]


def _env(name: str) -> str:
    return os.environ.get(name, "")


def _default_ollama_factory(*, settings: dict, cfg: Config) -> LLMBackend:
    client = OllamaClient(
        base_url=settings["base_url"],
        model=settings["model_image"],
        timeout_seconds=cfg.analysis_timeout_seconds,
        max_retries=cfg.analysis_max_retries,
        parallel=cfg.ollama_parallel,
    )
    return OllamaBackend(client=client)


def _default_gemini_factory(*, settings: dict, cfg: Config) -> LLMBackend:
    from .backends.gemini import GeminiBackend

    return GeminiBackend(
        api_key=settings.get("api_key") or _env("GEMINI_API_KEY"),
        model_image=settings["model_image"],
        model_audio=settings["model_audio"],
        model_embed=settings["model_embed"],
        timeout=cfg.analysis_timeout_seconds,
    )


def _default_openai_factory(*, settings: dict, cfg: Config) -> LLMBackend:
    from .backends.openai_backend import OpenAIBackend

    return OpenAIBackend(
        api_key=settings.get("api_key") or _env("OPENAI_API_KEY"),
        model_image=settings["model_image"],
        model_audio=settings["model_audio"],
        model_embed=settings["model_embed"],
        timeout=cfg.analysis_timeout_seconds,
    )


class BackendRegistry:
    """instantiated backends + composed chains.

    factory 인자가 None 이면 해당 backend 는 아예 instantiate 안 함 (Phase 0
    에서 외부 backend factory 는 None).
    """

    def __init__(
        self,
        instances: dict[str, LLMBackend],
        chains: dict[str, BackendChain],
    ) -> None:
        self._instances = instances
        self._chains = chains

    def get_chain(self, modality: Modality) -> BackendChain:
        return self._chains[modality]

    def first_backend(self, modality: Modality) -> LLMBackend | None:
        """chain[modality] 의 첫 번째 eligible backend. 없으면 None.

        BatchManager 가 modality 별 첫 backend 의 name/supports_batch 를 검사하는 데 사용.
        """
        chain = self._chains.get(modality)
        if chain is None:
            return None
        eligible = chain._eligible()
        return eligible[0] if eligible else None

    def get_backend(self, name: str) -> LLMBackend | None:
        return self._instances.get(name)

    @classmethod
    def from_config(
        cls,
        cfg: Config,
        *,
        ollama_factory: BackendFactory | None = None,
        gemini_factory: BackendFactory | None = None,
        openai_factory: BackendFactory | None = None,
    ) -> "BackendRegistry":
        ollama_factory = ollama_factory or _default_ollama_factory
        gemini_factory = gemini_factory or _default_gemini_factory
        openai_factory = openai_factory or _default_openai_factory
        factories: dict[str, BackendFactory | None] = {
            "ollama": ollama_factory,
            "gemini": gemini_factory,
            "openai": openai_factory,
        }
        instances: dict[str, LLMBackend] = {}
        for name, settings in cfg.backends.items():
            if not settings.get("enabled"):
                continue
            factory = factories.get(name)
            if factory is None:
                log.debug(
                    "backend %s enabled but no factory registered (Phase 0 외부 backend)",
                    name,
                )
                continue
            try:
                instances[name] = factory(settings=settings, cfg=cfg)
            except Exception as e:
                log.warning(
                    "backend %s instantiation failed: %s",
                    name, e,
                )

        chains: dict[str, BackendChain] = {}
        for modality, order in cfg.chains.items():
            ordered = [instances[n] for n in order if n in instances]
            chains[modality] = BackendChain(ordered, modality=modality)  # type: ignore[arg-type]
        return cls(instances, chains)
