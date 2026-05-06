"""QC 规则定义管理路由 — Round 3 需求 1, 2

GET    /api/qc/rules          — 列表（支持 scope/severity/enabled 过滤）
POST   /api/qc/rules          — 创建新规则（version=1）
GET    /api/qc/rules/{id}     — 获取单条规则详情
PATCH  /api/qc/rules/{id}     — 更新规则（version+1，保留历史）
DELETE /api/qc/rules/{id}     — 软删除规则
POST   /api/qc/rules/{id}/dry-run — 规则试运行（不写 DB，返回命中率）

权限：role='qc' | 'admin'
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.services.qc_rule_definition_service import qc_rule_definition_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/qc/rules", tags=["qc-rules"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class QcRuleCreateRequest(BaseModel):
    """创建规则请求体"""

    rule_code: str = Field(..., min_length=1, max_length=50, description="规则编号，如 QC-01")
    severity: Literal["blocking", "warning", "info"] = Field(..., description="严重级别")
    scope: Literal["workpaper", "project", "consolidation", "audit_log"] = Field(
        ..., description="规则作用域"
    )
    category: Optional[str] = Field(None, max_length=100, description="分类")
    title: str = Field(..., min_length=1, max_length=200, description="规则标题")
    description: str = Field(..., min_length=1, description="规则描述")
    standard_ref: Optional[list[dict]] = Field(
        None, description="准则引用 [{code, section, name}]"
    )
    expression_type: Literal["python", "jsonpath", "sql", "regex"] = Field(
        ..., description="表达式类型"
    )
    expression: str = Field(..., min_length=1, description="表达式内容")
    parameters_schema: Optional[dict] = Field(None, description="参数 JSON Schema")
    enabled: bool = Field(True, description="是否启用")


class QcRuleUpdateRequest(BaseModel):
    """更新规则请求体（所有字段可选）"""

    rule_code: Optional[str] = Field(None, min_length=1, max_length=50)
    severity: Optional[Literal["blocking", "warning", "info"]] = None
    scope: Optional[Literal["workpaper", "project", "consolidation", "audit_log"]] = None
    category: Optional[str] = Field(None, max_length=100)
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1)
    standard_ref: Optional[list[dict]] = None
    expression_type: Optional[Literal["python", "jsonpath", "sql", "regex"]] = None
    expression: Optional[str] = Field(None, min_length=1)
    parameters_schema: Optional[dict] = None
    enabled: Optional[bool] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_rules(
    scope: Optional[str] = Query(None, description="按 scope 过滤"),
    severity: Optional[str] = Query(None, description="按 severity 过滤"),
    enabled: Optional[bool] = Query(None, description="按 enabled 过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """列出 QC 规则定义，支持过滤与分页。"""
    result = await qc_rule_definition_service.list_rules(
        db,
        scope=scope,
        severity=severity,
        enabled=enabled,
        page=page,
        page_size=page_size,
    )
    return result


@router.post("", status_code=201)
async def create_rule(
    body: QcRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """创建新 QC 规则，version 初始为 1。"""
    result = await qc_rule_definition_service.create_rule(
        db,
        data=body.model_dump(exclude_unset=False),
        created_by=current_user.id,
    )
    await db.commit()
    return result


@router.get("/{rule_id}")
async def get_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """获取单条 QC 规则详情。"""
    return await qc_rule_definition_service.get_rule(db, rule_id)


@router.patch("/{rule_id}")
async def update_rule(
    rule_id: UUID,
    body: QcRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """更新 QC 规则，每次更新 version+1。"""
    data = body.model_dump(exclude_unset=True)
    if not data:
        # 没有任何字段需要更新
        return await qc_rule_definition_service.get_rule(db, rule_id)

    result = await qc_rule_definition_service.update_rule(db, rule_id, data=data)
    await db.commit()
    return result


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """软删除 QC 规则。"""
    result = await qc_rule_definition_service.delete_rule(db, rule_id)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# Dry-run schemas & endpoint — 需求 2
# ---------------------------------------------------------------------------


class DryRunRequest(BaseModel):
    """规则试运行请求体"""

    scope: Literal["project", "all"] = Field(
        ..., description="试运行范围：project=指定项目, all=全部项目"
    )
    project_ids: Optional[list[UUID]] = Field(
        None, description="项目 ID 列表（scope='project' 时必填）"
    )
    sample_size: Optional[int] = Field(
        None, ge=1, le=500, description="采样大小（默认 50，最大 500）"
    )


class DryRunFinding(BaseModel):
    """试运行命中详情"""

    wp_id: str
    wp_code: Optional[str] = None
    message: str
    severity: str


class DryRunResponse(BaseModel):
    """试运行同步响应"""

    total_checked: int
    hits: int
    hit_rate: float
    sample_findings: list[DryRunFinding]


class DryRunAsyncResponse(BaseModel):
    """试运行异步响应（走 BackgroundJob）"""

    job_id: str
    status: str = "queued"
    message: str = "试运行任务已提交，请轮询 job_status 获取结果"


@router.post("/{rule_id}/dry-run")
async def dry_run_rule(
    rule_id: UUID,
    body: DryRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """规则试运行 — 需求 2

    对采样底稿跑规则沙箱，不写 DB，返回命中率。
    如果 sample_size > 100，走 BackgroundJob 异步化。
    """
    from app.services.qc_rule_dry_run_service import qc_rule_dry_run_service

    # 验证 scope='project' 时必须提供 project_ids
    if body.scope == "project" and not body.project_ids:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail="scope='project' 时必须提供 project_ids",
        )

    # 加载规则
    rule = await qc_rule_definition_service._get_or_404(db, rule_id)

    # 判断是否走异步
    should_async = await qc_rule_dry_run_service.should_run_async(
        db, rule, body.scope, body.project_ids, body.sample_size
    )

    if should_async:
        # 走 BackgroundJob 异步
        from app.services.background_job_service import BackgroundJobService

        job_svc = BackgroundJobService(db)
        # 创建一个空 wp_ids 的 job（dry-run 不需要逐项跟踪）
        job_result = await job_svc.create_job(
            project_id=body.project_ids[0] if body.project_ids else UUID(int=0),
            job_type="qc_rule_dry_run",
            wp_ids=[],
            payload={
                "rule_id": str(rule_id),
                "scope": body.scope,
                "project_ids": [str(pid) for pid in body.project_ids] if body.project_ids else [],
                "sample_size": body.sample_size,
            },
            user_id=current_user.id,
        )
        await db.commit()

        # 后台执行 dry-run
        job_id = job_result["job_id"]

        async def _run_async_dry_run():
            """后台执行 dry-run 并更新 job 状态。"""
            from app.core.database import async_session

            async with async_session() as async_db:
                try:
                    from app.models.phase12_models import BackgroundJob
                    import sqlalchemy as _sa

                    # 标记 running
                    job_obj = (await async_db.execute(
                        _sa.select(BackgroundJob).where(
                            BackgroundJob.id == UUID(job_id)
                        )
                    )).scalar_one_or_none()
                    if job_obj:
                        job_obj.status = "running"
                        await async_db.flush()

                    # 重新加载规则
                    from app.models.qc_rule_models import QcRuleDefinition

                    rule_obj = (await async_db.execute(
                        _sa.select(QcRuleDefinition).where(
                            QcRuleDefinition.id == rule_id
                        )
                    )).scalar_one_or_none()

                    if rule_obj:
                        result = await qc_rule_dry_run_service.run_dry_run(
                            async_db,
                            rule_obj,
                            body.scope,
                            body.project_ids,
                            body.sample_size,
                        )
                        # 存结果到 payload
                        if job_obj:
                            job_obj.payload = {
                                **(job_obj.payload or {}),
                                "result": result.to_dict(),
                            }
                            job_obj.status = "succeeded"
                            job_obj.progress_done = result.total_checked
                            job_obj.progress_total = result.total_checked
                    else:
                        if job_obj:
                            job_obj.status = "failed"
                            job_obj.payload = {
                                **(job_obj.payload or {}),
                                "error": "规则不存在",
                            }

                    await async_db.commit()
                except Exception as e:
                    logger.exception("[DRY_RUN_ASYNC] Failed: %s", e)
                    try:
                        from app.models.phase12_models import BackgroundJob
                        import sqlalchemy as _sa

                        job_obj = (await async_db.execute(
                            _sa.select(BackgroundJob).where(
                                BackgroundJob.id == UUID(job_id)
                            )
                        )).scalar_one_or_none()
                        if job_obj:
                            job_obj.status = "failed"
                            job_obj.payload = {
                                **(job_obj.payload or {}),
                                "error": str(e)[:500],
                            }
                        await async_db.commit()
                    except Exception:
                        pass

        background_tasks.add_task(_run_async_dry_run)

        return DryRunAsyncResponse(job_id=job_id, status="queued")

    else:
        # 同步执行
        result = await qc_rule_dry_run_service.run_dry_run(
            db, rule, body.scope, body.project_ids, body.sample_size
        )
        return DryRunResponse(
            total_checked=result.total_checked,
            hits=result.hits,
            hit_rate=result.hit_rate,
            sample_findings=[
                DryRunFinding(**f) for f in result.sample_findings
            ],
        )

