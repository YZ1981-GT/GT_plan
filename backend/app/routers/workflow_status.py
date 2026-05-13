"""工作流进度端点（F18/F19/D5）

GET /api/projects/{pid}/workflow-status?year=2025
从数据层推导 6 步进度（不用 localStorage）
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(
    prefix="/api/projects/{project_id}/workflow-status",
    tags=["workflow"],
)


@router.get("")
async def get_workflow_status(
    project_id: UUID,
    year: int = Query(2025, description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从数据层推导 6 步工作流进度

    推导规则:
    1. 导入完成: tb_balance > 0
    2. 映射完成: account_mapping completion_rate >= 80%
    3. 试算表完成: trial_balance > 0
    4. 报表完成: financial_report > 0
    5. 底稿完成: working_papers > 0
    6. 附注完成: disclosure_notes > 0
    """
    pid = str(project_id)

    # 1. 导入: tb_balance 行数
    r1 = await db.execute(sa.text(
        "SELECT COUNT(*) FROM tb_balance "
        "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
    ), {"pid": pid, "yr": year})
    import_count = r1.scalar() or 0

    # 2. 映射: account_mapping 完成率（该表无 year 列）
    r2_total = await db.execute(sa.text(
        "SELECT COUNT(*) FROM account_mapping "
        "WHERE project_id = :pid AND is_deleted = false"
    ), {"pid": pid})
    mapping_total = r2_total.scalar() or 0

    r2_mapped = await db.execute(sa.text(
        "SELECT COUNT(*) FROM account_mapping "
        "WHERE project_id = :pid AND is_deleted = false "
        "AND standard_account_code IS NOT NULL AND standard_account_code != ''"
    ), {"pid": pid})
    mapping_mapped = r2_mapped.scalar() or 0
    mapping_rate = round((mapping_mapped / mapping_total * 100) if mapping_total > 0 else 0, 1)

    # 3. 试算表: trial_balance 行数
    r3 = await db.execute(sa.text(
        "SELECT COUNT(*) FROM trial_balance "
        "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
    ), {"pid": pid, "yr": year})
    tb_count = r3.scalar() or 0

    # 4. 报表: financial_report 行数
    r4 = await db.execute(sa.text(
        "SELECT COUNT(*) FROM financial_report "
        "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
    ), {"pid": pid, "yr": year})
    report_count = r4.scalar() or 0

    # 5. 底稿: working_paper 行数
    r5 = await db.execute(sa.text(
        "SELECT COUNT(*) FROM working_paper "
        "WHERE project_id = :pid AND is_deleted = false"
    ), {"pid": pid})
    wp_count = r5.scalar() or 0

    # 6. 附注: disclosure_notes 行数
    r6 = await db.execute(sa.text(
        "SELECT COUNT(*) FROM disclosure_notes "
        "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
    ), {"pid": pid, "yr": year})
    notes_count = r6.scalar() or 0

    # 推导完成状态
    import_completed = import_count > 0
    mapping_completed = mapping_rate >= 80
    tb_completed = tb_count > 0
    report_completed = report_count > 0
    wp_completed = wp_count > 0
    notes_completed = notes_count > 0

    steps = {
        "import": {"completed": import_completed, "count": import_count},
        "mapping": {"completed": mapping_completed, "rate": mapping_rate},
        "trial_balance": {"completed": tb_completed, "count": tb_count},
        "report": {"completed": report_completed, "count": report_count},
        "workpaper": {"completed": wp_completed, "count": wp_count},
        "notes": {"completed": notes_completed, "count": notes_count},
    }

    # 推导当前步骤（最后一个已完成的步骤索引）
    step_flags = [import_completed, mapping_completed, tb_completed,
                  report_completed, wp_completed, notes_completed]
    current_step = 0
    for i, flag in enumerate(step_flags):
        if flag:
            current_step = i + 1
        else:
            break

    # 推导下一步动作
    next_action = None
    if not import_completed:
        next_action = {"label": "导入账套", "route": f"/projects/{project_id}/ledger"}
    elif not mapping_completed:
        next_action = {"label": "科目映射", "route": f"/projects/{project_id}/mapping"}
    elif not tb_completed:
        next_action = {"label": "生成试算表", "route": f"/projects/{project_id}/trial-balance"}
    elif not report_completed:
        next_action = {"label": "生成报表", "route": f"/projects/{project_id}/reports"}
    elif not wp_completed:
        next_action = {"label": "生成底稿", "route": f"/projects/{project_id}/workpapers"}
    elif not notes_completed:
        next_action = {"label": "生成附注", "route": f"/projects/{project_id}/disclosure"}

    return {
        "steps": steps,
        "current_step": current_step,
        "next_action": next_action,
    }
