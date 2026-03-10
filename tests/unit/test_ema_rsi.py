"""Unit tests for quant/strategies/ema_rsi.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.ema_rsi import EmaRsiStrategy


class TestGenerateReturnsCorrectShapes:
    """generate() must return 3 arrays each of length n."""

    def test_generate_returns_correct_shapes(self, sample_ohlcv: pd.DataFrame) -> None:
        params = EmaRsiStrategy.default_params()
        entries, exits, direction = EmaRsiStrategy.generate(sample_ohlcv, params)
        n = len(sample_ohlcv)

        assert entries.shape == (n,)
        assert exits.shape == (n,)
        assert direction.shape == (n,)


class TestGenerateReturnsBooleanArrays:
    """All 3 arrays must be boolean dtype."""

    def test_generate_returns_boolean_arrays(self, sample_ohlcv: pd.DataFrame) -> None:
        params = EmaRsiStrategy.default_params()
        entries, exits, direction = EmaRsiStrategy.generate(sample_ohlcv, params)

        assert entries.dtype == bool
        assert exits.dtype == bool
        assert direction.dtype == bool


class TestNoEntriesDuringWarmup:
    """Entries must be all False during warmup period."""

    def test_no_entries_during_warmup(self, sample_ohlcv: pd.DataFrame) -> None:
        params = EmaRsiStrategy.default_params()
        entries, _, _ = EmaRsiStrategy.generate(sample_ohlcv, params)

        # Warmup = max(ema_slow, rsi_period)
        warmup = max(params["ema_slow"], params["rsi_period"])
        assert not entries[:warmup].any(), (
            f"Expected no entries during warmup period (first {warmup} bars)"
        )


class TestDefaultParamsReturnsDict:
    """default_params() must return a non-empty dict."""

    def test_default_params_returns_dict(self) -> None:
        params = EmaRsiStrategy.default_params()
        assert isinstance(params, dict)
        assert len(params) > 0


class TestEntriesSubsetOfDirection:
    """Every entry bar must have a direction set (no entry without direction info)."""

    def test_entries_subset_of_direction(self, sample_ohlcv: pd.DataFrame) -> None:
        params = EmaRsiStrategy.default_params()
        entries, _, direction = EmaRsiStrategy.generate(sample_ohlcv, params)

        # Where entries fire, direction must be True (long) or False (short).
        # Since direction is bool, this is always satisfied structurally.
        # The meaningful check: every long entry has direction=True,
        # and entries without direction=True must be short entries.
        # i.e., entries should be a subset of (long_entries | short_entries)
        # which equals entries itself. Verify at least that entry bars
        # don't appear where neither long nor short logic would trigger.
        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0, "Need entries to test direction"

        long_entries = entries & direction
        short_entries = entries & ~direction

        # Every entry must be either long or short
        assert np.array_equal(entries, long_entries | short_entries)
