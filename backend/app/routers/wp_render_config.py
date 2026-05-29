"""底稿渲染配置端点

GET /api/workpapers/{wp_id}/render-config
按 design §5.1.1 实现：获取底稿渲染 schema + 项目数据 + 跨底稿引用。

Requirements: 1.2, 3.0.3, 3.0.5
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import (
    WpCrossRef,
    WpIndex,
    WorkingPaper,
)
from app.services.wp_classification_service import (
    ClassificationNotFoundError,
    WpClassificationService,
    derive_component_type,
)
from app.services.wp_auto_fill_service import _resolve_auto_fill_values
from app.services.wp_render_schema_service import WpRenderSchemaService
from app.services.wp_template_version_service import WpTemplateVersionService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["wp-render-config"],
)

# ─── Singleton schema service (stateless + cache) ────────────────────────────
_schema_service = WpRenderSchemaService()


# ─── Response schemas ────────────────────────────────────────────────────────


class CrossRefItem(BaseModel):
    wp_code: str
    cell: str | None = None


class SheetRenderConfig(BaseModel):
    sheet_name: str
    componentType: str
    schema_: dict | None = None
    html_data: dict | None = None
    cross_refs: list[CrossRefItem] = []

    class Config:
        # Allow 'schema_' to be serialized as 'schema' in JSON
        populate_by_name = True

    def model_dump(self, **kwargs):
        """Override to rename schema_ → schema in output."""
        data = super().model_dump(**kwargs)
        data["schema"] = data.pop("schema_", None)
        return data


class RenderConfigResponse(BaseModel):
    wp_id: str
    wp_code: str
    project_id: str
    scope: str
    is_real_workpaper: bool
    template_version: str | None = None
    sheets: list[dict]  # Use dict to allow custom 'schema' key


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.get("/{wp_id}/render-config")
async def get_render_config(
    wp_id: UUID,
    sheet_name: str | None = Query(None, description="可选，仅返回单 sheet 数据"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取底稿渲染 schema + 项目数据 + 跨底稿引用。

    EARS:
    - IF wp_id 不存在 THEN 返回 404
    - IF scope = 'consolidated' OR 'parent_only' THEN 返回 redirect 提示
    - WHEN 项目 template_version_id IS NULL THEN 默认按 current version 返回 schema
    """
    # ─── Step 1: 查 working_paper 获取基本信息 ────────────────────────────
    wp_query = sa.select(WorkingPaper).where(
        WorkingPaper.id == wp_id,
        WorkingPaper.is_deleted == False,  # noqa: E712
    )
    wp_result = await db.execute(wp_query)
    working_paper = wp_result.scalars().first()

    if working_paper is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    project_id = working_paper.project_id

    # ─── Step 2: 查 wp_index 获取 wp_code ────────────────────────────────
    wp_index_query = sa.select(WpIndex).where(
        WpIndex.id == working_paper.wp_index_id,
        WpIndex.is_deleted == False,  # noqa: E712
    )
    wp_index_result = await db.execute(wp_index_query)
    wp_index = wp_index_result.scalars().first()

    if wp_index is None:
        raise HTTPException(status_code=404, detail="底稿索引不存在")

    wp_code = wp_index.wp_code

    # ─── Step 3: 获取模板版本 ────────────────────────────────────────────
    # 项目 template_version_id 通过 raw SQL 获取（ORM 模型未定义该列）
    # 注意：该列由 V018 迁移添加，已通过 ALTER TABLE 补齐
    project_template_version_id = None
    try:
        version_query = sa.text(
            "SELECT template_version_id FROM projects WHERE id = :pid"
        )
        version_result = await db.execute(version_query, {"pid": str(project_id)})
        version_row = version_result.first()
        project_template_version_id = version_row[0] if version_row and version_row[0] else None
    except Exception:
        # 列不存在或其他 DB 错误 → 降级继续（不 rollback，避免 session 失效）
        logger.warning("projects.template_version_id lookup failed, continuing without version")
        project_template_version_id = None

    # 获取版本字符串
    template_version_str: str | None = None
    version_service = WpTemplateVersionService(db)
    try:
        if project_template_version_id:
            version_obj = await version_service.get_version_by_id(project_template_version_id)
            template_version_str = version_obj.version
        else:
            # 默认按 current version
            version_obj = await version_service.get_current_version()
            template_version_str = version_obj.version
            project_template_version_id = version_obj.id
    except HTTPException:
        # 版本表可能未初始化，降级继续
        logger.warning("Template version lookup failed, continuing without version info")
        template_version_str = None
        project_template_version_id = None

    # ─── Step 4: 获取 classifications ────────────────────────────────────
    classification_service = WpClassificationService(db)
    try:
        classifications = await classification_service.get_classification(
            wp_code=wp_code,
            project_id=project_id,
            template_version_id=project_template_version_id,
        )
    except ClassificationNotFoundError:
        # 归类未找到时降级：返回空 sheets（前端显示 pending 状态）
        logger.warning(
            "No classification found for wp_code=%s, project_id=%s",
            wp_code, project_id,
        )
        classifications = []

    # ─── Step 5: 检查 scope（EARS: consolidated/parent_only → redirect） ──
    # 取第一个 sheet 的 scope 作为底稿级 scope
    scope = "standalone"
    is_real_workpaper = True
    if classifications:
        scope = classifications[0].scope
        is_real_workpaper = classifications[0].is_real_workpaper

    if scope in ("consolidated", "parent_only"):
        # 返回 redirect 提示，前端跳合并模块
        delegated_module = classifications[0].delegated_module if classifications else None
        return {
            "wp_id": str(wp_id),
            "wp_code": wp_code,
            "project_id": str(project_id),
            "scope": scope,
            "is_real_workpaper": is_real_workpaper,
            "template_version": template_version_str,
            "redirect": True,
            "delegated_module": delegated_module or "consolidation_hub",
            "sheets": [],
        }

    # ─── Step 6: 加载 schema + html_data + cross_refs per sheet ──────────
    parsed_data = working_paper.parsed_data or {}
    html_data_all = parsed_data.get("html_data", {})

    # 获取跨底稿引用
    cross_ref_query = sa.select(WpCrossRef).where(
        WpCrossRef.source_wp_id == wp_id,
        WpCrossRef.project_id == project_id,
    )
    cross_ref_result = await db.execute(cross_ref_query)
    cross_refs_all = cross_ref_result.scalars().all()

    # 按 target_wp_code 分组（简化：所有 cross_refs 挂到每个 sheet）
    cross_ref_items = [
        CrossRefItem(wp_code=cr.target_wp_code, cell=cr.cell_reference)
        for cr in cross_refs_all
    ]

    sheets: list[dict] = []
    for classification in classifications:
        # 如果指定了 sheet_name，只返回匹配的 sheet
        if sheet_name and classification.sheet_name != sheet_name:
            continue

        # 派生 componentType
        try:
            component_type = derive_component_type(classification)
        except ClassificationNotFoundError as e:
            logger.warning("Cannot derive componentType: %s", e)
            component_type = "skip"

        # 加载 schema YAML
        schema_data: dict | None = None
        try:
            schema_data = _schema_service.load_schema(
                wp_code=wp_code,
                template_version_id=project_template_version_id,
            )
        except FileNotFoundError:
            # schema 文件不存在时返回 None（前端可降级处理）
            logger.debug(
                "No render schema found for wp_code=%s, sheet=%s",
                wp_code, classification.sheet_name,
            )

        # 获取 sheet 级 html_data
        sheet_html_data = html_data_all.get(classification.sheet_name)

        sheet_config = {
            "sheet_name": classification.sheet_name,
            "componentType": component_type,
            "schema": schema_data,
            "html_data": sheet_html_data,
            "cross_refs": [item.model_dump() for item in cross_ref_items],
        }
        sheets.append(sheet_config)

    # ─── Step 7: 批量解析 auto-fill 取数值（US-15）────────────────────────
    fill_results: dict = {}
    # 获取项目年度
    year_query = sa.text("SELECT year FROM projects WHERE id = :pid")
    year_result = await db.execute(year_query, {"pid": str(project_id)})
    year_row = year_result.first()
    project_year = year_row[0] if year_row and year_row[0] else None

    if project_year:
        # 合并所有 sheet 的 schema 用于批量取数
        combined_schema: dict = {"sheets": {}}
        for sheet_cfg in sheets:
            if sheet_cfg.get("schema") and isinstance(sheet_cfg["schema"], dict):
                combined_schema["sheets"][sheet_cfg["sheet_name"]] = sheet_cfg["schema"].get(
                    "sheets", {}
                ).get(sheet_cfg["sheet_name"], sheet_cfg["schema"])
        try:
            fill_results = await _resolve_auto_fill_values(
                schema=combined_schema,
                project_id=project_id,
                year=project_year,
                db=db,
            )
        except Exception as e:
            logger.warning("Auto-fill resolution failed: %s", e)
            fill_results = {}

    return {
        "wp_id": str(wp_id),
        "wp_code": wp_code,
        "project_id": str(project_id),
        "scope": scope,
        "is_real_workpaper": is_real_workpaper,
        "template_version": template_version_str,
        "sheets": sheets,
        "fill_results": fill_results,
    }
