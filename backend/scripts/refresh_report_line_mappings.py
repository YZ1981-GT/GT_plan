"""刷新所有项目的 report_line_mapping (老 BSXXX/ISXXX → 新 BS-XXX/IS-XXX)

可复用工具(非一次性):每次 seed 升级后都可以批量刷新所有项目的 ai_suggested 记录.

策略:
- 仅刷新 mapping_type='ai_suggested' 且 is_confirmed=false 的记录
- 保留 manual / reference_copied / 已确认 (即使是老格式也不动,因为是用户手工选的)
- 按项目 (template_type, report_scope) 派生 applicable_standard 加载对应 seed
- 干跑模式 (--dry-run): 只打印不写库

使用方式:
  python backend/scripts/refresh_report_line_mappings.py --dry-run  # 干跑预览
  python backend/scripts/refresh_report_line_mappings.py            # 真实执行
  python backend/scripts/refresh_report_line_mappings.py --project <UUID>  # 仅刷新单项目
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.audit_platform_models import (
    ReportLineMapping,
    ReportLineMappingType,
    ReportType,
)
from app.models.core import Project
from app.services import report_line_mapping_service as svc

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


async def refresh_project(
    project_id: UUID, db: AsyncSession, dry_run: bool = False, force: bool = False
) -> tuple[int, int, int]:
    """刷新单个项目的 report_line_mapping.

    Returns: (refreshed_count, unchanged_count, untouched_protected_count)

    Args:
        force: True 时刷新所有 ai_suggested 记录(包括已确认的);
               False 时只刷新 ai_suggested + is_confirmed=False
    """
    # 派生 applicable_standard
    applicable_standard = await svc._get_project_applicable_standard(project_id, db)

    # 取所有 ai_suggested 记录(force 模式包括已确认的)
    query = select(ReportLineMapping).where(
        ReportLineMapping.project_id == project_id,
        ReportLineMapping.is_deleted == False,  # noqa: E712
        ReportLineMapping.mapping_type == ReportLineMappingType.ai_suggested,
    )
    if not force:
        query = query.where(ReportLineMapping.is_confirmed == False)  # noqa: E712
    result = await db.execute(query)
    records = result.scalars().all()

    refreshed = 0
    unchanged = 0
    not_in_seed = 0

    for rec in records:
        seed_hit = svc._lookup_report_line_from_seed(rec.standard_account_code, applicable_standard)
        if seed_hit is None:
            not_in_seed += 1
            continue

        line_code, line_name, _ = seed_hit
        if rec.report_line_code == line_code and rec.report_line_name == line_name:
            unchanged += 1
            continue

        old = f"{rec.report_line_code} ({rec.report_line_name})"
        new = f"{line_code} ({line_name})"
        logger.info(
            f"  [{rec.standard_account_code}] {old} → {new}"
        )
        if not dry_run:
            rec.report_line_code = line_code
            rec.report_line_name = line_name
            rec.report_line_level = 1
            rec.parent_line_code = None
        refreshed += 1

    # 还要列出"已确认/manual"的老格式记录,但不刷新(给运维感知)
    protected_old_format_result = await db.execute(
        select(ReportLineMapping).where(
            ReportLineMapping.project_id == project_id,
            ReportLineMapping.is_deleted == False,  # noqa: E712,
            ~ReportLineMapping.report_line_code.like('BS-%'),
            ~ReportLineMapping.report_line_code.like('IS-%'),
        )
    )
    protected = protected_old_format_result.scalars().all()
    protected_count = len(protected)
    if protected_count > 0:
        logger.warning(
            f"  ⚠ {protected_count} 条 manual/确认 老格式记录未刷新(需手工处理)"
        )

    if not dry_run:
        await db.commit()

    return refreshed, unchanged, not_in_seed


async def main():
    parser = argparse.ArgumentParser(description='刷新 report_line_mapping')
    parser.add_argument('--dry-run', action='store_true', help='干跑模式')
    parser.add_argument('--project', type=str, help='仅刷新单项目 UUID')
    parser.add_argument('--force', action='store_true', help='强制刷新所有 ai_suggested 记录(含已确认的,用于格式升级)')
    args = parser.parse_args()

    # 用 SQLAlchemy async engine 连接
    db_url = settings.DATABASE_URL
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        # 取项目列表
        if args.project:
            project_ids = [UUID(args.project)]
        else:
            result = await db.execute(
                select(Project.id, Project.client_name).where(Project.is_deleted == False)  # noqa: E712
            )
            rows = result.all()
            project_ids = [r[0] for r in rows]
            logger.info(f"将刷新 {len(project_ids)} 个项目")

        total_refreshed = 0
        total_unchanged = 0
        total_not_in_seed = 0

        for pid in project_ids:
            # 取项目名
            p = (await db.execute(select(Project.client_name).where(Project.id == pid))).scalar_one_or_none()
            logger.info(f"\n--- 项目 {pid} ({p}) ---")
            try:
                r, u, n = await refresh_project(pid, db, dry_run=args.dry_run, force=args.force)
                logger.info(f"  刷新 {r} 条 / 无需更新 {u} 条 / seed 中无定义 {n} 条")
                total_refreshed += r
                total_unchanged += u
                total_not_in_seed += n
            except Exception as e:
                logger.error(f"  ✗ 项目 {pid} 失败: {e}")

        mode_str = '[DRY-RUN]' if args.dry_run else '[已写入]'
        logger.info(f"\n=== 汇总 {mode_str} ===")
        logger.info(f"  总刷新: {total_refreshed}")
        logger.info(f"  无需更新: {total_unchanged}")
        logger.info(f"  seed 无定义(待人工处理): {total_not_in_seed}")

    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
