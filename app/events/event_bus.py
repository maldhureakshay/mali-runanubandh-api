"""
EventBus implementation.

Core bus registry to subscribe handlers to event types and publish events.
"""

import logging
from typing import Dict, List, Set

from app.events.base_event import BaseEvent
from app.events.event_types import EventType
from app.events.handler import EventHandler
from app.events.event_dispatcher import EventDispatcher

logger = logging.getLogger(__name__)


class EventBus:
    """
    Central event bus that manages handler subscriptions and routes published events
    to the EventDispatcher for execution.
    """

    def __init__(self, dispatcher: EventDispatcher) -> None:
        """
        Initialize the event bus with a dispatcher.
        """
        self._dispatcher = dispatcher
        self._handlers: Dict[EventType, Set[EventHandler]] = {}

    def register_handler(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Register a subscriber handler to receive events of a specific type.
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = set()
        self._handlers[event_type].add(handler)
        logger.info("Registered handler %s for event type: %s", handler.__class__.__name__, event_type)

    def unregister_handler(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Remove a subscriber handler registration.
        """
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.info("Unregistered handler %s from event type: %s", handler.__class__.__name__, event_type)

    async def publish(self, event: BaseEvent) -> None:
        """
        Publish an event to the bus. Resolves registered handlers and passes them
        to the dispatcher for async processing.
        """
        event_type = event.eventType
        logger.info("Event Published: eventId=%s, eventType=%s", event.eventId, event_type)

        handlers = self._handlers.get(event_type, set())
        if not handlers:
            logger.debug("No handlers registered for event type: %s", event_type)
            return

        # Hand over execution to dispatcher
        await self._dispatcher.dispatch(event, list(handlers))
