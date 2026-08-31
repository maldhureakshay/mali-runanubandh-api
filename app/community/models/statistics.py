from pydantic import BaseModel, Field

class CommunityStatistics(BaseModel):
    """
    Model representing dynamic community statistics.
    """
    members: int = Field(default=0, description="Total members count")
    activeProfiles: int = Field(default=0, description="Total active profiles count")
    doctors: int = Field(default=0, description="Total doctors count")
    engineers: int = Field(default=0, description="Total engineers count")
    new: int = Field(default=0, description="Total new profiles count")
    verified: int = Field(default=0, description="Total verified profiles count")

class CommunityStatisticsDB(CommunityStatistics):
    """
    Database representation of community statistics.
    """
    id: str = Field(default="global_stats", alias="_id")
