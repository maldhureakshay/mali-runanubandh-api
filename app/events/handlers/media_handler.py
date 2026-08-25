"""
MediaHandler implementation.

Placeholder handler to process image/video assets in the background.
"""

import logging

from app.events.base_event import BaseEvent
from app.events.handler import EventHandler

logger = logging.getLogger(__name__)


class MediaHandler(EventHandler):
    """
    Subscribes to events to trigger thumbnail generation, metadata extraction, or compression.
    """

    async def handle(self, event: BaseEvent) -> None:
        """
        Trigger media workflows.
        """
        logger.info(
            "MediaHandler: Event Received - Type: %s, ID: %s. TODO: Trigger image compression or thumbnail creation.",
            event.eventType,
            event.eventId
        )
