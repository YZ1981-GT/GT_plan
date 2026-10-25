"""V169 在真 PostgreSQL 上可执行、幂等、可回滚，且 ORM 能按其写读（一次性 schema，结束 DROP）。

spec: chain-closure-phase2-formula-push-engine · 任务 4

用 ``MigrationRunner._split_sql_statements`` + ``exec_driver_sql``（与 runner 生产执行路径同一拆句与
执行方式）在临时 schema 里执行 V169 两次（幂等），再验证：
- information_schema 列集 == ORM 列集；
- ORM 写入：JSONB 数值 / 字符串 / 对象原样读回，state 默认 auto；
- 非法 state 被 CHECK 拒绝、同 (project, year, addr_id) 第二行被唯一约束拒绝；
- 删 run ⇒ state.last_run_id 置 NULL；删 project ⇒ 两表级联删除；
- R169 执行后两表不存在。

``DATABASE_URL`` 非 PostgreSQL 时直接失败不 skip（与 task35 / 适配器 PG 守卫同策略）。
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_MIGRATIONS = _BACKEND / "migrations"
_STUBS = (
    "CREATE TABLE projects (id UUID PRIMARY KEY)",
    "CREATE TABLE working_paper (id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id))",
)


async def _run_sql_file(conn, path: Path) -> int:
    from app.core.migration_runner import MigrationRunner

    statements = MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8"))
    for stmt in statements:
        await conn.exec_driver_sql(stmt)
    return len(statements)


async def _columns(conn, table: str) -> set[str]:
    rows = await conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :t"
    ), {"t": table})
    return {r[0] for r in rows}


async def _expect_integrity_error(conn, sql: str, params: dict) -> bool:
    from sqlalchemy.exc import IntegrityError

    nested = await conn.begin_nested()
    try:
        await conn.execute(sa.text(sql), params)
    except IntegrityError:
        await nested.rollback()
        return True
    await nested.rollback()
    return False


async def _scenario() -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.database import engine
    from app.models.formula_push_models import FormulaPushRun, FormulaPushState

    assert engine.dialect.name == "postgresql", f"需要 PostgreSQL，实际 {engine.dialect.name}"
    schema = f"tmp_formula_push_{uuid.uuid4().hex[:10]}"
    v169 = _MIGRATIONS / "V169__formula_push_engine.sql"
    r169 = _MIGRATIONS / "R169__rollback_formula_push_engine.sql"
    pid, wp = uuid.uuid4(), uuid.uuid4()
    out: dict = {}
    async with engine.begin() as conn:
        await conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text(f'SET search_path TO "{schema}"'))
            for stmt in _STUBS:
                await conn.execute(sa.text(stmt))
            out["statements"] = await _run_sql_file(conn, v169)
            out["statements_rerun"] = await _run_sql_file(conn, v169)  # 幂等
            out["run_cols"] = await _columns(conn, "formula_push_run")
            out["state_cols"] = await _columns(conn, "formula_push_state")

            await conn.execute(sa.text("INSERT INTO projects (id) VALUES (:p)"), {"p": pid})
            await conn.execute(sa.text("INSERT INTO working_paper (id, project_id) VALUES (:w, :p)"),
                               {"w": wp, "p": pid})

            session = AsyncSession(bind=conn)
            run = FormulaPushRun(project_id=pid, year=2025, trigger_source="manual")
            session.add(run)
            await session.flush()
            run_id = run.id
            state = FormulaPushState(
                project_id=pid, year=2025, addr_id="E1/E1-1/E1-adj-tb-amount-ending",
                rule_id="E1.tb_amount.ending", domain="workpaper", wp_id=wp,
                last_pushed_value=100.5, last_formula_value="200.25",
                current_value={"rows": [1, 2]}, last_run_id=run.id,
            )
            session.add(state)
            await session.flush()
            session.expire_all()
            got = (await session.execute(sa.select(FormulaPushState))).scalar_one()
            got_run = (await session.execute(sa.select(FormulaPushRun))).scalar_one()
            out["values"] = (got.last_pushed_value, got.last_formula_value, got.current_value)
            out["defaults"] = (got.state, got_run.status)
            await session.close()

            out["bad_state_rejected"] = await _expect_integrity_error(
                conn,
                "INSERT INTO formula_push_state (project_id, year, addr_id, rule_id, domain, state) "
                "VALUES (:p, 2025, 'x', 'r', 'workpaper', 'stale')",
                {"p": pid},
            )
            out["duplicate_rejected"] = await _expect_integrity_error(
                conn,
                "INSERT INTO formula_push_state (project_id, year, addr_id, rule_id, domain) "
                "VALUES (:p, 2025, 'E1/E1-1/E1-adj-tb-amount-ending', 'dup', 'workpaper')",
                {"p": pid},
            )

            await conn.execute(sa.text("DELETE FROM formula_push_run WHERE id = :r"), {"r": run_id})
            out["last_run_after_delete"] = (await conn.execute(sa.text(
                "SELECT last_run_id FROM formula_push_state"
            ))).scalar_one()

            await conn.execute(sa.text("DELETE FROM working_paper WHERE id = :w"), {"w": wp})
            await conn.execute(sa.text("DELETE FROM projects WHERE id = :p"), {"p": pid})
            out["rows_after_project_delete"] = (await conn.execute(sa.text(
                "SELECT count(*) FROM formula_push_state"
            ))).scalar_one()

            await _run_sql_file(conn, r169)
            out["tables_after_rollback"] = (await conn.execute(sa.text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = current_schema() "
                "AND table_name IN ('formula_push_state', 'formula_push_run')"
            ))).scalar_one()
            await conn.rollback()
    finally:
        async with engine.begin() as conn:
            await conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
    return out


def test_v169_on_real_postgres():
    from app.models.formula_push_models import FormulaPushRun, FormulaPushState

    out = asyncio.run(_scenario())
    assert out["statements"] == out["statements_rerun"] > 0
    assert out["run_cols"] == {c.name for c in FormulaPushRun.__table__.columns}
    assert out["state_cols"] == {c.name for c in FormulaPushState.__table__.columns}
    assert out["values"] == (100.5, "200.25", {"rows": [1, 2]})
    assert out["defaults"] == ("auto", "running")
    assert out["bad_state_rejected"], "state CHECK 未生效"
    assert out["duplicate_rejected"], "(project, year, addr_id) 唯一约束未生效"
    assert out["last_run_after_delete"] is None, "删 run 后 last_run_id 未置 NULL"
    assert out["rows_after_project_delete"] == 0, "删 project 未级联删除 state"
    assert out["tables_after_rollback"] == 0, "R169 未删净"
