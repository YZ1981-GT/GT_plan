"""E2E 种子项目创建脚本。

用途：为 Playwright E2E 测试创建最小数据集项目，确保底稿路由可达。
运行：python scripts/e2e/ensure_e2e_project.py

创建内容：
1. 一个测试项目（如已存在则跳过）
2. 为 D~S 各循环生成至少 1 个 workpaper 记录（确保路由不 404）
3. 插入最小 trial_balance 数据（确保审定表/程序表有数据展示）

环境要求：
- 后端 PG 数据库已启动
- .env 已配置 DATABASE_URL
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID

# 将 backend 加入 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))


E2E_PROJECT_ID = UUID("df5b8403-1cfe-4784-8b43-1b7b5e0c2e1a")
E2E_PROJECT_NAME = "E2E测试项目_底稿冒烟"
E2E_CLIENT_NAME = "E2E测试公司"

# 每个循环至少需要的 wp_code（用于验证路由不 404）
SMOKE_WP_CODES = [
    # D~N 各一个程序表 + 一个审定表
    "D1A", "D1-1",
    "E1A", "E1-1",
    "F1A", "F1-1",
    "G1A", "G7-1",
    "H1A", "H1-1",
    "I1A", "I1-1",
    "J1A", "J1-1",
    "K1A", "K1-1",
    "L1A", "L1-1",
    "M2A", "M6-1",
    "N1A", "N5-1",
    # S 类代表
    "S1", "S14", "S15", "S32-1", "S34-0",
]


async def main():
    """创建 E2E 种子项目。"""
    from app.core.database import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy import text

    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

    async with session_factory() as session:
        # 1. 检查项目是否已存在
        result = await session.execute(
            text("SELECT id FROM projects WHERE id = :pid"),
            {"pid": str(E2E_PROJECT_ID)},
        )
        if result.scalar():
            print(f"✓ E2E 项目已存在: {E2E_PROJECT_ID}")
        else:
            await session.execute(
                text("""
                    INSERT INTO projects (id, name, client_name, audit_period_start, audit_period_end, status)
                    VALUES (:pid, :name, :client, '2025-01-01', '2025-12-31', 'in_progress')
                """),
                {
                    "pid": str(E2E_PROJECT_ID),
                    "name": E2E_PROJECT_NAME,
                    "client": E2E_CLIENT_NAME,
                },
            )
            await session.commit()
            print(f"✓ 创建 E2E 项目: {E2E_PROJECT_ID}")

        # 2. 为每个 wp_code 生成 workpaper 记录
        for wp_code in SMOKE_WP_CODES:
            result = await session.execute(
                text("""
                    SELECT COUNT(*) FROM wp_index wi
                    JOIN working_papers wp ON wp.wp_index_id = wi.id
                    WHERE wi.wp_code = :code AND wp.project_id = :pid
                """),
                {"code": wp_code, "pid": str(E2E_PROJECT_ID)},
            )
            if result.scalar() > 0:
                continue
            # 先确保 wp_index 存在
            idx_result = await session.execute(
                text("SELECT id FROM wp_index WHERE wp_code = :code LIMIT 1"),
                {"code": wp_code},
            )
            idx_id = idx_result.scalar()
            if not idx_id:
                print(f"  ⚠️ wp_index 无 {wp_code}，跳过")
                continue
            await session.execute(
                text("""
                    INSERT INTO working_papers (project_id, wp_index_id, status, is_deleted)
                    VALUES (:pid, :idx, 'draft', false)
                """),
                {"pid": str(E2E_PROJECT_ID), "idx": str(idx_id)},
            )
            print(f"  + 生成 workpaper: {wp_code}")

        await session.commit()
        print(f"\n✓ E2E 种子数据就绪，共 {len(SMOKE_WP_CODES)} 个冒烟底稿")


if __name__ == "__main__":
    asyncio.run(main())
