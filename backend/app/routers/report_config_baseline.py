"""报表配置主模板回填 + 联动 API

端点：
- POST /api/report-config/suggest-to-master       — 项目级优化提交为主模板候选
- POST /api/report-config/review-candidate         — admin 审核候选（通过/驳回）
- GET  /api/report-config/diff-vs-master/{project_id} — 项目 vs 主模板差异
- POST /api/report-config/apply-master-update      — 主模板更新同步到项目
- GET  /api/report-config/candidates               — 待审核候选列表（admin）
- GET  /api/report-config/stale-status/{project_id} — 项目 stale 状态查询
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user, require_project_access, require_role
from app.models.core import User
from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.propagation import publish_events
from app.services.report_config_service import ReportConfigService

router = APIRouter(
    prefix="/api/report-config",
    tags=["report-config-baseline"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SuggestToMasterRequest(BaseModel):
    project_id: UUID
    row_code: str = Field(..., min_length=1)
    report_type: str = Field(..., min_length=1)
    standard: str = Field(..., min_length=1)
    candidate_formula: str | None = None


class ReviewCandidateRequest(BaseModel):
    candidate_id: UUID
    approved: bool


class ApplyMasterUpdateRequest(BaseModel):
    project_id: UUID
    standard: str = Field(..., min_length=1)
    keep_local: bool = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/suggest-to-master")
async def suggest_to_master(
    body: SuggestToMasterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """项目级优化提交为主模板候选（写 ReportConfigBaseline pending）。

    🔴 V199 补：原只校验登录 ⇒ 任何人可读任意项目的公式并以它的名义提交候选；现需来源项目 edit。
    """
    await assert_project_permission(db, current_user, body.project_id, "edit")
    svc = ReportConfigService(db)
    try:
        candidate_id = await svc.suggest_to_master(
            project_id=body.project_id,
            row_code=body.row_code,
            report_type=body.report_type,
            standard=body.standard,
            candidate_formula=body.candidate_formula,
            submitted_by=current_user.id,
        )
        await db.commit()
        return {"candidate_id": str(candidate_id), "message": "已提交主模板候选"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/review-candidate")
async def review_candidate(
    body: ReviewCandidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """admin 审核候选：通过则作为全局发布（经同步内核，冲突交项目确认），commit 后发变更事件。"""
    svc = ReportConfigService(db)
    try:
        published = await svc.review_candidate(
            candidate_id=body.candidate_id,
            approved=body.approved,
            reviewer=current_user.id,
        )
    except FormulaSettingError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    if published:
        await publish_events(published.get("events") or [], domain="report", source="promote",
                             token=published.get("publish_id"))
    status = "已通过" if body.approved else "已驳回"
    summary = (published or {}).get("summary") or {}
    return {"message": f"候选审核{status}", "approved": body.approved,
            "pending_total": summary.get("pending_total", 0)}


@router.get("/diff-vs-master/{project_id}")
async def diff_vs_master(
    project_id: UUID,
    standard: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """项目级 vs 主模板差异（V199 补项目 readonly 鉴权，原只校验登录）"""
    if not standard:
        standard = await ReportConfigService.resolve_applicable_standard(db, project_id)
    svc = ReportConfigService(db)
    diffs = await svc.diff_vs_master(project_id=project_id, standard=standard)
    return {
        "project_id": str(project_id),
        "standard": standard,
        "diff_count": len(diffs),
        "diffs": [
            {
                "row_code": d.row_code,
                "report_type": d.report_type,
                "project_formula": d.project_formula,
                "master_formula": d.master_formula,
                "diff_type": d.diff_type,
            }
            for d in diffs
        ],
    }


@router.post("/apply-master-update")
async def apply_master_update(
    body: ApplyMasterUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """主模板更新同步到项目（V199：经同步内核；改过且不同的行生成待确认事项，不再静默保留）。

    🔴 原只校验登录 ⇒ 任何人可改写任意项目的项目级公式；现需目标项目 edit。
    """
    from app.services.formula_settings.legacy_report import sync_project_to_global
    from app.services.formula_settings.projects import get_project

    await assert_project_permission(db, current_user, body.project_id, "edit")
    if await get_project(db, "report", body.project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在或已删除")
    result = await sync_project_to_global(db, project_id=body.project_id, standard=body.standard,
                                          keep_local=body.keep_local, user_id=current_user.id)
    await db.commit()
    await publish_events(result["events"], domain="report", source="master_sync")
    pending = result["pending"]
    message = f"已同步 {result['updated']} 行" + (f"，{pending} 处与本项目修改冲突，已列入待确认" if pending else "")
    return {"updated_count": result["updated"], "pending_count": pending, "rebased_count": result["rebased"],
            "message": message}


@router.get("/candidates")
async def list_candidates(
    status: str = Query("pending"),
    standard: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """待审核候选列表（admin）"""
    import sqlalchemy as sa
    from app.models.report_models import ReportConfigBaseline

    q = sa.select(ReportConfigBaseline).where(
        ReportConfigBaseline.status == status
    )
    if standard:
        q = q.where(ReportConfigBaseline.standard == standard)
    q = q.order_by(ReportConfigBaseline.created_at.desc())

    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "standard": r.standard,
            "report_type": r.report_type,
            "row_code": r.row_code,
            "candidate_formula": r.candidate_formula,
            "source_project_id": str(r.source_project_id) if r.source_project_id else None,
            "status": r.status,
            "version": r.version,
            "submitted_by": str(r.submitted_by) if r.submitted_by else None,
            "reviewed_by": str(r.reviewed_by) if r.reviewed_by else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/stale-status/{project_id}")
async def stale_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询项目是否有 stale 配置行 + 报表公式待确认事项（V199 补项目 readonly 鉴权）"""
    import sqlalchemy as sa
    from app.models.formula_setting_models import FormulaSyncItem
    from app.models.report_models import ReportConfig

    project_standard = f"project:{project_id}"
    result = await db.execute(
        sa.select(sa.func.count()).select_from(ReportConfig).where(
            ReportConfig.applicable_standard == project_standard,
            ReportConfig.is_stale == sa.true(),
            ReportConfig.is_deleted == sa.false(),
        )
    )
    stale_count = result.scalar() or 0
    pending_count = (await db.execute(sa.select(sa.func.count()).select_from(FormulaSyncItem).where(
        FormulaSyncItem.project_id == project_id, FormulaSyncItem.domain == "report",
        FormulaSyncItem.status == "pending"))).scalar() or 0
    return {
        "project_id": str(project_id),
        "is_stale": stale_count > 0 or pending_count > 0,
        "stale_count": stale_count,
        "pending_count": pending_count,
    }
