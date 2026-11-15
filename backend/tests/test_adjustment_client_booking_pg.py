"""客户已入账真实 PG 全流程（需求 6.1）。

在真实 PostgreSQL 的最后回滚事务内验证：AJE 计算 → 客户已入账 →
当前账套回滚后恢复计入 → 撤销标记。SQLite 版本不能替代这里的账套时间、JSONB、
外键和真实全量重算行为。
"""
from __future__ import annotations

from fastapi import FastAPI
import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.adjustment_review_models import AdjustmentClientBooking
from app.models.audit_platform_models import TrialBalance
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.core import User
from app.models.dataset_models import DatasetStatus
from app.routers.adjustment_client_booking import router as booking_router
from app.services.adjustment_amount_source import adj_net
from app.services.adjustment_client_booking import (
    apply_booking_change,
    booking_history,
    effective_booked_group_ids,
    mark_booked,
    revoke_booking,
)
from app.services.adjustment_treatment_service import record_client_booking, record_withdrawal
from app.services.dataset_service import DatasetService
from app.services.trial_balance_service import TrialBalanceService

pytestmark = pytest.mark.pg_only
pytest_plugins = ("tests._adjustment_booking_pg_support",)


async def _tb_adjustments(db, project_id):
    rows = (await db.execute(sa.select(
        TrialBalance.standard_account_code,
        TrialBalance.aje_adjustment,
        TrialBalance.audited_amount,
    ).where(
        TrialBalance.project_id == project_id,
        TrialBalance.year == 2025,
    ))).all()
    return {code: (aje, audited) for code, aje, audited in rows}


@pytest.mark.asyncio
async def test_pg_booking_rollback_and_revoke_restore_all_calculation_readers(booking_pg_world):
    world = booking_pg_world
    db = world.db
    before = await adj_net(
        db,
        project_id=world.project.id,
        year=2025,
        account_code="1122",
        adj_type="aje_net",
        exclude_origins=frozenset({"workpaper"}),
    )
    assert before == 100

    record = await mark_booked(
        db,
        project_id=world.project.id,
        year=2025,
        entry_group_id=world.group_id,
        voucher_key_values=[world.key.to_str()],
        actor_id=world.actor.id,
        note="客户凭证已入账",
    )
    await record_client_booking(
        db,
        project_id=world.project.id,
        year=2025,
        entry_group_id=world.group_id,
        actor_id=world.actor.id,
        booking=record,
    )
    await apply_booking_change(
        db,
        project_id=world.project.id,
        year=2025,
        entry_group_id=world.group_id,
        actor_id=world.actor.id,
        action="book",
    )
    await db.flush()

    assert await effective_booked_group_ids(
        db, project_id=world.project.id, year=2025,
    ) == {world.group_id}
    assert await adj_net(
        db,
        project_id=world.project.id,
        year=2025,
        account_code="1122",
        adj_type="aje_net",
        exclude_origins=frozenset({"workpaper"}),
    ) == 0
    tb = await _tb_adjustments(db, world.project.id)
    assert tb["1122"] == (0, 1000)
    assert tb["6702"] == (0, 1000)

    # 真实回滚处理器走 full_recalc，而不是只重新读 effective_booked_group_ids。
    world.active_dataset.status = DatasetStatus.superseded
    await db.flush()
    world.old_dataset.status = DatasetStatus.active
    world.old_dataset.activated_at = world.active_dataset.activated_at
    await db.flush()
    await TrialBalanceService(db).on_import_rolled_back(EventPayload(
        event_type=EventType.LEDGER_DATASET_ROLLED_BACK,
        project_id=world.project.id,
        year=2025,
        extra={
            "rolled_back_dataset_id": str(world.active_dataset.id),
            "restored_dataset_id": str(world.old_dataset.id),
        },
    ))
    await db.flush()

    assert await effective_booked_group_ids(
        db, project_id=world.project.id, year=2025,
    ) == set()
    assert await adj_net(
        db,
        project_id=world.project.id,
        year=2025,
        account_code="1122",
        adj_type="aje_net",
        exclude_origins=frozenset({"workpaper"}),
    ) == 100
    tb = await _tb_adjustments(db, world.project.id)
    assert tb["1122"] == (100, 200)
    assert tb["6702"] == (-100, 0)

    revoked = await revoke_booking(
        db,
        project_id=world.project.id,
        year=2025,
        entry_group_id=world.group_id,
        actor_id=world.actor.id,
        reason="客户凭证已冲销",
    )
    await record_withdrawal(
        db,
        project_id=world.project.id,
        year=2025,
        entry_group_id=world.group_id,
        actor_id=world.actor.id,
        reason="客户凭证已冲销",
    )
    await apply_booking_change(
        db,
        project_id=world.project.id,
        year=2025,
        entry_group_id=world.group_id,
        actor_id=world.actor.id,
        action="revoke",
    )
    await db.flush()

    history = await booking_history(
        db, project_id=world.project.id, year=2025, entry_group_id=world.group_id,
    )
    actions = [item["action"] for item in history]
    assert len(actions) == 2
    assert set(actions) == {"book", "revoke"}
    assert revoked.action == "revoke"
    assert await effective_booked_group_ids(
        db, project_id=world.project.id, year=2025,
    ) == set()
    assert (await db.execute(sa.select(sa.func.count()).select_from(AdjustmentClientBooking).where(
        AdjustmentClientBooking.entry_group_id == world.group_id,
    ))).scalar_one() == 2


@pytest.mark.asyncio
async def test_pg_booking_routes_use_real_http_and_revoke_is_append_only(booking_pg_world):
    world = booking_pg_world
    admin = (await world.db.execute(sa.select(User).where(User.username == "admin"))).scalar_one()
    route_db = AsyncSession(
        bind=world.conn,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    app = FastAPI()
    app.include_router(booking_router)

    async def override_db():
        yield route_db

    async def override_user():
        return admin

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    url = f"/api/projects/{world.project.id}/adjustments/{world.group_id}/client-booking"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            marked = await client.post(url, json={
                "year": 2025,
                "voucher_keys": [world.key.to_str()],
                "note": "真实 HTTP 客户入账",
            })
            assert marked.status_code == 200, marked.text
            assert marked.json()["client_booking"]["effective"] is True

            revoked = await client.post(f"{url}/revoke", json={
                "year": 2025,
                "reason": "真实 HTTP 撤销客户入账",
            })
            assert revoked.status_code == 200, revoked.text
    finally:
        await route_db.close()

    rows = list((await world.db.execute(sa.select(AdjustmentClientBooking).where(
        AdjustmentClientBooking.entry_group_id == world.group_id,
    ).order_by(AdjustmentClientBooking.sequence))).scalars().all())
    assert [row.action for row in rows] == ["book", "revoke"]


@pytest.mark.asyncio
async def test_pg_dataset_rollback_releases_active_before_promoting_previous(booking_pg_world):
    world = booking_pg_world
    restored = await DatasetService.rollback(
        world.db,
        world.project.id,
        2025,
        performed_by=world.actor.id,
        reason="PG 回滚唯一 active 约束验收",
    )
    assert restored is not None
    assert restored.id == world.old_dataset.id
    assert restored.status.value == "active"
