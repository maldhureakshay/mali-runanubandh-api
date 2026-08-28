"""
Configuration module for the Mali Runanubandh Community Service.

This module defines the Settings class which loads and validates configuration parameters
from environment variables and `.env` files using Pydantic Settings v2.
"""

from typing import List, Optional
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """
    Application settings and environment configuration.
    
    Provides validation and default values for all configurations.
    """
    # Application Config
    PROJECT_NAME: str = Field("Mali Runanubandh Community Service", description="The name of the service")
    ENV: str = Field("development", description="Current running environment (development, staging, production)")
    DEBUG: bool = Field(True, description="Enable or disable debug mode")
    HOST: str = Field("0.0.0.0", description="IP address to bind the server to")
    PORT: int = Field(8000, description="Port to run the application on")
    
    # MongoDB Config
    MONGO_URI: str = Field("mongodb://localhost:27017", description="MongoDB connection URI")
    MONGO_DB_NAME: str = Field("mali_runanubandh_community", description="MongoDB database name")
    
    # Firebase Configuration
    # If not provided, it falls back to default Firebase credentials setup or mock during local dev
    FIREBASE_CREDENTIALS_PATH: Optional[str] = Field(None, description="Path to Firebase service account JSON key file")
    
    # Security & CORS
    CORS_ORIGINS: List[str] = Field(["*"], description="Allowed CORS origins")
    
    # Logging Config
    LOG_LEVEL: str = Field("INFO", description="Global application logging level")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instantiate settings singleton
settings = Settings()
