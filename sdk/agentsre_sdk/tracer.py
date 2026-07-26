from __future__ import annotations

from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource as OTelResource
from opentelemetry.sdk.trace import TracerProvider

from agentsre_sdk.config import SDKConfig
from agentsre_sdk.exporters.http_exporter import AgentSREHTTPExporter
from agentsre_sdk.processors.pii_processor import PIIProcessor
from agentsre_sdk.processors.span_processor import AgentSRESpanProcessor
from agentsre_sdk.utils.resource import collect_resource, detect_installed_version


@dataclass(slots=True)
class TracingSetup:
    tracer_provider: TracerProvider
    span_processor: AgentSRESpanProcessor
    exporter: AgentSREHTTPExporter


def configure_tracing(config: SDKConfig) -> TracingSetup:
    framework = "LangGraph" if config.instrument_langgraph and detect_installed_version("langgraph") else None
    agent_resource = collect_resource(framework=framework, framework_version=detect_installed_version("langgraph") if framework else None)
    otel_resource = OTelResource.create(
        {
            "service.name": config.service_name,
            "deployment.environment": config.environment,
            "agentsre.tenant_id": config.tenant_id,
            "agentsre.project_id": config.project_id,
            "agentsre.workflow_id": config.workflow_id,
            "agentsre.session_id": config.session_id,
            "telemetry.sdk.name": "agentsre-sdk",
            "telemetry.sdk.language": "python",
            "telemetry.sdk.version": agent_resource.sdk_version,
        }
    )
    tracer_provider = TracerProvider(resource=otel_resource)
    exporter = AgentSREHTTPExporter(config)
    pii_processor = PIIProcessor(config.pii_redaction, config.normalized_sensitive_fields)
    span_processor = AgentSRESpanProcessor(config, exporter, agent_resource, pii_processor)
    tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(tracer_provider)
    return TracingSetup(tracer_provider=tracer_provider, span_processor=span_processor, exporter=exporter)
