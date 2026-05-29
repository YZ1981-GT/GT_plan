"""检查 parsed_data 列的存储大小分布

使用方式：python scripts/check_parsed_data_size.py

依赖：需要能连接到 PostgreSQL 数据库（读取 DATABASE_URL 环境变量或 .env 配置）

输出：
  1. Top 20 最大的 parsed_data 记录（wp_code + 大小）
  2. 大小分布统计（按 bucket 分组）
  3. 总体统计（总数/平均/中位数/最大）
"""

import asyncio
import os
import sys
from pathlib import Path

# 确保可以 import app 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main():
    """执行 parsed_data 大小检查"""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import settings

    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        print("=" * 60)
        print("parsed_data 列存储大小分析")
        print("=" * 60)

        # 1. Top 20 最大记录
        print("\n📊 Top 20 最大的 parsed_data 记录：")
        print("-" * 60)
        result = await conn.execute(text("""
            SELECT
                wi.wp_code,
                pg_column_size(wp.parsed_data) AS raw_bytes,
                pg_size_pretty(pg_column_size(wp.parsed_data)::bigint) AS human_size
            FROM working_paper wp
            JOIN wp_index wi ON wp.wp_index_id = wi.id
            WHERE wp.parsed_data IS NOT NULL
            ORDER BY pg_column_size(wp.parsed_data) DESC
            LIMIT 20
        """))
        rows = result.fetchall()
        if rows:
            print(f"{'wp_code':<20} {'raw_bytes':>12} {'human_size':>12}")
            print(f"{'─' * 20} {'─' * 12} {'─' * 12}")
            for row in rows:
                print(f"{row.wp_code:<20} {row.raw_bytes:>12,} {row.human_size:>12}")
        else:
            print("  (无数据)")

        # 2. 大小分布统计
        print("\n📈 大小分布统计：")
        print("-" * 60)
        result = await conn.execute(text("""
            SELECT
                CASE
                    WHEN pg_column_size(parsed_data) < 1024 THEN '< 1 KB'
                    WHEN pg_column_size(parsed_data) < 10240 THEN '1-10 KB'
                    WHEN pg_column_size(parsed_data) < 102400 THEN '10-100 KB'
                    WHEN pg_column_size(parsed_data) < 1048576 THEN '100 KB - 1 MB'
                    ELSE '> 1 MB'
                END AS size_bucket,
                COUNT(*) AS count,
                pg_size_pretty(AVG(pg_column_size(parsed_data))::bigint) AS avg_size
            FROM working_paper
            WHERE parsed_data IS NOT NULL
            GROUP BY 1
            ORDER BY MIN(pg_column_size(parsed_data))
        """))
        rows = result.fetchall()
        if rows:
            print(f"{'bucket':<20} {'count':>8} {'avg_size':>12}")
            print(f"{'─' * 20} {'─' * 8} {'─' * 12}")
            for row in rows:
                print(f"{row.size_bucket:<20} {row.count:>8} {row.avg_size:>12}")
        else:
            print("  (无数据)")

        # 3. 总体统计
        print("\n📋 总体统计：")
        print("-" * 60)
        result = await conn.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(parsed_data) AS non_null,
                pg_size_pretty(AVG(pg_column_size(parsed_data))::bigint) AS avg_size,
                pg_size_pretty(MAX(pg_column_size(parsed_data))::bigint) AS max_size,
                pg_size_pretty(SUM(pg_column_size(parsed_data))::bigint) AS total_size
            FROM working_paper
        """))
        row = result.fetchone()
        if row:
            print(f"  总底稿数：{row.total}")
            print(f"  含 parsed_data：{row.non_null}")
            print(f"  平均大小：{row.avg_size}")
            print(f"  最大大小：{row.max_size}")
            print(f"  总占用：{row.total_size}")

        # 4. TOAST 压缩状态
        print("\n🗜️  TOAST 压缩状态：")
        print("-" * 60)
        result = await conn.execute(text("""
            SELECT
                a.attname AS column_name,
                CASE a.attstorage
                    WHEN 'p' THEN 'plain (不压缩)'
                    WHEN 'e' THEN 'external (不压缩，外部存储)'
                    WHEN 'm' THEN 'main (压缩，尽量不外部存储)'
                    WHEN 'x' THEN 'extended (压缩 + 外部存储)'
                END AS storage_strategy
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            WHERE c.relname = 'working_paper'
              AND a.attname = 'parsed_data'
        """))
        row = result.fetchone()
        if row:
            print(f"  列名：{row.column_name}")
            print(f"  存储策略：{row.storage_strategy}")
        else:
            print("  (未找到 parsed_data 列)")

    await engine.dispose()
    print("\n✅ 检查完成")


if __name__ == "__main__":
    asyncio.run(main())
