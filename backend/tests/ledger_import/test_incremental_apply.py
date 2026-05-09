"""S6-15: apply_incremental 增量追加测试。"""
from __future__ import annotations

from backend.app.services.ledger_data_service import compute_incremental_diff


def test_diff_only_new_periods():
    existing = {1, 2, 3}
    file_periods = {4, 5}
    result = compute_incremental_diff(existing, file_periods)
    assert result["new"] == [4, 5]
    assert result["overlap"] == []
    assert result["only_existing"] == [1, 2, 3]


def test_diff_with_overlap():
    existing = {1, 2, 3}
    file_periods = {3, 4, 5}
    result = compute_incremental_diff(existing, file_periods)
    assert result["new"] == [4, 5]
    assert result["overlap"] == [3]
    assert result["only_existing"] == [1, 2]


def test_diff_fully_overlap():
    existing = {1, 2, 3}
    file_periods = {1, 2, 3}
    result = compute_incremental_diff(existing, file_periods)
    assert result["new"] == []
    assert result["overlap"] == [1, 2, 3]


def test_diff_empty_existing():
    existing: set[int] = set()
    file_periods = {1, 12}
    result = compute_incremental_diff(existing, file_periods)
    assert result["new"] == [1, 12]
    assert result["overlap"] == []
    assert result["only_existing"] == []


def test_diff_empty_file():
    existing = {1, 2}
    file_periods: set[int] = set()
    result = compute_incremental_diff(existing, file_periods)
    assert result["new"] == []
    assert result["overlap"] == []
    assert result["only_existing"] == [1, 2]
