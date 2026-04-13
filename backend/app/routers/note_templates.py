"""附注模版 API 路由

- POST /api/note-templates/validate       — 校验附注数据
- GET  /api/note-templates/soe            — 国企版附注模版
- GET  /api/note-templates/listed         — 上市版附注模版
- GET  /api/note-templates/custom         — 自定义模版列表
- POST /api/note-templates/custom         — 创建自定义模版
- GET  /api/note-templates/custom/{id}    — 自定义模版详情
- PUT  /api/note-templates/custom/{id}    — 更新自定义模版
- DELETE /api/note-templates/custom/{id}  — 删除自定义模版

Validates: Requirements 9.2-9.5
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.note_formula_engine import validate_note, Finding
from app.services.note_template_service import NoteTemplateService

router = APIRouter(tags=["note-templates"])


# ── Request / Response models ──

class ValidateNoteRequest(BaseModel):
    note_data: dict
    rule_types: list[str] | None = None


class CreateNoteTemplateRequest(BaseModel):
    name: str
    category: str
    sections: list[dict]
    description: str | None = None
    created_by: str | None = None


class UpdateNoteTemplateRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    sections: list[dict] | None = None
    description: str | None = None
    changed_by: str | None = None


class RollbackRequest(BaseModel):
    target_version: str


# ── 校验 ──

@router.post("/api/note-templates/validate")
async def validate_note_data(body: ValidateNoteRequest):
    """校验附注数据（双层架构：本地规则 + LLM兜底）"""
    findings = validate_note(body.note_data, body.rule_types)
    return {
        "findings": [
            {"rule_type": f.rule_type, "severity": f.severity, "message": f.message, "details": f.details}
            for f in findings
        ],
        "total": len(findings),
    }


# ── SOE / Listed 模版 ──

@router.get("/api/note-templates/soe")
async def get_soe_template():
    """获取国企版附注模版"""
    svc = NoteTemplateService()
    return svc.get_soe_template()


@router.get("/api/note-templates/listed")
async def get_listed_template():
    """获取上市版附注模版"""
    svc = NoteTemplateService()
    return svc.get_listed_template()


# ── 自定义模版 CRUD ──

@router.get("/api/note-templates/custom")
async def list_custom_templates(category: str | None = None):
    """列出自定义模版"""
    svc = NoteTemplateService()
    return svc.list_templates(category=category)


@router.post("/api/note-templates/custom")
async def create_custom_template(body: CreateNoteTemplateRequest):
    """创建自定义模版"""
    svc = NoteTemplateService()
    return svc.create_template(
        name=body.name,
        category=body.category,
        sections=body.sections,
        description=body.description,
        created_by=body.created_by,
    )


@router.get("/api/note-templates/custom/{template_id}")
async def get_custom_template(template_id: str):
    """获取自定义模版详情"""
    svc = NoteTemplateService()
    result = svc.get_template(template_id)
    if result is None:
        raise HTTPException(status_code=404, detail="模版不存在")
    return result


@router.put("/api/note-templates/custom/{template_id}")
async def update_custom_template(template_id: str, body: UpdateNoteTemplateRequest):
    """更新自定义模版"""
    svc = NoteTemplateService()
    try:
        updates = body.model_dump(exclude_none=True, exclude={"changed_by"})
        return svc.update_template(template_id, updates, changed_by=body.changed_by)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/api/note-templates/custom/{template_id}")
async def delete_custom_template(template_id: str):
    """删除自定义模版"""
    svc = NoteTemplateService()
    try:
        return svc.delete_template(template_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/note-templates/custom/{template_id}/versions")
async def get_template_versions(template_id: str):
    """获取模版版本历史"""
    svc = NoteTemplateService()
    try:
        return svc.get_version_history(template_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/note-templates/custom/{template_id}/rollback")
async def rollback_template(template_id: str, body: RollbackRequest):
    """回滚模版到指定版本"""
    svc = NoteTemplateService()
    try:
        return svc.rollback_version(template_id, body.target_version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
