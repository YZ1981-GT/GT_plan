"""公式推送引擎存储三层一致：V169 DDL == ORM == policy 常量（+ SQLite 往返）。

spec: chain-closure-phase2-formula-push-engine · 任务 4 · 需求 2.6 / 3.2

判据：
1. V169 / R169 成对存在，且版本号 169 在迁移目录中唯一（撞号会被 runner 静默丢弃）。
2. 两张表 DDL 列集 == ORM 列集，逐列可空性一致（迁移有、ORM 无 ⇒ 写不进去；反之 ⇒ 缺迁移）。
3. CHECK 取值集合：DDL == ORM == ``policy.STATES`` / ``RUN_STATUSES`` / ``PUSH_DOMAINS``。
4. 唯一约束 (project_id, year, addr_id) 与索引名两侧都在。
5. SQLite 真 ORM 往返：JSONB 值（数值 / 字符串 / 对象）原样读回；非法 state 被 CHECK 拒绝；
   同一 (project, year, addr_id) 第二行被唯一约束拒绝。

抽取器自检防空转：抽到的列非空、必含已知列、约束关键字不被当成列名。
"""
from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.formula_push_models import (
    PUSH_DOMAINS,
    PUSH_STATES,
    RUN_STATUSES,
    FormulaPushRun,
    FormulaPushState,
)
from app.services.formula_push import policy

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
V169 = MIGRATIONS / "V169__formula_push_engine.sql"
R169 = MIGRATIONS / "R169__rollback_formula_push_engine.sql"

_CONSTRAINT_HEADS = {"constraint", "primary", "unique", "foreign", "check", "exclude", "key"}


def _strip_line_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _create_body(table: str) -> str:
    """取 ``CREATE TABLE IF NOT EXISTS <table> (...)`` 的括号体（括号配对，不按首个 ``)`` 截断）。"""
    ddl = _strip_line_comments(V169.read_text(encoding="utf-8"))
    m = re.search(rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table}\s*\(", ddl, re.IGNORECASE)
    assert m, f"V169 未找到 CREATE TABLE IF NOT EXISTS {table}（抽取器失效，不是漂移）"
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
    """列名 → 是否 NOT NULL（PRIMARY KEY 视为 NOT NULL）。"""
    cols: dict[str, bool] = {}
    for seg in _segments(_create_body(table)):
        head = re.match(r'"?([A-Za-z_][A-Za-z0-9_]*)"?', seg)
        if not head or head.group(1).lower() in _CONSTRAINT_HEADS:
            continue
        upper = seg.upper()
        cols[head.group(1)] = "NOT NULL" in upper or "PRIMARY KEY" in upper
    return cols


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


# ── 1. 迁移成对 + 版本号唯一 ─────────────────────────────────────────────


def test_v169_r169_pair_and_version_unique():
    assert V169.is_file() and R169.is_file()
    same = [p.name for p in MIGRATIONS.glob("V*.sql") if re.match(r"^V0*169__", p.name)]
    assert same == [V169.name], f"V169 版本号撞号: {same}"
    rollback = _strip_line_comments(R169.read_text(encoding="utf-8"))
    drops = re.findall(r"DROP\s+TABLE\s+IF\s+EXISTS\s+(\w+)", rollback, re.IGNORECASE)
    # state 引用 run，必须先删 state
    assert drops == ["formula_push_state", "formula_push_run"], drops


# ── 2. 列集 + 可空性 ─────────────────────────────────────────────────────


@pytest.mark.parametrize("model", [FormulaPushRun, FormulaPushState], ids=lambda m: m.__tablename__)
def test_orm_columns_match_ddl(model):
    ddl = _ddl_columns(model.__tablename__)
    orm = {c.name: (not c.nullable) for c in model.__table__.columns}
    assert not (set(orm) - set(ddl)), f"ORM 有列但 V169 无: {sorted(set(orm) - set(ddl))}"
    assert not (set(ddl) - set(orm)), f"V169 有列但 ORM 无: {sorted(set(ddl) - set(orm))}"
    mismatched = {k: (ddl[k], orm[k]) for k in ddl if ddl[k] != orm[k]}
    assert not mismatched, f"可空性不一致 (DDL NOT NULL, ORM NOT NULL): {mismatched}"


def test_extractor_is_not_vacuous():
    run_cols = _ddl_columns("formula_push_run")
    state_cols = _ddl_columns("formula_push_state")
    assert {"id", "project_id", "trigger_source", "status", "detail", "finished_at"} <= set(run_cols)
    assert {"addr_id", "last_pushed_value", "state", "last_run_id", "updated_by"} <= set(state_cols)
    lowered = {c.lower() for c in (*run_cols, *state_cols)}
    assert not (_CONSTRAINT_HEADS & lowered), "约束关键字被当成列名"
    assert run_cols["project_id"] is True and state_cols["wp_id"] is False


# ── 3. CHECK 取值三侧一致 ─────────────────────────────────────────────────


def test_check_value_sets_match_across_layers():
    assert _ddl_check_values("formula_push_state", "state") == set(PUSH_STATES) == set(policy.STATES)
    assert _orm_check_values(FormulaPushState, "ck_formula_push_state_state") == set(PUSH_STATES)
    assert _ddl_check_values("formula_push_state", "domain") == set(PUSH_DOMAINS)
    assert _orm_check_values(FormulaPushState, "ck_formula_push_state_domain") == set(PUSH_DOMAINS)
    assert _ddl_check_values("formula_push_run", "status") == set(RUN_STATUSES)
    assert _orm_check_values(FormulaPushRun, "ck_formula_push_run_status") == set(RUN_STATUSES)


# ── 4. 唯一约束 + 索引 ───────────────────────────────────────────────────


def test_unique_and_indexes_on_both_sides():
    body = _create_body("formula_push_state")
    assert re.search(
        r"CONSTRAINT\s+uq_formula_push_state_addr\s+UNIQUE\s*\(\s*project_id\s*,\s*year\s*,\s*addr_id\s*\)",
        body, re.IGNORECASE,
    )
    uniques = [
        tuple(c.name for c in uc.columns)
        for uc in FormulaPushState.__table__.constraints
        if isinstance(uc, sa.UniqueConstraint) and uc.name == "uq_formula_push_state_addr"
    ]
    assert uniques == [("project_id", "year", "addr_id")]

    ddl = V169.read_text(encoding="utf-8")
    for model, name in (
        (FormulaPushRun, "idx_formula_push_run_project_year"),
        (FormulaPushState, "idx_formula_push_state_project_year_state"),
    ):
        assert name in {i.name for i in model.__table__.indexes}, f"ORM 缺索引 {name}"
        assert re.search(rf"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+{name}\b", ddl), f"V169 缺索引 {name}"


# ── 5. SQLite 真 ORM 往返 ────────────────────────────────────────────────


async def _sqlite_roundtrip() -> dict:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [FormulaPushRun.__table__, FormulaPushState.__table__]
    out: dict = {}
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: FormulaPushRun.metadata.create_all(c, tables=tables))
        pid = uuid.uuid4()
        async with AsyncSession(engine) as s:
            run = FormulaPushRun(project_id=pid, year=2025, trigger_source="manual")
            s.add(run)
            await s.flush()
            s.add_all([
                FormulaPushState(project_id=pid, year=2025, addr_id="E1/E1-1/E1-adj-tb-amount-ending",
                                 rule_id="E1.tb_amount.ending", domain="workpaper",
                                 last_pushed_value=100.5, last_formula_value="200.25",
                                 current_value={"rows": [1, 2]}, last_run_id=run.id),
            ])
            await s.commit()
            row = (await s.execute(sa.select(FormulaPushState))).scalar_one()
            run_row = (await s.execute(sa.select(FormulaPushRun))).scalar_one()
            out["values"] = (row.last_pushed_value, row.last_formula_value, row.current_value)
            out["defaults"] = (row.state, run_row.status, run_row.written_count, run_row.detail)

        async with AsyncSession(engine) as s:
            s.add(FormulaPushState(project_id=pid, year=2025, addr_id="x", rule_id="r",
                                   domain="workpaper", state="stale"))
            try:
                await s.commit()
                out["bad_state"] = "accepted"
            except IntegrityError:
                out["bad_state"] = "rejected"

        async with AsyncSession(engine) as s:
            s.add(FormulaPushState(project_id=pid, year=2025, addr_id="E1/E1-1/E1-adj-tb-amount-ending",
                                   rule_id="dup", domain="workpaper"))
            try:
                await s.commit()
                out["duplicate"] = "accepted"
            except IntegrityError:
                out["duplicate"] = "rejected"
    finally:
        await engine.dispose()
    return out


def test_sqlite_orm_roundtrip():
    out = asyncio.run(_sqlite_roundtrip())
    assert out["values"] == (100.5, "200.25", {"rows": [1, 2]})
    assert out["defaults"] == ("auto", "running", 0, {})
    assert out["bad_state"] == "rejected", "state CHECK 未生效"
    assert out["duplicate"] == "rejected", "(project, year, addr_id) 唯一约束未生效"
