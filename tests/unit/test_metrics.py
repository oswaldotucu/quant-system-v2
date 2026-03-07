"""Unit tests for engine/metrics.py.

All values verified by hand — if these fail, something is fundamentally broken.
"""

from __future__ import annotations

from quant.engine.metrics import (
    calmar,
    max_drawdown,
    max_consecutive_losses,
    pf,
    sharpe,
    sortino,
    win_rate,
)


class TestProfitFactor:
    def test_basic_pf(self) -> None:
        trades = [100, -50, 200, -30]
        assert abs(pf(trades) - 300 / 80) < 0.001

    def test_all_wins(self) -> None:
        assert pf([100, 200, 300]) == float("inf")

    def test_all_losses(self) -> None:
        assert pf([-100, -200]) == 0.0

    def test_empty(self) -> None:
        assert pf([]) == 0.0

    def test_breakeven(self) -> None:
        assert pf([100, -100]) == 1.0


class TestWinRate:
    def test_50pct(self) -> None:
        assert win_rate([100, -50, 200, -30]) == 0.5

    def test_empty(self) -> None:
        assert win_rate([]) == 0.0


class TestMaxDrawdown:
    def test_drawdown(self) -> None:
        # Peak at 300, then drops to 100 -> DD = -200
        equity = [100, 200, 300, 250, 100, 150]
        dd_usd, dd_pct = max_drawdown(equity)
        assert dd_usd == -200.0
        assert abs(dd_pct - (-200 / 300 * 100)) < 0.01

    def test_only_up(self) -> None:
        dd_usd, dd_pct = max_drawdown([100, 200, 300])
        assert dd_usd == 0.0
        assert dd_pct == 0.0


class TestCalmar:
    def test_basic(self) -> None:
        assert calmar(30.0, 10.0) == 3.0

    def test_zero_dd(self) -> None:
        assert calmar(30.0, 0.0) == 0.0


class TestMaxConsecutiveLosses:
    def test_streak(self) -> None:
        trades = [100, -10, -20, -30, 100, -10]
        assert max_consecutive_losses(trades) == 3

    def test_no_losses(self) -> None:
        assert max_consecutive_losses([100, 200, 300]) == 0

    def test_all_losses(self) -> None:
        assert max_consecutive_losses([-1, -2, -3]) == 3
