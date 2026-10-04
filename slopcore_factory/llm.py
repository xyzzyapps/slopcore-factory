"""Optional LangChain model access for the storyboard generator.

The factory works without an LLM (a deterministic offline generator builds a
usable blueprint). To get the multi-director storyboard the reference production
used, point ``SLOPCORE_FACTORY_LLM`` at a chat model, e.g.::

    set SLOPCORE_FACTORY_LLM=anthropic:claude-sonnet-4-5
    set ANTHROPIC_API_KEY=...

Install the extra first: ``pip install -e ".[llm]"``.
"""

from __future__ import annotations

import os

from .errors import LLMError
from .logging_setup import get_logger

log = get_logger("llm")

ENV_MODEL = "SLOPCORE_FACTORY_LLM"


def configured_model() -> str | None:
    value = os.environ.get(ENV_MODEL)
    return value.strip() if value else None


def get_llm():
    """Return a LangChain chat model, or ``None`` when not configured."""
    spec = configured_model()
    if not spec:
        return None
    try:
        from langchain.chat_models import init_chat_model
    except ImportError as exc:  # pragma: no cover - env dependent
        raise LLMError(
            "langchain is not installed; run: pip install -e '.[llm]' "
            "and set SLOPCORE_FACTORY_LLM (e.g. anthropic:claude-sonnet-4-5)"
        ) from exc

    provider, _, model = spec.partition(":")
    kwargs: dict = {}
    if provider:
        kwargs["model_provider"] = provider
    log.info("using LLM %s", spec)
    return init_chat_model(model or None, **kwargs)
