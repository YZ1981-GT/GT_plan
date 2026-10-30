"""迁移 V214 / R214（advanced-query-linkage-closure 任务 25；design §8、§10.2「迁移」行）：在临时 schema 里回放。

同一事务内建临时 schema、``search_path`` 只含它，按迁移前的形状建 ``custom_query_templates``，原样执行迁移文件文本：
- V214 后两列、列表索引、scope 检查约束都在；再执行一遍不报错（IF NOT EXISTS / 约束存在即跳过）；约束拒收六个值以外的 scope。
- 旧库由 ``scripts/_ensure_custom_query_tables.py`` 建表时同名约束只认 4 个值（没有 project）：V214 后换成六个值（变异 B8-h：
  去掉替换分支 ⇒ 「指定项目共享」仍违反约束）。
- R214 后两列、索引、约束都不在了；再执行一遍不报错。结束整体回滚，共享库不留任何东西。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.migration_runner import MigrationRunner
from tests.authz_world import pg_engine

pytestmark = pytest.mark.pg_only

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
V214 = (MIGRATIONS / "V214__custom_query_template_soft_delete.sql").read_text(encoding="utf-8")
R214 = (MIGRATIONS / "R214__custom_query_template_soft_delete.sql").read_text(encoding="utf-8")


async def _run_file(conn, sql: str) -> int:
    """与 MigrationRunner 执行迁移同一路径：同一个分句器（DO 块整体保留）+ 逐条 exec_driver_sql。"""
    statements = MigrationRunner._split_sql_statements(sql)
    for statement in statements:
        await conn.exec_driver_sql(statement)
    return len(statements)

#: 迁移前的表形状（V033 / V051 / V101 之后、V214 之前；只取与 V214 相关的列）
_BEFORE = """
CREATE TABLE custom_query_templates (
    id UUID PRIMARY KEY, name VARCHAR(255) NOT NULL, scope VARCHAR(16) NOT NULL DEFAULT 'private',
    created_by UUID NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(){extra}
)
"""
_OLD_SCRIPT_CHECK = ",\n    CONSTRAINT ck_custom_query_templates_scope CHECK (scope IN ('private', 'team', 'public', 'global'))"


async def _state(conn, schema: str) -> dict:
    columns = {r[0]: (r[1], r[2], r[3]) for r in (await conn.execute(text(
        "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_schema = :s AND table_name = 'custom_query_templates'"), {"s": schema})).all()}
    indexes = {r[0]: r[1] for r in (await conn.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = :s AND tablename = 'custom_query_templates'"),
        {"s": schema})).all()}
    checks = {r[0]: r[1] for r in (await conn.execute(text(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'custom_query_templates'::regclass AND contype = 'c'"))).all()}
    return {"columns": columns, "indexes": indexes, "checks": checks}


async def _insert(conn, scope: str) -> None:
    await conn.execute(text("INSERT INTO custom_query_templates (id, name, scope, created_by) VALUES (:i, '【测试】', :s, :u)"),
                       {"i": uuid.uuid4(), "s": scope, "u": uuid.uuid4()})


async def _rejects(conn, scope: str) -> bool:
    savepoint = await conn.begin_nested()
    try:
        await _insert(conn, scope)
    except IntegrityError:
        await savepoint.rollback()
        return True
    await savepoint.rollback()
    return False


@pytest.mark.parametrize("old_script_constraint", [False, True], ids=["plain", "old-4-value-constraint"])
async def test_v214_applies_twice_and_r214_rolls_back(old_script_constraint: bool):
    engine = pg_engine()
    schema = f"aql_v214_{uuid.uuid4().hex[:10]}"
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            try:
                await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                await conn.exec_driver_sql(_BEFORE.format(extra=_OLD_SCRIPT_CHECK if old_script_constraint else ""))
                await _insert(conn, "private")  # 存量行：迁移后即「未删除」

                assert await _run_file(conn, V214) == 4  # 两次加列、建索引、约束 DO 块（分句器没把 DO 块拆开）
                await _run_file(conn, V214)  # 幂等
                after = await _state(conn, schema)
                assert after["columns"]["is_deleted"][:2] == ("boolean", "NO")
                assert "false" in (after["columns"]["is_deleted"][2] or "")
                assert after["columns"]["deleted_at"][:2] == ("timestamp with time zone", "YES")
                assert "(is_deleted, updated_at DESC)" in after["indexes"]["idx_cqt_live_updated"]
                check = after["checks"]["ck_custom_query_templates_scope"]
                for scope in ("private", "team", "project", "public", "global", "personal"):
                    assert f"'{scope}'" in check, check
                    assert not await _rejects(conn, scope), scope
                assert await _rejects(conn, "shared")
                # 存量行迁移后即「未删除」（_rejects 的试插都在保存点里，插入后一律回滚）
                live = (await conn.execute(text("SELECT count(*) FROM custom_query_templates WHERE NOT is_deleted"))).scalar()
                assert live == 1

                assert await _run_file(conn, R214) == 3
                await _run_file(conn, R214)  # 幂等
                rolled = await _state(conn, schema)
                assert {"is_deleted", "deleted_at"}.isdisjoint(rolled["columns"])
                assert "idx_cqt_live_updated" not in rolled["indexes"]
                assert "ck_custom_query_templates_scope" not in rolled["checks"]
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()
