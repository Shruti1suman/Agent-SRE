from backend.core.settings import settings
from backend.database.postgresql import PostgresStore


class SchemaRepository:
    def __init__(self) -> None:
        self.metrics = PostgresStore(settings.metrics_database)
        self.ingestion = PostgresStore(settings.ingestion_database)

    def ensure_schema(self) -> None:
        if settings.metrics_database != settings.ingestion_database:
            raise RuntimeError(
                "POSTGRES_METRICS_DATABASE and POSTGRES_INGESTION_DATABASE must match; "
                "the metrics worker queries ingestion and evaluation tables together."
            )
        self.metrics.ensure_database()
        self.metrics.execute_script(
            [
                """CREATE TABLE IF NOT EXISTS dashboard_users (
                    user_id VARCHAR(64) PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE,
                    display_name VARCHAR(160) NOT NULL, password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
                """CREATE TABLE IF NOT EXISTS dashboard_sessions (
                    token_hash CHAR(64) PRIMARY KEY, user_id VARCHAR(64) NOT NULL,
                    expires_at TIMESTAMP NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_dashboard_sessions_user FOREIGN KEY (user_id) REFERENCES dashboard_users(user_id))""",
                """CREATE TABLE IF NOT EXISTS dashboard_projects (
                    project_id VARCHAR(80) PRIMARY KEY, owner_user_id VARCHAR(64) NOT NULL,
                    project_name VARCHAR(180) NOT NULL, description TEXT NULL,
                    tenant_id VARCHAR(80) NOT NULL, sdk_key_hash CHAR(64), sdk_key_preview VARCHAR(24),
                    sdk_key_name VARCHAR(120), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_dashboard_projects_user FOREIGN KEY (owner_user_id) REFERENCES dashboard_users(user_id))""",
                """CREATE TABLE IF NOT EXISTS projects (
                    project_id VARCHAR(64) PRIMARY KEY, project_name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
                """CREATE TABLE IF NOT EXISTS slo_configurations (
                    slo_id VARCHAR(80) PRIMARY KEY, project_id VARCHAR(80) NOT NULL,
                    metric_name VARCHAR(100) NOT NULL, slo_type VARCHAR(100) NOT NULL,
                    label VARCHAR(160) NOT NULL, operator VARCHAR(10) NOT NULL,
                    threshold_value DOUBLE PRECISION NOT NULL, unit VARCHAR(24),
                    severity VARCHAR(20) NOT NULL DEFAULT 'warning', is_active BOOLEAN DEFAULT TRUE,
                    configuration_kind VARCHAR(20) NOT NULL DEFAULT 'predefined', deleted_at TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_slo_project_type UNIQUE (project_id, slo_type))""",
                """CREATE TABLE IF NOT EXISTS trace_evaluations (
                    evaluation_id VARCHAR(64) PRIMARY KEY DEFAULT gen_random_uuid()::text,
                    trace_id VARCHAR(100) NOT NULL UNIQUE, agent_id VARCHAR(64), project_id VARCHAR(64),
                    trace_status VARCHAR(20), evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_duration_ms DOUBLE PRECISION, total_prompt_tokens INT, total_completion_tokens INT,
                    total_tokens INT, total_cost_usd DECIMAL(16, 8), cost_computation_skipped BOOLEAN DEFAULT FALSE,
                    llm_latency_ms DOUBLE PRECISION, total_tool_latency_ms DOUBLE PRECISION, step_count INT,
                    tool_call_count INT, tool_failure_count INT, tool_failure_rate DOUBLE PRECISION,
                    avg_step_latency_ms DOUBLE PRECISION, p95_step_latency_ms DOUBLE PRECISION,
                    avg_tool_latency_ms DOUBLE PRECISION, tokens_per_step DOUBLE PRECISION,
                    repetition_score DOUBLE PRECISION, grounded_response_rate DOUBLE PRECISION,
                    groundedness_judgements JSONB, agentic_metrics JSONB, baseline_eligible BOOLEAN DEFAULT FALSE,
                    loop_detected BOOLEAN DEFAULT FALSE, loop_reason TEXT, z_total_duration_ms DOUBLE PRECISION,
                    z_total_cost_usd DOUBLE PRECISION, z_step_count DOUBLE PRECISION,
                    z_tool_failure_rate DOUBLE PRECISION, z_repetition_score DOUBLE PRECISION,
                    z_grounded_response_rate DOUBLE PRECISION, z_tokens_per_step DOUBLE PRECISION,
                    z_avg_tool_latency_ms DOUBLE PRECISION, slo_breaches JSONB, slo_results JSONB,
                    slo_status VARCHAR(20) DEFAULT 'not_evaluated', incidents_created INT DEFAULT 0,
                    alerts_sent INT DEFAULT 0, model_name VARCHAR(150), pricing_matched_on VARCHAR(20))""",
                """CREATE TABLE IF NOT EXISTS incidents (
                    incident_id VARCHAR(64) PRIMARY KEY DEFAULT gen_random_uuid()::text,
                    trace_id VARCHAR(100) NOT NULL, agent_id VARCHAR(64), project_id VARCHAR(64),
                    rule_id VARCHAR(20) NOT NULL, category VARCHAR(50) NOT NULL, severity VARCHAR(20) NOT NULL,
                    rca_text TEXT, suggestion_text TEXT, metric_name VARCHAR(100), observed_value DOUBLE PRECISION,
                    z_score DOUBLE PRECISION, threshold_value DOUBLE PRECISION, triggered_by VARCHAR(20) DEFAULT 'slo',
                    slo_id VARCHAR(80), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_incident_trace_rule UNIQUE (trace_id, rule_id))""",
                """CREATE TABLE IF NOT EXISTS agent_baseline_stats (
                    agent_id VARCHAR(128) NOT NULL, metric_name VARCHAR(100) NOT NULL,
                    mean DOUBLE PRECISION NOT NULL DEFAULT 0, m2 DOUBLE PRECISION NOT NULL DEFAULT 0,
                    stddev DOUBLE PRECISION NOT NULL DEFAULT 0, sample_count INT NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (agent_id, metric_name))""",
                """CREATE TABLE IF NOT EXISTS incident_chat_messages (
                    message_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    incident_id VARCHAR(64) NOT NULL, user_id VARCHAR(64) NOT NULL,
                    role VARCHAR(20) NOT NULL, content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_incident_chat_incident FOREIGN KEY (incident_id) REFERENCES incidents(incident_id) ON DELETE CASCADE)""",
                "CREATE INDEX IF NOT EXISTS idx_slo_project_active ON slo_configurations (project_id, is_active)",
                "CREATE INDEX IF NOT EXISTS idx_slo_project_metric ON slo_configurations (project_id, metric_name)",
                "CREATE INDEX IF NOT EXISTS idx_trace_evaluations_project ON trace_evaluations (project_id)",
                "CREATE INDEX IF NOT EXISTS idx_trace_evaluations_agent ON trace_evaluations (agent_id)",
                "CREATE INDEX IF NOT EXISTS idx_incidents_project ON incidents (project_id)",
                "CREATE INDEX IF NOT EXISTS idx_baseline_agent ON agent_baseline_stats (agent_id)",
                "CREATE INDEX IF NOT EXISTS idx_incident_chat_user_incident_message ON incident_chat_messages (user_id, incident_id, message_id)",
                "CREATE INDEX IF NOT EXISTS idx_incident_chat_incident ON incident_chat_messages (incident_id)",
            ]
        )
        self._ensure_metrics_column("dashboard_projects", "description", "TEXT NULL")
        self._ensure_metrics_column("dashboard_projects", "sdk_key_name", "VARCHAR(120)")
        self._ensure_metrics_column("trace_evaluations", "groundedness_judgements", "JSONB")
        self._ensure_metrics_column("trace_evaluations", "agentic_metrics", "JSONB")
        self._ensure_metrics_column("trace_evaluations", "baseline_eligible", "BOOLEAN DEFAULT FALSE")
        for column in (
            "z_total_duration_ms", "z_total_cost_usd", "z_step_count", "z_tool_failure_rate",
            "z_repetition_score", "z_grounded_response_rate", "z_tokens_per_step", "z_avg_tool_latency_ms",
        ):
            self._ensure_metrics_column("trace_evaluations", column, "DOUBLE PRECISION")
        self._ensure_metrics_column("slo_configurations", "configuration_kind", "VARCHAR(20) NOT NULL DEFAULT 'predefined'")
        self._ensure_metrics_column("slo_configurations", "deleted_at", "TIMESTAMP NULL")
        self._ensure_metrics_column("incidents", "slo_id", "VARCHAR(80)")
        self.ingestion.execute_script(
            [
                """CREATE TABLE IF NOT EXISTS executions (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    execution_id VARCHAR(128) NOT NULL, trace_id VARCHAR(128) NOT NULL,
                    project_id VARCHAR(128) NULL, service_name VARCHAR(255) NULL,
                    environment VARCHAR(64) NULL, status VARCHAR(64) NULL,
                    started_at VARCHAR(64) NULL, ended_at VARCHAR(64) NULL, duration_ms BIGINT NULL,
                    llm_call_count INTEGER NOT NULL DEFAULT 0,
                    tool_call_count INTEGER NOT NULL DEFAULT 0,
                    raw_payload JSONB NOT NULL, governance_payload JSONB NOT NULL,
                    intelligence_payload JSONB NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_execution_id UNIQUE (execution_id))""",
                """CREATE TABLE IF NOT EXISTS published_events (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    event_id VARCHAR(255) NOT NULL, execution_id VARCHAR(128) NOT NULL,
                    topic VARCHAR(255) NOT NULL, message_key VARCHAR(255) NOT NULL,
                    payload JSONB NOT NULL, published_at VARCHAR(64) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_event_topic UNIQUE (event_id, topic))""",
                "CREATE INDEX IF NOT EXISTS idx_executions_trace_id ON executions (trace_id)",
                "CREATE INDEX IF NOT EXISTS idx_executions_project_id ON executions (project_id)",
                "CREATE INDEX IF NOT EXISTS idx_published_execution_topic ON published_events (execution_id, topic)",
            ]
        )
        self.ensure_ingestion_column("executions", "llm_call_count", "INTEGER NOT NULL DEFAULT 0")
        self.ensure_ingestion_column("executions", "tool_call_count", "INTEGER NOT NULL DEFAULT 0")

    def _ensure_metrics_column(self, table_name: str, column_name: str, column_definition: str) -> None:
        self.metrics.execute(
            f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{column_name}" {column_definition}'
        )

    def ensure_ingestion_column(self, table_name: str, column_name: str, column_definition: str) -> None:
        self.ingestion.execute(
            f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{column_name}" {column_definition}'
        )
