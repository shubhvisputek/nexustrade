"""Event bus implementation using Redis Streams.

Provides async publish/subscribe with consumer groups for
multi-service event consumption without duplicate processing.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import redis.asyncio as aioredis

from nexustrade.core.models import Event

logger = logging.getLogger(__name__)

EventCallback = Callable[[Event], Awaitable[None]]


class AsyncEventBus:
    """Redis Streams-backed asynchronous event bus.

    Supports:
    - Publishing events to named streams
    - Subscribing with consumer groups (prevents duplicate processing)
    - Event acknowledgment after successful processing
    - Automatic JSON serialization/deserialization
    """

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None
        self._subscriptions: dict[str, list[tuple[str, EventCallback]]] = {}
        self._running = False
        self._tasks: list[asyncio.Task[None]] = []

    async def connect(self) -> None:
        """Connect to Redis."""
        self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        await self._redis.ping()
        logger.info("Event bus connected to %s", self._redis_url)

    async def disconnect(self) -> None:
        """Disconnect from Redis and stop all subscription tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def publish(self, stream: str, event: Event) -> str:
        """Publish an event to a Redis Stream.

        Returns the event ID assigned by Redis.
        """
        assert self._redis is not None, "Not connected"
        data = {"data": event.to_json()}
        event_id: str = await self._redis.xadd(stream, data)  # type: ignore[assignment]
        logger.debug("Published event %s to %s", event_id, stream)
        return event_id

    async def subscribe(
        self,
        stream: str,
        group: str,
        callback: EventCallback,
        consumer: str | None = None,
    ) -> None:
        """Subscribe to a stream using a consumer group.

        Creates the consumer group if it doesn't exist.
        The callback is invoked for each new event.
        """
        assert self._redis is not None, "Not connected"
        consumer = consumer or f"consumer-{uuid4().hex[:8]}"

        # Create consumer group (ignore if exists)
        try:
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        if stream not in self._subscriptions:
            self._subscriptions[stream] = []
        self._subscriptions[stream].append((group, callback))

        # Start consumer task
        self._running = True
        task = asyncio.create_task(
            self._consume(stream, group, consumer, callback)
        )
        self._tasks.append(task)

    async def acknowledge(self, stream: str, group: str, event_id: str) -> None:
        """Acknowledge an event as processed."""
        assert self._redis is not None, "Not connected"
        await self._redis.xack(stream, group, event_id)

    async def _consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        callback: EventCallback,
    ) -> None:
        """Internal consumer loop reading from a stream group."""
        assert self._redis is not None
        while self._running:
            try:
                results = await self._redis.xreadgroup(
                    group, consumer, {stream: ">"}, count=10, block=1000,
                )
                if not results:
                    continue

                for _stream_name, messages in results:
                    for msg_id, msg_data in messages:
                        try:
                            event = Event.from_json(msg_data["data"])
                            await callback(event)
                            await self.acknowledge(stream, group, msg_id)
                        except Exception:
                            logger.exception(
                                "Error processing event %s from %s", msg_id, stream
                            )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Consumer error on %s/%s", stream, group)
                await asyncio.sleep(1)

    def create_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        source_service: str,
        correlation_id: str | None = None,
    ) -> Event:
        """Helper to create a new Event with defaults."""
        return Event(
            event_type=event_type,
            timestamp=datetime.now(UTC),
            payload=payload,
            source_service=source_service,
            correlation_id=correlation_id or uuid4().hex,
        )
