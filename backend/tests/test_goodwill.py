"""商誉计算服务测试

Validates: Requirements 5.1, 5.2, 5.3, 5.4
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project
from app.models.consolidation_models import GoodwillCalc
from app.models.consolidation_schemas import GoodwillInput
from app.services import goodwill_service as svc

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest.fixture
async def db_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()


async def _create_test_project(db: AsyncSession) -> Project:
    project = Project(id=uuid.uuid4(), name="Test Project", status="active")
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


class TestCalculateGoodwill:
    """calculate_goodwill 函数测试

    公式：商誉 = 合并成本 - 净资产公允价值 × 持股比例（持股比例为小数形式）
    """

    @pytest.mark.asyncio
    async def test_positive_goodwill(self):
        """正商誉：合并成本 > 净资产公允价值份额"""
        goodwill, is_neg, gtype, notes = svc.calculate_goodwill(
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),  # 80% → 0.80
        )
        # 1000 - 800 * 0.80 = 1000 - 640 = 360
        assert goodwill == Decimal("360")
        assert is_neg is False
        assert gtype == "positive"
        assert notes is not None
        assert "正商誉" in notes

    @pytest.mark.asyncio
    async def test_negative_goodwill(self):
        """负商誉：合并成本 < 净资产公允价值份额（廉价购买）

        负商誉不入商誉科目，goodwill_amount 入账为零
        """
        goodwill, is_neg, gtype, notes = svc.calculate_goodwill(
            acquisition_cost=Decimal("500"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        # 500 - 800 * 0.80 = 500 - 640 = -140 → 入账为零
        assert goodwill == Decimal("0")
        assert is_neg is True
        assert gtype == "negative"
        assert notes is not None
        assert "负商誉" in notes
        assert "营业外收入" in notes or "递延收益" in notes

    @pytest.mark.asyncio
    async def test_none_inputs(self):
        """空值输入应返回 None"""
        assert svc.calculate_goodwill(None, Decimal("800"), Decimal("0.80")) == (None, False, None, None)
        assert svc.calculate_goodwill(Decimal("1000"), None, Decimal("0.80")) == (None, False, None, None)
        assert svc.calculate_goodwill(Decimal("1000"), Decimal("800"), None) == (None, False, None, None)

    @pytest.mark.asyncio
    async def test_zero_goodwill(self):
        """零商誉：合并成本 = 净资产公允价值份额"""
        goodwill, is_neg, gtype, _ = svc.calculate_goodwill(
            acquisition_cost=Decimal("640"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        assert goodwill == Decimal("0")
        assert is_neg is False
        assert gtype == "positive"

    @pytest.mark.asyncio
    async def test_full_ownership(self):
        """100% 持股：净资产公允价值份额 = 净资产公允价值"""
        goodwill, is_neg, _, _ = svc.calculate_goodwill(
            acquisition_cost=Decimal("1200"),
            identifiable_net_assets_fv=Decimal("1000"),
            parent_share_ratio=Decimal("1.00"),
        )
        # 1200 - 1000 * 1.0 = 200
        assert goodwill == Decimal("200")
        assert is_neg is False


class TestGoodwillCrud:
    """商誉 CRUD 操作测试"""

    @pytest.mark.asyncio
    async def test_create_positive_goodwill(self, db_session: AsyncSession):
        """创建正商誉记录"""
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            year=2024,
            subsidiary_company_code="SUB001",
            acquisition_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        result = svc.create_goodwill(db_session, project.id, input_data)

        assert result.subsidiary_company_code == "SUB001"
        assert result.goodwill_amount == Decimal("360")
        assert result.is_negative_goodwill is False
        assert result.accumulated_impairment == Decimal("0")
        assert result.carrying_amount == Decimal("360")
        assert result.negative_goodwill_treatment is not None

    @pytest.mark.asyncio
    async def test_create_negative_goodwill(self, db_session: AsyncSession):
        """创建负商誉记录：goodwill_amount 入账为零"""
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            year=2024,
            subsidiary_company_code="SUB001",
            acquisition_date=date(2024, 1, 1),
            acquisition_cost=Decimal("500"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        result = svc.create_goodwill(db_session, project.id, input_data)

        assert result.goodwill_amount == Decimal("0")
        assert result.is_negative_goodwill is True
        assert result.carrying_amount == Decimal("0")
        assert result.negative_goodwill_treatment is not None

    @pytest.mark.asyncio
    async def test_get_goodwill_list(self, db_session: AsyncSession):
        """查询商誉列表"""
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            year=2024,
            subsidiary_company_code="SUB001",
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        svc.create_goodwill(db_session, project.id, input_data)

        results = svc.get_goodwill_list(db_session, project.id, 2024)
        assert len(results) == 1
        assert results[0].subsidiary_company_code == "SUB001"

    @pytest.mark.asyncio
    async def test_delete_goodwill(self, db_session: AsyncSession):
        """软删除商誉记录"""
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            year=2024,
            subsidiary_company_code="SUB001",
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        goodwill = svc.create_goodwill(db_session, project.id, input_data)

        deleted = svc.delete_goodwill(db_session, goodwill.id, project.id)
        assert deleted is True

        # 再次查询应该找不到
        found = svc.get_goodwill(db_session, goodwill.id, project.id)
        assert found is None


class TestRecordImpairment:
    """record_impairment 核心业务测试"""

    @pytest.mark.asyncio
    async def test_record_impairment_basic(self, db_session: AsyncSession):
        """记录减值：正常情况"""
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            year=2024,
            subsidiary_company_code="SUB001",
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        svc.create_goodwill(db_session, project.id, input_data)
        # initial goodwill = 360

        result = svc.record_impairment(
            db_session,
            project_id=project.id,
            company_code="SUB001",
            year=2024,
            impairment_amount=Decimal("50"),
            notes="年度减值测试",
        )

        assert result is not None
        assert result.current_year_impairment == Decimal("50")
        assert result.accumulated_impairment == Decimal("50")
        assert result.carrying_amount == Decimal("310")  # 360 - 50

    @pytest.mark.asyncio
    async def test_record_impairment_exceed_limit(self, db_session: AsyncSession):
        """减值金额超限应抛出异常"""
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            year=2024,
            subsidiary_company_code="SUB001",
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        svc.create_goodwill(db_session, project.id, input_data)
        # initial goodwill = 360

        with pytest.raises(ValueError, match="超出允许上限"):
            svc.record_impairment(
                db_session,
                project_id=project.id,
                company_code="SUB001",
                year=2024,
                impairment_amount=Decimal("500"),  # 超出 360
            )

    @pytest.mark.asyncio
    async def test_record_impairment_zero_amount(self, db_session: AsyncSession):
        """减值金额为零或负数应抛出异常"""
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            year=2024,
            subsidiary_company_code="SUB001",
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        svc.create_goodwill(db_session, project.id, input_data)

        with pytest.raises(ValueError, match="减值金额必须大于 0"):
            svc.record_impairment(
                db_session,
                project_id=project.id,
                company_code="SUB001",
                year=2024,
                impairment_amount=Decimal("0"),
            )

    @pytest.mark.asyncio
    async def test_record_impairment_not_found(self, db_session: AsyncSession):
        """商誉记录不存在应抛出异常"""
        project = await _create_test_project(db_session)

        with pytest.raises(ValueError, match="未找到商誉记录"):
            svc.record_impairment(
                db_session,
                project_id=project.id,
                company_code="NONEXISTENT",
                year=2024,
                impairment_amount=Decimal("50"),
            )

    @pytest.mark.asyncio
    async def test_record_impairment_cumulative(self, db_session: AsyncSession):
        """累计减值：分多笔记录"""
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            year=2024,
            subsidiary_company_code="SUB001",
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        svc.create_goodwill(db_session, project.id, input_data)
        # initial goodwill = 360

        # 第一笔
        r1 = svc.record_impairment(
            db_session, project.id, "SUB001", 2024, Decimal("100"), "第一笔减值"
        )
        assert r1.accumulated_impairment == Decimal("100")
        assert r1.current_year_impairment == Decimal("100")
        assert r1.carrying_amount == Decimal("260")

        # 第二笔
        r2 = svc.record_impairment(
            db_session, project.id, "SUB001", 2024, Decimal("60"), "第二笔减值"
        )
        assert r2.accumulated_impairment == Decimal("160")
        assert r2.current_year_impairment == Decimal("160")
        assert r2.carrying_amount == Decimal("200")  # 360 - 160

    @pytest.mark.asyncio
    async def test_record_impairment_negative_goodwill_rejected(self, db_session: AsyncSession):
        """负商誉不允许记录减值"""
        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            year=2024,
            subsidiary_company_code="SUB001",
            acquisition_cost=Decimal("500"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        svc.create_goodwill(db_session, project.id, input_data)

        with pytest.raises(ValueError, match="负商誉不入商誉科目"):
            svc.record_impairment(
                db_session, project.id, "SUB001", 2024, Decimal("10")
            )

    @pytest.mark.asyncio
    async def test_record_impairment_creates_elimination_entry(self, db_session: AsyncSession):
        """record_impairment 应生成抵消分录"""
        from app.models.consolidation_models import EliminationEntry

        project = await _create_test_project(db_session)
        input_data = GoodwillInput(
            year=2024,
            subsidiary_company_code="SUB001",
            acquisition_cost=Decimal("1000"),
            identifiable_net_assets_fv=Decimal("800"),
            parent_share_ratio=Decimal("0.80"),
        )
        svc.create_goodwill(db_session, project.id, input_data)

        svc.record_impairment(
            db_session, project.id, "SUB001", 2024, Decimal("50"), "测试减值"
        )

        # 验证抵消分录已生成
        entries = (
            db_session.query(EliminationEntry)
            .filter(
                EliminationEntry.project_id == project.id,
                EliminationEntry.year == 2024,
                EliminationEntry.is_deleted.is_(False),
            )
            .all()
        )
        assert len(entries) == 2  # 借方一行 + 贷方一行

        # 借贷平衡校验
        total_debit = sum(e.debit_amount for e in entries)
        total_credit = sum(e.credit_amount for e in entries)
        assert total_debit == total_credit == Decimal("50")

        # 验证分录类型和描述
        desc_entries = [e for e in entries if e.description]
        assert len(desc_entries) == 2
        assert any("商誉减值准备" in (e.description or "") for e in desc_entries)
