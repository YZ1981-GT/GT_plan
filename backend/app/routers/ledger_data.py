"""账表数据管理路由 — 查询 / 删除 / 增量追加。

端点：
- GET /api/projects/{pid}/ledger-data/summary       查询已导入数据概览
- DELETE /api/projects/{pid}/ledger-data            按维度删除
- POST /api/projects/{pid}/ledger-data/incremental/detect  增量追加前预检（返回期间差异）
- POST /api/projects/{pid}/ledger-data/incremental        执行增量追加

权限：项目成员可查询，manager/partner 可删除/追加。
"""
from __future__ import annotations

import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, check_consol_lock, require_project_access
from app.models.core import User
from app.services.ledger_import.base_token_resolver import resolve_base_token
from app.services.ledger_data_service import (
    LEDGER_TABLES,
    compute_incremental_diff,
    dedup_ledger_data,
    delete_ledger_data,
    detect_existing_periods,
    list_trash,
    restore_ledger_data,
    summarize_ledger_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/ledger-data", tags=["ledger-data"])


class DeleteLedgerRequest(BaseModel):
    """删除请求。"""
    year: int = Field(..., description="目标年度")
    tables: Optional[list[str]] = Field(
        None,
        description="指定表名（默认全部四表）",
    )
    periods: Optional[list[int]] = Field(
        None,
        description="月份列表（仅对 tb_ledger/tb_aux_ledger 生效；不传则删整年）",
    )
    confirmed: bool = Field(
        False,
        description="二次确认（防止误操作）",
    )
    hard_delete: bool = Field(
        False,
        description="硬删除（S7-10 默认软删，进回收站可恢复；硬删不可恢复）",
    )


class DedupLedgerRequest(BaseModel):
    """去重请求。"""
    year: int = Field(..., description="目标年度")
    tables: Optional[list[str]] = Field(
        None,
        description="指定表名（默认全部四表）",
    )
    dry_run: bool = Field(
        False,
        description="试运行：只统计可删重复行数，不实际删除",
    )
    hard_delete: bool = Field(
        False,
        description="硬删除（默认 False 软删，进回收站可恢复；硬删不可恢复）",
    )


class RestoreLedgerRequest(BaseModel):
    """S7-10 恢复请求。"""
    year: int
    tables: Optional[list[str]] = None
    periods: Optional[list[int]] = None


class IncrementalDetectRequest(BaseModel):
    """增量导入预检。"""
    year: int
    file_periods: list[int] = Field(..., description="文件中的月份列表")
    overlap_strategy: Literal["skip", "overwrite"] = "skip"


@router.get("/summary")
async def get_ledger_summary(
    project_id: UUID,
    year: Optional[int] = Query(None, description="只查某一年（None 则全部）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> dict:
    """查询项目已导入账表数据概览。"""
    try:
        return await summarize_ledger_data(db, project_id=project_id, year=year)
    except Exception as exc:
        logger.exception("summarize ledger data failed")
        raise HTTPException(status_code=500, detail=f"查询失败: {exc}")


@router.delete("")
async def delete_ledger(
    project_id: UUID,
    request: DeleteLedgerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _lock_check=Depends(check_consol_lock),
) -> dict:
    """按维度删除账表数据。

    必须 confirmed=True 才执行（防误操作）。
    """
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="删除操作必须显式确认（confirmed=true）",
        )

    # 权限校验
    if current_user.role not in ("admin", "partner", "manager"):
        raise HTTPException(status_code=403, detail="仅项目经理及以上可删除账表数据")

    try:
        deleted = await delete_ledger_data(
            db,
            project_id=project_id,
            year=request.year,
            tables=request.tables,
            periods=request.periods,
            hard_delete=request.hard_delete,
        )
        total = sum(v for v in deleted.values() if v >= 0)
        mode = "hard" if request.hard_delete else "soft"
        logger.info(
            "ledger %s-delete by user=%s project=%s year=%d periods=%s total=%d",
            mode, current_user.id, project_id, request.year, request.periods, total,
        )
        return {
            "success": True,
            "deleted": deleted,
            "total_deleted": total,
            "year": request.year,
            "periods": request.periods,
            "mode": mode,
            "recoverable": not request.hard_delete,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("delete ledger data failed")
        raise HTTPException(status_code=500, detail=f"删除失败: {exc}")


@router.post("/dedup")
async def dedup_ledger(
    project_id: UUID,
    request: DedupLedgerRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _lock_check=Depends(check_consol_lock),
) -> dict:
    """对 active 数据集做整行去重（保留每组最小 id，软删字节级完全相同的重复行）。

    安全：只删整行业务列完全相同的重复（含 summary/raw_extra/辅助维度），
    任一列有差异即保留；不动 superseded 历史版本；默认软删可经回收站恢复；
    写 app_audit_log 留痕。dry_run=true 可先预览将删除的重复行数。
    """
    if current_user.role not in ("admin", "partner", "manager"):
        raise HTTPException(status_code=403, detail="仅项目经理及以上可执行去重")

    try:
        result = await dedup_ledger_data(
            db,
            project_id=project_id,
            year=request.year,
            tables=request.tables,
            dry_run=request.dry_run,
            hard_delete=request.hard_delete,
            user_id=current_user.id,
            ip_address=http_request.client.host if http_request.client else None,
        )
        logger.info(
            "ledger dedup by user=%s project=%s year=%d dry_run=%s mode=%s total=%d",
            current_user.id, project_id, request.year,
            request.dry_run, result.get("mode"), result.get("total_deleted", 0),
        )
        return {"success": True, **result, "year": request.year}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("dedup ledger data failed")
        raise HTTPException(status_code=500, detail=f"去重失败: {exc}")


@router.get("/trash")
async def get_trash(
    project_id: UUID,
    year: Optional[int] = Query(None, description="只查某一年（None 则全部）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """S7-10: 列出回收站中已软删除的数据。"""
    try:
        return await list_trash(db, project_id=project_id, year=year)
    except Exception as exc:
        logger.exception("list_trash failed")
        raise HTTPException(status_code=500, detail=f"查询回收站失败: {exc}")


@router.post("/restore")
async def restore_ledger(
    project_id: UUID,
    request: RestoreLedgerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _lock_check=Depends(check_consol_lock),
) -> dict:
    """S7-10: 从回收站恢复数据（is_deleted=true → false）。"""
    if current_user.role not in ("admin", "partner", "manager"):
        raise HTTPException(status_code=403, detail="仅项目经理及以上可恢复账表数据")

    try:
        restored = await restore_ledger_data(
            db,
            project_id=project_id,
            year=request.year,
            tables=request.tables,
            periods=request.periods,
        )
        total = sum(v for v in restored.values() if v >= 0)
        logger.info(
            "ledger restore by user=%s project=%s year=%d periods=%s total=%d",
            current_user.id, project_id, request.year, request.periods, total,
        )
        return {
            "success": True,
            "restored": restored,
            "total_restored": total,
            "year": request.year,
            "periods": request.periods,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("restore ledger failed")
        raise HTTPException(status_code=500, detail=f"恢复失败: {exc}")


@router.post("/incremental/detect")
async def detect_incremental(
    project_id: UUID,
    request: IncrementalDetectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> dict:
    """增量追加预检：返回期间差异 + 当前 active 的不可变基准 token。

    R8 / design §5 / AC-15：响应必须携带
    `base_dataset_id` 与 `base_unit_contract_digest`（当前 active 数据集的
    canonical unit contract digest）。前端只能把这两个 token 原样随统一
    submit 提交，**不得**自己推算或使用 `dataset.version`。

    没有 active、或 active 的单位证据不可严格解析（legacy_unknown /
    legacy_declared）时返回 409 `BASE_DATASET_UNIT_VERIFIED` 的语义 ——
    具体码由 `resolve_base_token` 决定，这里不重复实现判据。
    """
    existing = await detect_existing_periods(
        db, project_id=project_id, year=request.year
    )
    file_periods_set = set(request.file_periods)
    if not file_periods_set or any(month < 1 or month > 12 for month in file_periods_set):
        raise HTTPException(status_code=422, detail="文件月份必须是 1~12 的非空集合")
    diff = compute_incremental_diff(existing, file_periods_set)
    inherit = (
        sorted(existing)
        if request.overlap_strategy == "skip"
        else diff["only_existing"]
    )

    # 唯一解析入口（与 submit / seal / activation 同一口径）。
    # 模块级符号（不是函数体内 import）—— 便于守卫/测试替换同一判据。
    base_token = await resolve_base_token(db, project_id=project_id, year=request.year)

    return {
        "year": request.year,
        "strategy": request.overlap_strategy,
        "existing_periods": sorted(existing),
        "file_periods": sorted(file_periods_set),
        "new_periods": diff["new"],
        "inherited_periods": inherit,
        "skipped_file_periods": diff["overlap"] if request.overlap_strategy == "skip" else [],
        "overwritten_periods": diff["overlap"] if request.overlap_strategy == "overwrite" else [],
        "diff": diff,
        "can_append_safely": len(diff["overlap"]) == 0,
        "requires_confirm": len(diff["overlap"]) > 0,
        # ── 不可变 CAS token（前端原样透传，不做任何本地推导）──
        "base_dataset_id": str(base_token.dataset_id) if base_token.dataset_id else None,
        "base_unit_contract_digest": base_token.unit_contract_digest,
    }


class IncrementalApplyRequest(BaseModel):
    """增量追加执行（S6-15）。"""
    year: int
    file_periods: list[int] = Field(..., description="文件中的月份列表")
    overlap_strategy: str = Field(
        "skip",
        description="重叠月份策略：skip=跳过/overwrite=覆盖",
    )
    confirmed: bool = Field(False, description="二次确认（overwrite 策略必填）")


@router.post("/incremental/apply")
async def apply_incremental_endpoint(
    project_id: UUID,
    request: IncrementalApplyRequest,
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
) -> dict:
    """旧的 active 数据预删入口永久退役；追加只允许在 staged 内合并。

    R8 / design §5 / AC-16：错误码固定为
    `INCREMENTAL_APPLY_MOVED_TO_IMPORT_JOB`（与入口注册表
    `LEDGER_IMPORT_ENTRYPOINTS` 的描述逐字一致）。
    函数体不 import/call 任何删除 service —— 守卫 AST 校验。
    """
    raise HTTPException(
        status_code=410,
        detail={
            "error_code": "INCREMENTAL_APPLY_MOVED_TO_IMPORT_JOB",
            "message": "增量覆盖已并入导入作业：请重新上传并在导入页提交，现行流程不会预删当前账套。",
        },
    )


__all__ = ["router"]
