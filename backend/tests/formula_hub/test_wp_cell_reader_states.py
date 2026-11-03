"""``wp_cell_reader.resolve_wp_cell`` 状态机 / 年度闸门单元测试（formula-hub 任务 23-1）。

🔴 2026-10-29 整合说明：本文件原在 `backend/tests/test_wp_cell_reader.py`，与
`acnr-foundation-defect-closure` T11 的同名文件冲突（两边是互补的两套用例）。按 design §8.2
「后落地方只接线、不改先落地方的契约测试」，ACNR 的 7 条 `reason_code` / `raw` 用例保留在原路径，
formula-hub 的这 18 条迁到本 spec 自己的测试目录。被测模块、断言与原文逐条不变。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType  # noqa: E402
from app.services import wp_cell_reader  # noqa: E402
from app.services.wp_cell_reader import WpCellRead, resolve_wp_cell  # noqa: E402

_TABLES = [User.__table__, Project.__table__, WpIndex.__table__, WorkingPaper.__table__]

# ── 两张表、同 A1 不同值 ────────────────────────────────────────────────────
_PARSED_TWO_SHEETS = {
    "html_data": {
        "资产负债表E1-1": {"cells": {"A1": {"v": "500.25"}, "B2": 100}},
        "利润表E1-2": {"cells": {"A1": "300.75", "C3": "非数值文本"}},
    },
}

_PARSED_SINGLE = {
    "html_data": {
        "明细表D1-1": {"cells": {"D4": 42, "E5": "", "F6": None}},
    },
}


@pytest.fixture
async def db_world():
    """SQLite 内存库 + 项目 + 多种底稿场景。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
        # 去掉唯一索引以便测试多份底稿场景
        await conn.execute(text("DROP INDEX uq_working_paper_project_index"))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        pid = uuid.uuid4()
        db.add(Project(
            id=pid, name="【测试】wp_cell_reader 单元", client_name="测试",
            status=ProjectStatus.execution, template_type="listed",
            report_scope="standalone", audit_year=2025, scenario="normal",
        ))
        await db.flush()

        papers: dict[str, uuid.UUID] = {}

        # E1: 两张表，同 A1 不同值
        idx_e1 = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code="E1", wp_name="E1")
        db.add(idx_e1)
        await db.flush()
        wp_e1 = WorkingPaper(
            id=uuid.uuid4(), project_id=pid, wp_index_id=idx_e1.id,
            file_path="E1.xlsx", source_type=WpSourceType.template,
            parsed_data=_PARSED_TWO_SHEETS,
        )
        db.add(wp_e1)
        papers["E1"] = wp_e1.id

        # D1: 单张表
        idx_d1 = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code="D1", wp_name="D1")
        db.add(idx_d1)
        await db.flush()
        wp_d1 = WorkingPaper(
            id=uuid.uuid4(), project_id=pid, wp_index_id=idx_d1.id,
            file_path="D1.xlsx", source_type=WpSourceType.template,
            parsed_data=_PARSED_SINGLE,
        )
        db.add(wp_d1)
        papers["D1"] = wp_d1.id

        # G1: 两条未删 working_paper（歧义）
        idx_g1 = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code="G1", wp_name="G1")
        db.add(idx_g1)
        await db.flush()
        for i in range(2):
            db.add(WorkingPaper(
                id=uuid.uuid4(), project_id=pid, wp_index_id=idx_g1.id,
                file_path=f"G1_{i}.xlsx", source_type=WpSourceType.template,
                parsed_data=_PARSED_SINGLE,
            ))

        # H1: 已删除 + 在用
        idx_h1 = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code="H1", wp_name="H1")
        db.add(idx_h1)
        await db.flush()
        db.add(WorkingPaper(
            id=uuid.uuid4(), project_id=pid, wp_index_id=idx_h1.id,
            file_path="H1_del.xlsx", source_type=WpSourceType.template,
            parsed_data=_PARSED_SINGLE, is_deleted=True,
        ))
        wp_h1 = WorkingPaper(
            id=uuid.uuid4(), project_id=pid, wp_index_id=idx_h1.id,
            file_path="H1_live.xlsx", source_type=WpSourceType.template,
            parsed_data=_PARSED_SINGLE,
        )
        db.add(wp_h1)
        papers["H1"] = wp_h1.id

        await db.commit()
        yield {"db": db, "pid": pid, "papers": papers}
    await engine.dispose()


@pytest.fixture(autouse=True)
def _bypass_year_gate(monkeypatch):
    """默认 year=None 不查年度；需要测年度闸门的用例自行覆盖。"""
    async def _always_2025(db, project_id):
        return 2025
    monkeypatch.setattr(wp_cell_reader, "fetch_project_audit_year", _always_2025)


# ── 同一底稿两表同 A1 不同值、指定 sheet_key 各取各的 ────────────────────────
class TestSameA1DifferentSheets:
    async def test_sheet1_gets_its_value(self, db_world):
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "E1", "资产负债表E1-1", "A1")
        assert r.state == "ok"
        assert r.value == Decimal("500.25")
        assert r.sheet_key == "资产负债表E1-1"

    async def test_sheet2_gets_its_value(self, db_world):
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "E1", "利润表E1-2", "A1")
        assert r.state == "ok"
        assert r.value == Decimal("300.75")
        assert r.sheet_key == "利润表E1-2"

    async def test_two_arg_takes_first_ordered_hit(self, db_world):
        """sheet_key=None 时 matches=2，值取 extract_custom_cells 顺序第一个。"""
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "E1", None, "A1")
        assert r.state == "ok"
        assert r.matches == 2
        # 值取决于 extract_custom_cells 顺序，这里只验证取到了某个值
        assert r.value in (Decimal("500.25"), Decimal("300.75"))


# ── 各状态 ──────────────────────────────────────────────────────────────────
class TestStates:
    async def test_ok_integer(self, db_world):
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "D1", "明细表D1-1", "D4")
        # raw = 找到单元格时的原文：ACNR 先落地的契约字段（design §8.2「后落地方不改先落地方契约」），这里按它断言
        assert r == WpCellRead("ok", Decimal("42"), None, db_world["papers"]["D1"], "明细表D1-1", matches=1, raw="42")

    async def test_missing_no_paper(self, db_world):
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "Z9", None, "A1")
        assert r.state == "missing"
        assert r.value is None
        assert "底稿 Z9" in r.reason

    async def test_missing_no_sheet(self, db_world):
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "D1", "不存在的表", "D4")
        assert r.state == "missing"
        assert "没有该工作表的数据" in r.reason

    async def test_missing_no_cell(self, db_world):
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "D1", "明细表D1-1", "Z99")
        assert r.state == "missing"
        assert "单元格未录入" in r.reason

    async def test_missing_empty_cell(self, db_world):
        """空字符串视为未录入。"""
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "D1", "明细表D1-1", "E5")
        assert r.state == "missing"
        assert "单元格未录入" in r.reason

    async def test_missing_none_cell(self, db_world):
        """None 视为未录入。"""
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "D1", "明细表D1-1", "F6")
        assert r.state == "missing"
        assert "单元格未录入" in r.reason

    async def test_blocked_ambiguous_papers(self, db_world):
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "G1", None, "A1")
        assert r.state == "blocked"
        assert "歧义" in r.reason
        assert len(r.candidates) == 2

    async def test_blocked_non_numeric(self, db_world):
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "E1", "利润表E1-2", "C3")
        assert r.state == "blocked"
        assert "不是数值" in r.reason

    async def test_deleted_paper_not_counted(self, db_world):
        """已删除的底稿不参与绑定，在用的那份正常返回。"""
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "H1", "明细表D1-1", "D4")
        assert r.state == "ok"
        assert r.value == Decimal("42")
        assert r.wp_id == db_world["papers"]["H1"]


# ── 年度闸门 ────────────────────────────────────────────────────────────────
class TestYearGate:
    async def test_year_none_skips_gate(self, db_world, monkeypatch):
        """year=None 不查项目年度。"""
        async def _boom(*_a, **_k):
            raise AssertionError("year=None 不应查项目年度")
        monkeypatch.setattr(wp_cell_reader, "fetch_project_audit_year", _boom)
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], None, "D1", "明细表D1-1", "D4")
        assert r.state == "ok"

    async def test_year_blocked_no_audit_year(self, db_world, monkeypatch):
        """项目年度为空 → blocked。"""
        async def _none(db, pid):
            return None
        monkeypatch.setattr(wp_cell_reader, "fetch_project_audit_year", _none)
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], 2025, "D1", "明细表D1-1", "D4")
        assert r.state == "blocked"
        assert "项目未设置审计年度" in r.reason

    async def test_year_mismatch_missing(self, db_world, monkeypatch):
        """请求年度与项目年度不符 → missing。"""
        async def _2024(db, pid):
            return 2024
        monkeypatch.setattr(wp_cell_reader, "fetch_project_audit_year", _2024)
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], 2025, "D1", "明细表D1-1", "D4")
        assert r.state == "missing"
        assert "不符" in r.reason

    async def test_year_match_ok(self, db_world, monkeypatch):
        """请求年度与项目年度一致 → 正常取值。"""
        async def _2025(db, pid):
            return 2025
        monkeypatch.setattr(wp_cell_reader, "fetch_project_audit_year", _2025)
        r = await resolve_wp_cell(db_world["db"], db_world["pid"], 2025, "D1", "明细表D1-1", "D4")
        assert r.state == "ok"
        assert r.value == Decimal("42")


# ── WPExecutor.execute + year 关键字 ────────────────────────────────────────
class TestWPExecutorYearKwarg:
    """验证 WPExecutor.execute 的 year 参数是仅关键字且默认 None。"""

    def test_year_is_keyword_only(self):
        import inspect
        from app.services.formula_engine import WPExecutor
        sig = inspect.signature(WPExecutor.execute)
        year_param = sig.parameters.get("year")
        assert year_param is not None, "execute 缺少 year 参数"
        assert year_param.kind == inspect.Parameter.KEYWORD_ONLY, "year 必须是仅关键字参数"
        assert year_param.default is None, "year 默认值必须是 None"


# ── WP_COLUMN_KEYS 模块常量 ────────────────────────────────────────────────
class TestWPColumnKeys:
    def test_exported_and_contains_four_keys(self):
        from app.services.formula_engine import WP_COLUMN_KEYS
        assert isinstance(WP_COLUMN_KEYS, dict)
        assert set(WP_COLUMN_KEYS.keys()) == {"审定数", "未审数", "期初余额", "期末余额"}
        assert WP_COLUMN_KEYS["审定数"] == "audited_amount"
        assert WP_COLUMN_KEYS["未审数"] == "unadjusted_amount"
        assert WP_COLUMN_KEYS["期初余额"] == "opening_balance"
        assert WP_COLUMN_KEYS["期末余额"] == "audited_amount"
