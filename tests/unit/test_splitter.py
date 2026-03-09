"""Unit tests for data/splitter.py.

Critical: these tests enforce the IS/OOS split is correct and no leakage occurs.
"""

from __future__ import annotations

import pandas as pd
import pytest

from quant.data.splitter import is_full, is_train, is_val, oos, validate_no_oos_leak


def _make_data() -> pd.DataFrame:
    """DataFrame spanning 2019-2026 for split tests."""
    idx = pd.date_range("2019-01-01", "2026-12-31", freq="D", tz="America/New_York")
    return pd.DataFrame({"close": range(len(idx))}, index=idx)


def test_is_train_range() -> None:
    data = _make_data()
    train = is_train(data)
    assert str(train.index[0].date()) == "2020-01-01"
    assert str(train.index[-1].date()) <= "2022-12-31"


def test_is_val_range() -> None:
    data = _make_data()
    val = is_val(data)
    assert str(val.index[0].date()) >= "2023-01-01"
    assert str(val.index[-1].date()) <= "2023-12-31"


def test_oos_range() -> None:
    data = _make_data()
    oos_data = oos(data)
    assert str(oos_data.index[0].date()) >= "2024-01-01"


def test_is_full_no_oos_data() -> None:
    """IS full should not contain any OOS rows."""
    data = _make_data()
    full = is_full(data)
    assert str(full.index[-1].date()) <= "2023-12-31"


def test_no_overlap_is_train_oos() -> None:
    """IS-train and OOS must be completely disjoint."""
    data = _make_data()
    train_dates = set(is_train(data).index.date)
    oos_dates = set(oos(data).index.date)
    assert len(train_dates & oos_dates) == 0


def test_validate_no_oos_leak_clean() -> None:
    """No exception when data is IS-only."""
    data = _make_data()
    is_only = is_full(data)
    validate_no_oos_leak(is_only, "test")  # should not raise


def test_validate_no_oos_leak_raises() -> None:
    """Should raise when OOS data is present."""
    data = _make_data()
    with pytest.raises(ValueError, match="OOS DATA LEAK"):
        validate_no_oos_leak(data, "test")
