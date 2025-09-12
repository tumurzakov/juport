"""Main application entry point."""
import logging
import asyncio
from contextlib import asynccontextmanager
from litestar import Litestar
from litestar.config.cors import CORSConfig
from litestar.static_files import StaticFilesConfig
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from sqlalchemy.exc import OperationalError
from app.config import settings
from app.database import engine, get_db_session
from app.models import Base
from app.routes.reports import ReportsController
from app.routes.notebooks import NotebooksController
from app.routes.web import WebController
from app.routes.files import FilesController
from app.routes.schedules import SchedulesController
from app.routes.tasks import TasksController
from app.routes.auth import AuthController
from app.middleware.auth import AuthMiddleware
from litestar.middleware.base import DefineMiddleware
from app.scheduler import scheduler
from app.worker import task_worker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def wait_for_database(max_retries: int = 30, delay: float = 2.0):
    """Wait for database to be ready with retry logic."""
    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database connection successful")
            return
        except OperationalError as e:
            logger.warning(f"Database connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
            else:
                logger.error("Failed to connect to database after all retries")
                raise


@asynccontextmanager
async def lifespan(app: Litestar):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Juport application...")
    
    # Wait for database to be ready and create tables
    await wait_for_database()
    
    # Start scheduler
    await scheduler.start()
    
    # Start task worker
    await task_worker.start()
    
    logger.info("Application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Juport application...")
    await scheduler.stop()
    await task_worker.stop()
    await engine.dispose()
    logger.info("Application shutdown complete")


# CORS configuration
cors_config = CORSConfig(
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files configuration
static_files_config = StaticFilesConfig(
    directories=["static"],
    path="/static",
)

# Template configuration
template_config = TemplateConfig(
    directory="templates",
    engine=JinjaTemplateEngine,
)

# Create application
app = Litestar(
    route_handlers=[
        AuthController,
        WebController,
        ReportsController,
        NotebooksController,
        FilesController,
        SchedulesController,
        TasksController,
    ],
    dependencies={"db_session": get_db_session},
    cors_config=cors_config,
    static_files_config=[static_files_config],
    template_config=template_config,
    lifespan=[lifespan],
    middleware=[DefineMiddleware(AuthMiddleware)],
    debug=settings.debug,
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )
