"""JSON API routes — consumed by HTMX and JS charts.

All control operations are here (start/stop runner, fetch data, kill job, etc.)
Business logic is in quant/ and db/. Routes are thin wrappers only.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from db.queries import (
    advance_experiment,
    count_experiments_by_gate,
    count_total_experiments,
    get_experiment,
    get_last_activity,
    list_experiments_by_gate,
    list_experiments_past_gate,
    list_pending_experiments,
    reject_experiment,
)
from quant.automation.loop import AutomationLoop
from quant.automation.seeder import seed
from quant.data.fetcher import fetch_all
from quant.strategies.registry import list_strategies
from webapp.deps import get_cfg, get_runner, get_templates

log = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Automation control
# ---------------------------------------------------------------------------


@router.post("/automation/start")
async def start_automation(runner: AutomationLoop = Depends(get_runner)) -> dict[str, str]:
    if runner.is_running:
        return {"status": "already_running"}
    runner.start()
    return {"status": "started"}


@router.post("/automation/stop")
async def stop_automation(runner: AutomationLoop = Depends(get_runner)) -> dict[str, str]:
    runner.stop()
    return {"status": "stopping"}


@router.post("/automation/pause")
async def pause_automation(runner: AutomationLoop = Depends(get_runner)) -> dict[str, str]:
    runner.pause()
    return {"status": "paused"}


@router.post("/automation/resume")
async def resume_automation(runner: AutomationLoop = Depends(get_runner)) -> dict[str, str]:
    runner.resume()
    return {"status": "running"}


@router.get("/automation/status")
async def automation_status(runner: AutomationLoop = Depends(get_runner)) -> dict[str, Any]:
    return {
        "running": runner.is_running,
        "paused": runner.is_paused,
    }


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@router.post("/data/fetch")
def trigger_fetch(cfg: Any = Depends(get_cfg)) -> dict[str, Any]:
    """Trigger incremental Yahoo Finance data update for all instruments."""
    try:
        results = fetch_all(cfg.data_dir)
        return {
            "status": "ok",
            "results": [
                {"ticker": r.ticker, "tf": r.timeframe, "new_bars": r.new_bars, "status": r.status}
                for r in results
            ],
        }
    except Exception as e:
        log.error("Data fetch failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


@router.get("/experiments")
async def list_experiments_api(gate: str | None = None) -> dict[str, Any]:
    if gate:
        exps = list_experiments_by_gate(gate)
    else:
        exps = list_pending_experiments()
    return {
        "experiments": [
            {
                "id": e.id,
                "strategy": e.strategy,
                "ticker": e.ticker,
                "timeframe": e.timeframe,
                "gate": e.gate,
                "oos_pf": e.oos_pf,
                "oos_trades": e.oos_trades,
                "daily_pnl": e.daily_pnl,
            }
            for e in exps
        ]
    }


_LEADERBOARD_SORT_FIELDS = frozenset({
    "oos_pf", "oos_trades", "oos_sharpe", "oos_sortino", "oos_calmar",
    "daily_pnl", "oos_max_dd_pct",
})


@router.get("/leaderboard")
async def leaderboard_api(sort_by: str = "oos_pf") -> dict[str, Any]:
    """Return all experiments past OOS_VAL, sorted by the given metric."""
    if sort_by not in _LEADERBOARD_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid sort_by '{sort_by}'. "
                f"Must be one of {sorted(_LEADERBOARD_SORT_FIELDS)}"
            ),
        )
    experiments = list_experiments_past_gate("OOS_VAL")

    # Client-requested sort (DB default is oos_pf DESC)
    reverse = sort_by != "oos_max_dd_pct"  # lower DD is better

    def _sort_key(e: Any) -> float:
        val = getattr(e, sort_by)
        if val is None:
            return float("-inf") if reverse else float("inf")
        return val

    experiments.sort(key=_sort_key, reverse=reverse)

    return {
        "experiments": [
            {
                "id": e.id,
                "strategy": e.strategy,
                "ticker": e.ticker,
                "timeframe": e.timeframe,
                "gate": e.gate,
                "oos_pf": e.oos_pf,
                "oos_trades": e.oos_trades,
                "oos_sharpe": e.oos_sharpe,
                "oos_sortino": e.oos_sortino,
                "oos_calmar": e.oos_calmar,
                "daily_pnl": e.daily_pnl,
                "oos_max_dd_pct": e.oos_max_dd_pct,
            }
            for e in experiments
        ],
        "sort_by": sort_by,
    }


@router.post("/experiments/{exp_id}/reject")
async def reject_exp(exp_id: int, reason: str = "Manual rejection") -> dict[str, str]:
    exp = get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    reject_experiment(exp_id, reason)
    return {"status": "rejected"}


# ---------------------------------------------------------------------------
# Strategy seeding
# ---------------------------------------------------------------------------


@router.post("/seed")
async def seed_experiments(
    strategy: str = Form(...),
    tickers: list[str] = Form(...),
    timeframes: list[str] = Form(...),
    priority: int = Form(0),
) -> dict[str, Any]:
    try:
        results = seed(strategy, tickers, timeframes, priority)
        return {
            "seeded": [r.__dict__ for r in results if r.status == "seeded"],
            "already_exists": [r.__dict__ for r in results if r.status == "already_exists"],
        }
    except Exception as e:
        log.error("Seed failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/strategies")
async def list_strategies_api() -> dict[str, Any]:
    return {"strategies": list_strategies()}


# ---------------------------------------------------------------------------
# Lab (ad-hoc backtest)
# ---------------------------------------------------------------------------


@router.post("/lab/run")
def run_lab_backtest(
    request: Request,
    strategy: str = Form(...),
    ticker: str = Form(...),
    timeframe: str = Form(...),
    params: str = Form(...),
    date_from: str = Form(...),
    date_to: str = Form(...),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Run an ad-hoc backtest with custom params and date range. Returns HTML fragment."""
    from quant.data.cache import get_ohlcv
    from quant.engine.backtest import run_backtest
    from quant.strategies.registry import get_strategy

    try:
        params_dict = json.loads(params)
        strategy_cls = get_strategy(strategy)
        data = get_ohlcv(ticker, timeframe)
        sliced = data.loc[date_from:date_to]

        if sliced.empty:
            raise ValueError(f"No data for {ticker}/{timeframe} in {date_from} to {date_to}")

        result = run_backtest(strategy_cls, sliced, params_dict, ticker)
        return templates.TemplateResponse(
            "partials/lab_results.html",
            {
                "request": request,
                "pf": result.pf,
                "trades": result.trades,
                "win_rate": result.win_rate,
                "sharpe": result.sharpe,
                "daily_pnl": result.daily_pnl,
                "max_dd_pct": result.max_dd_pct,
                "total_return_pct": result.total_return_pct,
            },
        )
    except Exception as e:
        log.error("Lab backtest failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# FWD_READY endpoints (Pine Script, checklist, approve)
# ---------------------------------------------------------------------------


@router.get("/pine/{exp_id}")
async def download_pine(exp_id: int) -> FileResponse:
    """Generate and download Pine Script for an experiment."""
    from quant.automation.pine_generator import generate_pine_script

    exp = get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    try:
        path = generate_pine_script(exp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return FileResponse(path, filename=path.name, media_type="text/plain")


@router.get("/checklist/{exp_id}")
async def download_checklist(exp_id: int) -> FileResponse:
    """Generate and download forward-test checklist for an experiment."""
    from quant.automation.checklist_generator import generate_checklist

    exp = get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    path = generate_checklist(exp)
    return FileResponse(path, filename=path.name, media_type="text/markdown")


@router.post("/experiments/{exp_id}/approve")
async def approve_experiment(exp_id: int) -> dict[str, str]:
    """Approve a FWD_READY experiment -> DEPLOYED."""
    exp = get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.gate != "FWD_READY":
        raise HTTPException(
            status_code=400,
            detail=f"Experiment is at gate '{exp.gate}', not FWD_READY",
        )
    advance_experiment(exp_id, "DEPLOYED", {})
    return {"status": "deployed"}


# ---------------------------------------------------------------------------
# Equity chart data
# ---------------------------------------------------------------------------


@router.get("/experiments/{exp_id}/equity")
def experiment_equity(exp_id: int) -> dict[str, Any]:
    """Re-run OOS backtest and return cumulative PnL for equity chart."""
    from quant.data.cache import get_ohlcv
    from quant.data.splitter import oos
    from quant.engine.backtest import run_backtest
    from quant.strategies.registry import get_strategy

    exp = get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.params is None:
        raise HTTPException(status_code=400, detail="Experiment has no params yet")

    strategy_cls = get_strategy(exp.strategy)
    data = get_ohlcv(exp.ticker, exp.timeframe)
    oos_data = oos(data)
    result = run_backtest(strategy_cls, oos_data, exp.params, exp.ticker)

    # Build cumulative PnL from trade_pnl
    from itertools import accumulate

    cum_pnl = list(accumulate(result.trade_pnl)) if result.trade_pnl else []
    labels = [f"T{i + 1}" for i in range(len(cum_pnl))]

    return {"equity": cum_pnl, "labels": labels}


# ---------------------------------------------------------------------------
# Stats and health
# ---------------------------------------------------------------------------


_ALL_GATES = ["SCREEN", "IS_OPT", "OOS_VAL", "CONFIRM", "FWD_READY", "DEPLOYED", "REJECTED"]


@router.get("/stats")
async def pipeline_stats() -> dict[str, Any]:
    """Return experiment counts by gate and total."""
    gate_counts = count_experiments_by_gate()
    total = count_total_experiments()
    return {
        "total": total,
        "by_gate": gate_counts,
    }


@router.get("/stats/html", response_class=HTMLResponse)
async def pipeline_stats_html(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Return stats bar as an HTML fragment for HTMX."""
    gate_counts = count_experiments_by_gate()
    total = count_total_experiments()
    return templates.TemplateResponse(
        "partials/stats_bar.html",
        {
            "request": request,
            "total": total,
            "by_gate": gate_counts,
            "all_gates": _ALL_GATES,
        },
    )


@router.get("/health")
async def health_check(
    request: Request,
    runner: AutomationLoop = Depends(get_runner),
) -> dict[str, Any]:
    """System health endpoint."""
    cfg = get_cfg()
    start_time: float = getattr(request.app.state, "start_time", time.time())
    uptime = time.time() - start_time

    # DB file size
    db_size_mb = 0.0
    db_path = cfg.db_path
    if db_path.exists():
        db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)

    total = count_total_experiments()
    last_activity = get_last_activity()

    status = "ok"
    if not runner.is_running and total > 0:
        status = "degraded"

    return {
        "status": status,
        "db_size_mb": db_size_mb,
        "total_experiments": total,
        "automation_running": runner.is_running,
        "last_activity": last_activity,
        "uptime_seconds": round(uptime, 1),
    }
