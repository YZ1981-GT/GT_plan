"""抽凭的审计阶段上下文（spec voucher-identity-writeback-and-audit-phase 任务 15，需求 7.1，design §6）。

- ``GET /api/projects/{pid}/sampling/phase-context?wp_id=&year=``：当前阶段、预审截止日（及口径 a 实际
  采用的截止日与来源）、本底稿预审批次数 / 样本数 / 分录数 / 预审手工挂凭数、上次年审口径、是否须选口径。
  年审抽凭弹窗据此决定是否弹出、缺省选哪个口径（上次的选择，首次 b）。
- ``GET /api/projects/{pid}/sampling/phase-evaluation?wp_id=&log_id=``：年审批次的全年合并评价（任务 16），
  计算在 ``services/sampling_phase_evaluation.py``，保存评价时同一结果写进年审批次评价。

``voucher_sampling.py`` 行数余量不足，阶段相关端点放这里。口径的判定与执行在
``services/sampling_final_population.py``，抽凭接口按同一份上下文校验，弹窗看到的与后端执行的一致。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import authorize_wp_edit, authorize_wp_read, get_current_user
from app.models.core import User
from app.services.interim_survival import (
    MAX_ROWS,
    check_interim_survival,
    set_unacked,
    survival_status,
)
from app.services.project_audit_phase import project_phase
from app.services.sampling_final_population import load_phase_context
from app.services.sampling_phase_evaluation import phase_evaluation
from app.services.sampling_registry_service import resolve_project_year

router = APIRouter(prefix="/api/projects/{pid}/sampling", tags=["sampling"])


@router.get("/phase-context")
async def phase_context(
    pid: UUID,
    wp_id: UUID = Query(..., description="底稿 ID"),
    year: int | None = Query(None, description="审计年度，缺省取项目审计年度（只用于推算预审批次期间上限）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """年审抽凭口径弹窗的上下文。底稿须属于路径项目，调用人须是该项目成员（只读级即可）。"""
    wp_project_id = await authorize_wp_read(db, current_user, wp_id)
    if str(wp_project_id) != str(pid):
        raise HTTPException(status_code=403, detail="底稿不属于该项目")
    resolved_year = year if year is not None else await resolve_project_year(db, pid)
    ctx = await load_phase_context(db, project_id=pid, workpaper_id=wp_id, year=resolved_year)
    return ctx.to_dict()


@router.get("/phase-evaluation")
async def phase_evaluation_view(
    pid: UUID,
    wp_id: UUID = Query(..., description="底稿 ID"),
    log_id: UUID | None = Query(None, description="年审批次日志 ID，缺省取本底稿最近一次带年审口径的批次"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全年合并评价（任务 16，ADR-VK-10）：各分量、口径、科目范围是否一致；不可用时 available=false + 原因。"""
    wp_project_id = await authorize_wp_read(db, current_user, wp_id)
    if str(wp_project_id) != str(pid):
        raise HTTPException(status_code=403, detail="底稿不属于该项目")
    return await phase_evaluation(db, project_id=pid, workpaper_id=wp_id, log_id=log_id)


class InterimSurvivalRow(BaseModel):
    """宿主行元数据的核对输入；后端会再与 lfp 内嵌的科目 / 借贷栏 / 金额逐值校验。"""

    row_key: str = Field(min_length=1, max_length=2000)
    lfp: str = Field(min_length=1, max_length=2000)
    vk: str = Field(min_length=1, max_length=1000)
    account_code: str = Field(min_length=1, max_length=100)
    side: str = Field(pattern="^[DCX]$")
    amount: str = Field(min_length=1, max_length=100)
    previous_dataset_id: str | None = None
    previous_status: str | None = Field(None, pattern="^(unchanged|modified|renumbered|deleted)$")
    acknowledged: bool = False


class InterimSurvivalRequest(BaseModel):
    wp_id: UUID
    year: int = Field(ge=2000, le=2100)
    rows: list[InterimSurvivalRow] = Field(min_length=1, max_length=MAX_ROWS)


class InterimSurvivalAckRequest(BaseModel):
    wp_id: UUID
    dataset_id: UUID
    unacked: int = Field(ge=0)


async def _authorize_survival(
    db: AsyncSession, current_user: User, pid: UUID, wp_id: UUID, *, edit: bool,
) -> None:
    owner = await (authorize_wp_edit if edit else authorize_wp_read)(db, current_user, wp_id)
    if str(owner) != str(pid):
        raise HTTPException(status_code=403, detail="底稿不属于该项目")


async def _require_final_phase(db: AsyncSession, pid: UUID) -> None:
    if await project_phase(db, pid) != "final":
        raise HTTPException(status_code=409, detail={
            "error_code": "FINAL_PHASE_REQUIRED", "message": "预审样本存续核对只在项目年审阶段执行",
        })


@router.get("/interim-survival/status")
async def interim_survival_status(
    pid: UUID,
    wp_id: UUID = Query(..., description="底稿 ID"),
    year: int | None = Query(None, description="审计年度，缺省取项目审计年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当前 active 账套与本底稿在该版本上的最近存续核对汇总（只读）。"""
    await _authorize_survival(db, current_user, pid, wp_id, edit=False)
    resolved = year if year is not None else await resolve_project_year(db, pid)
    if resolved is None:
        return {"year": None, "active_dataset_id": None, "check": None,
                "reason": "项目审计年度无法判定"}
    return await survival_status(db, project_id=pid, workpaper_id=wp_id, year=int(resolved))


@router.post("/interim-survival")
async def run_interim_survival(
    pid: UUID,
    req: InterimSurvivalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按 ADR-VK-11 四步顺序核对预审分录，并 upsert 当前账套版本的汇总。"""
    await _authorize_survival(db, current_user, pid, req.wp_id, edit=True)
    await _require_final_phase(db, pid)
    project_year = await resolve_project_year(db, pid)
    if project_year is not None and int(project_year) != req.year:
        raise HTTPException(status_code=422, detail={
            "error_code": "SURVIVAL_YEAR_MISMATCH",
            "message": f"请求年度 {req.year} 与项目审计年度 {project_year} 不一致",
        })
    result = await check_interim_survival(
        db,
        project_id=pid,
        workpaper_id=req.wp_id,
        year=req.year,
        rows=[row.model_dump() for row in req.rows],
        checked_by=current_user.id,
    )
    await db.commit()
    return result


@router.patch("/interim-survival/{check_id}")
async def acknowledge_interim_survival(
    pid: UUID,
    check_id: UUID,
    req: InterimSurvivalAckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """行元数据已持久化后，用剩余未确认数幂等刷新汇总；旧账套版本 409，避免污染当前概览。"""
    await _authorize_survival(db, current_user, pid, req.wp_id, edit=True)
    await _require_final_phase(db, pid)
    result = await set_unacked(
        db,
        project_id=pid,
        workpaper_id=req.wp_id,
        dataset_id=req.dataset_id,
        check_id=check_id,
        unacked=req.unacked,
        actor_id=current_user.id,
    )
    await db.commit()
    return result
