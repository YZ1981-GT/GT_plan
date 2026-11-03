"""合并附注明细映射建议：上年同集团规则 + 匹配优先级。

原 ``test_consol_note_mapping_template.py`` 的规则模板库部分随 V202 退役删除（spec note-pull-followup-closure
R16）；与 V202 无关、仍在用的「上年规则」与匹配优先级用例移到这里。
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
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
]
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_SECTION = "五-1-1"
_MAPPINGS = [
    {"source_label": "货币资金", "source_row_key": "货币资金#0",
     "target_row_id": "t1", "mapping_action": "map"},
    {"source_label": "合计", "source_row_key": "合计#0",
     "target_row_id": "t2", "mapping_action": "map"},
]


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


@pytest_asyncio.fixture
async def project(db: AsyncSession) -> Project:
    p = Project(id=uuid4(), name="G_2025", client_name="TestGroup",
                company_code="TG", ultimate_company_code="TG001",
                audit_year=2025, audit_period_end=date(2025, 12, 31))
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def prev_year_project(db: AsyncSession) -> Project:
    """上年同集团项目（client_name 相同）。"""
    p = Project(id=uuid4(), name="G_2024", client_name="TestGroup",
                company_code="TG", ultimate_company_code="TG001",
                audit_year=2024, audit_period_end=date(2024, 12, 31))
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def other_group_project(db: AsyncSession) -> Project:
    """另一个集团的项目（client_name 不同）。"""
    p = Project(id=uuid4(), name="H_2024", client_name="OtherGroup",
                company_code="OG", ultimate_company_code="OG001",
                audit_year=2024, audit_period_end=date(2024, 12, 31))
    db.add(p)
    await db.flush()
    return p


async def _create_rule(
    db: AsyncSession, project: Project, user: User,
    section_id: str = _SECTION, hash_val: str = _HASH_A,
) -> ConsolNoteMappingRule:
    """辅助：建模板 + 版本 + 已确认规则（模拟 confirm_mapping 的结果）。"""
    tmpl = ConsolNoteDetailTemplate(
        template_type="soe", section_id=section_id, name="测试模板",
        visibility="project", created_by=user.id,
    )
    db.add(tmpl)
    await db.flush()
    ver = ConsolNoteDetailTemplateVersion(
        template_id=tmpl.id, version_number=1,
        rows=[
            {"target_row_id": "t1", "canonical_name": "货币资金",
             "aliases": [], "sort_order": 10, "row_type": "data"},
            {"target_row_id": "t2", "canonical_name": "合计",
             "aliases": [], "sort_order": 20, "row_type": "total"},
        ],
        change_note="初始", created_by=user.id,
    )
    db.add(ver)
    await db.flush()
    rule = ConsolNoteMappingRule(
        project_id=project.id, section_id=section_id,
        template_version_id=ver.id, source_structure_hash=hash_val,
        version_number=1, mappings=_MAPPINGS,
        confirmed_by=user.id, is_active=True,
    )
    db.add(rule)
    await db.flush()
    return rule


class TestMatchPriority:
    """匹配优先级（规则模板一级已退役）。"""

    def _groups(self, labels: list[str], hash_val: str = _HASH_A) -> list[dict]:
        return [{
            "hash": hash_val,
            "section_id": _SECTION,
            "source_rows": [{"label": lb, "row_type": "data", "key": f"{lb}#0"} for lb in labels],
            "entities": [],
        }]

    def test_rule_template_level_retired(self):
        """规则模板一级随 V202 退役：不再接受 rule_template_suggestions（传了即 TypeError，调用方漏改会当场暴露）。"""
        from app.services.consol_note_detail_source_service import suggest_template_rows

        with pytest.raises(TypeError):
            suggest_template_rows(self._groups(["货币资金"]), rule_template_suggestions=[])  # type: ignore[call-arg]

    def test_previous_year_used(self):
        """上年匹配在无精确 / 别名命中时命中。"""
        from app.services.consol_note_detail_source_service import suggest_template_rows

        prev_year = [{"source_label": "存货",
                      "suggested_target": {"target_row_id": "t_prev"},
                      "confidence": 0.88, "match_type": "previous_year"}]
        result = suggest_template_rows(self._groups(["存货"]), previous_year_suggestions=prev_year)
        assert len(result) == 1
        assert result[0]["match_type"] == "previous_year"
        assert result[0]["confidence"] == 0.88

    def test_fallback_to_manual(self):
        """全不匹配 → manual。"""
        from app.services.consol_note_detail_source_service import suggest_template_rows

        result = suggest_template_rows(self._groups(["完全不存在的行名"]))
        assert len(result) == 1
        assert result[0]["match_type"] == "manual"
        assert result[0]["confidence"] == 0.0

    def test_previous_year_beats_history(self):
        """上年匹配优先于项目历史。"""
        from app.services.consol_note_detail_source_service import suggest_template_rows

        prev_year = [{"source_label": "其他应收款",
                      "suggested_target": {"target_row_id": "t_prev"},
                      "confidence": 0.88}]
        history = [{"source_label": "其他应收款", "target_row_id": "t_hist"}]
        template_rows = [{"target_row_id": "t_hist", "canonical_name": "XXXX",
                          "aliases": [], "sort_order": 10, "row_type": "data"}]
        result = suggest_template_rows(
            self._groups(["其他应收款"]), existing_template_rows=template_rows,
            previous_year_suggestions=prev_year, history_mappings=history,
        )
        assert len(result) == 1
        assert result[0]["match_type"] == "previous_year"

    def test_exact_without_optional_inputs(self):
        """不传上年 / 历史时按行名精确匹配。"""
        from app.services.consol_note_detail_source_service import suggest_template_rows

        template_rows = [{"target_row_id": "t1", "canonical_name": "货币资金",
                          "aliases": [], "sort_order": 10, "row_type": "data"}]
        result = suggest_template_rows(self._groups(["货币资金"]), existing_template_rows=template_rows)
        assert len(result) == 1
        assert result[0]["match_type"] == "exact"


class TestFindPreviousYearRules:

    @pytest.mark.asyncio
    async def test_same_group_match(self, db, project, prev_year_project, user):
        """同集团上年项目有匹配规则 → 返回 previous_year 建议。"""
        from app.services.consol_note_detail_source_service import find_previous_year_rules

        await _create_rule(db, prev_year_project, user, section_id=_SECTION, hash_val=_HASH_A)
        result = await find_previous_year_rules(
            db, consol_project_id=project.id, section_id=_SECTION, source_structure_hash=_HASH_A,
        )
        assert len(result) >= 1
        assert result[0]["match_type"] == "previous_year"
        assert result[0]["confidence"] == 0.88

    @pytest.mark.asyncio
    async def test_cross_group_no_match(self, db, project, other_group_project, user):
        """跨集团项目不匹配 → 返回空。"""
        from app.services.consol_note_detail_source_service import find_previous_year_rules

        await _create_rule(db, other_group_project, user, section_id=_SECTION, hash_val=_HASH_A)
        result = await find_previous_year_rules(
            db, consol_project_id=project.id, section_id=_SECTION, source_structure_hash=_HASH_A,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_no_previous_project(self, db, project, user):
        """无上年项目 → 返回空。"""
        from app.services.consol_note_detail_source_service import find_previous_year_rules

        result = await find_previous_year_rules(
            db, consol_project_id=project.id, section_id=_SECTION, source_structure_hash=_HASH_A,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_hash_mismatch(self, db, project, prev_year_project, user):
        """上年项目 hash 不匹配 → 返回空。"""
        from app.services.consol_note_detail_source_service import find_previous_year_rules

        await _create_rule(db, prev_year_project, user, section_id=_SECTION, hash_val=_HASH_B)
        result = await find_previous_year_rules(
            db, consol_project_id=project.id, section_id=_SECTION, source_structure_hash=_HASH_A,
        )
        assert result == []
