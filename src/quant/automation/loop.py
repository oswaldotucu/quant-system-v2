"""AutomationLoop — background thread that advances pipeline experiments.

Polls DB every POLL_INTERVAL seconds, picks pending experiments, and runs their
next gate in a ThreadPoolExecutor.

RULE: Uses ThreadPoolExecutor (NOT multiprocessing) because:
- SQLite connections cannot be pickled across processes
- vectorbt releases GIL during numpy operations -> threads get real parallelism
- CSV cache is shared across threads (same process memory)

RULE: Uses queue.Queue for EventBus (NOT asyncio.Queue) because this runs in a thread.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from typing import Any

from config.settings import get_settings
from db.queries import list_pending_experiments, Experiment
from quant.automation.notifier import get_event_bus, notify_macos
from quant.pipeline.runner import run_next_gate, GateResult

log = logging.getLogger(__name__)


class AutomationLoop:
    """Background thread: polls DB, runs gates, emits events."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._bus = get_event_bus()
        self._cfg = get_settings()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def start(self) -> None:
        """Start the automation loop in a background thread."""
        if self.is_running:
            log.warning("AutomationLoop already running")
            return
        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(target=self._loop, name="automation-loop", daemon=True)
        self._thread.start()
        log.info("AutomationLoop started")

    def stop(self) -> None:
        """Signal the loop to stop. Non-blocking."""
        self._stop_event.set()
        log.info("AutomationLoop stop requested")

    def pause(self) -> None:
        """Pause the loop (don't pick up new experiments)."""
        self._pause_event.set()
        log.info("AutomationLoop paused")

    def resume(self) -> None:
        """Resume from pause."""
        self._pause_event.clear()
        log.info("AutomationLoop resumed")

    def _loop(self) -> None:
        """Main loop: poll -> dispatch -> sleep."""
        n_workers = self._cfg.n_workers
        if n_workers < 1:
            import os
            n_workers = os.cpu_count() or 4

        log.info("AutomationLoop running with %d workers, poll=%ds",
                 n_workers, self._cfg.poll_interval)

        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                time.sleep(5)
                continue

            try:
                self._tick(n_workers)
            except Exception as e:
                log.error("AutomationLoop tick error: %s", e, exc_info=True)

            self._stop_event.wait(timeout=self._cfg.poll_interval)

        log.info("AutomationLoop stopped")

    def _tick(self, n_workers: int) -> None:
        """One tick: fetch pending experiments and advance their gates."""
        experiments = list_pending_experiments()
        if not experiments:
            return

        log.info("Tick: %d experiments pending", len(experiments))

        # Dynamic timeout: IS_OPT can take up to 2h (300 Optuna trials).
        # Other gates complete in < 5min.
        has_is_opt = any(e.gate == "IS_OPT" for e in experiments)
        tick_timeout = 7200 if has_is_opt else 300

        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures: dict[Future[GateResult], Experiment] = {
                pool.submit(run_next_gate, exp): exp
                for exp in experiments
            }

            try:
                for future in as_completed(futures, timeout=tick_timeout):
                    exp = futures[future]
                    try:
                        result = future.result()
                        elapsed = result.metrics.get("elapsed_s", 0.0)
                        self._bus.emit_gate_progress(
                            exp_id=exp.id,
                            gate=exp.gate,
                            status="passed" if result.passed else "rejected",
                            reason=result.reason,
                            strategy=exp.strategy,
                            ticker=exp.ticker,
                            timeframe=exp.timeframe,
                            elapsed_s=elapsed,
                        )
                        if result.passed and exp.gate == "CONFIRM":
                            notify_macos(
                                "FWD_READY",
                                f"{exp.strategy} {exp.ticker} {exp.timeframe} is ready!",
                            )
                            self._bus.emit_fwd_ready(
                                exp_id=exp.id,
                                strategy=exp.strategy,
                                ticker=exp.ticker,
                                oos_pf=exp.oos_pf or 0.0,
                            )
                    except Exception as e:
                        log.error(
                            "Gate future error for exp %d (%s/%s/%s at %s): %s",
                            exp.id, exp.strategy, exp.ticker, exp.timeframe,
                            exp.gate, e, exc_info=True,
                        )
                        self._bus.emit_gate_error(exp.id, exp.gate, str(e))
            except TimeoutError:
                log.error("Tick timed out after %ds — some gates may still be running", tick_timeout)
