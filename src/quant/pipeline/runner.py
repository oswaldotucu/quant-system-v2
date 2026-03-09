"""Pipeline runner — advances one experiment through its next gate.

Called by AutomationLoop. Handles DB updates and error logging.
"""

from __future__ import annotations

import logging
import time

from db.queries import (
    Experiment,
    advance_experiment,
    mark_experiment_error,
    reject_experiment,
)
from quant.pipeline.gates import GATE_SEQUENCE, GateResult, run_gate

log = logging.getLogger(__name__)


def run_next_gate(exp: Experiment) -> GateResult:
    """Run the current gate for an experiment and update the DB.

    Returns:
        GateResult (passed or failed)

    Side effects:
        - On pass: advances experiment to next gate in DB
        - On fail: marks experiment as REJECTED in DB
        - On exception: marks experiment with error_msg, does NOT reject (allows retry)
    """
    current_gate = exp.gate
    next_gate = GATE_SEQUENCE.get(current_gate)

    if next_gate is None:
        log.info("Experiment %d is already at terminal gate %s", exp.id, current_gate)
        return GateResult(gate=current_gate, passed=True, reason="terminal gate", metrics={})

    log.info(
        "Running gate %s for exp %d (%s/%s/%s)",
        current_gate,
        exp.id,
        exp.strategy,
        exp.ticker,
        exp.timeframe,
    )

    t0 = time.monotonic()
    try:
        result = run_gate(exp, current_gate)
    except Exception as e:
        elapsed = time.monotonic() - t0
        log.error(
            "Gate %s EXCEPTION for exp %d in %.1fs: %s",
            current_gate,
            exp.id,
            elapsed,
            e,
            exc_info=True,
        )
        mark_experiment_error(exp.id, f"{current_gate}: {e}")
        return GateResult(
            gate=current_gate,
            passed=False,
            reason=f"Exception: {e}",
            metrics={"elapsed_s": round(elapsed, 1)},
        )
    elapsed = time.monotonic() - t0

    if result.passed:
        log.info(
            "Gate %s PASSED for exp %d -> %s in %.1fs", current_gate, exp.id, next_gate, elapsed
        )
        advance_experiment(exp.id, next_gate, result.metrics)
    else:
        log.info(
            "Gate %s FAILED for exp %d in %.1fs: %s", current_gate, exp.id, elapsed, result.reason
        )
        reject_experiment(exp.id, f"{current_gate}: {result.reason}")

    # Return result with elapsed_s for SSE (not stored in DB)
    return GateResult(
        gate=result.gate,
        passed=result.passed,
        reason=result.reason,
        metrics={**result.metrics, "elapsed_s": round(elapsed, 1)},
    )
