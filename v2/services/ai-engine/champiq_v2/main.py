"""ChampIQ V2 AI Engine - FastAPI Application Entry Point.

Stateless AI/ML worker service. The Gateway owns the pipeline state
machine; this service exposes endpoints for research, pitch, email,
call, and scoring operations.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from champiq_v2.api.middleware.rate_limit import RateLimitMiddleware
from champiq_v2.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("Starting ChampIQ V2 AI Engine...")

    # Connect to Neo4j
    try:
        from champiq_v2.graph.service import get_graph_service
        graph = await get_graph_service()
        await graph.setup_schema()
        logger.info("Graph schema initialized")
    except Exception as e:
        logger.warning("Could not connect to Neo4j: %s", e)

    # Initialize Graphiti semantic layer
    try:
        from champiq_v2.graph.graphiti_service import get_graphiti_service
        graphiti = await get_graphiti_service()
        await graphiti.initialize()
        logger.info("Graphiti semantic layer initialized")
    except Exception as e:
        logger.warning("Could not initialize Graphiti: %s", e)

    yield

    # Shutdown
    logger.info("Shutting down ChampIQ V2 AI Engine...")
    try:
        from champiq_v2.graph.graphiti_service import get_graphiti_service
        graphiti = await get_graphiti_service()
        await graphiti.close()
    except Exception:
        pass
    try:
        from champiq_v2.graph.service import get_graph_service
        graph = await get_graph_service()
        await graph.disconnect()
    except Exception:
        pass
    try:
        from champiq_v2.workers.base import activity_stream
        await activity_stream.close()
    except Exception:
        pass
    try:
        from champiq_v2.llm.service import get_llm_service
        llm = get_llm_service()
        if hasattr(llm, '_client') and llm._client is not None:
            await llm._client.close()
        if hasattr(llm, '_fallback_client') and llm._fallback_client is not None:
            await llm._fallback_client.close()
    except Exception:
        pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="ChampIQ V2 AI Engine - Fixed Pipeline Lead Qualification",
        lifespan=lifespan,
    )

    # CORS — never wildcard; in dev allow frontend dev server + gateway
    frontend_url = "http://localhost:3001"
    allowed_origins = (
        [frontend_url, settings.gateway_url]
        if settings.environment == "development"
        else [settings.gateway_url]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting middleware (applied before auth, so 429 before 401 on burst)
    app.add_middleware(RateLimitMiddleware)

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "type": type(exc).__name__},
        )

    # Root health check
    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "healthy",
            "service": settings.app_name,
            "version": settings.app_version,
        }

    # Include V2 API routes
    from champiq_v2.api.routes import health as health_routes
    from champiq_v2.api.routes import prospects, research, pitch, email, call, pipeline, settings as settings_routes

    app.include_router(health_routes.router, prefix="/api")
    app.include_router(prospects.router, prefix="/api")
    app.include_router(research.router, prefix="/api")
    app.include_router(pitch.router, prefix="/api")
    app.include_router(email.router, prefix="/api")
    app.include_router(call.router, prefix="/api")
    app.include_router(pipeline.router, prefix="/api")
    app.include_router(settings_routes.router, prefix="/api")

    # Register workers
    from champiq_v2.workers import register_all_workers
    register_all_workers()

    return app


app = create_app()


def run() -> None:
    """Run the application using uvicorn."""
    settings = get_settings()
    uvicorn.run(
        "champiq_v2.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers if not settings.debug else 1,
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__":
    run()
