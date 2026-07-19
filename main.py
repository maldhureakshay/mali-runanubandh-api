from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from config import settings
from database import db_manager
from routes import profile, admin

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan handler that manages connection resources.
    Triggers MongoDB initialization and geospatial index creation before requests flow.
    """
    logger.info("Initializing application resources...")
    try:
        # Start database connection pool
        db_manager.connect()
        # Ensure correct geospatial indexing
        await db_manager.ensure_indexes()
        logger.info("Application resources initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize application resources: {e}")
        raise e
    
    yield  # The application serves requests here

    # Shutdown sequence
    logger.info("Releasing application resources...")
    db_manager.disconnect()
    logger.info("Application shut down clean.")

# Instantiate FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Asynchronous Python API using FastAPI and Motor (MongoDB async driver) "
        "to find nearby matrimony profiles sorted by proximity with robust pagination."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Enable Cross-Origin Resource Sharing (CORS) for local and production integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this to designated origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include profile API routers
app.include_router(profile.router)
app.include_router(admin.router)

@app.get("/", include_in_schema=False)
async def redirect_to_swagger():
    """
    Redirects application root requests directly to interactive Swagger API documentation.
    """
    return RedirectResponse(url="/docs")

@app.get("/health", include_in_schema=False)
async def health_check():
    """
    Health check endpoint for load balancers, monitoring, and deployment verification.
    Returns MongoDB connection status.
    """
    db_ok = await db_manager.check_health()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected"
    }

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on {settings.HOST}:{settings.PORT}")
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
