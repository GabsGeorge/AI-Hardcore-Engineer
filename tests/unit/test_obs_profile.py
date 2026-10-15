"""Config do profile ``obs`` do compose e dashboards de Grafana (REQ-OBS-03, REQ-INF-01).

Checa a shape dos arquivos de infra sem subir nada — garante que o PR não acidentalmente
quebra o YAML/JSON e que todas as métricas usadas pelos dashboards estão de fato expostas
por ``observability/metrics``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
METRIC_RE = re.compile(r"getnet_[a-z_]+")


@pytest.mark.req("REQ-OBS-03")
def test_prometheus_scrape_targets_api() -> None:
    config = yaml.safe_load((ROOT / "deploy/prometheus/prometheus.yml").read_text())
    jobs = {job["job_name"]: job for job in config["scrape_configs"]}
    assert "getnet-api" in jobs
    targets = jobs["getnet-api"]["static_configs"][0]["targets"]
    assert "api:9100" in targets  # internal exporter port, not the public API


@pytest.mark.req("REQ-OBS-03")
def test_prometheus_alerts_cover_slo_signals() -> None:
    alerts = yaml.safe_load((ROOT / "deploy/prometheus/alerts.yml").read_text())
    rules = [r for group in alerts["groups"] for r in group["rules"]]
    names = {r["alert"] for r in rules}
    for required in ("HighRequestLatencyP95", "ToolErrorRateHigh", "GuardrailBlockSpike"):
        assert required in names, f"alerta {required} ausente"


@pytest.mark.req("REQ-OBS-03")
def test_grafana_dashboards_only_reference_exposed_metrics() -> None:
    from app.observability import metrics  # import só na frontier do teste

    exported_names: set[str] = set()
    for attr in dir(metrics):
        value = getattr(metrics, attr)
        if value.__class__.__name__ in ("Counter", "Histogram"):
            name = getattr(value, "_name", None)
            if isinstance(name, str):
                exported_names.add(name)
    # prometheus-client expõe o nome base; o endpoint anexa _total/_bucket/_sum/_count sozinho
    for dash_path in (ROOT / "deploy/grafana/dashboards").glob("*.json"):
        dash = json.loads(dash_path.read_text())
        used = set(METRIC_RE.findall(json.dumps(dash)))
        for name in used:
            base = re.sub(r"_bucket$|_sum$|_count$|_total$", "", name)
            assert base in exported_names, (
                f"dashboard {dash_path.name} usa {name!r} que não existe em metrics.py"
            )


@pytest.mark.req("REQ-INF-01")
def test_compose_profile_obs_defines_prometheus_and_grafana() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]
    for name in ("prometheus", "grafana"):
        assert name in services, f"serviço {name} ausente"
        assert "obs" in services[name].get("profiles", []), (
            f"{name} deve estar no profile 'obs' (não deve subir por padrão)"
        )
