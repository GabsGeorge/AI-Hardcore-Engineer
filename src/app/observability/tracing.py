"""OpenTelemetry setup. Spans are always created (so every request has a W3C trace_id); they are
exported over OTLP only when OTEL_EXPORTER_OTLP_ENDPOINT is set (profile `obs`)."""

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_configured = False


def configure_tracing(otlp_endpoint: str) -> None:
    global _configured
    if _configured:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "getnet-support-api"}))
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces"))
        )
    trace.set_tracer_provider(provider)
    _configured = True


def get_tracer() -> trace.Tracer:
    return trace.get_tracer("getnet-support")


def current_trace_id() -> str:
    return format(trace.get_current_span().get_span_context().trace_id, "032x")


def set_prompt_version(span: trace.Span, prompt_name: str) -> None:
    """Anota o span com ``prompt.version`` do prompt carregado (REQ-OBS-02, ADR 0009)."""
    from app.core.prompts import prompt_version

    span.set_attribute("prompt.name", prompt_name)
    span.set_attribute("prompt.version", prompt_version(prompt_name))
