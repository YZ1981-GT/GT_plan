"""
# Feature: global-refinement-v5-closure, Property 8~9
函证 service 属性测试

Validates: Requirements 10.3, 10.4, 10.5, 11.2, 11.3, 12.1, 12.3
"""
import uuid

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.confirmation_models import ConfirmationType, ConfirmationStatus
from app.services.confirmation_service import (
    create_confirmation,
    list_confirmations,
    get_confirmation,
    update_confirmation,
    delete_confirmation,
    transition_status,
    _ALLOWED_TRANSITIONS,
)

# SQLite compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

# hypothesis max_examples=5（项目铁律）
SETTINGS = settings(max_examples=5, deadline=10000, suppress_health_check=[HealthCheck.too_slow])

# 独立引擎
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_SessionFactory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

PID = uuid.uuid4()

type_st = st.sampled_from([t.value for t in ConfirmationType])
status_st = st.sampled_from([s.value for s in ConfirmationStatus])


async def _fresh_db() -> AsyncSession:
    """每次调用创建全新表 + session"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    return _SessionFactory()


# --------------------------------------------------------------------------
# Property 8: 函证持久化往返
# Feature: global-refinement-v5-closure, Property 8
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(confirm_type=type_st, counterparty=st.text(min_size=1, max_size=50))
async def test_p8_crud_roundtrip(confirm_type: str, counterparty: str):
    """Property 8: 函证 CRUD 持久化往返

    **Validates: Requirements 10.3, 10.4, 10.5, 12.1, 12.3**
    """
    db = await _fresh_db()
    try:
        data = {"confirm_type": confirm_type, "counterparty": counterparty, "book_amount": 1000.0}
        created = await create_confirmation(db, PID, data)
        assert created["confirm_type"] == confirm_type
        assert created["counterparty"] == counterparty

        # 列表能查到
        items = await list_confirmations(db, PID)
        ids = [i["id"] for i in items]
        assert created["id"] in ids

        # 详情一致
        detail = await get_confirmation(db, uuid.UUID(created["id"]))
        assert detail["counterparty"] == counterparty

        # 更新
        updated = await update_confirmation(db, uuid.UUID(created["id"]), {"counterparty": "新对象"})
        assert updated["counterparty"] == "新对象"

        # 删除后不在列表
        await delete_confirmation(db, uuid.UUID(created["id"]))
        items2 = await list_confirmations(db, PID)
        assert created["id"] not in [i["id"] for i in items2]
    finally:
        await db.close()


# --------------------------------------------------------------------------
# Property 9: 函证状态机合法性
# Feature: global-refinement-v5-closure, Property 9
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(current=status_st, target=status_st)
async def test_p9_state_machine_legality(current: str, target: str):
    """Property 9: 仅合法转换成功，非法转换拒绝+状态不变

    **Validates: Requirements 11.2, 11.3**
    """
    db = await _fresh_db()
    try:
        data = {"confirm_type": "receivable", "counterparty": f"test-{uuid.uuid4().hex[:6]}"}
        created = await create_confirmation(db, PID, data)
        cid = uuid.UUID(created["id"])

        # 把状态强制设为 current（跳过状态机直接写）
        from sqlalchemy import update as sa_update
        from app.models.confirmation_models import Confirmation
        stmt = sa_update(Confirmation).where(Confirmation.id == cid).values(status=current)
        await db.execute(stmt)
        await db.flush()

        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if target in allowed:
            result = await transition_status(db, cid, target)
            assert result["status"] == target
        else:
            if current == target:
                return  # 同状态不测（不是合法也不该报错的边界）
            with pytest.raises(ValueError):
                await transition_status(db, cid, target)
            # 状态不变
            detail = await get_confirmation(db, cid)
            assert detail["status"] == current
    finally:
        await db.close()
