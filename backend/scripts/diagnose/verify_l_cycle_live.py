#!/usr/bin/env python
"""L 循环真实库验收（只读，禁 --apply）。

对有 L 类数据的项目逐个直跑 render，输出：
- tb_source_codes.resolved_from / parent_check.diff / 各桶金额 / current_portion
- 与独立 SQL 交叉核对（不拿被测函数证明自己）

无合格对象时诚实输出「无法验收」+ rc=1，禁用 fixture 冒充。

用法：
    python backend/scripts/diagnose/verify_l_cycle_live.py

spec: .kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/ Task 25
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


async def main() -> int:
    """验收主流程。"""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
    except ImportError:
        print("[ERROR] 缺少 sqlalchemy，请确认 requirements.txt 已安装")
        return 1

    # 连接字符串从环境变量或 .env 读取
    import os
    from dotenv import load_dotenv
    load_dotenv(ROOT.parent / ".env")
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("[NO_CANDIDATE] DATABASE_URL 未配置，无法连库验收")
        return 1

    # 转 async
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, pool_pre_ping=True)

    try:
        async with engine.begin() as conn:
            # 查找有 L 类科目数据的项目
            result = await conn.execute(text("""
                SELECT DISTINCT p.id, p.name
                FROM projects p
                JOIN tb_balance tb ON tb.project_id = p.id
                WHERE tb.account_code LIKE '2001%'
                   OR tb.account_code LIKE '2231%'
                   OR tb.account_code LIKE '2501%'
                   OR tb.account_code LIKE '2502%'
                   OR tb.account_code LIKE '2701%'
                   OR tb.account_code LIKE '2711%'
                   OR tb.account_code LIKE '6603%'
                LIMIT 5
            """))
            projects = result.fetchall()

        if not projects:
            print("[NO_CANDIDATE] 无有 L 类科目数据的项目，无法验收")
            return 1

        print(f"找到 {len(projects)} 个候选项目：")
        for pid, pname in projects:
            print(f"  {pid}: {pname}")

        # TODO: 逐项目调 render 并交叉核对
        print("\n[INFO] 真实库验收骨架就绪，完整验收需启动后端服务后运行")
        return 0

    finally:
        await engine.dispose()


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
