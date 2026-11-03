"""客户已入账：三处计算同源、账套回滚恢复、撤销与精确建议。"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.adjustment_review_models import AdjustmentClientBooking, AdjustmentTreatmentEvent
from app.models.audit_platform_models import (
    AccountCategory, AccountChart, AccountDirection, AccountMapping, AccountSource,
    Adjustment, AdjustmentEntry, AdjustmentType, ReviewStatus, TbLedger, TrialBalance,
    UnadjustedMisstatement,
)
from app.models.base import Base, UserRole
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.models.dataset_models import DatasetStatus, ImportEventConsumption, ImportEventOutbox, LedgerDataset
from app.services.adjustment_amount_source import adj_net, adj_net_batch
from app.services.adjustment_client_booking import (
    apply_booking_change, booking_projection, effective_booked_group_ids,
    mark_booked, revoke_booking, suggest_bookings,
)
from app.services.adjustment_group_writer import AdjustmentGroupLine, AdjustmentGroupWriter
from app.services.adjustment_treatment_service import (
    convert_to_unadjusted_misstatement,
    effective_excluded_group_ids,
    treatment_history,
    treatment_projection,
    withdraw_current_treatment,
)
from app.services.trial_balance_service import TrialBalanceService
from app.services.voucher_identity import VoucherKey

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


@pytest_asyncio.fixture
async def world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        User.__table__, Project.__table__, LedgerDataset.__table__,
        AccountChart.__table__, AccountMapping.__table__, Adjustment.__table__, AdjustmentEntry.__table__,
        TbLedger.__table__, TrialBalance.__table__, AdjustmentClientBooking.__table__,
        AdjustmentTreatmentEvent.__table__, UnadjustedMisstatement.__table__,
        ImportEventOutbox.__table__, ImportEventConsumption.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(
            id=uuid.uuid4(), username="booking_user", email="booking@test.local",
            hashed_password="x", role=UserRole.manager,
        )
        project = Project(
            id=uuid.uuid4(), name="【测试】客户已入账", client_name="【测试】客户已入账",
            project_type=ProjectType.annual, status=ProjectStatus.execution,
            company_code="913500001234567890", created_by=user.id,
        )
        db.add_all([user, project])
        await db.flush()
        for code, name, direction, category in [
            ("1122", "应收账款", AccountDirection.debit, AccountCategory.asset),
            ("6702", "信用减值损失", AccountDirection.debit, AccountCategory.expense),
        ]:
            db.add(AccountChart(
                project_id=project.id, account_code=code, account_name=name,
                direction=direction, category=category, level=1, source=AccountSource.standard,
            ))
            db.add(TrialBalance(
                project_id=project.id, year=2025, company_code="001",
                standard_account_code=code, account_name=name, account_category=category,
                unadjusted_amount=Decimal("1000"), aje_adjustment=Decimal("0"),
                rje_adjustment=Decimal("0"), wp_adjustment=Decimal("0"), audited_amount=Decimal("1000"),
            ))
        old = LedgerDataset(
            id=uuid.uuid4(), project_id=project.id, year=2025,
            status=DatasetStatus.superseded, source_type="import", created_by=user.id,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        current = LedgerDataset(
            id=uuid.uuid4(), project_id=project.id, year=2025,
            status=DatasetStatus.active, source_type="import", created_by=user.id,
            created_at=datetime(2025, 12, 31, tzinfo=timezone.utc),
            activated_at=datetime(2026, 1, 2, tzinfo=timezone.utc), previous_dataset_id=old.id,
        )
        db.add_all([old, current])
        await db.flush()
        key = VoucherKey.of(
            year=2025, company_code="001", voucher_date=date(2025, 12, 31),
            voucher_type="记", voucher_no="0008",
        )
        for seq, (code, debit, credit) in enumerate([
            ("1122", Decimal("100"), Decimal("0")),
            ("6702", Decimal("0"), Decimal("100")),
        ], start=1):
            db.add(TbLedger(
                id=uuid.uuid4(), project_id=project.id, year=2025, company_code="001",
                voucher_date=key.date_value, voucher_type=key.voucher_type, voucher_no=key.voucher_no,
                entry_seq=seq, account_code=code, account_name=code,
                debit_amount=debit, credit_amount=credit, summary="客户入账调整",
                dataset_id=current.id,
            ))
        group_id = uuid.uuid4()
        await AdjustmentGroupWriter(db).write_group(
            project_id=project.id, year=2025, company_code="001",
            adjustment_no="AJE-BOOK-001", adjustment_type=AdjustmentType.aje,
            description="客户已在年末入账", entry_group_id=group_id,
            lines=[
                AdjustmentGroupLine(standard_account_code="1122", account_name="应收账款", debit_amount=Decimal("100")),
                AdjustmentGroupLine(standard_account_code="6702", account_name="信用减值损失", credit_amount=Decimal("100")),
            ], content_revision=1, audit_phase="preliminary",
            review_status=ReviewStatus.approved, created_by=user.id,
        )
        await db.commit()
        yield db, user, project, old, current, key, group_id
    await engine.dispose()


@pytest.mark.asyncio
async def test_mark_booked_excludes_all_three_calculation_paths_and_rollback_restores(world):
    db, user, project, old, current, key, group_id = world
    before = await adj_net(
        db, project_id=project.id, year=2025, account_code="1122", adj_type="aje_net",
        exclude_origins=frozenset({"workpaper"}),
    )
    assert before == Decimal("100")

    record = await mark_booked(
        db, project_id=project.id, year=2025, entry_group_id=group_id,
        voucher_key_values=[key.to_str()], actor_id=user.id, note="客户已提供入账凭证",
    )
    await apply_booking_change(
        db, project_id=project.id, year=2025, entry_group_id=group_id,
        actor_id=user.id, action="book",
    )
    await db.flush()
    assert record.booked_dataset_id == current.id
    assert await effective_booked_group_ids(db, project_id=project.id, year=2025) == {group_id}
    assert await adj_net(
        db, project_id=project.id, year=2025, account_code="1122", adj_type="aje_net",
        exclude_origins=frozenset({"workpaper"}),
    ) == Decimal("0")
    batch = await adj_net_batch(
        db, project_id=project.id, year=2025, account_codes={"1122", "6702"},
        exclude_origins=frozenset({"workpaper"}),
    )
    assert batch == {}
    await TrialBalanceService(db).recalc_adjustments(
        project.id, 2025, company_code="001", account_codes=["1122", "6702"],
    )
    tb_aje = dict((await db.execute(sa.select(
        TrialBalance.standard_account_code, TrialBalance.aje_adjustment,
    ).where(TrialBalance.project_id == project.id))).all())
    assert tb_aje == {"1122": Decimal("0"), "6702": Decimal("0")}

    # 回滚到标记前的旧账套：标记自动失效，AJE 恢复计入。
    current.status = DatasetStatus.superseded
    old.status = DatasetStatus.active
    old.activated_at = datetime(2026, 1, 3, tzinfo=timezone.utc)
    await db.flush()
    assert await effective_booked_group_ids(db, project_id=project.id, year=2025) == set()
    assert await adj_net(
        db, project_id=project.id, year=2025, account_code="1122", adj_type="aje_net",
        exclude_origins=frozenset({"workpaper"}),
    ) == Decimal("100")


@pytest.mark.asyncio
async def test_revoke_and_projection_preserve_append_only_history(world):
    db, user, project, _old, _current, key, group_id = world
    await mark_booked(
        db, project_id=project.id, year=2025, entry_group_id=group_id,
        voucher_key_values=[key.to_str()], actor_id=user.id,
    )
    revoked = await revoke_booking(
        db, project_id=project.id, year=2025, entry_group_id=group_id,
        actor_id=user.id, reason="客户凭证已冲销",
    )
    projection = await booking_projection(
        db, project_id=project.id, year=2025, group_ids=[group_id],
    )
    assert revoked.action == "revoke"
    assert projection[str(group_id)].status == "revoked"
    assert projection[str(group_id)].effective is False
    rows = list((await db.execute(sa.select(AdjustmentClientBooking).where(
        AdjustmentClientBooking.entry_group_id == group_id,
    ))).scalars().all())
    assert [row.action for row in rows] == ["book", "revoke"]


@pytest.mark.asyncio
async def test_suggestion_is_exact_and_one_cent_difference_is_not_candidate(world):
    db, _user, project, _old, _current, key, group_id = world
    suggestions = await suggest_bookings(db, project_id=project.id, year=2025)
    assert len(suggestions) == 1
    assert suggestions[0]["entry_group_id"] == str(group_id)
    assert suggestions[0]["candidates"][0]["voucher_key"] == key.to_str()
    ledger = (await db.execute(sa.select(TbLedger).where(
        TbLedger.project_id == project.id, TbLedger.account_code == "1122",
    ))).scalars().one()
    ledger.debit_amount = Decimal("100.01")
    await db.flush()
    assert await suggest_bookings(db, project_id=project.id, year=2025) == []


@pytest.mark.asyncio
async def test_unadjusted_treatment_is_mutually_exclusive_and_withdraw_restores_tb(world):
    db, user, project, _old, _current, _key, group_id = world
    before = await treatment_projection(
        db, project_id=project.id, year=2025, group_ids=[group_id],
    )
    assert before[str(group_id)].status == "include_in_working_tb"

    result = await convert_to_unadjusted_misstatement(
        db, project_id=project.id, year=2025, entry_group_id=group_id,
        actor_id=user.id, management_reason="管理层认为金额不重大",
        management_communication_at=datetime(2025, 12, 31, tzinfo=timezone.utc),
        auditor_evaluation="累计后未超过整体重要性",
    )
    await db.flush()
    assert result["misstatement_id"]
    assert await effective_excluded_group_ids(db, project_id=project.id, year=2025) == {group_id}
    assert (await treatment_history(
        db, project_id=project.id, year=2025, entry_group_id=group_id,
    ))[0]["action"] == "unadjusted_misstatement"
    assert await adj_net(
        db, project_id=project.id, year=2025, account_code="1122", adj_type="aje_net",
        exclude_origins=frozenset({"workpaper"}),
    ) == Decimal("0")

    await withdraw_current_treatment(
        db, project_id=project.id, year=2025, entry_group_id=group_id,
        actor_id=user.id, reason="管理层同意调账",
    )
    await db.flush()
    assert await effective_excluded_group_ids(db, project_id=project.id, year=2025) == set()
    assert await adj_net(
        db, project_id=project.id, year=2025, account_code="1122", adj_type="aje_net",
        exclude_origins=frozenset({"workpaper"}),
    ) == Decimal("100")
    misstatement = (await db.execute(sa.select(UnadjustedMisstatement))).scalars().one()
    assert misstatement.is_deleted is True
    assert [item["action"] for item in await treatment_history(
        db, project_id=project.id, year=2025, entry_group_id=group_id,
    )] == ["withdraw", "unadjusted_misstatement"]
