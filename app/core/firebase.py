"""
Firebase initialization module.

Configures and initializes the Firebase Admin SDK to verify authentication tokens
and communicate with Firebase services.
"""

import logging
import firebase_admin
from firebase_admin import credentials
from app.core.config import settings

logger = logging.getLogger(__name__)


def initialize_firebase() -> None:
    """
    Initialize the Firebase Admin app.
    
    Uses provided service account credentials if configured, otherwise falls back
    to default credentials. Logs warnings if initialization cannot be performed.
    """
    # Prevent re-initialization error if app is already initialized
    if firebase_admin._apps:
        logger.info("Firebase Admin app already initialized.")
        return

    logger.info("Initializing Firebase Admin SDK...")
    try:
        if settings.FIREBASE_CREDENTIALS_PATH:
            logger.info("Using Firebase credentials JSON from: %s", settings.FIREBASE_CREDENTIALS_PATH)
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
        else:
            logger.warning(
                "No FIREBASE_CREDENTIALS_PATH configured. "
                "Attempting to initialize Firebase Admin app using default credentials."
            )
            # This triggers ADC (Application Default Credentials)
            firebase_admin.initialize_app()
        logger.info("Firebase Admin SDK initialized successfully.")
    except Exception as e:
        logger.critical("Failed to initialize Firebase Admin SDK: %s", e)
        # In a real environment, we might want to raise this exception, but let's log it
        # to ensure local development without firebase configs is still runnable
        if settings.ENV == "production":
            raise e
