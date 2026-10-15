"""Golden-set eval against a running API with the real model (REQ-OBS-06, REQ-ORC-01).
Exits 1 when route accuracy < 95%. Tools, handoff and guardrail expectations are reported.

    docker compose --profile eval run --rm eval
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
TARGET_ROUTE_ACCURACY = 0.95


def load_scenarios() -> list[dict[str, Any]]:
    data = yaml.safe_load((ROOT / "evals" / "golden_set.yaml").read_text(encoding="utf-8"))
    return list(data["scenarios"])


def check(expected: dict[str, Any], body: dict[str, Any]) -> dict[str, bool]:
    """One bool per expectation the scenario declares; a missing key is not checked."""
    route, blocked = set(body["route"]), body["guardrails"]["input"] == "blocked"
    out: dict[str, bool] = {}
    if "route" in expected:
        want = set(expected["route"])
        out["route"] = blocked if want == {"safe_response"} else want <= route
    if "tools_contains" in expected:
        used = {t["name"] for t in body["tools_used"]}
        out["tools"] = bool(used & set(expected["tools_contains"]))
    if "handoff" in expected:
        out["handoff"] = body["handoff"]["status"] == expected["handoff"]
    if "guardrails_input" in expected:
        out["guardrails"] = body["guardrails"]["input"] == expected["guardrails_input"]
    if expected.get("pii_masked"):
        out["pii"] = body["guardrails"]["input"] == "masked"
    return out


def _post(client: httpx.Client, payload: dict[str, Any]) -> dict[str, Any]:
    resp = client.post("/v1/chat", json=payload)
    if resp.status_code == 429:  # the golden set is close to the per-minute limit
        time.sleep(int(resp.headers.get("Retry-After", "60")))
        resp = client.post("/v1/chat", json=payload)
    resp.raise_for_status()
    return dict(resp.json())


def main() -> int:
    from app.api.auth import create_token

    base_url = os.environ.get("EVAL_BASE_URL", "http://api:8000")
    token = create_token(os.environ.get("EVAL_USER", "cliente1988"), "merchant")
    totals: dict[str, list[bool]] = {}
    with httpx.Client(
        base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=60
    ) as client:
        for sc in load_scenarios():
            payload: dict[str, Any] = {"message": sc["message"]}
            if "context_message" in sc:
                payload["conversation_id"] = _post(client, {"message": sc["context_message"]})[
                    "conversation_id"
                ]
            result = check(sc["expected"], _post(client, payload))
            for name, ok in result.items():
                totals.setdefault(name, []).append(ok)
            print(f"{'PASS' if all(result.values()) else 'FAIL'}  {sc['id']}  {result}")
    for name, oks in totals.items():
        print(f"{name:<11} {sum(oks)}/{len(oks)}")
    accuracy = sum(totals["route"]) / len(totals["route"])
    if accuracy < TARGET_ROUTE_ACCURACY:
        print(f"FAIL: route accuracy {accuracy:.0%} < {TARGET_ROUTE_ACCURACY:.0%}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
