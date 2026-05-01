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

from app.deps import get_current_user
from app.models.core import User
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


# ── 附注校验预设公式（供公式管理中心一键导入） ──

@router.get("/api/note-templates/preset-formulas/{template_type}")
async def get_note_preset_formulas(template_type: str):
    """获取附注校验预设公式列表（从 check_presets 生成）

    template_type: soe 或 listed
    返回该模板类型下所有章节的预设校验公式
    """
    import json
    import os
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "note_check_preset_formulas.json"
    )
    if not os.path.exists(data_path):
        return []
    with open(data_path, "r", encoding="utf-8") as f:
        all_presets = json.load(f)
    key = template_type.lower()
    if key not in ("soe", "listed"):
        raise HTTPException(status_code=400, detail="template_type 必须是 soe 或 listed")
    return all_presets.get(key, [])


# ── 报表Excel公式预设（供公式管理中心加载） ──

@router.get("/api/report-templates/excel-formulas/{template_type}")
async def get_report_excel_formulas(template_type: str):
    """获取报表Excel模板中的计算公式

    template_type: soe 或 listed
    返回按sheet分组的公式列表
    """
    import json
    import os
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "report_excel_formulas.json"
    )
    if not os.path.exists(data_path):
        return {}
    with open(data_path, "r", encoding="utf-8") as f:
        all_formulas = json.load(f)
    key = template_type.lower()
    if key not in ("soe", "listed"):
        raise HTTPException(status_code=400, detail="template_type 必须是 soe 或 listed")
    return all_formulas.get(key, {})
