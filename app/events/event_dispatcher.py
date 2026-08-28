"""
EventDispatcher implementation.

Asynchronously dispatches events to handlers in background tasks safely.
"""

import asyncio
import logging
from typing import List

from app.events.base_event import BaseEvent
from app.events.handler import EventHandler

logger = logging.getLogger(__name__)


class EventDispatcher:
    """
    Schedules handlers to process events asynchronously as background tasks.
    Guarantees errors in one handler do not disrupt others or the publisher thread.
    """

    async def dispatch(self, event: BaseEvent, handlers: List[EventHandler]) -> None:
        """
        Dispatch the event to all registered handlers by spawning background tasks.
        """
        logger.info("Event Dispatched: eventId=%s to %d handlers", event.eventId, len(handlers))
        for handler in handlers:
            # Spawn background task so it executes concurrently without blocking
            asyncio.create_task(self._execute_handler_safely(handler, event))

    async def _execute_handler_safely(self, handler: EventHandler, event: BaseEvent) -> None:
        """
        Safely execute an individual handler, trapping any raised exceptions.
        """
        handler_name = handler.__class__.__name__
        logger.info("Handler Started: %s for event %s", handler_name, event.eventId)
        try:
            await handler.handle(event)
            logger.info("Handler Completed: %s for event %s", handler_name, event.eventId)
        except Exception as e:
            logger.error(
                "Handler Failed: %s for event %s. Exception: %s",
                handler_name,
                event.eventId,
                e,
                exc_info=True
            )
