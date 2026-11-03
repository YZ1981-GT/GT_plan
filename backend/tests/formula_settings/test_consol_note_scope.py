"""consol_note 域作用范围只含合并项目（ADR-CNS-01）。

测试目标：
* scope_of 四种组合（soe/listed × consolidated/standalone）+ 空 report_scope
* list_projects("consol_note") 只返回合并项目
* get_project 对单体项目返回 None
* require_project：单体 → 422 DomainNotApplicable，不存在 → 404 NotFound
* apply_to_projects：单体目标进 skipped
* propagate_consol_note：非合并项目返回 {"skipped": "not_consolidated"}
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ProjectStatus
from app.services.formula_settings.definitions import get_spec
from app.services.formula_settings.errors import DomainNotApplicable, NotFound
from app.services.formula_settings.projects import ProjectInfo, get_project, list_projects, scope_of
from app.services.formula_settings.project_ops import require_project

from ._env import add_project, add_user, make_db

DOMAIN = "consol_note"


# ── scope_of 纯函数测试 ─────────────────────────────────────────────────────


class TestScopeOf:
    """scope_of("consol_note", ...) 四象限 + 空值。"""

    def test_consolidated_soe(self):
        assert scope_of(DOMAIN, "soe", "consolidated") == "soe"

    def test_consolidated_listed(self):
        assert scope_of(DOMAIN, "listed", "consolidated") == "listed"

    def test_standalone_soe(self):
        assert scope_of(DOMAIN, "soe", "standalone") is None

    def test_standalone_listed(self):
        assert scope_of(DOMAIN, "listed", "standalone") is None

    def test_null_report_scope(self):
        """report_scope 为空 → 按非合并处理（None）。"""
        assert scope_of(DOMAIN, "soe", None) is None

    def test_null_template_type_consolidated(self):
        """template_type 为空但 report_scope='consolidated' → 缺省 soe。"""
        assert scope_of(DOMAIN, None, "consolidated") == "soe"

    def test_null_both(self):
        assert scope_of(DOMAIN, None, None) is None

    def test_unknown_template_type_consolidated(self):
        """template_type 不认识但是合并项目 → 缺省 soe。"""
        assert scope_of(DOMAIN, "xyz", "consolidated") == "soe"

    def test_note_domain_unchanged(self):
        """note 域仍走 template_type 口径，不受 report_scope 影响。"""
        assert scope_of("note", "soe", "standalone") == "soe"
        assert scope_of("note", "soe", "consolidated") == "soe"

    def test_report_domain_unchanged(self):
        """report 域仍走 standard 口径。"""
        assert scope_of("report", "soe", "standalone") == "soe_standalone"

    def test_spec_scope_kind(self):
        assert get_spec(DOMAIN).scope_kind == "consolidated_template_type"


# ── list_projects / get_project（SQLite）──────────────────────────────────────


@pytest.mark.asyncio
async def test_list_projects_only_consolidated():
    """list_projects("consol_note") 只返回合并项目。"""
    async with make_db() as factory, factory() as db:
        pid_c = await add_project(db, "合并项目", report_scope="consolidated")
        pid_s1 = await add_project(db, "单体项目1", report_scope="standalone")
        pid_s2 = await add_project(db, "单体项目2")  # 默认 standalone
        await db.flush()

        result = await list_projects(db, DOMAIN)
        ids = {p.id for p in result}
        assert pid_c in ids
        assert pid_s1 not in ids
        assert pid_s2 not in ids


@pytest.mark.asyncio
async def test_list_projects_with_scope_filter():
    """scope='soe' 也只返回合并项目中 soe 的。"""
    async with make_db() as factory, factory() as db:
        pid_c = await add_project(db, "合并SOE", template_type="soe", report_scope="consolidated")
        pid_cl = await add_project(db, "合并Listed", template_type="listed", report_scope="consolidated")
        pid_s = await add_project(db, "单体SOE", template_type="soe", report_scope="standalone")
        await db.flush()

        result = await list_projects(db, DOMAIN, scope="soe")
        ids = {p.id for p in result}
        assert pid_c in ids
        assert pid_cl not in ids  # listed 不匹配 soe scope
        assert pid_s not in ids   # 单体


@pytest.mark.asyncio
async def test_list_projects_wildcard_scope():
    """scope='*' 也跳过不适用的（单体）项目。"""
    async with make_db() as factory, factory() as db:
        pid_c = await add_project(db, "合并项目", report_scope="consolidated")
        pid_s = await add_project(db, "单体项目", report_scope="standalone")
        await db.flush()

        result = await list_projects(db, DOMAIN, scope="*")
        ids = {p.id for p in result}
        assert pid_c in ids
        assert pid_s not in ids


@pytest.mark.asyncio
async def test_list_projects_by_ids():
    """指定 ids 时也过滤单体。"""
    async with make_db() as factory, factory() as db:
        pid_c = await add_project(db, "合并项目", report_scope="consolidated")
        pid_s = await add_project(db, "单体项目", report_scope="standalone")
        await db.flush()

        result = await list_projects(db, DOMAIN, ids=[pid_c, pid_s])
        ids = {p.id for p in result}
        assert pid_c in ids
        assert pid_s not in ids


@pytest.mark.asyncio
async def test_list_projects_null_report_scope():
    """report_scope 为空的项目不在 consol_note 域内。"""
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "空scope项目", report_scope="standalone")
        # 直接把 report_scope 改为 NULL
        from app.models.core import Project
        await db.execute(sa.update(Project).where(Project.id == pid).values(report_scope=None))
        await db.flush()

        result = await list_projects(db, DOMAIN)
        assert all(p.id != pid for p in result)


@pytest.mark.asyncio
async def test_get_project_consolidated():
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "合并项目", report_scope="consolidated")
        await db.flush()

        p = await get_project(db, DOMAIN, pid)
        assert p is not None
        assert p.scope == "soe"


@pytest.mark.asyncio
async def test_get_project_standalone_returns_none():
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "单体项目", report_scope="standalone")
        await db.flush()

        p = await get_project(db, DOMAIN, pid)
        assert p is None


@pytest.mark.asyncio
async def test_get_project_nonexistent_returns_none():
    async with make_db() as factory, factory() as db:
        p = await get_project(db, DOMAIN, uuid.uuid4())
        assert p is None


# ── require_project 错误区分 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_require_project_consolidated_ok():
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "合并项目", report_scope="consolidated")
        await db.flush()

        p = await require_project(db, DOMAIN, pid, writable=False)
        assert p.id == pid


@pytest.mark.asyncio
async def test_require_project_standalone_422():
    """单体项目 → 422 DomainNotApplicable。"""
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "单体项目", report_scope="standalone")
        await db.flush()

        with pytest.raises(DomainNotApplicable) as exc_info:
            await require_project(db, DOMAIN, pid, writable=False)
        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "FORMULA_DOMAIN_NOT_APPLICABLE"
        assert "不是合并项目" in str(exc_info.value)


@pytest.mark.asyncio
async def test_require_project_nonexistent_404():
    """不存在的项目 → 404 NotFound。"""
    async with make_db() as factory, factory() as db:
        with pytest.raises(NotFound) as exc_info:
            await require_project(db, DOMAIN, uuid.uuid4(), writable=False)
        assert exc_info.value.status_code == 404


# ── note 域不受影响（对照） ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_note_domain_list_projects_includes_standalone():
    """note 域仍然包含单体项目（对照 consol_note 的行为变化）。"""
    async with make_db() as factory, factory() as db:
        pid_c = await add_project(db, "合并项目", report_scope="consolidated")
        pid_s = await add_project(db, "单体项目", report_scope="standalone")
        await db.flush()

        result = await list_projects(db, "note")
        ids = {p.id for p in result}
        assert pid_c in ids
        assert pid_s in ids
