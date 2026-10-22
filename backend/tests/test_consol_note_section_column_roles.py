"""合并附注审核 / 下级汇总的认列（spec consol-note-header-library-and-node-reaggregate R5）。

表头识别统一走标题行库（``note_table_header_library``）：逐列角色按模板展示用的多级表头认，变动表勾稽列由
``rollforward_columns`` 给出。这里测路由侧选表（模板 vs 本次平表头）与三处真实调用：全部审核、单表审核、
下级汇总的试算表兜底。附注数据落真实行，试算表金额（合并计算上下文）打桩。
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型与 SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, UserRole
from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import Project
from app.routers import consol_note_sections as R
from app.services.consol_node_scope import NodeScope
from app.services.consol_tree_service import TreeNode

Y = 2025
BASE = "/api/consol-note-sections"


def _section(section_id: str, std: str = "soe") -> dict:
    return next(s for s in R._load_sections(std) if s["section_id"] == section_id)


def _roles(table: dict) -> list[str | None]:
    return R._column_view(table)[1]


# ─── 选表 + 逐列角色 ──────────────────────────────────────────────────────────


class TestHeaderTable:
    def test_template_header_rows_when_columns_match(self):
        """五-24-1 种子平表头只在分组起始列写期间：按模板多级表头认，列名取展示路径。"""
        sec = _section("五-24-1")
        labels, roles = R._column_view(R._header_table(sec, sec["headers"]))
        assert roles == ["label", "closing", None, None, "opening", None, None]
        assert labels[2] == "期末余额/减值准备" and labels[4] == "期初余额/账面余额"

    def test_flat_headers_when_column_count_differs(self):
        headers = ["项目", "期末余额", "期初余额"]
        table = R._header_table(_section("五-24-1"), headers)
        assert table == {"headers": headers} and _roles(table) == ["label", "closing", "opening"]
        assert R._column_view(R._header_table(None, [])) == ([], [])

    @pytest.mark.parametrize("headers,roles", [
        (["项  目", "期末余额", "期初余额"], ["label", "closing", "opening"]),
        (["项  目", "期初余额", "本期增加", "本期减少", "期末余额"], ["label", "opening", "increase", "decrease", "closing"]),
        (["类别", "金额", "比例(%)"], ["label", None, None]),
        (["项目", "期末数"], ["label", "closing"]),
        (["列1", "期末余额", "上年年末余额"], ["label", "closing", "opening"]),
        # 旧逻辑把「本期<br/>增加」当成期末值列
        (["项目", "期初余额", "本期<br/>增加", "期末<br/>余额"], ["label", "opening", "increase", "closing"]),
        # 平表头里的「/」不拆段：期间与计量混写的列不认作余额列（不会拿坏账准备列去比审定数）。
        # 真库已保存的合并附注表头与模板逐字相同，审核走的是模板多级表头，不走这里。
        (["类  别", "期末数/账面余额/金额", "期末数/坏账准备/金额", "期初数/账面余额"], ["label", None, None, None]),
    ])
    def test_flat_header_roles(self, headers, roles):
        assert _roles(R._header_table(None, headers)) == roles

    @pytest.mark.parametrize("std,section_id,closing,opening", [
        ("soe", "五-1-1", [1], [2]),
        ("soe", "五-5-1", [1], [3]),  # 两级表头：坏账准备列不算
        ("soe", "五-5-2", [1], [6]),  # 三级表头：账面余额/金额；比例 / 坏账准备 / 账面价值 不算
        ("soe", "五-5-6", [1], [4]),  # 种子平表头把「期初数」写在第 2 列（实际是 期末数/计提比例）
        ("listed", "五-5-6", [1], [4]),  # 上年年末余额
        ("soe", "五-57-1", [4], [1]),  # 变动表
    ])
    def test_real_template_balance_columns(self, std, section_id, closing, opening):
        sec = _section(section_id, std)
        roles = _roles(R._header_table(sec, sec["headers"]))
        assert [i for i, r in enumerate(roles) if r == "closing"] == closing
        assert [i for i, r in enumerate(roles) if r == "opening"] == opening


# ─── 端点真实调用 ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    project = Project(
        id=uuid.uuid4(), name="【测试】合并附注认列", client_name="【测试】合并附注认列",
        status=ProjectStatus.execution, audit_year=Y,
    )
    async with factory() as db:
        db.add(project)
        await db.commit()
    app = FastAPI()
    app.include_router(R.router)
    actor = type("Actor", (), {
        "id": uuid.uuid4(), "username": "test_column_roles", "role": UserRole.admin, "is_active": True, "is_deleted": False,
    })()

    async def override_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        yield factory, project, app
    finally:
        await engine.dispose()


async def _post(app, url: str, body: dict) -> dict:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(url, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _brief(results: list[dict], prefix: str) -> list[tuple[str, str, str]]:
    return [(r["rule_name"], r["expected"], r["actual"]) for r in results if r["rule_name"].startswith(prefix)]


class TestAuditAll:
    @pytest.mark.asyncio
    async def test_tb_check_compares_only_balance_columns(self, env):
        """五-24-1：只比 期末余额/账面余额、期初余额/账面余额；平表头会把「期末余额/减值准备」当期初列去比。"""
        factory, project, app = env
        sec = _section("五-24-1")
        rows = [["在建工程", "100", "5", "95", "80", "4", "76"], ["工程物资", "100", "0", "100", "70", "0", "70"]]
        async with factory() as db:
            db.add(ConsolNoteData(
                project_id=project.id, year=Y, section_id="五-24-1", data={"headers": sec["headers"], "rows": rows},
            ))
            await db.commit()
        tb = {"在建工程": {"audited": 100.0, "opening": 80.0}, "工程物资": {"audited": 100.0, "opening": 80.0}}
        with patch.object(R, "_load_tb_map", AsyncMock(return_value=tb)):
            body = await _post(app, f"{BASE}/audit-all/{project.id}/{Y}", {"standard": "soe"})
        assert "load_errors" not in body
        assert _brief(body["results"], "试算表交叉校验") == [("试算表交叉校验 - 工程物资/期初余额/账面余额", "80.00", "70.00")]


class TestAuditSingle:
    async def _audit(self, app, project, section_id: str, rows: list, tb: dict | None = None) -> list[dict]:
        headers = _section(section_id)["headers"]
        with patch.object(R, "_load_tb_map", AsyncMock(return_value=tb or {})):
            body = await _post(app, f"{BASE}/audit/{project.id}/{Y}/{section_id}", {
                "standard": "soe", "headers": headers, "rows": rows,
            })
        return body["results"]

    @pytest.mark.asyncio
    async def test_rollforward_uses_every_leaf_of_movement_groups(self, env):
        """五-10-2：其他增加 / 转销 / 其他减少 都参与（旧逻辑只认分组起始列，第一行会误报）；按平表头认，
        「其他增加」列没有表头、方向不定，最后一行就不会被校验出来。"""
        _, project, app = env
        rows = [
            ["原材料", "100", "30", "6", "10", "2", "3", "121"],
            ["库存商品", "100", "30", "0", "10", "0", "0", "125"],
            ["周转材料", "100", "0", "6", "0", "0", "0", "110"],
        ]
        results = await self._audit(app, project, "五-10-2", rows)
        assert _brief(results, "勾稽校验") == [
            ("勾稽校验 - 库存商品", "120.00", "125.00"), ("勾稽校验 - 周转材料", "106.00", "110.00"),
        ]

    @pytest.mark.asyncio
    async def test_rows_with_unknown_flows_are_not_checked(self, env):
        """五-81-9：现金流量净额 / 公允价值变动 / 其他 方向不定，有数的行不勾稽（旧逻辑当 0 算，必误报）。"""
        _, project, app = env
        rows = [
            ["长期借款", "100", "50", "2", "0", "0", "152"],
            ["应付债券", "100", "0", "2", "0", "0", "103"],
        ]
        results = await self._audit(app, project, "五-81-9", rows)
        assert _brief(results, "勾稽校验") == [("勾稽校验 - 应付债券", "102.00", "103.00")]

    @pytest.mark.asyncio
    async def test_tb_check_names_columns_by_header_rows(self, env):
        _, project, app = env
        rows = [["工程物资", "100", "0", "100", "70", "0", "70"]]
        results = await self._audit(app, project, "五-24-1", rows, tb={"工程物资": {"audited": 100.0, "opening": 80.0}})
        assert _brief(results, "试算表校验") == [("试算表校验 - 工程物资/期初余额/账面余额", "80.00", "70.00")]


class TestAggregateTbFallback:
    @pytest.mark.asyncio
    async def test_only_balance_columns_fall_back_to_child_tb(self, env):
        """下级没有附注数据时按试算表兜底：只有期末 / 期初余额列取，减值准备列不取（平表头会把它认成期初）。"""
        _, project, app = env
        children = [
            TreeNode(None, code, f"子{code}", "P", "P", 1, node_key=f"{code}:parent", role="parent") for code in ("A", "B")
        ]
        root = TreeNode(None, "P", "母公司", None, None, 0, children=children, node_key="P:consol", role="consol")
        scope = NodeScope(project.id, Y, "五-24-1", "P:consol", root, root)
        child_tb = {
            "A:parent": {"在建工程": {"audited": 100.0, "opening": 80.0}},
            "B:parent": {"在建工程": {"audited": 50.0, "opening": 20.0}},
        }
        tb_loader = AsyncMock(side_effect=lambda db, s: child_tb[s.node_key])
        url = f"{BASE}/aggregate/{project.id}/{Y}?node_key=P:consol"
        body = {"standard": "soe", "section_id": "五-24-1", "row_idx": 0, "mode": "direct"}
        with patch.object(R, "_resolve_note_scope", AsyncMock(return_value=scope)), patch.object(R, "_load_tb_map", tb_loader):
            closing = await _post(app, url, {**body, "col_idx": 1})
            opening = await _post(app, url, {**body, "col_idx": 4})
            tb_loader.reset_mock()
            impairment = await _post(app, url, {**body, "col_idx": 2})
        assert (closing["value"], closing["count"]) == (150.0, 2)
        assert (opening["value"], opening["count"]) == (100.0, 2)
        assert (impairment["value"], impairment["count"]) == (None, 0)
        tb_loader.assert_not_called()
