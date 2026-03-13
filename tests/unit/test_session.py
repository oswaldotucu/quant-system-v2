"""Tests for session time filter module."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.data.session import make_dow_mask, make_session_mask, make_time_exit_mask


def _make_index(hours: list[int], tz: str = "America/New_York") -> pd.DatetimeIndex:
    """Create a DatetimeIndex with specified hours on a single day."""
    base = pd.Timestamp("2024-01-15", tz=tz)  # A Monday
    return pd.DatetimeIndex([base + pd.Timedelta(hours=h) for h in hours])


class TestMakeSessionMask:
    def test_default_9_to_14(self) -> None:
        hours = list(range(0, 24))
        idx = _make_index(hours)
        mask = make_session_mask(idx)
        # Hours 9,10,11,12,13 should be True (5 hours)
        assert mask.sum() == 5
        assert mask[9]
        assert mask[13]
        assert not mask[14]
        assert not mask[8]

    def test_custom_range(self) -> None:
        hours = list(range(0, 24))
        idx = _make_index(hours)
        mask = make_session_mask(idx, start_et=10, end_et=12)
        assert mask.sum() == 2
        assert mask[10]
        assert mask[11]
        assert not mask[12]

    def test_empty_index(self) -> None:
        idx = pd.DatetimeIndex([], tz="America/New_York")
        mask = make_session_mask(idx)
        assert len(mask) == 0

    def test_tz_naive_treated_as_et(self) -> None:
        """If index is tz-naive, we treat .hour as ET."""
        hours = [9, 10, 15]
        idx = pd.DatetimeIndex([pd.Timestamp("2024-01-15") + pd.Timedelta(hours=h) for h in hours])
        mask = make_session_mask(idx)
        assert mask[0]  # 9
        assert mask[1]  # 10
        assert not mask[2]  # 15


class TestMakeDowMask:
    def test_default_thu_fri(self) -> None:
        # Create index spanning Mon-Fri
        dates = pd.date_range("2024-01-15", periods=5, freq="D", tz="America/New_York")
        # Mon=15, Tue=16, Wed=17, Thu=18, Fri=19
        mask = make_dow_mask(dates)
        assert not mask[0]  # Mon
        assert not mask[1]  # Tue
        assert not mask[2]  # Wed
        assert mask[3]  # Thu
        assert mask[4]  # Fri

    def test_custom_days(self) -> None:
        dates = pd.date_range("2024-01-15", periods=5, freq="D", tz="America/New_York")
        mask = make_dow_mask(dates, allowed_days=(0, 4))  # Mon + Fri
        assert mask[0]  # Mon
        assert not mask[1]  # Tue
        assert mask[4]  # Fri

    def test_empty_index(self) -> None:
        idx = pd.DatetimeIndex([], tz="America/New_York")
        mask = make_dow_mask(idx)
        assert len(mask) == 0


class TestMakeTimeExitMask:
    def test_default_exit_at_15(self) -> None:
        hours = list(range(0, 24))
        idx = _make_index(hours)
        mask = make_time_exit_mask(idx)
        # Hours 15-23 should be True (9 hours)
        assert mask.sum() == 9
        assert not mask[14]  # 2pm
        assert mask[15]  # 3pm
        assert mask[23]

    def test_exit_at_12(self) -> None:
        hours = list(range(0, 24))
        idx = _make_index(hours)
        mask = make_time_exit_mask(idx, exit_hour_et=12)
        # Hours 12-23 = 12 hours
        assert mask.sum() == 12
        assert not mask[11]
        assert mask[12]

    def test_empty_index(self) -> None:
        idx = pd.DatetimeIndex([], tz="America/New_York")
        mask = make_time_exit_mask(idx)
        assert len(mask) == 0

    def test_combined_with_session_mask(self) -> None:
        """Session mask + time exit should create a valid trading window."""
        hours = list(range(0, 24))
        idx = _make_index(hours)
        session = make_session_mask(idx, start_et=9, end_et=14)
        time_exit = make_time_exit_mask(idx, exit_hour_et=15)

        # Entry window: 9-14 (session mask on entries)
        # Exit window: >= 15 (time exit on exits)
        # No overlap: entries stop at 14, exits start at 15
        assert not np.any(
            session[:14] & time_exit[:14]
        )  # No bar is both entry and exit in the 0-14 range
