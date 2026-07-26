import httpx
from opentelemetry import context as otel_context

from agentsre_sdk.config import SDKConfig
from agentsre_sdk.exporters.http_exporter import AgentSREHTTPExporter
from agentsre_sdk.schema.models import AgentSREPayload


class FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad status", request=httpx.Request("POST", "https://x"), response=httpx.Response(self.status_code))


class FakeClient:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[dict[str, object]] = []
        self.suppression_seen = False

    def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:
        self.suppression_seen = bool(otel_context.get_value(otel_context._SUPPRESS_INSTRUMENTATION_KEY))
        self.calls.append({"url": url, "headers": headers, "json": json})
        if len(self.calls) <= self.failures:
            raise httpx.ConnectError("network unavailable")
        return FakeResponse()

    def close(self) -> None:
        self.calls.append({"closed": True})


def test_exporter_posts_json_with_auth_headers(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    client = FakeClient()
    exporter = AgentSREHTTPExporter(_config(), client=client)

    assert exporter.export(_payload()) is True
    call = client.calls[0]
    assert call["url"] == "https://agentsre.example.com/api/v1/ingest"
    assert call["headers"] == {"Content-Type": "application/json", "Authorization": "Bearer test-key"}
    assert call["json"]["execution"]["tenant_id"] == "company_xyz"
    assert client.suppression_seen is True


def test_exporter_retries_network_failures(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    client = FakeClient(failures=2)
    exporter = AgentSREHTTPExporter(_config(), client=client)

    assert exporter.export(_payload()) is True
    assert len(client.calls) == 3


def test_exporter_shutdown_is_idempotent_and_export_after_shutdown_does_not_raise() -> None:
    client = FakeClient()
    exporter = AgentSREHTTPExporter(_config(), client=client)

    exporter.shutdown()
    exporter.shutdown()

    assert exporter.export(_payload()) is False
    assert client.calls == []


def _config() -> SDKConfig:
    return SDKConfig(
        tenant_id="company_xyz",
        project_id="travel-ai",
        service_name="trip-planner",
        environment="production",
        backend_url="https://agentsre.example.com/api/v1/ingest",
        api_key="test-key",
        user_id="user_1001",
        workflow_id="wf_trip_planner",
        session_id="session_001",
    )


def _payload() -> AgentSREPayload:
    return AgentSREPayload.model_validate(
        {
            "execution": {
                "trace_id": "9f3a5b2c8d7e4f109a1b2c3d4e5f6789",
                "execution_id": "exec_20260629_001",
                "workflow_id": "wf_trip_planner",
                "session_id": "session_001",
                "user_id": "user_1001",
                "tenant_id": "company_xyz",
                "project_id": "travel-ai",
                "service_name": "trip-planner",
                "environment": "production",
                "execution_start": "2026-06-29T10:15:20.100Z",
                "execution_end": "2026-06-29T10:15:20.980Z",
                "total_duration_ms": 880,
            },
            "resource": {
                "sdk_version": "1.0.0",
                "plugin_version": "1.0.0",
                "framework": "LangGraph",
                "framework_version": "0.3.14",
                "language": "Python",
                "host_name": "planner-vm-01",
                "process_id": 4521,
                "os": "Ubuntu 24.04",
                "cpu_architecture": "x86_64",
                "runtime": "Python",
                "runtime_version": "3.12.4",
                "container_id": None,
                "kubernetes_pod": None,
                "cloud_provider": None,
            },
            "spans": [
                {
                    "trace_id": "9f3a5b2c8d7e4f109a1b2c3d4e5f6789",
                    "span_id": "101",
                    "parent_span_id": None,
                    "span_name": "OpenAI Chat Completion",
                    "span_kind": "LLM",
                    "start_time": "2026-06-29T10:15:20.200Z",
                    "end_time": "2026-06-29T10:15:20.980Z",
                    "duration_ms": 780,
                    "status": "SUCCESS",
                    "error_type": None,
                    "error_message": None,
                    "trace_context": "00-9f3a5b2c8d7e4f109a1b2c3d4e5f6789-101-01",
                    "baggage": {},
                    "retry_count": 0,
                    "iteration_count": 1,
                    "agent": None,
                    "llm": {
                        "provider": "OpenAI",
                        "model": "gpt-4o",
                        "temperature": 0.2,
                        "max_tokens": 1000,
                        "top_p": 1.0,
                        "frequency_penalty": 0,
                        "presence_penalty": 0,
                        "system_prompt": "You are a travel planner.",
                        "prompt": "Create a travel itinerary for Mysore.",
                        "response": "I need the current weather before generating the itinerary.",
                        "finish_reason": "stop",
                        "input_tokens": 125,
                        "output_tokens": 98,
                        "total_tokens": 223,
                        "estimated_cost": 0.0032,
                    },
                    "tool": None,
                    "memory": None,
                    "reasoning": None,
                    "http": None,
                }
            ],
        }
    )
