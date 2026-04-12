"""项目看板路由 — 概览/工时/时间线/PBC

Validates: Requirements 5.1-5.6
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.core import User
from app.services.dashboard_service import DashboardService
from app.services.collaboration_schemas import (
    ProjectOverview,
    RiskAlert,
    WorkloadSummary,
    WorkhourCreate,
    WorkhourResponse,
    TimelineCreate,
    TimelineUpdate,
    TimelineResponse,
    PBCItemCreate,
    PBCItemUpdate,
    PBCItemResponse,
)

router = APIRouter(prefix="/dashboard", tags=["项目看板"])


# ---------------------------------------------------------------------------
# 项目概览
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/overview")
def get_project_overview(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """项目概览统计"""
    try:
        return DashboardService.get_project_overview(db, project_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/projects/{project_id}/risk-alerts")
def get_risk_alerts(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """风险预警列表"""
    return DashboardService.get_risk_alerts(db, project_id)


@router.get("/projects/{project_id}/workload-summary")
def get_workload_summary(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """工时汇总（预算 vs 实际）"""
    return DashboardService.get_workload_summary(db, project_id)


# ---------------------------------------------------------------------------
# 工时管理
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/workhours")
def record_workhours(
    project_id: str,
    req: WorkhourCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """记录工时"""
    user_id = req.user_id or str(user.id)
    wh = DashboardService.record_workhours(
        db, project_id, user_id, req.work_date, req.hours, req.work_description
    )
    return {
        "id": str(wh.id),
        "project_id": str(wh.project_id),
        "user_id": str(wh.user_id) if wh.user_id else None,
        "work_date": wh.work_date,
        "hours": float(wh.hours),
        "work_description": wh.work_description,
    }


@router.get("/projects/{project_id}/workhours")
def list_workhours(
    project_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取工时列表"""
    from app.models.collaboration_models import WorkHours
    items = db.query(WorkHours).filter(
        WorkHours.project_id == project_id,
        WorkHours.is_deleted == False,  # noqa: E712
    ).offset(skip).limit(limit).all()
    return [
        {
            "id": str(w.id),
            "project_id": str(w.project_id),
            "user_id": str(w.user_id) if w.user_id else None,
            "work_date": w.work_date,
            "hours": float(w.hours),
            "work_description": w.work_description,
        }
        for w in items
    ]


# ---------------------------------------------------------------------------
# 时间节点
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/timelines")
def list_timelines(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取项目时间节点"""
    timelines = DashboardService.get_timelines(db, project_id)
    return [_timeline_to_response(t) for t in timelines]


@router.post("/projects/{project_id}/timelines")
def create_timeline(
    project_id: str,
    req: TimelineCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建时间节点"""
    tl = DashboardService.create_timeline(
        db, project_id, req.milestone_type, req.due_date, req.notes
    )
    return _timeline_to_response(tl)


@router.put("/timelines/{timeline_id}")
def update_timeline(
    timeline_id: str,
    req: TimelineUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新时间节点"""
    tl = DashboardService.update_timeline(
        db, timeline_id,
        due_date=req.due_date,
        completed_date=req.completed_date,
        is_completed=req.is_completed,
        notes=req.notes,
    )
    if not tl:
        raise HTTPException(404, "时间节点不存在")
    return _timeline_to_response(tl)


# ---------------------------------------------------------------------------
# PBC 清单
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/pbc-items")
def list_pbc_items(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取 PBC 清单"""
    items = DashboardService.get_pbc_items(db, project_id)
    return [_pbc_to_response(i) for i in items]


@router.post("/projects/{project_id}/pbc-items")
def create_pbc_item(
    project_id: str,
    req: PBCItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建 PBC 清单项"""
    item = DashboardService.create_pbc_item(
        db, project_id,
        item_name=req.item_name,
        category=req.category,
        requested_date=req.requested_date,
        notes=req.notes,
        created_by=str(user.id),
    )
    return _pbc_to_response(item)


@router.put("/pbc-items/{item_id}")
def update_pbc_item(
    item_id: str,
    req: PBCItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新 PBC 清单项"""
    item = DashboardService.update_pbc_item(
        db, item_id,
        item_name=req.item_name,
        category=req.category,
        status=req.status,
        received_date=req.received_date,
        notes=req.notes,
    )
    if not item:
        raise HTTPException(404, "PBC 清单项不存在")
    return _pbc_to_response(item)


@router.get("/projects/{project_id}/pbc-status")
def get_pbc_status(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """PBC 接收状态汇总"""
    return DashboardService.get_pbc_status(db, project_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _timeline_to_response(tl) -> dict:
    return {
        "id": str(tl.id),
        "project_id": str(tl.project_id),
        "milestone_type": tl.milestone_type.value
                          if hasattr(tl.milestone_type, 'value')
                          else str(tl.milestone_type),
        "due_date": tl.due_date,
        "completed_date": tl.completed_date,
        "is_completed": tl.is_completed,
        "notes": tl.notes,
    }


def _pbc_to_response(item) -> dict:
    return {
        "id": str(item.id),
        "project_id": str(item.project_id),
        "item_name": item.item_name,
        "category": item.category,
        "requested_date": item.requested_date,
        "received_date": item.received_date,
        "status": item.status.value if hasattr(item.status, 'value') else str(item.status),
        "notes": item.notes,
    }
