"""底稿可编辑公式保存端点的函数门（spec formula-governance-coverage-closure R6.1 / R6.4）与求值回执（R6.3）。

端点级真发请求（权限世界 tests/authz_world.py）：R6 补齐的函数过函数门、进入保存；序时账 / PREV 三参仍 422，
且一次保存调用都没有、逐项给出原因、提示里列出可编辑公式支持的函数（与函数支持矩阵同源）。
求值有错（取不到数）时：格子留空、只回原因、不回 0（R5 真库走查发现原先照写 0 并提示「公式已保存」）。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.schema import CreateTable

import app.routers.wp_formula as wp_formula_router
from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex
from tests.authz_world import TARGET_PROJECT_ID, WORLD_TABLE_NAMES, sqlite_world

PID = TARGET_PROJECT_ID
WP = uuid.UUID("7c2e9a41-3d5b-4f60-8e17-9b0a4c6d2f33")
_EXTRA = (WpIndex.__table__, WorkingPaper.__table__, WpFormula.__table__)
_URL = f"/api/workpapers/{WP}/formulas"
_ISSUE = [{"ref": "X", "uri": "x://", "status": "not_found", "reason": "not_found", "message": "桩：悬空"}]


def _create_extra_tables(session) -> None:
    conn = session.connection()
    known = WORLD_TABLE_NAMES | {t.name for t in _EXTRA}
    for table in _EXTRA:
        fks = [fk for fk in table.foreign_key_constraints
               if {e.target_fullname.split(".")[-2] for e in fk.elements} <= known]
        conn.execute(CreateTable(table, include_foreign_key_constraints=fks))


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch) as w:
        await w.db.run_sync(_create_extra_tables)
        idx = WpIndex(id=uuid.uuid4(), project_id=PID, wp_code="E1", wp_name="货币资金")
        w.db.add(idx)
        await w.db.flush()
        w.db.add(WorkingPaper(id=WP, project_id=PID, wp_index_id=idx.id, file_path="x.xlsx", source_type="template"))
        await w.db.flush()
        yield w


def _handler_app():
    """只挂处理函数这一层：生产注册另有 router 级底稿可见性门（拒绝时会写真库安全审计外发表，
    且与本用例观测的函数门无关）；处理函数自身的项目编辑级判定照常执行（edit 级成员真实通过）。"""
    from fastapi import FastAPI

    api = FastAPI()
    api.include_router(wp_formula_router.router)
    return api


async def _put(world, expression: str):
    identity = await world.identity("edit_member")
    async with world.client_for_app(_handler_app(), user=identity.user) as client:
        return await client.put(_URL, json={"sheet_name": "审定表E1-1", "target_cell": "B5",
                                            "expression": expression, "year": 2025})


@pytest.mark.parametrize("expression", [
    "ROW('BS-002') + SUM_ROW('BS-002','BS-003') + REPORT('BS-002','期初')",
    "NOTE('八、1','合计','期末余额') + PREV('1001','期末余额') + PREV(TB('1001','年初余额'))",
    "AUX('1122','客户','甲公司','期末余额') + AUX('1122','客户','期末') + ADJ('1122','aje_net')",
])
async def test_r6_functions_pass_the_gate_and_reach_save(world, expression):
    stub = world.stub(wp_formula_router.wp_formula_service, "save", returns=(None, _ISSUE))
    resp = await _put(world, expression)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["error_code"] != "FORMULA_UNSUPPORTED_FUNCTION", detail  # 422 来自桩的悬空引用，不是函数门
    assert stub.count == 1


@pytest.mark.parametrize(("expression", "fn", "reason"), [
    ("LEDGER('6001','借','全年')", "LEDGER", "序时账取数由底稿预填充承担"),
    ("TB('1001','期末余额') + PREV('D2','审定表D2-1','审定数')", "PREV", "上年底稿取数"),
    ("TB_AUX('1121','客户','期末余额')", "TB_AUX", "AUX('科目','辅助类型','列')"),
])
async def test_unsupported_functions_are_rejected_with_reasons_before_save(world, expression, fn, reason):
    stub = world.stub(wp_formula_router.wp_formula_service, "save", returns=(None, []))
    resp = await _put(world, expression)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["error_code"] == "FORMULA_UNSUPPORTED_FUNCTION"
    assert detail["unsupported_functions"] == [fn]
    assert [i["function"] for i in detail["issues"]] == [fn] and reason in detail["issues"][0]["reason"]
    assert "可编辑公式支持 TB/SUM_TB/ROW/SUM_ROW/REPORT/NOTE/WP/PREV/AUX/ADJ" in detail["message"]
    assert stub.count == 0  # 被拦下的请求一次保存都没有


# ── R6.3 求值回执：取不到数时格子留空、只回原因 ────────────────────────────────────────


def _saved_row() -> WpFormula:
    return WpFormula(id=uuid.uuid4(), project_id=PID, wp_id=WP, sheet_name="审定表E1-1", target_cell="B5",
                     expression="x", formula_type="auto_calc")


async def _cell(world, cell: str = "B5"):
    wp = await world.db.get(WorkingPaper, WP)
    await world.db.refresh(wp)
    cells = (((wp.parsed_data or {}).get("html_data") or {}).get("审定表E1-1") or {}).get("cells") or {}
    return cell in cells, cells.get(cell)


async def test_eval_gap_clears_cell_and_returns_reason_not_zero(world):
    """求值器回「上年无数据」：响应只有 eval_warnings、没有 evaluated_value；格子写成空（覆盖旧值），不是 0。"""
    wp = await world.db.get(WorkingPaper, WP)
    wp.parsed_data = {"html_data": {"审定表E1-1": {"cells": {"B5": {"value": 123, "v": 123}}, "max_row": 5,
                                                     "max_col": 2}}}
    await world.db.flush()
    world.stub(wp_formula_router.wp_formula_service, "save", returns=(_saved_row(), []))
    reason = "PREV('1001','期末余额')：上年（2024）试算表无数据"
    evaluator = world.stub(wp_formula_router, "evaluate_wp_formula_expression", returns=(Decimal("0"), [reason]))
    resp = await _put(world, "PREV('1001','期末余额')")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["eval_warnings"] == [reason]
    assert "evaluated_value" not in body, "取不到数不回 0（R6.3）"
    assert evaluator.count == 1
    assert await _cell(world) == (True, {"value": None, "v": None}), "格子留空（旧值 123 被清掉），不写 0"


async def test_eval_success_writes_value_and_returns_it(world):
    """对照：求值成功照常写格、回值（不受留空逻辑影响）。"""
    world.stub(wp_formula_router.wp_formula_service, "save", returns=(_saved_row(), []))
    world.stub(wp_formula_router, "evaluate_wp_formula_expression", returns=(Decimal("300.00"), []))
    resp = await _put(world, "ROW('BS-002')")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["evaluated_value"] == "300.00" and "eval_warnings" not in body
    assert await _cell(world) == (True, 300)
