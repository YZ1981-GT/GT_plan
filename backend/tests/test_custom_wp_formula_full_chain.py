# Feature: custom-workpaper-formula-binding — 组⑧任务 12.2
"""全链路 in-process ASGI：parsed_data → 注册表 → wp_formula → WP() → preparation-info。"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm.attributes import flag_modified

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpSourceType,
)
from app.services.address_registry import address_registry
from app.services.formula_engine import WPExecutor
from app.services.workpaper_generation_service import workpaper_generation_service

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

import app.models.core  # noqa: F401 — User, Project
import app.models.workpaper_models  # noqa: F401 — WpIndex, WorkingPaper, WpFormula
from app.models.workpaper_models import WpFormula

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
FAKE_WP_INDEX_ID = uuid.uuid4()
FAKE_WP_ID = uuid.uuid4()
WP_CODE = "CUST-01"
YEAR = 2025


def _unwrap(resp_json: dict) -> dict:
    if isinstance(resp_json, dict) and "code" in resp_json and "data" in resp_json:
        return resp_json["data"]
    return resp_json


_CHAIN_TABLES = [
    User.__table__,
    Project.__table__,
    WpIndex.__table__,
    WorkingPaper.__table__,
    WpFormula.__table__,
]


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.drop_all(
                sync_conn, tables=_CHAIN_TABLES
            )
        )
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=_CHAIN_TABLES
            )
        )
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_chain(db_session: AsyncSession):
    user = User(
        id=FAKE_USER_ID,
        username="chain_user",
        email="chain@test.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.flush()

    project = Project(
        id=FAKE_PROJECT_ID,
        name="全链路测试公司",
        client_name="客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
        audit_period_end=date(2025, 12, 31),
        template_type="soe",
    )
    db_session.add(project)
    await db_session.flush()

    wp_index = WpIndex(
        id=FAKE_WP_INDEX_ID,
        project_id=FAKE_PROJECT_ID,
        wp_code=WP_CODE,
        wp_name="自定义测试底稿",
        audit_cycle="A",
    )
    db_session.add(wp_index)
    await db_session.flush()

    parsed = {
        "html_data": {
            "审定表": {
                "cells": {
                    "A5": "货币资金",
                    "B5": 8888,
                }
            }
        }
    }
    wp = WorkingPaper(
        id=FAKE_WP_ID,
        project_id=FAKE_PROJECT_ID,
        wp_index_id=FAKE_WP_INDEX_ID,
        file_path="storage/projects/test/workpapers/A/CUST-01.xlsx",
        source_type=WpSourceType.manual,
        status=WpFileStatus.draft,
        parsed_data=parsed,
        created_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )
    db_session.add(wp)
    await db_session.commit()
    return {
        "project_id": FAKE_PROJECT_ID,
        "wp_id": FAKE_WP_ID,
        "wp_index_id": FAKE_WP_INDEX_ID,
    }


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_chain):
    from app.main import app
    from tests._test_auth_helper import override_auth

    async with override_auth(app, db_session=db_session) as c:
        yield c


@pytest.mark.asyncio
async def test_custom_wp_formula_full_chain(client, db_session, seeded_chain):
    """端到端：注册表含自定义单元格 → 保存公式 → WP() 取值 → 编制信息 7 字段。"""
    project_id = seeded_chain["project_id"]
    wp_id = seeded_chain["wp_id"]
    wp_index_id = seeded_chain["wp_index_id"]

    # ① 模拟解析入库后失效缓存
    wp = await db_session.get(WorkingPaper, wp_id)
    assert wp is not None
    wp.parsed_data = {
        **(wp.parsed_data or {}),
        "html_data": {
            "审定表": {"cells": {"A5": "货币资金", "B5": 8888}},
        },
    }
    flag_modified(wp, "parsed_data")
    await db_session.commit()
    from app.services.wp_parsed_data_service import touch_wp_registry

    await touch_wp_registry(project_id)

    # ② 幂等生成 working_paper（已存在应返回同一记录）
    wp_again = await workpaper_generation_service.ensure_working_paper(
        db_session, project_id, wp_index_id
    )
    assert wp_again.id == wp_id

    # ③ 地址注册表 WP 域含自定义单元格（直接调 service，避免全量 build 过慢）
    await address_registry.invalidate_async(str(project_id), domain="wp", year=YEAR)
    from app.services.address_registry import _build_custom_wp_cell_entries

    custom_entries = await _build_custom_wp_cell_entries(
        db_session, str(project_id), YEAR
    )
    custom_hits = [
        e
        for e in custom_entries
        if e.wp_code == WP_CODE
        and e.cell == "B5"
        and e.formula_ref == "WP('CUST-01','B5')"
    ]
    assert custom_hits, "注册表应包含自定义底稿 B5 单元格条目"

    # ④ 保存 wp_formula
    with patch(
        "app.services.address_registry.AddressRegistryService.validate_formula_refs",
        new_callable=AsyncMock,
        return_value=[],
    ):
        save_resp = await client.put(
            f"/api/workpapers/{wp_id}/formulas",
            json={
                "sheet_name": "审定表",
                "target_cell": "B5",
                "expression": "8888",
                "year": YEAR,
                "template_type": "soe",
                "category": "auto_calc",
                "description": "全链路测试",
            },
        )
    assert save_resp.status_code == 200
    saved = _unwrap(save_resp.json()).get("saved", {})
    assert saved.get("target_cell") == "B5"

    list_resp = await client.get(f"/api/workpapers/{wp_id}/formulas")
    assert list_resp.status_code == 200
    list_body = _unwrap(list_resp.json())
    assert list_body.get("count", 0) >= 1

    # ⑤ WP() 单元格地址求值
    val = await WPExecutor.execute(db_session, project_id, WP_CODE, "B5")
    assert val == Decimal("8888")

    # ⑥ 编制信息 7 字段、无 accounting_period
    prep_resp = await client.get(f"/api/workpapers/{wp_id}/preparation-info")
    assert prep_resp.status_code == 200
    prep = _unwrap(prep_resp.json())
    assert "accounting_period" not in prep
    assert set(prep.keys()) == {
        "entity_name",
        "period_end",
        "preparer",
        "prep_date",
        "reviewer",
        "review_date",
        "index_no",
    }
    assert prep["entity_name"] == "全链路测试公司"
    assert prep["index_no"] == WP_CODE
    assert prep["period_end"] == "2025-12-31"
