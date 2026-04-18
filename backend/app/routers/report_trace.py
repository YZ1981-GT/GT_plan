"""报告溯源 + 合并增强 + 打卡 + 辅助汇总 + 权限 + 快照 + 推荐 + 差异 + 分类 + 排版 API

Phase 10 Task 7/9/10/13/14/16/17/19/20/21 — 合并为一个路由模块减少文件数。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.report_trace_service import ReportTraceService
from app.services.consol_enhanced_service import ConsolLockService, IndependentModuleService
from app.services.annotation_service import AnnotationService

router = APIRouter(tags=["phase10-misc"])


# ── 报告溯源 (Task 9) ────────────────────────────────────

@router.get("/api/report-review/{project_id}/trace/{section_number}")
async def trace_section(
    project_id: UUID, section_number: str,
    db: AsyncSession = Depends(get_db),
):
    svc = ReportTraceService()
    return await svc.trace_section(db, project_id, section_number)


@router.get("/api/projects/{project_id}/findings-summary")
async def findings_summary(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = ReportTraceService()
    return await svc.get_findings_summary(db, project_id)


# ── 合并锁定 (Task 7.1) ──────────────────────────────────

@router.post("/api/consolidation/{project_id}/lock")
async def lock_project(project_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = ConsolLockService()
    user_id = current_user.id
    result = await svc.lock_project(db, project_id, user_id)
    await db.commit()
    return result


@router.post("/api/consolidation/{project_id}/unlock")
async def unlock_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = ConsolLockService()
    result = await svc.unlock_project(db, project_id)
    await db.commit()
    return result


@router.get("/api/consolidation/{project_id}/lock-status")
async def check_lock(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = ConsolLockService()
    return await svc.check_lock(db, project_id)


# ── 独立模块 (Task 7.3) ──────────────────────────────────

class TempProjectRequest(BaseModel):
    module: str


@router.post("/api/temp-project")
async def create_temp_project(req: TempProjectRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = IndependentModuleService()
    user_id = current_user.id
    try:
        result = await svc.create_temp_project(db, req.module, user_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 打卡签到 (Task 10.1) ─────────────────────────────────

class CheckInRequest(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    location_name: str | None = None
    check_type: str = "morning"


@router.post("/api/staff/{staff_id}/check-in")
async def check_in(staff_id: UUID, req: CheckInRequest, db: AsyncSession = Depends(get_db)):
    from app.models.phase10_models import CheckIn
    ci = CheckIn(
        staff_id=staff_id,
        check_time=datetime.utcnow(),
        latitude=req.latitude,
        longitude=req.longitude,
        location_name=req.location_name,
        check_type=req.check_type,
    )
    db.add(ci)
    await db.commit()
    return {"id": str(ci.id), "check_time": ci.check_time.isoformat()}


@router.get("/api/staff/{staff_id}/check-ins")
async def list_check_ins(
    staff_id: UUID, limit: int = 30, db: AsyncSession = Depends(get_db),
):
    import sqlalchemy as sa
    from app.models.phase10_models import CheckIn
    stmt = (
        sa.select(CheckIn).where(CheckIn.staff_id == staff_id)
        .order_by(CheckIn.check_time.desc()).limit(limit)
    )
    result = await db.execute(stmt)
    return [
        {
            "id": str(c.id), "check_time": c.check_time.isoformat(),
            "location_name": c.location_name, "check_type": c.check_type,
        }
        for c in result.scalars().all()
    ]


# ── 辅助余额汇总 (Task 13.1) ─────────────────────────────

@router.get("/api/projects/{project_id}/ledger/aux-summary")
async def aux_summary(project_id: UUID, year: int | None = None, db: AsyncSession = Depends(get_db)):
    import sqlalchemy as sa
    from app.models.audit_platform_models import TbAuxBalance, TbBalance

    # 辅助余额按科目汇总
    aux_conditions = [TbAuxBalance.project_id == project_id, TbAuxBalance.is_deleted == sa.false()]
    if year:
        aux_conditions.append(TbAuxBalance.year == year)
    aux_stmt = (
        sa.select(
            TbAuxBalance.account_code,
            sa.func.sum(TbAuxBalance.closing_balance).label("aux_total"),
        )
        .where(*aux_conditions)
        .group_by(TbAuxBalance.account_code)
    )
    aux_result = await db.execute(aux_stmt)
    aux_map = {r.account_code: float(r.aux_total or 0) for r in aux_result.fetchall()}

    # 科目余额
    bal_conditions = [TbBalance.project_id == project_id, TbBalance.is_deleted == sa.false()]
    if year:
        bal_conditions.append(TbBalance.year == year)
    bal_stmt = (
        sa.select(TbBalance.account_code, TbBalance.account_name, TbBalance.closing_balance)
        .where(*bal_conditions)
    )
    bal_result = await db.execute(bal_stmt)

    items = []
    for r in bal_result.fetchall():
        tb_bal = float(r.closing_balance or 0)
        aux_bal = aux_map.get(r.account_code, 0)
        diff = round(tb_bal - aux_bal, 2)
        items.append({
            "account_code": r.account_code,
            "account_name": r.account_name,
            "tb_balance": tb_bal,
            "aux_summary": aux_bal,
            "diff": diff,
            "is_matched": abs(diff) < 0.01,
        })
    return items


# ── 权限精细化 (Task 14.1) ────────────────────────────────

@router.get("/api/projects/{project_id}/check-delete-permission")
async def check_delete_permission(
    project_id: UUID, object_type: str, object_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """检查删除权限（stub — 实际需从 JWT 获取用户角色）"""
    return {"allowed": True, "reason": "管理员权限"}


# ── 合并快照 (Task 16.1) ─────────────────────────────────

@router.get("/api/consolidation/{project_id}/snapshots")
async def list_snapshots(project_id: UUID, db: AsyncSession = Depends(get_db)):
    import sqlalchemy as sa
    from app.models.phase10_models import ConsolSnapshot
    stmt = (
        sa.select(ConsolSnapshot).where(ConsolSnapshot.project_id == project_id)
        .order_by(ConsolSnapshot.created_at.desc()).limit(20)
    )
    result = await db.execute(stmt)
    return [
        {
            "id": str(s.id), "year": s.year, "trigger_reason": s.trigger_reason,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in result.scalars().all()
    ]


@router.post("/api/consolidation/{project_id}/snapshots")
async def create_snapshot(
    project_id: UUID, year: int = 2025, reason: str = "manual",
    db: AsyncSession = Depends(get_db),
):
    from app.models.phase10_models import ConsolSnapshot
    snap = ConsolSnapshot(
        project_id=project_id, year=year,
        snapshot_data={"created_at": datetime.utcnow().isoformat()},
        trigger_reason=reason,
    )
    db.add(snap)
    await db.commit()
    return {"id": str(snap.id), "year": year}


# ── 底稿推荐 (Task 17.1) ─────────────────────────────────

@router.post("/api/projects/{project_id}/ai/recommend-workpapers")
async def recommend_workpapers(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """LLM 推荐底稿优先级（stub）"""
    return {
        "recommendations": [
            {"wp_code": "E9-1", "priority": "high", "reason": "固定资产金额重大"},
            {"wp_code": "E1-1", "priority": "high", "reason": "货币资金需函证"},
            {"wp_code": "E3-1", "priority": "medium", "reason": "应收账款需账龄分析"},
        ]
    }


# ── 年度差异报告 (Task 19.1) ──────────────────────────────

@router.post("/api/projects/{project_id}/ai/annual-diff-report")
async def annual_diff_report(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """年度差异分析报告（stub）"""
    return {
        "project_id": str(project_id),
        "report": "年度差异分析报告生成中（stub）",
        "significant_changes": [],
    }


# ── 附件智能分类 (Task 20.1) ──────────────────────────────

class ClassifyAttachmentRequest(BaseModel):
    attachment_id: str
    file_name: str


@router.post("/api/projects/{project_id}/attachments/classify")
async def classify_attachment(
    project_id: UUID, req: ClassifyAttachmentRequest,
    db: AsyncSession = Depends(get_db),
):
    """附件智能分类（stub）"""
    # 简单规则分类
    name = req.file_name.lower()
    if "合同" in name or "contract" in name:
        category = "contract"
    elif "发票" in name or "invoice" in name:
        category = "invoice"
    elif "对账" in name or "reconciliation" in name:
        category = "reconciliation"
    elif "函证" in name or "confirmation" in name:
        category = "confirmation"
    else:
        category = "other"
    return {"attachment_id": req.attachment_id, "category": category, "confidence": 0.8}


# ── 排版模板 (Task 21.1) ─────────────────────────────────

@router.get("/api/report-format-templates")
async def list_format_templates(db: AsyncSession = Depends(get_db)):
    import sqlalchemy as sa
    from app.models.phase10_models import ReportFormatTemplate
    stmt = (
        sa.select(ReportFormatTemplate)
        .where(ReportFormatTemplate.is_deleted == sa.false())
        .order_by(ReportFormatTemplate.created_at.desc())
    )
    result = await db.execute(stmt)
    return [
        {
            "id": str(t.id), "template_name": t.template_name,
            "template_type": t.template_type, "config": t.config,
            "version": t.version, "is_default": t.is_default,
        }
        for t in result.scalars().all()
    ]


@router.post("/api/report-format-templates")
async def create_format_template(
    req: dict[str, Any], db: AsyncSession = Depends(get_db),
):
    from app.models.phase10_models import ReportFormatTemplate
    tpl = ReportFormatTemplate(
        template_name=req.get("template_name", "新模板"),
        template_type=req.get("template_type", "standard"),
        config=req.get("config", {}),
    )
    db.add(tpl)
    await db.commit()
    return {"id": str(tpl.id), "template_name": tpl.template_name}
