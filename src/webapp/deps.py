"""FastAPI dependency injection.

All shared resources are injected via these functions.
No direct imports of singletons in route handlers.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from config.settings import Settings, get_settings
from db.connection import get_conn
from quant.automation.loop import AutomationLoop
from quant.automation.notifier import EventBus


def get_db(request: Request) -> Any:
    """Dependency: thread-local SQLite connection."""
    return get_conn()


def get_runner(request: Request) -> AutomationLoop:
    """Dependency: automation loop instance."""
    return request.app.state.runner


def get_bus(request: Request) -> EventBus:
    """Dependency: event bus instance."""
    return request.app.state.event_bus


def get_templates(request: Request) -> Jinja2Templates:
    """Dependency: Jinja2 templates."""
    return request.app.state.templates


def get_cfg() -> Settings:
    """Dependency: app settings."""
    return get_settings()
