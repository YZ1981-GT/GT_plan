"""权益变动表单元格编辑写入 eq_matrix 契约测试."""
from __future__ import annotations

from app.services.report_engine import (
    apply_equity_cell_edit_to_source_accounts,
    parse_equity_cell_column_key,
)


def test_parse_equity_cell_column_key_cy_py_prefix():
    assert parse_equity_cell_column_key("cy:paid_in_capital") == (
        "paid_in_capital",
        "current_year",
    )
    assert parse_equity_cell_column_key("py:oci") == ("oci", "prior_year")
    assert parse_equity_cell_column_key("capital_reserve", "prior_year") == (
        "capital_reserve",
        "prior_year",
    )


def test_apply_equity_cell_edit_writes_matrix_current_year():
    result = apply_equity_cell_edit_to_source_accounts(
        {"paid_in_capital": 999},
        "cy:paid_in_capital",
        1000.0,
    )
    assert result["eq_matrix"]["current_year"]["share_capital"] == 1000.0
    assert "paid_in_capital" not in result
    assert "share_capital" not in result


def test_apply_equity_cell_edit_writes_matrix_prior_year():
    result = apply_equity_cell_edit_to_source_accounts(
        None,
        "py:retained_earnings",
        500.0,
        year_key="prior_year",
    )
    assert result["eq_matrix"]["prior_year"]["retained_earnings"] == 500.0


def test_apply_equity_cell_edit_total_maps_to_total_equity():
    result = apply_equity_cell_edit_to_source_accounts(
        {"eq_matrix": {"current_year": {"share_capital": 100}}},
        "cy:total",
        8888.0,
    )
    assert result["eq_matrix"]["current_year"]["total_equity"] == 8888.0
    assert result["eq_matrix"]["current_year"]["share_capital"] == 100


def test_apply_equity_cell_edit_clears_value():
    result = apply_equity_cell_edit_to_source_accounts(
        {"eq_matrix": {"current_year": {"share_capital": 100, "total_equity": 200}}},
        "cy:paid_in_capital",
        None,
    )
    assert "share_capital" not in result["eq_matrix"]["current_year"]
    assert result["eq_matrix"]["current_year"]["total_equity"] == 200
