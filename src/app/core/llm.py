"""Single entry point for chat models and embeddings, with an override hook for tests."""

from collections.abc import Callable
from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import get_settings

_model_factory: Callable[[str], Any] | None = None
_embeddings: Any | None = None


def set_overrides(
    model_factory: Callable[[str], Any] | None = None, embeddings: Any | None = None
) -> None:
    """Tests install fakes here (ADR 0006); passing None restores the real providers."""
    global _model_factory, _embeddings
    _model_factory, _embeddings = model_factory, embeddings


def get_model(role: str) -> Any:
    """Chat model for a graph role (supervisor, knowledge, support, synthesize, ...).

    When ``OPENAI_MODEL_FALLBACK`` is configured, the primary model is wrapped with
    ``.with_fallbacks([fallback])`` (REQ-REL-02): if the primary fails (timeout or server
    error), LangChain automatically retries the same request on the fallback model.
    """
    if _model_factory is not None:
        return _model_factory(role)
    s = get_settings()
    primary = ChatOpenAI(
        model=s.openai_model_primary,
        api_key=s.openai_api_key,
        timeout=20,
        max_retries=2,
    )
    if s.openai_model_fallback:
        fallback = ChatOpenAI(
            model=s.openai_model_fallback,
            api_key=s.openai_api_key,
            timeout=20,
            max_retries=1,
        )
        return primary.with_fallbacks([fallback])
    return primary


def get_embeddings() -> Any:
    if _embeddings is not None:
        return _embeddings
    s = get_settings()
    return OpenAIEmbeddings(model=s.openai_embedding_model, openai_api_key=s.openai_api_key)
