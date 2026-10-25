"""合并推送存储三层一致：V172 DDL == ORM（+ SQLite 真 ORM 往返）。

spec: consol-elimination-single-source-push · 任务 1 · 需求 1.1 / 2.4 / 6.1 / 8.1

判据：
1. V172 / R172 成对存在，版本号 172 在迁移目录唯一（撞号会被 runner 拒绝）；R172 撤销 V172 的每项改动。
2. 两张新表 DDL 列集 == ORM 列集，逐列可空性一致；新增列（elimination_entries.origin / origin_key、
   consol_note_data.is_stale）三侧都在。
3. CHECK 取值集合：DDL == ORM == 模块常量。
4. 部分唯一索引两侧同名同列。
5. SQLite 真 ORM 往返：默认值落库；非法状态被 CHECK 拒绝；同来源同键第二笔未删分录被唯一索引拒绝，
   软删后同键可再建（部分索引谓词真生效）；同单元格第二条未删公式被拒绝。
"""
from __future__ import annotations

import asyncio
import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import tests.conftest  # noqa: F401  (注册全部 ORM 模型与 SQLite 方言补丁)
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_push_models import (
    NOTE_FORMULA_SOURCES,
    NOTE_TEMPLATE_TYPES,
    PUSH_RUN_STATUSES,
    ConsolNoteFormula,
    ConsolPushRun,
)
from app.models.consolidation_models import (
    EliminationEntry,
    EliminationEntryType,
    ReviewStatusEnum,
)

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
V172 = MIGRATIONS / "V172__consol_elimination_single_source_push.sql"
R172 = MIGRATIONS / "R172__rollback_consol_elimination_single_source_push.sql"

_CONSTRAINT_HEADS = {"constraint", "primary", "unique", "foreign", "check", "exclude", "key"}


def _strip_line_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _ddl() -> str:
    return _strip_line_comments(V172.read_text(encoding="utf-8"))


def _create_body(table: str) -> str:
    ddl = _ddl()
    m = re.search(rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table}\s*\(", ddl, re.IGNORECASE)
    assert m, f"V172 未找到 CREATE TABLE IF NOT EXISTS {table}（抽取器失效，不是漂移）"
    start = m.end() - 1
    depth = 0
    for i in range(start, len(ddl)):
        if ddl[i] == "(":
            depth += 1
        elif ddl[i] == ")":
            depth -= 1
            if depth == 0:
                return ddl[start + 1 : i]
    raise AssertionError(f"{table} 建表体括号未配对")


def _segments(body: str) -> list[str]:
    out, depth, seg_start = [], 0, 0
    for i, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(body[seg_start:i].strip())
            seg_start = i + 1
    out.append(body[seg_start:].strip())
    return [s for s in out if s]


def _ddl_columns(table: str) -> dict[str, bool]:
    cols: dict[str, bool] = {}
    for seg in _segments(_create_body(table)):
        head = re.match(r'"?([A-Za-z_][A-Za-z0-9_]*)"?', seg)
        if not head or head.group(1).lower() in _CONSTRAINT_HEADS:
            continue
        upper = seg.upper()
        cols[head.group(1)] = "NOT NULL" in upper or "PRIMARY KEY" in upper
    return cols


def _ddl_added_columns(table: str) -> dict[str, bool]:
    """``ALTER TABLE <table> ADD COLUMN IF NOT EXISTS <col> ...`` → 列名 → 是否 NOT NULL。"""
    out: dict[str, bool] = {}
    pattern = rf"ALTER\s+TABLE\s+{table}\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+(\w+)([^;]*);"
    for m in re.finditer(pattern, _ddl(), re.IGNORECASE):
        out[m.group(1)] = "NOT NULL" in m.group(2).upper()
    return out


def _ddl_check_values(table: str, column: str) -> set[str]:
    body = _create_body(table)
    m = re.search(rf"CHECK\s*\(\s*{column}\s+IN\s*\(([^)]*)\)\s*\)", body, re.IGNORECASE)
    assert m, f"{table}.{column} 的 CHECK IN 未找到"
    return set(re.findall(r"'([^']*)'", m.group(1)))


def _orm_check_values(model, name: str) -> set[str]:
    for c in model.__table__.constraints:
        if isinstance(c, sa.CheckConstraint) and c.name == name:
            return set(re.findall(r"'([^']*)'", str(c.sqltext)))
    raise AssertionError(f"ORM {model.__name__} 缺 CHECK {name}")


# ── 1. 迁移成对 + 版本号唯一 + 回滚覆盖 ─────────────────────────────────────


def test_v172_r172_pair_and_version_unique():
    assert V172.is_file() and R172.is_file()
    same = [p.name for p in MIGRATIONS.glob("V*.sql") if re.match(r"^V0*172__", p.name)]
    assert same == [V172.name], f"V172 版本号撞号: {same}"
    rollback = _strip_line_comments(R172.read_text(encoding="utf-8"))
    drops = set(re.findall(r"DROP\s+TABLE\s+IF\s+EXISTS\s+(\w+)", rollback, re.IGNORECASE))
    assert drops == {"consol_push_run", "consol_note_formula"}
    dropped_cols = set(re.findall(
        r"ALTER\s+TABLE\s+(\w+)\s+DROP\s+COLUMN\s+IF\s+EXISTS\s+(\w+)", rollback, re.IGNORECASE,
    ))
    assert dropped_cols == {
        ("elimination_entries", "origin"), ("elimination_entries", "origin_key"), ("consol_note_data", "is_stale"),
    }
    assert re.search(r"DROP\s+INDEX\s+IF\s+EXISTS\s+ux_elim_entries_origin\b", rollback)


# ── 2. 列集与可空性 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("model", [ConsolPushRun, ConsolNoteFormula], ids=lambda m: m.__tablename__)
def test_new_tables_orm_columns_match_ddl(model):
    ddl = _ddl_columns(model.__tablename__)
    orm = {c.name: (not c.nullable) for c in model.__table__.columns}
    assert not (set(orm) - set(ddl)), f"ORM 有列但 V172 无: {sorted(set(orm) - set(ddl))}"
    assert not (set(ddl) - set(orm)), f"V172 有列但 ORM 无: {sorted(set(ddl) - set(orm))}"
    mismatched = {k: (ddl[k], orm[k]) for k in ddl if ddl[k] != orm[k]}
    assert not mismatched, f"可空性不一致 (DDL NOT NULL, ORM NOT NULL): {mismatched}"


@pytest.mark.parametrize(
    ("model", "table", "columns"),
    [
        (EliminationEntry, "elimination_entries", {"origin", "origin_key"}),
        (ConsolNoteData, "consol_note_data", {"is_stale"}),
    ],
    ids=["elimination_entries", "consol_note_data"],
)
def test_added_columns_on_both_sides(model, table, columns):
    ddl = _ddl_added_columns(table)
    assert set(ddl) == columns, f"V172 对 {table} 新增列 {sorted(ddl)} ≠ 预期 {sorted(columns)}"
    orm = {c.name: (not c.nullable) for c in model.__table__.columns}
    for col in columns:
        assert col in orm, f"ORM {model.__name__} 缺列 {col}"
        assert orm[col] == ddl[col], f"{table}.{col} 可空性不一致 DDL={ddl[col]} ORM={orm[col]}"


def test_extractor_is_not_vacuous():
    assert len(_ddl_columns("consol_push_run")) >= 9
    assert len(_ddl_columns("consol_note_formula")) >= 11
    assert _ddl_added_columns("elimination_entries")


def test_v173_blank_reason_three_layers():
    """V173：financial_report.blank_reason（合并报表留空原因）DDL == ORM == 响应 schema；R173 撤销。"""
    from app.models.consolidation_schemas import ConsolReportRow
    from app.models.report_models import FinancialReport

    v173 = MIGRATIONS / "V173__financial_report_blank_reason.sql"
    r173 = MIGRATIONS / "R173__rollback_financial_report_blank_reason.sql"
    assert v173.is_file() and r173.is_file()
    assert [p.name for p in MIGRATIONS.glob("V*.sql") if re.match(r"^V0*173__", p.name)] == [v173.name]
    ddl = _strip_line_comments(v173.read_text(encoding="utf-8"))
    m = re.search(r"ALTER\s+TABLE\s+financial_report\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+blank_reason\s+(\w+)([^;]*);",
                  ddl, re.IGNORECASE)
    assert m and m.group(1).upper() == "TEXT" and "NOT NULL" not in m.group(2).upper()
    column = FinancialReport.__table__.columns["blank_reason"]
    assert column.nullable and isinstance(column.type, sa.Text)
    assert "blank_reason" in ConsolReportRow.model_fields
    rollback = _strip_line_comments(r173.read_text(encoding="utf-8"))
    assert re.search(r"ALTER\s+TABLE\s+financial_report\s+DROP\s+COLUMN\s+IF\s+EXISTS\s+blank_reason", rollback)


# ── 3. CHECK 取值两侧一致 ───────────────────────────────────────────────────


def test_check_value_sets_match_across_layers():
    assert _ddl_check_values("consol_push_run", "status") == set(PUSH_RUN_STATUSES)
    assert _orm_check_values(ConsolPushRun, "ck_consol_push_run_status") == set(PUSH_RUN_STATUSES)
    assert _ddl_check_values("consol_note_formula", "source") == set(NOTE_FORMULA_SOURCES)
    assert _orm_check_values(ConsolNoteFormula, "ck_consol_note_formula_source") == set(NOTE_FORMULA_SOURCES)
    assert _ddl_check_values("consol_note_formula", "template_type") == set(NOTE_TEMPLATE_TYPES)
    assert _orm_check_values(ConsolNoteFormula, "ck_consol_note_formula_template") == set(NOTE_TEMPLATE_TYPES)


# ── 4. 索引两侧同名同列 ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("model", "name", "columns", "unique"),
    [
        (EliminationEntry, "ux_elim_entries_origin", ("project_id", "year", "origin", "origin_key"), True),
        (ConsolNoteFormula, "ux_consol_note_formula_cell", ("template_type", "section_id", "row_index", "col_index"), True),
        (ConsolPushRun, "idx_consol_push_run_project_year", ("project_id", "year", "started_at"), False),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_indexes_on_both_sides(model, name, columns, unique):
    idx = {i.name: i for i in model.__table__.indexes}.get(name)
    assert idx is not None, f"ORM 缺索引 {name}"
    assert tuple(c.name for c in idx.columns) == columns
    assert bool(idx.unique) == unique
    kw = "UNIQUE\\s+INDEX" if unique else "INDEX"
    m = re.search(rf"CREATE\s+{kw}\s+IF\s+NOT\s+EXISTS\s+{name}\s+ON\s+\w+\s*\(([^)]*)\)", _ddl(), re.IGNORECASE)
    assert m, f"V172 缺索引 {name}"
    assert tuple(c.strip() for c in m.group(1).split(",")) == columns


# ── 5. SQLite 真 ORM 往返 ───────────────────────────────────────────────────


def _entry(pid: uuid.UUID, origin: str | None, key: str | None, no: str) -> EliminationEntry:
    return EliminationEntry(
        project_id=pid, year=2025, entry_no=no, entry_type=EliminationEntryType.equity,
        account_code="1511", debit_amount=Decimal("1"), credit_amount=Decimal("1"),
        lines=[], entry_group_id=uuid.uuid4(), review_status=ReviewStatusEnum.draft,
        origin=origin, origin_key=key,
    )


async def _sqlite_roundtrip() -> dict:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        EliminationEntry.__table__, ConsolPushRun.__table__, ConsolNoteFormula.__table__, ConsolNoteData.__table__,
    ]
    out: dict = {}
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: EliminationEntry.metadata.create_all(
                c, tables=[t for t in EliminationEntry.metadata.sorted_tables
                           if t.name in {"projects", "users"} or t in tables],
            ))
        pid = uuid.uuid4()
        async with AsyncSession(engine) as s:
            s.add(ConsolPushRun(project_id=pid, year=2025, trigger_source="manual"))
            s.add(ConsolNoteFormula(template_type="soe", section_id="五-1-1", row_index=4, col_index=1,
                                    formula="REPORT('BS-002')"))
            s.add(ConsolNoteData(project_id=pid, year=2025, section_id="五-1-1", data={}))
            s.add(_entry(pid, "ws_equity_sim", "equity_sim:step1:A", "EQ-1"))
            s.add(_entry(pid, None, None, "EQ-2"))
            s.add(_entry(pid, None, None, "EQ-3"))  # 手工分录不受来源唯一约束
            await s.commit()
            run = (await s.execute(sa.select(ConsolPushRun))).scalar_one()
            note = (await s.execute(sa.select(ConsolNoteData))).scalar_one()
            formula = (await s.execute(sa.select(ConsolNoteFormula))).scalar_one()
            out["defaults"] = (run.status, run.steps, run.warnings, note.is_stale, formula.source, formula.is_deleted)

        async with AsyncSession(engine) as s:
            s.add(ConsolPushRun(project_id=pid, year=2025, trigger_source="manual", status="stale"))
            try:
                await s.commit()
                out["bad_status"] = "accepted"
            except IntegrityError:
                out["bad_status"] = "rejected"

        async with AsyncSession(engine) as s:
            s.add(_entry(pid, "ws_equity_sim", "equity_sim:step1:A", "EQ-4"))
            try:
                await s.commit()
                out["duplicate_origin"] = "accepted"
            except IntegrityError:
                out["duplicate_origin"] = "rejected"

        async with AsyncSession(engine) as s:
            first = (await s.execute(sa.select(EliminationEntry).where(EliminationEntry.entry_no == "EQ-1"))).scalar_one()
            first.soft_delete()
            await s.commit()
            s.add(_entry(pid, "ws_equity_sim", "equity_sim:step1:A", "EQ-5"))
            try:
                await s.commit()
                out["after_soft_delete"] = "accepted"
            except IntegrityError:
                out["after_soft_delete"] = "rejected"

        async with AsyncSession(engine) as s:
            s.add(ConsolNoteFormula(template_type="soe", section_id="五-1-1", row_index=4, col_index=1,
                                    formula="TB('1001','期末余额')"))
            try:
                await s.commit()
                out["duplicate_cell"] = "accepted"
            except IntegrityError:
                out["duplicate_cell"] = "rejected"
    finally:
        await engine.dispose()
    return out


def test_sqlite_orm_roundtrip():
    out = asyncio.run(_sqlite_roundtrip())
    assert out["defaults"] == ("running", [], [], False, "manual", False)
    assert out["bad_status"] == "rejected", "status CHECK 未生效"
    assert out["duplicate_origin"] == "rejected", "同来源同键唯一索引未生效"
    assert out["after_soft_delete"] == "accepted", "部分索引谓词未生效：软删后同键应可再建"
    assert out["duplicate_cell"] == "rejected", "同单元格唯一索引未生效"
