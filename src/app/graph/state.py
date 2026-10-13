"""Typed graph state (data-model.md §3). FROZEN after the base graph block.

`user_id` is deliberately absent: identity travels in `config["configurable"]` (ADR 0005).
Per-turn accumulators (results, route_trace, guardrail_flags, tokens_used) use reducers so
parallel specialists can write to them; the API resets them with `Overwrite` on every turn.
"""

import operator
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, model_validator

AgentName = Literal["knowledge", "support", "escalation"]


class Source(TypedDict):
    title: str
    url: str
    kind: Literal["kb", "web"]
    retrieved_at: NotRequired[str]


class ToolCallRecord(TypedDict):
    name: str
    status: Literal["ok", "error", "timeout", "denied"]
    latency_ms: int


class SubTask(TypedDict):
    id: str
    agent: AgentName
    query: str


class AgentResult(TypedDict):
    subtask_id: str
    agent: AgentName
    answer: str
    confidence: float
    sources: list[Source]
    tools_used: list[ToolCallRecord]
    error: str | None


class Escalation(TypedDict):
    reason: str
    status: Literal["awaiting_human", "resolved", "expired"]
    ticket_id: str | None
    summary: str
    pending_action: dict[str, Any] | None


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    input_pii: list[str]
    summary: str | None
    language: str | None
    plan: dict[str, Any] | None
    results: Annotated[list[AgentResult], operator.add]
    attempts: int
    step: int
    tokens_used: Annotated[int, operator.add]
    route_trace: Annotated[list[str], operator.add]
    escalation: Escalation | None
    guardrail_flags: Annotated[list[str], operator.add]
    final_response: str | None


class SpecialistInput(TypedDict):
    """Payload sent by the Supervisor to a specialist with `Send` (one subtask each)."""

    subtask: SubTask
    language: str


class SubTaskModel(BaseModel):
    id: str = Field(min_length=1, max_length=20)
    agent: AgentName
    query: str = Field(min_length=1, max_length=1000)


class PlanModel(BaseModel):
    """Structured output of the Supervisor planner (REQ-ORC-01)."""

    route: list[AgentName] = Field(min_length=1, max_length=3)
    subtasks: list[SubTaskModel] = Field(min_length=1, max_length=4)
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(max_length=500)
    language: str = Field(min_length=2, max_length=5, description="ISO 639-1 of the user message")
    sensitive: bool = Field(description="dispute, fraud, cancellation or other sensitive topic")

    @model_validator(mode="after")
    def _route_matches_subtasks(self) -> "PlanModel":
        if set(self.route) != {s.agent for s in self.subtasks}:
            raise ValueError("route must list exactly the agents of the subtasks")
        return self
