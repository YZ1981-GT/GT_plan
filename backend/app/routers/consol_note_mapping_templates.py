"""合并附注映射规则模板 API

spec: consol-note-mapping-reuse-and-reference-push Phase 2 Task 6

端点：
  POST   /api/projects/{pid}/consol-note-mapping/rules/{rid}/promote  — 提升规则为模板
  GET    /api/consol-note-mapping-templates                           — 列出规则模板
  GET    /api/consol-note-mapping-templates/{tid}                     — 获取详情
  DELETE /api/consol-note-mapping-templates/{tid}                     — 停用模板
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.consol_note_mapping_template_service import (
    MappingTemplateError,
    deactivate_template,
    get_template,
    list_templates,
    promote_rule_to_template,
)

router = APIRouter(tags=["consol-note-mapping-templates"])


# ─── 错误转 HTTP ─────────────────────────────────────────────────────────────


def _raise(exc: MappingTemplateError) -> None:
    raise HTTPException(status_code=exc.status, detail={
        "error_code": exc.code,
        "message": exc.message,
        "detail": exc.detail,
    })


# ─── 端点 ────────────────────────────────────────────────────────────────────


@router.post("/api/projects/{project_id}/consol-note-mapping/rules/{rule_id}/promote")
async def promote_rule(
    project_id: UUID,
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """提升项目级映射规则为可复用模板。需 review 级权限。"""
    try:
        result = await promote_rule_to_template(
            db, rule_id=rule_id, promoted_by=current_user.id,
        )
        await db.commit()

        # SSE 通知：规则已提升为模板，其他项目可引用
        try:
            from app.services.event_bus import event_bus
            event_bus.broadcast_raw(
                "consol.note_mapping_template_promoted",
                {
                    "project_id": str(project_id),
                    "template_id": str(result.get("template_id", "")),
                    "section_id": result.get("section_id", ""),
                    "version_number": result.get("version_number", 1),
                },
            )
        except Exception:
            pass  # SSE 失败不阻断业务

        return result
    except MappingTemplateError as exc:
        _raise(exc)


@router.get("/api/consol-note-mapping-templates")
async def list_mapping_templates(
    template_type: str | None = Query(None, description="soe / listed"),
    section_id: str | None = Query(None, description="附注章节 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出映射规则模板（可按 template_type/section_id 筛选）。"""
    return await list_templates(
        db, template_type=template_type, section_id=section_id,
    )


@router.get("/api/consol-note-mapping-templates/{template_id}")
async def get_mapping_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个映射规则模板详情。"""
    result = await get_template(db, template_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"message": "规则模板不存在"})
    return result


@router.delete("/api/consol-note-mapping-templates/{template_id}")
async def deactivate_mapping_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """停用映射规则模板（soft delete）。需登录用户。"""
    try:
        result = await deactivate_template(db, template_id)
        await db.commit()
        return result
    except MappingTemplateError as exc:
        _raise(exc)



# ─── 标准科目参考端点（US-3 / Phase 3 Task 9） ──────────────────────────────


@router.get("/api/projects/{project_id}/consol-note-account-reference/{section_id}")
async def get_account_reference(
    project_id: UUID,
    section_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询某章节的集团推荐科目码。

    逻辑：查项目绑定的模板版本 → 读 rows 中有 recommended_account_codes 的行。
    """
    from app.models.consol_note_mapping_models import (
        ConsolNoteDetailTemplate,
        ConsolNoteDetailTemplateVersion,
        ConsolNoteTemplateBinding,
    )
    import sqlalchemy as sa

    # 查项目绑定
    binding = (await db.execute(
        sa.select(ConsolNoteTemplateBinding).where(
            ConsolNoteTemplateBinding.project_id == project_id,
            ConsolNoteTemplateBinding.section_id == section_id,
        )
    )).scalar_one_or_none()
    if binding is None:
        raise HTTPException(status_code=404, detail={"message": "该章节无模板绑定"})

    # 读版本
    version = (await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion).where(
            ConsolNoteDetailTemplateVersion.id == binding.template_version_id,
        )
    )).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail={"message": "绑定的模板版本不存在"})

    # 读模板获取 template_type
    template = (await db.execute(
        sa.select(ConsolNoteDetailTemplate).where(
            ConsolNoteDetailTemplate.id == version.template_id,
        )
    )).scalar_one_or_none()

    # 提取有推荐科目码的行
    rows_with_codes = []
    for row in (version.rows if isinstance(version.rows, list) else []):
        codes = row.get("recommended_account_codes")
        if codes and isinstance(codes, list):
            rows_with_codes.append({
                "target_row_id": row.get("target_row_id"),
                "canonical_name": row.get("canonical_name"),
                "recommended_account_codes": codes,
            })

    return {
        "project_id": str(project_id),
        "section_id": section_id,
        "template_type": template.template_type if template else None,
        "template_version_id": str(version.id),
        "rows": rows_with_codes,
    }



# ─── 值变化 stale 汇总端点（US-4 / Phase 4 Task 15） ────────────────────────


@router.get("/api/projects/{project_id}/consol-note-value/stale-summary")
async def stale_summary(
    project_id: UUID,
    section_id: str | None = Query(None, description="按章节筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """返回 stale 汇总：哪些章节的哪些子企业数据已更新但合并侧未刷新。"""
    from app.services.consol_note_value_change_service import get_stale_summary

    return await get_stale_summary(
        db, consol_project_id=project_id, section_id=section_id,
    )



# ─── 值确认端点（US-5 / Phase 5 Task 18） ───────────────────────────────────


class ConfirmValueRequest(BaseModel):
    section_id: str
    entity_node_key: str = "_self"
    value_hash: str


@router.post("/api/projects/{project_id}/consol-note-value/confirm")
async def confirm_value(
    project_id: UUID,
    body: ConfirmValueRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """确认某企业某章节的当前值。需 review 级权限。"""
    from app.services.consol_note_value_confirmation_service import confirm_entity_value

    result = await confirm_entity_value(
        db, project_id=project_id, section_id=body.section_id,
        entity_node_key=body.entity_node_key,
        confirmed_by=current_user.id, value_hash=body.value_hash,
    )
    await db.commit()
    return result


@router.get("/api/projects/{project_id}/consol-note-value/confirmation-status")
async def confirmation_status(
    project_id: UUID,
    section_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询确认状态汇总。"""
    from app.services.consol_note_value_confirmation_service import get_confirmation_status

    return await get_confirmation_status(
        db, project_id=project_id, section_id=section_id,
    )


@router.get("/api/projects/{project_id}/consol-note-value/readiness-check")
async def readiness_check(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """签发前闸门检查：所有映射章节所有子企业数据是否已确认定稿。"""
    from app.services.consol_note_value_confirmation_service import check_all_confirmed

    return await check_all_confirmed(db, consol_project_id=project_id)



# ─── 结构锁端点（US-6 / Phase 6 Task 22） ───────────────────────────────────


class ActivateLockRequest(BaseModel):
    section_id: str
    locked_version_id: str


@router.post("/api/projects/{project_id}/consol-note-structure-lock")
async def activate_structure_lock(
    project_id: UUID,
    body: ActivateLockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """激活结构锁。需 review 级权限。"""
    from app.services.consol_note_structure_lock_service import (
        StructureLockError, activate_lock,
    )

    try:
        result = await activate_lock(
            db, consol_project_id=project_id, section_id=body.section_id,
            locked_version_id=UUID(body.locked_version_id),
            locked_by=current_user.id,
        )
        await db.commit()
        return result
    except StructureLockError as exc:
        raise HTTPException(status_code=exc.status, detail={
            "error_code": exc.code, "message": exc.message, "detail": exc.detail,
        })


@router.delete("/api/projects/{project_id}/consol-note-structure-lock/{section_id}")
async def release_structure_lock(
    project_id: UUID,
    section_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """解除结构锁。需 review 级权限。"""
    from app.services.consol_note_structure_lock_service import (
        StructureLockError, release_lock,
    )

    try:
        result = await release_lock(
            db, consol_project_id=project_id, section_id=section_id,
            released_by=current_user.id,
        )
        await db.commit()
        return result
    except StructureLockError as exc:
        raise HTTPException(status_code=exc.status, detail={
            "error_code": exc.code, "message": exc.message, "detail": exc.detail,
        })


@router.get("/api/projects/{project_id}/consol-note-structure-lock")
async def list_structure_locks(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询某合并项目的所有活跃结构锁。"""
    from app.services.consol_note_structure_lock_service import get_locks

    return await get_locks(db, consol_project_id=project_id)
