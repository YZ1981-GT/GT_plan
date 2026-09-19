"""Property 14: V074 DDL 幂等 — note-guidance-text-separation Task 1.5."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from tests.services.conftest import _pg_url

pytestmark = pytest.mark.pg_only


@pytest.mark.asyncio
async def test_v074_guidance_text_column_idempotent():
    """Feature: note-guidance-text-separation, Property 14: 迁移幂等（DDL）"""
    from sqlalchemy.ext.asyncio import create_async_engine

    root = Path(__file__).resolve().parents[2]
    ddl = (root / "migrations" / "V074__disclosure_notes_guidance_text.sql").read_text(encoding="utf-8")

    engine = create_async_engine(_pg_url(), echo=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(ddl))
            await conn.execute(text(ddl))
            row = await conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name='disclosure_notes' AND column_name='guidance_text'"
                )
            )
            assert row.scalar_one() == "text"
    finally:
        await engine.dispose()
