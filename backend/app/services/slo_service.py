from __future__ import annotations

from operator import ge, gt, le, lt
from math import isfinite
from typing import Any

from backend.app.repositories.slo_repository import SloRepository
from backend.app.services.slo_catalog import metric_catalog, metric_definition


OPERATORS = {
    "gt": gt,
    "lt": lt,
    "gte": ge,
    "lte": le,
}


class SloService:
    def __init__(self) -> None:
        self.repository = SloRepository()

    def overview(self, project_id: str) -> dict[str, Any]:
        self.repository.ensure_defaults(project_id)
        configs = self.repository.list_configs(project_id)
        evaluations = self.repository.recent_evaluations(project_id)
        latest_by_slo = latest_results_by_slo(evaluations)

        rows = []
        for config in configs:
            latest = aggregate_result(config, evaluations) if config["metric_name"] == "execution_success_rate" else latest_by_slo.get(config["slo_id"])
            status = status_for_config(config, latest)
            rows.append({
                "slo_id": config["slo_id"],
                "project_id": config["project_id"],
                "metric": config["label"],
                "metric_name": config["metric_name"],
                "slo_type": config["slo_type"],
                "operator": config["operator"],
                "target": config["threshold_value"],
                "threshold_value": config["threshold_value"],
                "unit": display_unit(config),
                "raw_unit": config.get("unit"),
                "severity": config["severity"],
                "configuration_kind": config.get("configuration_kind") or "predefined",
                "enabled": bool(config["is_active"]),
                "status": status,
                "observed_value": latest.get("observed_value") if latest else None,
                "updated": config.get("updated_at"),
            })

        enabled = [row for row in rows if row["enabled"]]
        evaluated_runs = [row for row in evaluations if row.get("slo_status") in {"compliant", "breached"}]
        breached_runs = [row for row in evaluated_runs if row.get("slo_status") == "breached"]
        healthy_runs = [row for row in evaluated_runs if row.get("slo_status") == "compliant"]
        return {
            "summary": {
                "configured": len(rows),
                "enabled": len(enabled),
                "healthy_runs": len(healthy_runs),
                "breached_runs": len(breached_runs),
                "loop_count": len([row for row in evaluations if row.get("loop_detected")]),
                "success_count": len([row for row in evaluations if str(row.get("trace_status")).lower() in {"completed", "success"}]),
            },
            "slos": rows,
            "timeline": timeline_from_evaluations(evaluations, rows),
        }

    def update(self, project_id: str, slo_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.repository.ensure_defaults(project_id)
        current = self.repository.get_config(project_id, slo_id)
        if not current or "error" in current:
            return {"error": "SLO not found"}
        definition = metric_definition(current["metric_name"])
        operator = payload.get("operator")
        if operator and (not definition or operator not in definition["operators"]):
            return {"error": "Operator is not supported for this metric"}
        if "threshold_value" in payload and not valid_threshold(payload["threshold_value"]):
            return {"error": "Threshold must be a finite non-negative number"}
        updated = self.repository.update_config(project_id, slo_id, payload)
        if not updated:
            return {"error": "SLO not found"}
        return updated

    def create(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.repository.ensure_defaults(project_id)
        definition = metric_definition(payload["metric_name"])
        if not definition or definition.get("customizable") is False:
            return {"error": "Unsupported SLO metric"}
        predefined_metrics = {
            config["metric_name"]
            for config in self.repository.list_configs(project_id)
            if (config.get("configuration_kind") or "predefined") == "predefined"
        }
        if payload["metric_name"] in predefined_metrics:
            return {"error": "This metric is already configured as a predefined SLO"}
        if payload["operator"] not in definition["operators"]:
            return {"error": "Operator is not supported for this metric"}
        if not valid_threshold(payload["threshold_value"]):
            return {"error": "Threshold must be a finite non-negative number"}
        return self.repository.create_config(project_id, payload, definition)

    def delete(self, project_id: str, slo_id: str) -> dict[str, Any]:
        self.repository.ensure_defaults(project_id)
        if not self.repository.delete_custom_config(project_id, slo_id):
            return {"error": "Only custom SLOs can be removed"}
        return {"deleted": True, "slo_id": slo_id}

    @staticmethod
    def catalog() -> dict[str, Any]:
        return {"metrics": metric_catalog()}


def evaluate_slos_for_metrics(project_id: str, metrics: dict[str, Any]) -> dict[str, Any]:
    repository = SloRepository()
    repository.ensure_defaults(project_id)
    configs = repository.list_configs(project_id, active_only=True)
    results = []
    breaches = []

    for config in configs:
        if config["metric_name"] == "execution_success_rate":
            continue
        observed = metric_value(metrics, config["metric_name"])
        status = evaluate_status(config["operator"], observed, config["threshold_value"])
        result = {
            "slo_id": config["slo_id"],
            "slo_type": config["slo_type"],
            "metric_name": config["metric_name"],
            "label": config["label"],
            "operator": config["operator"],
            "threshold_value": config["threshold_value"],
            "observed_value": observed,
            "status": status,
            "severity": config["severity"],
            "unit": config.get("unit"),
        }
        results.append(result)
        if status == "breached" and observed is not None:
            breaches.append(result)

    return {
        "slo_results": results,
        "slo_breaches": breaches,
        "slo_status": "breached" if breaches else "compliant" if results else "not_configured",
    }


def metric_value(metrics: dict[str, Any], name: str) -> float | None:
    value = metrics.get(name)
    if value is None:
        value = (metrics.get("agentic_metrics") or {}).get(name)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def valid_threshold(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(number) and number >= 0


def evaluate_status(operator: str, observed: float | None, threshold: float) -> str:
    if observed is None:
        return "not_evaluated"
    comparison = OPERATORS.get(operator)
    if comparison is None:
        return "not_evaluated"
    return "breached" if comparison(float(observed), float(threshold)) else "compliant"


def latest_results_by_slo(evaluations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest = {}
    for evaluation in evaluations:
        for result in evaluation.get("slo_results") or []:
            slo_id = result.get("slo_id")
            if slo_id and slo_id not in latest:
                latest[slo_id] = result
    return latest


def aggregate_result(config: dict[str, Any], evaluations: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not evaluations:
        return None
    success_count = len([
        row for row in evaluations
        if str(row.get("trace_status") or "").lower() in {"completed", "success"}
    ])
    observed = success_count / len(evaluations)
    status = evaluate_status(config["operator"], observed, config["threshold_value"])
    return {
        "slo_id": config["slo_id"],
        "slo_type": config["slo_type"],
        "metric_name": config["metric_name"],
        "label": config["label"],
        "operator": config["operator"],
        "threshold_value": config["threshold_value"],
        "observed_value": observed,
        "status": status,
        "severity": config["severity"],
        "unit": config.get("unit"),
        "sample_size": len(evaluations),
        "success_count": success_count,
    }


def status_for_config(config: dict[str, Any], latest: dict[str, Any] | None) -> str:
    if not bool(config.get("is_active")):
        return "disabled"
    if not latest:
        return "not_evaluated"
    if latest.get("status") == "breached":
        return "breach"
    if latest.get("status") == "compliant":
        return "healthy"
    return "not_evaluated"


def timeline_from_evaluations(evaluations: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    success_rate_row = next((row for row in rows if row["metric_name"] == "execution_success_rate"), None)
    if success_rate_row and success_rate_row.get("observed_value") is not None:
        state = "breach" if success_rate_row["status"] == "breach" else "healthy"
        events.append({
            "time": str(evaluations[0].get("evaluated_at") if evaluations else ""),
            "metric": success_rate_row["metric"],
            "state": state,
            "type": "SLO breach" if state == "breach" else "SLO compliant",
            "observed": observed_text({
                "observed_value": success_rate_row["observed_value"],
                "threshold_value": success_rate_row["threshold_value"],
                "operator": success_rate_row["operator"],
                "unit": success_rate_row.get("raw_unit"),
            }),
            "evidence": f"{success_rate_row['observed_value'] * 100:.1f}% success across {len(evaluations)} evaluated traces",
        })

    for evaluation in evaluations:
        for result in evaluation.get("slo_results") or []:
            status = "breach" if result.get("status") == "breached" else "healthy"
            events.append({
                "time": str(evaluation.get("evaluated_at") or ""),
                "metric": result.get("label") or result.get("metric_name"),
                "state": status,
                "type": "SLO breach" if status == "breach" else "SLO compliant",
                "observed": observed_text(result),
                "evidence": f"Trace {short_trace_id(evaluation.get('trace_id'))} evaluated; execution status {evaluation.get('trace_status')}",
            })
            if len(events) >= 20:
                return events
    return events


def observed_text(result: dict[str, Any]) -> str:
    observed = result.get("observed_value")
    threshold = result.get("threshold_value")
    operator = result.get("operator")
    unit = result.get("unit") or ""
    comparator = {
        "gt": "at most",
        "gte": "below",
        "lt": "at least",
        "lte": "above",
    }.get(operator, operator)
    return f"Observed {format_value(observed, unit)}; target is {comparator} {format_value(threshold, unit)}"


def format_value(value: Any, unit: str) -> str:
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if unit == "ratio":
        return f"{number * 100:.1f}%"
    if unit == "USD":
        return f"${number:.4f}"
    if unit == "ms":
        return f"{number:.0f}ms"
    if number.is_integer():
        return f"{number:.0f} {unit}".strip()
    return f"{number:.2f} {unit}".strip()


def display_unit(config: dict[str, Any]) -> str:
    if config.get("unit") == "ratio":
        return "%"
    return config.get("unit") or ""


def short_trace_id(value: Any) -> str:
    text = str(value or "unknown")
    return text if len(text) <= 12 else f"{text[:8]}..."
