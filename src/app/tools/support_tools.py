"""Support tools (contracts/tools.md) over the mock merchant data. The user is read only from
`config["configurable"]["user_id"]`, set by the API from the JWT (ADR 0005, REQ-SEC-03); no input
model carries identity. Validation, the 2 s timeout and the `tool_call` audit event are applied by
`app.agents.common.call_tool`. An empty list means "no records"."""

from datetime import date, timedelta
from typing import Any

import psycopg
from langchain_core.runnables import RunnableConfig

from app.agents.common import ToolImpl
from app.core.config import get_settings
from app.core.resilience import with_retry
from app.db import support_repo
from app.db.pool import get_pool
from app.tools.interfaces import (
    CustomerProfile,
    DeclineCodeInfo,
    DiagnoseTerminalInput,
    GetCustomerProfileInput,
    GetRecentTransactionsInput,
    GetSettlementScheduleInput,
    LookupDeclineCodeInput,
    SettlementDay,
    TerminalDiagnosis,
    TransactionItem,
)

# Documented first checks per problem, keyed by language and then by connectivity or status.
_CHECKS: dict[str, dict[str, list[str]]] = {
    "pt": {
        "chip_4g": [
            "Confira se o chip está bem encaixado e se há sinal da operadora no local.",
            "Reinicie a maquininha segurando o botão de ligar.",
            "Se houver Wi-Fi no local, conecte a maquininha a ele nas configurações de rede.",
        ],
        "wifi": [
            "Confira se o roteador está ligado e com internet.",
            "Confirme o nome e a senha da rede Wi-Fi nas configurações da maquininha.",
            "Reinicie a maquininha segurando o botão de ligar.",
        ],
        "ethernet": [
            "Confira se o cabo de rede está bem conectado na maquininha e no roteador.",
            "Reinicie a maquininha e o roteador.",
        ],
        "error": [
            "Reinicie a maquininha segurando o botão de ligar.",
            "Se o erro continuar, fale com o atendimento Getnet informando o código do erro.",
        ],
    },
    "en": {
        "chip_4g": [
            "Check that the SIM card is properly inserted and that there is carrier signal.",
            "Restart the card machine by holding the power button.",
            "If Wi-Fi is available, connect the card machine to it in the network settings.",
        ],
        "wifi": [
            "Check that the router is on and has internet access.",
            "Confirm the Wi-Fi network name and password in the card machine settings.",
            "Restart the card machine by holding the power button.",
        ],
        "ethernet": [
            "Check that the network cable is firmly connected to the card machine and router.",
            "Restart the card machine and the router.",
        ],
        "error": [
            "Restart the card machine by holding the power button.",
            "If the error persists, contact Getnet support with the error code.",
        ],
    },
}


def _user(config: RunnableConfig) -> str:
    """The token's user. Missing identity fails closed (KeyError), never falls back."""
    return str(config["configurable"]["user_id"])


def _language(config: RunnableConfig) -> str:
    lang = str(config.get("configurable", {}).get("language") or "pt")
    return "en" if lang.startswith("en") else "pt"


def reference_date() -> date:
    """Mock data is relative to SEED_REFERENCE_DATE when set (tests, demos), else today."""
    return get_settings().seed_reference_date or date.today()


def _checks(row: dict[str, Any], lang: str) -> list[str]:
    if row["status"] == "online":
        return []
    key = "error" if row["status"] == "error" else row["connectivity"]
    return list(_CHECKS[lang][key])


@with_retry(attempts=2, retry_on=(psycopg.OperationalError,))
async def get_settlement_schedule(
    args: GetSettlementScheduleInput, config: RunnableConfig
) -> list[SettlementDay]:
    rows = await support_repo.settlement_schedule(
        get_pool(), _user(config), args.from_date, args.to_date
    )
    return [SettlementDay.model_validate(r) for r in rows]


@with_retry(attempts=2, retry_on=(psycopg.OperationalError,))
async def diagnose_terminal(
    args: DiagnoseTerminalInput, config: RunnableConfig
) -> list[TerminalDiagnosis]:
    rows = await support_repo.terminals(get_pool(), _user(config), args.terminal_id)
    lang = _language(config)
    return [
        TerminalDiagnosis(
            terminal_id=r["id"],
            model=r["model"],
            connectivity=r["connectivity"],
            status=r["status"],
            last_seen_at=r["last_seen_at"],
            last_error=r["last_error"],
            suggested_checks=_checks(r, lang),
        )
        for r in rows
    ]


@with_retry(attempts=2, retry_on=(psycopg.OperationalError,))
async def lookup_decline_code(
    args: LookupDeclineCodeInput, config: RunnableConfig
) -> DeclineCodeInfo:
    row = await support_repo.decline_code(get_pool(), args.code)
    if row is None:
        return DeclineCodeInfo(code=args.code, known=False)
    lang = _language(config)
    return DeclineCodeInfo(
        code=row["code"],
        known=True,
        description=row[f"description_{lang}"],
        action=row[f"action_{lang}"],
    )


@with_retry(attempts=2, retry_on=(psycopg.OperationalError,))
async def get_recent_transactions(
    args: GetRecentTransactionsInput, config: RunnableConfig
) -> list[TransactionItem]:
    since = reference_date() - timedelta(days=args.days)
    rows = await support_repo.recent_transactions(
        get_pool(), _user(config), since, args.status, args.limit
    )
    return [TransactionItem.model_validate(r) for r in rows]


@with_retry(attempts=2, retry_on=(psycopg.OperationalError,))
async def get_customer_profile(
    args: GetCustomerProfileInput, config: RunnableConfig
) -> CustomerProfile:
    row = await support_repo.customer_profile(get_pool(), _user(config))
    if row is None:
        raise LookupError("no merchant profile for the current user")
    return CustomerProfile.model_validate(row)


SUPPORT_TOOLS: dict[str, ToolImpl] = {
    "get_settlement_schedule": get_settlement_schedule,
    "diagnose_terminal": diagnose_terminal,
    "lookup_decline_code": lookup_decline_code,
    "get_recent_transactions": get_recent_transactions,
    "get_customer_profile": get_customer_profile,
}
