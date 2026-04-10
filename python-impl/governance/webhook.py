from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class WebhookEventType(str, Enum):
    TICKET_CREATED = "ticket.created"
    TICKET_UPDATED = "ticket.updated"
    TICKET_STATUS_CHANGED = "ticket.status.changed"
    TICKET_RESOLVED = "ticket.resolved"
    TICKET_REJECTED = "ticket.rejected"
    TICKET_CLOSED = "ticket.closed"
    REVIEW_REQUESTED = "review.requested"
    REVIEW_APPROVED = "review.approved"
    REVIEW_REJECTED = "review.rejected"


WEBHOOK_EVENT_LABELS: dict[WebhookEventType, str] = {
    WebhookEventType.TICKET_CREATED: "工单创建",
    WebhookEventType.TICKET_UPDATED: "工单更新",
    WebhookEventType.TICKET_STATUS_CHANGED: "工单状态变更",
    WebhookEventType.TICKET_RESOLVED: "工单已解决",
    WebhookEventType.TICKET_REJECTED: "工单已拒绝",
    WebhookEventType.TICKET_CLOSED: "工单已关闭",
    WebhookEventType.REVIEW_REQUESTED: "待审核",
    WebhookEventType.REVIEW_APPROVED: "审核通过",
    WebhookEventType.REVIEW_REJECTED: "审核拒绝",
}


@dataclass
class WebhookDelivery:
    delivery_id: str
    webhook_id: str
    event_type: str
    payload: dict[str, Any]
    status: str
    attempts: int
    last_attempt_at: str | None
    response_status: int | None
    response_body: str | None
    error: str | None
    created_at: str


@dataclass
class Webhook:
    webhook_id: str
    url: str
    events: list[str]
    secret: str
    description: str
    is_active: bool
    created_at: str
    delivery_stats: dict[str, int] = field(default_factory=dict)


class WebhookRegistry:
    def __init__(self):
        self._webhooks: dict[str, Webhook] = {}
        self._deliveries: dict[str, list[WebhookDelivery]] = {}
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue | None = None

    async def start(self):
        self._queue = asyncio.Queue()
        asyncio.create_task(self._delivery_worker())

    async def _delivery_worker(self):
        while True:
            try:
                delivery_task = await self._queue.get()
                await self._deliver(delivery_task)
                self._queue.task_done()
            except Exception as e:
                logger.error(f"Webhook delivery worker error: {e}")

    async def enqueue(self, webhook_id: str, event_type: str, payload: dict[str, Any]):
        if self._queue is None:
            await self.start()
        delivery = WebhookDelivery(
            delivery_id=str(uuid.uuid4()),
            webhook_id=webhook_id,
            event_type=event_type,
            payload=payload,
            status="pending",
            attempts=0,
            last_attempt_at=None,
            response_status=None,
            response_body=None,
            error=None,
            created_at=datetime.now().isoformat(),
        )
        if webhook_id not in self._deliveries:
            self._deliveries[webhook_id] = []
        self._deliveries[webhook_id].insert(0, delivery)
        await self._queue.put(delivery)

    async def register(
        self,
        url: str,
        events: list[str],
        secret: str = "",
        description: str = "",
    ) -> Webhook:
        webhook_id = str(uuid.uuid4())[:16]
        secret = secret or uuid.uuid4().hex[:32]
        webhook = Webhook(
            webhook_id=webhook_id,
            url=url,
            events=events,
            secret=secret,
            description=description,
            is_active=True,
            created_at=datetime.now().isoformat(),
            delivery_stats={"total": 0, "success": 0, "failed": 0},
        )
        async with self._lock:
            self._webhooks[webhook_id] = webhook
            self._deliveries[webhook_id] = []
        return webhook

    async def unregister(self, webhook_id: str) -> bool:
        async with self._lock:
            if webhook_id in self._webhooks:
                del self._webhooks[webhook_id]
                return True
            return False

    async def get(self, webhook_id: str) -> Webhook | None:
        return self._webhooks.get(webhook_id)

    async def list_all(self) -> list[Webhook]:
        return list(self._webhooks.values())

    async def deliveries(self, webhook_id: str, limit: int = 20) -> list[WebhookDelivery]:
        return self._deliveries.get(webhook_id, [])[:limit]

    async def test(self, webhook_id: str) -> WebhookDelivery:
        webhook = self._webhooks.get(webhook_id)
        if not webhook:
            raise ValueError(f"Webhook {webhook_id} not found")
        payload = {
            "event": "webhook.test",
            "message": "This is a test webhook delivery.",
            "webhook_id": webhook_id,
            "timestamp": datetime.now().isoformat(),
        }
        delivery = await self._deliver_sync(webhook, payload)
        return delivery

    def _sign_payload(self, payload: str, secret: str) -> str:
        return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    async def _deliver(self, delivery: WebhookDelivery):
        webhook = self._webhooks.get(delivery.webhook_id)
        if not webhook or not webhook.is_active:
            delivery.status = "skipped"
            return

        await self._deliver_sync(webhook, delivery.payload)
        delivery.last_attempt_at = datetime.now().isoformat()

    async def _deliver_sync(self, webhook: Webhook, payload: dict[str, Any]) -> WebhookDelivery:
        delivery = WebhookDelivery(
            delivery_id=str(uuid.uuid4()),
            webhook_id=webhook.webhook_id,
            event_type=payload.get("event", "unknown"),
            payload=payload,
            status="pending",
            attempts=0,
            last_attempt_at=None,
            response_status=None,
            response_body=None,
            error=None,
            created_at=datetime.now().isoformat(),
        )

        body = json.dumps(payload, ensure_ascii=False)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-ID": webhook.webhook_id,
            "X-Webhook-Event": payload.get("event", "unknown"),
            "X-Webhook-Timestamp": str(int(time.time())),
        }
        if webhook.secret:
            signature = self._sign_payload(body, webhook.secret)
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        for attempt in range(3):
            delivery.attempts = attempt + 1
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(webhook.url, content=body, headers=headers)
                    delivery.response_status = resp.status_code
                    delivery.response_body = resp.text[:500] if resp.text else ""
                    if 200 <= resp.status_code < 300:
                        delivery.status = "success"
                        webhook.delivery_stats["total"] += 1
                        webhook.delivery_stats["success"] += 1
                        return delivery
                    delivery.error = f"HTTP {resp.status_code}"
            except Exception as e:
                delivery.error = str(e)
                delivery.response_status = None

            if attempt < 2:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)

        delivery.status = "failed"
        webhook.delivery_stats["total"] += 1
        webhook.delivery_stats["failed"] += 1
        return delivery


_registry: WebhookRegistry | None = None


def get_webhook_registry() -> WebhookRegistry:
    global _registry
    if _registry is None:
        _registry = WebhookRegistry()
    return _registry


async def emit_webhook(event_type: str, payload: dict[str, Any]):
    registry = get_webhook_registry()
    for webhook in await registry.list_all():
        if webhook.is_active and event_type in webhook.events:
            await registry.enqueue(webhook.webhook_id, event_type, payload)
