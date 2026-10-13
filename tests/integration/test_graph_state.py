import json

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import get_settings
from app.db.pool import Pool
from app.graph.builder import build_graph
from tests.fakes import FakeLLM, Scripted, make_plan

pytestmark = pytest.mark.req("REQ-ORC-06")


async def test_state_is_persisted_and_reloaded_after_restart(
    db_pool: Pool, fake_llm: FakeLLM
) -> None:
    config = {
        "configurable": {
            "thread_id": "cliente1988:restart",
            "user_id": "cliente1988",
            "trace_id": "0" * 32,
        },
        "recursion_limit": 25,
    }
    # A plan that exhausts the token budget is stored and then degrades: no specialist runs,
    # so this test does not depend on how specialists are implemented.
    budget = get_settings().token_budget_per_run
    fake_llm.script(supervisor=[Scripted(make_plan("knowledge", language="en"), tokens=budget)])
    before = await build_graph(AsyncPostgresSaver(db_pool)).ainvoke(
        {
            "messages": [HumanMessage(content="What is Get Smart?")],
            "plan": None,
            "step": 0,
            "attempts": 0,
        },
        config,
    )

    # A brand-new graph and checkpointer on the same database simulates a process restart.
    snapshot = await build_graph(AsyncPostgresSaver(db_pool)).aget_state(config)
    after = snapshot.values
    assert after["route_trace"] == before["route_trace"]
    assert after["final_response"] == before["final_response"]
    assert after["plan"] == before["plan"] is not None
    assert after["language"] == "en"
    assert [m.content for m in after["messages"]] == [m.content for m in before["messages"]]
    # Everything except LangChain messages is plain JSON-serialisable data.
    json.dumps({k: v for k, v in after.items() if k != "messages"})
