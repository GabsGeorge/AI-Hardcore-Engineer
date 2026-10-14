"""Tools exposed to the escalation agent (REQ-HITL-02, REQ-HITL-04)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from langchain_core.runnables import RunnableConfig

from app.core.config import get_settings
from app.tools.interfaces import (
    ApprovalPending,
    CreateTicketInput,
    RequestActionApprovalInput,
    TicketCreated,
)


async def create_ticket(args: CreateTicketInput, config: RunnableConfig) -> TicketCreated:
    """Fabricates the ticket metadata; the row is written by the escalation node."""
    s = get_settings()
    now = datetime.now(UTC)
    return TicketCreated(
        ticket_id=str(uuid4()),
        sla_due_at=now + timedelta(minutes=s.handoff_sla_minutes),
        expires_at=now + timedelta(hours=s.handoff_expiry_hours),
    )


async def request_action_approval(
    args: RequestActionApprovalInput, config: RunnableConfig
) -> ApprovalPending:
    """Side-effect actions wait for operator approval (REQ-HITL-04). Nothing runs here."""
    return ApprovalPending(ticket_id=str(uuid4()), decision="pending")


ESCALATION_TOOLS: dict[str, Any] = {
    "create_ticket": create_ticket,
    "request_action_approval": request_action_approval,
}


def new_ticket_id() -> UUID:
    return uuid4()
