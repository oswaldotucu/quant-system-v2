-- schema.sql -- version 1
-- Every connection must execute: PRAGMA foreign_keys = ON;
-- See db/connection.py for enforcement.

CREATE TABLE IF NOT EXISTS strategies (
    id          INTEGER PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,        -- 'ema_rsi'
    family      TEXT NOT NULL,               -- 'trend_following'
    description TEXT,
    param_space TEXT NOT NULL,               -- JSON: Optuna search space
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS experiments (
    id          INTEGER PRIMARY KEY,
    strategy    TEXT NOT NULL REFERENCES strategies(name),
    ticker      TEXT NOT NULL CHECK(ticker IN ('MNQ','MES','MGC')),
    timeframe   TEXT NOT NULL CHECK(timeframe IN ('1m','5m','15m')),
    params      TEXT,                        -- JSON: best params from IS_OPT
    gate        TEXT NOT NULL DEFAULT 'SCREEN'
                CHECK(gate IN ('SCREEN','IS_OPT','OOS_VAL','CONFIRM','FWD_READY','DEPLOYED','REJECTED')),
    priority    INTEGER NOT NULL DEFAULT 0,  -- higher = runs first (set via dashboard)
    error_msg   TEXT,                        -- populated if gate raised an exception

    -- SCREEN gate results
    screen_pf       REAL,
    screen_trades   INTEGER,

    -- IS_OPT gate results
    is_sharpe       REAL,
    is_pf           REAL,
    sens_min_pf     REAL,                    -- parameter sensitivity: worst neighbor OOS PF

    -- OOS_VAL gate results
    oos_pf          REAL,
    oos_trades      INTEGER,
    oos_sharpe      REAL,
    oos_sortino     REAL,
    oos_calmar      REAL,
    oos_max_dd      REAL,                    -- in USD
    oos_max_dd_pct  REAL,                    -- as % of peak equity
    daily_pnl       REAL,                    -- $/day OOS net of commission
    quarterly_wr    TEXT,                    -- JSON: {'2024Q1': 0.82, ...}

    -- CONFIRM gate results
    p_ruin          REAL,                    -- Monte Carlo P(ruin at -30% DD)
    p_positive      REAL,                    -- Monte Carlo P(positive 1yr)
    wf_windows      INTEGER,                 -- walk-forward: profitable windows out of 4
    cross_confirmed INTEGER DEFAULT 0,       -- 1 if same params pass on >= 1 other instrument
    max_corr        REAL,                    -- max Pearson corr vs deployed strategies

    -- Output
    notes          TEXT,
    pine_path      TEXT,                     -- path to generated Pine Script file
    checklist_path TEXT,                     -- path to generated checklist markdown file

    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Auto-update updated_at on every UPDATE (SQLite does not do this automatically)
CREATE TRIGGER IF NOT EXISTS experiments_updated_at
    AFTER UPDATE ON experiments
    BEGIN
        UPDATE experiments SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE INDEX IF NOT EXISTS idx_experiments_gate     ON experiments(gate, priority DESC);
CREATE INDEX IF NOT EXISTS idx_experiments_strategy ON experiments(strategy, ticker, timeframe);
-- Allow re-seed only after rejection
CREATE UNIQUE INDEX IF NOT EXISTS idx_experiments_unique ON experiments(strategy, ticker, timeframe)
    WHERE gate NOT IN ('REJECTED');

CREATE TABLE IF NOT EXISTS optuna_trials (
    id          INTEGER PRIMARY KEY,
    exp_id      INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    trial_num   INTEGER NOT NULL,
    params      TEXT NOT NULL,               -- JSON
    is_sharpe   REAL,                        -- objective metric (IS-val Sharpe, NOT PF)
    is_train_pf REAL,                        -- IS-train PF (diagnostic only)
    is_val_pf   REAL,                        -- IS-val PF (diagnostic only)
    state       TEXT NOT NULL DEFAULT 'complete'
                CHECK(state IN ('complete','pruned','failed')),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trials_exp     ON optuna_trials(exp_id);
CREATE INDEX IF NOT EXISTS idx_trials_exp_best ON optuna_trials(exp_id, is_sharpe DESC);
