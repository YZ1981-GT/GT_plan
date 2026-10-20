"""出品物溯源与章节状态查询端点 — deliverable-lineage-and-writeback Task 5.1/17.1/17.2/17.3

GET /api/projects/{project_id}/deliverables/{word_export_task_id}/trace
    溯源查询（项目成员 readonly），2s 超时返回明确错误（需求 10.1）

GET /api/projects/{project_id}/deliverables/{word_export_task_id}/section-states
    章节状态查询（项目成员 readonly）

POST /api/projects/{project_id}/deliverables/{word_export_task_id}/writeback
    回填触发，终态拒绝（需求 7.1, 10.2, 10.3, 10.4, 11.1）

POST /api/projects/{project_id}/deliverables/{word_export_task_id}/refresh-section
    单章节增量刷新（需求 5.1, 10.3, 10.4, 11.1）

POST /api/projects/{project_id}/deliverables/{word_export_task_id}/refresh-stale
    批量刷新所有过期章节（需求 5.7, 10.2, 10.3, 10.4, 11.1）

鉴权：回填 / 刷新与交付中心同一判定 ``deliverable._guard_action``（项目成员 review 及以上 + 角色矩阵 +
EQCR 只读）—— 原为 edit 级，合伙人 / 经理（项目里是 review 级）用不了（2026-10-19 用户拍板放开）。
五个端点都先校验交付件属于路径上的项目（``_ensure_task_in_project``）。

Requirements: 1.1, 3.1, 5.1, 5.7, 7.1, 10.1, 10.2, 10.3, 10.4, 11.1, 11.3
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_project_access
from app.models.core import User
from app.routers.deliverable import _guard_action
from app.services.audit_logger_enhanced import audit_logger
from app.services.deliverable_permissions import DeliverableAction
from app.services.deliverable_section_state_service import DeliverableSectionStateService
from app.services.linkage_facade_service import LinkageFacadeService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/deliverables/{word_export_task_id}",
    tags=["deliverable-lineage"],
)

# ---------------------------------------------------------------------------
# Terminal state constants — deliverables in these states forbid writeback/refresh
# (needs 11.1/11.3, reuse TERMINAL_REEXPORT_STATUSES concept)
# ---------------------------------------------------------------------------

TERMINAL_STATUSES = frozenset({"signed", "confirmed", "archived"})

# 🔴 「> 100 节转异步」已删除（2026-10-17）：export_jobs_v2 全仓无 worker 处理 deliverable_writeback，走到即 500；
# 报告正文章节数远小于 100，回填一律同步执行。原 ASYNC_SECTION_THRESHOLD / _delegate_to_async_job 一并移除。


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------


class WritebackRequest(BaseModel):
    year: int
    resolutions: dict[str, str] | None = None


def _group_writeback_receipt(result: dict) -> dict:
    """把 WritebackResult 五桶归并为「已回填 / 已拒绝 / 未回填」三组回执（AC-3.2）。

    - 已回填 = ``written``；
    - 已拒绝 = ``rejected``（护栏 TABLE/TITLE 变更），拒绝原因取 ``rejection_reason``；
    - 未回填 = ``skipped``（锚点丢失）+ ``failed``（写入 0 行 / 派生段落），各带可读原因。

    原始五桶键原样保留（前端 WritebackResultPanel 仍按 written/rejected/... 读），
    新增 ``receipt`` 为 additive 分组视图：拒绝原因**只认后端字段 ``rejection_reason``**，
    不再出现「前端读 item.reason 恒空」的历史缺陷（需求 §1.2）。
    """
    written = list(result.get("written") or [])
    rejected_items = result.get("rejected") or []
    skipped = list(result.get("skipped") or [])
    failed_items = result.get("failed") or []

    rejected_group = [
        {
            "section_code": item.get("section_code"),
            "rejection_reason": item.get("rejection_reason"),
        }
        for item in rejected_items
    ]
    not_filled_group = (
        [
            {"section_code": code, "reason": "无法定位锚点，未回填"}
            for code in skipped
        ]
        + [
            {
                "section_code": item.get("section_code"),
                "reason": item.get("reason"),
            }
            for item in failed_items
        ]
    )

    return {
        **result,
        "receipt": {
            "filled": written,  # 已回填
            "rejected": rejected_group,  # 已拒绝（含 rejection_reason）
            "not_filled": not_filled_group,  # 未回填（锚点丢失 / 写入失败）
            "counts": {
                "filled": len(written),
                "rejected": len(rejected_group),
                "not_filled": len(not_filled_group),
            },
        },
    }


class RefreshSectionRequest(BaseModel):
    year: int
    section_code: str
    confirm_overwrite: bool = False


class RefreshStaleRequest(BaseModel):
    year: int
    confirm_overwrite: bool = False


async def _ensure_task_in_project(db: AsyncSession, word_export_task_id: UUID, project_id: UUID) -> None:
    """交付件必须属于路径上的项目 —— 否则本项目成员凭别的项目的交付件 id 就能读溯源、刷新或回填。"""
    from sqlalchemy import select

    from app.models.phase13_models import WordExportTask

    owner = (
        await db.execute(select(WordExportTask.project_id).where(WordExportTask.id == word_export_task_id))
    ).scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    if owner != project_id:
        raise HTTPException(status_code=403, detail="交付物不属于该项目")


@router.get("/trace")
async def trace_deliverable(
    project_id: UUID,
    word_export_task_id: UUID,
    section_code: str = Query(..., description="章节编码（如 八、1）"),
    year: int | None = Query(default=None, description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """出品物章节溯源查询。

    调用 LinkageFacadeService.trace(source_type='deliverable')，
    source_id = '{word_export_task_id}:{section_code}'。
    2 秒超时返回明确错误（需求 10.1）。
    """
    await _ensure_task_in_project(db, word_export_task_id, project_id)
    source_id = f"{word_export_task_id}:{section_code}"
    facade = LinkageFacadeService(db)

    try:
        contracts = await asyncio.wait_for(
            facade.trace(
                project_id=project_id,
                source_type="deliverable",
                source_id=source_id,
                year=year,
            ),
            timeout=2.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="溯源查询超时（超过 2 秒），请稍后重试",
        )

    # 补充章节级 stale 状态
    dss = DeliverableSectionStateService(db)
    states = await dss.get_section_states(word_export_task_id)
    section_state = next(
        (s for s in states if s["section_code"] == section_code),
        None,
    )

    return {
        "contracts": contracts,
        "section_state": section_state,
    }


@router.get("/section-states")
async def get_section_states(
    project_id: UUID,
    word_export_task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """出品物章节状态列表查询。

    返回所有章节的 stale 状态 + 锚点 + 快照哈希。
    """
    await _ensure_task_in_project(db, word_export_task_id, project_id)
    dss = DeliverableSectionStateService(db)
    sections = await dss.get_section_states(word_export_task_id)
    return {"sections": sections}



# ---------------------------------------------------------------------------
# Helper: terminal state check (needs 11.1/11.3)
# ---------------------------------------------------------------------------


async def _load_task_gate_fields(
    db: AsyncSession,
    word_export_task_id: UUID,
) -> tuple[str | None, str | None]:
    """一次查询取出门控所需两列：``(status, doc_type)``。

    合并为单次查询的理由：终态检查与能力门控在同一请求里背靠背执行，拆两次
    ``SELECT`` 是白付一次往返；且拆开后「任务不存在」在两处各判一次，语义容易漂移。

    两列都可能为 ``None``：任务不存在 → ``(None, None)``；老数据缺列 → 该列 None。
    调用方必须把 ``None`` 当「未知」而不是「已知的某个值」处理（见
    ``_require_capability`` 的 fail-open 说明）。
    """
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT status, doc_type FROM word_export_task WHERE id = :tid"),
        {"tid": str(word_export_task_id)},
    )
    row = result.first()
    if row is None:
        return None, None
    status = row[0] if len(row) > 0 else None
    # 索引 1 可能不存在（测试替身只备了 status 一列）→ 视为 doc_type 未知
    doc_type = row[1] if len(row) > 1 else None
    return status, doc_type


async def _check_terminal_state(
    db: AsyncSession,
    word_export_task_id: UUID,
) -> str | None:
    """Check if deliverable is in terminal state. Returns status if terminal, None otherwise."""
    status, _ = await _load_task_gate_fields(db, word_export_task_id)
    if status in TERMINAL_STATUSES:
        return status
    return None


# ---------------------------------------------------------------------------
# Helper: doc_type 能力门控（spec deliverable-lineage-wiring-… 需求 6.4）
# ---------------------------------------------------------------------------


async def _get_doc_type(db: AsyncSession, word_export_task_id: UUID) -> str | None:
    """读交付件 doc_type；读不到返回 None（=未知，不等于「不支持」）。"""
    _, doc_type = await _load_task_gate_fields(db, word_export_task_id)
    return doc_type


async def _require_capability(
    db: AsyncSession,
    word_export_task_id: UUID,
    *,
    kind: str,
) -> str | None:
    """校验该交付件类型是否支持 writeback / section_refresh。

    服务端硬校验（需求 6.4）：不依赖前端门控 —— 前端只是隐藏按钮，
    直接 POST 仍会打到端点；历史缺陷是 xlsx 交付件回填后返回「成功」但零写入。
    """
    from app.services.deliverable_capabilities import (
        section_refresh_unsupported_message,
        supports_section_refresh,
        supports_writeback,
        writeback_unsupported_message,
    )

    doc_type = await _get_doc_type(db, word_export_task_id)

    # 🔴 「读不到 doc_type」是**未知**，不是「已知不支持」——两者必须分开：
    # 任务不存在 / 老数据缺列时若一律拒绝，会把真实的 404 掩盖成「该类型不支持回填」，
    # 让人以为是能力问题而不是数据问题。此处 fail-open 交下游（下游取不到版本文件
    # 会给出准确错误）；门控只拦「确实读到了某个不支持的 doc_type」。
    if doc_type is None:
        logger.warning(
            "[DELIVERABLE_CAPABILITY] doc_type 未知，跳过能力门控交由下游处理: "
            "task=%s kind=%s",
            word_export_task_id,
            kind,
        )
        return None

    if kind == "writeback":
        if not supports_writeback(doc_type):
            raise HTTPException(
                status_code=400, detail=writeback_unsupported_message(doc_type)
            )
    else:
        if not supports_section_refresh(doc_type):
            raise HTTPException(
                status_code=400,
                detail=section_refresh_unsupported_message(doc_type),
            )
    return doc_type


# ---------------------------------------------------------------------------
# POST /writeback — 回填触发（仅 audit_report；附注已下线）
# ---------------------------------------------------------------------------


@router.post("/writeback")
async def writeback_deliverable(
    project_id: UUID,
    word_export_task_id: UUID,
    body: WritebackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """出品物报告正文回填（显式按钮触发）。

    权限: 交付中心同一判定（项目成员 review 及以上 + 角色矩阵 + EQCR 只读，无权限 403，需求 10.3）
    终态: signed/confirmed/archived 拒绝（需求 11.1/11.3）
    能力门控: 仅 audit_report 可回填；附注已下线（disclosure_notes → 400，US-2）
    提交: service 只 flush，路由成功后 `await db.commit()`（修 get_db 不自动提交，US-3 AC-3.2）
    回执: 「已回填 / 已拒绝 / 未回填」三组，拒绝原因显示 rejection_reason（AC-3.2）
    审计日志: 写 app_audit_log（需求 10.4）
    """
    await _guard_action(db, current_user, project_id, DeliverableAction.edit)
    await _ensure_task_in_project(db, word_export_task_id, project_id)
    # 终态检查（needs 11.1/11.3）
    terminal_status = await _check_terminal_state(db, word_export_task_id)
    if terminal_status:
        raise HTTPException(
            status_code=409,
            detail=f"该出品物已{terminal_status}，不可回填或刷新；如需修改请走撤回/解锁流程",
        )

    # doc_type 能力门控（需求 6.4）：服务端硬校验，不依赖前端隐藏按钮。
    # 🔴 附注已下线（2026-10-17 方向裁定）：disclosure_notes 命中即 400（见 writeback_unsupported_message）。
    # 当前仅 audit_report 可回填。
    await _require_capability(db, word_export_task_id, kind="writeback")

    # 章节数仅用于审计计数；「> 100 节转异步」分支已删除——全仓无 worker 处理该 job，走到即 500，
    # 且报告正文章节数远小于 100。回填一律同步执行。
    dss = DeliverableSectionStateService(db)
    sections = await dss.get_section_states(word_export_task_id)

    # 同步执行回填
    from app.services.deliverable_writeback_service import DeliverableWritebackService

    writeback_svc = DeliverableWritebackService(db)
    try:
        result = await writeback_svc.writeback(
            word_export_task_id=word_export_task_id,
            project_id=project_id,
            year=body.year,
            actor_id=current_user.id,
            resolutions=body.resolutions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # 写审计日志（needs 10.4）
    await audit_logger.log_action(
        user_id=current_user.id,
        action="deliverable_writeback",
        object_type="deliverable",
        object_id=word_export_task_id,
        project_id=project_id,
        details={"year": body.year, "section_count": len(sections), "has_resolutions": body.resolutions is not None},
    )

    # 🔴 service 只 flush，get_db 不自动提交 —— 历史缺陷是回填写入随会话关闭回滚、界面却提示成功。
    # 报告正文回填成功后必须由路由统一提交。
    await db.commit()

    # 回执按「已回填 / 已拒绝 / 未回填」分组，拒绝原因显示 rejection_reason（AC-3.2）。
    # 原始五桶键保留以兼容既有前端；additive 的 receipt 为三组视图。
    return _group_writeback_receipt(result)


# ---------------------------------------------------------------------------
# POST /refresh-section — 单章节增量刷新（needs 5.1, 10.3, 10.4, 11.1/11.3）
# ---------------------------------------------------------------------------


@router.post("/refresh-section")
async def refresh_section(
    project_id: UUID,
    word_export_task_id: UUID,
    body: RefreshSectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """单章节增量刷新。

    权限: 交付中心同一判定（项目成员 review 及以上 + 角色矩阵 + EQCR 只读，无权限 403，需求 10.3）
    终态: signed/confirmed/archived 拒绝（需求 11.1/11.3）
    审计日志: 写 app_audit_log（需求 10.4）
    """
    await _guard_action(db, current_user, project_id, DeliverableAction.export)
    await _ensure_task_in_project(db, word_export_task_id, project_id)
    # 终态检查（needs 11.1/11.3）
    terminal_status = await _check_terminal_state(db, word_export_task_id)
    if terminal_status:
        raise HTTPException(
            status_code=409,
            detail=f"该出品物已{terminal_status}，不可回填或刷新；如需修改请走撤回/解锁流程",
        )

    # doc_type 能力门控（需求 6.4）
    await _require_capability(db, word_export_task_id, kind="section_refresh")

    # 写审计日志（needs 10.4）
    await audit_logger.log_action(
        user_id=current_user.id,
        action="deliverable_refresh_section",
        object_type="deliverable",
        object_id=word_export_task_id,
        project_id=project_id,
        details={
            "year": body.year,
            "section_code": body.section_code,
            "confirm_overwrite": body.confirm_overwrite,
        },
    )

    # Call DeliverableRefreshService
    from app.services.deliverable_refresh_service import DeliverableRefreshService

    refresh_svc = DeliverableRefreshService(db)
    try:
        result = await refresh_svc.refresh_section(
            word_export_task_id=word_export_task_id,
            project_id=project_id,
            year=body.year,
            section_code=body.section_code,
            actor_id=current_user.id,
            confirm_overwrite=body.confirm_overwrite,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # service 只 flush：新版本记录与章节状态由路由统一提交（get_db 不自动提交 —— 原实现漏了这一步，
    # 新版本文件落了盘、版本记录与「清过期」却随会话关闭回滚）
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# POST /refresh-stale — 批量刷新所有过期章节（needs 5.7, 10.2, 10.3, 10.4, 11.1/11.3）
# ---------------------------------------------------------------------------


@router.post("/refresh-stale")
async def refresh_stale(
    project_id: UUID,
    word_export_task_id: UUID,
    body: RefreshStaleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量刷新所有过期章节。

    权限: 交付中心同一判定（项目成员 review 及以上 + 角色矩阵 + EQCR 只读，无权限 403，需求 10.3）
    终态: signed/confirmed/archived 拒绝（需求 11.1/11.3）
    同步执行：刷新是「一次同口径重新导出 + 逐节移植」，耗时与过期章节数无关（spec deliverable-trio-generation-accuracy
    §7.2）。🔴 原「>100 节转异步」分支建的 export_jobs_v2 任务全仓没有 worker 处理 ⇒ 静默不执行、前端却提示已刷新，已删除。
    审计日志: 写 app_audit_log（需求 10.4）
    """
    await _guard_action(db, current_user, project_id, DeliverableAction.export)
    await _ensure_task_in_project(db, word_export_task_id, project_id)
    # 终态检查（needs 11.1/11.3）
    terminal_status = await _check_terminal_state(db, word_export_task_id)
    if terminal_status:
        raise HTTPException(
            status_code=409,
            detail=f"该出品物已{terminal_status}，不可回填或刷新；如需修改请走撤回/解锁流程",
        )

    # doc_type 能力门控（需求 6.4）
    await _require_capability(db, word_export_task_id, kind="section_refresh")

    # 获取 stale 章节（审计日志计数用）
    dss = DeliverableSectionStateService(db)
    sections = await dss.get_section_states(word_export_task_id)
    stale_sections = [s for s in sections if s.get("is_stale")]

    # 写审计日志（needs 10.4）
    await audit_logger.log_action(
        user_id=current_user.id,
        action="deliverable_refresh_stale",
        object_type="deliverable",
        object_id=word_export_task_id,
        project_id=project_id,
        details={
            "year": body.year,
            "stale_count": len(stale_sections),
            "confirm_overwrite": body.confirm_overwrite,
        },
    )

    # Call DeliverableRefreshService
    from app.services.deliverable_refresh_service import DeliverableRefreshService

    refresh_svc = DeliverableRefreshService(db)
    try:
        result = await refresh_svc.refresh_all_stale_sections(
            word_export_task_id=word_export_task_id,
            project_id=project_id,
            year=body.year,
            actor_id=current_user.id,
            confirm_overwrite=body.confirm_overwrite,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    await db.commit()  # 同 refresh-section：service 只 flush，路由统一提交
    return result
