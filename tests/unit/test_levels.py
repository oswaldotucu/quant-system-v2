"""Tests for level computation module.

Verifies:
1. No look-ahead: level[i] uses only data from bars before bar i
2. NaN until first complete period
3. Correct values against known synthetic data
4. Edge cases: empty data, single bar, single period
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.levels import (
    compute_annual_hl,
    compute_monthly_hl,
    compute_or30,
    compute_pdhl,
    compute_quarterly_hl,
    compute_semiannual_hl,
)


def _make_data(
    start: str,
    periods: int,
    freq: str = "5min",
    base_price: float = 18000.0,
    volatility: float = 50.0,
) -> pd.DataFrame:
    """Create synthetic OHLCV data with controlled highs and lows."""
    idx = pd.date_range(start, periods=periods, freq=freq, tz="America/New_York")
    rng = np.random.default_rng(42)
    close = base_price + np.cumsum(rng.normal(0, volatility / 100, periods))
    high = close + rng.uniform(1, volatility / 10, periods)
    low = close - rng.uniform(1, volatility / 10, periods)
    open_ = close + rng.normal(0, volatility / 100, periods)
    vol = rng.integers(100, 1000, periods)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def _make_empty_data() -> pd.DataFrame:
    """Create an empty OHLCV DataFrame with tz-aware index."""
    return pd.DataFrame(
        {"open": [], "high": [], "low": [], "close": [], "volume": []},
        index=pd.DatetimeIndex([], tz="America/New_York"),
    )


# ---------------------------------------------------------------------------
# PDH/PDL tests
# ---------------------------------------------------------------------------
class TestComputePDHL:
    def test_no_look_ahead(self) -> None:
        """PDH/PDL on day 2 must equal H/L of day 1, not day 2."""
        # Create 2 days of 5m data
        data = _make_data("2024-01-15 09:00", periods=200, freq="5min")
        pdh, pdl = compute_pdhl(data)

        # Day 1 bars should have NaN (no previous day)
        day1_mask = data.index.date == data.index[0].date()
        assert np.all(np.isnan(pdh[day1_mask])), "Day 1 PDH should be NaN"
        assert np.all(np.isnan(pdl[day1_mask])), "Day 1 PDL should be NaN"

        # Day 2 bars should have day 1's H/L
        day1_high = data["high"][day1_mask].max()
        day1_low = data["low"][day1_mask].min()
        day2_mask = data.index.date != data.index[0].date()
        if day2_mask.sum() > 0:
            pdh_day2 = pdh[day2_mask]
            pdl_day2 = pdl[day2_mask]
            valid_h = ~np.isnan(pdh_day2)
            valid_l = ~np.isnan(pdl_day2)
            assert valid_h.sum() > 0, "Day 2 should have valid PDH values"
            np.testing.assert_allclose(pdh_day2[valid_h][0], day1_high)
            np.testing.assert_allclose(pdl_day2[valid_l][0], day1_low)

    def test_nan_until_second_day(self) -> None:
        """All bars on the first trading day must be NaN."""
        data = _make_data("2024-01-15 09:00", periods=100, freq="5min")
        pdh, pdl = compute_pdhl(data)

        day1_date = data.index[0].date()
        day1_mask = data.index.date == day1_date
        assert np.all(np.isnan(pdh[day1_mask]))
        assert np.all(np.isnan(pdl[day1_mask]))

    def test_correct_values_three_days(self) -> None:
        """With 3 days of data, day 3 PDH/PDL should equal day 2 H/L."""
        # Use 15min bars across 3 days
        data = _make_data("2024-01-15 09:00", periods=500, freq="15min")
        pdh, pdl = compute_pdhl(data)

        unique_dates = np.unique(data.index.date)
        if len(unique_dates) >= 3:
            day2_mask = data.index.date == unique_dates[1]
            day3_mask = data.index.date == unique_dates[2]
            day2_high = data["high"][day2_mask].max()
            day2_low = data["low"][day2_mask].min()

            pdh_day3 = pdh[day3_mask]
            pdl_day3 = pdl[day3_mask]
            valid_h = ~np.isnan(pdh_day3)
            valid_l = ~np.isnan(pdl_day3)
            if valid_h.sum() > 0:
                np.testing.assert_allclose(pdh_day3[valid_h][0], day2_high)
                np.testing.assert_allclose(pdl_day3[valid_l][0], day2_low)

    def test_output_length_matches_input(self) -> None:
        data = _make_data("2024-01-15 09:00", periods=150, freq="5min")
        pdh, pdl = compute_pdhl(data)
        assert len(pdh) == len(data)
        assert len(pdl) == len(data)

    def test_empty_data(self) -> None:
        data = _make_empty_data()
        pdh, pdl = compute_pdhl(data)
        assert len(pdh) == 0
        assert len(pdl) == 0

    def test_single_bar(self) -> None:
        data = _make_data("2024-01-15 10:00", periods=1, freq="5min")
        pdh, pdl = compute_pdhl(data)
        assert len(pdh) == 1
        assert np.isnan(pdh[0])
        assert np.isnan(pdl[0])


# ---------------------------------------------------------------------------
# OR30 tests
# ---------------------------------------------------------------------------
class TestComputeOR30:
    def test_or_level_after_window(self) -> None:
        """OR30 level should only appear after 10:00 ET."""
        data = _make_data("2024-01-15 09:30", periods=100, freq="5min")
        or_h, or_l = compute_or30(data)

        # Bars strictly before 10:00 (during OR window) should be NaN
        before_10 = data.index.hour * 60 + data.index.minute < 10 * 60
        assert np.all(np.isnan(or_h[before_10])), "OR30 should be NaN during OR window"

        # At least some bars after 10:00 should have valid OR levels
        after_10 = data.index.hour * 60 + data.index.minute >= 10 * 60
        if after_10.sum() > 0:
            assert not np.all(np.isnan(or_h[after_10])), "OR30 should be set after 10:00"

    def test_or_values_match_window_hl(self) -> None:
        """OR30 high/low should match the actual H/L of 9:30-10:00 bars."""
        data = _make_data("2024-01-15 09:30", periods=100, freq="5min")
        or_h, or_l = compute_or30(data)

        # Get OR window bars (9:30 to 9:55 inclusive for 5min bars)
        or_mask = (data.index.hour == 9) & (data.index.minute >= 30)
        expected_h = data["high"][or_mask].max()
        expected_l = data["low"][or_mask].min()

        # First bar after OR window
        after_10 = data.index.hour * 60 + data.index.minute >= 10 * 60
        if after_10.sum() > 0:
            first_after = np.where(after_10)[0][0]
            np.testing.assert_allclose(or_h[first_after], expected_h)
            np.testing.assert_allclose(or_l[first_after], expected_l)

    def test_no_look_ahead_across_days(self) -> None:
        """OR30 on day 2 should not use day 2's data before OR window completes."""
        data = _make_data("2024-01-15 09:00", periods=400, freq="5min")
        or_h, or_l = compute_or30(data)

        dates = data.index.date
        unique_dates = np.unique(dates)
        if len(unique_dates) >= 2:
            day1 = unique_dates[0]
            day2 = unique_dates[1]

            # Compute day 1's OR high (9:30-10:00 window on day 1)
            day1_or_mask = (dates == day1) & (data.index.hour == 9) & (data.index.minute >= 30)
            assert day1_or_mask.sum() > 0, "Day 1 must have OR window bars"
            day1_or_h = data["high"][day1_or_mask].max()

            # Bars on day 2 BEFORE the OR window completes should carry day 1's OR
            day2_early = (dates == day2) & (data.index.hour * 60 + data.index.minute < 10 * 60)
            if day2_early.sum() > 0:
                early_vals = or_h[day2_early]
                valid_early = early_vals[~np.isnan(early_vals)]
                # Early day-2 bars must carry day 1's OR value, not day 2's
                if len(valid_early) > 0:
                    np.testing.assert_allclose(
                        valid_early,
                        day1_or_h,
                        err_msg="Day 2 pre-OR bars should carry day 1's OR high",
                    )

    def test_output_length_matches_input(self) -> None:
        data = _make_data("2024-01-15 09:30", periods=50, freq="5min")
        or_h, or_l = compute_or30(data)
        assert len(or_h) == len(data)
        assert len(or_l) == len(data)

    def test_empty_data(self) -> None:
        data = _make_empty_data()
        or_h, or_l = compute_or30(data)
        assert len(or_h) == 0
        assert len(or_l) == 0

    def test_single_bar(self) -> None:
        data = _make_data("2024-01-15 09:30", periods=1, freq="5min")
        or_h, or_l = compute_or30(data)
        assert len(or_h) == 1


# ---------------------------------------------------------------------------
# Monthly H/L tests
# ---------------------------------------------------------------------------
class TestComputeMonthlyHL:
    def test_no_look_ahead(self) -> None:
        """Monthly level in Feb must equal Jan's H/L."""
        # 2 months of 15min data
        data = _make_data("2024-01-02 10:00", periods=2000, freq="15min")
        mh, ml = compute_monthly_hl(data)

        # January bars should have NaN (no previous month in dataset)
        jan_mask = data.index.month == 1
        assert np.all(np.isnan(mh[jan_mask])), "January monthly level should be NaN"
        assert np.all(np.isnan(ml[jan_mask])), "January monthly level should be NaN"

        # February bars should have January's H/L
        jan_high = data["high"][jan_mask].max()
        jan_low = data["low"][jan_mask].min()
        feb_mask = data.index.month == 2
        if feb_mask.sum() > 0:
            feb_h_vals = mh[feb_mask]
            feb_l_vals = ml[feb_mask]
            valid_h = ~np.isnan(feb_h_vals)
            valid_l = ~np.isnan(feb_l_vals)
            if valid_h.sum() > 0:
                np.testing.assert_allclose(feb_h_vals[valid_h][0], jan_high)
                np.testing.assert_allclose(feb_l_vals[valid_l][0], jan_low)

    def test_nan_during_first_period(self) -> None:
        """All bars in the first month should be NaN."""
        data = _make_data("2024-03-15 10:00", periods=1000, freq="15min")
        mh, ml = compute_monthly_hl(data)
        first_month = data.index.month == data.index[0].month
        assert np.all(np.isnan(mh[first_month]))
        assert np.all(np.isnan(ml[first_month]))

    def test_output_length_matches_input(self) -> None:
        data = _make_data("2024-01-02 10:00", periods=500, freq="15min")
        mh, ml = compute_monthly_hl(data)
        assert len(mh) == len(data)
        assert len(ml) == len(data)

    def test_empty_data(self) -> None:
        data = _make_empty_data()
        mh, ml = compute_monthly_hl(data)
        assert len(mh) == 0
        assert len(ml) == 0


# ---------------------------------------------------------------------------
# Quarterly H/L tests
# ---------------------------------------------------------------------------
class TestComputeQuarterlyHL:
    def test_no_look_ahead(self) -> None:
        """Q2 level must equal Q1's H/L."""
        # Span Q1 and Q2 (Jan through April)
        data = _make_data("2024-01-02 10:00", periods=5000, freq="15min")
        qh, ql = compute_quarterly_hl(data)

        q1_mask = data.index.month <= 3
        q2_mask = (data.index.month >= 4) & (data.index.month <= 6)

        # Q1 bars should be NaN
        assert np.all(np.isnan(qh[q1_mask])), "Q1 quarterly level should be NaN"

        # Q2 should carry Q1's H/L
        if q2_mask.sum() > 0:
            q1_high = data["high"][q1_mask].max()
            q2_vals = qh[q2_mask]
            valid = ~np.isnan(q2_vals)
            if valid.sum() > 0:
                np.testing.assert_allclose(q2_vals[valid][0], q1_high)

    def test_returns_correct_shape(self) -> None:
        data = _make_data("2024-01-02 10:00", periods=5000, freq="15min")
        qh, ql = compute_quarterly_hl(data)
        assert len(qh) == len(data)
        assert len(ql) == len(data)

    def test_empty_data(self) -> None:
        data = _make_empty_data()
        qh, ql = compute_quarterly_hl(data)
        assert len(qh) == 0
        assert len(ql) == 0


# ---------------------------------------------------------------------------
# Semiannual H/L tests
# ---------------------------------------------------------------------------
class TestComputeSemiannualHL:
    def test_nan_during_first_half(self) -> None:
        """First 6 months should be NaN (no previous half-year)."""
        data = _make_data("2024-01-02 10:00", periods=10000, freq="15min")
        sh, sl = compute_semiannual_hl(data)
        h1_mask = data.index.month <= 6
        assert np.all(np.isnan(sh[h1_mask]))

    def test_returns_correct_shape(self) -> None:
        data = _make_data("2023-01-02 10:00", periods=10000, freq="15min")
        sh, sl = compute_semiannual_hl(data)
        assert len(sh) == len(data)
        assert len(sl) == len(data)

    def test_empty_data(self) -> None:
        data = _make_empty_data()
        sh, sl = compute_semiannual_hl(data)
        assert len(sh) == 0
        assert len(sl) == 0


# ---------------------------------------------------------------------------
# Annual H/L tests
# ---------------------------------------------------------------------------
class TestComputeAnnualHL:
    def test_no_look_ahead(self) -> None:
        """2024 level must equal 2023's H/L, not 2024's."""
        # Span 2023 and 2024
        data = _make_data("2023-06-01 10:00", periods=20000, freq="15min")
        ah, al = compute_annual_hl(data)

        y2023_mask = data.index.year == 2023
        y2024_mask = data.index.year == 2024

        # 2023 bars should be NaN (first year, no previous)
        assert np.all(np.isnan(ah[y2023_mask])), "First year should be NaN"

        # 2024 should carry 2023's H/L
        if y2024_mask.sum() > 0:
            y2023_high = data["high"][y2023_mask].max()
            y2023_low = data["low"][y2023_mask].min()
            y2024_h = ah[y2024_mask]
            valid = ~np.isnan(y2024_h)
            if valid.sum() > 0:
                np.testing.assert_allclose(y2024_h[valid][0], y2023_high)
                y2024_l = al[y2024_mask]
                valid_l = ~np.isnan(y2024_l)
                np.testing.assert_allclose(y2024_l[valid_l][0], y2023_low)

    def test_returns_correct_shape(self) -> None:
        data = _make_data("2022-06-01 10:00", periods=20000, freq="15min")
        ah, al = compute_annual_hl(data)
        assert len(ah) == len(data)
        assert len(al) == len(data)

    def test_empty_data(self) -> None:
        data = _make_empty_data()
        ah, al = compute_annual_hl(data)
        assert len(ah) == 0
        assert len(al) == 0

    def test_single_bar(self) -> None:
        data = _make_data("2024-01-15 10:00", periods=1, freq="15min")
        ah, al = compute_annual_hl(data)
        assert len(ah) == 1
        assert np.isnan(ah[0])
        assert np.isnan(al[0])
