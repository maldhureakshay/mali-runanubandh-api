"""
Logging configuration module.

Sets up system-wide structured logging using Python's standard logging library.
Adjusts output level and format based on application configuration settings.
"""

import logging
import sys
from app.core.config import settings


def setup_logging() -> None:
    """
    Configure global Python logging settings.
    
    Standardizes log format, level, and directs output to stdout.
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    # Define a clean, structured log format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Reduce noise from third-party libraries if necessary
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("Logging configured successfully at level: %s", settings.LOG_LEVEL)
