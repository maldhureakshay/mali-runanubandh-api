"""
EventHandler base interface.

Defines the structure that all handlers must implement.
"""

from abc import ABC, abstractmethod

from app.events.base_event import BaseEvent


class EventHandler(ABC):
    """
    Abstract interface defining how a handler processes domain events.
    """

    @abstractmethod
    async def handle(self, event: BaseEvent) -> None:
        """
        Process the given domain event asynchronously.

        Args:
            event: The domain event instance to process.
        """
        pass
