"""V176 在真 PostgreSQL 上可执行、两次幂等、回填正确、R176 删净，且 ORM 三层一致。

spec: chain-closure-phase3-push-rollout · 任务 8（决策 2 · V176 / R176 + ORM + 三层一致）

用 ``MigrationRunner._split_sql_statements`` + ``exec_driver_sql``（与 runner 生产执行路径
同一拆句与执行方式）在临时 schema 里：
- V176 两次（幂等）
- 插入试算表行（有分量差异 + 无分量差异），验证回填只修不等行
- information_schema 列集 ⊇ ORM 新增三列
- ORM 写入/读回 wp_adjustment / wp_publish_base / wp_published_at
- R176 执行后三列不存在

``DATABASE_URL`` 非 PostgreSQL 时 skip（真 PG 约束不可 SQLite 代替）。
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_MIGRATIONS = _BACKEND / "migrations"


async def _run_sql_file(conn, path: Path) -> int:
    from app.core.migration_runner import MigrationRunner

    statements = MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8"))
    for stmt in statements:
        await conn.exec_driver_sql(stmt)
    return len(statements)


async def _columns(conn, table: str) -> set[str]:
    rows = await conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :t"
        ),
        {"t": table},
    )
    return {r[0] for r in rows}


async def _scenario() -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.database import engine
    from app.models.audit_platform_models import TrialBalance

    if engine.dialect.name != "postgresql":
        return {"skip": True}

    schema = f"tmp_v176_{uuid.uuid4().hex[:10]}"
    v176 = _MIGRATIONS / "V176__trial_balance_workpaper_adjustment.sql"
    r176 = _MIGRATIONS / "R176__rollback_trial_balance_workpaper_adjustment.sql"

    pid = uuid.uuid4()
    out: dict = {}

    async with engine.begin() as conn:
        await conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))

    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text(f'SET search_path TO "{schema}"'))

            # ── 建前置依赖表 + trial_balance 基线列 ──────────────────────
            await conn.execute(sa.text("CREATE TABLE projects (id UUID PRIMARY KEY)"))
            await conn.execute(sa.text(
                "DO $$ BEGIN "
                "  CREATE TYPE account_category AS ENUM "
                "    ('asset','liability','equity','revenue','expense'); "
                "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
            ))
            await conn.execute(sa.text("""
                CREATE TABLE trial_balance (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    project_id UUID NOT NULL REFERENCES projects(id),
                    year INT NOT NULL,
                    company_code TEXT NOT NULL,
                    standard_account_code TEXT NOT NULL,
                    account_name TEXT,
                    account_category account_category NOT NULL,
                    unadjusted_amount NUMERIC(20,2),
                    rje_adjustment NUMERIC(20,2) NOT NULL DEFAULT 0,
                    aje_adjustment NUMERIC(20,2) NOT NULL DEFAULT 0,
                    audited_amount NUMERIC(20,2),
                    opening_balance NUMERIC(20,2),
                    currency_code VARCHAR(3) NOT NULL DEFAULT 'CNY',
                    is_deleted BOOLEAN NOT NULL DEFAULT false,
                    deleted_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
            """))

            # ── 插入测试行（V176 回填前） ────────────────────────────────
            await conn.execute(sa.text("INSERT INTO projects (id) VALUES (:p)"), {"p": pid})

            # 行 1：有分量差异（audited ≠ unadj+rje+aje）
            row1_id = uuid.uuid4()
            await conn.execute(sa.text(
                "INSERT INTO trial_balance "
                "(id, project_id, year, company_code, standard_account_code, account_name, "
                " account_category, unadjusted_amount, rje_adjustment, aje_adjustment, audited_amount) "
                "VALUES (:id, :p, 2025, '001', '1001', '银行存款', 'asset', 100, 5, -2, 120)"
            ), {"id": row1_id, "p": pid})

            # 行 2：无分量差异（audited == unadj+rje+aje）
            row2_id = uuid.uuid4()
            await conn.execute(sa.text(
                "INSERT INTO trial_balance "
                "(id, project_id, year, company_code, standard_account_code, account_name, "
                " account_category, unadjusted_amount, rje_adjustment, aje_adjustment, audited_amount) "
                "VALUES (:id, :p, 2025, '001', '1002', '应收账款', 'asset', 200, 10, -5, 205)"
            ), {"id": row2_id, "p": pid})

            # 行 3：audited IS NULL（不应被回填）
            row3_id = uuid.uuid4()
            await conn.execute(sa.text(
                "INSERT INTO trial_balance "
                "(id, project_id, year, company_code, standard_account_code, account_name, "
                " account_category, unadjusted_amount, rje_adjustment, aje_adjustment, audited_amount) "
                "VALUES (:id, :p, 2025, '001', '1003', '预付账款', 'asset', 50, 0, 0, NULL)"
            ), {"id": row3_id, "p": pid})

            # ── 第一次执行 V176（添加列 + 回填） ──────────────────────────
            out["v176_stmts_1"] = await _run_sql_file(conn, v176)
            out["cols_after_v176"] = await _columns(conn, "trial_balance")

            # ── 第二次执行 V176（幂等：IF NOT EXISTS 不报错） ──────────────
            out["v176_stmts_2"] = await _run_sql_file(conn, v176)

            # ── 验证回填结果 ──────────────────────────────────────────────
            rows = await conn.execute(sa.text(
                "SELECT id, wp_adjustment, wp_publish_base, wp_published_at "
                "FROM trial_balance ORDER BY standard_account_code"
            ))
            by_id = {r[0]: (r[1], r[2], r[3]) for r in rows}

            # 行 1：audited=120, unadj+rje+aje=100+5-2=103 → wp_adjustment=17
            adj1, base1, ts1 = by_id[row1_id]
            out["row1_wp_adjustment"] = adj1
            out["row1_wp_publish_base"] = base1
            out["row1_wp_published_at"] = ts1

            # 行 2：audited=205, unadj+rje+aje=200+10-5=205 → wp_adjustment=0（未修改）
            adj2, base2, ts2 = by_id[row2_id]
            out["row2_wp_adjustment"] = adj2
            out["row2_wp_publish_base"] = base2

            # 行 3：audited IS NULL → wp_adjustment=0（DEFAULT，未被回填）
            adj3, base3, ts3 = by_id[row3_id]
            out["row3_wp_adjustment"] = adj3

            # ── ORM 写入/读回 ─────────────────────────────────────────────
            session = AsyncSession(bind=conn)
            row4_id = uuid.uuid4()
            tb = TrialBalance(
                id=row4_id,
                project_id=pid,
                year=2025,
                company_code="001",
                standard_account_code="6001",
                account_name="营业收入",
                account_category="revenue",
                unadjusted_amount=Decimal("1000.00"),
                rje_adjustment=Decimal("0"),
                aje_adjustment=Decimal("0"),
                audited_amount=Decimal("1050.00"),
                wp_adjustment=Decimal("50.00"),
                wp_publish_base=Decimal("1000.00"),
            )
            session.add(tb)
            await session.flush()
            session.expire_all()
            got = (await session.execute(
                sa.select(TrialBalance).where(TrialBalance.id == row4_id)
            )).scalar_one()
            out["orm_wp_adjustment"] = got.wp_adjustment
            out["orm_wp_publish_base"] = got.wp_publish_base
            out["orm_wp_published_at"] = got.wp_published_at
            await session.close()

            # ── 三层一致：information_schema 列集 ⊇ ORM 列集 ──────────────
            orm_cols = {c.name for c in TrialBalance.__table__.columns}
            out["orm_cols"] = orm_cols
            out["db_cols"] = await _columns(conn, "trial_balance")

            # ── R176 删列 ─────────────────────────────────────────────────
            await _run_sql_file(conn, r176)
            out["cols_after_r176"] = await _columns(conn, "trial_balance")

            await conn.rollback()  # 全回滚，临时 schema 清理不留数据
    finally:
        async with engine.begin() as conn:
            await conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()

    return out


def test_v176_on_real_postgres():
    import pytest

    from app.models.audit_platform_models import TrialBalance

    out = asyncio.run(_scenario())
    if out.get("skip"):
        pytest.skip("需 PostgreSQL（V176 真 PG 幂等 + 回填 + 三层一致）")

    new_cols = {"wp_adjustment", "wp_publish_base", "wp_published_at"}

    # ── 幂等：两次执行语句数相同 ──────────────────────────────────────
    assert out["v176_stmts_1"] == out["v176_stmts_2"] > 0

    # ── 新列存在 ──────────────────────────────────────────────────────
    assert new_cols <= out["cols_after_v176"]

    # ── 回填：有差异行 wp_adjustment = audited − (unadj+rje+aje) ─────
    assert out["row1_wp_adjustment"] == Decimal("17.00"), (
        f"行1 wp_adjustment 应为 17（120−103），实际 {out['row1_wp_adjustment']}"
    )
    assert out["row1_wp_publish_base"] is None, "回填不写 wp_publish_base"
    assert out["row1_wp_published_at"] is None, "回填不写 wp_published_at"

    # ── 回填：无差异行 wp_adjustment 保持 DEFAULT 0 ───────────────────
    assert out["row2_wp_adjustment"] == Decimal("0"), (
        f"行2 wp_adjustment 应为 0（无差异），实际 {out['row2_wp_adjustment']}"
    )
    assert out["row2_wp_publish_base"] is None

    # ── 回填：audited IS NULL 行不被回填 ──────────────────────────────
    assert out["row3_wp_adjustment"] == Decimal("0"), (
        f"行3 wp_adjustment 应为 0（audited NULL），实际 {out['row3_wp_adjustment']}"
    )

    # ── ORM 写入/读回一致 ──────────────────────────────────────────────
    assert out["orm_wp_adjustment"] == Decimal("50.00")
    assert out["orm_wp_publish_base"] == Decimal("1000.00")
    assert out["orm_wp_published_at"] is None  # 未设置时为 NULL

    # ── 三层一致：ORM 列 ⊆ DB 列（ORM 声明的每一列 DB 都有） ─────────
    missing = out["orm_cols"] - out["db_cols"]
    assert not missing, f"ORM 声明了 DB 没有的列: {missing}"

    # ── R176 删净：三新列不再存在 ──────────────────────────────────────
    assert not (new_cols & out["cols_after_r176"]), (
        f"R176 后仍存在: {new_cols & out['cols_after_r176']}"
    )
