"""调整分录列表富化与分页（spec adjustment-hall-entry-review-closure 需求 3.4 / 5.3）。

SQLite 内存库 + 真 AdjustmentService：编制人 / 复核人姓名、已转错报、来源底稿编码与「来源已删除」；
单段查询失败只影响该段（各段独立保存点）；列表端点给出 has_more 供前端逐页取全量。
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.pagination import PaginationParams
from app.models.adjustment_review_models import AdjustmentClientBooking, AdjustmentTreatmentEvent
from app.models.audit_platform_models import (
    AccountCategory, AccountChart, AccountDirection, AccountSource, Adjustment, AdjustmentEntry,
    AdjustmentType, Materiality, MisstatementType,
    ReviewStatus, TrialBalance, UnadjustedMisstatement,
)
from app.models.audit_platform_schemas import AdjustmentCreate, AdjustmentLineItem, ReviewStatusChange
from app.models.base import Base, UserRole
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.models.staff_models import StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services import adjustment_list_enrich as enrich
from app.services.adjustment_service import AdjustmentService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    tables = [
        User.__table__, Project.__table__, StaffMember.__table__, AccountChart.__table__,
        Adjustment.__table__, AdjustmentEntry.__table__, Materiality.__table__,
        TrialBalance.__table__,
        AdjustmentClientBooking.__table__, AdjustmentTreatmentEvent.__table__,
        UnadjustedMisstatement.__table__, WpIndex.__table__, WorkingPaper.__table__,
    ]
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    async with async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await eng.dispose()


@pytest_asyncio.fixture
async def world(db: AsyncSession):
    w = SimpleNamespace()
    project = Project(id=uuid.uuid4(), name="富化测试_2025", client_name="富化测试",
                      project_type=ProjectType.annual, status=ProjectStatus.execution)
    db.add(project)
    for code, name in [("1231", "坏账准备"), ("6702", "信用减值损失")]:
        db.add(AccountChart(project_id=project.id, account_code=code, account_name=name, direction=AccountDirection.debit,
                            level=1, category=AccountCategory.asset, source=AccountSource.standard))
    w.pid = project.id
    w.preparer = User(id=uuid.uuid4(), username="prep", email="prep@t.com", hashed_password="x", role=UserRole.auditor)
    w.reviewer = User(id=uuid.uuid4(), username="rev", email="rev@t.com", hashed_password="x", role=UserRole.manager)
    db.add_all([w.preparer, w.reviewer])
    await db.flush()
    db.add(StaffMember(id=uuid.uuid4(), user_id=w.preparer.id, name="张编制"))  # 复核人只有用户名，没有人员记录
    await db.commit()
    return w


async def _entry(db, w, no: str, amount: str = "10") -> uuid.UUID:
    value = Decimal(amount)
    res = await AdjustmentService(db).create_entry(w.pid, AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=YEAR, description=no, adjustment_no=no,
        line_items=[AdjustmentLineItem(standard_account_code="6702", debit_amount=value),
                    AdjustmentLineItem(standard_account_code="1231", credit_amount=value)]), w.preparer.id)
    return res.entry_group_id


async def _items(db, w) -> dict[str, dict]:
    result = await AdjustmentService(db).list_entries(w.pid, YEAR, page=1, page_size=50)
    items = result["items"]
    await enrich.enrich_adjustment_list(db, w.pid, items)
    return {it["adjustment_no"]: it for it in items}


@pytest.mark.asyncio
async def test_names_converted_misstatement_and_source_workpaper(db, world):
    plain = await _entry(db, world, "A-1")
    rejected = await _entry(db, world, "A-2")
    await AdjustmentService(db).change_review_status(
        world.pid, rejected, ReviewStatusChange(status=ReviewStatus.pending_review), world.preparer.id)
    await AdjustmentService(db).change_review_status(
        world.pid, rejected, ReviewStatusChange(status=ReviewStatus.rejected, reason="比例不对"), world.reviewer.id)
    first_row = (await db.execute(sa.select(Adjustment.id).where(Adjustment.entry_group_id == rejected).limit(1))).scalar_one()
    mis = UnadjustedMisstatement(id=uuid.uuid4(), project_id=world.pid, year=YEAR, source_adjustment_id=first_row,
                                 misstatement_description="转错报", misstatement_amount=Decimal("10"),
                                 misstatement_type=MisstatementType.factual)
    db.add(mis)
    # 一笔来自底稿（底稿存在）、一笔来源底稿已删除
    idx = WpIndex(id=uuid.uuid4(), project_id=world.pid, wp_code="D2", wp_name="应收账款")
    idx_gone = WpIndex(id=uuid.uuid4(), project_id=world.pid, wp_code="D3", wp_name="预付账款")
    db.add_all([idx, idx_gone])
    await db.flush()
    source_type = WorkingPaper.__table__.c["source_type"].type.enum_class("template")
    wp = WorkingPaper(id=uuid.uuid4(), project_id=world.pid, wp_index_id=idx.id, file_path="x.xlsx", source_type=source_type)
    gone = WorkingPaper(id=uuid.uuid4(), project_id=world.pid, wp_index_id=idx_gone.id, file_path="y.xlsx",
                        source_type=source_type, is_deleted=True)
    db.add_all([wp, gone])
    from_wp = await _entry(db, world, "A-3")
    from_gone = await _entry(db, world, "A-4")
    for gid, wid in [(from_wp, wp.id), (from_gone, gone.id)]:
        await db.execute(sa.update(Adjustment).where(Adjustment.entry_group_id == gid)
                         .values(origin="workpaper", source_ref=f"{wid}:D2-4-adj-0"))
    await db.commit()

    items = await _items(db, world)
    assert items["A-1"]["creator_name"] == "张编制" and items["A-1"]["reviewer_name"] is None
    assert items["A-2"]["reviewer_name"] == "rev", "没有人员记录时用用户名"
    assert items["A-2"]["converted_to_misstatement_id"] == str(mis.id)
    assert items["A-1"]["converted_to_misstatement_id"] is None
    assert (items["A-3"]["source_wp_code"], items["A-3"]["source_missing"]) == ("D2", False)
    assert items["A-4"]["source_missing"] is True
    assert "source_wp_code" not in items["A-1"], "手工分录不带来源底稿字段"
    assert str(items["A-1"]["entry_group_id"]) == str(plain)


@pytest.mark.asyncio
async def test_one_failing_section_does_not_wipe_the_others(db, world, monkeypatch):
    await _entry(db, world, "B-1")
    await db.commit()

    async def boom(*_args, **_kwargs):
        await db.execute(sa.text("SELECT * FROM no_such_table"))

    monkeypatch.setattr(enrich, "_converted_misstatements", boom)
    items = await _items(db, world)
    assert items["B-1"]["converted_to_misstatement_id"] is None
    assert items["B-1"]["creator_name"] == "张编制", "已转错报那段失败，姓名照常富化"
    # 保存点回滚后会话仍可用
    assert (await db.execute(sa.select(sa.func.count()).select_from(Adjustment))).scalar() == 2


@pytest.mark.asyncio
async def test_list_endpoint_reports_has_more_before_scope_filter(db, world, monkeypatch):
    from app.routers import adjustments as adj_router

    for i in range(3):
        await _entry(db, world, f"C-{i}")
    await db.commit()

    async def no_scope(*_a, **_k):
        return None

    monkeypatch.setattr(adj_router, "get_user_scope_cycles", no_scope)
    kwargs = dict(
        project_id=world.pid, year=YEAR, adjustment_type=None, review_status=None, origin=None,
        search=None, account_code=None, amount_min=None, amount_max=None,
        created_by=None, reviewer_id=None, audit_phase=None, treatment_status=None,
        focus_entry_group_id=None, created_from=None, created_to=None,
        sort_by="adjustment_no", sort_order="asc", fields=None,
        db=db, current_user=world.preparer,
    )
    first = await adj_router.list_adjustments(pagination=PaginationParams(page=1, page_size=2), **kwargs)
    last = await adj_router.list_adjustments(pagination=PaginationParams(page=2, page_size=2), **kwargs)
    assert (len(first["items"]), first["has_more"]) == (2, True)
    assert (len(last["items"]), last["has_more"]) == (1, False)


@pytest.mark.asyncio
async def test_server_side_search_amount_sort_and_focus_page_are_stable(db, world):
    gids = [
        await _entry(db, world, "P-003", "30"),
        await _entry(db, world, "P-001", "10"),
        await _entry(db, world, "P-002", "20"),
    ]
    await db.commit()
    service = AdjustmentService(db)

    searched = await service.list_entries(world.pid, YEAR, search="P-002", page=1, page_size=50)
    assert searched["total"] == 1
    assert searched["items"][0]["adjustment_no"] == "P-002"

    sorted_page = await service.list_entries(
        world.pid, YEAR, amount_min=Decimal("15"), sort_by="amount", sort_order="desc",
        page=1, page_size=1,
    )
    assert sorted_page["total"] == 2 and sorted_page["has_more"] is True
    assert sorted_page["items"][0]["adjustment_no"] == "P-003"

    located = await service.list_entries(
        world.pid, YEAR, focus_entry_group_id=gids[0],
        sort_by="adjustment_no", sort_order="asc", page=1, page_size=1,
    )
    assert located["page"] == 3
    assert located["items"][0]["entry_group_id"] == gids[0]


@pytest.mark.asyncio
async def test_server_side_scope_filter_applies_before_count_and_pagination(db, world, monkeypatch):
    from app.routers import adjustments as adj_router

    await _entry(db, world, "S-ALLOW")
    await db.commit()

    async def limited_scope(*_args, **_kwargs):
        return ["D"]

    async def allowed_codes(*_args, **_kwargs):
        return {"6702"}

    monkeypatch.setattr(adj_router, "get_user_scope_cycles", limited_scope)
    monkeypatch.setattr(adj_router, "get_codes_by_cycles", allowed_codes)
    result = await adj_router.list_adjustments(
        project_id=world.pid, year=YEAR, adjustment_type=None, review_status=None,
        origin=None, search=None, account_code=None, amount_min=None, amount_max=None,
        created_by=None, reviewer_id=None, audit_phase=None, treatment_status=None,
        focus_entry_group_id=None, created_from=None, created_to=None,
        sort_by="adjustment_no", sort_order="asc", fields=None,
        pagination=PaginationParams(page=1, page_size=1), db=db, current_user=world.preparer,
    )
    assert result["total"] == 1
    assert len(result["items"]) == 1 and result["has_more"] is False
