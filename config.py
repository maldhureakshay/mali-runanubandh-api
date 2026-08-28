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

    # Platform Infrastructure settings
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECS: int = 60
    CACHE_DEFAULT_TTL_SECS: int = 300
    BACKGROUND_JOBS_MAX_WORKERS: int = 5
    LOG_LEVEL: str = "INFO"
    METRICS_ENABLED: bool = True
    PERFORMANCE_THRESHOLD_MS: int = 500

    # Configure Pydantic Settings to load from .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiated settings singleton
settings = Settings()
