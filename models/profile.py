import math
from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict
from typing_extensions import Annotated

# Helper to robustly cast MongoDB ObjectId (or raw string IDs) into strings
PyObjectId = Annotated[str, BeforeValidator(str)]

# Custom validator to cleanly coerce BSON Double NaN values to None, protecting against missing numeric values
def clean_nan_float(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, str) and v.lower() in ["nan", "null", "none"]:
        return None
    return v

NullableFloat = Annotated[Optional[float], BeforeValidator(clean_nan_float)]
NullableIncome = Annotated[Optional[Union[int, float, str]], BeforeValidator(clean_nan_float)]

class Geoloc(BaseModel):
    """
    Geospatial coordinates representing Latitude and Longitude.
    """
    lat: float
    lng: float

class ProfileBase(BaseModel):
    """
    Base Pydantic model for Matrimony Profile document mapping.
    Includes all fields from the sample document with default values
    to gracefully handle sparse data in MongoDB.
    """
    id: PyObjectId = Field(alias="_id")
    type: Optional[str] = None
    payment_status: Optional[str] = None
    original_id: Optional[str] = None
    mothers_phone: List[str] = Field(default_factory=list)
    mothers_occupation: Optional[str] = None
    mother_name: Optional[str] = None
    middle_name: Optional[str] = None
    maternal_uncle_phone: List[str] = Field(default_factory=list)
    maternal_uncle_name: Optional[str] = None
    maternal_uncle_address: Optional[str] = None
    last_name: Optional[str] = None
    job: Optional[str] = None
    fathers_occupation: Optional[str] = None
    fathers_name: Optional[str] = None
    created: Optional[datetime] = None
    complexion: Optional[str] = None
    branch: Optional[str] = None
    blood_group: Optional[str] = None
    client_id: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    expiration_date: Optional[datetime] = None
    activatedAt: Optional[datetime] = None
    activation_expires_at: Optional[datetime] = None
    height_feet: Optional[int] = None
    siblings: Optional[str] = None
    phone: Optional[str] = None
    birth_date: Optional[Union[str, datetime]] = None  # Resilient to string or ISO datetime formats
    job_location: Optional[str] = None
    relation: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    is_contact_private: Optional[bool] = True
    active: Optional[bool] = True
    height_cm: Optional[int] = None
    height_inches: Optional[int] = None
    height: Optional[str] = None
    biodata_image_url: Optional[str] = None
    biodata_file_url: Optional[str] = None
    is_from_book: Optional[bool] = False
    proper_place: Optional[str] = None
    verification_submitted_at: Optional[datetime] = None
    verification_doc_url: Optional[str] = None
    verification_doc_type: Optional[str] = None
    verification_reviewed_at: Optional[datetime] = None
    verification_status: Optional[str] = None
    is_verified: Optional[bool] = False
    fathers_address_latitude: NullableFloat = None
    fathers_address_longitude: NullableFloat = None
    education: Optional[str] = None
    fathers_phone: List[str] = Field(default_factory=list)
    
    # Internal index fields
    geohash: Optional[str] = Field(alias="_geohash", default=None)
    geoloc: Optional[Geoloc] = Field(alias="_geoloc", default=None)
    
    fathers_address: Optional[str] = None
    last_seen: Optional[datetime] = None
    is_online: Optional[bool] = False
    gender: Optional[str] = None
    creator_id: Optional[str] = None
    featured_at: Optional[datetime] = None
    listing_rand: NullableFloat = None
    tags: List[str] = Field(default_factory=list)
    annual_income_in_words: Optional[str] = None
    annual_income: NullableIncome = None
    featured_removed_at: Optional[datetime] = None
    featured_until: Optional[datetime] = None
    is_featured: Optional[bool] = False
    expectation: Optional[str] = None
    modified: Optional[datetime] = None

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: lambda dt: dt.isoformat()}
    )

class ProfileWithDistance(ProfileBase):
    """
    Extends ProfileBase by appending the dynamically calculated
    distance metrics returned by MongoDB's geospatial operations.
    """
    distance_km: float = Field(..., description="Distance in kilometers from target point")
    distance_meters: float = Field(..., description="Distance in meters from target point")
