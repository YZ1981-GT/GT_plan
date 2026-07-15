"""PBT: Overlay 保存/失效后可恢复 — write→invalidate→read roundtrip [P5]

Property 5 (P5): Overlay 写入 PG → invalidate 清内存 → 再次读取从 PG 恢复。
验证 Req-4.1 (PG 持久化权威) + Req-4.2 (invalidate 不删 PG) + Req-4.4 (缓存失效后重建)。

测试策略:
- Hypothesis 生成随机 project/wp/overlay 数据
- 使用 SQLite in-memory 引擎模拟 PG (StaticPool)
- 同步包装 async 调用 (PBT 与 async fixture 不兼容)
- write_overlay → assert in cache → invalidate → assert NOT in cache → load_from_pg → assert restored

**Validates: Requirements 4.1, 4.2, 4.4**
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ─── Path setup ──────────────────────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

# ─── SQLite compatibility patches ────────────────────────────────────────────
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

# Patch SQLite type compiler for JSONB / UUID (PG-only types)
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

if not hasattr(SQLiteTypeCompiler, "_original_visit_JSONB"):
    SQLiteTypeCompiler._original_visit_JSONB = getattr(
        SQLiteTypeCompiler, "visit_JSONB", None
    )
    SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "TEXT"

if not hasattr(SQLiteTypeCompiler, "_original_visit_UUID"):
    SQLiteTypeCompiler._original_visit_UUID = getattr(
        SQLiteTypeCompiler, "visit_UUID", None
    )
    SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "VARCHAR(36)"


# ─── Imports (after path setup) ──────────────────────────────────────────────
from app.models.base import Base
from app.models.acnr_overlay_model import AcnrProjectOverlay
from app.services.acnr.overlay import (
    OverlayPatch,
    clear_all_overlays,
    clear_project_overlays,
    ensure_cache_loaded,
    get_overlay,
    get_project_overlays,
    is_cache_loaded,
    load_project_overlays_from_pg,
    populate_cache,
    set_overlay_in_cache,
    write_overlay,
)
from app.services.acnr.overlay_repository import (
    create_overlay,
    get_overlays_for_project,
    upsert_overlay,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _run(coro):
    """Run async coroutine synchronously (PBT-compatible)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_engine():
    """Create SQLite in-memory async engine with StaticPool."""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    return engine


async def _setup_tables(engine):
    """Create tables in SQLite engine."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _create_session(engine):
    """Create an AsyncSession from engine."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    return SessionLocal()


# ─── Hypothesis Strategies ────────────────────────────────────────────────────

_wp_code_st = st.from_regex(r"[A-N][1-9][0-9]?", fullmatch=True)
_sheet_code_st = st.from_regex(r"[A-N][1-9][0-9]?-[1-9]", fullmatch=True)
_overlay_type_st = st.sampled_from(["alias", "cust", "binding"])
_payload_st = st.fixed_dictionaries({
    "sheet_name_alias_add": st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=3),
}).filter(lambda d: True)  # always valid


# ═══════════════════════════════════════════════════════════════════════════════
# Property 5: Overlay write → invalidate → read roundtrip
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5OverlayPersistenceRoundtrip:
    """P5: Overlay 保存/失效后可恢复。

    **Validates: Requirements 4.1, 4.2, 4.4**
    """

    @settings(max_examples=5, deadline=None)
    @given(
        parent_wp_code=_wp_code_st,
        sheet_code=_sheet_code_st,
        overlay_type=_overlay_type_st,
        payload=_payload_st,
    )
    def test_write_invalidate_read_roundtrip(
        self,
        parent_wp_code: str,
        sheet_code: str,
        overlay_type: str,
        payload: dict[str, Any],
    ):
        """Write overlay → invalidate cache → read from PG → data restored.

        Req-4.1: PG is authority
        Req-4.2: invalidate clears memory only
        Req-4.4: first read after invalidation rebuilds from PG
        """
        # Fresh state each example
        clear_all_overlays()

        async def _test():
            engine = _make_engine()
            await _setup_tables(engine)
            session = await _create_session(engine)

            project_id = str(uuid.uuid4())
            addr_id = f"{parent_wp_code}/{sheet_code}"

            try:
                # ── Step 1: Write overlay to PG (bypass ownership for unit test) ──
                await upsert_overlay(
                    session,
                    project_id=uuid.UUID(project_id),
                    wp_id=None,
                    parent_wp_code=parent_wp_code,
                    sheet_code=sheet_code,
                    overlay_type=overlay_type,
                    payload=payload,
                )
                await session.commit()

                # Also set in cache to simulate write_overlay behavior
                patch = OverlayPatch(
                    project_id=project_id,
                    addr_id=addr_id,
                    overrides=payload,
                    overlay_type=overlay_type,
                )
                set_overlay_in_cache(patch)

                # Verify cache has the data
                cached = get_overlay(project_id, addr_id)
                assert cached is not None, "cache should have data after write"
                assert cached.overrides == payload

                # ── Step 2: Invalidate (Req-4.2: clears memory, NOT PG) ──
                clear_project_overlays(project_id)

                # Verify cache is cleared
                assert not is_cache_loaded(project_id), "cache should be cleared after invalidate"
                assert get_overlay(project_id, addr_id) is None

                # ── Step 3: Read-through from PG (Req-4.4: rebuild cache) ──
                restored = await load_project_overlays_from_pg(session, project_id)

                # Verify data restored
                assert addr_id in restored, "overlay should be restored from PG"
                restored_patch = restored[addr_id]
                assert restored_patch.project_id == project_id
                assert restored_patch.addr_id == addr_id
                assert restored_patch.overrides == payload
                assert restored_patch.overlay_type == overlay_type

                # Verify cache is populated again
                assert is_cache_loaded(project_id)
                assert get_overlay(project_id, addr_id) is not None

            finally:
                await session.close()
                await engine.dispose()

        _run(_test())

    @settings(max_examples=5, deadline=None)
    @given(
        parent_wp_code=_wp_code_st,
        sheet_code=_sheet_code_st,
        overlay_type=_overlay_type_st,
    )
    def test_invalidate_does_not_delete_pg_data(
        self,
        parent_wp_code: str,
        sheet_code: str,
        overlay_type: str,
    ):
        """Req-4.2: invalidate() clears memory cache but NOT PG data."""
        clear_all_overlays()

        async def _test():
            engine = _make_engine()
            await _setup_tables(engine)
            session = await _create_session(engine)

            project_id = str(uuid.uuid4())
            payload = {"key": "value", "sheet_name_alias_add": ["测试别名"]}

            try:
                # Write to PG
                await upsert_overlay(
                    session,
                    project_id=uuid.UUID(project_id),
                    wp_id=None,
                    parent_wp_code=parent_wp_code,
                    sheet_code=sheet_code,
                    overlay_type=overlay_type,
                    payload=payload,
                )
                await session.commit()

                # Invalidate memory cache
                clear_project_overlays(project_id)

                # PG data still exists
                rows = await get_overlays_for_project(session, uuid.UUID(project_id))
                assert len(rows) == 1, "PG data must survive invalidation"
                assert rows[0].parent_wp_code == parent_wp_code
                assert rows[0].sheet_code == sheet_code
                assert rows[0].overlay_type == overlay_type

            finally:
                await session.close()
                await engine.dispose()

        _run(_test())

    @settings(max_examples=5, deadline=None)
    @given(
        parent_wp_code=_wp_code_st,
        sheet_code=_sheet_code_st,
    )
    def test_upsert_updates_existing(
        self,
        parent_wp_code: str,
        sheet_code: str,
    ):
        """Upsert existing overlay updates payload without duplicating rows."""
        clear_all_overlays()

        async def _test():
            engine = _make_engine()
            await _setup_tables(engine)
            session = await _create_session(engine)

            project_id = uuid.uuid4()
            payload_v1 = {"version": "v1"}
            payload_v2 = {"version": "v2", "extra": "field"}

            try:
                # Write v1
                await upsert_overlay(
                    session,
                    project_id=project_id,
                    wp_id=None,
                    parent_wp_code=parent_wp_code,
                    sheet_code=sheet_code,
                    overlay_type="cust",
                    payload=payload_v1,
                )
                await session.commit()

                # Upsert v2
                await upsert_overlay(
                    session,
                    project_id=project_id,
                    wp_id=None,
                    parent_wp_code=parent_wp_code,
                    sheet_code=sheet_code,
                    overlay_type="cust",
                    payload=payload_v2,
                )
                await session.commit()

                # Should still be 1 row
                rows = await get_overlays_for_project(session, project_id)
                assert len(rows) == 1, "upsert should not duplicate"
                assert rows[0].payload == payload_v2

            finally:
                await session.close()
                await engine.dispose()

        _run(_test())
