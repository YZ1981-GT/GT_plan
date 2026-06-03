"""底稿渲染配置端点

GET /api/workpapers/{wp_id}/render-config
按 design §5.1.1 实现：获取底稿渲染 schema + 项目数据 + 跨底稿引用。

Requirements: 1.2, 3.0.3, 3.0.5
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import (
    WpCrossRef,
    WpIndex,
    WorkingPaper,
    WpSourceType,
)
from app.services.wp_classification_service import (
    ClassificationNotFoundError,
    ClassificationResult,
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

# 标准底稿编号：A~I + 数字（D1-1、E11）；CUST-01 等字母后非数字则视为自建
_STANDARD_WP_CODE = re.compile(r"^[A-I]\d", re.IGNORECASE)


async def _has_custom_procedure(
    db: AsyncSession, project_id: UUID, wp_code: str
) -> bool:
    n = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(ProcedureInstance)
            .where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.wp_code == wp_code,
                ProcedureInstance.is_custom == True,  # noqa: E712
                ProcedureInstance.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar() or 0
    return n > 0


def _looks_like_standard_wp_code(wp_code: str) -> bool:
    return bool(_STANDARD_WP_CODE.search((wp_code or "").strip()))


async def _maybe_custom_classifications(
    db: AsyncSession,
    project_id: UUID,
    wp_code: str,
    wp_name: str | None,
    classifications: list,
    working_paper: WorkingPaper,
) -> list:
    """无模板归类时，为自定义程序/自建底稿合成 CUSTOM → componentType=custom。"""
    if classifications:
        return classifications
    use_custom = await _has_custom_procedure(db, project_id, wp_code)
    if not use_custom and working_paper.source_type == WpSourceType.manual:
        use_custom = not _looks_like_standard_wp_code(wp_code)
    if not use_custom:
        return classifications
    # sheet_name 与 parsed_data.html_data 的键一致（保存时用 wp_code 作 sheet 名）
    sheet_name = wp_code
    return [
        ClassificationResult(
            wp_code=wp_code,
            sheet_name=sheet_name,
            class_code="CUSTOM",
            class_="自定义底稿",
            scope="standalone",
            is_real_workpaper=True,
            delegated_module=None,
            render_schema_path=None,
            template_version_id=None,
        )
    ]


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


# ─── B-Index 自动生成辅助 ─────────────────────────────────────────────────


async def _build_preparation_info(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
) -> dict[str, str]:
    """编制信息 JOIN（workpaper 级表头 + B-Index 共用）。无 accounting_period。"""
    info: dict[str, str] = {
        "entity_name": "",
        "period_end": "",
        "preparer": "",
        "prep_date": "",
        "reviewer": "",
        "review_date": "",
        "index_no": "",
    }
    try:
        proj_result = await db.execute(
            sa.text("SELECT name, audit_period_end FROM projects WHERE id = :pid"),
            {"pid": str(project_id)},
        )
        proj_row = proj_result.first()
        if proj_row:
            info["entity_name"] = proj_row[0] or ""
            info["period_end"] = str(proj_row[1])[:10] if proj_row[1] else ""
    except Exception as e:
        logger.warning("preparation_info: 项目信息失败: %s", e)

    if not info["entity_name"]:
        try:
            from app.models.core import Project

            proj = await db.get(Project, project_id)
            if proj:
                info["entity_name"] = proj.name or ""
                if not info["period_end"] and getattr(proj, "audit_period_end", None):
                    info["period_end"] = str(proj.audit_period_end)[:10]
        except Exception as e:
            logger.warning("preparation_info: ORM 项目信息降级失败: %s", e)

    try:
        staff_result = await db.execute(
            sa.text("""
                SELECT pa.role, s.name
                FROM project_assignments pa
                JOIN staff_members s ON s.id = pa.staff_id
                WHERE pa.project_id = :pid
                  AND pa.role IN ('preparer', 'reviewer', 'partner', 'manager')
            """),
            {"pid": str(project_id)},
        )
        for role, name in staff_result:
            if role == "preparer":
                info["preparer"] = name or ""
            elif role in ("reviewer", "manager"):
                if not info["reviewer"] or role == "reviewer":
                    info["reviewer"] = name or ""
    except Exception as e:
        logger.warning("preparation_info: 人员信息失败: %s", e)

    try:
        wp_row = (
            await db.execute(
                sa.select(WorkingPaper.created_at, WpIndex.wp_code)
                .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
                .where(WorkingPaper.id == wp_id)
            )
        ).first()
        if wp_row:
            if wp_row[0]:
                info["prep_date"] = str(wp_row[0])[:10]
            info["index_no"] = wp_row[1] or ""
    except Exception as e:
        logger.warning("preparation_info: 底稿信息失败: %s", e)

    return info


async def _generate_b_index_data(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
    classifications: list,
) -> dict:
    """当 B-Index sheet 无持久化 html_data 时，从项目元数据 + 同底稿 sheets 自动生成。

    返回结构与 GtBIndex.vue 的 BIndexHtmlData 接口一致：
    {
      preparation_info: { entity_name, period_end, preparer, prep_date, reviewer, review_date, index_no },
      navigation_rows: [ { seq, content, index_ref, no_print } ]
    }
    """
    preparation_info = await _build_preparation_info(db, project_id, wp_id)

    # ─── 索引导航行（同底稿其他 sheet → 行） ─────────────────────────────
    # sheet 级索引号嵌在 sheet_name 末尾（如「审定表D1-1」→ D1-1，
    # 「应收票据审计程序表D1A」→ D1A）；wp_code 仅父级（D1），不能用作 index_ref。
    _SHEET_INDEX_PATTERN = re.compile(r"([A-Z]\d+[A-Z]?(?:-\d+)*)\s*$")

    navigation_rows: list[dict] = []
    seq = 1
    for cls in classifications:
        # 跳过 B-Index 自身
        try:
            ct = derive_component_type(cls)
        except Exception:
            ct = "skip"
        if ct == "b-index":
            continue

        # 从 sheet_name 末尾提取该 sheet 的真实索引号；提取不到则回退父 wp_code
        sheet_index = ""
        m = _SHEET_INDEX_PATTERN.search(cls.sheet_name or "")
        if m:
            sheet_index = m.group(1)
        else:
            sheet_index = getattr(cls, "wp_code", "") or ""

        navigation_rows.append({
            "seq": seq,
            "content": cls.sheet_name,
            "index_ref": sheet_index,
            "component_type": ct,
            "no_print": False,
        })
        seq += 1

    return {
        "preparation_info": preparation_info,
        "navigation_rows": navigation_rows,
    }


# ─── A-程序表中控台自动生成辅助 ────────────────────────────────────────────


async def _generate_a_program_data(
    file_path: str | None,
    sheet_name: str,
    existing: dict | None = None,
) -> dict:
    """当 a-program-console sheet 无持久化 programs 时，从模板 xlsx 提取程序清单。

    返回结构与 GtAProgramConsole.vue 的 AProgramHtmlData 接口一致：
    {
      programs: [ { id, program_no, program_desc, program_category,
                    assertions, linked_workpapers, status } ],
      trim_decisions: [],
      signatures: [...]（保留 existing 中的签字信息）
    }

    解析失败 / 文件缺失 → programs 为空列表（前端仍显示空态，不报错）。
    """
    from app.services.wp_program_extract import extract_program_rows

    programs: list[dict] = []
    if file_path:
        try:
            programs = extract_program_rows(file_path, sheet_name)
        except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
            logger.warning("A-程序表提取失败 %s/%s: %s", file_path, sheet_name, e)
            programs = []

    result: dict = {
        "programs": programs,
        "trim_decisions": [],
    }
    # 保留已有签字信息（若 sheet 之前存过部分数据）
    if existing and isinstance(existing.get("signatures"), list):
        result["signatures"] = existing["signatures"]
    return result


# ─── univer 表格类底稿网格自动生成辅助 ─────────────────────────────────────


def _has_grid_cells(html_data: dict | None) -> bool:
    """判断 sheet html_data 是否已含可渲染的网格 cells。"""
    if not isinstance(html_data, dict):
        return False
    cells = html_data.get("cells")
    return isinstance(cells, dict) and len(cells) > 0


async def _generate_grid_data(
    file_path: str | None,
    sheet_name: str,
    existing: dict | None = None,
) -> dict:
    """当 univer 类 sheet 无持久化网格数据时，从模板 xlsx 提取只读网格。

    返回结构与 GtGridSheet.vue 的 GridHtmlData 接口一致：
    { cells, merged_cells, col_widths, max_row, max_col }

    解析失败 / 文件缺失 → 空网格（前端显示空态，不报错）。
    """
    from app.services.wp_grid_extract import extract_grid

    grid: dict = {"cells": {}, "merged_cells": [], "col_widths": {}, "max_row": 0, "max_col": 0}
    if file_path:
        try:
            grid = extract_grid(file_path, sheet_name)
        except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
            logger.warning("univer 网格提取失败 %s/%s: %s", file_path, sheet_name, e)

    # 合并已有持久化数据（若用户曾编辑过部分单元格）
    if existing and isinstance(existing.get("cells"), dict) and existing["cells"]:
        grid = {**grid, **existing}
    return grid


@router.get("/{wp_id}/preparation-info")
async def get_preparation_info(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """workpaper 级编制信息（7 字段，无 accounting_period）。"""
    wp = (
        await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if wp is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    return await _build_preparation_info(db, wp.project_id, wp_id)


@router.post("/generate-from-index")
async def generate_workpaper_from_index(
    wp_index_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """手动从 wp_index 幂等生成 working_paper。"""
    from app.services.workpaper_generation_service import workpaper_generation_service

    wp_index = (
        await db.execute(
            sa.select(WpIndex).where(
                WpIndex.id == wp_index_id,
                WpIndex.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars().first()
    if wp_index is None:
        raise HTTPException(status_code=404, detail="底稿索引不存在")

    wp = await workpaper_generation_service.ensure_working_paper(
        db,
        wp_index.project_id,
        wp_index_id,
        created_by=user.id,
    )
    await db.commit()
    return {
        "working_paper_id": str(wp.id),
        "wp_index_id": str(wp_index_id),
        "wp_code": wp_index.wp_code,
        "file_path": wp.file_path,
    }


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
    # 注：projects 表无 template_version_id 列（该列属于 workpaper_sheet_classification，
    #     从无 projects 级定义）。历史代码曾 SELECT projects.template_version_id，
    #     在 PG 中该语句失败会使整个事务进入 aborted 状态，后续查询全部 500
    #     （render-config 对所有底稿普适 500 的根因）。故移除该探测查询，
    #     统一按 current version 解析（项目级版本绑定由 classification 层承担）。
    project_template_version_id = None

    # 获取版本字符串
    template_version_str: str | None = None
    version_service = WpTemplateVersionService(db)
    try:
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

    classifications = await _maybe_custom_classifications(
        db,
        project_id,
        wp_code,
        wp_index.wp_name,
        classifications,
        working_paper,
    )

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

        # ─── B-Index 自动生成逻辑：编制信息 + 索引导航 ─────────────────
        if component_type == "b-index" and not sheet_html_data:
            sheet_html_data = await _generate_b_index_data(
                db=db,
                project_id=project_id,
                wp_id=wp_id,
                classifications=classifications,
            )

        # ─── A-程序表中控台自动生成：从模板 xlsx 提取审计程序行 ─────────
        # GtAProgramConsole 消费 html_data.programs；当 sheet 无持久化 programs
        # 时，从底稿模板 xlsx 解析程序清单（序号/描述/分类/5项认定/底稿索引），
        # 否则中控台永远显示「暂无审计程序」（模板里的程序内容无法体现）。
        if component_type == "a-program-console" and not (
            isinstance(sheet_html_data, dict) and sheet_html_data.get("programs")
        ):
            sheet_html_data = await _generate_a_program_data(
                file_path=working_paper.file_path,
                sheet_name=classification.sheet_name,
                existing=sheet_html_data if isinstance(sheet_html_data, dict) else None,
            )

        # ─── univer 表格类底稿网格自动生成：从模板 xlsx 提取只读网格 ──────
        # 混合底稿（含 HTML sheet + univer sheet）整本走 GtWpRenderer 时，
        # univer sheet（审定表/明细表/测算表）之前只显示死占位「数据尚未导入」，
        # 模板网格结构完全不体现。此处补 cells/merged_cells 让模板内容可见（只读），
        # TB 取数后续再填。
        if component_type == "univer" and not _has_grid_cells(sheet_html_data):
            sheet_html_data = await _generate_grid_data(
                file_path=working_paper.file_path,
                sheet_name=classification.sheet_name,
                existing=sheet_html_data if isinstance(sheet_html_data, dict) else None,
            )

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
    # 获取项目年度：projects 表无 year 列，年度从 audit_period_end 提取年份
    # （系统标准做法，见 rotation_check/client_quality_trend 等）。
    # 该字段可能为 NULL → project_year=None → 跳过 auto-fill（降级，不报错）。
    project_year = None
    try:
        year_query = sa.text(
            "SELECT EXTRACT(YEAR FROM audit_period_end)::int FROM projects WHERE id = :pid"
        )
        year_result = await db.execute(year_query, {"pid": str(project_id)})
        year_row = year_result.first()
        project_year = year_row[0] if year_row and year_row[0] else None
    except Exception as e:
        logger.warning("项目年度解析失败，跳过 auto-fill: %s", e)
        project_year = None

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
