"""HTML page routes — server-rendered Jinja2 templates."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db.queries import (
    count_experiments_by_gate,
    list_experiments_by_gate,
    list_experiments_past_gate,
    list_pending_experiments,
)
from quant.automation.loop import AutomationLoop
from quant.strategies.registry import list_strategies
from webapp.deps import get_runner, get_templates

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    runner: AutomationLoop = Depends(get_runner),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    deployed = list_experiments_by_gate("DEPLOYED")
    pending = list_pending_experiments()
    gate_counts = count_experiments_by_gate()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "deployed": deployed,
            "pending": pending,
            "gate_counts": gate_counts,
            "runner_running": runner.is_running,
            "runner_paused": runner.is_paused,
        },
    )


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline(
    request: Request,
    gate: str | None = None,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    if gate:
        experiments = list_experiments_by_gate(gate)
    else:
        experiments = list_pending_experiments()
    return templates.TemplateResponse(
        "pipeline.html",
        {"request": request, "experiments": experiments, "active_gate": gate},
    )


@router.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    experiments = list_experiments_past_gate("OOS_VAL")
    return templates.TemplateResponse(
        "leaderboard.html",
        {"request": request, "experiments": experiments},
    )


@router.get("/experiment/{exp_id}", response_class=HTMLResponse)
async def experiment_detail(
    request: Request,
    exp_id: int,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    from db.queries import count_trials, get_best_trial, get_experiment

    exp = get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    best_trial = get_best_trial(exp_id)
    trial_count = count_trials(exp_id)

    return templates.TemplateResponse(
        "experiment_detail.html",
        {
            "request": request,
            "exp": exp,
            "best_trial": best_trial,
            "trial_count": trial_count,
        },
    )


@router.get("/strategies", response_class=HTMLResponse)
async def strategies_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "strategies.html",
        {"request": request, "strategies": list_strategies()},
    )


@router.get("/portfolio", response_class=HTMLResponse)
async def portfolio(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    deployed = list_experiments_by_gate("DEPLOYED")
    return templates.TemplateResponse("portfolio.html", {"request": request, "deployed": deployed})


@router.get("/fwd-ready", response_class=HTMLResponse)
async def fwd_ready(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    experiments = list_experiments_by_gate("FWD_READY")
    return templates.TemplateResponse(
        "fwd_ready.html", {"request": request, "experiments": experiments}
    )


@router.get("/lab", response_class=HTMLResponse)
async def lab(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "lab.html",
        {"request": request, "strategies": list_strategies()},
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    from webapp.deps import get_cfg

    cfg = get_cfg()
    return templates.TemplateResponse("settings.html", {"request": request, "cfg": cfg})
