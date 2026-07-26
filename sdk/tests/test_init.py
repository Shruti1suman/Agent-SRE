import agentsre_sdk
from agentsre_sdk.config import DEFAULT_BACKEND_URL


class FakeSpanProcessor:
    def __init__(self) -> None:
        self.shutdown_called = False

    def shutdown(self) -> None:
        self.shutdown_called = True


class FakeTracing:
    def __init__(self) -> None:
        self.tracer_provider = object()
        self.span_processor = FakeSpanProcessor()


def test_init_builds_config_and_instrumentors(monkeypatch) -> None:
    agentsre_sdk._STATE = None
    fake_tracing = FakeTracing()
    monkeypatch.setattr(agentsre_sdk, "configure_tracing", lambda config: fake_tracing)
    captured = {}

    def fake_instrument_all(tracer_provider, *, instrument_langgraph=True, instrument_crewai=True):
        captured["instrument_langgraph"] = instrument_langgraph
        captured["instrument_crewai"] = instrument_crewai
        return [{"name": "langgraph", "status": "instrumented"}]

    monkeypatch.setattr(agentsre_sdk, "instrument_all", fake_instrument_all)

    state = agentsre_sdk.init(
        tenant_id="company_xyz",
        project_id="travel-ai",
        service_name="trip-planner",
        environment="production",
        backend_url="https://agentsre.example.com/api/v1/ingest",
        api_key="test-key",
        sensitive_fields=["email"],
    )

    assert state.config.tenant_id == "company_xyz"
    assert state.config.instrument_langgraph is True
    assert state.config.instrument_crewai is True
    assert state.config.normalized_sensitive_fields == {"email"}
    assert captured["instrument_langgraph"] is True
    assert captured["instrument_crewai"] is True
    assert state.instrumentors == [{"name": "langgraph", "status": "instrumented"}]
    assert agentsre_sdk.init(
        tenant_id="ignored",
        project_id="ignored",
        service_name="ignored",
        environment="ignored",
        backend_url="https://ignored",
        api_key="ignored",
    ) is state
    agentsre_sdk.shutdown()
    assert fake_tracing.span_processor.shutdown_called is True


def test_init_can_disable_langgraph_instrumentation(monkeypatch) -> None:
    agentsre_sdk._STATE = None
    fake_tracing = FakeTracing()
    monkeypatch.setattr(agentsre_sdk, "configure_tracing", lambda config: fake_tracing)
    captured = {}

    def fake_instrument_all(tracer_provider, *, instrument_langgraph=True, instrument_crewai=True):
        captured["instrument_langgraph"] = instrument_langgraph
        captured["instrument_crewai"] = instrument_crewai
        return []

    monkeypatch.setattr(agentsre_sdk, "instrument_all", fake_instrument_all)

    state = agentsre_sdk.init(
        tenant_id="company_xyz",
        project_id="travel-ai",
        service_name="trip-planner",
        environment="production",
        backend_url="https://agentsre.example.com/api/v1/ingest",
        api_key="test-key",
        instrument_langgraph=False,
    )

    assert state.config.instrument_langgraph is False
    assert captured["instrument_langgraph"] is False
    assert captured["instrument_crewai"] is True
    agentsre_sdk.shutdown()


def test_init_can_disable_crewai_instrumentation(monkeypatch) -> None:
    agentsre_sdk._STATE = None
    fake_tracing = FakeTracing()
    monkeypatch.setattr(agentsre_sdk, "configure_tracing", lambda config: fake_tracing)
    captured = {}

    def fake_instrument_all(tracer_provider, *, instrument_langgraph=True, instrument_crewai=True):
        captured["instrument_crewai"] = instrument_crewai
        return []

    monkeypatch.setattr(agentsre_sdk, "instrument_all", fake_instrument_all)

    state = agentsre_sdk.init(
        tenant_id="company_xyz",
        project_id="travel-ai",
        service_name="trip-planner",
        environment="production",
        backend_url="https://agentsre.example.com/api/v1/ingest",
        api_key="test-key",
        instrument_crewai=False,
    )

    assert state.config.instrument_crewai is False
    assert captured["instrument_crewai"] is False
    agentsre_sdk.shutdown()


def test_init_uses_default_backend_url(monkeypatch) -> None:
    agentsre_sdk._STATE = None
    fake_tracing = FakeTracing()
    monkeypatch.setattr(agentsre_sdk, "configure_tracing", lambda config: fake_tracing)
    monkeypatch.setattr(agentsre_sdk, "instrument_all", lambda tracer_provider, *, instrument_langgraph=True, instrument_crewai=True: [])
    monkeypatch.delenv("AGENTSRE_BACKEND_URL", raising=False)

    state = agentsre_sdk.init(
        tenant_id="company_xyz",
        project_id="travel-ai",
        service_name="trip-planner",
        environment="production",
        api_key="test-key",
    )

    assert state.config.backend_url == DEFAULT_BACKEND_URL
    agentsre_sdk.shutdown()


def test_init_generates_uuid_session_id_when_omitted(monkeypatch) -> None:
    agentsre_sdk._STATE = None
    fake_tracing = FakeTracing()
    monkeypatch.setattr(agentsre_sdk, "configure_tracing", lambda config: fake_tracing)
    monkeypatch.setattr(agentsre_sdk, "instrument_all", lambda tracer_provider, *, instrument_langgraph=True, instrument_crewai=True: [])

    state = agentsre_sdk.init(
        tenant_id="company_xyz",
        project_id="research-agent-demo",
        service_name="research-agent",
        environment="production",
        backend_url="https://agentsre.example.com/api/v1/ingest",
        api_key="test-key",
    )

    parts = state.config.session_id.split("_", 1)
    assert parts[0] == "session"
    assert len(parts) == 2
    assert len(parts[1]) == 36
    assert parts[1].count("-") == 4
    agentsre_sdk.shutdown()


def test_init_keeps_explicit_session_id(monkeypatch) -> None:
    agentsre_sdk._STATE = None
    fake_tracing = FakeTracing()
    monkeypatch.setattr(agentsre_sdk, "configure_tracing", lambda config: fake_tracing)
    monkeypatch.setattr(agentsre_sdk, "instrument_all", lambda tracer_provider, *, instrument_langgraph=True, instrument_crewai=True: [])

    state = agentsre_sdk.init(
        tenant_id="company_xyz",
        project_id="research-agent-demo",
        service_name="research-agent",
        environment="production",
        backend_url="https://agentsre.example.com/api/v1/ingest",
        api_key="test-key",
        session_id="session_external_controlled",
    )

    assert state.config.session_id == "session_external_controlled"
    agentsre_sdk.shutdown()


def test_init_reads_required_values_from_environment(monkeypatch) -> None:
    agentsre_sdk._STATE = None
    fake_tracing = FakeTracing()
    monkeypatch.setattr(agentsre_sdk, "configure_tracing", lambda config: fake_tracing)
    monkeypatch.setattr(agentsre_sdk, "instrument_all", lambda tracer_provider, *, instrument_langgraph=True, instrument_crewai=True: [])
    monkeypatch.setenv("AGENTSRE_TENANT_ID", "env_company")
    monkeypatch.setenv("AGENTSRE_PROJECT_ID", "env_project")
    monkeypatch.setenv("AGENTSRE_SERVICE_NAME", "env_service")
    monkeypatch.setenv("AGENTSRE_ENVIRONMENT", "env")
    monkeypatch.setenv("AGENTSRE_BACKEND_URL", "https://env.example.com/api/v1/ingest")
    monkeypatch.setenv("AGENTSRE_API_KEY", "env-key")
    monkeypatch.setenv("AGENTSRE_USER_ID", "env-user")

    state = agentsre_sdk.init()

    assert state.config.tenant_id == "env_company"
    assert state.config.project_id == "env_project"
    assert state.config.service_name == "env_service"
    assert state.config.environment == "env"
    assert state.config.backend_url == "https://env.example.com/api/v1/ingest"
    assert state.config.api_key == "env-key"
    assert state.config.user_id == "env-user"
    agentsre_sdk.shutdown()


def test_init_explicit_backend_url_overrides_environment(monkeypatch) -> None:
    agentsre_sdk._STATE = None
    fake_tracing = FakeTracing()
    monkeypatch.setattr(agentsre_sdk, "configure_tracing", lambda config: fake_tracing)
    monkeypatch.setattr(agentsre_sdk, "instrument_all", lambda tracer_provider, *, instrument_langgraph=True, instrument_crewai=True: [])
    monkeypatch.setenv("AGENTSRE_BACKEND_URL", "https://env.example.com/api/v1/ingest")

    state = agentsre_sdk.init(
        tenant_id="company_xyz",
        project_id="travel-ai",
        service_name="trip-planner",
        environment="production",
        backend_url="https://explicit.example.com/api/v1/ingest",
        api_key="test-key",
    )

    assert state.config.backend_url == "https://explicit.example.com/api/v1/ingest"
    agentsre_sdk.shutdown()


def test_load_env_file_falls_back_to_sdk_env(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / "sdk" / ".env"
    env_file.parent.mkdir()
    env_file.write_text(
        "\n".join(
            [
                "AGENTSRE_TENANT_ID=file_company",
                "AGENTSRE_PROJECT_ID=file_project",
                "AGENTSRE_SERVICE_NAME=file_service",
                "AGENTSRE_ENVIRONMENT=file_env",
                "AGENTSRE_BACKEND_URL=https://file.example.com/api/v1/ingest",
                "AGENTSRE_API_KEY=file-key",
            ]
        ),
        encoding="utf-8",
    )
    cwd = tmp_path / "run-from-here"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(agentsre_sdk, "__file__", str(tmp_path / "sdk" / "agentsre_sdk" / "__init__.py"))
    for name in [
        "AGENTSRE_TENANT_ID",
        "AGENTSRE_PROJECT_ID",
        "AGENTSRE_SERVICE_NAME",
        "AGENTSRE_ENVIRONMENT",
        "AGENTSRE_BACKEND_URL",
        "AGENTSRE_API_KEY",
    ]:
        monkeypatch.delenv(name, raising=False)

    agentsre_sdk._load_env_file()

    assert agentsre_sdk.os.getenv("AGENTSRE_TENANT_ID") == "file_company"
    assert agentsre_sdk.os.getenv("AGENTSRE_BACKEND_URL") == "https://file.example.com/api/v1/ingest"
    assert agentsre_sdk.os.getenv("AGENTSRE_API_KEY") == "file-key"


def test_load_env_file_does_not_read_env_example(monkeypatch, tmp_path) -> None:
    sdk_dir = tmp_path / "sdk"
    sdk_dir.mkdir()
    (sdk_dir / ".env.example").write_text("AGENTSRE_API_KEY=example-key\n", encoding="utf-8")
    cwd = tmp_path / "run-from-here"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(agentsre_sdk, "__file__", str(sdk_dir / "agentsre_sdk" / "__init__.py"))
    monkeypatch.delenv("AGENTSRE_API_KEY", raising=False)

    agentsre_sdk._load_env_file()

    assert agentsre_sdk.os.getenv("AGENTSRE_API_KEY") is None
