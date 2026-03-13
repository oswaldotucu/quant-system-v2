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
    staging_dir: Path = Path("")  # NT export staging folder (empty = disabled)

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

    # -- Session filtering (Sentinel research) --------------------------------
    session_filter: bool = True
    session_start_et: int = 9
    session_end_et: int = 14
    exit_time_et: int = 15  # force exit hour ET (options: 12,13,14,15)
    time_exit: bool = True  # force exit at exit_time_et; disable for overnight holds
    dow_filter: bool = False  # off by default; enable for Thu/Fri-only
    dow_allowed_days: str = "3,4"  # comma-separated weekday ints

    @field_validator("dow_allowed_days", mode="before")
    @classmethod
    def validate_dow_days(cls, v: str) -> str:
        """Validate dow_allowed_days is comma-separated ints in 0-6."""
        for part in str(v).split(","):
            day = int(part.strip())
            if not 0 <= day <= 6:
                raise ValueError(f"DOW day must be 0-6, got {day}")
        return str(v)

    @field_validator("data_dir", "pine_dir", "checklist_dir", "staging_dir", mode="before")
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
