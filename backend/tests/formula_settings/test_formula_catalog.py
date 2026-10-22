"""公式目录测试（spec unified-formula-registry Phase 2/4 · Task 6~11, 15）。

SQLite 真 ORM + TestClient。验证：
- build_catalog 跨 6 域返回 CatalogEntry
- catalog_stats 聚合正确
- extract_function_names 提取正确
- addr_id 格式正确
- formula-functions 端点返回全部已注册函数
- 端点鉴权
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._env import BS, STD, add_global_row, add_member, add_project, add_user, make_db


# ═══════════════════════════════════════════════════════════════════════════
# §1 纯函数测试
# ═══════════════════════════════════════════════════════════════════════════


class TestExtractFunctionNames:

    def test_single_function(self):
        from app.services.formula_catalog import extract_function_names

        assert extract_function_names("TB('1001','期末余额')") == ["TB"]

    def test_multiple_functions(self):
        from app.services.formula_catalog import extract_function_names

        result = extract_function_names("TB('1001','期末余额') + ROW('BS-002') * 0.5")
        assert result == ["TB", "ROW"]

    def test_dedup_preserves_order(self):
        from app.services.formula_catalog import extract_function_names

        result = extract_function_names("TB('1001','a') + TB('1002','b') + ROW('BS-001')")
        assert result == ["TB", "ROW"]

    def test_empty_formula(self):
        from app.services.formula_catalog import extract_function_names

        assert extract_function_names("") == []
        assert extract_function_names(None) == []

    def test_ledger_functions_recognized(self):
        from app.services.formula_catalog import extract_function_names

        assert extract_function_names("LEDGER('1001','借','全年')") == ["LEDGER"]
        assert extract_function_names("LEDGER_DETAIL('6001','12月','>=100000')") == ["LEDGER_DETAIL"]
        assert extract_function_names("TB_AUX('1121','客户','期末余额')") == ["TB_AUX"]


class TestSlotToAddr:

    def test_report(self):
        from app.services.formula_catalog import _slot_to_addr

        assert _slot_to_addr("report", "balance_sheet:BS-002") == "report:balance_sheet:BS-002"

    def test_wp(self):
        from app.services.formula_catalog import _slot_to_addr

        assert _slot_to_addr("wp", "D2|审定表D2-1|E100") == "wp:D2/审定表D2-1/E100"

    def test_note(self):
        from app.services.formula_catalog import _slot_to_addr

        assert _slot_to_addr("note", "五、1|应收账款:value") == "note:五、1"

    def test_cross_check(self):
        from app.services.formula_catalog import _slot_to_addr

        assert _slot_to_addr("cross_check", "report_bs#00001") == "cross_check:report_bs#00001"


# ═══════════════════════════════════════════════════════════════════════════
# §2 build_catalog — SQLite 真 ORM
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildCatalog:

    @pytest_asyncio.fixture
    async def env(self):
        async with make_db() as factory:
            async with factory() as db:
                user = await add_user(db, "cataloguser")
                pid = await add_project(db, "目录测试")
                await add_member(db, pid, user)
                await add_global_row(db, "BS-001", "TB('1001','期末余额')", row_number=1, row_name="货币资金")
                await add_global_row(db, "BS-002", "TB('1001','期末余额')+TB('1002','期末余额')",
                                     row_number=2, row_name="短期投资")
                await add_global_row(db, "BS-003", None, row_number=3, row_name="无公式行")
                await db.commit()
            yield {"factory": factory, "pid": pid, "user": user}

    @pytest.mark.asyncio
    async def test_returns_entries_with_formulas(self, env):
        from app.services.formula_catalog import build_catalog

        async with env["factory"]() as db:
            entries = await build_catalog(db, env["pid"], domains=["report"])
        # BS-003 无公式不进目录
        assert len(entries) == 2
        addr_ids = {e.addr_id for e in entries}
        assert "report:balance_sheet:BS-001" in addr_ids
        assert "report:balance_sheet:BS-002" in addr_ids

    @pytest.mark.asyncio
    async def test_function_refs_extracted(self, env):
        from app.services.formula_catalog import build_catalog

        async with env["factory"]() as db:
            entries = await build_catalog(db, env["pid"], domains=["report"])
        bs002 = next(e for e in entries if "BS-002" in e.addr_id)
        assert bs002.function_refs == ["TB"]
        assert bs002.layer == "global"

    @pytest.mark.asyncio
    async def test_stats_aggregation(self, env):
        from app.services.formula_catalog import catalog_stats

        from app.services.formula_push.engine import load_push_rules

        async with env["factory"]() as db:
            stats = await catalog_stats(db, env["pid"])
        # 公式推送规则也在内核里（spec formula-governance-coverage-closure R2）：公式来源的规则以系统预设进目录
        push_formulas = [r.source.expression for r in load_push_rules() if r.source.kind == "formula"]
        assert stats["by_domain"]["report"] == 2
        assert stats["by_domain"]["push"] == len(push_formulas)
        assert stats["total"] == 2 + len(push_formulas)
        assert stats["by_function"]["TB"] == 2 + sum("TB(" in e for e in push_formulas)

    @pytest.mark.asyncio
    async def test_domain_filter(self, env):
        from app.services.formula_catalog import build_catalog

        async with env["factory"]() as db:
            entries = await build_catalog(db, env["pid"], domains=["wp"])
        # 无底稿公式
        assert entries == []


# ═══════════════════════════════════════════════════════════════════════════
# §3 端点级测试
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def api():
    async with make_db() as factory:
        async with factory() as db:
            admin = await add_user(db, "admin", "admin")
            editor = await add_user(db, "editor", "auditor")
            outsider = await add_user(db, "outsider", "auditor")
            pid = await add_project(db, "端点测试")
            await add_member(db, pid, editor, "edit")
            await add_global_row(db, "BS-001", "TB('1001','期末余额')", row_number=1)
            await db.commit()

        from app.routers import formula_catalog as fc_mod

        app = FastAPI()
        app.include_router(fc_mod.router)

        who: dict[str, Any] = {"u": admin}

        async def _db():
            async with factory() as s:
                yield s

        async def _user():
            return who["u"]

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            yield {
                "c": client, "pid": pid,
                "switch": lambda name: who.update(u={"admin": admin, "editor": editor, "outsider": outsider}[name]),
            }


class TestCatalogEndpoint:

    @pytest.mark.asyncio
    async def test_member_gets_catalog(self, api):
        api["switch"]("editor")
        r = await api["c"].get(f"/api/projects/{api['pid']}/formula-catalog")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert data["entries"][0]["addr_id"].startswith("report:")

    @pytest.mark.asyncio
    async def test_outsider_gets_403(self, api):
        api["switch"]("outsider")
        r = await api["c"].get(f"/api/projects/{api['pid']}/formula-catalog")
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_stats_endpoint(self, api):
        api["switch"]("editor")
        r = await api["c"].get(f"/api/projects/{api['pid']}/formula-catalog/stats")
        assert r.status_code == 200
        assert "by_domain" in r.json()


class TestFormulaFunctionsEndpoint:

    @pytest.mark.asyncio
    async def test_returns_all_registered_functions(self, api):
        api["switch"]("editor")
        r = await api["c"].get("/api/formula-functions")
        assert r.status_code == 200
        data = r.json()
        names = {f["name"] for f in data["functions"]}
        # 至少包含全部 20 个已知函数
        for fn in ["TB", "SUM_TB", "ROW", "LEDGER", "LEDGER_DETAIL", "TB_AUX",
                    "COUNT_LEDGER", "PLACEHOLDER", "ABS", "IF"]:
            assert fn in names, f"{fn} 不在 /api/formula-functions 返回中"

    @pytest.mark.asyncio
    async def test_wp_has_multi_arity(self, api):
        r = await api["c"].get("/api/formula-functions")
        wp = next(f for f in r.json()["functions"] if f["name"] == "WP")
        assert wp["minArgs"] == 2 and wp["maxArgs"] == 3

    @pytest.mark.asyncio
    async def test_each_function_has_description(self, api):
        r = await api["c"].get("/api/formula-functions")
        for fn in r.json()["functions"]:
            assert fn["description"], f"{fn['name']} 缺少 description"
