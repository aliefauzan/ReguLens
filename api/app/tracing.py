"""OpenTelemetry -> Cloud Trace. Best effort: if the exporter cannot start (no
credentials locally, for instance) the app still serves traffic."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def instrument(app, project_id: str) -> None:
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter(project_id=project_id)))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:  # noqa: BLE001 - tracing must never break serving
        logger.warning("tracing disabled", extra={"extra_fields": {"reason": str(exc)}})
