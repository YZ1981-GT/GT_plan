"""客户已入账 PG 验收夹具。

只在回滚事务中创建【测试】项目、账套和调整分录，供两个 pg_only 文件复用。
夹具不调用应用启动流程，也不提交共享库数据。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountMapping,
    AccountSource,
    AdjustmentType,
    MappingType,
    ReviewStatus,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.models.base import UserRole
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.adjustment_group_writer import AdjustmentGroupLine, AdjustmentGroupWriter
from app.services.voucher_identity import VoucherKey

YEAR = 2025


@pytest_asyncio.fixture
async def booking_pg_world():
    if not str(settings.DATABASE_URL).split("://", 1)[0].startswith("postgres"):
        pytest.skip("需要真实 PostgreSQL")

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        outer = await conn.begin()
        db = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            actor = User(
                id=uuid.uuid4(),
                username=f"t_adj_booking_{uuid.uuid4().hex[:8]}",
                email=f"t_adj_booking_{uuid.uuid4().hex[:8]}@test.local",
                hashed_password="x",
                role=UserRole.manager,
            )
            project = Project(
                id=uuid.uuid4(),
                name=f"【测试】客户入账 PG {uuid.uuid4().hex[:8]}",
                client_name="【测试】客户入账 PG",
                project_type=ProjectType.annual,
                status=ProjectStatus.execution,
                company_code="913500001234567890",
                created_by=actor.id,
            )
            db.add(actor)
            await db.flush()
            db.add(project)
            await db.flush()

            account_names = {"1122": "应收账款", "6702": "信用减值损失"}
            for code, name in account_names.items():
                db.add(AccountChart(
                    project_id=project.id,
                    account_code=code,
                    account_name=name,
                    direction=AccountDirection.debit,
                    level=1,
                    category=AccountCategory.asset if code == "1122" else AccountCategory.expense,
                    source=AccountSource.standard,
                ))
                db.add(AccountMapping(
                    project_id=project.id,
                    original_account_code=code,
                    original_account_name=name,
                    standard_account_code=code,
                    mapping_type=MappingType.auto_exact,
                    created_by=actor.id,
                ))
            await db.flush()

            old_dataset = LedgerDataset(
                id=uuid.uuid4(),
                project_id=project.id,
                year=YEAR,
                status=DatasetStatus.superseded,
                source_type="import",
                created_by=actor.id,
                created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            )
            active_dataset = LedgerDataset(
                id=uuid.uuid4(),
                project_id=project.id,
                year=YEAR,
                status=DatasetStatus.active,
                source_type="import",
                created_by=actor.id,
                previous_dataset_id=old_dataset.id,
                created_at=datetime(2025, 12, 31, tzinfo=timezone.utc),
                activated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
            db.add(old_dataset)
            await db.flush()
            db.add(active_dataset)
            await db.flush()

            for dataset_id in (old_dataset.id, active_dataset.id):
                for code, name in account_names.items():
                    db.add(TbBalance(
                        project_id=project.id,
                        year=YEAR,
                        company_code="001",
                        account_code=code,
                        account_name=name,
                        level=1,
                        opening_balance=Decimal("0"),
                        debit_amount=Decimal("100"),
                        credit_amount=Decimal("0"),
                        closing_balance=Decimal("100"),
                        closing_direction="debit",
                        dataset_id=dataset_id,
                    ))

            for code, name in account_names.items():
                db.add(TrialBalance(
                    project_id=project.id,
                    year=YEAR,
                    company_code="001",
                    standard_account_code=code,
                    account_name=name,
                    account_category=AccountCategory.asset if code == "1122" else AccountCategory.expense,
                    unadjusted_amount=Decimal("1000"),
                    aje_adjustment=Decimal("0"),
                    rje_adjustment=Decimal("0"),
                    wp_adjustment=Decimal("0"),
                    audited_amount=Decimal("1000"),
                ))

            key = VoucherKey.of(
                year=YEAR,
                company_code="001",
                voucher_date=date(2025, 12, 31),
                voucher_type="记",
                voucher_no="0008",
            )
            for seq, (code, debit, credit) in enumerate((
                ("1122", Decimal("100"), Decimal("0")),
                ("6702", Decimal("0"), Decimal("100")),
            ), start=1):
                db.add(TbLedger(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    year=YEAR,
                    company_code="001",
                    voucher_date=key.date_value,
                    voucher_type=key.voucher_type,
                    voucher_no=key.voucher_no,
                    entry_seq=seq,
                    account_code=code,
                    account_name=account_names[code],
                    debit_amount=debit,
                    credit_amount=credit,
                    summary="客户入账调整",
                    dataset_id=active_dataset.id,
                ))

            group_id = uuid.uuid4()
            await AdjustmentGroupWriter(db).write_group(
                project_id=project.id,
                year=YEAR,
                company_code="001",
                adjustment_no="AJE-PG-BOOK-001",
                adjustment_type=AdjustmentType.aje,
                description="客户已在年末入账",
                entry_group_id=group_id,
                lines=[
                    AdjustmentGroupLine(
                        standard_account_code="1122",
                        account_name=account_names["1122"],
                        debit_amount=Decimal("100"),
                    ),
                    AdjustmentGroupLine(
                        standard_account_code="6702",
                        account_name=account_names["6702"],
                        credit_amount=Decimal("100"),
                    ),
                ],
                content_revision=1,
                audit_phase="final",
                review_status=ReviewStatus.approved,
                created_by=actor.id,
            )
            await db.flush()
            yield SimpleNamespace(
                db=db,
                conn=conn,
                actor=actor,
                project=project,
                old_dataset=old_dataset,
                active_dataset=active_dataset,
                key=key,
                group_id=group_id,
                account_names=account_names,
            )
        finally:
            await db.close()
            if outer.is_active:
                await outer.rollback()
    await engine.dispose()
