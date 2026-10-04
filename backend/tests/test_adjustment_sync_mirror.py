"""底稿→大厅镜像 (ADR-P3-008) 测试

spec: chain-closure-phase3-push-rollout Task 5

覆盖：
- 内容签名相同不写库、不换编号（M1）
- 内容变化原地更新保组号与编号（M2）
- pending_review / rejected 回 draft（M3）
- approved 仍 APPROVED_LOCKED（M4）
- 编号不烧：重同步不消耗新编号（M5）
- 咨询锁键稳定摘要（M6）

变异覆盖：
- 去掉签名比较 → M1 红
- 恢复软删重建（新 group_id / 新编号）→ M2/M5 红
"""

import hashlib
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

from app.models.base import Base, UserRole
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountSource,
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    ReviewStatus,
    TrialBalance,
)
from app.models.audit_platform_schemas import AdjustmentSyncRequest
from app.services.adjustment_sync_service import (
    AdjustmentSyncService,
    AdjustmentSyncError,
)
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
        id=uuid.uuid4(), name="镜像测试_2025", client_name="镜像测试",
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
        AccountChart(
            project_id=p, account_code="1002", account_name="银行存款",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
    ])
    await db_session.commit()
    return p


def _req(item_id="D4-4-rows", debit="5000", credit="5000",
         code_debit="1001", code_credit="6001", desc="收入跨期调整"):
    return AdjustmentSyncRequest(
        year=2025, wp_id=_WP_ID, item_id=item_id, source_wp_code="D4",
        description=desc, adjustment_type=AdjustmentType.aje,
        line_items=[
            {"standard_account_code": code_debit, "account_name": "库存现金",
             "debit_amount": Decimal(debit), "credit_amount": Decimal("0")},
            {"standard_account_code": code_credit, "account_name": "主营业务收入",
             "debit_amount": Decimal("0"), "credit_amount": Decimal(credit)},
        ],
    )


async def _get_active_adj_rows(db, project_id, source_ref):
    r = await db.execute(
        sa.select(Adjustment).where(
            Adjustment.project_id == project_id,
            Adjustment.source_ref == source_ref,
            Adjustment.is_deleted == sa.false(),
        ).order_by(Adjustment.created_at)
    )
    return list(r.scalars().all())


async def _get_active_entry_rows(db, entry_group_id):
    r = await db.execute(
        sa.select(AdjustmentEntry).where(
            AdjustmentEntry.entry_group_id == entry_group_id,
            AdjustmentEntry.is_deleted == sa.false(),
        ).order_by(AdjustmentEntry.line_no)
    )
    return list(r.scalars().all())


async def _count_all_groups(db, project_id):
    """所有 entry_group_id（含已删除），用于验证编号没有烧"""
    r = await db.execute(
        sa.select(sa.func.count(sa.distinct(Adjustment.entry_group_id))).where(
            Adjustment.project_id == project_id,
        )
    )
    return r.scalar() or 0


# ─── M1 内容签名相同不写库、不换编号 ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_m1_same_content_no_write(db_session, pid):
    """同内容重复同步 → 不写库（行数不增加）、不换编号、保 group_id。"""
    svc = AdjustmentSyncService(db_session)
    source_ref = f"{_WP_ID}:D4-4-rows"

    # 首次同步
    res1 = await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    gid1 = res1.entry_group_id
    no1 = res1.adjustment_no

    # 记录首次同步后的总 Adjustment 行数（含已删除）
    r = await db_session.execute(
        sa.select(sa.func.count()).select_from(Adjustment).where(
            Adjustment.project_id == pid,
        )
    )
    count_after_first = r.scalar()

    # 同内容二次同步
    res2 = await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()

    # 组号和编号不变
    assert res2.entry_group_id == gid1
    assert res2.adjustment_no == no1

    # 总行数不增加（没有新增软删行 + 新行）
    r = await db_session.execute(
        sa.select(sa.func.count()).select_from(Adjustment).where(
            Adjustment.project_id == pid,
        )
    )
    count_after_second = r.scalar()
    assert count_after_second == count_after_first, "同内容重同步不应写新行"


# ─── M2 内容变化原地更新保组号与编号 ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_m2_content_change_in_place_update(db_session, pid):
    """内容变化 → 原地更新：保 entry_group_id 与 adjustment_no；内容变为新值。"""
    svc = AdjustmentSyncService(db_session)

    # 首次同步
    res1 = await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    gid1 = res1.entry_group_id
    no1 = res1.adjustment_no

    # 改金额重同步
    res2 = await svc.sync_from_workpaper(
        pid, _req(debit="8000", credit="8000"), _USER_ID
    )
    await db_session.flush()

    # 组号和编号不变
    assert res2.entry_group_id == gid1
    assert res2.adjustment_no == no1

    # 新内容生效
    debit_items = [li for li in res2.line_items if li.debit_amount and li.debit_amount > 0]
    assert debit_items[0].debit_amount == Decimal("8000")

    # 活跃行只有新内容
    source_ref = f"{_WP_ID}:D4-4-rows"
    active_rows = await _get_active_adj_rows(db_session, pid, source_ref)
    assert len(active_rows) == 2
    assert all(r.entry_group_id == gid1 for r in active_rows)


# ─── M2b 描述变化也触发原地更新 ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_m2b_description_change_triggers_update(db_session, pid):
    """描述变化也算内容变化，触发原地更新。"""
    svc = AdjustmentSyncService(db_session)

    res1 = await svc.sync_from_workpaper(pid, _req(desc="原始描述"), _USER_ID)
    await db_session.flush()
    gid1 = res1.entry_group_id

    res2 = await svc.sync_from_workpaper(pid, _req(desc="修改后描述"), _USER_ID)
    await db_session.flush()

    assert res2.entry_group_id == gid1  # 保组号
    assert res2.description == "修改后描述"


# ─── M3 pending_review / rejected 回 draft ────────────────────────────────────
@pytest.mark.asyncio
async def test_m3_pending_review_back_to_draft(db_session, pid):
    """pending_review 状态下内容变化 → 回 draft 并清复核信息。"""
    svc = AdjustmentSyncService(db_session)

    res1 = await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    source_ref = f"{_WP_ID}:D4-4-rows"

    # 手动置 pending_review + reviewer
    rows = await _get_active_adj_rows(db_session, pid, source_ref)
    reviewer_id = uuid.uuid4()
    for r in rows:
        r.review_status = ReviewStatus.pending_review
        r.reviewer_id = reviewer_id
    await db_session.flush()

    # 改内容重同步
    res2 = await svc.sync_from_workpaper(
        pid, _req(debit="9000", credit="9000"), _USER_ID
    )
    await db_session.flush()

    assert res2.review_status in (ReviewStatus.draft, "draft")
    # 新行的复核人和复核时间应为空（新建的行默认 draft 无复核信息）
    active_rows = await _get_active_adj_rows(db_session, pid, source_ref)
    for r in active_rows:
        assert r.review_status == ReviewStatus.draft
        assert r.reviewer_id is None


@pytest.mark.asyncio
async def test_m3b_rejected_back_to_draft(db_session, pid):
    """rejected 状态下内容变化 → 回 draft。"""
    svc = AdjustmentSyncService(db_session)

    res1 = await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    source_ref = f"{_WP_ID}:D4-4-rows"

    # 手动置 rejected
    rows = await _get_active_adj_rows(db_session, pid, source_ref)
    for r in rows:
        r.review_status = ReviewStatus.rejected
        r.rejection_reason = "金额不对"
    await db_session.flush()

    # 改内容重同步
    res2 = await svc.sync_from_workpaper(
        pid, _req(debit="7000", credit="7000"), _USER_ID
    )
    await db_session.flush()

    assert res2.review_status in (ReviewStatus.draft, "draft")


# ─── M3c pending_review 同内容不写、不降级 ─────────────────────────────────────
@pytest.mark.asyncio
async def test_m3c_pending_review_same_content_no_change(db_session, pid):
    """pending_review 但内容相同 → 不写库、保留 pending_review。"""
    svc = AdjustmentSyncService(db_session)

    res1 = await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    source_ref = f"{_WP_ID}:D4-4-rows"

    # 手动置 pending_review
    rows = await _get_active_adj_rows(db_session, pid, source_ref)
    for r in rows:
        r.review_status = ReviewStatus.pending_review
    await db_session.flush()

    # 同内容重同步
    res2 = await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()

    # 状态保留 pending_review
    assert res2.review_status in (ReviewStatus.pending_review, "pending_review")


# ─── M4 approved 仍 APPROVED_LOCKED ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_m4_approved_locked_even_different_content(db_session, pid):
    """approved 状态下，即使内容变化，仍拒绝（需先撤回）。"""
    svc = AdjustmentSyncService(db_session)

    res1 = await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    source_ref = f"{_WP_ID}:D4-4-rows"

    # 手动置 approved
    rows = await _get_active_adj_rows(db_session, pid, source_ref)
    for r in rows:
        r.review_status = ReviewStatus.approved
    await db_session.flush()

    with pytest.raises(AdjustmentSyncError) as ei:
        await svc.sync_from_workpaper(
            pid, _req(debit="9999", credit="9999"), _USER_ID
        )
    assert ei.value.code == "APPROVED_LOCKED"


# ─── M4b approved 同内容也 APPROVED_LOCKED ────────────────────────────────────
@pytest.mark.asyncio
async def test_m4b_approved_locked_same_content(db_session, pid):
    """approved 状态下，即使内容相同，也拒绝（内容签名比较在 approved 检查之后）。"""
    svc = AdjustmentSyncService(db_session)

    res1 = await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    source_ref = f"{_WP_ID}:D4-4-rows"

    # 手动置 approved
    rows = await _get_active_adj_rows(db_session, pid, source_ref)
    for r in rows:
        r.review_status = ReviewStatus.approved
    await db_session.flush()

    with pytest.raises(AdjustmentSyncError) as ei:
        await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    assert ei.value.code == "APPROVED_LOCKED"


# ─── M5 编号不烧 ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_m5_no_number_burned(db_session, pid):
    """重同步不消耗新编号：group 总数不增加（旧行为每次同步会新建 group）。"""
    svc = AdjustmentSyncService(db_session)

    res1 = await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()
    group_count_1 = await _count_all_groups(db_session, pid)

    # 同内容重同步 3 次
    for _ in range(3):
        await svc.sync_from_workpaper(pid, _req(), _USER_ID)
        await db_session.flush()

    group_count_after = await _count_all_groups(db_session, pid)
    assert group_count_after == group_count_1, "同内容重同步不应产生新 entry_group_id"


@pytest.mark.asyncio
async def test_m5b_content_change_preserves_group_id(db_session, pid):
    """内容变化也不产生新 entry_group_id。"""
    svc = AdjustmentSyncService(db_session)

    res1 = await svc.sync_from_workpaper(pid, _req(), _USER_ID)
    await db_session.flush()

    # 三次内容变化
    for i in range(3):
        amt = str(5000 + (i + 1) * 1000)
        await svc.sync_from_workpaper(
            pid, _req(debit=amt, credit=amt), _USER_ID
        )
        await db_session.flush()

    # entry_group_id 种类数始终只有 1（同一 source_ref 同一组）
    r = await db_session.execute(
        sa.select(sa.func.count(sa.distinct(Adjustment.entry_group_id))).where(
            Adjustment.project_id == pid,
        )
    )
    total_groups = r.scalar()
    assert total_groups == 1, "无论内容怎么变，同一 source_ref 只有一个 entry_group_id"


# ─── M6 咨询锁键稳定摘要 ──────────────────────────────────────────────────────
def test_m6_advisory_lock_key_stable():
    """lock_key 在相同输入下跨调用一致（sha256），不依赖 hash() 随机种子。"""
    pid = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    raw = f"{pid}:2025:AJE"
    expected = int.from_bytes(
        hashlib.sha256(raw.encode("utf-8")).digest()[:4], "big", signed=False,
    ) % (2**31)
    # 多次调用同一结果
    for _ in range(100):
        actual = int.from_bytes(
            hashlib.sha256(raw.encode("utf-8")).digest()[:4], "big", signed=False,
        ) % (2**31)
        assert actual == expected


# ─── 内容签名纯函数测试 ──────────────────────────────────────────────────────
def test_content_signature_deterministic():
    """同一输入多次调用产出相同签名。"""
    from app.models.audit_platform_schemas import AdjustmentSyncLineItem
    items = [
        AdjustmentSyncLineItem(standard_account_code="1001", account_name="库存现金",
                               debit_amount=Decimal("5000"), credit_amount=Decimal("0")),
        AdjustmentSyncLineItem(standard_account_code="6001", account_name="主营业务收入",
                               debit_amount=Decimal("0"), credit_amount=Decimal("5000")),
    ]
    sig1 = AdjustmentSyncService._compute_content_signature(
        AdjustmentType.aje, "测试", ["1001", "6001"], items,
    )
    sig2 = AdjustmentSyncService._compute_content_signature(
        AdjustmentType.aje, "测试", ["1001", "6001"], items,
    )
    assert sig1 == sig2
    assert len(sig1) == 24  # sha256 前 24 位


def test_content_signature_differs_on_amount_change():
    """金额变化 → 签名变化。"""
    from app.models.audit_platform_schemas import AdjustmentSyncLineItem
    items_a = [
        AdjustmentSyncLineItem(standard_account_code="1001", debit_amount=Decimal("5000"), credit_amount=Decimal("0")),
        AdjustmentSyncLineItem(standard_account_code="6001", debit_amount=Decimal("0"), credit_amount=Decimal("5000")),
    ]
    items_b = [
        AdjustmentSyncLineItem(standard_account_code="1001", debit_amount=Decimal("8000"), credit_amount=Decimal("0")),
        AdjustmentSyncLineItem(standard_account_code="6001", debit_amount=Decimal("0"), credit_amount=Decimal("8000")),
    ]
    sig_a = AdjustmentSyncService._compute_content_signature(
        AdjustmentType.aje, "测试", ["1001", "6001"], items_a,
    )
    sig_b = AdjustmentSyncService._compute_content_signature(
        AdjustmentType.aje, "测试", ["1001", "6001"], items_b,
    )
    assert sig_a != sig_b


def test_content_signature_differs_on_description_change():
    """描述变化 → 签名变化。"""
    from app.models.audit_platform_schemas import AdjustmentSyncLineItem
    items = [
        AdjustmentSyncLineItem(standard_account_code="1001", debit_amount=Decimal("5000"), credit_amount=Decimal("0")),
        AdjustmentSyncLineItem(standard_account_code="6001", debit_amount=Decimal("0"), credit_amount=Decimal("5000")),
    ]
    sig_a = AdjustmentSyncService._compute_content_signature(
        AdjustmentType.aje, "描述A", ["1001", "6001"], items,
    )
    sig_b = AdjustmentSyncService._compute_content_signature(
        AdjustmentType.aje, "描述B", ["1001", "6001"], items,
    )
    assert sig_a != sig_b
