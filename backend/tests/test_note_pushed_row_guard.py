"""子企业附注保存时保护集团下推的固定行（spec note-pull-followup-closure R13）。"""
from __future__ import annotations

import copy
import uuid
from datetime import date

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.core import Project, User
from app.models.report_models import DisclosureNote
from app.services.disclosure_engine import DisclosureEngine
from app.services.note_pushed_row_guard import pushed_row_violations

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]


def _td() -> dict:
    return {"_tables": [{"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"], "rows": [
        {"label": "库存现金", "values": [1, 2], "_pushed_row_id": "r-cash", "_pushed_category": "required"},
        {"label": "数字货币", "values": [None, None], "_pushed_row_id": "r-digital", "_pushed_category": "optional",
         "_pushed_optional_active": True},
        {"label": "自加行", "values": [3, 4]},
        {"label": "合计", "values": [4, 6], "is_total": True},
    ]}]}


def _rows(td: dict) -> list[dict]:
    return td["_tables"][0]["rows"]


def test_allowed_edits_pass():
    new = _td()
    _rows(new)[0]["values"] = [100, 200]                      # 改数
    _rows(new).insert(2, {"label": "新加行", "values": [5, 5]})  # 加行
    _rows(new)[1]["_pushed_optional_active"] = False           # 可选行标「本企业不适用」
    del _rows(new)[3]                                          # 删子企业自己加的行
    _rows(new)[0]["label"] = "库 存现金"                        # 只差空白
    assert pushed_row_violations(_td(), new) == []
    no_optional = _td()
    del _rows(no_optional)[1]
    assert pushed_row_violations(_td(), no_optional) == [], "可选行可以删"
    assert pushed_row_violations({"_tables": [{"rows": [{"label": "甲"}]}]}, {}) == [], "旧数据没有固定下推行不检查"


@pytest.mark.parametrize("edit, problem", [
    (lambda rows: rows.pop(0), "删除"),
    (lambda rows: rows[0].update(label="现金"), "行名被改成「现金」"),
    (lambda rows: rows[0].pop("_pushed_row_id"), "去掉了集团下推标记"),
    (lambda rows: rows[0].update(_pushed_category="optional"), "可选行"),
])
def test_fixed_row_violations(edit, problem):
    new = copy.deepcopy(_td())
    edit(_rows(new))
    [v] = pushed_row_violations(_td(), new)
    assert v["table"] == "货币资金" and v["row"] == "库存现金" and problem in v["problem"], v


def test_missing_category_counts_as_fixed():
    """下推标记缺类别按固定行算（与编辑器 isPushedFixedRow 同口径）：删掉照样拒绝。"""
    old = _td()
    del _rows(old)[0]["_pushed_category"]
    new = copy.deepcopy(old)
    del _rows(new)[0]
    [v] = pushed_row_violations(old, new)
    assert v["row"] == "库存现金" and "删除" in v["problem"]


def test_legacy_single_table_layout_is_checked_too():
    old = {"headers": ["项目", "期末余额"], "rows": [
        {"label": "库存现金", "values": [1], "_pushed_row_id": "r1", "_pushed_category": "required"}]}
    assert pushed_row_violations(old, {"headers": ["项目", "期末余额"], "rows": []})


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    tables = [User.__table__, Project.__table__, DisclosureNote.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_note_rejects_with_409_and_keeps_data(db):
    project = Project(id=uuid.uuid4(), name="甲_2025", client_name="甲", audit_year=2025,
                      audit_period_end=date(2025, 12, 31))
    db.add(project)
    note = DisclosureNote(project_id=project.id, year=2025, note_section="八、1", section_title="货币资金",
                          table_data=_td(), status="draft")
    db.add(note)
    await db.flush()
    bad = copy.deepcopy(_td())
    _rows(bad)[0]["label"] = "现金"
    with pytest.raises(HTTPException) as exc:
        await DisclosureEngine(db).update_note(note.id, table_data=bad)
    assert exc.value.status_code == 409 and exc.value.detail["error_code"] == "PUSHED_ROW_PROTECTED"
    assert "库存现金" in exc.value.detail["message"] and exc.value.detail["rows"][0]["row"] == "库存现金"
    assert _rows(note.table_data)[0]["label"] == "库存现金", "拒绝时不改数据"
    good = copy.deepcopy(_td())
    _rows(good)[0]["values"] = [9, 9]
    saved = await DisclosureEngine(db).update_note(note.id, table_data=good)
    assert _rows(saved.table_data)[0]["values"] == [9, 9]
