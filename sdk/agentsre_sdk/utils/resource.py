from __future__ import annotations

import os
import platform
import socket
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from agentsre_sdk.schema.models import Resource


SDK_VERSION = "1.0.0"
PLUGIN_VERSION = "1.0.0"


def collect_resource(framework: str | None = None, framework_version: str | None = None) -> Resource:
    return Resource(
        sdk_version=SDK_VERSION,
        plugin_version=PLUGIN_VERSION,
        framework=framework,
        framework_version=framework_version,
        language="Python",
        host_name=socket.gethostname(),
        process_id=os.getpid(),
        os=f"{platform.system()} {platform.release()}".strip(),
        cpu_architecture=platform.machine(),
        runtime="Python",
        runtime_version=platform.python_version(),
        container_id=_detect_container_id(),
        kubernetes_pod=os.getenv("HOSTNAME") if os.getenv("KUBERNETES_SERVICE_HOST") else None,
        cloud_provider=_detect_cloud_provider(),
    )


def detect_installed_version(package_name: str) -> str | None:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None


def _detect_container_id() -> str | None:
    cgroup_path = Path("/proc/self/cgroup")
    if not cgroup_path.exists():
        return os.getenv("HOSTNAME") if Path("/.dockerenv").exists() else None

    try:
        for line in cgroup_path.read_text(encoding="utf-8").splitlines():
            candidates = [part for part in line.replace("\\", "/").split("/") if part]
            for candidate in reversed(candidates):
                cleaned = candidate.removeprefix("docker-").removesuffix(".scope")
                if len(cleaned) >= 12 and all(char in "0123456789abcdef" for char in cleaned.lower()):
                    return f"docker://{cleaned[:12]}"
    except OSError:
        return None
    return None


def _detect_cloud_provider() -> str | None:
    if os.getenv("AWS_EXECUTION_ENV") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"):
        return "AWS"
    if os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or os.getenv("K_SERVICE"):
        return "GCP"
    if os.getenv("AZURE_FUNCTIONS_ENVIRONMENT") or os.getenv("WEBSITE_SITE_NAME"):
        return "Azure"
    if "microsoft" in platform.release().lower() and sys.platform.startswith("linux"):
        return "Azure"
    return None
