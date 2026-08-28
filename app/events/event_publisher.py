"""
EventPublisher implementation.

Acts as the entrypoint for services to publish domain events without exposing the EventBus directly.
"""

import logging
from typing import Any, Dict, Optional

from app.events.base_event import BaseEvent
from app.events.event_types import EventType
from app.events.event_bus import EventBus

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Publisher class injected into business services. Exposes publish interface.
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Initialize the publisher with the central event bus.
        """
        self._event_bus = event_bus

    async def publish(
        self,
        event_type: EventType,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> BaseEvent:
        """
        Construct and publish a domain event to the event bus.
        """
        event = BaseEvent(
            eventType=event_type,
            payload=payload,
            correlationId=correlation_id,
            metadata=metadata or {}
        )
        logger.info("Publishing event: eventType=%s, eventId=%s", event_type, event.eventId)
        await self._event_bus.publish(event)
        return event
