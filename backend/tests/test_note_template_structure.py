"""附注「🔄 恢复模板结构」按当前表取模板表（spec note-pull-header-formula-closure，批 6 浏览器实测发现）。

原先 ``GET …/{note_section}/template-structure`` 恒返回章节第一张表：在「组合计提项目：应收中央企业客户」上点恢复，
表被换成「按账龄披露」的 3 列 12 行、金额只剩 2 格，2 分钟定时自动保存随即写库（2026-10-26【测试】甲 五、5）。
现行：按表名（表名比较键）找模板里的同一张表，当前表没有表名才按序号；找不到 404，不拿第一张表顶；返回逐列定义
（columns / _column_groups：多级表头与列身份）与行类型。纯函数用真种子；端点用 SQLite + 真路由 + 真鉴权。
"""
from __future__ import annotations

import copy
import json
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.routers import disclosure_notes
from app.services.note_section_catalog import section_applies_to_scope, template_json_path
from app.services.note_template_structure import pick_template_table, template_structure
from tests.test_note_text_batch_endpoints import _Actor

YEAR = 2025
COMBO = "组合计提项目：应收中央企业客户"


def _seed_tables(std: str, section: str) -> list[dict]:
    seed = json.loads(template_json_path(std).read_text(encoding="utf-8"))
    sec = next(s for s in seed["sections"] if s["section_number"] == section and section_applies_to_scope(s, "standalone"))
    return copy.deepcopy(sec["tables"])


class TestPickTemplateTable:

    def test_by_name_not_the_first_table(self):
        tables = _seed_tables("listed", "五、5")
        assert tables[0]["name"] == "按账龄披露" and tables.index(next(t for t in tables if t["name"] == COMBO)) > 0
        got = template_structure(pick_template_table(tables, table_name=COMBO, table_index=5))
        assert got["name"] == COMBO and len(got["headers"]) == 7
        assert [g["group"] for g in got["_column_groups"]] == ["期末余额", "上年年末余额"]
        assert [c.get("key") for c in got["columns"]][1:4] == ["end_amount", "end_provision", "end_loss_rate"]
        assert [r["label"] for r in got["rows"]] == ["1年以内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上", "合  计"]
        assert got["rows"][-1]["row_type"] == "total" and got["rows"][-1]["is_total"] is True
        assert all(r["values"] == [None] * 6 for r in got["rows"])

    def test_name_compare_ignores_enumerator_and_spaces(self):
        tables = [{"name": "（1）按账龄披露", "headers": ["账龄", "期末"]}, {"name": "（2）按 坏账准备计提方法分类", "headers": ["类别", "期末"]}]
        assert pick_template_table(tables, table_name="按坏账准备计提方法分类") is tables[1]

    def test_unknown_name_is_none_not_the_first_table(self):
        """当前表在模板里没有（用户自己加的表 / 改了表名）：不拿章节第一张表顶。"""
        assert pick_template_table(_seed_tables("listed", "五、5"), table_name="用户自己加的表", table_index=0) is None

    def test_same_name_twice_prefers_the_matching_index(self):
        tables = [{"name": "明细", "headers": ["a"]}, {"name": "其他", "headers": ["b"]}, {"name": "明细", "headers": ["c"]}]
        assert pick_template_table(tables, table_name="明细", table_index=2) is tables[2]
        assert pick_template_table(tables, table_name="明细", table_index=1) is tables[0]

    def test_without_name_by_index_and_without_hint_the_first(self):
        tables = [{"name": "A", "headers": ["x"]}, {"name": "B", "headers": ["y"]}]
        assert pick_template_table(tables, table_index=1) is tables[1]
        assert pick_template_table(tables, table_index=5) is None
        assert pick_template_table(tables) is tables[0]
        assert pick_template_table([]) is None

    def test_structure_requires_headers(self):
        assert template_structure({"name": "x", "headers": [], "rows": [{"label": "a"}]}) is None
        got = template_structure({"headers": ["项目", "金额"], "rows": [["库存现金"], {"label": "合计", "is_total": True}]})
        assert got["rows"] == [{"label": "库存现金", "values": [None], "is_total": False},
                               {"label": "合计", "values": [None], "is_total": True}]


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [User.__table__, Project.__table__, ProjectUser.__table__, StaffMember.__table__, ProjectAssignment.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    me, stranger, pid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with factory() as s:
        # 附注引擎按项目向导「基本信息」取模板口径（不是 projects.template_type）
        s.add(Project(id=pid, name="恢复模板结构_2025", client_name="恢复模板结构", template_type="listed",
                      report_scope="standalone", status=ProjectStatus.execution, audit_year=YEAR,
                      wizard_state={"steps": {"basic_info": {"data": {"template_type": "listed",
                                                                      "report_scope": "standalone"}}}}))
        await s.flush()
        s.add(ProjectUser(project_id=pid, user_id=me, role=ProjectUserRole.auditor, permission_level=PermissionLevel.edit))
        await s.commit()

    app = FastAPI()
    app.include_router(disclosure_notes.router)
    actor = {"user": _Actor(me)}

    async def _override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "url": f"/api/disclosure-notes/{pid}/{YEAR}/五、5/template-structure",
               "actor": actor, "stranger": stranger}
    await engine.dispose()


class TestTemplateStructureEndpoint:

    @pytest.mark.asyncio
    async def test_returns_the_requested_table(self, env):
        resp = await env["client"].get(env["url"], params={"table_name": COMBO, "table_index": 5})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == COMBO and len(body["headers"]) == 7 and len(body["rows"]) == 7
        assert len(body["_column_groups"]) == 2 and len(body["columns"]) == 7

    @pytest.mark.asyncio
    async def test_unknown_table_is_404_with_its_name(self, env):
        resp = await env["client"].get(env["url"], params={"table_name": "用户自己加的表", "table_index": 0})
        assert resp.status_code == 404 and "用户自己加的表" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_without_hint_keeps_the_first_table(self, env):
        resp = await env["client"].get(env["url"])
        assert resp.status_code == 200 and resp.json()["name"] == "按账龄披露"

    @pytest.mark.asyncio
    async def test_non_member_is_rejected(self, env):
        env["actor"]["user"] = _Actor(env["stranger"])
        resp = await env["client"].get(env["url"], params={"table_name": COMBO})
        assert resp.status_code == 403, resp.text
