"""EventBus for real-time SSE updates.

Uses queue.Queue (thread-safe stdlib) — NOT asyncio.Queue.
The FastAPI SSE route bridges to async via loop.run_in_executor().

RULE: Never put asyncio.Queue in a thread. This is the correct pattern.
See routes/sse.py for the async consumer side.
"""

from __future__ import annotations

import logging
import queue
import subprocess
import threading
from typing import Any

log = logging.getLogger(__name__)

MAX_SUBSCRIBER_QUEUE_SIZE = 200  # overflow dropped gracefully


class EventBus:
    """Singleton event bus for automation loop -> SSE -> browser updates."""

    def __init__(self) -> None:
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        """Register a new SSE subscriber. Returns a queue to drain from."""
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=MAX_SUBSCRIBER_QUEUE_SIZE)
        with self._lock:
            self._subscribers.append(q)
        log.debug("EventBus: +subscriber (total %d)", len(self._subscribers))
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        """Remove a subscriber queue (called when SSE client disconnects)."""
        with self._lock:
            try:
                self._subscribers.remove(q)
                log.debug("EventBus: -subscriber (total %d)", len(self._subscribers))
            except ValueError:
                pass

    def emit(self, event: dict[str, Any]) -> None:
        """Broadcast event to all subscribers. Overflow is dropped."""
        with self._lock:
            snapshot = list(self._subscribers)
        for q in snapshot:
            try:
                q.put_nowait(event)
            except queue.Full:
                log.debug("EventBus: subscriber queue full, event dropped: %s", event.get("type"))

    def emit_gate_progress(
        self,
        exp_id: int,
        gate: str,
        status: str,
        **kwargs: Any,
    ) -> None:
        self.emit(
            {"type": "gate_progress", "exp_id": exp_id, "gate": gate, "status": status, **kwargs}
        )

    def emit_gate_error(self, exp_id: int, gate: str, error: str) -> None:
        self.emit({"type": "gate_error", "exp_id": exp_id, "gate": gate, "error": error})

    def emit_fwd_ready(self, exp_id: int, strategy: str, ticker: str, oos_pf: float) -> None:
        self.emit(
            {
                "type": "fwd_ready",
                "exp_id": exp_id,
                "strategy": strategy,
                "ticker": ticker,
                "oos_pf": oos_pf,
            }
        )


def notify_macos(title: str, message: str) -> None:
    """Send a macOS system notification (fire and forget)."""
    try:
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
        safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
        script = f'display notification "{safe_message}" with title "{safe_title}"'
        subprocess.run(["osascript", "-e", script], timeout=2, capture_output=True)  # noqa: S603, S607
    except Exception as e:
        log.warning("macOS notification failed: %s", e)


# Singleton
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
