"""审定表域写入经发布门口径：写入后 ``recalc_audited`` 不把值算回去（真 SQLite + 真 ORM）。

缺陷（2026-11-26 公式管理排查）：``AdjudicationMutationAdapter`` 与
``AdjudicationWritebackService._write_audited`` 只改 ``audited_amount``、不动 ``wp_adjustment``，
下一次未审数 / 调整分录重算按 ``unadj + rje + aje + wp_adjustment`` 把写入值静默覆盖掉。
现两处都经 ``tb_audited_writer.write_audited_row``（同步回算 ``wp_adjustment``）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.audit_platform_models import TrialBalance
from app.services.formula_runtime.adapters.adjudication import AdjudicationMutationAdapter
from app.services.formula_runtime.contracts import CanonicalFormulaTarget
from app.services.tb_audited_writer import write_audited_row
from app.services.trial_balance_service import TrialBalanceService
from tests.test_tb_audited_writer import _seed_project, _tb_row, writer_session  # noqa: F401  夹具


async def _row(session, row_id) -> TrialBalance:
    session.expire_all()
    return (await session.execute(sa.select(TrialBalance).where(TrialBalance.id == row_id))).scalar_one()


@pytest.mark.asyncio
async def test_write_audited_row_survives_recalc(writer_session):
    project_id = await _seed_project(writer_session)
    row = _tb_row(project_id, "1001")  # 未审 100 + rje 5 + aje -2 = 103
    writer_session.add(row)
    await writer_session.flush()

    await write_audited_row(writer_session, row, Decimal("150.00"), now=datetime.now(timezone.utc))
    await writer_session.flush()
    stored = await _row(writer_session, row.id)
    assert stored.audited_amount == Decimal("150.00")
    assert stored.wp_adjustment == Decimal("47.00")  # 150 − 103

    await TrialBalanceService(writer_session).recalc_audited(project_id, 2025)
    assert (await _row(writer_session, row.id)).audited_amount == Decimal("150.00"), "重算把写入值算回去了"


@pytest.mark.asyncio
async def test_adjudication_adapter_apply_and_restore_survive_recalc(writer_session):
    project_id = await _seed_project(writer_session)
    row = _tb_row(project_id, "1122")
    writer_session.add(row)
    await writer_session.flush()

    adapter = AdjudicationMutationAdapter(writer_session)
    target = CanonicalFormulaTarget(domain="adjudication", project_id=project_id, year=2025,
                                    addr_id="adj/1122", locator={"standard_account_code": "1122"})
    (mutation,) = await adapter.prepare_many([target], {"adj/1122": Decimal("200.00")})
    await adapter.apply_many([mutation])
    await TrialBalanceService(writer_session).recalc_audited(project_id, 2025)
    assert (await _row(writer_session, row.id)).audited_amount == Decimal("200.00")

    (restored,) = await adapter.restore_many([mutation])
    assert not restored.conflict
    await TrialBalanceService(writer_session).recalc_audited(project_id, 2025)
    back = await _row(writer_session, row.id)
    assert back.audited_amount == Decimal("103.00") and back.wp_adjustment == Decimal("0.00")
