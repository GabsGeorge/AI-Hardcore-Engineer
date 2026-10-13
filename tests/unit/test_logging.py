import json
import re

import pytest

from app.observability.logging import configure_logging, get_logger


@pytest.mark.req("REQ-OBS-01", "REQ-GR-02")
def test_request_log_is_json_with_trace_id_and_masked_pii(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    get_logger().info(
        "request",
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        route="/v1/chat",
        latency_ms=12,
        status=200,
        detail="cartão 4111 1111 1111 1111 e cpf 529.982.247-25",
    )
    line = capsys.readouterr().out.strip().splitlines()[-1]
    event = json.loads(line)
    assert re.fullmatch(r"[0-9a-f]{32}", event["trace_id"])
    assert event["route"] == "/v1/chat"
    assert event["latency_ms"] == 12
    assert event["status"] == 200
    assert "4111" not in line and "529.982" not in line
    assert "[CARTAO]" in event["detail"] and "[CPF]" in event["detail"]
