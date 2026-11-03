"""调整分录 Excel 导入服务（spec adjustment-hall-entry-review-closure 任务 5）。

纯函数部分验分组与行级错误；预检 / 导入用 SQLite 真库 + 真 AdjustmentService，验逐笔保存点：
一笔失败其余照常入库、覆盖模式「删旧建新」失败时旧分录保留。
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

from app.models.audit_platform_models import (
    AccountCategory, AccountChart, AccountDirection, AccountMapping, AccountSource, Adjustment, AdjustmentType,
    MappingType, ReviewStatus,
)
from app.models.audit_platform_schemas import AdjustmentCreate, AdjustmentLineItem, ReviewStatusChange
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.adjustment_import_service import (
    AccountResolver, build_import_groups, group_errors, import_rows, parse_amount, preview_import,
)
from app.services.adjustment_service import AdjustmentService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
YEAR = 2025
USER = SimpleNamespace(id=uuid.uuid4())
RESOLVER = AccountResolver({"1122", "1231", "6702"}, {"应收账款": "1122", "坏账准备": "1231", "信用减值损失": "6702",
                                                     "应收账款-客户A": "112201"}, {"112201": "1122"})


def _row(no="", typ="AJE", desc="补提坏账", name="", code="", debit="", credit=""):
    return {"编号": no, "类型": typ, "摘要": desc, "二级科目名称": name, "二级科目编码": code,
            "借方金额": debit, "贷方金额": credit}


# ── 分组与行级错误（纯函数）──────────────────────────────────────────────────


def test_unnumbered_consecutive_rows_split_by_balance():
    rows = [_row(name="信用减值损失", debit="100"), _row(name="坏账准备", credit="60"), _row(name="坏账准备", credit="40"),
            _row(name="信用减值损失", debit="5", desc="第二笔"), _row(name="坏账准备", credit="5")]
    groups, _ = build_import_groups(rows, RESOLVER)
    assert [[ln.row_idx for ln in g.lines] for g in groups] == [[1, 2, 3], [4, 5]]
    assert [g.description for g in groups] == ["补提坏账", "第二笔"]
    assert all(group_errors(g, RESOLVER) == [] for g in groups)


def test_numbered_rows_merge_even_when_not_adjacent_and_break_running_auto_group():
    rows = [_row(no="AJE-1", name="信用减值损失", debit="10"), _row(name="信用减值损失", debit="7"),
            _row(no="AJE-1", name="坏账准备", credit="10"), _row(name="坏账准备", credit="7")]
    groups, _ = build_import_groups(rows, RESOLVER)
    by_key = {g.key: [ln.row_idx for ln in g.lines] for g in groups}
    # 第 2 行起一个无编号累计组，第 3 行（有编号）打断它 ⇒ 第 4 行另起一组
    assert by_key == {"AJE-1": [1, 3], "__auto_1": [2], "__auto_2": [4]}
    errs = {g.key: group_errors(g, RESOLVER) for g in groups}
    assert errs["AJE-1"] == [] and any("借贷不平衡" in e for e in errs["__auto_1"])


@pytest.mark.parametrize("rows, expected", [
    ([_row(no="A1", typ="XJE", name="信用减值损失", debit="1"), _row(no="A1", typ="XJE", name="坏账准备", credit="1")],
     "类型「XJE」无效"),
    ([_row(no="A1", typ="AJE", name="信用减值损失", debit="1"), _row(no="A1", typ="RJE", name="坏账准备", credit="1")],
     "类型不一致"),
    ([_row(no="A1", typ="", name="信用减值损失", debit="1"), _row(no="A1", typ="", name="坏账准备", credit="1")],
     "未填写类型"),
    ([_row(no="A1", name="信用减值损失", debit="一百"), _row(no="A1", name="坏账准备", credit="100")],
     "借方金额无法识别：一百"),
    ([_row(no="A1", name="信用减值损失", debit="-100"), _row(no="A1", name="坏账准备", credit="-100")],
     "金额不能为负数"),
    ([_row(no="A1", name="信用减值损失", debit="100", credit="100"), _row(no="A1", name="坏账准备", credit="0.01")],
     "借方和贷方不能同时填写"),
    ([_row(no="A1", name="不存在的科目", debit="1"), _row(no="A1", name="坏账准备", credit="1")],
     "在项目科目库中找不到"),
])
def test_group_errors_are_specific(rows, expected):
    groups, _ = build_import_groups(rows, RESOLVER)
    errors = [e for g in groups for e in group_errors(g, RESOLVER)]
    assert any(expected in e for e in errors), errors


def test_blank_type_falls_back_to_sheet_name_and_locations_label_rows():
    rows = [_row(no="A1", typ="", name="信用减值损失", debit="1"), _row(no="A1", typ="", name="坏账准备", credit="1")]
    groups, _ = build_import_groups(rows, RESOLVER, locations=[("RJE模板", 7), ("RJE模板", 8)])
    assert groups[0].adj_type == "RJE" and group_errors(groups[0], RESOLVER) == []
    assert [ln.label for ln in groups[0].lines] == ["RJE模板 第 7 行", "RJE模板 第 8 行"]


def test_zero_lines_with_account_are_ignored_with_warning_and_blank_rows_skipped():
    rows = [_row(typ="", desc=""), _row(no="A1", name="信用减值损失", debit="1"), _row(no="A1", name="应收账款"),
            _row(no="A1", name="坏账准备", credit="1")]
    groups, warnings = build_import_groups(rows, RESOLVER)
    assert [[ln.row_idx for ln in g.lines] for g in groups] == [[2, 4]]
    assert warnings == ["第 3 行借贷金额均为 0，已忽略"]


def test_amount_parsing_and_detail_code():
    assert parse_amount("1,234.565") == Decimal("1234.57") and parse_amount("¥ 10") == Decimal("10.00")
    assert parse_amount(None) == Decimal("0.00") and parse_amount(0.1 + 0.2) == Decimal("0.30")
    assert RESOLVER.resolve("", "应收账款-客户A", "") == ("1122", "112201")
    assert RESOLVER.resolve("1231", "", "") == ("1231", None)


# ── 预检 / 导入（SQLite 真库 + 真 AdjustmentService）────────────────────────


_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session


@pytest_asyncio.fixture
async def pid(db: AsyncSession):
    project = Project(id=uuid.uuid4(), name="导入测试_2025", client_name="导入测试", project_type=ProjectType.annual,
                      status=ProjectStatus.planning, created_by=USER.id)
    db.add(project)
    await db.flush()
    for code, name, source in [("1122", "应收账款", AccountSource.standard), ("1231", "坏账准备", AccountSource.standard),
                               ("6702", "信用减值损失", AccountSource.standard),
                               ("112201", "应收账款-客户A", AccountSource.client)]:
        db.add(AccountChart(project_id=project.id, account_code=code, account_name=name, direction=AccountDirection.debit,
                            level=1, category=AccountCategory.asset, source=source))
    db.add(AccountMapping(project_id=project.id, original_account_code="112201", original_account_name="应收账款-客户A",
                          standard_account_code="1122", mapping_type=MappingType.manual))
    await db.commit()
    return project.id


async def _active(db, pid) -> dict[str, list]:
    rows = (await db.execute(sa.select(Adjustment.adjustment_no, Adjustment.description, Adjustment.review_status).where(
        Adjustment.project_id == pid, Adjustment.is_deleted == sa.false()))).all()
    out: dict[str, list] = {}
    for no, desc, st in rows:
        out.setdefault(no, []).append((desc, st))
    return out


def _pair(no, desc, amount="100", name2="坏账准备"):
    return [_row(no=no, desc=desc, name="信用减值损失", debit=amount), _row(no=no, desc=desc, name=name2, credit=amount)]


@pytest.mark.asyncio
async def test_one_bad_group_does_not_block_others(db, pid):
    rows = _pair("F-1", "好的") + _pair("F-2", "科目找不到", name2="不存在的科目") + _pair("F-3", "也好")
    result = await import_rows(db, pid, YEAR, rows, USER, mode="append")
    await db.commit()
    assert result["imported"] == 2 and result["failed"] == 1
    assert result["failed_rows"][0]["adj_no"] == "F-2" and "在项目科目库中找不到" in result["failed_rows"][0]["error"]
    active = await _active(db, pid)
    assert sorted(d for v in active.values() for d, _ in v) == ["也好", "也好", "好的", "好的"]
    assert len(result["created"]) == 2


@pytest.mark.asyncio
async def test_overwrite_failure_keeps_old_entry(db, pid):
    svc = AdjustmentService(db)
    old = await svc.create_entry(pid, AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=YEAR, description="旧分录", adjustment_no="F-9",
        line_items=[AdjustmentLineItem(standard_account_code="6702", debit_amount=Decimal("5")),
                    AdjustmentLineItem(standard_account_code="1231", credit_amount=Decimal("5"))]), USER.id)
    await db.commit()
    rows = _pair("F-9", "新分录", name2="不存在的科目")  # 新内容科目找不到 ⇒ create_entry 失败
    result = await import_rows(db, pid, YEAR, rows, USER, mode="overwrite")
    await db.commit()
    assert result["failed"] == 1 and result["imported"] == 0
    assert (await _active(db, pid))["F-9"] == [("旧分录", ReviewStatus.draft)] * 2, "删旧建新须原子：失败时旧分录保留"
    # 内容正确时覆盖成功，编号钉为文件编号
    result = await import_rows(db, pid, YEAR, _pair("F-9", "新分录"), USER, mode="overwrite")
    await db.commit()
    assert result["imported"] == 1 and {d for d, _ in (await _active(db, pid))["F-9"]} == {"新分录"}
    assert str(old.entry_group_id) not in {c["entry_group_id"] for c in result["created"]}


@pytest.mark.asyncio
async def test_preview_reports_actions_without_writing(db, pid):
    svc = AdjustmentService(db)
    for no, status in [("P-1", None), ("P-2", ReviewStatus.approved), ("P-3", ReviewStatus.pending_review)]:
        g = await svc.create_entry(pid, AdjustmentCreate(
            adjustment_type=AdjustmentType.aje, year=YEAR, description=no, adjustment_no=no,
            line_items=[AdjustmentLineItem(standard_account_code="6702", debit_amount=Decimal("1")),
                        AdjustmentLineItem(standard_account_code="1231", credit_amount=Decimal("1"))]), USER.id)
        if status:
            await svc.change_review_status(pid, g.entry_group_id, ReviewStatusChange(status=status), USER.id)
    await db.commit()
    before = await _active(db, pid)
    rows = _pair("P-1", "x") + _pair("P-2", "x") + _pair("P-3", "x") + _pair("P-4", "x", amount="-1")
    preview = await preview_import(db, pid, YEAR, rows, mode="overwrite")
    actions = {g["key"]: (g["action"], g["ok"]) for g in preview["groups"]}
    assert actions == {"P-1": ("replace", True), "P-2": ("skip", False), "P-3": ("skip", False), "P-4": ("create", False)}
    skips = {g["key"]: g["skip_reason"] for g in preview["groups"] if g["action"] == "skip"}
    assert "撤回复核" in skips["P-2"] and "撤回提交" in skips["P-3"]
    assert preview["summary"] == {"total": 4, "ok": 1, "error": 1, "skip": 2, "replace": 1}
    assert await _active(db, pid) == before, "预检不写库"
