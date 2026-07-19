from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

class UserBase(BaseModel):
    """
    Pydantic model for User documents from the users collection.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow"
    )

    id: str = Field(alias="_id")
    profile_ids: Optional[List[str]] = None
    payment_status: Optional[str] = None
    subscription_status: Optional[str] = None
    subscription_source: Optional[str] = None
    is_legacy: Optional[bool] = None
    status: Optional[bool] = None
    subscription_product_id: Optional[str] = None
    subscription_updated_at: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    signin_via: Optional[str] = None
    createdAt: Optional[datetime] = None
    lastUpdated: Optional[datetime] = None
    phoneNumber: Optional[str] = None
    updated_at: Optional[datetime] = None
    displayName: Optional[str] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    inactive_profile_view_count: Optional[int] = None
    fcmToken: Optional[str] = None
    fcmTokenUpdatedAt: Optional[datetime] = None
    cast: Optional[str] = None
    branch: Optional[str] = None
    is_verified: Optional[bool] = None
    purchase_id: Optional[str] = None
    payment_date: Optional[datetime] = None
    is_discounted: Optional[bool] = None
    activatedAt: Optional[datetime] = None
