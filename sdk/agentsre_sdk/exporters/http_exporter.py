from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Any

import httpx
from opentelemetry import context as otel_context

from agentsre_sdk.config import SDKConfig
from agentsre_sdk.schema.models import AgentSREPayload


logger = logging.getLogger(__name__)


class AgentSREHTTPExporter:
    def __init__(self, config: SDKConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=10.0)
        self._owns_client = client is None
        self._queue: asyncio.Queue[AgentSREPayload] | None = None
        self._worker: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }

    def export(self, payloads: AgentSREPayload | Iterable[AgentSREPayload]) -> bool:
        if self._closed:
            return False
        if isinstance(payloads, AgentSREPayload):
            payload_list = [payloads]
        else:
            payload_list = list(payloads)
        return all(self._post_with_retries(payload) for payload in payload_list)

    async def export_async(self, payload: AgentSREPayload) -> None:
        if self._closed:
            return
        queue = self._ensure_queue()
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            await asyncio.to_thread(self.export, payload)

    async def flush_async(self) -> None:
        queue = self._queue
        if queue is not None:
            await queue.join()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._worker is not None:
            self._worker.cancel()
        if self._owns_client:
            self._client.close()

    def _post_with_retries(self, payload: AgentSREPayload) -> bool:
        if self._closed:
            return False
        body = payload.model_dump(mode="json")
        for attempt in range(3):
            try:
                suppress_context = otel_context.set_value(otel_context._SUPPRESS_INSTRUMENTATION_KEY, True)
                suppress_context = otel_context.set_value(
                    otel_context._SUPPRESS_HTTP_INSTRUMENTATION_KEY,
                    True,
                    suppress_context,
                )
                token = otel_context.attach(suppress_context)
                try:
                    response = self._client.post(self.config.backend_url, headers=self.headers, json=body)
                finally:
                    otel_context.detach(token)
                response.raise_for_status()
                return True
            except httpx.HTTPError as exc:
                if attempt == 2:
                    logger.warning("AgentSRE export failed after retries: %s", exc)
                    return False
                time.sleep(0.2 * (2**attempt))
        return False

    def _ensure_queue(self) -> asyncio.Queue[AgentSREPayload]:
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self.config.max_queue_size)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._drain_queue())
        return self._queue

    async def _drain_queue(self) -> None:
        queue = self._queue
        if queue is None:
            return
        while not self._closed:
            payload = await queue.get()
            try:
                await asyncio.to_thread(self.export, payload)
            finally:
                queue.task_done()


def serialize_payload(payload: AgentSREPayload) -> dict[str, Any]:
    return payload.model_dump(mode="json")
