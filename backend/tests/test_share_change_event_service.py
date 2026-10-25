"""Tests for share_change_event_service — 动态股比事件 CRUD + G7 幂等归一。

真 ORM/SQLite 测试，覆盖：
- 创建/列出/排序
- G7 幂等 upsert（创建、更新、重复导入不追加）
- 审批/撤回状态转换
- 删除仅 draft
- 1/2/3/4 事件场景

spec: consol-node-key-isolation-and-shared-context 任务 9.1~9.2、9.6
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401

from app.models.base import Base
from app.services.share_change_event_service import (
    approve_event,
    create_event,
    delete_event,
    list_events,
    revoke_event,
    upsert_from_g7,
)

PROJECT_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
YEAR = 2025

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


class TestCreateAndList:

    @pytest.mark.asyncio
    async def test_create_and_list(self, db):
        e1 = await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="A001",
                                before_ratio=Decimal("80"), after_ratio=Decimal("90"))
        e2 = await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="A001",
                                before_ratio=Decimal("90"), after_ratio=Decimal("70"))
        await db.flush()

        events = await list_events(db, PROJECT_ID, YEAR, company_code="A001")
        assert len(events) == 2
        # ratio_delta 自动计算（两事件无日期，UUID 排序不确定，用集合比较）
        deltas = {e.ratio_delta for e in events}
        assert deltas == {Decimal("10"), Decimal("-20")}

    @pytest.mark.asyncio
    async def test_list_sorted_by_date_sequence_id(self, db):
        from datetime import date
        # 第三个事件日期最早，应排在第一
        await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="B001",
                           effective_date=date(2025, 6, 1), sequence=0)
        await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="B001",
                           effective_date=date(2025, 3, 1), sequence=0)
        await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="B001",
                           effective_date=date(2025, 6, 1), sequence=1)
        await db.flush()

        events = await list_events(db, PROJECT_ID, YEAR, company_code="B001")
        dates = [(e.effective_date, e.sequence) for e in events]
        assert dates == [
            (date(2025, 3, 1), 0),
            (date(2025, 6, 1), 0),
            (date(2025, 6, 1), 1),
        ]

    @pytest.mark.asyncio
    async def test_filter_by_company(self, db):
        await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="A001")
        await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="B001")
        await db.flush()

        a_events = await list_events(db, PROJECT_ID, YEAR, company_code="A001")
        assert len(a_events) == 1
        all_events = await list_events(db, PROJECT_ID, YEAR)
        assert len(all_events) == 2


class TestG7UpsertIdempotent:

    @pytest.mark.asyncio
    async def test_first_import_creates(self, db):
        suggestions = [
            {"company_code": "A001", "type": "share_change_capital", "id": "g7-10-A001-nci",
             "before_ratio": 80, "after_ratio": 90, "change_type": "购买少数股权",
             "source_sheet": "G7-10"},
        ]
        result = await upsert_from_g7(db, project_id=PROJECT_ID, year=YEAR, suggestions=suggestions)
        assert result == {"created": 1, "updated": 0, "skipped": 0}

        events = await list_events(db, PROJECT_ID, YEAR)
        assert len(events) == 1
        assert events[0].source_row_id == "g7-10-A001-nci"
        assert events[0].before_ratio == Decimal("80")

    @pytest.mark.asyncio
    async def test_duplicate_import_updates_not_appends(self, db):
        suggestions = [
            {"company_code": "A001", "type": "share_change_capital", "id": "g7-10-A001-nci",
             "before_ratio": 80, "after_ratio": 90},
        ]
        await upsert_from_g7(db, project_id=PROJECT_ID, year=YEAR, suggestions=suggestions)

        # 第二次导入修改了 after_ratio
        suggestions[0]["after_ratio"] = 95
        result = await upsert_from_g7(db, project_id=PROJECT_ID, year=YEAR, suggestions=suggestions)
        assert result == {"created": 0, "updated": 1, "skipped": 0}

        events = await list_events(db, PROJECT_ID, YEAR)
        assert len(events) == 1  # 没有追加
        assert events[0].after_ratio == Decimal("95")

    @pytest.mark.asyncio
    async def test_skip_missing_identity(self, db):
        suggestions = [
            {"company_code": "", "type": "g7", "id": ""},  # 空 company_code
            {"company_code": "A001"},  # 无 id
        ]
        result = await upsert_from_g7(db, project_id=PROJECT_ID, year=YEAR, suggestions=suggestions)
        assert result["skipped"] == 2
        assert result["created"] == 0

    @pytest.mark.asyncio
    async def test_four_events_from_g7(self, db):
        """设计 §十三.2：4 次事件不被固定三列截断。"""
        suggestions = [
            {"company_code": "C001", "type": "g7-10", "id": f"g7-10-C001-{i}",
             "before_ratio": 80 + i * 5, "after_ratio": 80 + (i + 1) * 5}
            for i in range(4)
        ]
        result = await upsert_from_g7(db, project_id=PROJECT_ID, year=YEAR, suggestions=suggestions)
        assert result["created"] == 4

        events = await list_events(db, PROJECT_ID, YEAR, company_code="C001")
        assert len(events) == 4
        # 验证每个事件有独立的稳定 ID
        ids = [e.id for e in events]
        assert len(set(ids)) == 4


class TestStatusTransitions:

    @pytest.mark.asyncio
    async def test_approve_and_revoke(self, db):
        event = await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="A001")
        await db.flush()

        assert event.review_status == "draft"

        approved = await approve_event(db, event.id)
        assert approved.review_status == "approved"

        revoked = await revoke_event(db, event.id)
        assert revoked.review_status == "revoked"

    @pytest.mark.asyncio
    async def test_cannot_approve_non_draft(self, db):
        event = await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="A001")
        await approve_event(db, event.id)

        with pytest.raises(ValueError, match="只能审批 draft"):
            await approve_event(db, event.id)

    @pytest.mark.asyncio
    async def test_cannot_revoke_non_approved(self, db):
        event = await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="A001")
        await db.flush()

        with pytest.raises(ValueError, match="只能撤回 approved"):
            await revoke_event(db, event.id)


class TestDeleteEvent:

    @pytest.mark.asyncio
    async def test_delete_draft(self, db):
        event = await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="A001")
        await db.flush()

        assert await delete_event(db, event.id) is True
        events = await list_events(db, PROJECT_ID, YEAR)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_cannot_delete_approved(self, db):
        event = await create_event(db, project_id=PROJECT_ID, year=YEAR, company_code="A001")
        await approve_event(db, event.id)

        with pytest.raises(ValueError, match="只能删除 draft"):
            await delete_event(db, event.id)

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, db):
        assert await delete_event(db, uuid.uuid4()) is False
