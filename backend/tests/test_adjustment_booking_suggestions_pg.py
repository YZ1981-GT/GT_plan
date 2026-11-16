"""客户入账建议真实 PG 验收（需求 6.2）。"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import uuid

import pytest

from app.models.audit_platform_models import AdjustmentType, ReviewStatus, TbLedger
from app.services.adjustment_client_booking import suggest_bookings
from app.services.adjustment_group_writer import AdjustmentGroupLine, AdjustmentGroupWriter

pytestmark = pytest.mark.pg_only
pytest_plugins = ("tests._adjustment_booking_pg_support",)


@pytest.mark.asyncio
async def test_pg_suggestions_require_exact_amount_side_and_list_all_vouchers(booking_pg_world):
    world = booking_pg_world
    db = world.db
    account_names = world.account_names

    # 第二张完全匹配的凭证：建议必须全部列出，并按距离排序。
    for seq, (code, debit, credit) in enumerate((
        ("1122", Decimal("100"), Decimal("0")),
        ("6702", Decimal("0"), Decimal("100")),
    ), start=1):
        db.add(TbLedger(
            id=uuid.uuid4(),
            project_id=world.project.id,
            year=2025,
            company_code="001",
            voucher_date=date(2025, 12, 30),
            voucher_type="转",
            voucher_no="0009",
            entry_seq=seq,
            account_code=code,
            account_name=account_names[code],
            debit_amount=debit,
            credit_amount=credit,
            summary="第二张客户入账凭证",
            dataset_id=world.active_dataset.id,
        ))

    # 借贷方向相反：科目与金额相同，但不能成为候选。
    for seq, (code, debit, credit) in enumerate((
        ("1122", Decimal("0"), Decimal("100")),
        ("6702", Decimal("100"), Decimal("0")),
    ), start=1):
        db.add(TbLedger(
            id=uuid.uuid4(),
            project_id=world.project.id,
            year=2025,
            company_code="001",
            voucher_date=date(2025, 12, 29),
            voucher_type="转",
            voucher_no="0010",
            entry_seq=seq,
            account_code=code,
            account_name=account_names[code],
            debit_amount=debit,
            credit_amount=credit,
            summary="借贷相反，不应匹配",
            dataset_id=world.active_dataset.id,
        ))

    # 一分钱差异的独立 AJE 组：不得因为科目相同而被模糊推荐。
    await AdjustmentGroupWriter(db).write_group(
        project_id=world.project.id,
        year=2025,
        company_code="001",
        adjustment_no="AJE-PG-BOOK-002",
        adjustment_type=AdjustmentType.aje,
        description="金额差一分钱",
        entry_group_id=uuid.uuid4(),
        lines=[
            AdjustmentGroupLine(
                standard_account_code="1122",
                account_name=account_names["1122"],
                debit_amount=Decimal("100.01"),
            ),
            AdjustmentGroupLine(
                standard_account_code="6702",
                account_name=account_names["6702"],
                credit_amount=Decimal("100.01"),
            ),
        ],
        content_revision=1,
        audit_phase="final",
        review_status=ReviewStatus.approved,
        created_by=world.actor.id,
    )
    await db.flush()

    suggestions = await suggest_bookings(db, project_id=world.project.id, year=2025)
    first = next(item for item in suggestions if item["entry_group_id"] == str(world.group_id))
    keys = [item["voucher_key"] for item in first["candidates"]]
    assert keys == sorted(keys, key=lambda key: next(
        item["distance_days"] for item in first["candidates"] if item["voucher_key"] == key
    ))
    assert {item["voucher_no"] for item in first["candidates"]} == {"0008", "0009"}
    assert all(item["voucher_no"] != "0010" for item in first["candidates"])
    assert not any(item["adjustment_no"] == "AJE-PG-BOOK-002" for item in suggestions)
