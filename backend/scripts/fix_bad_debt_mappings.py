"""可复用工具: 修复 account_mapping 中 1231 总分类→二级分项的错误映射

诊断条件:
- account_mapping.standard_account_code = '1231' (总分类)
- 客户科目名称含"应收票据/应收账款/其他应收/预付/合同资产"等关键词
- 应改成对应的二级标准科目 1231-01~05

策略:
1. 找所有 standard_account_code='1231' 且原始名带分项关键词的记录
2. 按 _match_bad_debt_sub_account 同款关键词匹配,改为对应二级
3. 同步刷新 report_line_mapping (调 ai_suggest_mappings force_refresh=True)

使用:
  python backend/scripts/fix_bad_debt_mappings.py --dry-run
  python backend/scripts/fix_bad_debt_mappings.py
  python backend/scripts/fix_bad_debt_mappings.py --project <UUID>
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.audit_platform_models import AccountMapping, ReportLineMapping
from app.models.core import Project
from app.services import mapping_service, report_line_mapping_service as rlm_svc

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 复用 mapping_service 的关键词映射表
_BAD_DEBT_KEYWORD_MAP = mapping_service._BAD_DEBT_KEYWORD_MAP


def _match_keyword_to_sub_code(name: str) -> str | None:
    """按关键词匹配返回二级标准编码 (1231-01 ~ 1231-05)"""
    if not name:
        return None
    for keywords, std_code in _BAD_DEBT_KEYWORD_MAP:
        for kw in keywords:
            if kw in name:
                return std_code
    return None


async def fix_project(project_id: UUID, db: AsyncSession, dry_run: bool = False) -> dict:
    """修单项目: 自愈 account_chart + 修 account_mapping + 清孤立 ReportLineMapping

    Returns dict: {chart_added, fixed_count, rlm_orphan_deleted, skipped}
    """
    from app.models.audit_platform_models import (
        AccountChart, AccountSource, AccountDirection, AccountCategory,
    )

    # ─── Step 1: 自愈 account_chart 增量补齐 1231-01~05 ──────────────
    chart_result = await db.execute(
        select(AccountChart.account_code).where(
            AccountChart.project_id == project_id,
            AccountChart.source == AccountSource.standard,
            AccountChart.is_deleted == False,  # noqa: E712
            AccountChart.account_code.in_(['1231-01', '1231-02', '1231-03', '1231-04', '1231-05']),
        )
    )
    existing_sub = {r[0] for r in chart_result.all()}
    sub_codes_seed = [
        ('1231-01', '坏账准备-应收票据'),
        ('1231-02', '坏账准备-应收账款'),
        ('1231-03', '坏账准备-其他应收款'),
        ('1231-04', '坏账准备-预付账款'),
        ('1231-05', '坏账准备-合同资产'),
    ]
    chart_added = 0
    for code, name in sub_codes_seed:
        if code in existing_sub:
            continue
        logger.info(f"  [补齐二级标准] {code} {name}")
        if not dry_run:
            rec = AccountChart(
                project_id=project_id,
                account_code=code,
                account_name=name,
                direction=AccountDirection.credit,
                level=2,
                category=AccountCategory.asset,
                parent_code='1231',
                source=AccountSource.standard,
            )
            db.add(rec)
        chart_added += 1
    if not dry_run and chart_added > 0:
        await db.flush()

    # ─── Step 2: 修正 account_mapping ──────────────────────────────
    result = await db.execute(
        select(AccountMapping).where(
            AccountMapping.project_id == project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
            AccountMapping.standard_account_code == '1231',
        )
    )
    records = result.scalars().all()

    fixed = 0
    skipped = []
    for rec in records:
        if not rec.original_account_name:
            continue
        sub_code = _match_keyword_to_sub_code(rec.original_account_name)
        if not sub_code:
            skipped.append(rec.original_account_code)
            logger.info(
                f"  [跳过] {rec.original_account_code} ({rec.original_account_name}) "
                f"未匹配到二级关键词,保持 1231"
            )
            continue
        old = rec.standard_account_code
        if old == sub_code:
            continue
        logger.info(
            f"  [修复] {rec.original_account_code} ({rec.original_account_name}): "
            f"{old} → {sub_code}"
        )
        if not dry_run:
            rec.standard_account_code = sub_code
        fixed += 1

    # ─── Step 3: 清理孤立的 1231 总分类 ReportLineMapping ─────────────
    # 检测条件: account_mapping 中没有任何 standard_code='1231' 但 ReportLineMapping 中还有
    # (孤立场景: ①刚 fix 完 ②历史项目本来 mapping 就没指向 1231 但 RLM 是错配)
    rlm_orphan_deleted = 0
    from app.models.audit_platform_models import ReportLineMapping, ReportLineMappingType

    still_using = await db.execute(
        select(AccountMapping).where(
            AccountMapping.project_id == project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
            AccountMapping.standard_account_code == '1231',
        ).limit(1)
    )
    if still_using.scalar_one_or_none() is None:
        orphan_result = await db.execute(
            select(ReportLineMapping).where(
                ReportLineMapping.project_id == project_id,
                ReportLineMapping.is_deleted == False,  # noqa: E712
                ReportLineMapping.standard_account_code == '1231',
                ReportLineMapping.mapping_type == ReportLineMappingType.ai_suggested,
            )
        )
        for orphan in orphan_result.scalars().all():
            logger.info(
                f"  [清理孤立 RLM] standard_code=1231 → "
                f"{orphan.report_line_code}({orphan.report_line_name})"
            )
            if not dry_run:
                orphan.is_deleted = True
            rlm_orphan_deleted += 1

    if not dry_run and (fixed > 0 or chart_added > 0 or rlm_orphan_deleted > 0):
        await db.commit()

    return {
        'chart_added': chart_added,
        'fixed_count': fixed,
        'rlm_orphan_deleted': rlm_orphan_deleted,
        'skipped': skipped,
    }


async def refresh_rlm(project_id: UUID, db: AsyncSession, dry_run: bool = False):
    """刷新 report_line_mapping (force_refresh=True)"""
    if dry_run:
        logger.info("  (干跑模式不触发 ai_suggest 刷新)")
        return
    suggestions = await rlm_svc.ai_suggest_mappings(project_id, db, force_refresh=True)
    refreshed = sum(1 for s in suggestions if s.get('action') == 'refreshed')
    created = sum(1 for s in suggestions if s.get('action') == 'created')
    logger.info(f"  report_line_mapping 刷新 {refreshed} 条 / 新建 {created} 条")


async def main():
    parser = argparse.ArgumentParser(description='修复 1231 坏账总分类→二级分项映射')
    parser.add_argument('--dry-run', action='store_true', help='干跑模式')
    parser.add_argument('--project', type=str, help='仅处理单项目 UUID')
    parser.add_argument('--skip-rlm-refresh', action='store_true', help='跳过 report_line_mapping 刷新')
    args = parser.parse_args()

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        if args.project:
            project_ids = [UUID(args.project)]
        else:
            result = await db.execute(
                select(Project.id).where(Project.is_deleted == False)  # noqa: E712
            )
            project_ids = [r[0] for r in result.all()]
            logger.info(f"将处理 {len(project_ids)} 个项目")

        total_fixed = 0
        total_chart_added = 0
        total_orphan_deleted = 0
        for pid in project_ids:
            p = (await db.execute(select(Project.client_name).where(Project.id == pid))).scalar_one_or_none()
            logger.info(f"\n--- 项目 {pid} ({p}) ---")
            try:
                stats = await fix_project(pid, db, dry_run=args.dry_run)
                logger.info(
                    f"  补齐二级标准 {stats['chart_added']} 条 / "
                    f"修 mapping {stats['fixed_count']} 条 / "
                    f"清孤立 RLM {stats['rlm_orphan_deleted']} 条"
                )
                total_fixed += stats['fixed_count']
                total_chart_added += stats['chart_added']
                total_orphan_deleted += stats['rlm_orphan_deleted']
                if stats['fixed_count'] > 0 and not args.skip_rlm_refresh:
                    await refresh_rlm(pid, db, dry_run=args.dry_run)
            except Exception as e:
                logger.error(f"  ✗ 项目 {pid} 失败: {e}")

        mode_str = '[DRY-RUN]' if args.dry_run else '[已写入]'
        logger.info(
            f"\n=== 汇总 {mode_str} 补齐 {total_chart_added} 条二级标准 / "
            f"修 {total_fixed} 条 mapping / 清 {total_orphan_deleted} 条孤立 RLM ==="
        )

    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
