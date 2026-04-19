# -*- coding: utf-8 -*-
"""多企业大数据量扩展方案评估"""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def main():
    from app.core.database import engine
    import sqlalchemy as sa

    async with engine.begin() as conn:
        # 1. 当前索引效率评估
        print("=== 1. 索引效率（单企业 400万行） ===", flush=True)
        pid = "6687b8ce-7a83-4816-bd4a-c2d173d4b683"

        # 模拟50企业场景：当前索引是否能高效过滤
        r = await conn.execute(sa.text(f"""
            EXPLAIN (COSTS, FORMAT TEXT)
            SELECT COUNT(*) FROM tb_ledger
            WHERE project_id = '{pid}' AND year = 2025 AND is_deleted = false
        """))
        for row in r.fetchall():
            print(f"  {row[0]}", flush=True)

        # 2. 检查索引选择性
        print("\n=== 2. 索引选择性 ===", flush=True)
        for tbl in ["tb_ledger", "tb_aux_ledger"]:
            r = await conn.execute(sa.text(f"""
                SELECT
                    reltuples::bigint as est_rows,
                    pg_size_pretty(pg_relation_size('{tbl}'::regclass)) as data_size,
                    pg_size_pretty(pg_indexes_size('{tbl}'::regclass)) as index_size
                FROM pg_class WHERE relname = '{tbl}'
            """))
            row = r.fetchone()
            print(f"  {tbl}: ~{row[0]:,} 行, 数据 {row[1]}, 索引 {row[2]}", flush=True)

        # 3. 分区方案评估
        print("\n=== 3. 分区方案评估 ===", flush=True)
        print("  方案A: 按 project_id HASH 分区（固定分区数）", flush=True)
        print("    优点: 数据均匀分布，分区数固定（如16/32个）", flush=True)
        print("    缺点: 同一项目可能跨分区（HASH冲突），删除项目数据需扫描所有分区", flush=True)
        print("  方案B: 按 project_id LIST 分区（每个项目一个分区）", flush=True)
        print("    优点: 完美隔离，删除项目直接 DROP PARTITION", flush=True)
        print("    缺点: 分区数随项目增长，>1000个分区性能下降", flush=True)
        print("  方案C: 按 project_id RANGE 分区（按UUID范围分桶）", flush=True)
        print("    优点: 分区数可控，UUID天然均匀分布", flush=True)
        print("    缺点: 需要预建分区，新项目可能落在同一分区", flush=True)
        print("  ★ 推荐: 方案A（HASH 32分区）+ 归档机制", flush=True)
        print("    - 32个分区，每个分区约 50企业/32 ≈ 1.5企业的数据", flush=True)
        print("    - 查询时 PG 自动只扫描目标分区（project_id 在 WHERE 中）", flush=True)
        print("    - 归档项目数据移到冷存储表，主表保持精简", flush=True)

        # 4. 容量规划
        print("\n=== 4. 容量规划（基于和平药房数据） ===", flush=True)
        single = {
            "tb_balance": (407, 0.2),  # (行数, MB)
            "tb_aux_balance": (127618, 33),
            "tb_ledger": (1147414, 402),
            "tb_aux_ledger": (2732674, 920),
        }
        total_rows = sum(v[0] for v in single.values())
        total_mb = sum(v[1] for v in single.values())
        print(f"  单企业: {total_rows:,} 行, {total_mb:.0f} MB", flush=True)
        for n in [10, 50, 100, 200]:
            print(f"  {n} 企业: {total_rows*n:,} 行, {total_mb*n/1024:.1f} GB", flush=True)

asyncio.run(main())
