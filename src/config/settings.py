"""Application settings — loaded from .env via pydantic-settings.

All config access goes through Settings. No os.environ[] anywhere else.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # -- Paths ----------------------------------------------------------------
    data_dir: Path = Path("./data/raw")
    db_path: Path = Path("./data/db/quant_v2.db")
    pine_dir: Path = Path("./data/pine_scripts")
    checklist_dir: Path = Path("./data/checklists")

    # -- IS/OOS date splits (DO NOT CHANGE after first use) -------------------
    is_start: str = "2020-01-01"
    is_train_end: str = "2022-12-31"
    is_val_end: str = "2023-12-31"
    oos_start: str = "2024-01-01"

    # -- Trading constants ----------------------------------------------------
    commission_rt: float = 3.40  # USD per round-trip (fees + slippage)

    # -- Pipeline thresholds --------------------------------------------------
    screen_min_pf: float = 1.3
    screen_min_trades: int = 30
    oos_min_pf: float = 1.5
    oos_min_trades: int = 100
    oos_max_dd_pct: float = 40.0
    mc_min_p_positive: float = 0.95
    mc_max_p_ruin: float = 0.01
    is_opt_min_sharpe: float = 0.5
    is_opt_min_pf: float = 1.2
    confirm_max_corr: float = 0.6
    cross_min_trades: int = 50

    # -- Optuna ---------------------------------------------------------------
    optuna_trials: int = 300
    optuna_early_stop: int = 50
    n_workers: int = -1  # -1 = os.cpu_count()

    # -- Automation -----------------------------------------------------------
    autostart_runner: bool = False
    poll_interval: int = 60  # seconds

    @field_validator("data_dir", "pine_dir", "checklist_dir", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        return Path(v)

    @field_validator("db_path", mode="before")
    @classmethod
    def resolve_db_path(cls, v: str | Path) -> Path:
        p = Path(v)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
