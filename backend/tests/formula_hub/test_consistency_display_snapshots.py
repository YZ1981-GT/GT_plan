"""一致性检查三个展示端点按五态输出（第 2 轮 D-3，需求 16.5；design §10.3 末句「看板端点由响应快照覆盖」）。

同一合成夹具：五态各一项（通过 / 失败 / 未执行 / 不适用 / 检查异常，后四项各带原因）。三个端点经 HTTP 请求
（按生产注册挂 router，鉴权链真实运行，只替换 ``get_current_user`` / ``get_db``），响应与 ``_snapshots/`` 下的
快照逐字段相等；另逐项断言：非通过项都带状态与原因、没有任何非通过项显示成通过、原计数字段保持「失败」含义。
看板另有「0 失败」的四种组合（第 2 轮评审第 1 条）：``all_passed`` 与 consistency-check 同口径，每项都通过才为真。
前端 ``VRSummaryCard.fiveState.spec.ts`` / ``VRHeatmap.fiveState.spec.ts`` 读这里写下的快照。

- ``GET /api/projects/{pid}/workflow/consistency-check``（签字决策页、导出对话框、底稿侧栏门禁面板共用）
- ``GET /api/projects/{pid}/dashboard/summary`` 的 ``vr_summary``（唯一调 ``_aggregate_vr_summary`` 的端点）
- ``GET /api/projects/{pid}/qc/vr-heatmap``

快照更新：``FHIC_UPDATE_SNAPSHOTS=1`` 时写入（须人工核对后提交）；平时缺文件即红。
SQLite 上 ``fetch_project_audit_year``（PG 专用 SQL）换成同口径的 ORM 解析；看板其余四段与本条无关，打桩为空。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.routers import chain_workflow, dashboard_aggregator, qc_vr_heatmap
from app.services.consistency_gate import ConsistencyGate, ConsistencyResult, _models
from app.services.dashboard_aggregator_service import DashboardAggregatorService
from tests.formula_hub._history_http import http_client
from tests.formula_settings._env import add_project, add_user, make_db

SNAP_DIR = Path(__file__).resolve().parent / "_snapshots"
FIVE = (
    _models._ok("试算平衡", details="借贷平衡", severity="blocking"),
    _models._fail("D4勾稽:营业收入合计=主营+其他", reason="差额 10.00", details="主营 90.00 + 其他 0.00 ≠ 100.00",
                  severity="blocking"),
    _models._not_executed("E1勾稽:现金流量表", branch_id="e1.cfs_missing", reason="现金流量表尚未生成",
                          severity="blocking"),
    _models._not_applicable("F 三角勾稽", branch_id="f.trimmed", reason="底稿已裁剪"),
    _models._error("G 三角勾稽", branch_id="g.exception", reason="检查异常：RuntimeError：boom"),
)
#: 热力图按循环逐个方法取数：五态各落在一个循环里
HEATMAP = {"check_d4_revenue_reconciliation": [FIVE[1]], "check_e1_cfs_reconciliation": [FIVE[2]],
           "check_f5_f2_triangle_reconciliation": [FIVE[3]], "check_g_cycle_triangle_reconciliation": [FIVE[4]],
           "check_h_cycle_triangle_reconciliation": [FIVE[0]]}
#: 「0 失败」的四种组合（第 2 轮评审第 1 条）：通过 + 一项未执行（阻断级）/ 检查异常 / 不适用，以及每项都通过。
#: FIVE 恒含一项失败，测不到「只看失败数」把未执行显示成「全部通过」
NO_FAILURE = {
    "not_executed": (FIVE[0], FIVE[2]),
    "error": (FIVE[0], FIVE[4]),
    "not_applicable": (FIVE[0], FIVE[3]),
    "all_passed": (FIVE[0], _models._ok("D4勾稽:营业收入合计=主营+其他", details="主营 100.00 + 其他 0.00 = 100.00",
                                        severity="blocking")),
}


@pytest.fixture
def gate(monkeypatch):
    async def _run_all(self, project_id, year):
        assert year == 2025, year
        return ConsistencyResult(overall="fail", checks=list(FIVE))

    monkeypatch.setattr(ConsistencyGate, "run_all_checks", _run_all)
    for name in qc_vr_heatmap._CYCLE_CHECK_MAP.values():
        method = name[0]

        async def _checks(self, project_id, year, _m=method):
            return list(HEATMAP.get(_m, []))

        monkeypatch.setattr(ConsistencyGate, method, _checks)

    async def _orm_year(db, project_id):
        from app.services.project_audit_year import resolve_project_audit_year_for_request

        return await resolve_project_audit_year_for_request(db, project_id)

    monkeypatch.setattr("app.services.project_audit_year.fetch_project_audit_year", _orm_year)
    for section in ("_aggregate_cycle_progress", "_aggregate_open_reviews", "_aggregate_timeline",
                    "_aggregate_trimming"):
        monkeypatch.setattr(DashboardAggregatorService, section, AsyncMock(return_value=None))


def _check_snapshot(name: str, data) -> None:
    path = SNAP_DIR / f"{name}.json"
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("FHIC_UPDATE_SNAPSHOTS") == "1":
        SNAP_DIR.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.exists(), f"缺快照 {path}（FHIC_UPDATE_SNAPSHOTS=1 生成并人工核对）"
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(text), f"{name} 响应与快照不符"


def _assert_five_state_items(items: list[dict], *, with_passed: bool) -> None:
    """非通过项逐项带五态与原因；没有一项非通过项被标成通过。"""
    by_status = {i["status"]: i for i in items}
    expected = {"failed", "not_executed", "not_applicable", "error"} | ({"passed"} if with_passed else set())
    assert set(by_status) == expected, sorted(by_status)
    for status in ("failed", "not_executed", "not_applicable", "error"):
        assert by_status[status]["reason"], (status, by_status[status])
        assert by_status[status].get("passed") in (None, False), by_status[status]


async def _world(db):
    admin = await add_user(db, "fhic_display_admin", "admin")
    pid = await add_project(db, "门禁展示")
    no_year = await add_project(db, "门禁展示无年度")
    from app.models.core import Project

    (await db.get(Project, no_year)).audit_year = None
    await db.commit()
    return admin, pid, no_year


async def test_consistency_check_endpoint_snapshot(gate):
    async with make_db() as factory, factory() as db:
        admin, pid, _ = await _world(db)
        async with http_client(db, admin, chain_workflow.router) as http:
            resp = await http.get(f"/api/projects/{pid}/workflow/consistency-check", params={"year": 2025})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        _assert_five_state_items(body["checks"], with_passed=True)
        counts = {k: body[f"{k}_count"] for k in ("passed", "failed", "not_executed", "not_applicable", "error")}
        assert counts == dict.fromkeys(counts, 1) and body["all_passed"] is False
        _check_snapshot("consistency_check", body)


async def test_dashboard_vr_summary_snapshot(gate):
    async with make_db() as factory, factory() as db:
        admin, pid, no_year = await _world(db)
        async with http_client(db, admin, dashboard_aggregator.router) as http:
            resp = await http.get(f"/api/projects/{pid}/dashboard/summary")
            missing = await http.get(f"/api/projects/{no_year}/dashboard/summary")
        assert resp.status_code == 200, resp.text
        vr = resp.json()["vr_summary"]
        assert "vr_summary" not in (resp.json()["errors"] or {}), resp.json()["errors"]
        _assert_five_state_items(vr["not_passed_checks"], with_passed=False)
        assert vr["status_counts"] == dict.fromkeys(_models.FIVE_STATES, 1)
        # 原计数字段保持「失败」含义：只有「失败 ∧ 阻断级」计入 blocking_failed（未执行的阻断项不计）
        assert (vr["blocking_failed"], vr["all_passed"], vr["unavailable"]) == (1, False, False)
        # 无年度：不跑检查、明示不可用（原先缺 all_passed ⇒ 响应模型校验失败、整个看板 500）
        assert missing.status_code == 200, missing.text
        unavailable = missing.json()["vr_summary"]
        assert (unavailable["unavailable"], unavailable["all_passed"]) == (True, False), unavailable
        assert unavailable["reason"] == "项目未设置审计年度，未运行一致性检查"
        _check_snapshot("dashboard_vr_summary", {"with_year": vr, "without_year": unavailable})


async def test_dashboard_all_passed_same_as_consistency_check(gate, monkeypatch):
    """0 失败 ≠ 全部通过：有一项未执行 / 检查异常 / 不适用，看板 ``all_passed`` 就与 consistency-check 一样为假；
    每项都通过才为真。``blocking_failed`` / ``by_cycle`` 仍只数失败（这里恒为 0 / 空）。"""
    seen: dict[str, dict] = {}
    async with make_db() as factory, factory() as db:
        admin, pid, _ = await _world(db)
        async with http_client(db, admin, dashboard_aggregator.router, chain_workflow.router) as http:
            for case, checks in NO_FAILURE.items():
                async def _run_all(self, project_id, year, _checks=checks):
                    assert year == 2025, year
                    return ConsistencyResult(overall="fail", checks=list(_checks))

                monkeypatch.setattr(ConsistencyGate, "run_all_checks", _run_all)
                summary = await http.get(f"/api/projects/{pid}/dashboard/summary")
                check = await http.get(f"/api/projects/{pid}/workflow/consistency-check", params={"year": 2025})
                assert (summary.status_code, check.status_code) == (200, 200), (case, summary.text, check.text)
                vr, body = summary.json()["vr_summary"], check.json()
                want = case == "all_passed"
                assert (vr["all_passed"], body["all_passed"]) == (want, want), (case, vr, body)
                assert (vr["blocking_failed"], vr["by_cycle"]) == (0, []), (case, vr)
                assert [i["status"] for i in vr["not_passed_checks"]] == ([] if want else [case]), (case, vr)
                counts = dict.fromkeys(_models.FIVE_STATES, 0) | ({"passed": 2} if want else {"passed": 1, case: 1})
                assert vr["status_counts"] == counts, (case, vr)
                seen[case] = vr
    _check_snapshot("dashboard_vr_summary_no_failure", seen)


async def test_qc_vr_heatmap_snapshot(gate):
    async with make_db() as factory, factory() as db:
        admin, pid, no_year = await _world(db)
        async with http_client(db, admin, qc_vr_heatmap.router) as http:
            resp = await http.get(f"/api/projects/{pid}/qc/vr-heatmap")
            missing = await http.get(f"/api/projects/{no_year}/qc/vr-heatmap")
        assert resp.status_code == 200, resp.text
        assert missing.status_code == 422, missing.text
        body = resp.json()
        assert body["status_counts"] == dict.fromkeys(_models.FIVE_STATES, 1)
        assert body["total"] == {"blocking": 1, "warning": 0, "info": 0}, "严重级计数只数「失败」"
        _assert_five_state_items([i for row in body["matrix"] for i in row["not_passed_checks"]], with_passed=False)
        _check_snapshot("qc_vr_heatmap", body)
