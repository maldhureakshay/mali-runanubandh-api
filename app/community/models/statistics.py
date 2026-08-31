from pydantic import BaseModel, Field

class CommunityStatistics(BaseModel):
    """
    Model representing dynamic community statistics.
    """
    members: str = Field(default="0", description="Total members count")
    activeProfiles: str = Field(default="0", description="Total active profiles count")
    doctors: str = Field(default="0", description="Total doctors count")
    engineers: str = Field(default="0", description="Total engineers count")
    new: str = Field(default="0", description="Total new profiles count")
    verified: str = Field(default="0", description="Total verified profiles count")

class CommunityStatisticsDB(CommunityStatistics):
    """
    Database representation of community statistics.
    """
    id: str = Field(default="global_stats", alias="_id")
