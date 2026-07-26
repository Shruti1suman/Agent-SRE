from __future__ import annotations

import asyncio
import contextlib

from backend.app.services.metrics_service import MetricsService
from backend.core.settings import settings


class BackgroundMetricsWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if not settings.metrics_worker_enabled:
            print("[AgentSRE] Metrics background worker disabled.")
            return
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="agentsre-metrics-worker")
        print(
            "[AgentSRE] Metrics background worker started "
            f"(interval={settings.metrics_worker_interval_seconds}s, "
            f"batch={settings.metrics_worker_batch_size})."
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if not self._task:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        print("[AgentSRE] Metrics background worker stopped.")

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                result = await asyncio.to_thread(
                    MetricsService().process_pending,
                    settings.metrics_worker_batch_size,
                )
                for error in result.get("errors", []):
                    print(f"[AgentSRE] Metrics worker error: {error}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[AgentSRE] Metrics worker polling failed: {exc}")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=max(settings.metrics_worker_interval_seconds, 1),
                )
            except asyncio.TimeoutError:
                continue
