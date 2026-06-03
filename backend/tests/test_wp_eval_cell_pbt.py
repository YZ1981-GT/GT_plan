# Feature: custom-workpaper-formula-binding, Property 11: WP() 单元格地址求值正确
"""WPExecutor 对单元格地址第二参从 parsed_data 取值；缺失单元格返回 0。"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from hypothesis import given, settings, strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpSourceType,
)
from app.services.formula_engine import WPExecutor

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

import app.models.core  # noqa: F401
import app.models.workpaper_models  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
_tables_ready = False

_cell_st = st.sampled_from(["B5", "C12", "D10"])
_value_st = st.integers(min_value=1, max_value=999_999)
_label_st = st.sampled_from(["货币资金", "应收账款", "固定资产"])


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _ensure_tables():
    global _tables_ready
    if not _tables_ready:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _tables_ready = True


async def _seed_wp(session: AsyncSession, wp_code: str, parsed_data: dict) -> uuid.UUID:
    project_id = uuid.uuid4()
    idx_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    user = User(
        id=uuid.uuid4(),
        username="p11_user",
        email="p11@t.com",
        hashed_password="x",
        role=UserRole.admin,
        is_active=True,
    )
    project = Project(
        id=project_id,
        name="P11测试",
        client_name="客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=user.id,
        template_type="soe",
    )
    session.add_all([user, project])
    await session.flush()
    session.add(
        WpIndex(
            id=idx_id,
            project_id=project_id,
            wp_code=wp_code,
            wp_name=wp_code,
            audit_cycle="A",
        )
    )
    session.add(
        WorkingPaper(
            id=wp_id,
            project_id=project_id,
            wp_index_id=idx_id,
            file_path=f"/tmp/{wp_code}.xlsx",
            source_type=WpSourceType.manual,
            status=WpFileStatus.draft,
            parsed_data=parsed_data,
        )
    )
    await session.flush()
    return project_id


@settings(max_examples=5, deadline=None)
@given(cell=_cell_st, value=_value_st, label=_label_st)
def test_wp_cell_address_eval_matches_extracted_value(cell: str, value: int, label: str):
    cell_up = cell.upper()
    wp_code = f"CUST-P11-{cell_up}"
    parsed = {
        "html_data": {
            "审定表": {
                "cells": {
                    "A5": label,
                    cell_up: value,
                }
            }
        }
    }

    async def _inner():
        await _ensure_tables()
        factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            project_id = await _seed_wp(session, wp_code, parsed)
            return await WPExecutor.execute(session, project_id, wp_code, cell_up)

    assert _run(_inner()) == Decimal(str(value))


@settings(max_examples=5, deadline=None)
@given(cell=_cell_st)
def test_wp_missing_cell_returns_zero(cell: str):
    wp_code = "CUST-MISS"
    parsed = {"html_data": {"审定表": {"cells": {"A1": "仅标题"}}}}

    async def _inner():
        await _ensure_tables()
        factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            project_id = await _seed_wp(session, wp_code, parsed)
            return await WPExecutor.execute(session, project_id, wp_code, cell.upper())

    assert _run(_inner()) == Decimal("0")
