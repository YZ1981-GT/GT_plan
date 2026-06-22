"""底稿渲染配置端点

GET /api/workpapers/{wp_id}/render-config
按 design §5.1.1 实现：获取底稿渲染 schema + 项目数据 + 跨底稿引用。

Requirements: 1.2, 3.0.3, 3.0.5
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
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
from app.services.wp_account_package_resolver import resolve_package_sheets
from app.services.wp_render_schema_service import WpRenderSchemaService
from app.services.wp_template_version_service import WpTemplateVersionService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["wp-render-config"],
)

# ─── Singleton schema service (stateless + cache) ────────────────────────────
_schema_service = WpRenderSchemaService()

# sheet 名尾部的 sheet 级编码提取（如「合同负债及销售替代程序D0-5」→「D0-5」、
# 「审定表D2-1」→「D2-1」、「应收票据审计程序表D1A」→「D1A」）。
# 用于多 sheet 底稿按 sheet 级编码查 _WP_CODE_OVERRIDE（协作者 confirmation-* 精细组件）。
_SHEET_CODE_RE = re.compile(r"([A-Z]\d+[A-Z]?(?:-\d+[a-z]?)*)\s*$")

# 协作者 D0 函证精细组件（纯前端 componentType，无后端 renderer）。
# 这些不在 _ONLYOFFICE_HTML_WHITELIST 但必须保留(不被重写成 onlyoffice-sheet)，
# 由前端 htmlRendererRegistry 渲染；后端从模板提取 grid 供其消费。
_CONFIRMATION_COMPONENTS: set[str] = {
    "confirmation-summary",
    "confirmation-entity-verify",
    "confirmation-followup",
    "confirmation-diff-reconcile",
    "confirmation-diff-checklist",
    "confirmation-alternative-d05",
    "confirmation-alternative-d06",
    "confirmation-reliability",
    "confirmation-fraud-risk",
}

# confirmation 组件首次打开时的空初始数据（_format 标记让前端识别为新格式，显示可编辑空表）
_CONFIRMATION_FORMAT_MAP: dict[str, str] = {
    "confirmation-summary": "confirmation-v1",
    "confirmation-entity-verify": "entity-verify-v1",
    "confirmation-followup": "followup-v1",
    "confirmation-diff-reconcile": "diff-reconcile-v1",
    "confirmation-diff-checklist": "diff-checklist-v1",
    "confirmation-alternative-d05": "alternative-d05-v1",
    "confirmation-alternative-d06": "alternative-d06-v1",
    "confirmation-reliability": "reliability-v1",
    "confirmation-fraud-risk": "fraud-risk-v1",
}


def _confirmation_initial_data(component_type: str) -> dict:
    """为 confirmation 精细组件生成空的新格式初始数据。

    前端组件检测 `_format` 字段 → 识别为新格式 → 显示可编辑空表。
    无 `_format` 则前端降级为"旧格式只读"（设计意图：区分新旧数据）。
    """
    fmt = _CONFIRMATION_FORMAT_MAP.get(component_type, "confirmation-v1")
    return {"_format": fmt, "rows": [], "sampling": {}, "notes": {}, "conclusion": {}}

# ─── OnlyOffice HTML 白名单：这些 componentType 即使无 renderer 也继续走 grid 兜底，
# 不切换到 OnlyOffice 渲染。（design §1.1）
_ONLYOFFICE_HTML_WHITELIST: set[str] = {
    "b-index",
    "a-program-console",
    "audit-sheet",
    "c-note-table",
    "d-form-table",
    "d-form-confirmation",
    "d-form-paragraph",
    "bad-debt-sheet",
    "h-static-doc",
}

# 标准底稿编号：A~I + 数字（D1-1、E11）；CUST-01 等字母后非数字则视为自建
_STANDARD_WP_CODE = re.compile(r"^[A-I]\d", re.IGNORECASE)


# ─── sheet_type 推断辅助（Task 2.1: schema 显式 > 启发式 > null）─────────────

# 从 wp_generic_processor._detect_sheet_type 提取的启发式映射表
# 将旧式返回值（summary/detail/analysis/procedure 等）映射到 SheetContentType 枚举
_HEURISTIC_TO_SHEET_CONTENT_TYPE: dict[str, str] = {
    "summary": "audit_sheet",
    "detail": "detail_table",
    "analysis": "analysis",
    "procedure": "procedure",
    "adjustment": "adjustment",
    "disclosure": "disclosure",
    "movement": "detail_table",
    "aging": "analysis",
}


def _infer_sheet_type_from_schema(sheet_schema: dict | None, full_schema: dict | None) -> str | None:
    """从 schema YAML 中提取显式 sheet_type（优先 per-sheet，否则顶层）。

    Returns:
        显式配置的 sheet_type 字符串，或 None（schema 未配置）。
    """
    # per-sheet schema 中有 sheet_type
    if isinstance(sheet_schema, dict) and sheet_schema.get("sheet_type"):
        return str(sheet_schema["sheet_type"])
    # 顶层 schema 有 sheet_type（单 sheet yaml）
    if isinstance(full_schema, dict) and full_schema.get("sheet_type"):
        return str(full_schema["sheet_type"])
    return None


def _infer_sheet_type_by_heuristic(sheet_name: str) -> str | None:
    """用中文关键词启发式推断 sheet_type（与 wp_generic_processor._detect_sheet_type 同口径）。

    Returns:
        SheetContentType 枚举字符串，或 None（无法推断）。
    """
    name = sheet_name or ""
    # 顺序很重要：更具体的关键词优先匹配
    if "函证" in name or "询证" in name:
        return "confirmation_summary"
    if "控制测试" in name:
        return "control_test"
    if "内控" in name and "了解" in name:
        return "control_understanding"
    if "控制" in name and "了解" in name:
        return "control_understanding"
    if "控制" in name and "测试" in name:
        return "control_test"
    if "审定" in name or "汇总" in name:
        return "audit_sheet"
    if "明细" in name or "清单" in name:
        return "detail_table"
    if "分析" in name or "测算" in name or "复核" in name:
        return "analysis"
    if "程序" in name:
        return "procedure"
    if "调整" in name:
        return "adjustment"
    if "披露" in name or "附注" in name:
        return "disclosure"
    if "结论" in name:
        return "conclusion"
    if "目录" in name or "索引" in name or "驾驶" in name or "控制台" in name:
        return "control_panel"
    return None


def _load_semantic_registry() -> dict:
    """加载 D1/D2 语义标注注册表（缓存于模块级变量）。"""
    global _SEMANTIC_REGISTRY_CACHE
    if _SEMANTIC_REGISTRY_CACHE is not None:
        return _SEMANTIC_REGISTRY_CACHE
    import json
    # schema 文件实际位于 backend/data/ledger_adapters/wp_render_schema/
    registry_path = Path(__file__).parent.parent.parent / "data" / "ledger_adapters" / "wp_render_schema" / "d1_d2_semantic_registry.json"
    if registry_path.exists():
        try:
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            _SEMANTIC_REGISTRY_CACHE = data.get("sheets", {})
        except (json.JSONDecodeError, OSError):
            _SEMANTIC_REGISTRY_CACHE = {}
    else:
        _SEMANTIC_REGISTRY_CACHE = {}
    return _SEMANTIC_REGISTRY_CACHE


_SEMANTIC_REGISTRY_CACHE: dict | None = None


def _infer_sheet_type_from_registry(sheet_name: str) -> str | None:
    """从 D1/D2 语义标注注册表查找 sheet_type。"""
    registry = _load_semantic_registry()
    entry = registry.get(sheet_name)
    if entry and isinstance(entry, dict):
        st = entry.get("sheet_type")
        if st and isinstance(st, str):
            return st
    return None


def _resolve_sheet_type(
    sheet_schema: dict | None,
    full_schema: dict | None,
    sheet_name: str,
) -> str | None:
    """按优先级确定 sheet_type: schema 显式 > registry > 启发式 > None。"""
    # 1. schema 显式值
    explicit = _infer_sheet_type_from_schema(sheet_schema, full_schema)
    if explicit:
        return explicit
    # 2. 注册表（D1/D2 试点标注）
    registry_value = _infer_sheet_type_from_registry(sheet_name)
    if registry_value:
        return registry_value
    # 3. 启发式
    heuristic = _infer_sheet_type_by_heuristic(sheet_name)
    if heuristic:
        return heuristic
    # 4. 无法确定
    return None


def _extract_field_sources(sheet_schema: dict | None, full_schema: dict | None, sheet_name: str = "") -> dict:
    """从 schema YAML 或 registry 中提取 field_sources 配置。

    优先级: per-sheet schema > full schema > registry。

    Returns:
        字段来源配置 dict，或空 {}（schema 未配置）。
    """
    # per-sheet schema 中有 field_sources
    if isinstance(sheet_schema, dict) and isinstance(sheet_schema.get("field_sources"), dict):
        return sheet_schema["field_sources"]
    # 顶层 schema 有 field_sources（单 sheet yaml）
    if isinstance(full_schema, dict) and isinstance(full_schema.get("field_sources"), dict):
        return full_schema["field_sources"]
    # 注册表中查找 field_sources（Task 4.4）
    if sheet_name:
        registry = _load_semantic_registry()
        entry = registry.get(sheet_name)
        if entry and isinstance(entry, dict) and isinstance(entry.get("field_sources"), dict):
            return entry["field_sources"]
    return {}


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
    sheet_type: str | None = None
    field_sources: dict | None = None

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
                sa.select(WorkingPaper.created_at, WpIndex.wp_code, WorkingPaper.assigned_to)
                .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
                .where(WorkingPaper.id == wp_id)
            )
        ).first()
        if wp_row:
            if wp_row[0]:
                info["prep_date"] = str(wp_row[0])[:10]
            info["index_no"] = wp_row[1] or ""
            # 底稿级编制人优先（assigned_to）：表头编制人应是本底稿被分配人，
            # 而非项目级 preparer。仅当底稿未分配时才回退到项目级 preparer。
            wp_assignee_id = wp_row[2]
            if wp_assignee_id:
                try:
                    assignee_row = (
                        await db.execute(
                            sa.text(
                                "SELECT username FROM users WHERE id = :uid"
                            ),
                            {"uid": str(wp_assignee_id)},
                        )
                    ).first()
                    if assignee_row and assignee_row[0]:
                        info["preparer"] = assignee_row[0]
                except Exception as e:
                    logger.debug("preparation_info: 底稿级编制人取名降级: %s", e)
    except Exception as e:
        logger.warning("preparation_info: 底稿信息失败: %s", e)

    return info


@router.post("/{wp_id}/audit-sheet-refresh")
async def refresh_audit_sheet_from_ledger(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """一键刷新：从四表库（试算表/辅助余额表）预填充审定表/明细表数据。

    对于按客户明细表（如 D1-3），从 tb_aux_balance 按 account_code 查询辅助余额，
    按 aux_name（客户名称）聚合为行，填入 column_defs 对应列。
    对于按类别明细表（如 D1-2），从 trial_balance 按 account_code 查询余额。

    返回预填充后的 audit_rows（前端可直接覆盖 tableData）。
    """
    # 查 working_paper → wp_index → wp_code + project_id
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

    wp_index = (
        await db.execute(
            sa.select(WpIndex).where(WpIndex.id == wp.wp_index_id)
        )
    ).scalars().first()
    wp_code = wp_index.wp_code if wp_index else ""
    project_id = wp.project_id

    # 获取年度
    year_result = await db.execute(
        sa.text("SELECT EXTRACT(YEAR FROM audit_period_end)::int FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )
    year_row = year_result.first()
    project_year = year_row[0] if year_row and year_row[0] else None

    if not project_year:
        return {"rows": [], "message": "项目未设置审计期间，无法取数"}

    # 确定科目编码（从 wp_account_mapping 或直接根据 wp_code）
    import json
    from pathlib import Path as _Path

    mapping_file = _Path(__file__).resolve().parent.parent.parent / "data" / "wp_account_mapping.json"
    account_codes: list[str] = []
    try:
        with open(mapping_file, "r", encoding="utf-8") as f:
            mappings = json.load(f)
        for m in mappings:
            if m.get("wp_code") == wp_code:
                account_codes = m.get("account_codes", [])
                break
    except Exception as e:
        logger.warning("加载 wp_account_mapping 失败 wp_code=%s: %s", wp_code, e)

    if not account_codes:
        # D1 系列默认 1121（应收票据）
        if wp_code.startswith("D1"):
            account_codes = ["1121"]
        else:
            return {"rows": [], "message": f"未找到 {wp_code} 的科目映射"}

    # 从辅助余额表查询按客户/辅助核算维度的余额
    try:
        aux_result = await db.execute(
            sa.text("""
                SELECT aux_name, opening_balance, debit_amount, credit_amount, closing_balance
                FROM tb_aux_balance
                WHERE project_id = :pid
                  AND year = :year
                  AND account_code = ANY(:codes)
                  AND is_deleted = false
                  AND aux_name IS NOT NULL AND aux_name != ''
                ORDER BY closing_balance DESC NULLS LAST
            """),
            {"pid": str(project_id), "year": project_year, "codes": account_codes},
        )
        aux_rows = aux_result.all()
    except Exception as e:
        logger.warning("audit-sheet-refresh 辅助余额查询失败: %s", e)
        aux_rows = []

    if not aux_rows:
        # 回退到试算表查询
        try:
            tb_result = await db.execute(
                sa.text("""
                    SELECT standard_account_code, opening_balance, unadjusted_amount,
                           aje_adjustment, rje_adjustment
                    FROM trial_balance
                    WHERE project_id = :pid
                      AND year = :year
                      AND standard_account_code = ANY(:codes)
                      AND is_deleted = false
                """),
                {"pid": str(project_id), "year": project_year, "codes": account_codes},
            )
            tb_rows = tb_result.all()
        except Exception as e:
            logger.warning("audit-sheet-refresh TB 查询失败: %s", e)
            tb_rows = []

        if not tb_rows:
            return {"rows": [], "message": "四表库中未找到该科目数据"}

        # TB 数据返回（简单行）
        rows = []
        for i, tr in enumerate(tb_rows):
            rows.append({
                "id": f"refresh-{i+1}",
                "item": tr[0] or "",
                "isCustom": True,
                "opening_unadjusted": float(tr[1]) if tr[1] else None,
                "current_unadjusted": float(tr[2]) if tr[2] else None,
                "sys_aje": float(tr[3]) if tr[3] else None,
                "sys_rje": float(tr[4]) if tr[4] else None,
            })
        return {"rows": rows, "message": f"已从试算表预填充 {len(rows)} 行"}

    # 辅助余额数据 → 明细行
    rows = []
    for i, ar in enumerate(aux_rows):
        rows.append({
            "id": f"refresh-{i+1}",
            "item": ar[0] or "",  # 客户名称
            "isCustom": True,
            "col_opening": float(ar[1]) if ar[1] else None,
            "col_debit": float(ar[2]) if ar[2] else None,
            "col_credit": float(ar[3]) if ar[3] else None,
            "col_closing": float(ar[4]) if ar[4] else None,
        })

    return {"rows": rows, "message": f"已从辅助余额表预填充 {len(rows)} 行（按客户）"}


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
    from app.services.wp_preparation_info_service import build_preparation_info

    return await build_preparation_info(db, wp.project_id, wp_id)


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




def _unpack_sheet_schema(schema_data: dict | None, sheet_name: str) -> dict | None:
    """按 sheet 名解包 schema（前端组件读顶层 sub_tables/fields）。"""
    if not isinstance(schema_data, dict):
        return None
    nested = schema_data.get("sheets")
    if isinstance(nested, dict) and sheet_name in nested:
        per_sheet = nested[sheet_name]
        if isinstance(per_sheet, dict):
            merged = {k: v for k, v in schema_data.items() if k != "sheets"}
            merged.update(per_sheet)
            return merged
    if schema_data.get("sub_tables") or schema_data.get("fields"):
        return schema_data
    return None


def _resolve_template_path(working_paper, wp_code: str) -> str | None:
    """模板文件路径：优先 file_path，否则回退 wp_templates 库。"""
    fp = working_paper.file_path
    if fp and Path(fp).is_file():
        return fp
    try:
        from app.services.wp_template_init_service import find_template_file_any
        t = find_template_file_any(wp_code)
        return str(t) if t else fp
    except Exception:  # noqa: BLE001
        return fp


@router.get("/{wp_id}/export-template")
async def export_template(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出底稿对应的原始 xlsx 模板文件"""
    from fastapi.responses import FileResponse
    from urllib.parse import quote

    working_paper = (await db.execute(sa.select(WorkingPaper).where(
        WorkingPaper.id == wp_id, WorkingPaper.is_deleted == False))).scalars().first()  # noqa: E712
    if not working_paper:
        raise HTTPException(status_code=404, detail="底稿不存在")
    wp_index = (await db.execute(sa.select(WpIndex).where(
        WpIndex.id == working_paper.wp_index_id))).scalars().first()
    wp_code = wp_index.wp_code if wp_index else "unknown"
    tpl_path = _resolve_template_path(working_paper, wp_code)
    if not tpl_path or not Path(tpl_path).is_file():
        raise HTTPException(status_code=404, detail="模板文件不存在")
    filename = Path(tpl_path).name
    return FileResponse(
        path=str(tpl_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/{wp_id}/render-config")
async def get_render_config(
    wp_id: UUID,
    sheet_name: str | None = Query(None, description="可选，仅返回单 sheet 数据"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取底稿渲染 schema + 项目数据 + 跨底稿引用（dispatch 模式）。"""
    try:
        return await _get_render_config_impl(wp_id, sheet_name, db, current_user)
    except Exception as _fatal:
        # 临时：把完整堆栈写到文件方便排查 500
        import traceback
        with open("_render_config_500.log", "a", encoding="utf-8") as _f:
            _f.write(f"\n{'='*60}\nwp_id={wp_id}\n")
            traceback.print_exc(file=_f)
        raise


async def _get_render_config_impl(
    wp_id: UUID,
    sheet_name: str | None,
    db: AsyncSession,
    current_user,
):
    """实际实现（从原 get_render_config 提取）。"""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH
    from app.routers.wp_render_strategies._context import RenderContext
    from app.routers.wp_render_strategies._context import CrossRefItem as _CRI
    from app.services.wp_classification_service import _WP_CODE_OVERRIDE

    # Step 1~2: working_paper + wp_index
    working_paper = (await db.execute(sa.select(WorkingPaper).where(
        WorkingPaper.id == wp_id, WorkingPaper.is_deleted == False))).scalars().first()  # noqa: E712
    if not working_paper:
        raise HTTPException(status_code=404, detail="底稿不存在")
    project_id = working_paper.project_id
    # 已软删除项目的底稿不应可打开（根因修复：首汽租车_2025 已删但 D2 底稿仍可访问）
    _proj_deleted = (await db.execute(sa.text(
        "SELECT is_deleted FROM projects WHERE id = :pid"), {"pid": str(project_id)})).scalar()
    if _proj_deleted:
        raise HTTPException(status_code=404, detail="项目已删除")
    wp_index = (await db.execute(sa.select(WpIndex).where(
        WpIndex.id == working_paper.wp_index_id, WpIndex.is_deleted == False))).scalars().first()  # noqa: E712
    if not wp_index:
        raise HTTPException(status_code=404, detail="底稿索引不存在")
    wp_code = wp_index.wp_code

    # Step 3: 模板版本
    tpl_ver_id = tpl_ver_str = None
    try:
        v = await WpTemplateVersionService(db).get_current_version()
        tpl_ver_str, tpl_ver_id = v.version, v.id
    except HTTPException:
        pass

    # Step 4: classifications
    try:
        classifications = await WpClassificationService(db).get_classification(
            wp_code=wp_code, project_id=project_id, template_version_id=tpl_ver_id)
    except ClassificationNotFoundError:
        classifications = []
    classifications = await _maybe_custom_classifications(
        db, project_id, wp_code, wp_index.wp_name, classifications, working_paper)

    # Step 4b: 科目工作包多文件聚合（spec workpaper-account-multifile-aggregation）
    # 父码科目（如 D2 应收账款）若在 account_package_registry 中有条目，则消费注册表
    # 声明的全部 sheet（聚合 3 个 Excel 文件的 14 sheet），替换单文件回退的
    # classifications。无条目返回 None → 走原 classification，零回归。
    # 忽略 registry 的 mapping_status，只要 package 存在即直接消费其 sheets。
    try:
        pkg_sheets = await resolve_package_sheets(db, wp_code, project_id)
    except Exception as e:  # noqa: BLE001 — 聚合失败按"无聚合"降级，零回归
        logger.warning("科目工作包聚合失败 wp_code=%s: %s", wp_code, e)
        pkg_sheets = None
        # 查询失败可能导致事务 aborted → rollback 恢复
        try:
            await db.rollback()
        except Exception:
            pass
    if pkg_sheets:
        classifications = pkg_sheets

    # Step 5: scope + redirect
    scope, is_real = (classifications[0].scope, classifications[0].is_real_workpaper) if classifications else ("standalone", True)
    _base = {"wp_id": str(wp_id), "wp_code": wp_code, "project_id": str(project_id),
             "scope": scope, "template_version": tpl_ver_str, "sheets": []}
    if scope in ("consolidated", "parent_only"):
        return {**_base, "is_real_workpaper": is_real, "redirect": True,
                "delegated_module": (classifications[0].delegated_module if classifications else None) or "consolidation_hub"}
    if _WP_CODE_OVERRIDE.get(wp_code) == "redirect-materiality":
        return {**_base, "is_real_workpaper": False, "redirect": True,
                "delegated_module": "materiality", "target_path": "/materiality"}

    # Step 6: 公共数据
    html_data_all = (working_paper.parsed_data or {}).get("html_data", {})
    cross_ref_items = [CrossRefItem(wp_code=cr.target_wp_code, cell=cr.cell_reference)
                       for cr in (await db.execute(sa.select(WpCrossRef).where(
                           WpCrossRef.source_wp_id == wp_id, WpCrossRef.project_id == project_id
                       ))).scalars().all()]
    _prog_year, _prog_biz = None, "C"
    try:
        pj = (await db.execute(sa.text(
            "SELECT EXTRACT(YEAR FROM audit_period_end)::int, COALESCE(business_category, 'C') "
            "FROM projects WHERE id = :pid"), {"pid": str(project_id)})).first()
        if pj:
            _prog_year, _prog_biz = pj[0], pj[1] or "C"
    except Exception as e:  # noqa: BLE001
        logger.warning("查询项目年度/业务类别失败 pid=%s: %s", project_id, e)
    _tpl = _resolve_template_path(working_paper, wp_code)

    # Per-sheet dispatch loop
    # 多 sheet 底稿（如 D2 含 底稿目录/程序表/审定表/附注 等）：每个 sheet 按自己的
    # class_code 独立派生 componentType，不能用 wp_code 级 override 压平所有 sheet。
    # wp_code override 仅对单 sheet 底稿生效（如 D1 应收票据审定表整张走 d-form-table）。
    _real_sheets = [c for c in classifications
                    if not (c.sheet_name and "GT_Custom" in c.sheet_name)]
    _is_multi_sheet = len(_real_sheets) > 1

    # 多 sheet 底稿 tab 排序：按模板 xlsx sheetnames 顺序排列
    # （DB created_at 顺序不可靠；openpyxl read_only 取 sheetnames → 按 index 排序）
    if _is_multi_sheet and _tpl and Path(_tpl).exists() and str(_tpl).endswith((".xlsx", ".xls")):
        try:
            import openpyxl
            _wb = openpyxl.load_workbook(_tpl, read_only=True, data_only=True)
            _template_order = {name: idx for idx, name in enumerate(_wb.sheetnames)}
            _wb.close()
            classifications = sorted(
                classifications,
                key=lambda c: _template_order.get(c.sheet_name, 999),
            )
        except Exception:  # noqa: BLE001 — 排序失败不影响渲染，保持原序
            pass

    sheets: list[dict] = []
    for cls in classifications:
        if sheet_name and cls.sheet_name != sheet_name:
            continue
        if cls.sheet_name and "GT_Custom" in cls.sheet_name:
            continue
        ovr = _WP_CODE_OVERRIDE.get(wp_code)
        # 多 sheet 底稿：按 sheet 级编码查 override（协作者 confirmation-* 精细组件，
        # 如 D0-5→confirmation-alternative-d05）。sheet 级 override 优先于 class_code 派生。
        _sheet_ovr = None
        if _is_multi_sheet and cls.sheet_name:
            _m = _SHEET_CODE_RE.search(cls.sheet_name)
            if _m:
                _sheet_ovr = _WP_CODE_OVERRIDE.get(_m.group(1))
            # fallback: 按完整 sheet_name 查找（如「函证差异检查表（示例）」无尾部编码）
            if not _sheet_ovr:
                _sheet_ovr = _WP_CODE_OVERRIDE.get(cls.sheet_name)
        try:
            if _is_multi_sheet:
                if _sheet_ovr:
                    # sheet 级 override 命中（精细 confirmation-* 组件）→ 直接采用
                    component_type = _sheet_ovr
                else:
                    # 否则按 class_code 派生（跳过父码 wp_code override 避免压平）
                    try:
                        component_type = derive_component_type(cls, ignore_wp_code_override=True)
                    except ClassificationNotFoundError:
                        component_type = ovr if ovr else "skip"
            else:
                # 单 sheet：wp_code override 优先（保留原行为）
                component_type = ovr if ovr else derive_component_type(cls)
        except ClassificationNotFoundError:
            component_type = "skip"
        schema_data: dict | None = None
        try:
            schema_data = _schema_service.load_schema(wp_code=wp_code, template_version_id=tpl_ver_id)
        except FileNotFoundError:
            pass
        sheet_schema = _unpack_sheet_schema(schema_data, cls.sheet_name)
        sheet_html_data = html_data_all.get(cls.sheet_name)

        # 聚合工作包或独立底稿中 G- 前缀 class_code 强制走 OnlyOffice 编辑（不走 univer grid）
        # G-OnlyOffice = 聚合 grid_table；G-替代程序 = 独立底稿替代程序检查表等
        _cls_code = getattr(cls, "class_code", "") or ""
        if _is_multi_sheet and _cls_code.startswith("G-"):
            component_type = "onlyoffice-sheet"
            sheet_html_data = {"onlyoffice": True, "sheet_name": cls.sheet_name}
            sheets.append({"sheet_name": cls.sheet_name, "componentType": component_type,
                           "schema": sheet_schema, "html_data": sheet_html_data,
                           "cross_refs": [i.model_dump() for i in cross_ref_items],
                           })
            continue

        renderer = RENDERER_DISPATCH.get(component_type)
        if renderer:
            ctx = RenderContext(
                db=db, project_id=project_id, wp_id=wp_id, wp_code=wp_code,
                working_paper=working_paper, classification=cls,
                component_type=component_type, sheet_html_data=sheet_html_data,
                sheet_schema=sheet_schema, template_file_path=_tpl,
                year=_prog_year, business_category=_prog_biz,
                cross_ref_items=[_CRI(wp_code=ci.wp_code, cell=ci.cell) for ci in cross_ref_items],
                prep_info=None, classifications=classifications, audit_cycle=wp_index.audit_cycle,
                source_files=list(getattr(cls, "source_files", []) or []))
            try:
                result = await renderer(ctx)
                if result is not None:
                    sheet_html_data = result
                if ctx.sheet_schema is not None and ctx.sheet_schema != sheet_schema:
                    sheet_schema = ctx.sheet_schema
            except Exception as e:  # noqa: BLE001 — 单 sheet 渲染失败不影响其他 sheet
                logger.warning(
                    "sheet '%s' 渲染失败 (componentType=%s): %s",
                    cls.sheet_name, component_type, e,
                )
                # 事务可能已 aborted → rollback 恢复，避免后续 sheet 级联失败
                try:
                    await db.rollback()
                except Exception:
                    pass
        elif not renderer and _is_multi_sheet and component_type not in _ONLYOFFICE_HTML_WHITELIST and component_type not in _CONFIRMATION_COMPONENTS:
            # 非白名单 + 非 confirmation 精细组件 + 无 renderer + 多 sheet → OnlyOffice WOPI（design §1.1）
            component_type = "onlyoffice-sheet"
            sheet_html_data = {"onlyoffice": True, "sheet_name": cls.sheet_name}
        elif not sheet_html_data and _is_multi_sheet and component_type in _CONFIRMATION_COMPONENTS:
            # confirmation 精细组件首次打开（无持久化数据）→ 返回空的新格式初始数据
            # 前端组件检测 _format → 显示可编辑新表（而非"旧格式只读"降级）
            sheet_html_data = _confirmation_initial_data(component_type)
        elif not sheet_html_data and _tpl and _is_multi_sheet:
            # 白名单内无后端 renderer 且无持久化数据的 sheet（如 d-form-confirmation / d-form-table）：
            # 从模板提取网格 cells 供前端组件消费。
            try:
                from app.services.wp_grid_extract import extract_grid, strip_standard_header
                _grid = extract_grid(_tpl, cls.sheet_name)
                if isinstance(_grid, dict) and _grid.get("cells"):
                    sheet_html_data = strip_standard_header(_grid)
            except Exception:  # noqa: BLE001
                pass
        sheets.append({"sheet_name": cls.sheet_name, "componentType": component_type,
                       "schema": sheet_schema, "html_data": sheet_html_data,
                       "cross_refs": [i.model_dump() for i in cross_ref_items],
                       "sheet_type": _resolve_sheet_type(sheet_schema, schema_data, cls.sheet_name),
                       "field_sources": _extract_field_sources(sheet_schema, schema_data, cls.sheet_name)})

    # Step 7: auto-fill + Step 8: response
    fill_results: dict = {}
    try:
        yr = (await db.execute(sa.text("SELECT EXTRACT(YEAR FROM audit_period_end)::int FROM projects WHERE id = :pid"),
              {"pid": str(project_id)})).first()
        if yr and yr[0]:
            combined = {"sheets": {s["sheet_name"]: s["schema"] for s in sheets if isinstance(s.get("schema"), dict)}}
            try:
                fill_results = await _resolve_auto_fill_values(schema=combined, project_id=project_id, year=yr[0], db=db)
            except Exception as e:
                logger.warning("auto-fill 取数失败 pid=%s: %s", project_id, e)
    except Exception as e:
        logger.warning("auto-fill 年度查询失败 pid=%s: %s", project_id, e)
        # 事务可能已 aborted → rollback 恢复
        try:
            await db.rollback()
        except Exception:
            pass
    from app.services.wp_guidance_service import get_wp_guidance
    return {"wp_id": str(wp_id), "wp_code": wp_code, "project_id": str(project_id),
            "scope": scope, "is_real_workpaper": is_real, "template_version": tpl_ver_str,
            "sheets": sheets, "fill_results": fill_results, "guidance": get_wp_guidance(wp_code)}

