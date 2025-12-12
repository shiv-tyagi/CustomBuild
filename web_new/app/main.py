"""
Main FastAPI application entry point.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import router as v1_router
from app.core.config import get_settings, setup_external_modules_path

# Setup external modules path
setup_external_modules_path()

# Import external modules
# pylint: disable=wrong-import-position
import ap_git  # noqa: E402
import metadata_manager  # noqa: E402
import build_manager  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup
    settings = get_settings()

    repo = ap_git.GitRepo.clone_if_needed(
        source=settings.ap_git_url,
        dest=settings.source_dir,
        recurse_submodules=True,
    )

    ap_src_metadata_fetcher = metadata_manager.APSourceMetadataFetcher(
        ap_repo=repo,
        caching_enabled=True,
        redis_host=settings.redis_host,
        redis_port=settings.redis_port,
    )

    versions_fetcher = metadata_manager.VersionsFetcher(
        remotes_json_path=settings.remotes_json_path,
        ap_repo=repo
    )
    versions_fetcher.start()
    versions_fetcher.reload_remotes_json()

    vehicles_manager = metadata_manager.VehiclesManager.get_singleton()

    build_mgr = build_manager.BuildManager(
        outdir=settings.outdir_parent,
        redis_host=settings.redis_host,
        redis_port=settings.redis_port
    )

    # Store instances in app state
    app.state.repo = repo
    app.state.ap_src_metadata_fetcher = ap_src_metadata_fetcher
    app.state.versions_fetcher = versions_fetcher
    app.state.vehicles_manager = vehicles_manager
    app.state.build_manager = build_mgr

    yield

    # Shutdown
    if hasattr(versions_fetcher, 'stop'):
        versions_fetcher.stop()


# Create FastAPI application
app = FastAPI(
    title="CustomBuild API",
    description="API for custom ArduPilot firmware builds",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Include API v1 router
app.include_router(v1_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "CustomBuild API",
        "version": "1.0.0",
        "docs": "/docs",
        "api": "/api/v1"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
