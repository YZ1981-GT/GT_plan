"""formula-settings-wiring-closure 端点级测试：coverage / history / dependencies。

使用 SQLite 真 ORM + TestClient（httpx AsyncClient）真发 HTTP 请求；
只替换 get_db / get_current_user，鉴权中间件照常跑。

coverage.compute 是纯函数测试；history / dependencies 需要 DraftRefreshAudit 和
CrossCheckResult 两张额外表；dependency 直接走 effective_slots（SQLite 里的报表行）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import DraftRefreshAudit
from app.models.wp_optimization_models import CrossCheckResult as CrossCheckResultRow

from ._env import BS, STD, add_global_row, add_member, add_project, add_user, make_db

# ═══════════════════════════════════════════════════════════════════════════
# §1 coverage.compute — 纯函数
# ═══════════════════════════════════════════════════════════════════════════


class TestCoverageCompute:
    """coverage.compute 是纯函数，直接喂数据。"""

    @staticmethod
    def _compute(coverage: dict, mapping: dict) -> dict:
        from app.services.formula_push.coverage import compute

        return compute(coverage, mapping)

    def test_program_tables_excluded_from_denominator(self):
        """程序表 ``D1A`` / ``E1A`` 不进分母。"""
        mapping = {"mappings": [
            {"wp_code": "D1", "account_codes": ["1122"]},
            {"wp_code": "D1A", "account_codes": ["1122"]},  # 程序表
            {"wp_code": "D2", "account_codes": ["1123"]},
        ]}
        coverage = {"registered_codes": ["D1", "D2"], "not_applicable": []}
        r = self._compute(coverage, mapping)
        # D1A 不进分母；分母 = {D1, D2}，分子 = {D1, D2}
        assert r["total_codes"] == 2
        assert r["total_registered"] == 2
        assert r["percentage"] == 100.0
        d_cycle = next(c for c in r["cycles"] if c["cycle"] == "D")
        assert d_cycle["total"] == 2
        assert d_cycle["connected"] == 2

    def test_non_100_percent(self):
        """部分未接入 → percentage < 100，missing 列出缺口。"""
        mapping = {"mappings": [
            {"wp_code": "D1", "account_codes": ["1122"]},
            {"wp_code": "D2", "account_codes": ["1123"]},
            {"wp_code": "D3", "account_codes": ["1124"]},
        ]}
        coverage = {"registered_codes": ["D1"], "not_applicable": []}
        r = self._compute(coverage, mapping)
        assert r["total_codes"] == 3
        assert r["total_registered"] == 1
        assert r["percentage"] < 100
        d_cycle = next(c for c in r["cycles"] if c["cycle"] == "D")
        assert set(d_cycle["missing"]) == {"D2", "D3"}

    def test_not_applicable_excluded(self):
        """判为不适用的编码（如函证中心 D0）不进分母。"""
        mapping = {"mappings": [
            {"wp_code": "D0", "account_codes": ["9999"]},
            {"wp_code": "D1", "account_codes": ["1122"]},
        ]}
        coverage = {"registered_codes": ["D1"],
                    "not_applicable": [{"wp_code": "D0", "reason": "函证中心"}]}
        r = self._compute(coverage, mapping)
        assert r["total_codes"] == 1  # D0 排除
        assert r["total_registered"] == 1
        assert "D0" in r["excluded"]

    def test_abcs_not_needed(self):
        """A/B/C/S 标「不需推送」。"""
        r = self._compute({"registered_codes": [], "not_applicable": []}, {"mappings": []})
        for letter in "ABCS":
            cycle = next((c for c in r["cycles"] if c["cycle"] == letter), None)
            assert cycle is not None, f"{letter} 循环缺失"
            assert cycle["not_needed"] is True

    def test_no_account_codes_not_in_denominator(self):
        """无 account_codes 的编码不进分母。"""
        mapping = {"mappings": [
            {"wp_code": "D1", "account_codes": []},
            {"wp_code": "D2", "account_codes": ["1123"]},
        ]}
        r = self._compute({"registered_codes": ["D2"], "not_applicable": []}, mapping)
        assert r["total_codes"] == 1  # D1 无科目码，不进分母

    def test_load_coverage_on_real_data(self):
        """load_coverage 读真实数据文件（冒烟；不断言具体数字，只验结构）。"""
        from app.services.formula_push.coverage import load_coverage

        r = load_coverage()
        assert "total_codes" in r and "cycles" in r
        assert isinstance(r["cycles"], list)
        assert r["total_codes"] >= 0


# ═══════════════════════════════════════════════════════════════════════════
# §2 cross-check-history — 需要 DraftRefreshAudit + CrossCheckResult
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossCheckHistory:

    @pytest_asyncio.fixture
    async def env(self):
        """两次 run（一次有 issues、一次无）+ 1 条 issue 行。"""
        async with make_db((DraftRefreshAudit, CrossCheckResultRow)) as factory:
            async with factory() as db:
                user = await add_user(db, "editor")
                pid = await add_project(db, "历史测试")
                await add_member(db, pid, user)

                run1 = uuid.uuid4()
                run2 = uuid.uuid4()
                t1 = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
                t2 = datetime(2025, 6, 2, 10, 0, 0, tzinfo=timezone.utc)

                db.add(DraftRefreshAudit(
                    id=run1, project_id=pid, year=2025, operator_id=user.id,
                    operator_role="readonly", scope="formula:report-cross-check",
                    operated_at=t1, tb_snapshot_hash="aaa", affected_count=5,
                    result_status="success",
                    detail={"kind": "report_cross_check", "status": "executed",
                            "executed_count": 5, "issue_count": 1, "hint_count": 0},
                ))
                db.add(DraftRefreshAudit(
                    id=run2, project_id=pid, year=2025, operator_id=user.id,
                    operator_role="readonly", scope="formula:report-cross-check",
                    operated_at=t2, tb_snapshot_hash="bbb", affected_count=3,
                    result_status="success",
                    detail={"kind": "report_cross_check", "status": "executed",
                            "executed_count": 3, "issue_count": 0, "hint_count": 2},
                ))
                # 只给 run2 关联一条 issue（最近一次保留明细）
                db.add(CrossCheckResultRow(
                    project_id=pid, year=2025, rule_id="R001",
                    left_amount=Decimal("100"), right_amount=Decimal("90"),
                    difference=Decimal("10"), status="failed",
                    details={"run_id": str(run2), "description": "test"},
                ))
                await db.commit()
                yield {"factory": factory, "pid": pid, "user": user,
                       "run1": run1, "run2": run2}

    @pytest.mark.asyncio
    async def test_list_history_order_and_fields(self, env):
        from app.services.formula_management.cross_check_history import list_history

        async with env["factory"]() as db:
            runs = await list_history(db, env["pid"], 2025)
        # 按 operated_at DESC → run2 在前
        assert len(runs) == 2
        assert runs[0]["run_id"] == str(env["run2"])
        assert runs[0]["executed_count"] == 3
        assert runs[0]["hint_count"] == 2
        assert runs[0]["issues_retained"] is True
        assert len(runs[0]["issues"]) == 1
        assert runs[0]["issues"][0]["rule_id"] == "R001"
        assert runs[0]["issues"][0]["left_value"] == 100.0

        # run1 无关联 issues
        assert runs[1]["run_id"] == str(env["run1"])
        assert runs[1]["issues_retained"] is False
        assert runs[1]["issues"] == []

    @pytest.mark.asyncio
    async def test_year_filter(self, env):
        from app.services.formula_management.cross_check_history import list_history

        async with env["factory"]() as db:
            runs = await list_history(db, env["pid"], 2024)
        assert runs == []


# ═══════════════════════════════════════════════════════════════════════════
# §3 dependencies — 基于 effective_slots（SQLite 里的 report_config）
# ═══════════════════════════════════════════════════════════════════════════


class TestDependencies:

    @pytest_asyncio.fixture
    async def env(self):
        """BS-002 = TB('1001')+TB('1002'), BS-010 = ROW('BS-002'), BS-020 = SUM_ROW('BS-001','BS-015')。"""
        async with make_db() as factory:
            async with factory() as db:
                user = await add_user(db, "dep_user")
                pid = await add_project(db, "依赖测试")
                await add_member(db, pid, user)

                await add_global_row(db, "BS-001", "TB('1001','期末余额')", row_number=1, row_name="货币资金")
                await add_global_row(db, "BS-002", "TB('1001','期末余额')+TB('1002','期末余额')",
                                     row_number=2, row_name="短期投资")
                await add_global_row(db, "BS-010", "ROW('BS-002')", row_number=10, row_name="流动资产合计")
                await add_global_row(db, "BS-015", "TB('1005','期末余额')", row_number=15, row_name="预付账款")
                await add_global_row(db, "BS-020", "SUM_ROW('BS-001','BS-015')", row_number=20,
                                     row_name="资产合计")
                await db.commit()
            yield {"factory": factory, "pid": pid, "user": user}

    @pytest.mark.asyncio
    async def test_upstream_of_bs002(self, env):
        from app.services.formula_settings.dependencies import formula_dependencies

        async with env["factory"]() as db:
            r = await formula_dependencies(db, env["pid"], "balance_sheet:BS-002")
        assert r["kind"] == "report"
        assert r["addr_id"] == "report:balance_sheet:BS-002"
        ups = {u["addr_id"] for u in r["upstream"]}
        assert "tb:1001" in ups
        assert "tb:1002" in ups

    @pytest.mark.asyncio
    async def test_downstream_of_bs002(self, env):
        """BS-010 = ROW('BS-002') → BS-002 的下游应含 BS-010。"""
        from app.services.formula_settings.dependencies import formula_dependencies

        async with env["factory"]() as db:
            r = await formula_dependencies(db, env["pid"], "balance_sheet:BS-002")
        down_ids = {d["addr_id"] for d in r["downstream"]}
        assert "report:balance_sheet:BS-010" in down_ids

    @pytest.mark.asyncio
    async def test_tb_downstream(self, env):
        """tb:1001 被 BS-001 和 BS-002 引用。"""
        from app.services.formula_settings.dependencies import formula_dependencies

        async with env["factory"]() as db:
            r = await formula_dependencies(db, env["pid"], "tb:1001")
        down_ids = {d["addr_id"] for d in r["downstream"]}
        assert "report:balance_sheet:BS-001" in down_ids
        assert "report:balance_sheet:BS-002" in down_ids

    @pytest.mark.asyncio
    async def test_sum_row_range_includes_member(self, env):
        """BS-020 = SUM_ROW('BS-001','BS-015') 下游查 BS-002 应含 BS-020。"""
        from app.services.formula_settings.dependencies import formula_dependencies

        async with env["factory"]() as db:
            r = await formula_dependencies(db, env["pid"], "balance_sheet:BS-002")
        down_ids = {d["addr_id"] for d in r["downstream"]}
        assert "report:balance_sheet:BS-020" in down_ids

    @pytest.mark.asyncio
    async def test_bare_code_resolves(self, env):
        """裸行次 ``BS-002`` 在本项目报表里唯一 → 自动定位。"""
        from app.services.formula_settings.dependencies import formula_dependencies

        async with env["factory"]() as db:
            r = await formula_dependencies(db, env["pid"], "BS-002")
        assert r["addr_id"] == "report:balance_sheet:BS-002"
        assert len(r["upstream"]) > 0

    @pytest.mark.asyncio
    async def test_unknown_target_raises(self, env):
        from app.services.formula_settings.dependencies import (
            DependencyTargetError,
            formula_dependencies,
        )

        async with env["factory"]() as db:
            with pytest.raises(DependencyTargetError):
                await formula_dependencies(db, env["pid"], "BS-999")

    @pytest.mark.asyncio
    async def test_unavailable_domains_reported(self, env):
        """非报表域读不到时，unavailable_domains 如实报告（不崩）。"""
        from app.services.formula_settings.dependencies import formula_dependencies

        async with env["factory"]() as db:
            r = await formula_dependencies(db, env["pid"], "balance_sheet:BS-002")
        # SQLite 里没建 formula_setting 表以外的域可能 unavailable
        assert "unavailable_domains" in r


# ═══════════════════════════════════════════════════════════════════════════
# §4 纯函数：upstream_refs / references
# ═══════════════════════════════════════════════════════════════════════════


class TestUpstreamRefs:

    def test_tb_and_row(self):
        from app.services.formula_settings.dependencies import upstream_refs

        formula = "TB('1001','期末余额')+ROW('BS-002')"
        rt = {"BS-002": "balance_sheet"}
        refs = upstream_refs(formula, rt)
        addrs = {r["addr_id"] for r in refs}
        assert "tb:1001" in addrs
        assert "report:balance_sheet:BS-002" in addrs

    def test_sum_tb(self):
        from app.services.formula_settings.dependencies import upstream_refs

        refs = upstream_refs("SUM_TB('1001','期末余额')", {})
        assert refs[0]["type"] == "trial_balance"

    def test_note_ref(self):
        from app.services.formula_settings.dependencies import upstream_refs

        refs = upstream_refs("NOTE('五、1','应收账款','value')", {})
        assert refs[0]["addr_id"] == "note:五、1"

    def test_wp_ref(self):
        from app.services.formula_settings.dependencies import upstream_refs

        refs = upstream_refs("WP('D1','审定表D1-1','审定数')", {})
        assert refs[0]["addr_id"] == "wp:D1/审定表D1-1/审定数"


class TestReferences:

    def test_exact_row(self):
        from app.services.formula_settings.dependencies import references

        assert references("ROW('BS-002')+ROW('BS-005')", row_code="BS-002")
        assert not references("ROW('BS-002')+ROW('BS-005')", row_code="BS-003")

    def test_sum_row_range(self):
        from app.services.formula_settings.dependencies import references

        assert references("SUM_ROW('BS-001','BS-015')", row_code="BS-002")
        # 不同前缀不命中
        assert not references("SUM_ROW('BS-001','BS-015')", row_code="IS-002")

    def test_tb_account(self):
        from app.services.formula_settings.dependencies import references

        assert references("TB('1001','期末余额')", account="1001")
        assert not references("TB('1001','期末余额')", account="1002")


# ═══════════════════════════════════════════════════════════════════════════
# §5 端点级鉴权 — TestClient 真发请求
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def api():
    """TestClient：admin / editor(项目成员) / outsider(非成员)。"""
    async with make_db((DraftRefreshAudit, CrossCheckResultRow)) as factory:
        async with factory() as db:
            admin = await add_user(db, "admin", "admin")
            editor = await add_user(db, "editor", "auditor")
            outsider = await add_user(db, "outsider", "auditor")
            pid = await add_project(db, "鉴权测试")
            await add_member(db, pid, editor, "edit")

            await add_global_row(db, "BS-001", "TB('1001','期末余额')", row_number=1)
            await db.commit()

        from app.routers import formula_logic_check as flc_mod
        from app.routers import formula_push as fp_mod
        from app.routers import formula_settings as fs_mod

        app = FastAPI()
        app.include_router(flc_mod.router)
        app.include_router(fp_mod.global_router)
        app.include_router(fs_mod.project_router)

        who: dict[str, Any] = {"u": admin}

        async def _db():
            async with factory() as s:
                yield s

        async def _user():
            return who["u"]

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            yield {"c": client, "pid": pid, "admin": admin, "editor": editor, "outsider": outsider,
                   "switch": lambda name: who.update(u={"admin": admin, "editor": editor, "outsider": outsider}[name])}


class TestEndpointAuth:

    @pytest.mark.asyncio
    async def test_coverage_requires_login(self, api):
        """coverage 需登录（get_current_user），任何已登录用户可读。"""
        api["switch"]("editor")
        r = await api["c"].get("/api/formula-push/coverage")
        assert r.status_code == 200
        assert "total_codes" in r.json()

    @pytest.mark.asyncio
    async def test_cross_check_history_member_200(self, api):
        api["switch"]("editor")
        r = await api["c"].get(
            f"/api/projects/{api['pid']}/formula/cross-check-history",
            params={"year": 2025},
        )
        assert r.status_code == 200
        assert r.json()["runs"] == []

    @pytest.mark.asyncio
    async def test_cross_check_history_outsider_403(self, api):
        api["switch"]("outsider")
        r = await api["c"].get(
            f"/api/projects/{api['pid']}/formula/cross-check-history",
            params={"year": 2025},
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_dependencies_member_200(self, api):
        api["switch"]("editor")
        r = await api["c"].get(
            f"/api/projects/{api['pid']}/formula-settings/dependencies",
            params={"addr_id": "balance_sheet:BS-001"},
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_dependencies_outsider_403(self, api):
        api["switch"]("outsider")
        r = await api["c"].get(
            f"/api/projects/{api['pid']}/formula-settings/dependencies",
            params={"addr_id": "balance_sheet:BS-001"},
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_dependencies_unknown_target_404(self, api):
        api["switch"]("editor")
        r = await api["c"].get(
            f"/api/projects/{api['pid']}/formula-settings/dependencies",
            params={"addr_id": "NOT-EXIST"},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["error_code"] == "FORMULA_DEPENDENCY_TARGET_NOT_FOUND"
