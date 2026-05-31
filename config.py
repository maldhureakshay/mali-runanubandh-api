import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables and/or .env files.
    Pydantic handles automatic type validation and casting (e.g. string to int or bool).
    """
    APP_NAME: str = "Matrimony Geo-Search API"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # MongoDB settings
    MONGO_URI: str = "mongodb://localhost:27017/matrimony"
    MONGO_DB_NAME: str = "matrimony"
    MONGO_COLLECTION_NAME: str = "profiles"
    
    # Production MongoDB settings (Source for DB Pull script)
    PROD_MONGO_URI: Optional[str] = None

    # Configure Pydantic Settings to load from .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiated settings singleton
settings = Settings()
