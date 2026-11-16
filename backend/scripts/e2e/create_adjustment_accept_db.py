"""建/重建调整模块验收库（结构克隆 + V235 + 非 superuser 探针角色）。

为什么需要专用库
----------------
``tests/test_adjustment_concurrency_and_rls_pg.py`` 要做两件共享库做不到的事：

1. **真双事务并发**（两个独立连接同时持锁、同时提交）—— 单连接回滚事务夹具做不到；
2. **真实 RLS 隔离**（非 superuser 角色受 ``project_isolation`` 策略约束）——
   应用连的 ``postgres`` 是 ``rolsuper + rolbypassrls``，FORCE RLS 对它不生效，
   所以元数据断言证明不了隔离。

因此这两类验收只在**专用验收库**里跑，共享库 ``audit_platform`` 只被只读引用
（``CREATE TABLE ... (LIKE public.x INCLUDING ALL)`` 读结构，不读业务数据）。

用法::

    # 建库（幂等：已存在则先 DROP，结构每次重建）
    python backend/scripts/e2e/create_adjustment_accept_db.py
    python backend/scripts/e2e/create_adjustment_accept_db.py --db gt_adj_accept_1115

    # 跑验收用例
    set GT_ADJ_ACCEPT_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/gt_adj_accept
    python -m pytest backend/tests/test_adjustment_concurrency_and_rls_pg.py -v

    # 用完删库
    python backend/scripts/e2e/create_adjustment_accept_db.py --drop
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
for path in (str(BACKEND), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_DB = "gt_adj_accept"
PROBE_ROLE = "gt_rls_probe"
PROBE_PASSWORD = "gt_rls_probe_pw"
MIGRATION = "V235__adjustment_review_tasks_and_group_revision.sql"


def _admin_url(host: str, port: int, user: str, password: str) -> str:
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/postgres"


def _target_url(host: str, port: int, user: str, password: str, db: str) -> str:
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


async def _drop_database(admin_url: str, db: str) -> None:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            # 先断掉残留连接，否则 DROP 会被占用的会话挡住
            await conn.execute(sa.text("""
                SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                WHERE datname = :db AND pid <> pg_backend_pid()
            """), {"db": db})
            await conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db}"'))
    finally:
        await engine.dispose()


async def build(*, db: str, admin_url: str, target_url: str,
                source_db: str, host: str, port: int,
                user: str, password: str) -> int:
    import shutil
    import subprocess

    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    print(f"[1/5] 重建库 {db}")
    await _drop_database(admin_url, db)
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.execute(sa.text(f'CREATE DATABASE "{db}"'))
    finally:
        await admin.dispose()

    target = create_async_engine(target_url, poolclass=NullPool)
    try:
        # 2. 结构克隆：pg_dump --schema-only 从共享库导出，psql 灌入验收库
        #    （不能用 `CREATE TABLE (LIKE public.x)`：LIKE 在**目标库**里解析 public，
        #     而目标库此时是空的 —— 2026-11-15 实测会误报"共享库没有表"）
        print(f"[2/5] 结构克隆 {source_db} → {db}（pg_dump --schema-only，不读业务数据）")
        pg_dump = shutil.which("pg_dump")
        psql = shutil.which("psql")
        if not (pg_dump and psql):
            # 本机没装 PG 客户端时退回 docker（本仓开发环境就是 docker 里的 audit-postgres）
            container = "audit-postgres"
            dump_cmd = [
                "docker", "exec", container,
                "pg_dump", "-U", user, "-d", source_db,
                "--schema-only", "--no-owner", "--no-privileges",
            ]
            load_cmd = ["docker", "exec", "-i", container, "psql", "-U", user, "-d", db, "-q"]
        else:
            env = {"PGPASSWORD": password}
            dump_cmd = [pg_dump, "-h", host, "-p", str(port), "-U", user, "-d", source_db,
                        "--schema-only", "--no-owner", "--no-privileges"]
            load_cmd = [psql, "-h", host, "-p", str(port), "-U", user, "-d", db, "-q"]
            import os

            os.environ.update(env)
        started = time.perf_counter()
        dump = subprocess.run(dump_cmd, capture_output=True, check=True)
        load = subprocess.run(load_cmd, input=dump.stdout, capture_output=True)
        if load.returncode != 0:
            print("[error] 灌入结构失败：")
            print(load.stderr.decode("utf-8", errors="replace")[-2000:])
            return 1
        async with target.connect() as conn:
            table_count = await conn.scalar(sa.text("""
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """))
        print(f"      {table_count} 张表，{time.perf_counter() - started:.1f}s")
        if not table_count:
            print("[error] 克隆后验收库没有表")
            return 1

        # 3. 跑 V235（建三张新表 + 约束 + RLS 策略 + 编号唯一触发器）
        print(f"[3/5] 执行 {MIGRATION}")
        from tests.pg_temp_schema import run_sql_file

        async with target.begin() as conn:
            statements = await run_sql_file(conn, BACKEND / "migrations" / MIGRATION)
        print(f"      {statements} 条语句")

        # 4. 非 superuser 探针角色（RLS 验收用；FORCE RLS 对 superuser 无效）
        print(f"[4/5] 建探针角色 {PROBE_ROLE}（NOSUPERUSER NOBYPASSRLS）")
        async with target.begin() as conn:
            await conn.exec_driver_sql(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PROBE_ROLE}') THEN
                        CREATE ROLE {PROBE_ROLE} LOGIN PASSWORD '{PROBE_PASSWORD}'
                            NOSUPERUSER NOBYPASSRLS;
                    END IF;
                END
                $$
            """)
            await conn.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO {PROBE_ROLE}')
            await conn.exec_driver_sql(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {PROBE_ROLE}'
            )
            await conn.exec_driver_sql(
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {PROBE_ROLE}'
            )

        # 5. 自检：三张表的 RLS + 策略必须齐
        print("[5/5] 自检")
        async with target.connect() as conn:
            rows = (await conn.execute(sa.text("""
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname IN ('adjustment_review_tasks',
                                    'adjustment_client_bookings',
                                    'adjustment_treatment_events')
                ORDER BY 1
            """))).all()
            policies = {row[0] for row in (await conn.execute(sa.text("""
                SELECT tablename FROM pg_policies
                WHERE schemaname = 'public' AND policyname = 'project_isolation'
            """))).all()}
        ok = True
        for row in rows:
            has_policy = row.relname in policies
            print(f"      {row.relname}: enable={row.relrowsecurity} "
                  f"force={row.relforcerowsecurity} policy={has_policy}")
            ok = ok and row.relrowsecurity and has_policy
        if len(rows) != 3 or not ok:
            print("[error] 自检失败：RLS 或策略缺失")
            return 1
    finally:
        await target.dispose()

    print()
    print("✅ 验收库就绪。运行验收用例：")
    print(f'   set GT_ADJ_ACCEPT_DB_URL={target_url}')
    print("   python -m pytest backend/tests/test_adjustment_concurrency_and_rls_pg.py -v")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="建/删调整模块验收库")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"库名（默认 {DEFAULT_DB}）")
    parser.add_argument("--source-db", default="audit_platform",
                        help="结构来源库（默认 audit_platform，只读其结构）")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="postgres")
    parser.add_argument("--drop", action="store_true", help="只删库后退出")
    args = parser.parse_args()

    admin_url = _admin_url(args.host, args.port, args.user, args.password)
    target_url = _target_url(args.host, args.port, args.user, args.password, args.db)

    if args.drop:
        await _drop_database(admin_url, args.db)
        print(f"[drop] 已删除库 {args.db}")
        return 0

    return await build(
        db=args.db, admin_url=admin_url, target_url=target_url,
        source_db=args.source_db, host=args.host, port=args.port,
        user=args.user, password=args.password,
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
