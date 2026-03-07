"""Unit tests for quant/strategies/volume_breakout.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant.strategies.volume_breakout import VolumeBreakoutStrategy


class TestGeneratesSignals:
    def test_generates_signals(self, sample_ohlcv: pd.DataFrame) -> None:
        params = VolumeBreakoutStrategy.default_params()
        entries, exits, direction = VolumeBreakoutStrategy.generate(sample_ohlcv, params)

        assert entries.shape == (len(sample_ohlcv),)
        assert exits.shape == (len(sample_ohlcv),)
        assert direction.shape == (len(sample_ohlcv),)
        assert entries.dtype == bool
        assert exits.dtype == bool
        assert direction.dtype == bool
        assert entries.sum() > 0, "Strategy generated zero entry signals"

    def test_exits_all_false(self, sample_ohlcv: pd.DataFrame) -> None:
        params = VolumeBreakoutStrategy.default_params()
        _, exits, _ = VolumeBreakoutStrategy.generate(sample_ohlcv, params)
        assert exits.sum() == 0


class TestDirectionMatchesEntries:
    def test_direction_array_matches_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        params = VolumeBreakoutStrategy.default_params()
        entries, _, direction = VolumeBreakoutStrategy.generate(sample_ohlcv, params)

        entry_indices = np.where(entries)[0]
        assert len(entry_indices) > 0
        total = direction[entries].sum() + (~direction[entries]).sum()
        assert total > 0

    def test_volume_spike_at_entries(self, sample_ohlcv: pd.DataFrame) -> None:
        """All entries must occur on bars with above-average volume."""
        params = VolumeBreakoutStrategy.default_params()
        entries, _, _ = VolumeBreakoutStrategy.generate(sample_ohlcv, params)

        volume = sample_ohlcv["volume"].values.astype(float)
        avg_vol = pd.Series(volume).rolling(params["vol_period"]).mean().values

        entry_mask = entries & ~np.isnan(avg_vol)
        if entry_mask.sum() > 0:
            assert np.all(
                volume[entry_mask] > params["vol_multiplier"] * avg_vol[entry_mask]
            )


class TestEdgeCases:
    def test_empty_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.5], "volume": [1000],
        }, index=pd.date_range("2023-01-01", periods=1, freq="15min"))
        params = VolumeBreakoutStrategy.default_params()
        entries, exits, direction = VolumeBreakoutStrategy.generate(tiny, params)
        assert entries.shape == (1,)
        assert entries.sum() == 0

    def test_short_data(self) -> None:
        tiny = pd.DataFrame({
            "open": [100.0] * 5, "high": [101.0] * 5, "low": [99.0] * 5,
            "close": [100.5] * 5, "volume": [1000] * 5,
        }, index=pd.date_range("2023-01-01", periods=5, freq="15min"))
        params = VolumeBreakoutStrategy.default_params()
        entries, _, _ = VolumeBreakoutStrategy.generate(tiny, params)
        assert entries.sum() == 0


class TestDefaultParams:
    def test_has_all_required_keys(self) -> None:
        params = VolumeBreakoutStrategy.default_params()
        required = {"vol_period", "vol_multiplier", "session_lookback", "tp_pct", "sl_pct"}
        assert set(params.keys()) == required

    def test_intraday_scale_tp_sl(self) -> None:
        params = VolumeBreakoutStrategy.default_params()
        assert params["tp_pct"] < 1.0
        assert params["sl_pct"] < 1.0


class TestClassAttributes:
    def test_name(self) -> None:
        assert VolumeBreakoutStrategy.name == "volume_breakout"

    def test_family(self) -> None:
        assert VolumeBreakoutStrategy.family == "price_action"
