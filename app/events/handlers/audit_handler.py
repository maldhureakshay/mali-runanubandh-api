"""
AuditHandler implementation.

Placeholder handler to demonstrate auditing security/action logs from domain events.
"""

import logging

from app.events.base_event import BaseEvent
from app.events.handler import EventHandler

logger = logging.getLogger(__name__)


class AuditHandler(EventHandler):
    """
    Subscribes to all events to process platform audit trail records.
    """

    async def handle(self, event: BaseEvent) -> None:
        """
        Processes event and writes security/auditing records.
        """
        logger.info(
            "AuditHandler: Event Received - Type: %s, ID: %s. TODO: Write to platform-wide audit log collection.",
            event.eventType,
            event.eventId
        )
