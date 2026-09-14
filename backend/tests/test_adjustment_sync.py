"""底稿调整汇聚服务 AdjustmentSyncService 属性/单元测试

spec: workpaper-adjustment-centralization — Property 1-10

覆盖：幂等(P1)/借贷平衡守卫(P2)/类别→类型(P3)/TB 不双计(P4)/软删清理(P5)/
approved 锁定(P6)/溯源可跳转(P7)/回流一致(P8)/零回归(P9)。
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, UserRole
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountSource,
    Adjustment,
    AdjustmentType,
    ReviewStatus,
    TrialBalance,
)
from app.models.audit_platform_schemas import AdjustmentSyncRequest
from app.services.adjustment_sync_service import (
    AdjustmentSyncService,
    AdjustmentSyncError,
)
from app.services.adjustment_service import AdjustmentService
from app.services.trial_balance_service import TrialBalanceService
from app.models.audit_platform_schemas import AdjustmentCreate, AdjustmentLineItem
from app.models.core import Project, ProjectStatus, ProjectType

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

_USER_ID = uuid.uuid4()
_WP_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def pid(db_session: AsyncSession):
    project = Project(
        id=uuid.uuid4(), name="汇聚测试_2025", client_name="汇聚测试",
        project_type=ProjectType.annual, status=ProjectStatus.planning,
        created_by=_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()
    p = project.id
    db_session.add_all([
        AccountChart(
            project_id=p, account_code="1001", account_name="库存现金",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=p, account_code="6001", account_name="主营业务收入",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.revenue, source=AccountSource.standard,
        ),
    ])
    db_session.add_all([
        TrialBalance(
            project_id=p, year=2025, company_code="001",
            standard_account_code="1001", account_name="库存现金",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("12000"), audited_amount=Decimal("12000"),
        ),
        TrialBalance(
            project_id=p, year=2025, company_code="001",
            standard_account_code="6001", account_name="主营业务收入",
            account_category=AccountCategory.revenue,
            unadjusted_amount=Decimal("100000"), audited_amount=Decimal("100000"),
        ),
    ])
    await db_session.commit()
    return p


def _req(item_id="D4-4-rows", adj_type=AdjustmentType.aje, debit="5000", credit="5000",
         code_debit="1001", code_credit="6001"):
    return AdjustmentSyncRequest(
        year=2025, wp_id=_WP_ID, item_id=item_id, source_wp_code="D4",
        description="收入跨期调整", adjustment_type=adj_type,
        line_items=[
            {"standard_account_code": code_debit, "account_name": "库存现金",
             "debit_amount": Decimal(debit), "credit_amount": Decimal("0")},
            {"standard_account_code": code_credit, "account_name": "主营业务收入",
             "debit_amount": Decimal("0"), "credit_amount": Decimal(credit)},
        ],
    )


async def _count_active_groups(db, project_id, source_ref):
    import sqlalchemy as sa
    r = await db.execute(
        sa.select(sa.func.count(sa.distinct(Adjustment.entry_group_id))).where(
            Adjustment.project_id == project_id,
            Adjustment.source_ref == source_ref,
            Adjustment.is_deleted == sa.false(),
        )
    )
    return r.scalar() or 0


# ─── P1 幂等 ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p1_idempotent_same_source_ref(db_session, pid):
    svc = AdjustmentSyncService(db_session)
    for _ in range(3):
        await svc.sync_from_workpaper(pid, _req(), _USER_ID)
        await db_session.flush()
    source_ref = f"{_WP_ID}:D4-4-rows"
    assert await _count_active_groups(db_session, pid, source_ref) == 1


# ─── P2 借贷平衡守卫 ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p2_unbalanced_rejected(db_session, pid):
    svc = AdjustmentSyncService(db_session)
    with pytest.raises(AdjustmentSyncError) as ei:
        await svc.sync_from_workpaper(pid, _req(debit="5000", credit="3000"), _USER_ID)
    assert ei.value.code == "UNBALANCED"


# ─── P3 类别→类型映射 ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p3_type_preserved(db_session, pid):
    svc = AdjustmentSyncService(db_session)
    res = await svc.sync_from_workpaper(pid, _req(adj_type=AdjustmentType.rje), _USER_ID)
    assert res.adjustment_type in (AdjustmentType.rje, "rje")
    assert res.origin == "workpaper"
    assert res.source_ref == f"{_WP_ID}:D4-4-rows"


# ─── P4 TB 不双计（origin 过滤）────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p4_recalc_excludes_workpaper_origin(db_session, pid):
    # 手工调整：借 1001 2000 / 贷 6001 2000（origin=manual）
    adj_svc = AdjustmentService(db_session)
    await adj_svc.create_entry(pid, AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025, company_code="001",
        description="手工调整",
        line_items=[
            AdjustmentLineItem(standard_account_code="1001", account_name="库存现金",
                               debit_amount=Decimal("2000"), credit_amount=Decimal("0")),
            AdjustmentLineItem(standard_account_code="6001", account_name="主营业务收入",
                               debit_amount=Decimal("0"), credit_amount=Decimal("2000")),
        ],
    ), _USER_ID, batch_mode=True)
    # 底稿汇聚：借 1001 5000 / 贷 6001 5000（origin=workpaper）
    sync_svc = AdjustmentSyncService(db_session)
    await sync_svc.sync_from_workpaper(pid, _req(debit="5000", credit="5000"), _USER_ID)
    await db_session.flush()

    tb_svc = TrialBalanceService(db_session)
    await tb_svc.recalc_adjustments(pid, 2025, company_code="001")
    await db_session.flush()

    import sqlalchemy as sa
    r = await db_session.execute(
        sa.select(TrialBalance.aje_adjustment).where(
            TrialBalance.project_id == pid, TrialBalance.year == 2025,
            TrialBalance.standard_account_code == "1001",
        )
    )
    aje = r.scalar()
    # 仅 manual 的 2000 计入（借方类 1001 sign=+1），workpaper 的 5000 不计入
    assert Decimal(str(aje)) == Decimal("2000")


# ─── P5 软删清理 ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p5_remove_by_source_ref(db_session, pid):
    svc = AdjustmentSyncService(db_session)
    await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    source_ref = f"{_WP_ID}:D4-4-rows"
    n = await svc.remove_by_source_ref(pid, source_ref)
    assert n >= 1
    assert await _count_active_groups(db_session, pid, source_ref) == 0
    # 再次 sync 可重建
    await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    assert await _count_active_groups(db_session, pid, source_ref) == 1


# ─── P6 approved 锁定 ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p6_approved_locked(db_session, pid):
    svc = AdjustmentSyncService(db_session)
    await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    # 手动置 approved
    import sqlalchemy as sa
    rows = (await db_session.execute(
        sa.select(Adjustment).where(
            Adjustment.project_id == pid,
            Adjustment.source_ref == f"{_WP_ID}:D4-4-rows",
            Adjustment.is_deleted == sa.false(),
        )
    )).scalars().all()
    for r in rows:
        r.review_status = ReviewStatus.approved
    await db_session.flush()
    with pytest.raises(AdjustmentSyncError) as ei:
        await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    assert ei.value.code == "APPROVED_LOCKED"


# ─── P7 溯源可跳转（source_ref 解析出合法 wp_id）────────────────────────────────
def test_p7_source_ref_parse():
    ref = AdjustmentSyncService.build_source_ref(_WP_ID, "D4-4-rows")
    assert ref == f"{_WP_ID}:D4-4-rows"
    wp_id = ref.split(":", 1)[0]
    assert uuid.UUID(wp_id) == _WP_ID


# ─── P8 回流状态一致 ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p8_status_roundtrip(db_session, pid):
    svc = AdjustmentSyncService(db_session)
    await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    source_ref = f"{_WP_ID}:D4-4-rows"
    status = await svc.get_status_by_source_ref(pid, source_ref)
    assert status is not None
    assert status["review_status"] == "draft"
    assert status["source_wp_code"] == str(_WP_ID)


# ─── 科目解析：name fallback + unresolved ─────────────────────────────────────
@pytest.mark.asyncio
async def test_account_resolution_name_fallback(db_session, pid):
    svc = AdjustmentSyncService(db_session)
    # 不提供 code，仅提供 name（库存现金/主营业务收入 均为标准科目名）→ 应解析成功
    req = AdjustmentSyncRequest(
        year=2025, wp_id=_WP_ID, item_id="D4-4-rows", source_wp_code="D4",
        description="名称解析", adjustment_type=AdjustmentType.aje,
        line_items=[
            {"account_name": "库存现金", "debit_amount": Decimal("100"), "credit_amount": Decimal("0")},
            {"account_name": "主营业务收入", "debit_amount": Decimal("0"), "credit_amount": Decimal("100")},
        ],
    )
    res = await svc.sync_from_workpaper(pid, req, _USER_ID)
    assert len(res.line_items) == 2
    assert {li.standard_account_code for li in res.line_items} == {"1001", "6001"}


@pytest.mark.asyncio
async def test_account_resolution_unresolved(db_session, pid):
    svc = AdjustmentSyncService(db_session)
    req = AdjustmentSyncRequest(
        year=2025, wp_id=_WP_ID, item_id="D4-4-rows", source_wp_code="D4",
        description="无法解析", adjustment_type=AdjustmentType.aje,
        line_items=[
            {"account_name": "不存在的科目", "debit_amount": Decimal("100"), "credit_amount": Decimal("0")},
            {"standard_account_code": "6001", "account_name": "主营业务收入",
             "debit_amount": Decimal("0"), "credit_amount": Decimal("100")},
        ],
    )
    with pytest.raises(AdjustmentSyncError) as ei:
        await svc.sync_from_workpaper(pid, req, _USER_ID)
    assert ei.value.code == "UNRESOLVED_ACCOUNTS"
    assert "不存在的科目" in (ei.value.detail or {}).get("unresolved", [])
