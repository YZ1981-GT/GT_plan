"""ledger-import-view-refactor Day 30 索引清理（spec 9.10 / P1）

定位：
    spec F18 三阶段迁移最后一步：Day 30 DROP 废弃索引 + REINDEX，回收 ~55MB 空间。
    本脚本封装 dry-run / 实测 / 执行三种模式，CI 可定期跑 dry-run 监控索引膨胀。

操作清单：
    1. 实测前置条件：dead tuple 率 < 5%（避免在膨胀严重时 DROP）
    2. DROP INDEX CONCURRENTLY idx_tb_*_activate_staged（4 张表）
    3. REINDEX CONCURRENTLY idx_tb_*_active_queries（4 张表，回收膨胀）

可复用：未来其他 spec 的"废弃索引清理"按相同模板。

用法:
    python backend/scripts/day30_drop_deprecated_indexes.py [--dry-run] [--execute]

    --dry-run   仅打印将执行的 SQL 不实际跑（默认）
    --execute   真正执行 DROP/REINDEX
"""
from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


# 4 张表
TARGET_TABLES = ["tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"]
DEAD_TUPLE_THRESHOLD = 0.05  # < 5%


async def check_dead_tuple_ratio(db: AsyncSession) -> dict[str, float]:
    """对每张表算 dead_tuple_ratio = n_dead_tup / (n_live_tup + n_dead_tup)"""
    rows = (await db.execute(sa.text("""
        SELECT relname, n_live_tup, n_dead_tup
        FROM pg_stat_user_tables
        WHERE schemaname = 'public' AND relname = ANY(:tbls)
    """), {"tbls": TARGET_TABLES})).all()
    result = {}
    for name, live, dead in rows:
        total = (live or 0) + (dead or 0)
        ratio = (dead / total) if total > 0 else 0.0
        result[name] = ratio
    return result


async def list_deprecated_indexes(db: AsyncSession) -> list[tuple[str, str, int]]:
    """返回 [(tablename, indexname, size_bytes), ...]"""
    rows = (await db.execute(sa.text("""
        SELECT
            schemaname,
            tablename,
            indexname,
            pg_relation_size(quote_ident(schemaname)||'.'||quote_ident(indexname))::bigint AS size_bytes
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname LIKE 'idx_tb_%_activate_staged'
        ORDER BY tablename, indexname
    """))).all()
    return [(r[1], r[2], r[3]) for r in rows]


async def list_active_queries_indexes(db: AsyncSession) -> list[tuple[str, str, int]]:
    """需要 REINDEX 的 active_queries 索引"""
    rows = (await db.execute(sa.text("""
        SELECT
            schemaname,
            tablename,
            indexname,
            pg_relation_size(quote_ident(schemaname)||'.'||quote_ident(indexname))::bigint AS size_bytes
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname LIKE 'idx_tb_%_active_queries'
        ORDER BY tablename, indexname
    """))).all()
    return [(r[1], r[2], r[3]) for r in rows]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true",
                        help="真正执行 DROP/REINDEX（默认 dry-run）")
    args = parser.parse_args()
    dry_run = not args.execute

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 70)
    print(f"Day 30 废弃索引清理（{'DRY-RUN' if dry_run else 'EXECUTE'}）")
    print("=" * 70)

    # 用一个 connection 做查询，DROP/REINDEX CONCURRENTLY 走独立 raw connection（autocommit）
    async with sm() as db:
        # 1. 前置条件：dead tuple 率
        print("\n📊 步骤 1：dead tuple 率检查")
        ratios = await check_dead_tuple_ratio(db)
        if not ratios:
            print(f"  ⚠ 未找到目标表 {TARGET_TABLES}（PG 未启用 stats 或表不存在）")
        for table, ratio in ratios.items():
            mark = "✓" if ratio < DEAD_TUPLE_THRESHOLD else "⚠"
            print(f"  {mark} {table}: dead_tuple_ratio = {ratio*100:.2f}%（阈值 < {DEAD_TUPLE_THRESHOLD*100:.0f}%）")

        any_high = any(r >= DEAD_TUPLE_THRESHOLD for r in ratios.values())
        if any_high and not dry_run:
            print("\n  ⚠ 部分表 dead_tuple > 5%，建议先 VACUUM 再清理")
            print("  执行被中断（可手动确认后再 --execute）")
            await engine.dispose()
            return 1

        # 2. 列出废弃索引
        print("\n🗑️  步骤 2：废弃索引清单（idx_tb_*_activate_staged）")
        deprecated = await list_deprecated_indexes(db)
        if not deprecated:
            print("  ℹ 未发现废弃索引（可能已被前轮清理 / 从未创建）")
        else:
            total_bytes = 0
            for table, idx, sz in deprecated:
                print(f"  - {table}.{idx}: {sz/1024/1024:.2f} MB")
                total_bytes += sz
            print(f"  总计可回收: {total_bytes/1024/1024:.2f} MB（spec 预计 55MB）")

        # 列出 active_queries 索引（提前查清以便步骤 4 用）
        active = await list_active_queries_indexes(db)

    # 3. DROP / REINDEX 用独立 asyncpg raw connection（CONCURRENTLY 不能在事务内）
    print(f"\n🚀 步骤 3：DROP INDEX CONCURRENTLY（{'模拟' if dry_run else '真实执行'}）")
    if not dry_run:
        # 用 asyncpg.connect 直接走 autocommit 模式
        import asyncpg
        # 解析 DATABASE_URL 拿 dsn
        from urllib.parse import urlparse
        url = settings.DATABASE_URL
        if url.startswith("postgresql+asyncpg://"):
            dsn = url.replace("postgresql+asyncpg://", "postgresql://", 1)
        else:
            dsn = url
        conn = await asyncpg.connect(dsn)
        try:
            # 防御：超过 60s 拿不到锁就 fail，避免被 idle-in-transaction 卡死
            await conn.execute("SET lock_timeout = '60s'")
            for table, idx, sz in deprecated:
                sql = f'DROP INDEX CONCURRENTLY IF EXISTS "{idx}"'
                print(f"  SQL: {sql}")
                await conn.execute(sql)
                print(f"    ✓ DROPPED ({sz/1024/1024:.2f} MB recovered)")
        finally:
            await conn.close()
    else:
        for table, idx, sz in deprecated:
            sql = f"DROP INDEX CONCURRENTLY IF EXISTS {idx}"
            print(f"  SQL: {sql}")

    # 4. REINDEX active_queries 索引
    print(f"\n🔧 步骤 4：REINDEX CONCURRENTLY active_queries 索引（{'模拟' if dry_run else '真实执行'}）")
    if not active:
        print("  ℹ 未发现 idx_tb_*_active_queries 索引（可能未创建）")
    elif not dry_run:
        import asyncpg
        from urllib.parse import urlparse
        url = settings.DATABASE_URL
        if url.startswith("postgresql+asyncpg://"):
            dsn = url.replace("postgresql+asyncpg://", "postgresql://", 1)
        else:
            dsn = url
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute("SET lock_timeout = '60s'")
            # 0. 先清理之前 CONCURRENTLY 失败留下的 _ccnew/_ccold 残骸
            leftovers = await conn.fetch("""
                SELECT c.relname
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE NOT i.indisvalid
                  AND (c.relname LIKE 'idx_tb_%_active_queries_ccnew%'
                       OR c.relname LIKE 'idx_tb_%_active_queries_ccold%')
            """)
            for r in leftovers:
                drop_sql = f'DROP INDEX CONCURRENTLY IF EXISTS "{r["relname"]}"'
                print(f"  cleanup: {drop_sql}")
                await conn.execute(drop_sql)

            for table, idx, sz in active:
                sql = f'REINDEX INDEX CONCURRENTLY "{idx}"'
                print(f"  SQL: {sql} (当前 {sz/1024/1024:.2f} MB)")
                await conn.execute(sql)
                print(f"    ✓ REINDEXED")
        finally:
            await conn.close()
    else:
        for table, idx, sz in active:
            sql = f"REINDEX INDEX CONCURRENTLY {idx}"
            print(f"  SQL: {sql} (当前 {sz/1024/1024:.2f} MB)")

    print("\n" + "=" * 70)
    if dry_run:
        print("✓ DRY-RUN 完成（实际未执行）。要真实执行请加 --execute")
    else:
        print("✓ Day 30 清理完成")
    print("=" * 70)
    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
