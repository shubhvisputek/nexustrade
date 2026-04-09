"""Tests for event bus (requires Redis running on localhost:6379)."""

import asyncio
import pytest
from datetime import datetime, timezone

from nexustrade.core.events import AsyncEventBus
from nexustrade.core.models import Event


def redis_available() -> bool:
    """Check if Redis is available."""
    import redis
    try:
        r = redis.Redis()
        r.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not redis_available(),
    reason="Redis not available on localhost:6379",
)


@pytest.fixture
async def event_bus():
    bus = AsyncEventBus("redis://localhost:6379")
    await bus.connect()
    yield bus
    await bus.disconnect()


@pytest.fixture
def sample_event():
    return Event(
        event_type="test.event",
        timestamp=datetime.now(timezone.utc),
        payload={"symbol": "AAPL", "price": 185.50},
        source_service="test-service",
        correlation_id="test-123",
    )


class TestAsyncEventBus:
    async def test_publish_event(self, event_bus, sample_event):
        event_id = await event_bus.publish("test.stream", sample_event)
        assert event_id is not None
        assert isinstance(event_id, str)

    async def test_publish_and_subscribe(self, event_bus, sample_event):
        received_events: list[Event] = []

        async def handler(event: Event) -> None:
            received_events.append(event)

        await event_bus.subscribe("test.pubsub", "test-group", handler)
        await event_bus.publish("test.pubsub", sample_event)

        # Wait for consumer to process
        await asyncio.sleep(2)

        assert len(received_events) == 1
        assert received_events[0].event_type == "test.event"
        assert received_events[0].payload["symbol"] == "AAPL"

    async def test_publish_multiple_events_order(self, event_bus):
        received: list[int] = []

        async def handler(event: Event) -> None:
            received.append(event.payload["seq"])

        await event_bus.subscribe("test.order", "test-order-group", handler)

        for i in range(10):
            event = event_bus.create_event(
                "test.sequence", {"seq": i}, "test-service",
            )
            await event_bus.publish("test.order", event)

        await asyncio.sleep(3)

        assert received == list(range(10))

    async def test_event_serialization_roundtrip(self, event_bus):
        received_events: list[Event] = []

        async def handler(event: Event) -> None:
            received_events.append(event)

        await event_bus.subscribe("test.serial", "test-serial-group", handler)

        original = event_bus.create_event(
            "agent.signal",
            {"direction": "buy", "confidence": 0.85, "nested": {"key": "val"}},
            "agent-engine",
        )
        await event_bus.publish("test.serial", original)

        await asyncio.sleep(2)

        assert len(received_events) == 1
        restored = received_events[0]
        assert restored.payload["direction"] == "buy"
        assert restored.payload["confidence"] == 0.85
        assert restored.payload["nested"]["key"] == "val"

    async def test_create_event_helper(self, event_bus):
        event = event_bus.create_event(
            "market.data", {"symbol": "AAPL"}, "data-service",
        )
        assert event.event_type == "market.data"
        assert event.source_service == "data-service"
        assert event.correlation_id  # auto-generated
        assert event.timestamp.tzinfo == timezone.utc
