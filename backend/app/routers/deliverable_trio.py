"""交付中心三件套一键出具 — 项目级鉴权的正式 trio 端点（phase4 Task 9）。

spec: ``.kiro/specs/chain-closure-phase4-deliverable-center-trio``（design §4.4，需求 1.6/3.5/5.1/5.6/7.4）。

本路由是正式三件套（审定财务报表 → 报表附注 → 审计报告正文）的 HTTP 边界，
与既有 ``word_export.py`` 的登录态端点并存但语义不同：

- 既有 ``/word-exports/full-deliverables`` 等端点仅 ``Depends(get_current_user)``（只验登录，
  无项目级鉴权），为兼容既有前端调用保留，**不弱化**（铁律㉗①：不「对齐」有缺陷的端点）。
- 本路由每个端点经 ``require_project_access`` 真依赖链校验**项目级**权限：
    * readiness / 状态查询 / 下载 = ``readonly``（项目成员）；
    * 创建（一键出具） / 重试 = ``edit``（项目编辑/交付权）。
  非项目成员、只读成员访问写端点一律 403，且 403 时零写入（写端点的 commit 只在
  业务成功后由 **router** 执行；service 只 flush）。

端点清单（design §4.4）：

- ``GET  /api/projects/{project_id}/deliverables/trio/readiness?year=`` — readonly
- ``POST /api/projects/{project_id}/deliverables/trio`` — edit，重新 readiness 后创建 job
- ``GET  /api/projects/{project_id}/deliverables/trio/jobs/{job_id}`` — readonly，校验 job 属主项目
- ``POST /api/projects/{project_id}/deliverables/trio/jobs/{job_id}/retry`` — edit，只重试失败项
- ``GET  /api/projects/{project_id}/deliverables/trio/items/{item_id}/download`` — readonly，
  下载前再次执行物理文件存在/可读/指纹校验（``verify_file_fingerprint``），失败明确中文错误，
  绝不返回缺失/被篡改文件冒充正式交付（需求 3.5）。

铁律㉗：路径里的 ``project_id`` 不是隔离 —— job/item 的归属必须用数据层查询（``job.project_id``）
真的比对，不一致返回 403。
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.phase13_schemas import (
    ExportJobAttemptResponse,
    ExportJobItemResponse,
    ExportJobResponse,
    FullDeliverablesRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/deliverables/trio",
    tags=["deliverable-trio"],
)


# ---------------------------------------------------------------------------
# GET /readiness — 交付前就绪判定（readonly）
# ---------------------------------------------------------------------------


@router.get("/readiness")
async def get_trio_readiness(
    project_id: UUID,
    year: int = Query(..., description="审计年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """返回项目审计年度的三件套就绪状态（硬闸门 / 软 warning / 快照 / 逐项状态）。

    权限：项目 ``readonly``（非成员 403）。只读端点，不写库、不 commit。
    readiness 失败时返回可行动的中文原因（``status=blocked`` + ``hard_blockers``），
    而非 HTTP 200 加空文件（需求 1.6）。
    """
    from app.services.deliverable_readiness_service import DeliverableReadinessService

    svc = DeliverableReadinessService(db)
    result = await svc.check(project_id, year, include_file_checks=True)
    return result.to_dict()


# ---------------------------------------------------------------------------
# POST /trio — 一键出具三件套（edit）
# ---------------------------------------------------------------------------


@router.post("", response_model=ExportJobResponse)
async def create_trio(
    project_id: UUID,
    body: FullDeliverablesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """一键出具正式三件套：重新 readiness 判定 → ready 才创建并执行 job。

    权限：项目 ``edit``（非成员 / 只读成员 403，且 403 零写入）。
    readiness 阻断 ⇒ 返回 409 + 中文阻断项，绝不创建半成品 job（需求 1.6/4.4）。
    service 只 flush，成功后由本 router 统一 commit。
    """
    from app.services.deliverable_readiness_service import DeliverableReadinessService
    from app.services.export_job_service import ExportJobService
    from app.services.full_deliverables_executor import FullDeliverablesExecutor

    # ① readiness 复查（需求 1.1/1.6）：阻断时不创建 job，返回可行动中文原因。
    readiness = await DeliverableReadinessService(db).check(
        project_id, body.year, include_file_checks=True
    )
    if readiness.status == "blocked":
        raise HTTPException(
            status_code=409,
            detail={
                "status": "blocked",
                "message": "交付前检查未通过，无法出具三件套",
                "hard_blockers": [g.to_dict() for g in readiness.hard_blockers],
                "snapshot_id": (readiness.snapshot or {}).get("id"),
            },
        )

    # ② 创建并执行 job（service 只 flush）。
    executor = FullDeliverablesExecutor(db)
    payload = {
        "year": body.year,
        "template_variant": body.template_variant,
        "steps": body.steps,
        "optional_sections": body.optional_sections,
    }
    try:
        result = await executor.run(
            project_id=project_id,
            user_id=current_user.id,
            payload=payload,
        )
        await db.commit()
    except ValueError as e:
        # job 级前置校验失败（试算表未就绪等）→ 422
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"三件套出具失败: {str(e)}") from e

    job_svc = ExportJobService(db)
    job = await job_svc.get_job(result.job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="任务创建后无法读取")
    items = await job_svc.get_job_items(result.job_id)
    resp = ExportJobResponse.model_validate(job)
    resp.items = [ExportJobItemResponse.model_validate(i) for i in items]
    return resp


# ---------------------------------------------------------------------------
# GET /jobs/{job_id} — job 状态查询（readonly + 属主项目校验）
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}", response_model=ExportJobResponse)
async def get_trio_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询三件套 job 状态与逐项明细。

    权限：项目 ``readonly``。铁律㉗：除路径 project_id 外，必须校验
    ``job.project_id == project_id``（防跨项目越权读他人 job）。
    """
    from app.services.export_job_service import ExportJobService

    job_svc = ExportJobService(db)
    job = await job_svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.project_id != project_id:
        raise HTTPException(status_code=403, detail="任务不属于该项目")

    items = await job_svc.get_job_items(job_id)
    resp = ExportJobResponse.model_validate(job)
    resp.items = [ExportJobItemResponse.model_validate(i) for i in items]
    return resp


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/attempts — append-only 尝试历史（readonly + 属主校验）
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/attempts", response_model=list[ExportJobAttemptResponse])
async def get_trio_job_attempts(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """返回整个 job 的完整尝试历史（含原始失败原因、单调编号）。

    权限：项目 ``readonly`` + job 属主校验。前端刷新不得用空数组覆盖历史。
    """
    from app.services.export_job_service import ExportJobService

    job_svc = ExportJobService(db)
    job = await job_svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.project_id != project_id:
        raise HTTPException(status_code=403, detail="任务不属于该项目")

    attempts = await job_svc.get_job_attempts(job_id)
    return [ExportJobAttemptResponse.model_validate(a) for a in attempts]


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/retry — 重试失败项（edit + 属主校验 + 快照冲突 409）
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/retry")
async def retry_trio_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """重试三件套 job 的失败项（真正重跑步骤，非仅复位状态）。

    权限：项目 ``edit``（非成员 / 只读成员 403，且 403 零写入）。
    铁律㉗：校验 job 属主项目。快照已变化 ⇒ ``SnapshotMismatchError`` → 409，
    绝不在旧快照上混用新数据（需求 5.1/5.5）。service 只 flush，router 统一 commit。
    """
    from app.services.export_job_service import ExportJobService
    from app.services.full_deliverables_executor import SnapshotMismatchError

    job_svc = ExportJobService(db)
    job = await job_svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.project_id != project_id:
        raise HTTPException(status_code=403, detail="任务不属于该项目")

    try:
        retried = await job_svc.retry_failed(
            job_id,
            user_id=current_user.id,
            requesting_project_id=project_id,
        )
        await db.commit()
        return {"job_id": str(job_id), "retried_count": retried}
    except SnapshotMismatchError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=e.message) from e
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"重试失败: {str(e)}") from e


# ---------------------------------------------------------------------------
# GET /items/{item_id}/download — 正式项下载（readonly + 物理指纹校验）
# ---------------------------------------------------------------------------

_MEDIA_BY_SUFFIX = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
}


@router.get("/items/{item_id}/download")
async def download_trio_item(
    project_id: UUID,
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """下载三件套某正式项的文件。

    权限：项目 ``readonly`` + item 所属 job 的属主项目校验（铁律㉗）。
    返回文件前**再次**执行物理校验（存在/可读/大小>0/SHA-256 与记录一致，
    需求 3.5）：任一失败返回明确中文错误，绝不返回空响应或被篡改文件冒充交付。
    """
    from app.services.deliverable_file_fingerprint import (
        FileFingerprintError,
        verify_file_fingerprint,
    )
    from app.services.export_job_service import ExportJobService

    job_svc = ExportJobService(db)
    item = await job_svc.get_job_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="交付项不存在")

    # 铁律㉗：item 不带 project_id，必须经所属 job 校验归属（防跨项目越权下载）。
    job = await job_svc.get_job(item.job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=403, detail="交付项不属于该项目")

    if not item.file_path:
        raise HTTPException(status_code=404, detail="文件尚未生成")

    # 下载前物理指纹校验（需求 3.5）：文件缺失 / 被截断 / 被篡改 / 哈希不一致 → 明确中文错误。
    try:
        verify_file_fingerprint(
            item.file_path,
            expected_sha256=item.file_sha256,
            expected_size=item.file_size,
        )
    except FileFingerprintError as e:
        # missing_file → 404；其余（空文件 / 哈希不一致 / 路径逃逸）→ 409 冲突，均不返回文件。
        status_code = 404 if e.code == "missing_file" else 409
        raise HTTPException(status_code=status_code, detail=e.message) from e

    file_path = Path(item.file_path)
    media_type = _MEDIA_BY_SUFFIX.get(
        file_path.suffix.lower(), "application/octet-stream"
    )
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type,
    )
