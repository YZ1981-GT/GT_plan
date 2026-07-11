# Feature: formula-management-library — Task 1.3 V100 迁移幂等测试
"""V100（公式管理库）迁移幂等性集成测试（真实 PG）。

Task 1.3 / 需求 3.2、4.1、4.2：验证 V100 迁移脚本
`backend/migrations/V100__formula_management_library.sql`：

- 建成 `wp_formula` 五个新列（formula_type / last_computed_at / refs /
  issue_description / hint_text）——实际 V100 还含 formula_source /
  reference_formula_id，一并断言。
- 建成三张新表：draft_marker / draft_refresh_audit / draft_refresh_snapshot。
- 重复执行迁移不报错（IF NOT EXISTS + DO $$ information_schema.columns 守护），
  确保重复运行幂等。

迁移用 `MigrationRunner._split_sql_statements` 分句（正确处理 DO $$ 块），
经 `exec_driver_sql` 逐条执行——与运行时 `_apply_migration` 同口径。
PG 不可达则 skip（V100 依赖 information_schema / DO $$ / JSONB / TIMESTAMPTZ
等 PG 专属特性，SQLite 无法覆盖）。

Validates: Requirements 3.2, 4.1, 4.2
"""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.migration_runner import MigrationRunner

_V100 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V100__formula_management_library.sql"
)
_IS_PG = settings.DATABASE_URL.startswith("postgresql")

# wp_formula 五个新列（+ V100 附加的来源/参照两列）
_NEW_COLUMNS = (
    "formula_type",
    "last_computed_at",
    "refs",
    "issue_description",
    "hint_text",
    "formula_source",
    "reference_formula_id",
)
# 三张新表
_NEW_TABLES = (
    "draft_marker",
    "draft_refresh_audit",
    "draft_refresh_snapshot",
)


async def _apply_v100(engine) -> None:
    """按运行时口径分句执行 V100（DO $$ 块整体保留），逐条 exec_driver_sql。"""
    sql = _V100.read_text(encoding="utf-8")
    statements = MigrationRunner._split_sql_statements(sql)
    assert statements, "V100 迁移解析出的语句为空"
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    """真实 PG async engine；不可达则 skip。"""
    if not _IS_PG:
        pytest.skip("need PostgreSQL (V100 migration idempotency test)")

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")

    try:
        yield engine
    finally:
        await engine.dispose()


def test_v100_migration_file_exists():
    """V100 迁移文件存在。"""
    assert _V100.is_file(), "V100 formula-management-library 迁移缺失"


@pytest.mark.asyncio
async def test_v100_creates_columns_and_tables_and_is_idempotent(pg_engine):
    """重复执行 V100 迁移不报错；五个新列 + 三张新表建成。

    Validates: Requirements 3.2, 4.1, 4.2
    """
    # 连续执行两次——第二次即幂等验证（IF NOT EXISTS + information_schema 守护）。
    await _apply_v100(pg_engine)
    await _apply_v100(pg_engine)  # 不得抛错

    async with pg_engine.connect() as conn:
        # ① wp_formula 新列全部存在
        cols = set(
            (
                await conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'wp_formula'"
                    )
                )
            )
            .scalars()
            .all()
        )
        missing_cols = [c for c in _NEW_COLUMNS if c not in cols]
        assert not missing_cols, f"wp_formula 缺少 V100 新列: {missing_cols}"

        # ② 三张新表全部存在
        for tbl in _NEW_TABLES:
            reg = (
                await conn.execute(
                    sa.text("SELECT to_regclass(:t)"), {"t": f"public.{tbl}"}
                )
            ).scalar()
            assert reg is not None, f"V100 未建成表: {tbl}"


@pytest.mark.asyncio
async def test_v100_repeat_run_preserves_schema(pg_engine):
    """第三次执行后 schema 仍稳定：新列/新表数量不因重复运行而变化。

    Validates: Requirements 4.1, 4.2
    """
    await _apply_v100(pg_engine)

    async with pg_engine.connect() as conn:
        cols_before = (
            await conn.execute(
                sa.text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name = 'wp_formula' AND column_name = ANY(:names)"
                ),
                {"names": list(_NEW_COLUMNS)},
            )
        ).scalar()

    # 再跑一次，列数不应改变（幂等：ALTER 被 information_schema 守护跳过）
    await _apply_v100(pg_engine)

    async with pg_engine.connect() as conn:
        cols_after = (
            await conn.execute(
                sa.text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name = 'wp_formula' AND column_name = ANY(:names)"
                ),
                {"names": list(_NEW_COLUMNS)},
            )
        ).scalar()

    assert cols_before == cols_after == len(_NEW_COLUMNS), (
        f"重复运行后新列数量变化: before={cols_before} after={cols_after} "
        f"expected={len(_NEW_COLUMNS)}"
    )
