"""Tool contracts from specs/001-multi-agent-support/contracts/tools.md. FROZEN after the base
graph block: implementations live in *_tools.py and must use these models unchanged.

No input model carries identity. Support tools read the user from `config["configurable"]`
(ADR 0005), so the model can never choose whose data is read.
"""

from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Knowledge -------------------------------------------------------------------------------
class SearchKnowledgeBaseInput(_Input):
    query: str = Field(min_length=1, max_length=500, description="What to look up")
    lang: Literal["pt", "en"] | None = Field(default=None, description="Preferred language")


class KnowledgeHit(BaseModel):
    chunk_id: int
    title: str
    url: str
    section: str
    content: str
    score: float = Field(ge=0, le=1)


class WebSearchInput(_Input):
    query: str = Field(min_length=1, max_length=300, description="General web question")


class WebResult(BaseModel):
    title: str
    url: str
    snippet: str
    retrieved_at: datetime


# --- Support (data of the token's user only) ----------------------------------------------
class GetSettlementScheduleInput(_Input):
    from_date: date
    to_date: date

    @model_validator(mode="after")
    def _window(self) -> "GetSettlementScheduleInput":
        if self.to_date < self.from_date or self.to_date - self.from_date > timedelta(days=90):
            raise ValueError("date window must be 0..90 days")
        return self


class SettlementDay(BaseModel):
    expected_date: date
    amount_cents: int
    status: Literal["scheduled", "paid", "anticipated"]
    transaction_count: int


class DiagnoseTerminalInput(_Input):
    terminal_id: str | None = Field(default=None, max_length=64)


class TerminalDiagnosis(BaseModel):
    terminal_id: str
    model: str
    connectivity: Literal["wifi", "chip_4g", "ethernet"]
    status: Literal["online", "offline", "error"]
    last_seen_at: datetime
    last_error: str | None
    suggested_checks: list[str]


class LookupDeclineCodeInput(_Input):
    code: str = Field(min_length=1, max_length=4)


class DeclineCodeInfo(BaseModel):
    code: str
    known: bool
    description: str | None = None
    action: str | None = None


class GetRecentTransactionsInput(_Input):
    days: int = Field(ge=1, le=30)
    status: Literal["approved", "declined"] | None = None
    limit: int = Field(default=20, ge=1, le=50)


class TransactionItem(BaseModel):
    id: str
    created_at: datetime
    amount_cents: int
    method: Literal["credit", "debit", "pix", "payment_link"]
    installments: int
    status: Literal["approved", "declined"]
    decline_code: str | None


class GetCustomerProfileInput(_Input):
    pass


class CustomerProfile(BaseModel):
    trade_name: str
    plan: str
    settlement_days: int
    anticipation_enabled: bool
    terminal_count: int


# --- Escalation ------------------------------------------------------------------------------
HandoffReason = Literal[
    "low_confidence",
    "human_request",
    "sensitive_topic",
    "repeated_failures",
    "side_effect_action",
]


class CreateTicketInput(_Input):
    reason: HandoffReason
    summary: str = Field(min_length=1, max_length=1000)


class TicketCreated(BaseModel):
    ticket_id: str
    sla_due_at: datetime
    expires_at: datetime


class OpenDisputeParams(_Input):
    transaction_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


class RequestActionApprovalInput(_Input):
    action: Literal["open_dispute"]
    params: OpenDisputeParams


class ApprovalPending(BaseModel):
    ticket_id: str
    decision: Literal["pending"]


# --- Registry --------------------------------------------------------------------------------
TOOL_INPUTS: dict[str, type[BaseModel]] = {
    "search_knowledge_base": SearchKnowledgeBaseInput,
    "web_search": WebSearchInput,
    "get_settlement_schedule": GetSettlementScheduleInput,
    "diagnose_terminal": DiagnoseTerminalInput,
    "lookup_decline_code": LookupDeclineCodeInput,
    "get_recent_transactions": GetRecentTransactionsInput,
    "get_customer_profile": GetCustomerProfileInput,
    "create_ticket": CreateTicketInput,
    "request_action_approval": RequestActionApprovalInput,
}

TOOL_OUTPUTS: dict[str, type[BaseModel]] = {
    "search_knowledge_base": KnowledgeHit,
    "web_search": WebResult,
    "get_settlement_schedule": SettlementDay,
    "diagnose_terminal": TerminalDiagnosis,
    "lookup_decline_code": DeclineCodeInfo,
    "get_recent_transactions": TransactionItem,
    "get_customer_profile": CustomerProfile,
    "create_ticket": TicketCreated,
    "request_action_approval": ApprovalPending,
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "search_knowledge_base": "Search public Getnet content (products, fees, help center).",
    "web_search": "Search the public web for general questions (weather, exchange rates).",
    "get_settlement_schedule": "Expected settlements (receivables) of the current merchant.",
    "diagnose_terminal": "Status and suggested checks of the current merchant's terminals.",
    "lookup_decline_code": "Meaning and recommended action for a card decline code.",
    "get_recent_transactions": "Recent sales of the current merchant, optionally only declined.",
    "get_customer_profile": "Plan and settlement settings of the current merchant.",
    "create_ticket": "Open a ticket for a human operator.",
    "request_action_approval": "Ask a human operator to approve an action with side effects.",
}

TIMEOUT_SECONDS: dict[str, float] = {
    "search_knowledge_base": 5.0,
    "web_search": 5.0,
    "get_settlement_schedule": 2.0,
    "diagnose_terminal": 2.0,
    "lookup_decline_code": 2.0,
    "get_recent_transactions": 2.0,
    "get_customer_profile": 2.0,
    "create_ticket": 2.0,
    "request_action_approval": 2.0,
}

ALLOWLIST: dict[str, set[str]] = {
    "knowledge": {"search_knowledge_base", "web_search"},
    "support": {
        "get_settlement_schedule",
        "diagnose_terminal",
        "lookup_decline_code",
        "get_recent_transactions",
        "get_customer_profile",
        "search_knowledge_base",
    },
    "escalation": {"create_ticket", "request_action_approval"},
    "supervisor": set(),
}


def openai_tool_specs(agent: str) -> list[dict[str, Any]]:
    """Tool specs for `bind_tools`, limited to the agent's allowlist."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": TOOL_INPUTS[name].model_json_schema(),
            },
        }
        for name in sorted(ALLOWLIST[agent])
    ]
