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
        # Connect community database manager
        from app.core.database import db_manager as community_db_manager
        community_db_manager.connect()
        # Setup event framework handlers
        from app.core.dependencies import setup_event_handlers
        await setup_event_handlers(community_db_manager.db)
        
        # Configure structured logging formatting
        root_logger = logging.getLogger()
        log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        root_logger.setLevel(log_level)
        for h in root_logger.handlers:
            h.setFormatter(StructuredLogFormatter())
            
        # Start background job runner
        job_runner.start()

        # Trigger one-off birthday post generation on startup to catch up
        from app.community.repositories.post import PostRepository
        from app.community.services.birthday import BirthdayPostService
        import asyncio
        post_repo = PostRepository(community_db_manager.db)
        birthday_service = BirthdayPostService(post_repo)
        asyncio.create_task(birthday_service.generate_birthday_posts())
        
        # Initialize Firebase Admin SDK
        from app.core.firebase import initialize_firebase
        initialize_firebase()
        # Ensure correct geospatial indexing
        await db_manager.ensure_indexes()
        logger.info("Application resources initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize application resources: {e}")
        raise e
    
    yield  # The application serves requests here

    # Shutdown sequence
    logger.info("Releasing application resources...")
    # Stop background job runner
    await job_runner.stop()
    db_manager.disconnect()
    from app.core.database import db_manager as community_db_manager
    community_db_manager.disconnect()
    logger.info("Application shut down clean.")

# Instantiate Platform singletons
from app.platform.cache import MemoryCacheProvider
from app.platform.idempotency import IdempotencyService, IdempotencyMiddleware
from app.platform.rate_limit import InMemRateLimiter, RateLimitMiddleware
from app.platform.background_jobs import JobQueue, BackgroundJobRunner
from app.platform.monitoring import MonitoringMiddleware, MetricsService, StructuredLogFormatter

cache_provider = MemoryCacheProvider()
idempotency_service = IdempotencyService(cache_provider)
rate_limiter = InMemRateLimiter(settings.RATE_LIMIT_REQUESTS, settings.RATE_LIMIT_WINDOW_SECS)
job_queue = JobQueue()
job_runner = BackgroundJobRunner(job_queue, max_workers=settings.BACKGROUND_JOBS_MAX_WORKERS)
metrics_service = MetricsService()

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

from app.core.exceptions import register_exception_handlers
register_exception_handlers(app)

# Enable Cross-Origin Resource Sharing (CORS) for local and production integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this to designated origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Platform Middlewares
app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)
app.add_middleware(IdempotencyMiddleware, idempotency_service=idempotency_service)
app.add_middleware(MonitoringMiddleware)

# Include profile API routers
app.include_router(profile.router)
app.include_router(admin.router)

# Include community API routers
from app.community.routers import community_router
app.include_router(community_router)

# Include notifications API router
from app.notifications.routers.notifications import router as notifications_router
app.include_router(notifications_router, prefix="/api/v1/notifications", tags=["Notifications"])

# Include health API router
from app.platform.health import health_router
app.include_router(health_router, tags=["Health Checks"])

@app.get("/", include_in_schema=False)
async def redirect_to_swagger():
    """
    Redirects application root requests directly to interactive Swagger API documentation.
    """
    return RedirectResponse(url="/docs")

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on {settings.HOST}:{settings.PORT}")
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
