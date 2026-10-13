"""合并附注明细模板与绑定 API

spec: consol-note-detail-template-and-mapping Phase 1 Task 4 + Phase 2 Task 12~13

模板 CRUD：
  POST   /api/consol-note-templates                          — 创建模板（附首版本）
  GET    /api/consol-note-templates                          — 列表
  GET    /api/consol-note-templates/{id}                     — 详情
  POST   /api/consol-note-templates/{id}/versions            — 追加版本
  GET    /api/consol-note-templates/{id}/versions            — 版本历史
  PUT    /api/consol-note-templates/{id}/visibility          — 改可见范围
  DELETE /api/consol-note-templates/{id}                     — 软删除
  POST   /api/consol-note-templates/{id}/check-row-deletion  — 检测删除行影响

绑定：
  PUT    /api/projects/{pid}/consol-note-template-binding/{section_id}  — 绑定/切换
  GET    /api/projects/{pid}/consol-note-template-binding               — 列表
  GET    /api/projects/{pid}/consol-note-template-binding/{section_id}  — 单个

刷新预览与建议（Phase 2）：
  POST   /api/projects/{pid}/consol-note-detail-refresh/preview           — 预览
  POST   /api/projects/{pid}/consol-note-detail-refresh/suggest-template  — 模板建议
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import check_consol_lock, get_current_user, require_project_access
from app.models.core import User
from app.services.consol_note_detail_template_service import (
    TemplateServiceError,
    add_version,
    bind_template_version,
    change_visibility,
    check_row_deletion_impact,
    create_template,
    get_binding,
    get_bindings,
    get_template,
    get_versions,
    list_templates,
    soft_delete_template,
)

router = APIRouter(tags=["consol-note-detail-templates"])


# ─── Request Models ──────────────────────────────────────────────────────────


class CreateTemplateRequest(BaseModel):
    template_type: str
    section_id: str
    name: str = ""
    visibility: str = "project"
    rows: list[dict] = Field(default_factory=list)
    change_note: str | None = None


class AddVersionRequest(BaseModel):
    rows: list[dict]
    change_note: str | None = None


class ChangeVisibilityRequest(BaseModel):
    visibility: str


class CheckRowDeletionRequest(BaseModel):
    target_row_ids: list[str]


class BindTemplateRequest(BaseModel):
    template_version_id: str
    confirm: bool = False


# ─── 错误转 HTTP ─────────────────────────────────────────────────────────────


def _raise(exc: TemplateServiceError) -> None:
    raise HTTPException(status_code=exc.status, detail={
        "error_code": exc.code,
        "message": exc.message,
        "detail": exc.detail,
    })


# ─── 模板 CRUD ───────────────────────────────────────────────────────────────


@router.post("/api/consol-note-templates")
async def api_create_template(
    body: CreateTemplateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建合并附注明细模板（附首版本 v1）。"""
    try:
        return await create_template(
            db,
            template_type=body.template_type,
            section_id=body.section_id,
            name=body.name,
            visibility=body.visibility,
            rows=body.rows,
            change_note=body.change_note,
            created_by=user.id,
        )
    except TemplateServiceError as exc:
        await db.rollback()
        _raise(exc)
    finally:
        await db.commit()


@router.get("/api/consol-note-templates")
async def api_list_templates(
    template_type: str | None = Query(None),
    section_id: str | None = Query(None),
    visibility: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出合并附注明细模板。"""
    return await list_templates(
        db,
        template_type=template_type,
        section_id=section_id,
        visibility=visibility,
    )


@router.get("/api/consol-note-templates/{template_id}")
async def api_get_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取单个合并附注明细模板详情。"""
    result = await get_template(db, template_id)
    if result is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    return result


@router.post("/api/consol-note-templates/{template_id}/versions")
async def api_add_version(
    template_id: UUID,
    body: AddVersionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """追加模板新版本（不可变）。"""
    try:
        result = await add_version(
            db, template_id,
            rows=body.rows,
            change_note=body.change_note,
            created_by=user.id,
        )
        await db.commit()
        return result
    except TemplateServiceError as exc:
        await db.rollback()
        _raise(exc)


@router.get("/api/consol-note-templates/{template_id}/versions")
async def api_get_versions(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查看模板版本历史。"""
    try:
        return await get_versions(db, template_id)
    except TemplateServiceError as exc:
        _raise(exc)


@router.put("/api/consol-note-templates/{template_id}/visibility")
async def api_change_visibility(
    template_id: UUID,
    body: ChangeVisibilityRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """修改模板可见范围。"""
    try:
        result = await change_visibility(db, template_id, visibility=body.visibility)
        await db.commit()
        return result
    except TemplateServiceError as exc:
        await db.rollback()
        _raise(exc)


@router.delete("/api/consol-note-templates/{template_id}")
async def api_delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """软删除模板。"""
    try:
        result = await soft_delete_template(db, template_id)
        await db.commit()
        return result
    except TemplateServiceError as exc:
        await db.rollback()
        _raise(exc)


@router.post("/api/consol-note-templates/{template_id}/check-row-deletion")
async def api_check_row_deletion(
    template_id: UUID,
    body: CheckRowDeletionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """检测删除模板行的影响（受影响规则数和企业数）。"""
    return await check_row_deletion_impact(db, template_id, body.target_row_ids)


# ─── 模板绑定 ────────────────────────────────────────────────────────────────


@router.put("/api/projects/{project_id}/consol-note-template-binding/{section_id}")
async def api_bind_template_version(
    project_id: UUID,
    section_id: str,
    body: BindTemplateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """项目绑定/切换合并附注明细模板版本。切换已有绑定需 confirm=true。"""
    try:
        result = await bind_template_version(
            db,
            project_id=project_id,
            section_id=section_id,
            template_version_id=UUID(body.template_version_id),
            bound_by=user.id,
            confirm=body.confirm,
        )
        await db.commit()
        return result
    except TemplateServiceError as exc:
        await db.rollback()
        _raise(exc)


@router.get("/api/projects/{project_id}/consol-note-template-binding")
async def api_get_bindings(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """查看当前项目所有章节的模板绑定。"""
    return await get_bindings(db, project_id)


@router.get("/api/projects/{project_id}/consol-note-template-binding/{section_id}")
async def api_get_binding(
    project_id: UUID,
    section_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """查看单个章节的模板绑定。"""
    result = await get_binding(db, project_id, section_id)
    if result is None:
        raise HTTPException(status_code=404, detail="该章节未绑定模板")
    return result


# ─── 刷新预览与建议（Phase 2） ───────────────────────────────────────────────


class PreviewRequest(BaseModel):
    section_id: str
    year: int


class SuggestTemplateRequest(BaseModel):
    section_id: str
    year: int


@router.post("/api/projects/{project_id}/consol-note-detail-refresh/preview")
async def api_preview_detail_refresh(
    project_id: UUID,
    body: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """预览明细刷新：读取来源、检测 stale、生成建议。只读不写数据（stale 标记除外）。"""
    from app.services.consol_note_detail_source_service import preview_detail_refresh

    result = await preview_detail_refresh(
        db,
        project_id=project_id,
        section_id=body.section_id,
        year=body.year,
    )
    await db.commit()  # stale 标记的 flush 需要 commit
    # 不返回内部 _token_data
    out = {k: v for k, v in result.items() if not k.startswith("_")}
    return out


@router.post("/api/projects/{project_id}/consol-note-detail-refresh/suggest-template")
async def api_suggest_template(
    project_id: UUID,
    body: SuggestTemplateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """扫描来源并生成模板行建议（按频率和金额排序）。"""
    from app.services.consol_note_detail_source_service import suggest_template_for_section

    return await suggest_template_for_section(
        db,
        project_id=project_id,
        section_id=body.section_id,
        year=body.year,
    )


# ─── 映射规则 CRUD + confirm_mapping（Phase 3） ──────────────────────────────


class CreateRuleRequest(BaseModel):
    section_id: str
    template_version_id: str
    source_structure_hash: str
    mappings: list[dict]


class UpgradeRuleRequest(BaseModel):
    mappings: list[dict]


class ConfirmMappingRequest(BaseModel):
    section_id: str
    year: int
    template_version_id: str
    source_structure_hash: str
    mappings: list[dict]
    entity_node_keys: list[dict]  # [{node_key, project_id, hash}]
    excluded_node_keys: list[str] = Field(default_factory=list)
    preview_token: str | None = None
    current_entity_hashes: dict[str, str] | None = None


@router.get("/api/projects/{project_id}/consol-note-mapping/rules")
async def api_get_rules(
    project_id: UUID,
    section_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """列出项目的活跃映射规则。"""
    from app.services.consol_note_mapping_rule_service import get_active_rules
    return await get_active_rules(db, project_id=project_id, section_id=section_id)


@router.post("/api/projects/{project_id}/consol-note-mapping/rules")
async def api_create_rule(
    project_id: UUID,
    body: CreateRuleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """创建映射规则（v1）。"""
    from app.services.consol_note_mapping_rule_service import MappingRuleError, create_rule
    try:
        result = await create_rule(
            db,
            project_id=project_id,
            section_id=body.section_id,
            template_version_id=UUID(body.template_version_id),
            source_structure_hash=body.source_structure_hash,
            mappings=body.mappings,
            confirmed_by=user.id,
        )
        await db.commit()
        return result
    except MappingRuleError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail={"error_code": exc.code, "message": exc.message, "detail": exc.detail})


@router.put("/api/projects/{project_id}/consol-note-mapping/rules/{rule_id}/deactivate")
async def api_deactivate_rule(
    project_id: UUID,
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """停用映射规则。"""
    from app.services.consol_note_mapping_rule_service import MappingRuleError, deactivate_rule
    try:
        result = await deactivate_rule(db, rule_id)
        await db.commit()
        return result
    except MappingRuleError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail={"error_code": exc.code, "message": exc.message})


@router.get("/api/projects/{project_id}/consol-note-mapping/rules/{rule_id}/versions")
async def api_get_rule_versions(
    project_id: UUID,
    rule_id: UUID,
    section_id: str = Query(...),
    source_structure_hash: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """查看映射规则版本历史。"""
    from app.services.consol_note_mapping_rule_service import get_rule_versions
    return await get_rule_versions(db, project_id=project_id, section_id=section_id, source_structure_hash=source_structure_hash)


@router.post("/api/projects/{project_id}/consol-note-detail-refresh/confirm-mapping")
async def api_confirm_mapping(
    project_id: UUID,
    body: ConfirmMappingRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """确认映射——校验 + 写规则 + 批量绑定。409 表示来源已变化需重新预览。"""
    from app.services.consol_note_mapping_rule_service import MappingRuleError, confirm_mapping
    try:
        result = await confirm_mapping(
            db,
            project_id=project_id,
            section_id=body.section_id,
            year=body.year,
            template_version_id=UUID(body.template_version_id),
            source_structure_hash=body.source_structure_hash,
            mappings=body.mappings,
            entity_node_keys=body.entity_node_keys,
            excluded_node_keys=body.excluded_node_keys,
            confirmed_by=user.id,
            preview_token=body.preview_token,
            current_entity_hashes=body.current_entity_hashes,
        )
        await db.commit()
        return result
    except MappingRuleError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail={"error_code": exc.code, "message": exc.message, "detail": exc.detail})


# ─── apply（Phase 4） ────────────────────────────────────────────────────────


class ApplyRequest(BaseModel):
    section_id: str
    year: int
    node_key: str | None = None
    preview_entity_hashes: dict[str, str] | None = None


@router.post("/api/projects/{project_id}/consol-note-detail-refresh/apply")
async def api_apply_detail_refresh(
    project_id: UUID,
    body: ApplyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """按已确认映射规则将来源行转换后写入合并附注。409 表示来源已变化。"""
    from app.services.consol_note_detail_apply_service import ApplyError, apply_detail_refresh
    try:
        result = await apply_detail_refresh(
            db,
            project_id=project_id,
            section_id=body.section_id,
            year=body.year,
            node_key=body.node_key,
            preview_entity_hashes=body.preview_entity_hashes,
        )
        await db.commit()
        return result
    except ApplyError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail={
            "error_code": exc.code, "message": exc.message, "detail": exc.detail,
        })
