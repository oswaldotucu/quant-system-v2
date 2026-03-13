"""Tests for SL x exit time grid expander."""

from __future__ import annotations

from quant.portfolio.grid_expander import (
    EXIT_GRID,
    SL_GRID,
    expand_grid,
)


class TestExpandGrid:
    def test_default_grid_size(self) -> None:
        """Default grid: 7 SL x 4 EXIT = 28 variants minus 1 base = 27."""
        base_params = {"sl_pct": 0.5, "exit_time_et": 15, "tp_pct": 0.3}
        variants = expand_grid(base_exp_id=1, base_params=base_params)
        # 7 * 4 = 28 - 1 (base combo) = 27
        assert len(variants) == 27

    def test_excludes_base_combo(self) -> None:
        """The base SL + exit combo should not appear in variants."""
        base_params = {"sl_pct": 0.5, "exit_time_et": 15, "tp_pct": 0.3}
        variants = expand_grid(base_exp_id=1, base_params=base_params)
        for v in variants:
            assert not (v.sl_pct == 0.5 and v.exit_time_et == 15)

    def test_all_sl_values_present(self) -> None:
        """All SL grid values should appear in variants."""
        base_params = {"sl_pct": 0.5, "exit_time_et": 15}
        variants = expand_grid(base_exp_id=1, base_params=base_params)
        sl_values = {v.sl_pct for v in variants}
        assert sl_values == set(SL_GRID)

    def test_all_exit_values_present(self) -> None:
        """All exit grid values should appear in variants."""
        base_params = {"sl_pct": 0.5, "exit_time_et": 15}
        variants = expand_grid(base_exp_id=1, base_params=base_params)
        exit_values = {v.exit_time_et for v in variants}
        assert exit_values == set(EXIT_GRID)

    def test_custom_grid(self) -> None:
        """Custom SL and exit grids."""
        base_params = {"sl_pct": 0.5, "exit_time_et": 14}
        variants = expand_grid(
            base_exp_id=1,
            base_params=base_params,
            sl_grid=[0.3, 0.5],
            exit_grid=[14, 15],
        )
        # 2 * 2 = 4 - 1 base = 3
        assert len(variants) == 3

    def test_variant_preserves_base_params(self) -> None:
        """Each variant should keep all base params except SL and exit_time."""
        base_params = {
            "sl_pct": 0.5,
            "exit_time_et": 15,
            "tp_pct": 0.3,
            "level_type": "annual",
        }
        variants = expand_grid(base_exp_id=1, base_params=base_params)
        for v in variants:
            assert v.params["tp_pct"] == 0.3
            assert v.params["level_type"] == "annual"

    def test_base_exp_id_preserved(self) -> None:
        base_params = {"sl_pct": 0.5, "exit_time_et": 15}
        variants = expand_grid(base_exp_id=42, base_params=base_params)
        for v in variants:
            assert v.base_exp_id == 42

    def test_no_base_match_includes_all(self) -> None:
        """If base SL/exit not in grid, all combos are included."""
        base_params = {"sl_pct": 0.99, "exit_time_et": 11}
        variants = expand_grid(base_exp_id=1, base_params=base_params)
        # No base match removed: 7 * 4 = 28
        assert len(variants) == 28
