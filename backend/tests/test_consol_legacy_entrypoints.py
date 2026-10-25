"""遗留入口处置（spec consol-elimination-single-source-push 任务 8，需求 9.1 / 9.3）。

- ``POST /api/consol-note-sections/fill-tb/...`` 与 ``POST /api/report-config/batch-update`` 已删除（真发请求 ⇒ 不存在），
  全仓前端不再引用（源码扫描钉死，防回潮）；
- ``POST /api/report-config/drill-down`` 改为企业树子节点贡献：直接下级之和 = 末级之和 = 合并报表该行；
  不再读 ``consol_worksheet_data['info']``、不按持股比例估算；项目级鉴权（体内项目，非成员 403）。
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio

import tests.conftest  # noqa: F401
from app.models.base import PermissionLevel, UserRole
from app.models.consolidation_models import EliminationEntryType
from tests.test_consol_push import (  # noqa: F401
    Y,
    _entry,
    _persist,
    _User,
    client_for,
    db,
    factory,
    group,
)

D = Decimal
FRONTEND_SRC = Path(__file__).resolve().parents[2] / "audit-platform" / "frontend" / "src"


@pytest_asyncio.fixture
async def legacy_client(client_for):
    from app.routers.consol_note_sections import router as ns_router
    from app.routers.report_config import router as rc_router

    def make(user):
        client = client_for(user)
        app = client._transport.app  # noqa: SLF001
        if not any(getattr(r, "path", "").startswith("/api/report-config") for r in app.routes):
            app.include_router(rc_router)
            app.include_router(ns_router)
        return client

    return make


def test_frontend_no_longer_calls_removed_endpoints():
    pattern = re.compile(r"consol-note-sections/fill-tb|report-config/batch-update|reportConfig\.batchUpdate|P_rc\.batchUpdate")
    hits = [
        f"{p.relative_to(FRONTEND_SRC)}:{text[:m.start()].count(chr(10)) + 1}"
        for p in FRONTEND_SRC.rglob("*") if p.suffix in (".ts", ".vue") and "node_modules" not in p.parts
        for text in [p.read_text(encoding="utf-8", errors="replace")]
        for m in pattern.finditer(text)
    ]
    # 试算页（任务 11 重写为只读 report-trial）曾是最后的调用方；重写后全仓零引用，不留白名单
    assert hits == [], hits


def test_trial_tab_reads_report_trial_only():
    """试算页只读计算结果：不再读写 consol_tb_* JSON、不再「提取填充 / 保存 / 生成报表 / 提取上年数」、
    不在前端按「借减贷」重算合并审定数（需求 4.2 / 4.3、design §十一）。"""
    text = (FRONTEND_SRC / "components" / "consolidation" / "ConsolTrialBalanceTab.vue").read_text(encoding="utf-8")
    assert "getConsolReportTrial" in text
    for gone in ("consol_tb_", "saveWorksheetData", "loadWorksheetData", "fill-tb", "batch-update",
                 "prior-year", "recalcTbAudited", "equity_dr"):
        assert gone not in text, gone


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_removed_routes_are_gone(self, db, group, legacy_client):
        admin = _User(UserRole.admin)
        gid = str(group["G"].id)
        async with legacy_client(admin) as c:
            gone = await c.post(f"/api/consol-note-sections/fill-tb/{gid}/{Y}", json={})
            assert gone.status_code in (404, 405), gone.status_code
            gone = await c.post("/api/report-config/batch-update", json={"project_id": gid, "updates": []})
            assert gone.status_code in (404, 405), gone.status_code

    @pytest.mark.asyncio
    async def test_drill_down_is_tree_contribution(self, db, group, legacy_client):
        from app.services.consol_report_service import generate_consol_reports_sync

        admin = _User(UserRole.admin)
        g_id = group["G"].id
        gid = str(g_id)
        db.add(_entry(group["G"], "IA-1", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "50", "0"), ("1122", "应收账款", "0", "50")]))
        db.add(_entry(group["A"], "IA-A", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "7", "0"), ("1122", "应收账款", "0", "7")]))
        await db.commit()
        await generate_consol_reports_sync(db, g_id, Y)
        await db.commit()
        async with legacy_client(admin) as c:
            report = {r["row_code"]: r for r in (await c.get(f"/api/consolidation/reports/{gid}/{Y}",
                                                              params={"report_type": "balance_sheet"})).json()}
            resp = await c.post("/api/report-config/drill-down",
                                json={"project_id": gid, "year": Y, "report_type": "balance_sheet", "row_code": "BS-006"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert D(body["total"]) == D(report["BS-006"]["current_period_amount"]) == D("343.00")
            direct = {r["node_key"]: r for r in body["rows"]}
            assert set(direct) == {"G:consol_elim", "G:parent", "A:consol", "B:subsidiary"}
            assert (direct["G:consol_elim"]["amount"], direct["G:consol_elim"]["source"]) == ("-50.00", "抵销与调整")
            assert direct["A:consol"]["amount"] == "73.00", "下级合并项目：A1 80 − 7"
            assert sum(D(r["amount"]) for r in body["rows"]) == D(body["total"]), "直接下级之和 = 合并数"
            leaves = {r["node_key"]: r for r in body["leaf_rows"]}
            assert {"A:consol_elim", "A1:subsidiary"} <= set(leaves) and "A:consol" not in leaves
            assert leaves["A:consol_elim"]["parent_name"] == "甲公司（合并）"
            assert sum(D(r["amount"]) for r in body["leaf_rows"]) == D(body["total"]), "末级之和 = 合并数"
            assert direct["G:parent"]["pct"] == str((D("320") / D("343") * 100).quantize(D("0.01")))

            sub = (await c.post("/api/report-config/drill-down",
                                json={"project_id": gid, "row_code": "BS-006", "node_key": "A:consol"})).json()
            assert sub["total"] == "73.00" and {r["node_key"] for r in sub["rows"]} == {"A:consol_elim", "A:parent", "A1:subsidiary"}
            for bad, code in (({"row_code": "NOPE"}, 404), ({"node_key": "B:subsidiary"}, 400), ({"row_code": ""}, 400)):
                r = await c.post("/api/report-config/drill-down", json={"project_id": gid, "row_code": "BS-006", **bad})
                assert r.status_code == code, (bad, r.text)
            standalone = await c.post("/api/report-config/drill-down",
                                      json={"project_id": str(group["B"].id), "row_code": "BS-006"})
            assert standalone.status_code == 404

    @pytest.mark.asyncio
    async def test_drill_down_auth(self, db, group, legacy_client):
        outsider = await _persist(db, _User(UserRole.auditor))
        reader = await _persist(db, _User(UserRole.auditor), [(group["G"], PermissionLevel.readonly)])
        body = {"project_id": str(group["G"].id), "row_code": "BS-006"}
        async with legacy_client(outsider) as c:
            assert (await c.post("/api/report-config/drill-down", json=body)).status_code == 403
        async with legacy_client(reader) as c:
            assert (await c.post("/api/report-config/drill-down", json=body)).status_code == 200
