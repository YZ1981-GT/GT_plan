"""R1 Task 22 测试：独立性声明服务 + gate 规则

覆盖：
1. IndependenceService CRUD + submit
2. IndependenceDeclarationCompleteRule gate 规则
3. 问题模板读取
4. legacy 兼容逻辑

Validates: Requirements 10 (refinement-round1-review-closure)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.independence_models  # noqa: F401
import app.models.extension_models  # noqa: F401
import app.models.staff_models  # noqa: F401
from app.models.base import Base
from app.models.independence_models import IndependenceDeclaration
from app.models.extension_models import SignatureRecord
from app.services.independence_service import IndependenceService, _check_conflict_answers

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

FAKE_PROJECT_ID = uuid.uuid4()
FAKE_USER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# 问题模板测试
# ---------------------------------------------------------------------------


class TestGetQuestions:
    def test_returns_20_questions(self):
        """问题模板应返回 20 条。"""
        questions = IndependenceService.get_questions()
        assert len(questions) == 20

    def test_question_structure(self):
        """每条问题应有 id/category/question/answer_type 字段。"""
        questions = IndependenceService.get_questions()
        for q in questions:
            assert "id" in q
            assert "category" in q
            assert "question" in q
            assert "answer_type" in q

    def test_question_ids_unique(self):
        """问题 ID 应唯一。"""
        questions = IndependenceService.get_questions()
        ids = [q["id"] for q in questions]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# CRUD 测试
# ---------------------------------------------------------------------------


class TestIndependenceServiceCRUD:
    @pytest.mark.asyncio
    async def test_create_declaration(self, db_session: AsyncSession):
        """创建声明应返回 draft 状态。"""
        decl = await IndependenceService.create_declaration(
            db=db_session,
            project_id=FAKE_PROJECT_ID,
            declarant_id=FAKE_USER_ID,
            year=2025,
        )
        assert decl.status == "draft"
        assert decl.project_id == FAKE_PROJECT_ID
        assert decl.declarant_id == FAKE_USER_ID
        assert decl.declaration_year == 2025

    @pytest.mark.asyncio
    async def test_list_declarations(self, db_session: AsyncSession):
        """列表应返回已创建的声明。"""
        await IndependenceService.create_declaration(
            db=db_session, project_id=FAKE_PROJECT_ID,
            declarant_id=FAKE_USER_ID, year=2025,
        )
        await db_session.flush()
        results = await IndependenceService.list_declarations(
            db=db_session, project_id=FAKE_PROJECT_ID,
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_declarations_filter_by_year(self, db_session: AsyncSession):
        """按年份筛选应只返回匹配的声明。"""
        await IndependenceService.create_declaration(
            db=db_session, project_id=FAKE_PROJECT_ID,
            declarant_id=FAKE_USER_ID, year=2025,
        )
        await IndependenceService.create_declaration(
            db=db_session, project_id=FAKE_PROJECT_ID,
            declarant_id=uuid.uuid4(), year=2024,
        )
        await db_session.flush()
        results = await IndependenceService.list_declarations(
            db=db_session, project_id=FAKE_PROJECT_ID, year=2025,
        )
        assert len(results) == 1
        assert results[0].declaration_year == 2025

    @pytest.mark.asyncio
    async def test_update_declaration(self, db_session: AsyncSession):
        """更新 draft 声明的 answers。"""
        decl = await IndependenceService.create_declaration(
            db=db_session, project_id=FAKE_PROJECT_ID,
            declarant_id=FAKE_USER_ID, year=2025,
        )
        await db_session.flush()
        answers = {"IND-01": {"answer": "no"}, "IND-02": {"answer": "no"}}
        updated = await IndependenceService.update_declaration(
            db=db_session, declaration_id=decl.id, answers=answers,
        )
        assert updated is not None
        assert updated.answers == answers

    @pytest.mark.asyncio
    async def test_update_non_draft_raises(self, db_session: AsyncSession):
        """更新非 draft 状态应抛出 ValueError。"""
        decl = await IndependenceService.create_declaration(
            db=db_session, project_id=FAKE_PROJECT_ID,
            declarant_id=FAKE_USER_ID, year=2025,
        )
        decl.status = "submitted"
        await db_session.flush()
        with pytest.raises(ValueError, match="只能更新 draft"):
            await IndependenceService.update_declaration(
                db=db_session, declaration_id=decl.id,
                answers={"IND-01": {"answer": "no"}},
            )

    @pytest.mark.asyncio
    async def test_submit_declaration(self, db_session: AsyncSession):
        """提交声明应切换状态并创建 SignatureRecord。"""
        decl = await IndependenceService.create_declaration(
            db=db_session, project_id=FAKE_PROJECT_ID,
            declarant_id=FAKE_USER_ID, year=2025,
        )
        decl.answers = {"IND-01": {"answer": "no"}, "IND-02": {"answer": "no"}}
        await db_session.flush()

        with patch("app.services.audit_logger_enhanced.audit_logger") as mock_logger:
            mock_logger.log_action = AsyncMock(return_value={})
            submitted = await IndependenceService.submit_declaration(
                db=db_session, declaration_id=decl.id, signer_id=FAKE_USER_ID,
            )
        assert submitted.status == "submitted"
        assert submitted.signed_at is not None
        assert submitted.signature_record_id is not None

    @pytest.mark.asyncio
    async def test_submit_with_conflict_answer(self, db_session: AsyncSession):
        """有利益冲突答案时应切换到 pending_conflict_review。"""
        decl = await IndependenceService.create_declaration(
            db=db_session, project_id=FAKE_PROJECT_ID,
            declarant_id=FAKE_USER_ID, year=2025,
        )
        decl.answers = {"IND-01": {"answer": "yes", "detail": "持有股票"}}
        await db_session.flush()

        with patch("app.services.audit_logger_enhanced.audit_logger") as mock_logger:
            mock_logger.log_action = AsyncMock(return_value={})
            submitted = await IndependenceService.submit_declaration(
                db=db_session, declaration_id=decl.id, signer_id=FAKE_USER_ID,
            )
        assert submitted.status == "pending_conflict_review"


# ---------------------------------------------------------------------------
# 冲突检测辅助函数测试
# ---------------------------------------------------------------------------


class TestCheckConflictAnswers:
    def test_no_answers(self):
        assert _check_conflict_answers(None) is False
        assert _check_conflict_answers({}) is False

    def test_all_no(self):
        answers = {"IND-01": {"answer": "no"}, "IND-02": {"answer": "no"}}
        assert _check_conflict_answers(answers) is False

    def test_has_yes(self):
        answers = {"IND-01": {"answer": "yes"}, "IND-02": {"answer": "no"}}
        assert _check_conflict_answers(answers) is True

    def test_bool_true(self):
        answers = {"IND-01": True}
        assert _check_conflict_answers(answers) is True

    def test_bool_false(self):
        answers = {"IND-01": False, "IND-02": False}
        assert _check_conflict_answers(answers) is False


# ---------------------------------------------------------------------------
# Gate 规则测试
# ---------------------------------------------------------------------------


class TestIndependenceDeclarationCompleteRule:
    @pytest.mark.asyncio
    async def test_no_project_id_returns_none(self, db_session: AsyncSession):
        """无 project_id 时不阻断。"""
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule

        rule = IndependenceDeclarationCompleteRule()
        result = await rule.check(db_session, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_no_assignments_returns_none(self, db_session: AsyncSession):
        """无核心角色分配时不阻断。"""
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule

        rule = IndependenceDeclarationCompleteRule()
        result = await rule.check(db_session, {"project_id": FAKE_PROJECT_ID})
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_declarations_blocks(self, db_session: AsyncSession):
        """有核心角色但缺少声明时应阻断。"""
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule
        from app.models.staff_models import ProjectAssignment

        # 创建项目分配
        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=FAKE_PROJECT_ID,
            staff_id=FAKE_USER_ID,
            role="signing_partner",
            is_deleted=False,
        )
        db_session.add(assignment)
        await db_session.flush()

        rule = IndependenceDeclarationCompleteRule()
        result = await rule.check(db_session, {"project_id": FAKE_PROJECT_ID})
        assert result is not None
        assert result.rule_code == "R1-INDEPENDENCE"
        assert result.error_code == "INDEPENDENCE_DECLARATION_INCOMPLETE"
        assert "signing_partner" in result.message

    @pytest.mark.asyncio
    async def test_all_submitted_passes(self, db_session: AsyncSession):
        """所有核心角色都已提交时不阻断。"""
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule
        from app.models.staff_models import ProjectAssignment

        staff_id = uuid.uuid4()
        # 创建项目分配
        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=FAKE_PROJECT_ID,
            staff_id=staff_id,
            role="signing_partner",
            is_deleted=False,
        )
        db_session.add(assignment)

        # 创建已提交的声明
        decl = IndependenceDeclaration(
            id=uuid.uuid4(),
            project_id=FAKE_PROJECT_ID,
            declarant_id=staff_id,
            declaration_year=2025,
            status="submitted",
        )
        db_session.add(decl)
        await db_session.flush()

        rule = IndependenceDeclarationCompleteRule()
        result = await rule.check(db_session, {"project_id": FAKE_PROJECT_ID})
        assert result is None


# ---------------------------------------------------------------------------
# declaration_to_dict 测试
# ---------------------------------------------------------------------------


class TestDeclarationToDict:
    def test_basic_conversion(self):
        """to_dict 应正确转换所有字段。"""
        decl = IndependenceDeclaration(
            id=uuid.uuid4(),
            project_id=FAKE_PROJECT_ID,
            declarant_id=FAKE_USER_ID,
            declaration_year=2025,
            status="draft",
            answers={"IND-01": {"answer": "no"}},
            attachments=[],
        )
        result = IndependenceService.declaration_to_dict(decl)
        assert result["status"] == "draft"
        assert result["declaration_year"] == 2025
        assert result["answers"] == {"IND-01": {"answer": "no"}}



# ---------------------------------------------------------------------------
# Batch 2-3: legacy 宽容期 tests (R1 Bug Fix 4 retrospective)
# ---------------------------------------------------------------------------


class TestIndependenceLegacyGracePeriod:
    """Fix 4: 验证 archived/legacy 项目与 R1 上线后新项目的检查差异。"""

    @pytest.mark.asyncio
    async def test_archived_project_skipped(self, db_session: AsyncSession):
        """归档项目（archived_at IS NOT NULL）直接跳过检查，即使核心角色缺声明。"""
        from app.models.core import Project
        from app.models.staff_models import ProjectAssignment
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule

        # 新项目（created_at 晚于 LEGACY_CUTOFF_DATE）但已归档
        project = Project(
            id=FAKE_PROJECT_ID,
            name="归档新项目",
            client_name="测试客户",
            archived_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        db_session.add(project)
        # 核心角色分配但无声明
        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=FAKE_PROJECT_ID,
            staff_id=FAKE_USER_ID,
            role="signing_partner",
            is_deleted=False,
        )
        db_session.add(assignment)
        await db_session.flush()

        rule = IndependenceDeclarationCompleteRule()
        result = await rule.check(db_session, {"project_id": FAKE_PROJECT_ID})
        # 归档项目跳过
        assert result is None

    @pytest.mark.asyncio
    async def test_legacy_project_grace_returns_none_with_warning(
        self, db_session: AsyncSession, caplog
    ):
        """早于 LEGACY_CUTOFF_DATE 的老项目缺声明 → 返回 None，日志记 warning。"""
        import logging as _log
        from app.models.core import Project
        from app.models.staff_models import ProjectAssignment
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule

        # Legacy 项目（created_at=2025-12-01 早于 LEGACY_CUTOFF_DATE 2026-05-05）
        project = Project(
            id=FAKE_PROJECT_ID,
            name="Legacy 项目",
            client_name="老客户",
            created_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
        )
        db_session.add(project)
        # 核心角色分配但无声明
        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=FAKE_PROJECT_ID,
            staff_id=FAKE_USER_ID,
            role="signing_partner",
            is_deleted=False,
        )
        db_session.add(assignment)
        await db_session.flush()

        rule = IndependenceDeclarationCompleteRule()
        with caplog.at_level(_log.WARNING, logger="app.services.gate_rules_phase14"):
            result = await rule.check(db_session, {"project_id": FAKE_PROJECT_ID})

        # legacy 宽容期：不阻断
        assert result is None
        # warning 日志中包含 "legacy"
        has_legacy_warning = any(
            "legacy" in rec.getMessage().lower() for rec in caplog.records
        )
        assert has_legacy_warning, (
            f"expected legacy warning log, got: {[r.getMessage() for r in caplog.records]}"
        )

    @pytest.mark.asyncio
    async def test_new_project_strict_blocks(self, db_session: AsyncSession):
        """晚于 LEGACY_CUTOFF_DATE 的新项目缺声明 → 返回 blocking GateRuleHit。"""
        from app.models.core import Project
        from app.models.staff_models import ProjectAssignment
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule

        # 新项目（created_at=2026-06-01 晚于 LEGACY_CUTOFF_DATE 2026-05-05）
        project = Project(
            id=FAKE_PROJECT_ID,
            name="新项目",
            client_name="新客户",
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        db_session.add(project)
        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=FAKE_PROJECT_ID,
            staff_id=FAKE_USER_ID,
            role="signing_partner",
            is_deleted=False,
        )
        db_session.add(assignment)
        await db_session.flush()

        rule = IndependenceDeclarationCompleteRule()
        result = await rule.check(db_session, {"project_id": FAKE_PROJECT_ID})

        # 严格阻断
        assert result is not None
        assert result.rule_code == "R1-INDEPENDENCE"
        assert result.error_code == "INDEPENDENCE_DECLARATION_INCOMPLETE"
        assert result.severity.value == "blocking" if hasattr(result.severity, "value") else str(result.severity) == "blocking"


# ---------------------------------------------------------------------------
# Batch 3-1: _resolve_legacy_cutoff 三种分支测试
# ---------------------------------------------------------------------------


class TestResolveLegacyCutoff:
    """Batch 3-1: settings.INDEPENDENCE_LEGACY_CUTOFF_DATE 解析分支。

    修复前：解析失败时静默回退到硬编码的 LEGACY_CUTOFF_DATE（2026-05-05），
    与"空串=关闭宽容期"语义矛盾。修复后统一：
    - 空字符串 → None（关闭，静默）
    - 非法值 → None（关闭）+ WARNING 日志
    - 合法 YYYY-MM-DD → tz-aware datetime
    """

    def test_resolve_legacy_cutoff_empty_returns_none(self, monkeypatch):
        """settings 为空字符串 → 返回 None（关闭宽容期）。"""
        from app.core.config import settings
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule

        monkeypatch.setattr(settings, "INDEPENDENCE_LEGACY_CUTOFF_DATE", "", raising=False)
        result = IndependenceDeclarationCompleteRule._resolve_legacy_cutoff()
        assert result is None

    def test_resolve_legacy_cutoff_invalid_returns_none_with_warning(
        self, monkeypatch, caplog
    ):
        """settings 为非法字符串（如 "abc"）→ 返回 None + WARNING 日志。"""
        import logging as _log
        from app.core.config import settings
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule

        monkeypatch.setattr(
            settings, "INDEPENDENCE_LEGACY_CUTOFF_DATE", "abc", raising=False
        )

        with caplog.at_level(_log.WARNING, logger="app.services.gate_rules_phase14"):
            result = IndependenceDeclarationCompleteRule._resolve_legacy_cutoff()

        assert result is None
        # WARNING 日志含 "invalid INDEPENDENCE_LEGACY_CUTOFF_DATE"
        has_warning = any(
            "invalid INDEPENDENCE_LEGACY_CUTOFF_DATE" in rec.getMessage()
            for rec in caplog.records
        )
        assert has_warning, (
            f"expected invalid-config warning, got: {[r.getMessage() for r in caplog.records]}"
        )

    def test_resolve_legacy_cutoff_valid_returns_datetime(self, monkeypatch):
        """settings 为合法日期字符串 → 返回 tz-aware datetime。"""
        from app.core.config import settings
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule

        monkeypatch.setattr(
            settings, "INDEPENDENCE_LEGACY_CUTOFF_DATE", "2026-01-01", raising=False
        )
        result = IndependenceDeclarationCompleteRule._resolve_legacy_cutoff()

        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 1
        # tz-aware
        assert result.tzinfo is not None


# ---------------------------------------------------------------------------
# Batch 3-7: INDEPENDENCE_LEGACY_GRACE_ENABLED 开关测试
# ---------------------------------------------------------------------------


class TestIndependenceLegacyGraceEnabledSwitch:
    """Batch 3-7: 全局宽容期开关验证。

    - True（默认）：早于 CUTOFF_DATE 的项目仍走 legacy 宽容路径
    - False：即使早于 CUTOFF_DATE 也严格检查（R6+ 老项目升级完毕后可关闭）
    """

    def test_grace_enabled_false_disables_legacy_path(self, monkeypatch):
        """GRACE_ENABLED=False → _is_legacy_project 直接返回 False。"""
        from app.core.config import settings
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule

        # created_at 早于 CUTOFF_DATE（2026-05-05）
        old_created_at = datetime(2025, 12, 1, tzinfo=timezone.utc)

        monkeypatch.setattr(
            settings, "INDEPENDENCE_LEGACY_GRACE_ENABLED", False, raising=False
        )
        # CUTOFF_DATE 保持默认或配置为合法日期
        monkeypatch.setattr(
            settings, "INDEPENDENCE_LEGACY_CUTOFF_DATE", "2026-05-05", raising=False
        )

        result = IndependenceDeclarationCompleteRule._is_legacy_project(old_created_at)
        assert result is False, (
            "GRACE_ENABLED=False 时应强制严格检查，不走 legacy 宽容路径"
        )

    def test_grace_enabled_true_default_uses_cutoff(self, monkeypatch):
        """GRACE_ENABLED=True（默认）+ 早于 CUTOFF_DATE → 返回 True（legacy）。"""
        from app.core.config import settings
        from app.services.gate_rules_phase14 import IndependenceDeclarationCompleteRule

        old_created_at = datetime(2025, 12, 1, tzinfo=timezone.utc)

        monkeypatch.setattr(
            settings, "INDEPENDENCE_LEGACY_GRACE_ENABLED", True, raising=False
        )
        monkeypatch.setattr(
            settings, "INDEPENDENCE_LEGACY_CUTOFF_DATE", "2026-05-05", raising=False
        )

        result = IndependenceDeclarationCompleteRule._is_legacy_project(old_created_at)
        assert result is True, (
            "GRACE_ENABLED=True 默认时，早于 CUTOFF_DATE 的项目应识别为 legacy"
        )
