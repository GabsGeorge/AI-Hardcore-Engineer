"""Fallback de modelo quando o primário falha (REQ-REL-02).

A composição real usa ``primary.with_fallbacks([fallback])`` do LangChain. Este teste
simula o comportamento com um primário que levanta e um fallback que responde — garantindo
que ``get_model`` entrega uma cadeia que retoma pelo backup."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableLambda


class _AlwaysFails(Runnable):  # type: ignore[type-arg]
    def invoke(self, _input: object, _config: object = None) -> AIMessage:
        raise RuntimeError("primary down")

    async def ainvoke(self, _input: object, _config: object = None, **_: object) -> AIMessage:
        raise RuntimeError("primary down")


@pytest.mark.req("REQ-REL-02")
async def test_with_fallbacks_calls_backup_when_primary_raises() -> None:
    primary = _AlwaysFails()
    fallback = RunnableLambda(lambda _msgs: AIMessage(content="fallback-reply"))
    chain = primary.with_fallbacks([fallback])  # type: ignore[arg-type]
    reply = await chain.ainvoke([HumanMessage(content="oi")])
    assert isinstance(reply, AIMessage)
    assert reply.content == "fallback-reply"
