"""Shared helpers for specialists: allowlisted, validated, timed and audited tool calls."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.db import repo
from app.db.pool import get_pool
from app.graph.state import AgentName, AgentResult, Source, SubTask, ToolCallRecord
from app.observability.metrics import TOOL_ERRORS
from app.tools.interfaces import ALLOWLIST, TIMEOUT_SECONDS, TOOL_INPUTS

ToolImpl = Callable[[Any, RunnableConfig], Awaitable[Any]]


async def _audit(config: RunnableConfig, action: str, tool: str, outcome: str) -> None:
    conf = config.get("configurable", {})
    await repo.insert_audit_event(
        get_pool(),
        actor_id=conf["user_id"],
        actor_role=conf.get("user_role", "merchant"),
        action=action,
        target=f"tool:{tool}",
        outcome=outcome,
        trace_id=conf.get("trace_id", ""),
    )


async def call_tool(
    agent: str, name: str, impl: ToolImpl | None, raw_args: dict[str, Any], config: RunnableConfig
) -> tuple[Any | None, ToolCallRecord]:
    """Runs a tool for an agent. Outside the allowlist → `denied` and audited, never executed
    (REQ-ORC-05). An unknown name inside the allowlist is `error`, not `denied`: the agent is
    allowed to call it, we just do not have an implementation. Arguments are validated against
    the frozen interface before running."""
    if name not in ALLOWLIST.get(agent, set()):
        await _audit(config, "tool_denied", name, "denied")
        return None, {"name": name, "status": "denied", "latency_ms": 0}
    if impl is None:
        await _audit(config, "tool_call", name, "error")
        return None, {"name": name, "status": "error", "latency_ms": 0}
    started = time.perf_counter()
    try:
        args = TOOL_INPUTS[name].model_validate(raw_args)
        output = await asyncio.wait_for(impl(args, config), TIMEOUT_SECONDS[name])
        status: Any = "ok"
    except TimeoutError:
        output, status = None, "timeout"
    except Exception:  # invalid arguments or a failing tool: the agent reports an honest error
        output, status = None, "error"
    latency = round((time.perf_counter() - started) * 1000)
    await _audit(config, "tool_call", name, "allowed" if status == "ok" else "error")
    if status != "ok":
        TOOL_ERRORS.labels(name).inc()
    return output, {"name": name, "status": status, "latency_ms": latency}


def make_result(
    subtask: SubTask,
    agent: AgentName,
    *,
    answer: str = "",
    confidence: float = 0.0,
    sources: Iterable[Source] = (),
    tools_used: Iterable[ToolCallRecord] = (),
    error: str | None = None,
) -> AgentResult:
    return {
        "subtask_id": subtask["id"],
        "agent": agent,
        "answer": answer,
        "confidence": max(0.0, min(1.0, confidence)),
        "sources": list(sources),
        "tools_used": list(tools_used),
        "error": error,
    }
