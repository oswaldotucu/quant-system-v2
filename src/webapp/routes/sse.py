"""Server-Sent Events stream.

Correct threading pattern:
- EventBus uses queue.Queue (thread-safe stdlib, NOT asyncio.Queue)
- SSE route bridges to asyncio via loop.run_in_executor(None, lambda: sub.get(timeout=30))
- On timeout, emits keepalive comment to prevent proxy cutoff
- On client disconnect, unsubscribes from bus

RULE: NEVER use asyncio.Queue here -- it cannot be put() from a thread safely.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from webapp.deps import get_bus
from quant.automation.notifier import EventBus

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/events")
async def sse_stream(
    request: Request,
    bus: EventBus = Depends(get_bus),
) -> StreamingResponse:
    """SSE endpoint. Browser connects here once; events flow until disconnect."""
    sub = bus.subscribe()
    loop = asyncio.get_event_loop()

    async def generator() -> AsyncGenerator[str, None]:
        try:
            while not await request.is_disconnected():
                try:
                    # Bridge: drain thread-safe queue from async context
                    event: dict[str, Any] = await loop.run_in_executor(
                        None, lambda: sub.get(timeout=30)
                    )
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Keepalive: prevents proxy/load balancer timeout
                    yield ": keepalive\n\n"
                except Exception as e:
                    log.error("SSE generator error: %s", e)
                    break
        finally:
            bus.unsubscribe(sub)
            log.debug("SSE client disconnected, unsubscribed")

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
