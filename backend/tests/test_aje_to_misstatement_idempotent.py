"""Spec A 集成测试：AJE → 错报转换幂等性

Validates: requirements.md R4 + design.md D5 + Property P3
"""
from __future__ import annotations

import pytest
from uuid import UUID, uuid4
from decimal import Decimal


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_aje_to_misstatement_idempotent(db_session):
    """Property P3: 同一笔 AJE 重复转换应抛 ALREADY_CONVERTED"""
    from app.services.misstatement_service import UnadjustedMisstatementService
    from app.models.audit_platform_models import (
        Adjustment, AdjustmentType, ReviewStatus,
    )

    project_id = UUID("00000000-0000-0000-0000-000000000001")
    year = 2025
    eg_id = uuid4()

    # 准备一笔 rejected AJE
    adj = Adjustment(
        project_id=project_id, year=year, company_code="default",
        adjustment_no="AJE-TEST-001", adjustment_type=AdjustmentType.aje,
        description="测试 AJE", account_code="1001",
        account_name="库存现金", debit_amount=Decimal("100"),
        credit_amount=Decimal("0"), entry_group_id=eg_id,
        review_status=ReviewStatus.rejected,
    )
    db_session.add(adj)
    await db_session.flush()

    svc = UnadjustedMisstatementService(db_session)

    # 第一次转换：成功
    r1 = await svc.create_from_rejected_aje(project_id, eg_id, year, None)
    assert r1.id is not None

    # 第二次转换：抛 ALREADY_CONVERTED
    with pytest.raises(ValueError) as exc_info:
        await svc.create_from_rejected_aje(project_id, eg_id, year, None)
    assert str(exc_info.value) == "ALREADY_CONVERTED"
    # 错误对象上挂 misstatement_id
    assert hasattr(exc_info.value, "misstatement_id")
    assert exc_info.value.misstatement_id == str(r1.id)


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_aje_to_misstatement_nonexistent(db_session):
    """不存在的分录组应抛 ValueError"""
    from app.services.misstatement_service import UnadjustedMisstatementService

    svc = UnadjustedMisstatementService(db_session)

    with pytest.raises(ValueError) as exc_info:
        await svc.create_from_rejected_aje(
            UUID("00000000-0000-0000-0000-000000000099"),
            uuid4(),
            2025,
            None,
        )
    assert "调整分录不存在" in str(exc_info.value)
