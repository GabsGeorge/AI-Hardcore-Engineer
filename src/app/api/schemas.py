"""API models mirroring contracts/openapi.yaml. FROZEN after the base graph block: changes go
through the main agent only."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

HandoffStatus = Literal["none", "awaiting_human", "resolved", "expired"]
RouteNode = Literal[
    "input_guardrail",
    "supervisor",
    "knowledge",
    "support",
    "escalation",
    "synthesize",
    "degraded_response",
    "safe_response",
    "output_guardrail",
]
HandoffReason = Literal[
    "low_confidence",
    "human_request",
    "sensitive_topic",
    "repeated_failures",
    "side_effect_action",
]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    user_id: str | None = Field(default=None, max_length=64)
    conversation_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


class Source(BaseModel):
    title: str
    url: str
    kind: Literal["kb", "web"]
    retrieved_at: datetime | None = None


class ToolCall(BaseModel):
    name: str
    status: Literal["ok", "error", "timeout", "denied"]
    latency_ms: int = Field(ge=0)


class HandoffRef(BaseModel):
    status: HandoffStatus = "none"
    ticket_id: UUID | None = None


class GuardrailsResult(BaseModel):
    input: Literal["pass", "masked", "blocked"] = "pass"
    output: Literal["pass", "rewritten", "blocked"] = "pass"


class ChatResponse(BaseModel):
    response: str
    conversation_id: UUID
    route: list[RouteNode]
    sources: list[Source]
    tools_used: list[ToolCall]
    confidence: float = Field(ge=0, le=1)
    handoff: HandoffRef
    guardrails: GuardrailsResult
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    trace_id: str | None = None


class Conversation(BaseModel):
    conversation_id: UUID
    handoff: HandoffRef
    last_activity_at: datetime
    messages: list[ConversationMessage]


class PendingAction(BaseModel):
    type: Literal["open_dispute"]
    params: dict[str, Any]
    decision: Literal["pending", "approved", "rejected"]


class Handoff(BaseModel):
    ticket_id: UUID
    conversation_id: UUID
    reason: HandoffReason
    status: Literal["awaiting_human", "resolved", "expired"]
    priority: Literal["normal", "high"]
    summary: str
    context: dict[str, Any] = Field(default_factory=dict)
    pending_action: PendingAction | None = None
    created_at: datetime
    sla_due_at: datetime
    expires_at: datetime
    operator_reply: str | None = None
    resolved_at: datetime | None = None


class HandoffReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1, max_length=4000)
    action_decision: Literal["approve", "reject"] | None = None


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    rating: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=1000)


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]
