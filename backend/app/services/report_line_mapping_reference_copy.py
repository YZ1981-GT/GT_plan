"""报表行次映射：集团参照复制（Task 7a.4，Validates: Requirements 3.12, 3.13）。

从 ``report_line_mapping_service`` 原样拆出（该文件超行数门；spec consol-autotree-residual-closure R2.3 改的正是这两个函数）。
服务模块按原名导出，路由与测试照旧调 ``report_line_mapping_service.reference_copy`` / ``reference_copy_from_project``。
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart,
    AccountMapping,
    AccountSource,
    ReportLineMapping,
    ReportLineMappingType,
)
from app.models.audit_platform_schemas import ReferenceCopyResult
from app.models.core import Project


async def reference_copy(
    source_company_code: str,
    target_project_id: UUID,
    db: AsyncSession,
    *,
    readable_project_ids: set[UUID] | None,
) -> ReferenceCopyResult:
    """按来源企业名称，从同集团企业复制已确认的报表行次映射。

    Validates: Requirements 3.12, 3.13

    - ``readable_project_ids``：可作来源的项目，由调用方按当前用户算（``deps.readable_project_ids``，与项目读门禁
      同一口径；``None`` = 不限，只给 admin）。必须显式传入：漏传等于不筛。
    - 名称对不上任何可读项目即 ``source_found=False``、一条不复制。原先还会「随便找一个有已确认映射的其他项目」
      来复制 —— 来源与用户输入无关，还可能是用户无权读的项目（spec consol-autotree-residual-closure R2.3）。
    """
    # 来源：客户名称相同、可读、未删除、不是本项目，取最新建的那个。
    # 名称比 ``projects.client_name``（建项目 / 改基本信息时由向导同步写入）。原先读
    # ``wizard_state["basic_info"]["data"]``，而向导实际存在 ``wizard_state["steps"]["basic_info"]["data"]``
    # —— 恒取不到，名称从来没对上过，参照复制一直是靠上面说的「随便找一个」在出结果。
    query = select(Project.id).where(
        Project.is_deleted == False,  # noqa: E712
        Project.id != target_project_id,
        Project.client_name == source_company_code,
    )
    if readable_project_ids is not None:
        query = query.where(Project.id.in_(list(readable_project_ids)))
    source_id = (await db.execute(query.order_by(Project.created_at.desc()).limit(1))).scalar_one_or_none()
    if source_id is None:
        return ReferenceCopyResult(copied_count=0, unmatched_accounts=[], source_found=False)
    return await reference_copy_from_project(source_id, target_project_id, db)


async def reference_copy_from_project(
    source_project_id: UUID,
    target_project_id: UUID,
    db: AsyncSession,
) -> ReferenceCopyResult:
    """从指定来源项目复制已确认的报表行次映射（调用方先校验当前用户能读来源项目）。

    来源项目不存在或已删除 ⇒ ``source_found=False``。
    """
    source = await db.get(Project, source_project_id)
    if source is None or source.is_deleted or source_project_id == target_project_id:
        return ReferenceCopyResult(copied_count=0, unmatched_accounts=[], source_found=False)

    # 获取源项目已确认映射
    source_result = await db.execute(
        select(ReportLineMapping).where(
            ReportLineMapping.project_id == source_project_id,
            ReportLineMapping.is_confirmed == True,  # noqa: E712
            ReportLineMapping.is_deleted == False,  # noqa: E712
        )
    )
    source_mappings = source_result.scalars().all()

    if not source_mappings:
        return ReferenceCopyResult(copied_count=0, unmatched_accounts=[])

    # 获取目标项目的标准科目编码集合
    target_std_result = await db.execute(
        select(AccountChart.account_code).where(
            AccountChart.project_id == target_project_id,
            AccountChart.source == AccountSource.standard,
            AccountChart.is_deleted == False,  # noqa: E712
        )
    )
    target_std_codes = {row[0] for row in target_std_result.all()}

    # 也包含已映射的标准科目
    target_mapped_result = await db.execute(
        select(AccountMapping.standard_account_code).where(
            AccountMapping.project_id == target_project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
        ).distinct()
    )
    target_std_codes.update(row[0] for row in target_mapped_result.all())

    copied_count = 0
    unmatched: list[str] = []

    for src in source_mappings:
        if src.standard_account_code not in target_std_codes:
            unmatched.append(src.standard_account_code)
            continue

        # 检查目标项目是否已有该映射
        existing = await db.execute(
            select(ReportLineMapping).where(
                ReportLineMapping.project_id == target_project_id,
                ReportLineMapping.standard_account_code == src.standard_account_code,
                ReportLineMapping.report_type == src.report_type,
                ReportLineMapping.is_deleted == False,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none():
            continue

        new_mapping = ReportLineMapping(
            project_id=target_project_id,
            standard_account_code=src.standard_account_code,
            report_type=src.report_type,
            report_line_code=src.report_line_code,
            report_line_name=src.report_line_name,
            report_line_level=src.report_line_level,
            parent_line_code=src.parent_line_code,
            mapping_type=ReportLineMappingType.reference_copied,
            is_confirmed=False,
        )
        db.add(new_mapping)
        copied_count += 1

    await db.flush()
    await db.commit()

    return ReferenceCopyResult(
        copied_count=copied_count,
        unmatched_accounts=list(set(unmatched)),
    )
