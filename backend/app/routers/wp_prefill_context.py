"""项目信息预填充上下文（供B/C/A/S类底稿使用）— P4"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.deps import get_db, get_current_user

router = APIRouter(prefix="/api/projects", tags=["workpaper-prefill"])


@router.get("/{project_id}/workpapers/prefill-context")
async def get_prefill_context(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取项目级预填充上下文（公司名/年度/合伙人/重要性等）"""

    # Get project info
    # 注：projects 表无 year 列，年度从 audit_period_end 提取（系统标准做法）。
    result = await db.execute(
        text("""
            SELECT name, EXTRACT(YEAR FROM audit_period_end)::int AS year,
                   template_type, report_scope, wizard_state
            FROM projects WHERE id = :pid
        """),
        {"pid": project_id},
    )
    project = result.fetchone()

    if not project:
        return {"context": {}, "message": "项目未找到"}

    # Get materiality from materiality table
    # 注：materiality 表列名为 overall_materiality（非 materiality_level）。
    mat_result = await db.execute(
        text("""
            SELECT overall_materiality, performance_materiality, trivial_threshold
            FROM materiality WHERE project_id = :pid
            ORDER BY created_at DESC LIMIT 1
        """),
        {"pid": project_id},
    )
    mat_row = mat_result.fetchone()

    # Get partner info
    # 注：project_assignments.staff_id → staff_members.id，姓名在 staff_members.name
    #     （非 users.display_name，该列不存在）。
    partner_result = await db.execute(
        text("""
            SELECT s.name FROM project_assignments pa
            JOIN staff_members s ON s.id = pa.staff_id
            WHERE pa.project_id = :pid AND pa.role = 'partner'
            LIMIT 1
        """),
        {"pid": project_id},
    )
    partner_row = partner_result.fetchone()

    # Get manager info
    manager_result = await db.execute(
        text("""
            SELECT s.name FROM project_assignments pa
            JOIN staff_members s ON s.id = pa.staff_id
            WHERE pa.project_id = :pid AND pa.role = 'manager'
            LIMIT 1
        """),
        {"pid": project_id},
    )
    manager_row = manager_result.fetchone()

    context = {
        "company_name": project[0] if project else "",
        "audit_year": project[1] if project else None,
        "template_type": project[2] if project else "soe",
        "report_scope": project[3] if project else "standalone",
        "partner_name": partner_row[0] if partner_row else "",
        "manager_name": manager_row[0] if manager_row else "",
        "materiality_level": float(mat_row[0]) if mat_row and mat_row[0] else None,
        "performance_materiality": float(mat_row[1]) if mat_row and mat_row[1] else None,
        "trivial_threshold": float(mat_row[2]) if mat_row and mat_row[2] else None,
        "report_date": None,  # To be filled by user
        "balance_sheet_date": f"{project[1]}-12-31" if project and project[1] else None,
    }

    return {"context": context}
