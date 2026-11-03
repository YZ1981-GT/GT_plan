"""行业误用收口（spec trim-followup-residual-findings-closure R1）。

平台没有项目级行业来源：``projects`` 无行业列、向导无行业字段。原先 H5 / H7 把质控分类码（A / A1~A8 / B / B1~B6 / C）
当行业比对 oil_gas / 农林牧渔（永不命中），M8 返回由不存在属性伪造的 ``industry = ""``，B1 / B1-3 / B1-4 / N2 / A17
把分类码写进「行业」。本文件钉住：任何分类都不再影响这些底稿的取数，行业栏 / 提示词行不再取分类码，
两个无调用方的 industry-check 端点已删除，H5 导入导出按请求体底稿 id 鉴权。

同族（读 ``RenderContext`` 没有的属性、被 except 吞成静默缺数）：H7 策略读 ``ctx.sheet_name``（整册 html_data 为 None）
且多包一层返回值，M4 / M7 快照读 ``ctx.workpaper_id`` 且查不存在的列；全目录 AST 守卫防再犯。
"""
from __future__ import annotations

import types
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings

CATEGORIES = ("A1", "C", None)


class _Result:
    def __init__(self, rows=None, one=None, scalar=None):
        self._rows = rows or []
        self._one = one
        self._scalar = scalar

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._one

    def first(self):
        return self._one

    def scalar_one_or_none(self):
        return self._scalar


def _ctx(execute, business_category=None):
    """真实 ``RenderContext``：读到它没有的属性当场 AttributeError（SimpleNamespace 曾掩盖 H7 的 ``ctx.sheet_name``）。"""
    from app.routers.wp_render_strategies._context import RenderContext

    db = MagicMock()
    db.execute = execute
    return RenderContext(
        db=db, project_id=uuid.uuid4(), wp_id=uuid.uuid4(), wp_code="", working_paper=None,
        classification=types.SimpleNamespace(sheet_name="", wp_code="", component_type=""),
        component_type="", sheet_html_data=None, sheet_schema=None, template_file_path=None,
        year=2025, business_category=business_category,
    )


def _fake_accounts(slot_keys, *, found: bool):
    slots = {
        key: types.SimpleNamespace(found=found, codes=["9999"] if found else [], standard_codes=["9999"] if found else [])
        for key in slot_keys
    }
    return types.SimpleNamespace(slots=slots, as_dict=lambda: {"slots": sorted(slots)}, codes_of=lambda _k: [])


# ── H5 ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("category", CATEGORIES)
async def test_h5_render_returns_saved_content_for_any_category(monkeypatch, category):
    """原先所有项目都返回 industry_error 且不带 responses_snapshot / tb_source_codes。"""
    monkeypatch.setattr(settings, "HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    from app.routers.wp_render_strategies import _h5_oil_gas_assets as h5

    async def execute(stmt, params=None):
        sql = str(stmt)
        if "checklist_responses" in sql:
            return _Result(rows=[types.SimpleNamespace(item_id="H5-2-rows", conclusion="", remark="[]")])
        if "FROM projects" in sql or "JOIN projects" in sql:
            row = types.SimpleNamespace(client_name="客户", audit_year=2025, business_category=category,
                                        applicable_standards=None)
            return _Result(one=row)
        return _Result()

    monkeypatch.setattr(
        h5, "_fetch_tb_data",
        AsyncMock(return_value=({}, _fake_accounts(h5.H5_SLOT_KEY_PREFIX, found=False), False)),
    )
    out = await h5.render(_ctx(execute, category))

    assert "industry_error" not in out and "industry" not in out
    assert out["responses_snapshot"] == {"H5-2-rows": {"conclusion": "", "remark": "[]"}}
    assert out["tb_source_codes"] == {"slots": sorted(h5.H5_SLOT_KEY_PREFIX)}
    assert out["accounts_found"] is False
    assert out["account_codes"] == ["1631"]  # 兜底码不代表找到了科目


@pytest.mark.asyncio
@pytest.mark.parametrize(("tb_found", "expected"), [(False, False), (True, True), (None, None)])
async def test_h5_accounts_found_uses_actual_tb_result_not_resolved_codes(monkeypatch, tb_found, expected):
    """解析器有 fallback 码不等于 active TB 有行；查询失败保持未知，不误报缺科目。"""
    monkeypatch.setattr(settings, "HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    from app.routers.wp_render_strategies import _h5_oil_gas_assets as h5

    async def execute(stmt, params=None):
        return _Result()

    monkeypatch.setattr(
        h5, "_fetch_tb_data",
        AsyncMock(return_value=({}, _fake_accounts(h5.H5_SLOT_KEY_PREFIX, found=True), tb_found)),
    )
    out = await h5.render(_ctx(execute, "A1"))
    assert out["accounts_found"] is expected
    assert out["account_codes"] == ["9999"]


# ── H7 ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("category", CATEGORIES)
async def test_h7_four_table_enhancement_runs_for_any_category(monkeypatch, category):
    """原先 is_applicable 恒 False（分类码永远不在农林牧渔里）⇒ 四表增强永远不跑。"""
    monkeypatch.setattr(settings, "HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    from app.routers.wp_render_strategies import _h7_biological_assets as h7
    from app.services.d_cycle_extraction import prefill, tier_a_seed

    async def execute(stmt, params=None):
        return _Result(one=types.SimpleNamespace(business_category=category))

    monkeypatch.setattr(
        h7, "_fetch_tb_data",
        AsyncMock(return_value=({}, _fake_accounts(h7.H7_SLOT_KEY_PREFIX, found=True), False)),
    )
    monkeypatch.setattr(prefill, "build_d_adjudication_prefill", AsyncMock(return_value=[{"row": 1}]))
    monkeypatch.setattr(tier_a_seed, "seed_tier_a_reconciliation", AsyncMock(return_value=None))
    html = await h7.render_h7_biological_assets(_ctx(execute, category))

    assert html["component_type"] == "h7-biological-assets" and "sheets" not in html  # 返回值即本页 html_data
    assert "is_applicable" not in html and "industry" not in html
    assert html["accounts_found"] is False  # 有查询码但 active TB 零行；四表增强仍按查询码尝试取数
    assert html["hi_extraction_enabled"] is True
    assert html["adjudication_segment_prefill"]["segments"]


@pytest.mark.asyncio
async def test_h7_accounts_not_found_reported(monkeypatch):
    monkeypatch.setattr(settings, "HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    from app.routers.wp_render_strategies import _h7_biological_assets as h7

    async def execute(stmt, params=None):
        return _Result()

    monkeypatch.setattr(
        h7, "_fetch_tb_data",
        AsyncMock(return_value=({}, _fake_accounts(h7.H7_SLOT_KEY_PREFIX, found=False), False)),
    )
    html = await h7.render_h7_biological_assets(_ctx(execute, "C"))
    assert html["accounts_found"] is False
    assert html["account_codes"] == ["1621"]
    assert html["measurement_model"] == "cost"  # 没存过


def test_accounts_found_requires_actual_tb_row_with_strict_prefix_boundary():
    """fallback 解析码只是查询口径；只有 active TB 实际行才算找到，零余额行也算。"""
    from app.services.four_table.semantic_account_resolver import has_resolved_tb_rows

    accounts = _fake_accounts(("gross", "provision"), found=True)
    assert has_resolved_tb_rows(accounts, []) is False
    assert has_resolved_tb_rows(accounts, [{"account_code": "9999", "closing_balance": 0}]) is True
    assert has_resolved_tb_rows(accounts, [{"account_code": "9999.01", "closing_balance": 0}]) is True
    assert has_resolved_tb_rows(accounts, [{"account_code": "99990", "closing_balance": 1}]) is False


def test_accounts_found_can_be_scoped_to_one_semantic_slot():
    from app.services.four_table.semantic_account_resolver import has_resolved_tb_rows

    slots = {
        "gross": types.SimpleNamespace(codes=["4102"]),
        "provision": types.SimpleNamespace(codes=["4103"]),
    }
    accounts = types.SimpleNamespace(slots=slots)
    rows = [{"account_code": "4103", "closing_balance": 1}]
    assert has_resolved_tb_rows(accounts, rows) is True
    assert has_resolved_tb_rows(accounts, rows, slot_keys=("gross",)) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [
    "app.routers.wp_render_strategies._h5_oil_gas_assets",
    "app.routers.wp_render_strategies._h7_biological_assets",
])
@pytest.mark.parametrize(("query_fails", "expected"), [(False, False), (True, None)])
async def test_h5_h7_accounts_found_distinguishes_empty_tb_from_query_failure(
    monkeypatch, module, query_fails, expected,
):
    """空查询是确定缺少；查询异常是未知。两者都不能由 fallback 码改写成 True。"""
    import importlib

    import sqlalchemy as sa

    mod = importlib.import_module(module)
    slot_keys = (
        mod.H5_SLOT_KEY_PREFIX
        if module.endswith("_h5_oil_gas_assets")
        else mod.H7_SLOT_KEY_PREFIX
    )
    accounts = _fake_accounts(slot_keys, found=True)
    monkeypatch.setattr(mod, "resolve_semantic_accounts", AsyncMock(return_value=accounts))
    monkeypatch.setattr(mod, "get_active_filter", AsyncMock(return_value=sa.true()))

    async def execute(stmt, params=None):
        if query_fails:
            raise RuntimeError("boom")
        return _Result()

    _values, _accounts, found = await mod._fetch_tb_data(_ctx(execute, "A1"))
    assert found is expected


def test_accounts_found_writers_do_not_cast_resolved_codes_to_bool():
    """三处业务字段只接受实际 TB 行判定结果，不再把 fallback 查询码当存在证据。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "routers" / "wp_render_strategies"
    files = ["_h5_oil_gas_assets.py", "_h7_biological_assets.py", "_m8_general_risk_reserve.py"]
    for name in files:
        source = (root / name).read_text(encoding="utf-8")
        assert '"accounts_found": accounts_found' in source, name
        assert not __import__("re").search(r'["\']accounts_found["\']\s*:\s*bool\(', source), name


@pytest.mark.asyncio
@pytest.mark.parametrize(("row", "expected"), [
    (types.SimpleNamespace(remark="fair_value", conclusion=None), "fair_value"),  # 宿主 PUT 写在 remark
    (types.SimpleNamespace(remark=None, conclusion="fair_value"), "fair_value"),
    (types.SimpleNamespace(remark="成本", conclusion=None), "cost"),
    (None, "cost"),
])
async def test_h7_measurement_model_comes_from_saved_response(monkeypatch, row, expected):
    """原先写死 cost：接通后每次重载都会把用户选的公允价值模式改回成本模式。"""
    monkeypatch.setattr(settings, "HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    from app.routers.wp_render_strategies import _h7_biological_assets as h7

    seen: list[tuple[str, dict]] = []

    async def execute(stmt, params=None):
        seen.append((str(stmt), params or {}))
        return _Result(one=row)

    monkeypatch.setattr(
        h7, "_fetch_tb_data",
        AsyncMock(return_value=({}, _fake_accounts(h7.H7_SLOT_KEY_PREFIX, found=False), False)),
    )
    ctx = _ctx(execute, "C")
    html = await h7.render_h7_biological_assets(ctx)
    assert html["measurement_model"] == expected
    sql, params = next((s, p) for s, p in seen if "H7-measurement-model" in s)
    assert params == {"wp_id": str(ctx.wp_id)}
    ctx.db.begin_nested.assert_called_once()  # 保存点隔离


@pytest.mark.asyncio
async def test_h7_measurement_model_read_failure_falls_back_to_cost(monkeypatch):
    monkeypatch.setattr(settings, "HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    from app.routers.wp_render_strategies import _h7_biological_assets as h7

    async def execute(stmt, params=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        h7, "_fetch_tb_data",
        AsyncMock(return_value=({}, _fake_accounts(h7.H7_SLOT_KEY_PREFIX, found=False), False)),
    )
    assert (await h7.render_h7_biological_assets(_ctx(execute, "C")))["measurement_model"] == "cost"


# ── M4 / M7：快照读法 ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(("module", "prefix"), [
    ("app.routers.wp_render_strategies._m4_capital_reserve", "M4"),
    ("app.routers.wp_render_strategies._m7_special_reserve", "M7"),
])
async def test_m4_m7_snapshot_reads_wp_id_and_existing_columns(monkeypatch, module, prefix):
    """原先读 RenderContext 没有的 ``workpaper_id``、查不存在的 evidence / status 列 ⇒ 快照恒空、公式校验从不跑。"""
    import importlib

    mod = importlib.import_module(module)
    seen: list[tuple[str, dict]] = []
    rows = [
        types.SimpleNamespace(item_id=f"{prefix}-1-adjudicated-amount", conclusion="150", remark=None),
        types.SimpleNamespace(item_id=f"{prefix}-1-row-a", conclusion='{"begin": 100, "credit": 50, "debit": 0, "end_balance": 120}', remark=None),
    ]

    async def execute(stmt, params=None):
        sql = str(stmt)
        seen.append((sql, params or {}))
        if "checklist_responses" in sql:
            return _Result(rows=rows)
        return _Result()

    monkeypatch.setattr(mod, "_fetch_tb_data", AsyncMock(return_value={}))
    monkeypatch.setattr(mod, "resolve_report_line_account_codes", AsyncMock(return_value=["4002"]))
    ctx = _ctx(execute, "C")
    out = await mod.render(ctx)

    sql, params = next((s, p) for s, p in seen if "checklist_responses" in s)
    assert params == {"wid": str(ctx.wp_id)}
    assert "evidence" not in sql and "status" not in sql
    assert out["responses_snapshot"][f"{prefix}-1-row-a"]["conclusion"].startswith("{")
    assert out["adjudicated_amount"] == 150.0
    assert [e["row_key"] for e in out["formula_errors"]] == [f"{prefix}-1-row-a"]  # 期末 120 ≠ 100 + 50 - 0
    ctx.db.begin_nested.assert_called()  # 保存点隔离


# ── 渲染策略只读 RenderContext 真有的字段 ──────────────────────────────────────


def _unknown_render_context_reads(source: str, fields: set[str]) -> list[str]:
    import ast

    found: list[str] = []
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names = {
            a.arg for a in fn.args.args + fn.args.kwonlyargs
            if (a.annotation is not None and "RenderContext" in ast.unparse(a.annotation))
            or (a.annotation is None and a.arg == "ctx")
        }
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in names:
                if node.attr not in fields:
                    found.append(f"{node.attr}@L{node.lineno}")
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"getattr", "hasattr"}
                    and len(node.args) >= 2 and isinstance(node.args[0], ast.Name) and node.args[0].id in names
                    and isinstance(node.args[1], ast.Constant) and node.args[1].value not in fields):
                found.append(f"getattr:{node.args[1].value}@L{node.lineno}")
    return found


def test_render_strategies_only_read_render_context_fields():
    """读不存在的属性会被策略或路由的 except 吞掉，页面只是静默缺数（H7 整册、M4 / M7 快照都是这样坏了几个月）。"""
    import dataclasses
    from pathlib import Path

    from app.routers.wp_render_strategies import _context

    fields = {f.name for f in dataclasses.fields(_context.RenderContext)}
    strategy_dir = Path(_context.__file__).parent
    scanned = sorted(strategy_dir.glob("*.py"))
    assert len(scanned) > 100  # 扫描面非空
    offenders = {
        path.name: bad for path in scanned
        if (bad := _unknown_render_context_reads(path.read_text(encoding="utf-8"), fields))
    }
    assert offenders == {}

    # 扫描器自检：H7 / M4 原来的写法必须被认出来
    sample = (
        "async def render(ctx: RenderContext):\n    return ctx.sheet_name\n"
        "async def _helper(ctx):\n    return getattr(ctx, 'workpaper_id', None)\n"
    )
    assert _unknown_render_context_reads(sample, fields) == ["sheet_name@L2", "getattr:workpaper_id@L4"]


# ── M8 ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(("gross", "tb_rows", "expected"), [
    ([], [], False),
    (["4102"], [], False),  # 有解析码但 active TB 零行
    (["4102"], [types.SimpleNamespace(
        account_code="4102", begin_balance=0, debit_amount=0, credit_amount=0, end_balance=0,
    )], True),  # 金额全零的真实行仍表示科目存在
])
async def test_m8_project_info_has_no_fake_industry_and_found_uses_tb_rows(
    monkeypatch, gross, tb_rows, expected,
):
    """原先伪行业让整页拦截；随后 accounts_found 又把解析码误当实际 TB 行。"""
    import sqlalchemy as sa

    from app.routers.wp_render_strategies import _m8_general_risk_reserve as m8

    slots = {"gross": types.SimpleNamespace(codes=list(gross))}
    accounts = types.SimpleNamespace(
        slots=slots,
        codes_of=lambda _k: list(gross),
        as_dict=lambda: {"gross": list(gross)},
    )
    monkeypatch.setattr(m8, "resolve_semantic_accounts", AsyncMock(return_value=accounts))
    monkeypatch.setattr(m8, "get_active_filter", AsyncMock(return_value=sa.true()))

    tb_statements = []

    async def execute(stmt, params=None):
        if "tb_balance" in str(stmt).lower():
            tb_statements.append(stmt)
            return _Result(rows=tb_rows)
        return _Result(scalar="某银行股份有限公司")

    out = await m8.render(_ctx(execute, "A1"))
    assert out["project_info"] == {"client_name": "某银行股份有限公司"}
    assert out["accounts_found"] is expected
    assert out["account_codes"] == gross
    assert bool(out["tb_snapshot"]) is bool(tb_rows)
    if gross:
        params = tb_statements[0].compile().params
        assert "4102" in params.values() and "4102." in params.values()  # 等值或点号子科目


@pytest.mark.asyncio
async def test_m8_tb_query_failure_keeps_accounts_found_unknown(monkeypatch):
    import sqlalchemy as sa

    from app.routers.wp_render_strategies import _m8_general_risk_reserve as m8

    accounts = types.SimpleNamespace(
        slots={"gross": types.SimpleNamespace(codes=["4102"])},
        codes_of=lambda _k: ["4102"],
        as_dict=lambda: {},
    )
    monkeypatch.setattr(m8, "resolve_semantic_accounts", AsyncMock(return_value=accounts))
    monkeypatch.setattr(m8, "get_active_filter", AsyncMock(return_value=sa.true()))

    async def execute(stmt, params=None):
        if "tb_balance" in str(stmt).lower():
            raise RuntimeError("boom")
        return _Result(scalar="客户")

    assert (await m8.render(_ctx(execute, "A1")))["accounts_found"] is None


# ── 删除的端点与 service 函数 ────────────────────────────────────────────────


def test_industry_check_routes_and_services_removed():
    from app.routers import h5_oil_gas_assets, h7_biological_assets
    from app.services import h5_oil_gas_assets_service, h7_biological_assets_service

    paths = {route.path for route in h5_oil_gas_assets.router.routes} | {
        route.path for route in h7_biological_assets.router.routes}
    assert not any(p.endswith("/industry-check") for p in paths), paths
    assert "/api/h5/export-data" in paths and "/api/workpapers/{wp_id}/h7/export-data" in paths  # 扫描面非空
    assert not hasattr(h5_oil_gas_assets_service, "check_industry_applicability")
    assert not hasattr(h7_biological_assets_service, "check_industry_applicability")


# ── H5 导入导出：请求体底稿 id 鉴权 ───────────────────────────────────────────


def _h5_client(monkeypatch, *, read=None, edit=None):
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import h5_oil_gas_assets as h5r

    calls: dict[str, list] = {"read": [], "edit": [], "load": [], "save": []}

    async def fake_read(db, user, wp_id):
        calls["read"].append(wp_id)
        if read:
            raise read
        return uuid.uuid4()

    async def fake_edit(db, user, wp_id):
        calls["edit"].append(wp_id)
        if edit:
            raise edit
        return uuid.uuid4()

    async def fake_load(db, wp_id, item_id):
        calls["load"].append((wp_id, item_id))
        return []

    async def fake_save(db, wp_id, item_id, rows):
        calls["save"].append((wp_id, item_id))

    monkeypatch.setattr(h5r, "authorize_wp_read", fake_read)
    monkeypatch.setattr(h5r, "authorize_wp_edit", fake_edit)
    monkeypatch.setattr(h5r, "_load_rows_from_db", fake_load)
    monkeypatch.setattr(h5r, "_save_rows_to_db", fake_save)
    app = FastAPI()
    app.include_router(h5r.router)
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: types.SimpleNamespace(id=uuid.uuid4())
    return TestClient(app), calls


def test_h5_export_data_requires_wp_read(monkeypatch):
    wp = uuid.uuid4()
    client, calls = _h5_client(monkeypatch, read=HTTPException(status_code=403, detail="无权"))
    assert client.post("/api/h5/export-data", json={"wpId": str(wp), "sheet": "H5-2"}).status_code == 403
    assert calls["read"] == [wp] and calls["load"] == []  # 先鉴权，后读正文

    client, calls = _h5_client(monkeypatch)
    resp = client.post("/api/h5/export-data", json={"wpId": str(wp), "sheet": "H5-2"})
    assert resp.status_code == 200
    assert calls["load"] == [(str(wp), "H5-2-rows")]


def test_h5_export_data_rejects_non_uuid_before_lookup(monkeypatch):
    client, calls = _h5_client(monkeypatch)
    assert client.post("/api/h5/export-data", json={"wpId": "1 OR 1=1", "sheet": "H5-2"}).status_code == 404
    assert calls["read"] == [] and calls["load"] == []


def test_h5_import_data_requires_wp_edit(monkeypatch):
    import io

    from openpyxl import Workbook

    buf = io.BytesIO()
    wb = Workbook()
    wb.active.append(["资产名称"])
    wb.active.append(["井 1"])
    wb.save(buf)
    wp = uuid.uuid4()
    files = {"file": ("h5.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    client, calls = _h5_client(monkeypatch, edit=HTTPException(status_code=403, detail="无底稿编辑权限"))
    resp = client.post("/api/h5/import-data", data={"wp_id": str(wp), "sheet": "H5-2"}, files=files)
    assert resp.status_code == 403
    assert calls["edit"] == [wp] and calls["save"] == []

    client, calls = _h5_client(monkeypatch)
    resp = client.post("/api/h5/import-data", data={"wp_id": str(wp), "sheet": "H5-2"}, files=files)
    assert resp.status_code == 200, resp.text
    assert calls["save"] == [(str(wp), "H5-2-rows")]


# ── 行业栏 / 提示词不再取分类码 ───────────────────────────────────────────────


def _capturing_execute(row):
    seen: list[str] = []

    async def execute(stmt, params=None):
        seen.append(str(stmt))
        return _Result(one=row, rows=[], scalar=row)

    return execute, seen


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [
    "app.routers.wp_render_strategies._b1_risk_assessment",
    "app.routers.wp_render_strategies._b14_due_diligence",
    "app.routers.wp_render_strategies._b1_3_evaluation",
])
async def test_b_cycle_project_context_industry_stays_empty(module):
    import importlib

    mod = importlib.import_module(module)
    row = types.SimpleNamespace(client_name="客户", audit_year=2025, business_category="A1")
    execute, seen = _capturing_execute(row)
    db = MagicMock()
    db.execute = execute
    ctx = await mod._load_project_context(uuid.uuid4(), db)
    assert ctx["industry"] == ""
    assert ctx["client_name"] == "客户"
    assert not any("business_category" in sql for sql in seen)


@pytest.mark.asyncio
async def test_b13_render_does_not_prefill_industry_with_category():
    from app.routers.wp_render_strategies import _b1_3_evaluation as b13

    row = types.SimpleNamespace(client_name="客户", audit_year=2025, business_category="A1", conclusion=None)

    async def execute(stmt, params=None):
        sql = str(stmt)
        if "FROM projects" in sql:
            return _Result(one=row)
        return _Result()

    out = await b13.render(_ctx(execute, "A1"))
    assert out["values"]["basic-client_name"]["value"] == "客户"
    assert out["values"].get("basic-industry", {}).get("value", "") == ""


def test_b14_ai_prompt_drops_empty_industry_line():
    from app.routers.b14_ai_generate import _render_system_prompt

    base = {"client_name": "客户", "audit_period": "2025年度", "firm_name": "致同"}
    prompt = _render_system_prompt("序言", {**base, "industry": ""})
    assert "所属行业" not in prompt and "客户" in prompt and "2025年度" in prompt
    assert "- 所属行业：制造业" in _render_system_prompt("序言", {**base, "industry": "制造业"})


@pytest.mark.asyncio
async def test_b14_ai_project_context_does_not_read_category():
    from app.routers.b14_ai_generate import _load_project_context

    execute, seen = _capturing_execute(types.SimpleNamespace(client_name="客户", audit_year=2025, business_category="A1"))
    db = MagicMock()
    db.execute = execute
    ctx = await _load_project_context(db, uuid.uuid4())
    assert ctx["industry"] == "" and ctx["client_name"] == "客户"
    assert not any("business_category" in sql for sql in seen)


@pytest.mark.asyncio
async def test_n2_ai_context_has_no_industry_line():
    from app.routers.n2_taxes_payable import _build_ai_user_prompt, _load_project_context

    execute, seen = _capturing_execute(types.SimpleNamespace(client_name="客户", audit_year=2025, industry="A1"))
    db = MagicMock()
    db.execute = execute
    ctx = await _load_project_context(str(uuid.uuid4()), db)
    assert "industry" not in ctx
    assert not any("business_category" in sql for sql in seen)
    prompt = _build_ai_user_prompt("summary", "", {}, ctx)
    assert "行业" not in prompt and "客户" in prompt


@pytest.mark.asyncio
async def test_a17_context_labels_category_and_rag_query_is_title(monkeypatch):
    from app.services import a17_llm_service as a17

    project = types.SimpleNamespace(name="项目", client_name="客户", audit_period_end="2025-12-31", business_category="A1")
    execute, _seen = _capturing_execute(project)
    db = MagicMock()
    db.execute = execute
    text = await a17._get_project_context(db, uuid.uuid4())
    assert "质控业务分类: A1" in text
    assert "行业" not in text

    captured: list[str] = []

    async def fake_rag(_db, _pid, query, **_kw):
        captured.append(query)
        return ""

    from app.services import llm_client

    monkeypatch.setattr(settings, "WP_AI_SERVICE_ENABLED", True)
    monkeypatch.setattr(a17, "_get_project_context", AsyncMock(return_value=text))
    monkeypatch.setattr(a17, "_get_chapter_def", lambda _cid: {"title": "审计约定范围", "guidance": ""})
    monkeypatch.setattr(a17, "_retrieve_rag_context", fake_rag)
    monkeypatch.setattr(llm_client, "chat_completion", AsyncMock(return_value="草稿"))
    result = await a17.A17LlmService().generate_chapter_draft(db, uuid.uuid4(), "A17-1-ch01")
    assert result.get("draft") == "草稿"
    assert captured == ["审计约定范围"]  # 原先拼上下文第 3 行（截止日）


# ── 提示词 / 上下文不把分类码标成「行业」 ───────────────────────────────────────


def _category_labelled_as_industry(source: str) -> list[str]:
    """f-string 里「行业」文字 + 插值 business_category，或 format 模板「行业…{business_category}」。"""
    import ast
    import re

    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.JoinedStr):
            text = "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
            exprs = " ".join(ast.unparse(v.value) for v in node.values if isinstance(v, ast.FormattedValue))
            if "行业" in text and "business_category" in exprs:
                found.append(f"L{node.lineno}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.search(r"行业[^{\n]{0,6}\{business_category\}", node.value):
                found.append(f"L{node.lineno}")
    return found


def test_no_prompt_labels_business_category_as_industry():
    """22 个 H / I / K 循环 AI 生成模块与底稿对话上下文曾把分类码（A1 / C …）写成「行业：A1」。"""
    from pathlib import Path

    import app

    app_dir = Path(app.__file__).parent
    scanned = sorted(app_dir.rglob("*.py"))
    assert len(scanned) > 1000  # 扫描面非空
    offenders = {
        path.relative_to(app_dir).as_posix(): bad for path in scanned
        if "行业" in (text := path.read_text(encoding="utf-8")) and (bad := _category_labelled_as_industry(text))
    }
    assert offenders == {}

    sample = (
        "a = f\"行业：{project_context['business_category']}\"\n"
        "b = '- 行业类别：{business_category}'\n"
        "c = f\"质控业务分类：{project_context['business_category']}\"\n"
    )
    assert _category_labelled_as_industry(sample) == ["L1", "L2"]


def test_wp_chat_system_prompt_labels_category():
    from app.services.context_injector import ContextInjector, WpChatContext

    prompt = ContextInjector().build_system_prompt(WpChatContext(
        wp_code="H1-1", wp_name="固定资产审定表", component_type="audit-sheet", client_name="客户",
        audit_period="2025-01-01 至 2025-12-31", business_category="A1", guidance_text="", filled_data_summary="",
    ))
    assert "质控业务分类：A1" in prompt and "行业" not in prompt


def test_h1_ai_prompt_labels_category():
    from app.routers.wp_render_strategies import _h1_ai_generate as h1

    prompt = h1._build_user_prompt("conclusion", "", {}, {"client_name": "客户", "business_category": "A1"})
    assert "质控业务分类：A1" in prompt and "行业：" not in prompt
