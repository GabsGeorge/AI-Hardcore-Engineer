"""get_model wires the fallback model only when OPENAI_MODEL_FALLBACK is set (REQ-REL-02)."""

from __future__ import annotations

import pytest
from langchain_core.runnables import RunnableWithFallbacks
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.llm import get_model


@pytest.fixture
def real_models(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "openai_api_key", SecretStr("sk-test"))  # build only, no calls
    monkeypatch.setattr(s, "openai_model_primary", "primary-model")


@pytest.mark.req("REQ-REL-02")
@pytest.mark.usefixtures("real_models")
def test_fallback_model_is_chained_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "openai_model_fallback", "fallback-model")
    model = get_model("supervisor")
    assert isinstance(model, RunnableWithFallbacks)
    assert model.runnable.model_name == "primary-model"  # type: ignore[attr-defined]
    assert model.fallbacks[0].model_name == "fallback-model"  # type: ignore[attr-defined]


@pytest.mark.req("REQ-REL-02")
@pytest.mark.usefixtures("real_models")
def test_no_fallback_chain_without_fallback_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "openai_model_fallback", "")
    assert not isinstance(get_model("supervisor"), RunnableWithFallbacks)
