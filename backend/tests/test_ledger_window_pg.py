"""True PostgreSQL contract tests for bounded Ledger windows.

All rows belong to a random 【测试】 project inside one outer transaction.  No
application router or independent audit connection is used; teardown rolls the
whole world back.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import uuid
from contextlib import contextmanager
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbAuxBalance, TbAuxLedger, TbBalance, TbLedger
from app.models.base import ProjectStatus
from app.models.core import Project
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.schemas.ledger_window import LedgerWindowQuery
from app.services.ledger_window_service import LedgerWindowService
from app.services.ledger_window_export import build_ledger_export
from openpyxl import load_workbook
from tests.authz_world import pg_engine

pytestmark = pytest.mark.pg_only
YEAR = 2025


def _uid(value: int) -> uuid.UUID:
    return uuid.UUID(int=value)


@pytest_asyncio.fixture
async def ledger_world():
    engine = pg_engine()
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            try:
                async with AsyncSession(bind=conn, expire_on_commit=False,
                                        join_transaction_mode="create_savepoint") as db:
                    ids = await _seed(db)
                    yield db, ids, conn.sync_connection
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()


async def _seed(db: AsyncSession) -> dict[str, uuid.UUID]:
    pid = uuid.uuid4()
    db.add(Project(id=pid, name="【测试】Ledger窗口", client_name="【测试】Ledger窗口",
                   status=ProjectStatus.execution, template_type="listed", report_scope="standalone",
                   audit_year=YEAR, scenario="normal"))
    await db.flush()
    active = LedgerDataset(project_id=pid, year=YEAR, status=DatasetStatus.active,
                           activated_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))
    old = LedgerDataset(project_id=pid, year=YEAR, status=DatasetStatus.superseded,
                        activated_at=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc))
    db.add_all([active, old])
    await db.flush()
    db.add_all([
        TbBalance(id=_uid(100), project_id=pid, year=YEAR, company_code="T", account_code="1002",
                  account_name="银行存款", opening_balance=Decimal("100"), opening_direction="debit",
                  sign_convention_version="v2_category_natural_positive", dataset_id=active.id),
        TbBalance(id=_uid(101), project_id=pid, year=YEAR, company_code="T", account_code="2202",
                  account_name="应付账款", opening_balance=Decimal("100"), opening_direction="credit",
                  sign_convention_version="v2_category_natural_positive", dataset_id=active.id),
        TbAuxBalance(id=_uid(200), project_id=pid, year=YEAR, company_code="T", account_code="1002",
                     account_name="银行存款", aux_type="客户", aux_code="C1", aux_name="客户一",
                     opening_balance=Decimal("100"), opening_direction="debit",
                     sign_convention_version="v2_category_natural_positive", dataset_id=active.id),
        TbAuxBalance(id=_uid(201), project_id=pid, year=YEAR, company_code="T", account_code="1002",
                     account_name="银行存款", aux_type="部门", aux_code="D1", aux_name="部门一",
                     opening_balance=Decimal("100"), opening_direction="debit",
                     sign_convention_version="v2_category_natural_positive", dataset_id=active.id),
        TbAuxBalance(id=_uid(202), project_id=pid, year=YEAR, company_code="T", account_code="1002",
                     account_name="银行存款", aux_type="供应商", aux_code="S1", aux_name="供应商一",
                     opening_balance=Decimal("20"), opening_direction="debit",
                     sign_convention_version="v2_category_natural_positive", dataset_id=active.id),
    ])

    movements = [
        (1, dt.date(YEAR, 1, 1), "001", "隐藏一", "10", "0"),
        (2, dt.date(YEAR, 1, 1), "001", "隐藏二", "0", "3"),
        (3, dt.date(YEAR, 1, 15), "002", "可见一", "5", "0"),
        (4, dt.date(YEAR, 2, 1), "001", "隐藏三", "0", "7"),
        (5, dt.date(YEAR, 2, 2), "002", "可见二", "2", "0"),
    ]
    for seq, day, no, summary, debit, credit in movements:
        # JSONB 允许历史异常标量；额外列目录必须安全忽略它，不能让整窗500。
        raw = ["non-object"] if seq == 1 else {"批次": "A", "_system": "hidden"}
        db.add(TbLedger(id=_uid(300 + seq), project_id=pid, year=YEAR, company_code="T",
                        voucher_date=day, voucher_no=no, account_code="1002", account_name="银行存款",
                        summary=summary, debit_amount=Decimal(debit), credit_amount=Decimal(credit),
                        dataset_id=active.id, raw_extra=raw))
        for offset, aux_type, aux_code in ((400, "客户", "C1"), (500, "部门", "D1")):
            db.add(TbAuxLedger(id=_uid(offset + seq), project_id=pid, year=YEAR, company_code="T",
                               voucher_date=day, voucher_no=no, account_code="1002", account_name="银行存款",
                               aux_type=aux_type, aux_code=aux_code, aux_name=aux_code,
                               summary=summary, debit_amount=Decimal(debit), credit_amount=Decimal(credit),
                               dataset_id=active.id, raw_extra=raw))
    db.add_all([
        TbAuxLedger(id=_uid(701), project_id=pid, year=YEAR, company_code="T",
                    voucher_date=None, voucher_no=None, account_code="1002", account_name="银行存款",
                    aux_type="供应商", aux_code="S1", aux_name="供应商一", summary="无日期一",
                    debit_amount=Decimal("1"), credit_amount=Decimal("0"), dataset_id=active.id),
        TbAuxLedger(id=_uid(702), project_id=pid, year=YEAR, company_code="T",
                    voucher_date=None, voucher_no=None, account_code="1002", account_name="银行存款",
                    aux_type="供应商", aux_code="S1", aux_name="供应商一", summary="无日期二",
                    debit_amount=Decimal("2"), credit_amount=Decimal("0"), dataset_id=active.id),
        TbLedger(id=_uid(601), project_id=pid, year=YEAR, company_code="T",
                 voucher_date=dt.date(YEAR, 1, 1), voucher_no="001", account_code="2202",
                 debit_amount=Decimal("0"), credit_amount=Decimal("10"), dataset_id=active.id),
        TbLedger(id=_uid(602), project_id=pid, year=YEAR, company_code="T",
                 voucher_date=dt.date(YEAR, 1, 2), voucher_no="002", account_code="2202",
                 debit_amount=Decimal("3"), credit_amount=Decimal("0"), dataset_id=active.id),
    ])
    await db.flush()
    return {"project": pid, "active": active.id, "old": old.id}


@contextmanager
def _capture_count(sync_conn):
    seen: list[str] = []
    def capture(_conn, _cursor, statement, _params, _context, _many):
        if re.search(r"\bcount\s*\(", statement, re.I):
            seen.append(statement)
    event.listen(sync_conn, "before_cursor_execute", capture)
    try:
        yield seen
    finally:
        event.remove(sync_conn, "before_cursor_execute", capture)


@pytest.mark.asyncio
async def test_filtered_windows_keep_canonical_balance_and_do_not_recount(ledger_world) -> None:
    db, ids, sync_conn = ledger_world
    service = LedgerWindowService(db)
    query = LedgerWindowQuery(year=YEAR, account_code="1002", keyword="可见", limit=1)
    first = await service.fetch("ledger", ids["project"], "user-a", query)
    assert first.summary.total == 2
    assert first.summary.range_opening_signed == "100.00"
    assert first.summary.debit_total == "7.00" and first.summary.credit_total == "0.00"
    assert first.entries[0]["summary"] == "可见一"
    assert first.entries[0]["running_balance_signed"] == "112.00"
    assert first.extra_columns == ["批次"]
    assert first.subtotals[0].month.month == "2025-01"
    assert first.subtotals[0].month.closing_balance_signed == "112.00"

    with _capture_count(sync_conn) as counts:
        second = await service.fetch("ledger", ids["project"], "user-a",
                                     query.model_copy(update={"cursor": first.page.next_cursor}))
    assert counts == [], "后续窗口不得重复 COUNT"
    assert second.entries[0]["summary"] == "可见二"
    assert second.entries[0]["running_balance_signed"] == "107.00", "隐藏的 2 月贷方 7 仍参与余额"
    assert second.page.start == 2 and second.page.end == 2 and not second.page.has_more
    assert second.subtotals[0].month.month == "2025-02"
    assert second.subtotals[0].month.closing_balance_signed == "107.00"
    assert {first.entries[0]["id"], second.entries[0]["id"]} == {str(_uid(303)), str(_uid(305))}


@pytest.mark.asyncio
async def test_date_range_opening_includes_prior_movements(ledger_world) -> None:
    db, ids, _ = ledger_world
    query = LedgerWindowQuery(year=YEAR, account_code="1002", date_from="2025-01-15", limit=10)
    result = await LedgerWindowService(db).fetch("ledger", ids["project"], "user-a", query)
    assert result.summary.total == 3
    assert result.summary.annual_opening_signed == "100.00"
    assert result.summary.range_opening_signed == "107.00"
    assert [row["running_balance_signed"] for row in result.entries] == ["112.00", "105.00", "107.00"]


@pytest.mark.asyncio
async def test_v2_credit_opening_is_converted_to_signed_basis(ledger_world) -> None:
    db, ids, _ = ledger_world
    result = await LedgerWindowService(db).fetch(
        "ledger", ids["project"], "user-a", LedgerWindowQuery(year=YEAR, account_code="2202", limit=10),
    )
    assert result.summary.annual_opening == "100.00"
    assert result.summary.annual_opening_signed == "-100.00"
    assert result.summary.annual_opening_direction == "credit"
    assert [row["running_balance_signed"] for row in result.entries] == ["-110.00", "-107.00"]
    assert [row["running_balance"] for row in result.entries] == ["110.00", "107.00"]


@pytest.mark.asyncio
async def test_auxiliary_window_requires_one_dimension_and_does_not_double_count(ledger_world) -> None:
    db, ids, _ = ledger_world
    service = LedgerWindowService(db)
    with pytest.raises(HTTPException) as exc:
        await service.fetch("aux_ledger", ids["project"], "user-a",
                            LedgerWindowQuery(year=YEAR, account_code="1002", limit=10))
    assert exc.value.detail["error_code"] == "AUX_TYPE_REQUIRED"

    result = await service.fetch(
        "aux_ledger", ids["project"], "user-a",
        LedgerWindowQuery(year=YEAR, account_code="1002", aux_type="客户", limit=10),
    )
    assert result.summary.total == 5
    assert result.summary.debit_total == "17.00" and result.summary.credit_total == "10.00"
    assert result.summary.annual_opening_signed == "100.00"
    assert result.entries[-1]["running_balance_signed"] == "107.00"
    assert all(row["aux_type"] == "客户" for row in result.entries)


@pytest.mark.asyncio
async def test_auxiliary_null_date_and_number_are_stably_pageable(ledger_world) -> None:
    db, ids, _ = ledger_world
    service = LedgerWindowService(db)
    query = LedgerWindowQuery(year=YEAR, account_code="1002", aux_type="供应商", aux_code="S1", limit=1)
    first = await service.fetch("aux_ledger", ids["project"], "user-a", query)
    second = await service.fetch(
        "aux_ledger", ids["project"], "user-a",
        query.model_copy(update={"cursor": first.page.next_cursor}),
    )
    assert first.summary.total == 2 and first.summary.undated_count == 2
    assert first.summary.warnings == ["有 2 条分录没有日期，按规范账序排在最后"]
    assert [first.entries[0]["id"], second.entries[0]["id"]] == [str(_uid(701)), str(_uid(702))]
    assert [first.entries[0]["running_balance_signed"], second.entries[0]["running_balance_signed"]] == ["21.00", "23.00"]
    assert second.subtotals[0].month.label == "未注明日期合计"


@pytest.mark.asyncio
async def test_active_dataset_change_rejects_old_cursor(ledger_world) -> None:
    db, ids, _ = ledger_world
    service = LedgerWindowService(db)
    query = LedgerWindowQuery(year=YEAR, account_code="1002", limit=1)
    first = await service.fetch("ledger", ids["project"], "user-a", query)
    active = await db.get(LedgerDataset, ids["active"])
    old = await db.get(LedgerDataset, ids["old"])
    active.status = DatasetStatus.superseded
    await db.flush()
    old.status = DatasetStatus.active
    old.activated_at = dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc)
    await db.flush()
    with pytest.raises(HTTPException) as exc:
        await service.fetch("ledger", ids["project"], "user-a",
                            query.model_copy(update={"cursor": first.page.next_cursor}))
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "LEDGER_SNAPSHOT_CHANGED"


@pytest.mark.asyncio
async def test_streaming_export_uses_complete_query_not_current_window(ledger_world) -> None:
    db, ids, _ = ledger_world
    query = LedgerWindowQuery(year=YEAR, account_code="1002", keyword="可见", limit=1)
    chunks, filename, exported = await build_ledger_export(db, "ledger", ids["project"], query)
    raw = bytearray()
    async for chunk in chunks:
        raw.extend(chunk)
    assert filename == "序时账_1002_2025.xlsx" and exported == 2
    book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    values = list(book.active.values)
    assert values[0][:7] == ("日期", "凭证号", "摘要", "借方", "贷方", "余额", "余额方向")
    business = [row for row in values if row[2] in ("可见一", "可见二")]
    assert [row[2] for row in business] == ["可见一", "可见二"]
    assert [Decimal(str(row[5])) for row in business] == [Decimal("112"), Decimal("107")]
    assert any(row[2] == "2025-01 本月合计" for row in values)
    assert any(row[2] == "2025-02 本月合计" for row in values)


@pytest.mark.asyncio
async def test_service_binds_cursor_to_user_and_query(ledger_world) -> None:
    db, ids, _ = ledger_world
    service = LedgerWindowService(db)
    query = LedgerWindowQuery(year=YEAR, account_code="1002", limit=1)
    first = await service.fetch("ledger", ids["project"], "user-a", query)
    for user, changed, code in [
        ("user-b", query, "LEDGER_CURSOR_INVALID"),
        ("user-a", query.model_copy(update={"account_code": "2202"}), "LEDGER_CURSOR_QUERY_MISMATCH"),
        ("user-a", query.model_copy(update={"limit": 2}), "LEDGER_CURSOR_QUERY_MISMATCH"),
    ]:
        with pytest.raises(HTTPException) as exc:
            await service.fetch("ledger", ids["project"], user,
                                changed.model_copy(update={"cursor": first.page.next_cursor}))
        assert exc.value.detail["error_code"] == code


@pytest.mark.asyncio
async def test_no_active_dataset_fails_visible_instead_of_reading_all_versions(ledger_world) -> None:
    db, ids, _ = ledger_world
    active = await db.get(LedgerDataset, ids["active"])
    active.status = DatasetStatus.superseded
    await db.flush()
    with pytest.raises(HTTPException) as exc:
        await LedgerWindowService(db).fetch(
            "ledger", ids["project"], "user-a", LedgerWindowQuery(year=YEAR, account_code="1002"),
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "LEDGER_ACTIVE_DATASET_REQUIRED"
