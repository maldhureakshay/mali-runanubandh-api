"""
BaseEvent definition.

Base Pydantic model for all platform domain events.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field

from app.events.event_types import EventType


class BaseEvent(BaseModel):
    """
    Every domain event emitted on the platform inherits from BaseEvent.
    """
    eventId: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique ID for this event instance")
    eventType: EventType = Field(..., description="Categorical type of the event")
    occurredAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of the event occurrence")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event-specific payload values")
    correlationId: Optional[str] = Field(None, description="Optional tracing identifier across async operations")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Extra contextual headers/options")

    model_config = {
        "use_enum_values": True,
        "populate_by_name": True
    }
