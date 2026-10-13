"""Deterministic test doubles (ADR 0006): scripted chat models, embeddings and reranker."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel, ValidationError

DEFAULT_USAGE = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}


@dataclass
class Scripted:
    """A scripted reply with explicit token usage."""

    value: Any
    tokens: int = DEFAULT_USAGE["total_tokens"]


def _usage(tokens: int) -> dict[str, int]:
    return {
        "input_tokens": tokens - tokens // 6,
        "output_tokens": tokens // 6,
        "total_tokens": tokens,
    }


def _as_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, BaseMessage):
        return str(payload.content)
    if isinstance(payload, list | tuple):
        return "\n".join(_as_text(p) for p in payload)
    if hasattr(payload, "to_messages"):
        return _as_text(payload.to_messages())
    return str(payload)


@dataclass
class FakeLLM:
    """Registry of scripted replies per role. Install with ``llm.set_overrides``."""

    scripts: dict[str, deque[Any]] = field(default_factory=lambda: defaultdict(deque))
    calls: list[tuple[str, str]] = field(default_factory=list)

    def script(self, **by_role: list[Any]) -> FakeLLM:
        for role, items in by_role.items():
            self.scripts[role].extend(items)
        return self

    def model(self, role: str) -> FakeChatModel:
        return FakeChatModel(self, role)

    def prompts(self, role: str | None = None) -> str:
        return "\n".join(text for r, text in self.calls if role in (None, r))

    def next(self, role: str, payload: Any) -> Scripted:
        self.calls.append((role, _as_text(payload)))
        if not self.scripts[role]:
            raise AssertionError(f"no scripted reply left for role {role!r}")
        item = self.scripts[role].popleft()
        return item if isinstance(item, Scripted) else Scripted(item)


@dataclass
class FakeChatModel:
    llm: FakeLLM
    role: str

    async def ainvoke(self, payload: Any, config: Any = None, **_: Any) -> AIMessage:
        reply = self.llm.next(self.role, payload)
        if isinstance(reply.value, Exception):
            raise reply.value
        if isinstance(reply.value, AIMessage):
            return reply.value
        return AIMessage(content=str(reply.value), usage_metadata=_usage(reply.tokens))

    def with_structured_output(
        self, schema: type[BaseModel], *, include_raw: bool = False, **_: Any
    ) -> _Structured:
        return _Structured(self, schema, include_raw)

    def bind_tools(self, *_: Any, **__: Any) -> FakeChatModel:
        return self


@dataclass
class _Structured:
    model: FakeChatModel
    schema: type[BaseModel]
    include_raw: bool

    async def ainvoke(self, payload: Any, config: Any = None, **_: Any) -> Any:
        reply = self.model.llm.next(self.model.role, payload)
        raw = AIMessage(content="", usage_metadata=_usage(reply.tokens))
        parsed: BaseModel | None = None
        error: Exception | None = None
        if isinstance(reply.value, Exception):
            error = reply.value
        else:
            try:
                parsed = (
                    reply.value
                    if isinstance(reply.value, self.schema)
                    else self.schema.model_validate(reply.value)
                )
            except ValidationError as exc:
                error = exc
        if self.include_raw:
            return {"raw": raw, "parsed": parsed, "parsing_error": error}
        if error:
            raise error
        return parsed


def fake_embeddings() -> DeterministicFakeEmbedding:
    return DeterministicFakeEmbedding(size=1536)


class FakeReranker:
    """Scores passages by word overlap with the query (0..1), highest first."""

    def rerank(self, query: str, passages: list[str]) -> list[tuple[int, float]]:
        terms = set(query.lower().split())
        scores = [
            (i, len(terms & set(p.lower().split())) / max(len(terms), 1))
            for i, p in enumerate(passages)
        ]
        return sorted(scores, key=lambda s: s[1], reverse=True)


@dataclass
class SpyGraph:
    """Stands in for the compiled graph when a test only checks the API boundary."""

    calls: int = 0
    last_input: Any = None
    last_config: Any = None
    reply: str = "ok"

    async def ainvoke(self, payload: Any, config: Any = None, **_: Any) -> dict[str, Any]:
        self.calls += 1
        self.last_input, self.last_config = payload, config
        return {
            "final_response": self.reply,
            "route_trace": [],
            "results": [],
            "guardrail_flags": [],
            "escalation": None,
        }


def make_plan(
    *agents: str,
    language: str = "pt",
    confidence: float = 0.9,
    sensitive: bool = False,
    query: str = "pergunta",
) -> dict[str, Any]:
    """A valid supervisor plan routing one subtask to each agent given."""
    return {
        "route": list(agents),
        "subtasks": [
            {"id": f"s{i}", "agent": agent, "query": query} for i, agent in enumerate(agents, 1)
        ],
        "confidence": confidence,
        "rationale": "test plan",
        "language": language,
        "sensitive": sensitive,
    }
