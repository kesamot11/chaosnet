"""Tracing for the lab service (#157, ADR-009).

Spans go to Jaeger over OTLP when OTEL_EXPORTER_OTLP_ENDPOINT is set (the generated lab
sets it); without it, as in unit tests, nothing is exported. The instrumentation of
FastAPI reads the W3C `traceparent` header of an incoming request, the instrumentation
of httpx adds it to every outgoing call, so the spans of all services join one trace.
"""

import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_tracing(app: FastAPI) -> None:
    """Call once at import, before the app starts: middleware cannot be added later."""
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    resource = Resource.create({SERVICE_NAME: os.environ["SERVICE_NAME"]})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,metrics")
    HTTPXClientInstrumentor().instrument()  # every client created afterwards
