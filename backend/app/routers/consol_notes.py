"""合并附注 API 路由

覆盖:
- POST /api/consolidation/notes/{project_id}/{year}/reaggregate  重新汇总（所选节点子树逐节点拉数 / 差额 / 汇总）
- GET/PUT /api/consolidation/notes/{project_id}/config/consol-note-gray  试算表事件自动刷新合并附注的项目级开关

合并附注章节的读写、明细映射、按公式填入见 ``consol_note_sections`` / ``consol_note_formulas`` 等路由。
旧的合并附注生成 / 整合 / 保存端点与「查看合并明细」（V2 汇总器，mock 章节映射、生产从未启用）已于
2026-10-22 下线（spec consol-note-header-library-and-node-reaggregate R6.1）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import check_consol_lock, require_project_access
from app.core.database import get_db

router = APIRouter(
    prefix="/api/consolidation/notes",
    tags=["合并附注"],
)


# ---------------------------------------------------------------------------
# 重新汇总端点
# ---------------------------------------------------------------------------


class ReaggregateRequest(BaseModel):
    """节点感知的重新汇总请求；旧客户端可省略新增字段。"""
    section_ids: list[str] | None = None  # None = 当前附注模板的全部章节
    node_key: str | None = None
    standard: str | None = None
    template_type: str | None = None
    force: bool = False  # True = 忽略 stale 状态强制重算（共享公式内核始终按请求执行）


class ReaggregateResponse(BaseModel):
    """重新汇总响应，保留旧计数字段并暴露逐章节持久化证据。

    ``mode="subtree"``：所选节点子树逐节点更新 + 自下而上汇总；``results`` 只放所选节点的逐章节结果，
    ``nodes`` 是子树每个节点的写入 / 跳过 / 失败计数与原因，``pending_entities`` 是需到「📋 明细映射」
    确认映射的企业。
    """
    success: bool
    status: str
    project_id: UUID
    year: int
    node_key: str | None = None
    legacy_null: bool = False
    template_type: str
    sections_processed: int
    sections_updated: int
    results: list[dict] = []
    failures: list[dict] = []
    errors: list[str] = []
    mode: str = "subtree"
    nodes: list[dict] = []
    pending_entities: list[dict] = []


@router.post(
    "/{project_id}/{year}/reaggregate",
    response_model=ReaggregateResponse,
)
async def reaggregate_consol_notes(
    project_id: UUID,
    year: int,
    request: ReaggregateRequest | None = None,
    node_key: str | None = Query(None, description="企业树节点；与 body.node_key 同时传入时必须一致"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """重新汇总：所选节点（缺省为根合并节点）子树逐节点更新 —— 数据叶子按已确认映射从单体附注拉数、
    差额节点按抵销 / 调整分录算差额、汇总节点 = Σ 直接下级 + 差额 —— 自下而上汇总到所选节点。"""
    from app.services.consol_note_aggregation_service import validate_lineage_dag
    from app.services.consol_note_formula_service import NoteFormulaError, note_template_type
    from app.services.consol_note_subtree_reaggregate import reaggregate_subtree
    from app.services.consol_node_scope import (
        NodeScopeError,
        resolve_node_scope,
        resolve_requested_node_key,
    )

    request = request or ReaggregateRequest()
    try:
        resolved_node_key = resolve_requested_node_key(
            node_key,
            request.model_dump(exclude_none=True),
        )
        scope = await resolve_node_scope(db, project_id, year, resolved_node_key)
        if not await validate_lineage_dag(project_id, db):
            raise HTTPException(status_code=400, detail="合并层级链存在循环引用，无法汇总")
        if request.standard and request.template_type and note_template_type(request.standard) != note_template_type(request.template_type):
            raise NoteFormulaError(
                f"standard={request.standard} 与 template_type={request.template_type} 指向不同附注模板"
            )
        result = await reaggregate_subtree(
            db,
            project_id,
            scope.year,
            node_key=scope.node_key,
            section_ids=request.section_ids,
            template_type=request.template_type or request.standard,
            tree=scope.tree,
        )
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except (NoteFormulaError, NodeScopeError) as exc:
        await db.rollback()
        raise HTTPException(status_code=getattr(exc, "status", 400), detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        raise

    errors = [f"{item['section_id']}: {item['error']}" for item in result["failures"]]
    return ReaggregateResponse(
        success=not result["failures"],
        status=result["status"],
        project_id=project_id,
        year=year,
        node_key=result["node_key"],
        legacy_null=False,
        template_type=result["template_type"],
        sections_processed=result["sections_processed"],
        sections_updated=result["sections_updated"],
        results=result["results"],
        failures=result["failures"],
        errors=errors[:10],
        mode=result["mode"],
        nodes=result["nodes"],
        pending_entities=result["pending_entities"],
    )


# ---------------------------------------------------------------------------
# 试算表事件自动刷新合并附注的项目级开关（consol-disclosure-note-persistence Req5）
# ---------------------------------------------------------------------------
#
# 开关名沿用 V2 时期（wizard_state.consol_notes_v2_enabled / CONSOL_NOTES_V2_ENABLED），现只门控
# ``consol_note_formula_refresh_handler``：试算表更新后按公式刷新合并附注（从单体附注拉来的数只标待更新）。
# 路由 {project_id}/config/consol-note-gray 为 3 段静态路径（第二段字面 config），
# 与 {project_id}/{year}/reaggregate 不冲突。


class ConsolNoteGrayResponse(BaseModel):
    """试算表事件自动刷新合并附注的开关状态"""
    project_enabled: bool          # 项目级 opt-in（wizard_state.consol_notes_v2_enabled）
    global_enabled: bool           # 全局开关 CONSOL_NOTES_V2_ENABLED
    effective_enabled: bool        # 生效值（global OR project）


class ConsolNoteGrayUpdateRequest(BaseModel):
    """设置项目级 opt-in"""
    enabled: bool


@router.get(
    "/{project_id}/config/consol-note-gray",
    response_model=ConsolNoteGrayResponse,
)
async def get_consol_note_gray(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """读取试算表事件自动刷新合并附注的开关（项目级 opt-in / 全局 / 生效值）。"""
    import sqlalchemy as sa
    from app.core.config import settings
    from app.models.core import Project

    global_enabled = getattr(settings, "CONSOL_NOTES_V2_ENABLED", False) is True

    result = await db.execute(
        sa.select(Project.wizard_state).where(
            Project.id == project_id,
            Project.is_deleted == sa.false(),
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    ws = row[0]
    project_enabled = bool(ws.get("consol_notes_v2_enabled", False)) if isinstance(ws, dict) else False

    return ConsolNoteGrayResponse(
        project_enabled=project_enabled,
        global_enabled=global_enabled,
        effective_enabled=global_enabled or project_enabled,
    )


@router.put(
    "/{project_id}/config/consol-note-gray",
    response_model=ConsolNoteGrayResponse,
)
async def update_consol_note_gray(
    project_id: UUID,
    payload: ConsolNoteGrayUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
):
    """设置试算表事件自动刷新合并附注的项目级 opt-in（现场经理+ 编辑权限）。

    写 project.wizard_state.consol_notes_v2_enabled（JSONB，flag_modified 就地改落库）。
    全局开关 True 时本 opt-in 不影响生效值（生效恒 True，向后兼容）。
    """
    import sqlalchemy as sa
    from sqlalchemy.orm.attributes import flag_modified
    from app.core.config import settings
    from app.models.core import Project

    result = await db.execute(
        sa.select(Project).where(
            Project.id == project_id,
            Project.is_deleted == sa.false(),
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    ws = project.wizard_state if isinstance(project.wizard_state, dict) else {}
    ws["consol_notes_v2_enabled"] = bool(payload.enabled)
    project.wizard_state = ws
    flag_modified(project, "wizard_state")
    await db.commit()

    global_enabled = getattr(settings, "CONSOL_NOTES_V2_ENABLED", False) is True
    project_enabled = bool(payload.enabled)
    return ConsolNoteGrayResponse(
        project_enabled=project_enabled,
        global_enabled=global_enabled,
        effective_enabled=global_enabled or project_enabled,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 集团模板下推（V204，spec: consol-note-template-push-to-subsidiaries）
# ═══════════════════════════════════════════════════════════════════════════════


class PushTemplateRequest(BaseModel):
    """下推集团模板到子企业的请求。"""
    template_version_id: str
    section_ids: list[str] | None = None  # None = 全部已绑定章节
    activate_lock: bool = True


class PushTemplateResponse(BaseModel):
    """下推结果。"""
    success: bool
    results: list[dict[str, Any]] = []
    total_entities: int = 0
    total_success: int = 0
    total_failure: int = 0


@router.post(
    "/{project_id}/{year}/push-template",
    response_model=PushTemplateResponse,
)
async def push_template_to_subsidiaries(
    project_id: UUID,
    year: int,
    request: PushTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(require_project_access("edit")),
):
    """下推集团附注模板到各子企业——在子企业附注中预生成行骨架。

    合并负责人定义好集团级披露模板后，通过此端点一键推送到全部子企业。
    固定行锁定不可删改名，可选行子企业可以取消，动态行区子企业可自行添加。
    """
    from app.services.consol_note_template_push_service import push_template_to_subsidiaries as push_svc
    from app.services.consol_note_detail_template_service import get_bindings

    version_id = UUID(request.template_version_id)

    if request.section_ids:
        sections = request.section_ids
    else:
        # 全部已绑定章节
        bindings = await get_bindings(db, project_id)
        sections = [b["section_id"] for b in bindings]
        if not sections:
            return PushTemplateResponse(success=False, results=[], total_entities=0)

    all_results = []
    total_e = total_s = total_f = 0

    for sid in sections:
        result = await push_svc(
            db,
            consol_project_id=project_id,
            section_id=sid,
            year=year,
            template_version_id=version_id,
            pushed_by=current_user.id if hasattr(current_user, "id") else None,
            activate_lock=request.activate_lock,
        )
        all_results.append(result.to_dict())
        total_e += result.entity_count
        total_s += result.success_count
        total_f += result.failure_count

    await db.commit()

    return PushTemplateResponse(
        success=total_f == 0,
        results=all_results,
        total_entities=total_e,
        total_success=total_s,
        total_failure=total_f,
    )
