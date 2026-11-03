"""子企业单体附注保存 → 合并附注章节标「待更新」（``on_note_section_saved``）。

原 spec consol-note-mapping-reuse-and-reference-push 的值指纹 / 值确认 / 结构锁用例随 V202 退役删除（spec
note-pull-followup-closure R16，V208 删表）；只留在用的 is_stale 标记。
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_note_mapping_models import (
    ConsolNoteDetailTemplate,
    ConsolNoteDetailTemplateVersion,
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)
from app.models.core import Project, User

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, poolclass=StaticPool)
_SESSION = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)
_TABLES = [
    User.__table__, Project.__table__,
    ConsolNoteDetailTemplate.__table__, ConsolNoteDetailTemplateVersion.__table__,
    ConsolNoteTemplateBinding.__table__,
    ConsolNoteMappingRule.__table__, ConsolNoteMappingBinding.__table__,
    ConsolNoteData.__table__,
]
_HASH_A = "a" * 64
_SECTION = "五-1-1"
_YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _ENGINE.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=_TABLES))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    async with _SESSION() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(id=uuid4(), username="tester", email="t@test.com",
             hashed_password="fakehash", role="partner")
    db.add(u)
    await db.flush()
    return u


async def _project(db: AsyncSession, name: str) -> Project:
    p = Project(id=uuid4(), name=name, client_name="TestGroup", company_code=name,
                audit_year=_YEAR, audit_period_end=date(_YEAR, 12, 31))
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def consol_project(db: AsyncSession) -> Project:
    return await _project(db, "G_2025_consol")


@pytest_asyncio.fixture
async def entity_project(db: AsyncSession) -> Project:
    return await _project(db, "SubCo_2025")


async def _version(db: AsyncSession, user: User):
    """本章节的明细模板版本（同一用户同一章节只能有一个模板，多个合并项目共用）。"""
    existing = (await db.execute(sa.select(ConsolNoteDetailTemplateVersion.id).join(
        ConsolNoteDetailTemplate, ConsolNoteDetailTemplate.id == ConsolNoteDetailTemplateVersion.template_id,
    ).where(ConsolNoteDetailTemplate.section_id == _SECTION))).scalar_one_or_none()
    if existing is not None:
        return existing
    tmpl = ConsolNoteDetailTemplate(template_type="soe", section_id=_SECTION, name="T",
                                    visibility="project", created_by=user.id)
    db.add(tmpl)
    await db.flush()
    ver = ConsolNoteDetailTemplateVersion(template_id=tmpl.id, version_number=1, rows=[], created_by=user.id)
    db.add(ver)
    await db.flush()
    return ver.id


async def _bind(db: AsyncSession, consol: Project, entity: Project, user: User, *, status: str = "confirmed") -> None:
    """合并项目 ``consol`` 本章节把 ``entity`` 作为来源的明细映射绑定。"""
    version_id = await _version(db, user)
    rule = ConsolNoteMappingRule(project_id=consol.id, section_id=_SECTION, template_version_id=version_id,
                                 source_structure_hash=_HASH_A, version_number=1, mappings=[], is_active=True)
    db.add(rule)
    await db.flush()
    db.add(ConsolNoteMappingBinding(project_id=consol.id, section_id=_SECTION, entity_node_key="sub_1",
                                    entity_project_id=entity.id, rule_id=rule.id,
                                    bound_source_hash=_HASH_A, status=status))
    await db.flush()


async def _note(db: AsyncSession, project: Project, node_key: str | None, *, section: str = _SECTION,
                year: int = _YEAR) -> ConsolNoteData:
    row = ConsolNoteData(project_id=project.id, year=year, section_id=section, node_key=node_key,
                         data={"rows": []}, is_stale=False)
    db.add(row)
    await db.flush()
    return row


async def _stale_flags(db: AsyncSession, *rows: ConsolNoteData) -> list[bool]:
    ids = [r.id for r in rows]
    found = dict((await db.execute(sa.select(ConsolNoteData.id, ConsolNoteData.is_stale)
                                   .where(ConsolNoteData.id.in_(ids)))).all())
    return [bool(found[i]) for i in ids]


class TestOnNoteSectionSaved:

    @pytest.mark.asyncio
    async def test_no_binding_returns_none(self, db, entity_project):
        """没有绑定 → None（不标任何章节）。"""
        from app.services.consol_note_value_change_service import on_note_section_saved

        assert await on_note_section_saved(db, entity_project_id=entity_project.id,
                                           section_id=_SECTION, year=_YEAR) is None

    @pytest.mark.asyncio
    async def test_with_binding_marks_every_node_stale(self, db, consol_project, entity_project, user):
        """有绑定 → 回报受影响合并项目，并把该合并项目本章节本年度的全部节点（含项目级旧行）标 is_stale；
        别的章节 / 别的年度不动。"""
        from app.services.consol_note_value_change_service import on_note_section_saved

        await _bind(db, consol_project, entity_project, user)
        root = await _note(db, consol_project, "root")
        child = await _note(db, consol_project, "sub_1")
        legacy = await _note(db, consol_project, None)
        other_section = await _note(db, consol_project, "root", section="五-2")
        other_year = await _note(db, consol_project, "root", year=_YEAR - 1)

        result = await on_note_section_saved(db, entity_project_id=entity_project.id,
                                             section_id=_SECTION, year=_YEAR)
        assert result == {"affected_projects": [{
            "consol_project_id": str(consol_project.id), "section_id": _SECTION,
            "entity_node_key": "sub_1", "entity_project_id": str(entity_project.id),
        }]}
        assert await _stale_flags(db, root, child, legacy, other_section, other_year) == [True, True, True, False, False]

    @pytest.mark.asyncio
    async def test_excluded_binding_ignored(self, db, consol_project, entity_project, user):
        """只看已确认 / 结构已变化的绑定：用户排除了的企业不触发标记。"""
        from app.services.consol_note_value_change_service import on_note_section_saved

        await _bind(db, consol_project, entity_project, user, status="excluded")
        root = await _note(db, consol_project, "root")
        assert await on_note_section_saved(db, entity_project_id=entity_project.id,
                                           section_id=_SECTION, year=_YEAR) is None
        assert await _stale_flags(db, root) == [False]

    @pytest.mark.asyncio
    async def test_consol_project_filter(self, db, consol_project, entity_project, user):
        """给了 consol_project_ids 只处理这些合并项目（处理器按章节映射算出的受影响项目）。"""
        from app.services.consol_note_value_change_service import on_note_section_saved

        other_consol = await _project(db, "G2_2025_consol")
        await _bind(db, consol_project, entity_project, user)
        await _bind(db, other_consol, entity_project, user)
        mine = await _note(db, consol_project, "root")
        theirs = await _note(db, other_consol, "root")

        result = await on_note_section_saved(db, entity_project_id=entity_project.id, section_id=_SECTION,
                                             year=_YEAR, consol_project_ids=[other_consol.id])
        assert [a["consol_project_id"] for a in result["affected_projects"]] == [str(other_consol.id)]
        assert await _stale_flags(db, mine, theirs) == [False, True]
