from __future__ import annotations

import json
from typing import Any

from backend.core.settings import settings

try:
    from kafka import KafkaProducer
except ImportError:  # pragma: no cover
    KafkaProducer = None


class EventPublisher:
    def __init__(self) -> None:
        self._producer: KafkaProducer | None = None

    def publish(self, governance: dict[str, Any], intelligence: dict[str, Any]) -> dict[str, Any]:
        execution = governance.get("execution") or {}
        execution_id = execution.get("execution_id") or "N/A"
        published_at = governance.get("published_at") or "N/A"

        return {
            "governance": self.publish_one(
                topic=settings.kafka_governance_topic,
                key=execution_id,
                payload=governance,
                event_id=governance.get("event_id") or execution_id,
                execution_id=execution_id,
                published_at=published_at,
            ),
            "intelligence": self.publish_one(
                topic=settings.kafka_intelligence_topic,
                key=execution_id,
                payload=intelligence,
                event_id=f"evt_intel_{execution_id}_{governance.get('event_id', '')}",
                execution_id=execution_id,
                published_at=published_at,
            ),
        }

    def publish_one(
        self,
        topic: str,
        key: str,
        payload: dict[str, Any],
        event_id: str,
        execution_id: str,
        published_at: str,
    ) -> dict[str, Any]:
        base = {
            "topic": topic,
            "key": key,
            "event_id": event_id,
            "execution_id": execution_id,
            "published_at": published_at,
        }
        if not settings.kafka_enabled:
            return {**base, "published": False, "reason": "KAFKA_ENABLED=false"}
        if KafkaProducer is None:
            return {**base, "published": False, "reason": "kafka-python is not installed"}

        try:
            producer = self._get_producer()
            metadata = producer.send(topic, key=key, value=payload).get(timeout=20)
            producer.flush(timeout=20)
            return {
                **base,
                "published": True,
                "partition": metadata.partition,
                "offset": metadata.offset,
            }
        except Exception as exc:
            return {**base, "published": False, "reason": str(exc)}

    def close(self) -> None:
        if self._producer is not None:
            self._producer.flush(timeout=10)
            self._producer.close(timeout=10)
            self._producer = None

    def _get_producer(self) -> KafkaProducer:
        if self._producer is None:
            self._producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
                key_serializer=lambda value: str(value).encode("utf-8"),
                value_serializer=lambda value: json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"),
                acks="all",
                retries=3,
            )
        return self._producer
