"""一次性诊断脚本：对 df5b8403 实跑现状基线

用法: ..\.venv\Scripts\python.exe scripts/_baseline_wp_pipeline.py

待环境验证：需要 PG 容器 audit-postgres 运行中。
本脚本用于固化修复前的真实状态，作为诊断驱动的起点。

Feature: wp-generation-pipeline, Task 1
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

PROJECT_ID = "df5b8403-0000-0000-0000-000000000000"  # 首汽租车_2025 前缀
YEAR = 2025


async def run_baseline():
    """执行基线诊断"""
    import sqlalchemy as sa
    from app.core.database import get_async_session_factory
    from app.models.workpaper_models import WpIndex, WorkingPaper
    from app.models.audit_platform_models import TrialBalance, TbBalance

    print("=" * 60)
    print("  底稿生成管线基线诊断 - df5b8403 首汽租车_2025")
    print("=" * 60)

    session_factory = get_async_session_factory()
    async with session_factory() as db:
        # 查找真实 project_id（前缀匹配）
        from app.models.core import Project
        proj_result = await db.execute(
            sa.select(Project).where(
                sa.cast(Project.id, sa.String).like("df5b8403%")
            )
        )
        project = proj_result.scalar_one_or_none()
        if not project:
            print("[ERROR] 未找到 df5b8403 开头的项目")
            return
        pid = project.id
        print(f"\n  项目: {project.name} (id={pid})")

        # 1. 推荐链
        print("\n[1] 推荐链...")
        try:
            from app.services.wp_mapping_service import WpMappingService
            svc = WpMappingService(db)
            recommended = await svc.recommend_workpapers(pid, YEAR, "standalone")
            print(f"  推荐 wp_codes 数量: {len(recommended)}")
        except Exception as e:
            print(f"  推荐失败: {e}")

        # 2. working_paper / wp_index 计数
        print("\n[2] 当前 DB 计数...")
        wp_count = (await db.execute(
            sa.select(sa.func.count()).select_from(WorkingPaper).where(
                WorkingPaper.project_id == pid
            )
        )).scalar_one() or 0
        idx_count = (await db.execute(
            sa.select(sa.func.count()).select_from(WpIndex).where(
                WpIndex.project_id == pid
            )
        )).scalar_one() or 0
        print(f"  working_paper: {wp_count}")
        print(f"  wp_index: {idx_count}")

        # 3. parsed_data 抽查
        print("\n[3] parsed_data 抽查...")
        if wp_count > 0:
            null_pd = (await db.execute(
                sa.select(sa.func.count()).select_from(WorkingPaper).where(
                    WorkingPaper.project_id == pid,
                    WorkingPaper.parsed_data == sa.null(),
                )
            )).scalar_one() or 0
            print(f"  parsed_data 为 NULL 的记录: {null_pd}/{wp_count}")
        else:
            print(f"  无 working_paper 记录（预期当前为 0）")

        # 4. bound_dataset_id 抽查
        print("\n[4] bound_dataset_id 抽查...")
        if wp_count > 0:
            null_bd = (await db.execute(
                sa.select(sa.func.count()).select_from(WorkingPaper).where(
                    WorkingPaper.project_id == pid,
                    WorkingPaper.bound_dataset_id == sa.null(),
                )
            )).scalar_one() or 0
            print(f"  bound_dataset_id 为 NULL 的记录: {null_bd}/{wp_count}")
        else:
            print(f"  无 working_paper 记录")

        # 5. trial_balance 检查
        print("\n[5] trial_balance 数据源...")
        tb_count = (await db.execute(
            sa.select(sa.func.count()).select_from(TrialBalance).where(
                TrialBalance.project_id == pid,
                TrialBalance.year == YEAR,
            )
        )).scalar_one() or 0
        print(f"  trial_balance 行数: {tb_count}")

        if tb_count > 0:
            no_sac = (await db.execute(
                sa.select(sa.func.count()).select_from(TrialBalance).where(
                    TrialBalance.project_id == pid,
                    TrialBalance.year == YEAR,
                    sa.or_(
                        TrialBalance.standard_account_code == sa.null(),
                        TrialBalance.standard_account_code == "",
                    ),
                )
            )).scalar_one() or 0
            print(f"  缺 standard_account_code 的记录: {no_sac}/{tb_count}")

        # 6. tb_balance 对比
        print("\n[6] tb_balance 原始数据...")
        tbb_count = (await db.execute(
            sa.select(sa.func.count()).select_from(TbBalance).where(
                TbBalance.project_id == pid,
            )
        )).scalar_one() or 0
        print(f"  tb_balance 行数: {tbb_count}")

        print("\n" + "=" * 60)
        print("  基线诊断完成")
        print("  注：本脚本为一次性诊断工具（_ 前缀），修复验证后删除")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_baseline())
