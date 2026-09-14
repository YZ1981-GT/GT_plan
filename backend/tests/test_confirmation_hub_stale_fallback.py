"""
test_confirmation_hub_stale_fallback.py — G1 函证中心手动回函 stale 兜底

背景（2026-07-17 函证第二轮复盘 G1）：ConfirmationHub 手动 transition 通常不带
wp_code → 后端此前不发 CONFIRMATION_RECEIVED → 下游 D2/F2/G7 stale 只在
syncHubFromSummary 路径通。本兜底：transition 端点缺 wp_code 时从记录 wp_id
反查 wp_code（wp_index）+ year（projects.audit_year），使手动回函也能传播 stale。

验证：
1. _normalize_source_wp_code 归一（D0-1→D0，剥离 sheet 后缀，与前端口径一致）
2. derive_source_wp_code_and_year 无 wp_id → (None, None)（不臆测源底稿）
3. 记录不存在 → (None, None)
4. transition 端点源码已接兜底反查
"""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.confirmation_models import Confirmation
from app.services.confirmation_service import (
    create_confirmation,
    derive_source_wp_code_and_year,
    _normalize_source_wp_code,
)

# SQLite compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_SessionFactory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

PID = uuid.uuid4()


async def _fresh_db() -> AsyncSession:
    """只建 confirmations 单表（避免 Base.metadata 全量 create_all 的无关 FK 污染）。"""
    tbl = Confirmation.__table__

    def _recreate(sync_conn):
        tbl.drop(sync_conn, checkfirst=True)
        tbl.create(sync_conn, checkfirst=True)

    async with _engine.begin() as conn:
        await conn.run_sync(_recreate)
    return _SessionFactory()


# ─── Test 1: 归一化纯函数 ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("D0-1", "D0"),
        ("D0", "D0"),
        ("F0-1", "F0"),
        ("G0-2", "G0"),
        ("K0-7", "K0"),
        ("L0", "L0"),
        ("  D0-1  ", "D0"),
        (None, None),
        ("", None),
    ],
)
def test_normalize_source_wp_code(raw, expected):
    """剥离 sheet 级 -N 后缀得循环级源码；与前端 wpCode.split('-')[0] 口径一致。"""
    assert _normalize_source_wp_code(raw) == expected


# ─── Test 2/3: 反查兜底（无 wp_id / 记录不存在 → 不臆测）────────────────────


@pytest.mark.asyncio
async def test_derive_returns_none_without_wp_id():
    """函证记录无关联 wp_id → (None, None)，调用方据此不触发 stale。"""
    db = await _fresh_db()
    try:
        created = await create_confirmation(
            db, PID, {"confirm_type": "receivable", "counterparty": "手动台账对象"}
        )
        wp_code, year = await derive_source_wp_code_and_year(db, uuid.UUID(created["id"]))
        assert wp_code is None
        assert year is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_derive_returns_none_for_missing_record():
    """记录不存在 → (None, None)，不抛异常。"""
    db = await _fresh_db()
    try:
        wp_code, year = await derive_source_wp_code_and_year(db, uuid.uuid4())
        assert wp_code is None
        assert year is None
    finally:
        await db.close()


# ─── Test 4: 端点已接兜底反查 ────────────────────────────────────────────────


def test_transition_endpoint_wires_fallback():
    """transition 端点源码在缺 wp_code 时调用 derive_source_wp_code_and_year。"""
    import inspect
    from app.routers.confirmations import transition_confirmation

    source = inspect.getsource(transition_confirmation)
    assert "derive_source_wp_code_and_year" in source
    assert "apply_confirmation_result" in source
    # 三个终态都应触发反查/传播
    assert "returned" in source and "matched" in source and "discrepancy" in source
