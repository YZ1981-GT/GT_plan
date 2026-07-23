"""B50 render 策略契约测试（spec: b50-workpaper-rework）。

- Property 1：render 输出恒不含 cells / html_data.cells（防 grid 兜底 shadow）。
- Property 2：oo_sheet_map 五个 key（program/tab1..tab4）恒存在且 oo_sheet_name 非空。
- 降级：DB 异常时仍返回 component_type 且不含 cells（不 500）。
"""

from __future__ import annotations

import asyncio
import types

import pytest

from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._b50_risk_assessment import (
    _OO_SHEET_MAP,
    render,
)


def test_b50_dispatch_registered():
    assert RENDERER_DISPATCH.get("b50-risk-assessment") is render


def test_oo_sheet_map_five_keys_nonempty():
    """Property 2：program + tab1..tab4 全在，oo_sheet_name 非空。"""
    assert set(_OO_SHEET_MAP) == {"program", "tab1", "tab2", "tab3", "tab4"}
    for key, entry in _OO_SHEET_MAP.items():
        assert entry["source_wp_code"], f"{key} 缺 source_wp_code"
        assert entry["oo_sheet_name"].strip(), f"{key} 的 oo_sheet_name 为空"


def test_oo_sheet_map_source_codes():
    """源子底稿 wp_code 精确对齐 B50 / B50-1..4。"""
    assert _OO_SHEET_MAP["program"]["source_wp_code"] == "B50"
    assert _OO_SHEET_MAP["tab1"]["source_wp_code"] == "B50-1"
    assert _OO_SHEET_MAP["tab2"]["source_wp_code"] == "B50-2"
    assert _OO_SHEET_MAP["tab3"]["source_wp_code"] == "B50-3"
    assert _OO_SHEET_MAP["tab4"]["source_wp_code"] == "B50-4"


class _FakeResult:
    def fetchone(self):
        return None


class _FakeDB:
    """execute 抛异常 → 触发降级路径。"""

    async def execute(self, *a, **kw):
        raise RuntimeError("db down")


class _FakeDBOk:
    async def execute(self, *a, **kw):
        return _FakeResult()


def _make_ctx(db):
    return types.SimpleNamespace(db=db, project_id="00000000-0000-0000-0000-000000000000", wp_code="B50")


def test_render_no_cells_on_db_error():
    """Property 1（降级）：DB 异常仍返回 dict 且无 cells / html_data。"""
    out = asyncio.run(render(_make_ctx(_FakeDB())))
    assert out is not None
    assert out["component_type"] == "b50-risk-assessment"
    assert "cells" not in out
    assert "html_data" not in out
    assert set(out["project_context"]["oo_sheet_map"]) == {"program", "tab1", "tab2", "tab3", "tab4"}


def test_render_no_cells_normal():
    """Property 1：正常路径同样不含 cells。"""
    out = asyncio.run(render(_make_ctx(_FakeDBOk())))
    assert out["component_type"] == "b50-risk-assessment"
    assert "cells" not in out
    assert out["project_context"]["program_available"] is True
