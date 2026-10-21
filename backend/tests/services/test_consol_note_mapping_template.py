"""合并附注映射规则模板 CRUD + 七级匹配扩展测试。

spec: consol-note-mapping-reuse-and-reference-push Phase 2 Task 7
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
from app.models.consol_note_mapping_template_models import (
    ConsolNoteMappingRuleTemplate,
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
    ConsolNoteMappingRuleTemplate.__table__,
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


async def _create_rule_with_template(
    db: AsyncSession, project: Project, user: User,
    section_id: str = _SECTION, hash_val: str = _HASH_A,
    mappings: list | None = None,
) -> ConsolNoteMappingRule:
    """辅助：创建模板+版本+规则（模拟 confirm_mapping 的结果）。"""
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
             "aliases": [], "sort_order": 10, "row_type": "data",
             "recommended_account_codes": ["1001", "1002"]},
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
        version_number=1, mappings=mappings or _MAPPINGS,
        confirmed_by=user.id, is_active=True,
    )
    db.add(rule)
    await db.flush()
    return rule


# ═══════════════════════════════════════════════════════════════════════════════
# 1. promote_rule_to_template 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestPromoteRuleToTemplate:
    """规则提升为模板的 CRUD 测试。"""

    @pytest.mark.asyncio
    async def test_promote_success(self, db, project, user):
        """正常提升→返回 template_id + version_number=1。"""
        from app.services.consol_note_mapping_template_service import promote_rule_to_template

        rule = await _create_rule_with_template(db, project, user)
        result = await promote_rule_to_template(db, rule_id=rule.id, promoted_by=user.id)
        assert result["action"] == "promoted"
        assert result["version_number"] == 1
        assert result["mapping_count"] == 2
        # 源规则标记已提升
        await db.refresh(rule)
        assert rule.promoted_to_template_id is not None

    @pytest.mark.asyncio
    async def test_promote_inactive_rule_fails(self, db, project, user):
        """提升非活跃规则→400。"""
        from app.services.consol_note_mapping_template_service import (
            MappingTemplateError, promote_rule_to_template,
        )

        rule = await _create_rule_with_template(db, project, user)
        rule.is_active = False
        await db.flush()
        with pytest.raises(MappingTemplateError) as exc_info:
            await promote_rule_to_template(db, rule_id=rule.id, promoted_by=user.id)
        assert exc_info.value.status == 400
        assert exc_info.value.code == "RULE_INACTIVE"

    @pytest.mark.asyncio
    async def test_promote_incomplete_mapping_fails(self, db, project, user):
        """映射不完整（有 target_row_id=None 且非 ignore）→400。"""
        from app.services.consol_note_mapping_template_service import (
            MappingTemplateError, promote_rule_to_template,
        )

        incomplete_mappings = [
            {"source_label": "货币资金", "source_row_key": "k0",
             "target_row_id": None, "mapping_action": "map"},
        ]
        rule = await _create_rule_with_template(db, project, user, mappings=incomplete_mappings)
        with pytest.raises(MappingTemplateError) as exc_info:
            await promote_rule_to_template(db, rule_id=rule.id, promoted_by=user.id)
        assert exc_info.value.code == "INCOMPLETE_MAPPING"

    @pytest.mark.asyncio
    async def test_promote_ignore_action_ok(self, db, project, user):
        """mapping_action=ignore 且 target_row_id=None 不算不完整。"""
        from app.services.consol_note_mapping_template_service import promote_rule_to_template

        mappings = [
            {"source_label": "忽略行", "source_row_key": "k0",
             "target_row_id": None, "mapping_action": "ignore", "ignore_reason": "不适用"},
            {"source_label": "货币资金", "source_row_key": "k1",
             "target_row_id": "t1", "mapping_action": "map"},
        ]
        rule = await _create_rule_with_template(db, project, user, mappings=mappings)
        result = await promote_rule_to_template(db, rule_id=rule.id, promoted_by=user.id)
        assert result["action"] == "promoted"

    @pytest.mark.asyncio
    async def test_promote_duplicate_fails(self, db, project, user):
        """重复提升→409。"""
        from app.services.consol_note_mapping_template_service import (
            MappingTemplateError, promote_rule_to_template,
        )

        rule = await _create_rule_with_template(db, project, user)
        await promote_rule_to_template(db, rule_id=rule.id, promoted_by=user.id)
        with pytest.raises(MappingTemplateError) as exc_info:
            await promote_rule_to_template(db, rule_id=rule.id, promoted_by=user.id)
        assert exc_info.value.code == "ALREADY_PROMOTED"

    @pytest.mark.asyncio
    async def test_promote_same_hash_upgrades_version(self, db, project, user):
        """同 hash 第二次提升（不同规则）→升版 version_number=2。"""
        from app.services.consol_note_mapping_template_service import promote_rule_to_template

        rule1 = await _create_rule_with_template(db, project, user)
        r1 = await promote_rule_to_template(db, rule_id=rule1.id, promoted_by=user.id)
        assert r1["version_number"] == 1

        # 创建第二条规则（同 hash，用不同 section 的模板避免唯一约束冲突）
        rule2 = await _create_rule_with_template(
            db, project, user, section_id="五-1-2", hash_val=_HASH_A,
        )
        # 手动把 section_id 改回一致，只让底层 template 不同
        rule2.section_id = _SECTION
        await db.flush()
        r2 = await promote_rule_to_template(db, rule_id=rule2.id, promoted_by=user.id)
        assert r2["version_number"] == 2

    @pytest.mark.asyncio
    async def test_promote_not_found(self, db, user):
        """不存在的 rule_id→404。"""
        from app.services.consol_note_mapping_template_service import (
            MappingTemplateError, promote_rule_to_template,
        )
        with pytest.raises(MappingTemplateError) as exc_info:
            await promote_rule_to_template(db, rule_id=uuid4(), promoted_by=user.id)
        assert exc_info.value.status == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 2. find / list / deactivate 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestFindAndList:

    @pytest.mark.asyncio
    async def test_find_by_hash_exact(self, db, project, user):
        """精确 hash 查找命中。"""
        from app.services.consol_note_mapping_template_service import (
            find_template_for_hash, promote_rule_to_template,
        )
        rule = await _create_rule_with_template(db, project, user)
        await promote_rule_to_template(db, rule_id=rule.id, promoted_by=user.id)

        found = await find_template_for_hash(
            db, template_type="soe", section_id=_SECTION,
            source_structure_hash=_HASH_A,
        )
        assert found is not None
        assert found["source_structure_hash"] == _HASH_A

    @pytest.mark.asyncio
    async def test_find_by_hash_miss(self, db):
        """hash 不匹配→返回 None。"""
        from app.services.consol_note_mapping_template_service import find_template_for_hash
        found = await find_template_for_hash(
            db, template_type="soe", section_id=_SECTION,
            source_structure_hash=_HASH_B,
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_list_by_section(self, db, project, user):
        """按 section_id 列出。"""
        from app.services.consol_note_mapping_template_service import (
            list_templates, promote_rule_to_template,
        )
        rule = await _create_rule_with_template(db, project, user)
        await promote_rule_to_template(db, rule_id=rule.id, promoted_by=user.id)

        result = await list_templates(db, template_type="soe", section_id=_SECTION)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_deactivate(self, db, project, user):
        """停用后列表不返回。"""
        from app.services.consol_note_mapping_template_service import (
            deactivate_template, list_templates, promote_rule_to_template,
        )
        rule = await _create_rule_with_template(db, project, user)
        r = await promote_rule_to_template(db, rule_id=rule.id, promoted_by=user.id)

        await deactivate_template(db, template_id=r["template_id"])
        result = await list_templates(db, template_type="soe", section_id=_SECTION)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_deactivate_already_inactive(self, db, project, user):
        """重复停用→409。"""
        from app.services.consol_note_mapping_template_service import (
            MappingTemplateError, deactivate_template, promote_rule_to_template,
        )
        rule = await _create_rule_with_template(db, project, user)
        r = await promote_rule_to_template(db, rule_id=rule.id, promoted_by=user.id)
        await deactivate_template(db, template_id=r["template_id"])
        with pytest.raises(MappingTemplateError) as exc_info:
            await deactivate_template(db, template_id=r["template_id"])
        assert exc_info.value.code == "ALREADY_INACTIVE"

    @pytest.mark.asyncio
    async def test_account_code_hints_persisted(self, db, project, user):
        """提升时 recommended_account_codes 转存到 account_code_hints。"""
        from app.services.consol_note_mapping_template_service import (
            find_template_for_hash, promote_rule_to_template,
        )
        rule = await _create_rule_with_template(db, project, user)
        await promote_rule_to_template(db, rule_id=rule.id, promoted_by=user.id)

        found = await find_template_for_hash(
            db, template_type="soe", section_id=_SECTION,
            source_structure_hash=_HASH_A,
        )
        assert found is not None
        hints = found["account_code_hints"]
        assert "t1" in hints
        assert hints["t1"] == ["1001", "1002"]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. suggest_template_rows 七级匹配测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestSevenLevelMatching:
    """验证七级匹配的优先级顺序。"""

    def _groups(self, labels: list[str], hash_val: str = _HASH_A) -> list[dict]:
        return [{
            "hash": hash_val,
            "section_id": _SECTION,
            "source_rows": [{"label": l, "row_type": "data", "key": f"{l}#0"} for l in labels],
            "entities": [],
        }]

    def test_exact_beats_rule_template(self):
        """精确匹配（1级）优先于规则模板（3级）。"""
        from app.services.consol_note_detail_source_service import suggest_template_rows

        groups = self._groups(["货币资金"])
        template_rows = [{"target_row_id": "t1", "canonical_name": "货币资金",
                          "aliases": [], "sort_order": 10, "row_type": "data"}]
        rule_tmpl = [{"source_label": "货币资金", "suggested_target": {"target_row_id": "t_rule"},
                      "confidence": 0.92, "match_type": "rule_template"}]

        result = suggest_template_rows(
            groups, existing_template_rows=template_rows,
            rule_template_suggestions=rule_tmpl,
        )
        assert len(result) == 1
        assert result[0]["match_type"] == "exact"  # 精确匹配优先

    def test_rule_template_beats_fuzzy(self):
        """规则模板（3级）优先于模糊匹配（5级）。"""
        from app.services.consol_note_detail_source_service import suggest_template_rows

        groups = self._groups(["应收账款——关联方"])
        template_rows = [{"target_row_id": "t1", "canonical_name": "应收账款关联方",
                          "aliases": [], "sort_order": 10, "row_type": "data"}]
        rule_tmpl = [{"source_label": "应收账款——关联方",
                      "suggested_target": {"target_row_id": "t_rule"},
                      "confidence": 0.92, "match_type": "rule_template"}]

        result = suggest_template_rows(
            groups, existing_template_rows=template_rows,
            rule_template_suggestions=rule_tmpl,
        )
        assert len(result) == 1
        assert result[0]["match_type"] == "rule_template"

    def test_previous_year_used(self):
        """上年匹配（4级）在规则模板无匹配时命中。"""
        from app.services.consol_note_detail_source_service import suggest_template_rows

        groups = self._groups(["存货"])
        prev_year = [{"source_label": "存货",
                      "suggested_target": {"target_row_id": "t_prev"},
                      "confidence": 0.88, "match_type": "previous_year"}]

        result = suggest_template_rows(
            groups, previous_year_suggestions=prev_year,
        )
        assert len(result) == 1
        assert result[0]["match_type"] == "previous_year"
        assert result[0]["confidence"] == 0.88

    def test_fallback_to_manual(self):
        """七级全不匹配→manual。"""
        from app.services.consol_note_detail_source_service import suggest_template_rows

        groups = self._groups(["完全不存在的行名"])
        result = suggest_template_rows(groups)
        assert len(result) == 1
        assert result[0]["match_type"] == "manual"
        assert result[0]["confidence"] == 0.0

    def test_previous_year_beats_history(self):
        """上年匹配（4级）优先于项目历史（6级）。"""
        from app.services.consol_note_detail_source_service import suggest_template_rows

        groups = self._groups(["其他应收款"])
        prev_year = [{"source_label": "其他应收款",
                      "suggested_target": {"target_row_id": "t_prev"},
                      "confidence": 0.88}]
        history = [{"source_label": "其他应收款", "target_row_id": "t_hist"}]
        template_rows = [{"target_row_id": "t_hist", "canonical_name": "XXXX",
                          "aliases": [], "sort_order": 10, "row_type": "data"}]

        result = suggest_template_rows(
            groups, existing_template_rows=template_rows,
            previous_year_suggestions=prev_year, history_mappings=history,
        )
        assert len(result) == 1
        assert result[0]["match_type"] == "previous_year"

    def test_backward_compatible_no_new_params(self):
        """不传新参数时退化为原五级——保证兼容。"""
        from app.services.consol_note_detail_source_service import suggest_template_rows

        groups = self._groups(["货币资金"])
        template_rows = [{"target_row_id": "t1", "canonical_name": "货币资金",
                          "aliases": [], "sort_order": 10, "row_type": "data"}]
        result = suggest_template_rows(groups, existing_template_rows=template_rows)
        assert len(result) == 1
        assert result[0]["match_type"] == "exact"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. find_previous_year_rules 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestFindPreviousYearRules:

    @pytest.mark.asyncio
    async def test_same_group_match(self, db, project, prev_year_project, user):
        """同集团上年项目有匹配规则→返回 previous_year 建议。"""
        from app.services.consol_note_detail_source_service import find_previous_year_rules

        # 上年项目创建规则
        await _create_rule_with_template(db, prev_year_project, user,
                                         section_id=_SECTION, hash_val=_HASH_A)
        result = await find_previous_year_rules(
            db, consol_project_id=project.id,
            section_id=_SECTION, source_structure_hash=_HASH_A,
        )
        assert len(result) >= 1
        assert result[0]["match_type"] == "previous_year"
        assert result[0]["confidence"] == 0.88

    @pytest.mark.asyncio
    async def test_cross_group_no_match(self, db, project, other_group_project, user):
        """跨集团项目不匹配→返回空。"""
        from app.services.consol_note_detail_source_service import find_previous_year_rules

        await _create_rule_with_template(db, other_group_project, user,
                                         section_id=_SECTION, hash_val=_HASH_A)
        result = await find_previous_year_rules(
            db, consol_project_id=project.id,
            section_id=_SECTION, source_structure_hash=_HASH_A,
        )
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_no_previous_project(self, db, project, user):
        """无上年项目→返回空。"""
        from app.services.consol_note_detail_source_service import find_previous_year_rules

        result = await find_previous_year_rules(
            db, consol_project_id=project.id,
            section_id=_SECTION, source_structure_hash=_HASH_A,
        )
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_hash_mismatch(self, db, project, prev_year_project, user):
        """上年项目 hash 不匹配→返回空。"""
        from app.services.consol_note_detail_source_service import find_previous_year_rules

        await _create_rule_with_template(db, prev_year_project, user,
                                         section_id=_SECTION, hash_val=_HASH_B)
        result = await find_previous_year_rules(
            db, consol_project_id=project.id,
            section_id=_SECTION, source_structure_hash=_HASH_A,
        )
        assert len(result) == 0
