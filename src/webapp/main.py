"""FastAPI application factory.

RULE: This file only wires things together. No business logic here.
RULE: automation loop started via lifespan only if AUTOSTART_RUNNER=true.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config.settings import get_settings
from db.connection import apply_schema
from db.migrations import run_migrations
from quant.automation.loop import AutomationLoop
from quant.automation.notifier import get_event_bus

log = logging.getLogger(__name__)

# Paths relative to this file
_HERE = Path(__file__).parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR = _HERE / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """App startup and shutdown."""
    cfg = get_settings()

    # Initialize DB
    log.info("Initializing database at %s", cfg.db_path)
    apply_schema(cfg.db_path)
    run_migrations(cfg.db_path)

    # Wire up shared state
    runner = AutomationLoop()
    bus = get_event_bus()

    app.state.runner = runner
    app.state.event_bus = bus
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.start_time = time.time()

    # Auto-start automation if configured
    if cfg.autostart_runner:
        log.info("AUTOSTART_RUNNER=true -- starting automation loop")
        runner.start()

    log.info("quant-v2 startup complete")
    yield

    # Shutdown
    if runner.is_running:
        runner.stop()
        log.info("AutomationLoop stopped on shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="quant-v2",
        description="Micro-futures strategy research platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Routers
    from webapp.routes import pages, api, sse
    app.include_router(pages.router)
    app.include_router(api.router, prefix="/api")
    app.include_router(sse.router, prefix="/api")

    return app


# WSGI entrypoint for uvicorn
app = create_app()
