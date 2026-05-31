"""报表配置主模板回填 service 方法测试

Validates: Requirements 1.1, 1.2, 1.3, 2.4
测试 suggest_to_master / review_candidate / diff_vs_master / apply_master_update
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.report_models import (
    FinancialReportType,
    ReportConfig,
    ReportConfigBaseline,
)
from app.services.report_config_service import ConfigDiff, ReportConfigService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_REVIEWER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
STANDARD = "soe_consolidated"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建 standard 级配置 + 项目级克隆配置"""
    # standard 级配置（主模板）
    master_rows = [
        ReportConfig(
            report_type=FinancialReportType.balance_sheet,
            row_number=1,
            row_code="BS001",
            row_name="货币资金",
            indent_level=0,
            formula="TB(1001)",
            applicable_standard=STANDARD,
            is_total_row=False,
        ),
        ReportConfig(
            report_type=FinancialReportType.balance_sheet,
            row_number=2,
            row_code="BS002",
            row_name="应收账款",
            indent_level=0,
            formula="TB(1122)",
            applicable_standard=STANDARD,
            is_total_row=False,
        ),
        ReportConfig(
            report_type=FinancialReportType.balance_sheet,
            row_number=3,
            row_code="BS003",
            row_name="存货",
            indent_level=0,
            formula="TB(1405)",
            applicable_standard=STANDARD,
            is_total_row=False,
        ),
    ]
    db_session.add_all(master_rows)
    await db_session.flush()

    # 项目级克隆配置（模拟 clone_report_config 后的状态）
    project_standard = f"project:{FAKE_PROJECT_ID}"
    project_rows = [
        ReportConfig(
            report_type=FinancialReportType.balance_sheet,
            row_number=1,
            row_code="BS001",
            row_name="货币资金",
            indent_level=0,
            formula="TB(1001)+TB(1002)",  # 项目自定义了公式
            applicable_standard=project_standard,
            is_total_row=False,
        ),
        ReportConfig(
            report_type=FinancialReportType.balance_sheet,
            row_number=2,
            row_code="BS002",
            row_name="应收账款",
            indent_level=0,
            formula="TB(1122)",  # 与主模板相同
            applicable_standard=project_standard,
            is_total_row=False,
        ),
        # BS003 项目没有（模拟主模板新增行）
    ]
    db_session.add_all(project_rows)
    await db_session.flush()
    return db_session


# ------------------------------------------------------------------
# suggest_to_master 测试
# ------------------------------------------------------------------


class TestSuggestToMaster:
    """suggest_to_master 方法测试"""

    @pytest.mark.asyncio
    async def test_creates_pending_candidate(self, seeded_db: AsyncSession):
        """提交候选应创建 status=pending 的 ReportConfigBaseline 记录"""
        svc = ReportConfigService(seeded_db)
        candidate_id = await svc.suggest_to_master(
            project_id=FAKE_PROJECT_ID,
            row_code="BS001",
            report_type="balance_sheet",
            standard=STANDARD,
            submitted_by=FAKE_USER_ID,
        )
        assert isinstance(candidate_id, uuid.UUID)

        # 验证记录
        result = await seeded_db.execute(
            select(ReportConfigBaseline).where(ReportConfigBaseline.id == candidate_id)
        )
        candidate = result.scalar_one()
        assert candidate.status == "pending"
        assert candidate.standard == STANDARD
        assert candidate.row_code == "BS001"
        assert candidate.report_type == "balance_sheet"
        assert candidate.source_project_id == FAKE_PROJECT_ID
        assert candidate.submitted_by == FAKE_USER_ID
        # 从项目级配置读取的公式
        assert candidate.candidate_formula == "TB(1001)+TB(1002)"

    @pytest.mark.asyncio
    async def test_explicit_formula(self, seeded_db: AsyncSession):
        """显式传入 candidate_formula 时使用传入值"""
        svc = ReportConfigService(seeded_db)
        candidate_id = await svc.suggest_to_master(
            project_id=FAKE_PROJECT_ID,
            row_code="BS001",
            report_type="balance_sheet",
            standard=STANDARD,
            candidate_formula="TB(1001)+TB(1002)+TB(1012)",
            submitted_by=FAKE_USER_ID,
        )
        result = await seeded_db.execute(
            select(ReportConfigBaseline).where(ReportConfigBaseline.id == candidate_id)
        )
        candidate = result.scalar_one()
        assert candidate.candidate_formula == "TB(1001)+TB(1002)+TB(1012)"

    @pytest.mark.asyncio
    async def test_nonexistent_row_raises(self, seeded_db: AsyncSession):
        """项目中不存在的 row_code 应抛异常"""
        svc = ReportConfigService(seeded_db)
        with pytest.raises(ValueError, match="未找到"):
            await svc.suggest_to_master(
                project_id=FAKE_PROJECT_ID,
                row_code="NONEXIST",
                report_type="balance_sheet",
                standard=STANDARD,
                submitted_by=FAKE_USER_ID,
            )


# ------------------------------------------------------------------
# review_candidate 测试
# ------------------------------------------------------------------


class TestReviewCandidate:
    """review_candidate 方法测试"""

    @pytest.mark.asyncio
    async def test_approve_merges_to_standard(self, seeded_db: AsyncSession):
        """审核通过应合并候选公式回 standard 级"""
        svc = ReportConfigService(seeded_db)
        # 先提交候选
        candidate_id = await svc.suggest_to_master(
            project_id=FAKE_PROJECT_ID,
            row_code="BS001",
            report_type="balance_sheet",
            standard=STANDARD,
            submitted_by=FAKE_USER_ID,
        )

        # 审核通过
        await svc.review_candidate(candidate_id, approved=True, reviewer=FAKE_REVIEWER_ID)

        # 验证候选状态
        result = await seeded_db.execute(
            select(ReportConfigBaseline).where(ReportConfigBaseline.id == candidate_id)
        )
        candidate = result.scalar_one()
        assert candidate.status == "approved"
        assert candidate.reviewed_by == FAKE_REVIEWER_ID
        assert candidate.version == 2  # 版本递增

        # 验证 standard 级公式已更新
        master_result = await seeded_db.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == STANDARD,
                ReportConfig.row_code == "BS001",
                ReportConfig.is_deleted == False,  # noqa: E712
            )
        )
        master_row = master_result.scalar_one()
        assert master_row.formula == "TB(1001)+TB(1002)"

    @pytest.mark.asyncio
    async def test_reject_does_not_merge(self, seeded_db: AsyncSession):
        """审核驳回不应修改 standard 级"""
        svc = ReportConfigService(seeded_db)
        candidate_id = await svc.suggest_to_master(
            project_id=FAKE_PROJECT_ID,
            row_code="BS001",
            report_type="balance_sheet",
            standard=STANDARD,
            submitted_by=FAKE_USER_ID,
        )

        await svc.review_candidate(candidate_id, approved=False, reviewer=FAKE_REVIEWER_ID)

        # 候选状态为 rejected
        result = await seeded_db.execute(
            select(ReportConfigBaseline).where(ReportConfigBaseline.id == candidate_id)
        )
        candidate = result.scalar_one()
        assert candidate.status == "rejected"

        # standard 级公式未变
        master_result = await seeded_db.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == STANDARD,
                ReportConfig.row_code == "BS001",
                ReportConfig.is_deleted == False,  # noqa: E712
            )
        )
        master_row = master_result.scalar_one()
        assert master_row.formula == "TB(1001)"  # 原始值

    @pytest.mark.asyncio
    async def test_review_nonpending_raises(self, seeded_db: AsyncSession):
        """非 pending 状态的候选不可审核"""
        svc = ReportConfigService(seeded_db)
        candidate_id = await svc.suggest_to_master(
            project_id=FAKE_PROJECT_ID,
            row_code="BS001",
            report_type="balance_sheet",
            standard=STANDARD,
            submitted_by=FAKE_USER_ID,
        )
        # 先驳回
        await svc.review_candidate(candidate_id, approved=False, reviewer=FAKE_REVIEWER_ID)
        # 再次审核应报错
        with pytest.raises(ValueError, match="仅 pending 可审核"):
            await svc.review_candidate(candidate_id, approved=True, reviewer=FAKE_REVIEWER_ID)

    @pytest.mark.asyncio
    async def test_nonexistent_candidate_raises(self, seeded_db: AsyncSession):
        """不存在的候选 ID 应抛异常"""
        svc = ReportConfigService(seeded_db)
        with pytest.raises(ValueError, match="不存在"):
            await svc.review_candidate(uuid.uuid4(), approved=True, reviewer=FAKE_REVIEWER_ID)


# ------------------------------------------------------------------
# diff_vs_master 测试
# ------------------------------------------------------------------


class TestDiffVsMaster:
    """diff_vs_master 方法测试"""

    @pytest.mark.asyncio
    async def test_detects_modified_rows(self, seeded_db: AsyncSession):
        """检测项目自定义公式与主模板不同的行"""
        svc = ReportConfigService(seeded_db)
        diffs = await svc.diff_vs_master(FAKE_PROJECT_ID, STANDARD)

        modified = [d for d in diffs if d.diff_type == "modified"]
        assert len(modified) == 1
        assert modified[0].row_code == "BS001"
        assert modified[0].project_formula == "TB(1001)+TB(1002)"
        assert modified[0].master_formula == "TB(1001)"

    @pytest.mark.asyncio
    async def test_detects_master_only_rows(self, seeded_db: AsyncSession):
        """检测主模板有但项目没有的行"""
        svc = ReportConfigService(seeded_db)
        diffs = await svc.diff_vs_master(FAKE_PROJECT_ID, STANDARD)

        master_only = [d for d in diffs if d.diff_type == "master_only"]
        assert len(master_only) == 1
        assert master_only[0].row_code == "BS003"

    @pytest.mark.asyncio
    async def test_identical_rows_not_in_diff(self, seeded_db: AsyncSession):
        """公式相同的行不应出现在 diff 中"""
        svc = ReportConfigService(seeded_db)
        diffs = await svc.diff_vs_master(FAKE_PROJECT_ID, STANDARD)

        all_codes = [d.row_code for d in diffs]
        assert "BS002" not in all_codes


# ------------------------------------------------------------------
# apply_master_update 测试
# ------------------------------------------------------------------


class TestApplyMasterUpdate:
    """apply_master_update 方法测试"""

    @pytest.mark.asyncio
    async def test_keep_local_preserves_custom(self, seeded_db: AsyncSession):
        """keep_local=True 时不覆盖项目已自定义的行"""
        svc = ReportConfigService(seeded_db)
        updated = await svc.apply_master_update(FAKE_PROJECT_ID, STANDARD, keep_local=True)

        # BS001 公式不同 → 保留本地覆盖（不计入 updated）
        # BS002 公式相同 → 同步（计入 updated）
        # BS003 项目没有 → 新增（计入 updated）
        assert updated == 2

        # 验证 BS001 公式未被覆盖
        project_standard = f"project:{FAKE_PROJECT_ID}"
        result = await seeded_db.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == project_standard,
                ReportConfig.row_code == "BS001",
                ReportConfig.is_deleted == False,  # noqa: E712
            )
        )
        row = result.scalar_one()
        assert row.formula == "TB(1001)+TB(1002)"  # 保留本地

    @pytest.mark.asyncio
    async def test_keep_local_false_overwrites(self, seeded_db: AsyncSession):
        """keep_local=False 时覆盖所有行"""
        svc = ReportConfigService(seeded_db)
        updated = await svc.apply_master_update(FAKE_PROJECT_ID, STANDARD, keep_local=False)

        # 全部同步：BS001(覆盖) + BS002(同步) + BS003(新增)
        assert updated == 3

        # 验证 BS001 公式被覆盖
        project_standard = f"project:{FAKE_PROJECT_ID}"
        result = await seeded_db.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == project_standard,
                ReportConfig.row_code == "BS001",
                ReportConfig.is_deleted == False,  # noqa: E712
            )
        )
        row = result.scalar_one()
        assert row.formula == "TB(1001)"  # 被主模板覆盖

    @pytest.mark.asyncio
    async def test_adds_missing_rows(self, seeded_db: AsyncSession):
        """主模板有但项目没有的行应被新增"""
        svc = ReportConfigService(seeded_db)
        await svc.apply_master_update(FAKE_PROJECT_ID, STANDARD, keep_local=True)

        project_standard = f"project:{FAKE_PROJECT_ID}"
        result = await seeded_db.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == project_standard,
                ReportConfig.row_code == "BS003",
                ReportConfig.is_deleted == False,  # noqa: E712
            )
        )
        row = result.scalar_one()
        assert row.formula == "TB(1405)"
        assert row.row_name == "存货"

    @pytest.mark.asyncio
    async def test_clears_is_stale(self, seeded_db: AsyncSession):
        """同步后 is_stale 应被清除"""
        # 先标记 is_stale
        project_standard = f"project:{FAKE_PROJECT_ID}"
        result = await seeded_db.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == project_standard,
                ReportConfig.is_deleted == False,  # noqa: E712
            )
        )
        for row in result.scalars().all():
            row.is_stale = True
        await seeded_db.flush()

        svc = ReportConfigService(seeded_db)
        await svc.apply_master_update(FAKE_PROJECT_ID, STANDARD, keep_local=True)

        # 所有行 is_stale 应为 False
        result = await seeded_db.execute(
            select(ReportConfig).where(
                ReportConfig.applicable_standard == project_standard,
                ReportConfig.is_deleted == False,  # noqa: E712
            )
        )
        for row in result.scalars().all():
            assert row.is_stale is False
