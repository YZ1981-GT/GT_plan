"""底稿渲染配置端点

GET /api/workpapers/{wp_id}/render-config
按 design §5.1.1 实现：获取底稿渲染 schema + 项目数据 + 跨底稿引用。

Requirements: 1.2, 3.0.3, 3.0.5
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user, require_wp_edit_permission
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
from app.services.wp_account_package_resolver import resolve_package_sheets
from app.services.wp_render_schema_service import WpRenderSchemaService
from app.services.wp_template_version_service import WpTemplateVersionService
from app.services.project_audit_year import (
    PROJECT_AUDIT_YEAR_BIZ_SQL,
    PROJECT_AUDIT_YEAR_SQL,
)

# ─── 纯辅助函数/常量抽离到 helpers 模块（行为保持一致的重构）─────────────────
# 这些名字 re-import 回本模块命名空间，故既有调用点无需改动。
# _SEMANTIC_REGISTRY_CACHE 有意不在此 re-import：其经 `global` 变更，仅由被移动的
# 函数持有；本模块不直接引用它。
from app.routers.wp_render_config_helpers import (  # noqa: F401
    _CONFIRMATION_FORMAT_MAP,
    _HEURISTIC_TO_SHEET_CONTENT_TYPE,
    _confirmation_initial_data,
    _extract_field_sources,
    _has_custom_procedure,
    _infer_sheet_type_by_heuristic,
    _infer_sheet_type_from_registry,
    _infer_sheet_type_from_schema,
    _is_standard_wp_code_fn,
    _load_semantic_registry,
    _looks_like_standard_wp_code,
    _maybe_custom_classifications,
    _resolve_sheet_type,
    _resolve_template_path,
    _unpack_sheet_schema,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["wp-render-config"],
)

# ─── Singleton schema service (stateless + cache) ────────────────────────────
_schema_service = WpRenderSchemaService()

# 模板 sheet 顺序缓存（path → (mtime, {sheet_name: index})）。
# render-config 每次调用曾用 openpyxl 同步加载整册模板仅为算 tab 排序（J1 等大底稿约 0.4s），
# 该同步操作阻塞事件循环，并发请求（checklist-responses/active-job）被连累到数秒级。
# 模板文件运行时不变，按 (path, mtime) 缓存后每个模板只加载一次，消除重复阻塞。
_TEMPLATE_SHEET_ORDER_CACHE: dict[str, tuple[float, dict[str, int]]] = {}


def _get_template_sheet_order(tpl_path: str) -> dict[str, int]:
    """返回 {sheet_name: index}（按模板 xlsx tab 顺序），带 (path, mtime) 缓存。"""
    try:
        mtime = os.path.getmtime(tpl_path)
    except OSError:
        return {}
    cached = _TEMPLATE_SHEET_ORDER_CACHE.get(tpl_path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        import openpyxl
        _wb = openpyxl.load_workbook(tpl_path, read_only=True, data_only=True)
        order = {name: idx for idx, name in enumerate(_wb.sheetnames)}
        _wb.close()
    except Exception:  # noqa: BLE001 — 加载失败返回空序（保持原序）
        order = {}
    _TEMPLATE_SHEET_ORDER_CACHE[tpl_path] = (mtime, order)
    return order

# sheet 名尾部的 sheet 级编码提取（如「合同负债及销售替代程序D0-5」→「D0-5」、
# 「审定表D2-1」→「D2-1」、「应收票据审计程序表D1A」→「D1A」）。
# 用于多 sheet 底稿按 sheet 级编码查 _WP_CODE_OVERRIDE（协作者 confirmation-* 精细组件）。
_SHEET_CODE_RE = re.compile(r"([A-Z]\d+[A-Z]?(?:-\d+[a-z]?)*)\s*$")

# ─── 整册专属组件（多 sheet 但整册路由到同一 componentType，靠 sheetName v-if 分发） ──
# 这类底稿本身没有 account_package_registry 条目（非科目工作包），但设计上要求
# 整个 wp 的所有 sheet 都渲染为同一个专属自加载组件（如 C1 → GtC1EntityControl，
# 内部按 sheetName 分发 program/example/fr-summary/process-record）。
# 多 sheet dispatch 默认逐 sheet 按 class_code 派生（会把 C1 拆成 a-program-console +
# onlyoffice-sheet），故此处显式声明：当 wp_code override ∈ 本集合时，多 sheet 分支
# 统一采用 wp_code override（等价于 pkg_sheets 的 else 分支）。
# 只影响 override 命中本集合的 wp_code，对其余底稿零回归。
# 单一来源：backend/app/services/dedicated_component_types.py
# 契约：WHOLE ⊆ VALID ∩ FE；WHOLE − DISPATCH ⊆ WHITELIST ∪ CONFIRMATION
from app.services.dedicated_component_types import DEDICATED_COMPONENT_TYPES

_WHOLE_WP_MULTISHEET_DEDICATED: set[str] = set(DEDICATED_COMPONENT_TYPES)

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
    "confirmation-alternative-f05",
    "confirmation-alternative-f06",
    "confirmation-diff-securities",
    "confirmation-alternative-g06",
    "confirmation-alternative-h05",
    "confirmation-alternative-k05",
    "confirmation-alternative-k06",
    "confirmation-reliability",
    "confirmation-fraud-risk",
}

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
    "d4-operating-revenue",
    "d1-notes-receivable",
    "d2-accounts-receivable",
    "d3-prepaid-accounts",
    "d5-receivables-financing",
    "d6-contract-assets",
    "d7-contract-liabilities",
    # A/B 多 sheet Bundle（纯前端聚合，无后端 RENDERER_DISPATCH）
    "a10-bundle",
    "a11-bundle",
    "a12-bundle",
    "a15-bundle",
    "a16-bundle",
    "a17-bundle",
    "b2-bundle",
    "b13-bundle",
    "b19-bundle",
    "b51-bundle",
    # S32/S33 纯前端聚合组件（无后端 renderer）：保留 componentType，禁止改写为 onlyoffice-sheet
    "s32-fraud-bundle",
    "s33-ann14-bundle",
    # K12/K13 营业外收入/支出（K13 render 策略待后续 Task，暂保留白名单）
    "k12-non-operating-income",
    "k13-non-operating-expense",
    # H7 生产性生物资产（RENDERER_DISPATCH 在 Phase 5 创建，暂保留白名单）
    "h7-biological-assets",
}

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


@router.post("/{wp_id}/audit-sheet-refresh")
async def refresh_audit_sheet_from_ledger(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_wp_edit_permission()),
):
    """一键刷新（模块/循环级，Module_Refresh）：从四表库（试算表/辅助余额表）预填充审定表/明细表数据。

    门禁（公式管理库 Req 20）：由裸 ``get_current_user`` 收敛为 ``require_wp_edit_permission``
    编辑权门禁——对目标底稿具编辑权者即可触发（不锁死为合伙人），无编辑权返回 403
    且不执行任何数据写入。全局一键刷新（合伙人专属）见 ``POST /draft-refresh``（Req 1）。

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
        PROJECT_AUDIT_YEAR_SQL,
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
    component_type: str | None = Query(None, alias="force_component_type", description="强制使用指定 componentType 渲染策略"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取底稿渲染 schema + 项目数据 + 跨底稿引用（dispatch 模式）。"""
    try:
        return await _get_render_config_impl(wp_id, sheet_name, db, current_user, force_component_type=component_type)
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
    force_component_type: str | None = None,
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
    # 提前固化 audit_cycle 到本地变量：后续 Step 4b 聚合失败 / 单 sheet 渲染失败会触发
    # `await db.rollback()`，使 wp_index ORM 对象过期；若在 per-sheet 循环里再访问
    # wp_index.audit_cycle 会触发同步 lazy-load → 异步上下文 MissingGreenlet 致命 500
    # （H7 等多 sheet 底稿首当其冲）。早取本地值避免过期重载。
    audit_cycle = wp_index.audit_cycle
    # 同理固化 current_user.id（rollback 后 User ORM 对象亦过期，循环内访问 .id 会崩）。
    _user_id = current_user.id

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
        pj = (await db.execute(
            PROJECT_AUDIT_YEAR_BIZ_SQL, {"pid": str(project_id)}
        )).first()
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
                    if not (c.sheet_name and "GT_Custom" in c.sheet_name)
                    and not (getattr(c, "class_code", "") or "").startswith("I-")
                    and _WP_CODE_OVERRIDE.get(c.sheet_name) != "skip"
                    and not (c.sheet_name and (c.sheet_name.endswith("-原版") or c.sheet_name.endswith("-原")))]
    _is_multi_sheet = len(_real_sheets) > 1

    # 多 sheet 底稿 tab 排序：按模板 xlsx sheetnames 顺序排列
    # （DB created_at 顺序不可靠；openpyxl read_only 取 sheetnames → 按 index 排序）
    # 注意：pkg_sheets（来自 account_package_registry）的顺序已经是正确的 registry 声明顺序，
    # 不应被模板 xlsx 的 sheet tab 顺序覆盖（registry 名称可能与模板 sheet tab 名不完全匹配）。
    if _is_multi_sheet and not pkg_sheets and _tpl and str(_tpl).endswith((".xlsx", ".xls")):
        _template_order = _get_template_sheet_order(str(_tpl))  # 带 (path,mtime) 缓存，避免每次同步加载整册
        if _template_order:
            classifications = sorted(
                classifications,
                key=lambda c: _template_order.get(c.sheet_name, 999),
            )

    sheets: list[dict] = []
    for cls in classifications:
        if sheet_name and cls.sheet_name != sheet_name:
            continue
        if cls.sheet_name and "GT_Custom" in cls.sheet_name:
            continue
        # sheet_name 级 skip override（隐藏辅助 sheet，如 A1-11 的文号规则页）
        if cls.sheet_name and _WP_CODE_OVERRIDE.get(cls.sheet_name) == "skip":
            continue
        # 隐藏"原版/原"历史遗留程序表（如 "J1A-原版"、"L1A-原"）
        if cls.sheet_name and (cls.sheet_name.endswith("-原版") or cls.sheet_name.endswith("-原")):
            continue
        # 隐藏"原版本备份"、"参考用-"前缀、以"（原）"结尾的历史遗留 sheet
        if cls.sheet_name and ("原版本备份" in cls.sheet_name or cls.sheet_name.startswith("参考用-") or cls.sheet_name.endswith("（原）")):
            continue
        # 隐藏含"删除"关键字的历史遗留sheet（如 "股份支付检查表J1-10-删除"/"IPO企业股权激励工具-删除"）
        if cls.sheet_name and "删除" in cls.sheet_name:
            continue
        # 编码级 skip override：从 sheet_name 提取编码后再查（如 "C1-1 企业层面..." → "C1-1" → skip）
        if cls.sheet_name:
            _skip_m = _SHEET_CODE_RE.search(cls.sheet_name)
            if _skip_m and _WP_CODE_OVERRIDE.get(_skip_m.group(1)) == "skip":
                continue
            # 补充：编码在开头的场景（如 "C1-4-4企业层面..." → "C1-4-4"）
            if not _skip_m:
                _skip_m2 = re.match(r"([A-Z]\d+(?:-\d+)*)", cls.sheet_name)
                if _skip_m2 and _WP_CODE_OVERRIDE.get(_skip_m2.group(1)) == "skip":
                    continue
            # 向导式专属组件隐藏辅助sheet（选项清单/底稿目录/示例/不打印，无标准编码）
            _ovr_check = _WP_CODE_OVERRIDE.get(wp_code)
            if _ovr_check and _ovr_check in _WHOLE_WP_MULTISHEET_DEDICATED:
                _sn_lower = cls.sheet_name
                if ("选项清单" in _sn_lower or "不归档" in _sn_lower or "底稿目录" in _sn_lower
                        or "不打印" in _sn_lower or _sn_lower.startswith("示例")):
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
                    # sheet 级 override 命中（精细 confirmation-* 组件 或 *A→专属组件内分发）→ 直接采用
                    component_type = _sheet_ovr
                elif ovr in _WHOLE_WP_MULTISHEET_DEDICATED:
                    # 整册专属组件（如 C1→c1-entity-level-control）：所有 sheet 统一路由到
                    # wp_code override，由前端专属组件按 sheetName v-if 内部分发（对齐 D4 标准）。
                    component_type = ovr
                elif pkg_sheets and ovr:
                    # pkg_sheets（专属组件 registry）模式：非 b-index 的 sheet 统一用 wp_code override
                    # （附注/明细/调整等都路由到同一专属组件由其内部按 sheetName 分发）
                    # 但合成底稿目录（class_code 以 "B-" 开头）保留原生 b-index 渲染
                    _cls_code_prefix = (getattr(cls, "class_code", "") or "")[:2]
                    if _cls_code_prefix == "B-":
                        try:
                            component_type = derive_component_type(cls, ignore_wp_code_override=True)
                        except ClassificationNotFoundError:
                            component_type = "b-index"
                    else:
                        component_type = ovr
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
        # 但如果 sheet 已有 _sheet_ovr（专属组件 override），不强制走 OO
        _cls_code = getattr(cls, "class_code", "") or ""
        if _is_multi_sheet and _cls_code.startswith("G-") and not _sheet_ovr:
            component_type = "onlyoffice-sheet"
            sheet_html_data = {"onlyoffice": True, "sheet_name": cls.sheet_name}
            sheets.append({"sheet_name": cls.sheet_name, "componentType": component_type,
                           "schema": sheet_schema, "html_data": sheet_html_data,
                           "cross_refs": [i.model_dump() for i in cross_ref_items],
                           })
            continue

        renderer = RENDERER_DISPATCH.get(component_type)
        # force_component_type 覆盖（A1 Dashboard 子Tab需强制使用指定渲染策略）
        if force_component_type and force_component_type in RENDERER_DISPATCH:
            component_type = force_component_type
            renderer = RENDERER_DISPATCH[force_component_type]
        if renderer:
            ctx = RenderContext(
                db=db, project_id=project_id, wp_id=wp_id, wp_code=wp_code,
                working_paper=working_paper, classification=cls,
                component_type=component_type, sheet_html_data=sheet_html_data,
                sheet_schema=sheet_schema, template_file_path=_tpl,
                year=_prog_year, business_category=_prog_biz,
                cross_ref_items=[_CRI(wp_code=ci.wp_code, cell=ci.cell) for ci in cross_ref_items],
                prep_info=None, classifications=classifications, audit_cycle=audit_cycle,
                source_files=list(getattr(cls, "source_files", []) or []),
                user_id=_user_id)
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
        # skip 类 sheet 不加入输出（隐藏的辅助说明 sheet）
        if component_type == "skip":
            continue
        sheets.append({"sheet_name": cls.sheet_name, "componentType": component_type,
                       "schema": sheet_schema, "html_data": sheet_html_data,
                       "cross_refs": [i.model_dump() for i in cross_ref_items],
                       "sheet_type": _resolve_sheet_type(sheet_schema, schema_data, cls.sheet_name),
                       "field_sources": _extract_field_sources(sheet_schema, schema_data, cls.sheet_name)})

    # Step 7: auto-fill + Step 8: response
    fill_results: dict = {}
    try:
        yr = (await db.execute(PROJECT_AUDIT_YEAR_SQL, {"pid": str(project_id)})).first()
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

    # Step 9: word-template sign_status + OnlyOffice permissions
    sign_status: str | None = None
    permissions: dict | None = None
    _first_ct = sheets[0]["componentType"] if sheets else None
    if _first_ct == "word-template" and _prog_year:
        # scope 格式：A16 子版本 → word_template:A16:{wp_code}；其他 → word_template:{wp_code}
        if wp_code.startswith("A16-"):
            _sign_scope = f"word_template:A16:{wp_code}"
        else:
            _sign_scope = f"word_template:{wp_code}"
        try:
            from app.services.field_override_service import FieldOverrideService
            _fos = FieldOverrideService(db)
            sign_status = await _fos.get(
                project_id=project_id, year=_prog_year,
                scope=_sign_scope, item_key="sign_status", field="value",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("sign_status 查询失败 wp_code=%s: %s", wp_code, e)
        if not sign_status:
            sign_status = "draft"
        permissions = {"edit": sign_status != "signed"}

    response = {"wp_id": str(wp_id), "wp_code": wp_code, "project_id": str(project_id),
                "scope": scope, "is_real_workpaper": is_real, "template_version": tpl_ver_str,
                "audit_year": _prog_year,
                "sheets": sheets, "fill_results": fill_results, "guidance": get_wp_guidance(wp_code)}
    if sign_status is not None:
        response["sign_status"] = sign_status
        response["permissions"] = permissions
    return response

