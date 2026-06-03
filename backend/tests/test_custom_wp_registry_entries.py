# Feature: custom-workpaper-formula-binding — 组②任务 4.2 验收
"""_build_custom_wp_cell_entries 从 parsed_data 生成 WP 域 AddressEntry。"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.services.address_registry import _build_custom_wp_cell_entries


class _FakeRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.anyio
async def test_build_custom_wp_cell_entries_formula_ref():
    project_id = uuid.uuid4()
    parsed = {
        "html_data": {
            "审定表": {
                "cells": {
                    "A5": "货币资金",
                    "B5": 1000,
                }
            }
        }
    }
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_FakeRows([(parsed, "CUST-01", "测试自定义底稿")])
    )

    entries = await _build_custom_wp_cell_entries(db, str(project_id), 2025)
    by_cell = {e.cell: e for e in entries}

    assert "B5" in by_cell
    assert by_cell["B5"].wp_code == "CUST-01"
    assert by_cell["B5"].domain == "wp"
    assert by_cell["B5"].formula_ref == "WP('CUST-01','B5')"
    assert "货币资金" in by_cell["B5"].label
    assert "测试自定义底稿" in by_cell["B5"].label


@pytest.mark.anyio
async def test_build_custom_wp_cell_entries_skips_bad_wp_code():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_FakeRows([(None, "", "无名")]))
    entries = await _build_custom_wp_cell_entries(db, str(uuid.uuid4()), 2025)
    assert entries == []


@pytest.mark.anyio
async def test_build_custom_wp_cell_entries_invalid_project_id():
    db = AsyncMock()
    entries = await _build_custom_wp_cell_entries(db, "not-a-uuid", 2025)
    assert entries == []
    db.execute.assert_not_called()
