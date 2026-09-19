"""公式模块导入导出端点（Req 23）+ 编报说明/说明文档单一源端点（Req 25.2/25.3）。

遵循平台统一「导入导出▾」规范（``el-dropdown`` 三项，复用 composable + 三端点）：

- ``POST /api/formula-management/import-export/export-template``：导出模板
  （首区块=编报说明 + 示例公式行，Req 23.2）。
- ``POST /api/formula-management/import-export/export-data``：导出当前页面/模块
  已有公式（预设库条目，含最近计算时间，Req 23.3）。
- ``POST /api/formula-management/import-export/import-data``：上传 xlsx，逐条经
  ACNR ``full_resolve`` 校验引用，悬空报告并跳过，有效项幂等入库（Req 23.4）。

另提供说明文档单一源端点（供前端说明弹窗 ``GtFormulaPresetDialog`` 同源消费）：

- ``GET /api/formula-management/reporting-instructions``：结构化说明文档 / Markdown
  （与导出模板编报说明同源，Req 23.6 / 25.3）。

鉴权：三端点经 ``get_current_user``（http/axios 自动携带 Authorization）。中文文件名
按 RFC 5987 编码（复用 ``delivery_export.content_disposition_attachment``，Req 23.5）。
service 只 flush，router 层 commit（导入写入 seed 文件为文件系统操作，无 DB 事务）。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.services.formula_management.delivery_export import (
    content_disposition_attachment,
)
from app.services.formula_management.formula_import_export import (
    build_data_workbook,
    build_template_workbook,
    parse_import_rows,
    validate_single_formula_refs,
    workbook_to_bytes,
)
from app.services.formula_management.preset_library import (
    VALID_FORMULA_TYPES,
    PresetEntry,
    build_inventory,
    build_preset_library,
    compute_preset_coverage,
    find_presets_for_page,
    upsert_custom_presets,
    upsert_seed_presets,
)

# 自定义预设写入角色门控（与平台编辑门控一致：系统管理员 / 业务合伙人 / 签字合伙人）
_CUSTOM_PRESET_WRITE_ROLES = ["admin", "partner", "signing_partner"]
from app.services.formula_management.reporting_instructions import (
    DOC_VERSION,
    instructions_as_dict,
    instructions_as_markdown,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/formula-management",
    tags=["formula-import-export"],
)

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MAX_UPLOAD = 10 * 1024 * 1024  # 10MB


def _xlsx_response(data: bytes, filename: str, *, ascii_fallback: str) -> Response:
    """构造中文文件名 RFC 5987 编码的 xlsx 下载响应（Req 23.5）。"""
    return Response(
        content=data,
        media_type=_XLSX_MEDIA,
        headers={
            "Content-Disposition": content_disposition_attachment(
                filename, ascii_fallback=ascii_fallback
            )
        },
    )


def _filter_entries_by_page(page_key: str | None):
    """构建预设库并按 page_key 过滤（缺省返回全部）。"""
    entries, _stats = build_preset_library()
    if page_key:
        entries = [e for e in entries if e.page_key == page_key]
    return entries


# ── 导出模板（Req 23.1/23.2） ─────────────────────────────────────────────────
@router.post("/import-export/export-template")
async def export_template(
    _user: User = Depends(get_current_user),
) -> Response:
    """导出公式模板：首区块=编报说明（单一源）+ 示例公式行（Req 23.2）。"""
    wb = build_template_workbook()
    data = workbook_to_bytes(wb)
    return _xlsx_response(data, "公式管理_导入模板.xlsx", ascii_fallback="formula_template.xlsx")


# ── 导出数据（Req 23.3） ──────────────────────────────────────────────────────
@router.post("/import-export/export-data")
async def export_data(
    page_key: str | None = Query(default=None, description="页面键过滤（scope:key），缺省导出全部"),
    _user: User = Depends(get_current_user),
) -> Response:
    """导出当前页面/模块已有公式（预设库条目，含最近计算时间列，Req 23.3）。"""
    entries = _filter_entries_by_page(page_key)
    wb = build_data_workbook(entries)
    data = workbook_to_bytes(wb)
    suffix = f"_{page_key.replace(':', '_')}" if page_key else ""
    return _xlsx_response(
        data,
        f"公式管理_数据{suffix}.xlsx",
        ascii_fallback="formula_data.xlsx",
    )


# ── 导入数据（Req 23.4/23.5） ─────────────────────────────────────────────────
@router.post("/import-export/import-data")
async def import_data(
    file: UploadFile = File(...),
    page_key: str | None = Query(default=None, description="可选：限定导入到某页面键（校验一致性）"),
    project_id: str | None = Query(default=None, description="可选：项目上下文，供引用解析"),
    persist: bool = Query(default=True, description="是否把有效条目幂等入库（预设 seed）"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入公式：逐条经 ACNR full_resolve 校验，悬空报告并跳过（Req 23.4）。

    有效条目（引用可解析）幂等写入预设 seed；悬空引用条目在响应 ``skipped`` 中报告，
    不静默入库错误公式。
    """
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > _MAX_UPLOAD:
        raise HTTPException(400, "文件大小不能超过 10MB")

    try:
        result = await parse_import_rows(content, db=db, project_id=project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    # 可选：限定 page_key 一致性（不匹配的有效条目转入跳过报告）
    imported = result.imported
    if page_key:
        from app.services.formula_management.formula_import_export import ImportSkip

        mismatched = [e for e in imported if e.page_key != page_key]
        imported = [e for e in imported if e.page_key == page_key]
        for e in mismatched:
            result.skipped.append(
                ImportSkip(
                    row_number=0,
                    page_key=e.page_key,
                    target_cell=e.target_cell,
                    reason=f"page_key 与目标模块 {page_key} 不一致",
                )
            )
        result.imported = imported

    persist_stats: dict[str, int] | None = None
    if persist and result.imported:
        persist_stats = upsert_seed_presets(result.imported)

    payload = result.to_dict()
    if persist_stats is not None:
        payload["persisted"] = persist_stats
    return payload


# ── 预设库浏览（Req 25.4：弹窗内导航到预设浏览/编辑） ────────────────────────
@router.get("/presets/inventory")
async def get_preset_inventory(
    scope: str | None = Query(
        default=None,
        description="按作用域过滤（workpaper/report/note），缺省返回全部",
    ),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """返回 Preset Inventory 逐页登记 + 覆盖度摘要（供 GtFormulaPresetDialog 浏览）。

    每页含 page_key/scope/preset_status/formula_count/cycle/wp_code/sources；
    ``coverage`` 为 presetted/pending 分布（Req 22.5）。
    """
    entries, _stats = build_preset_library()
    pages = build_inventory(entries)
    if scope:
        pages = [p for p in pages if p.scope == scope]

    def _page_dict(p) -> dict[str, Any]:
        d = p.to_dict()
        # additive 只读派生：该页是否含自定义预设（Task 3.2 / Property 3）
        d["has_custom"] = "custom" in (p.sources or [])
        return d

    return {
        "pages": [_page_dict(p) for p in pages],
        "coverage": compute_preset_coverage(entries=entries),
    }


@router.get("/presets/page")
async def get_preset_page(
    page_key: str = Query(..., description="页面键（scope:key，如 workpaper:D2）"),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """返回某页面（page_key）的预设公式条目（供弹窗浏览/编辑，Req 25.4）。

    未预设页面返回空列表（``presetted=false``），前端据此提示"该页暂无预设"。
    """
    entries = find_presets_for_page(page_key)

    def _entry_dict(e) -> dict[str, Any]:
        d = e.to_dict()
        # additive 只读派生：来源标注（通用 vs 自定义，Task 3.2 / Property 3）
        d["is_custom"] = e.source == "custom"
        return d

    return {
        "page_key": page_key,
        "presetted": bool(entries),
        "presets": [_entry_dict(e) for e in entries],
    }


# ── 自定义预设写入（平台级共享，require edit role，隔离于 seed） ───────────────
@router.post("/presets/custom")
async def create_custom_preset(
    payload: dict[str, Any] = Body(...),
    project_id: str | None = Query(default=None, description="可选：项目上下文，供引用解析"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(_CUSTOM_PRESET_WRITE_ROLES)),
) -> dict[str, Any]:
    """新增/更新一条平台级自定义预设（写 ``formula_custom_presets.json``，隔离于 seed）。

    body：``{page_key, target_cell, expression, formula_type, refs?, description?, variant?}``。
    ``require_role``（admin/partner/signing_partner）为唯一权限防线（Property 5）。
    落库前**复用 ``import-data`` 的逐条 ACNR full_resolve 校验路径**（``validate_single_formula_refs``），
    悬空引用 → 422 携清单**不落库**（Property 6）；通过 → ``upsert_custom_presets``
    写 ``formula_custom_presets.json``（**绝不触碰 seed**，Property 2）。
    """
    page_key = str(payload.get("page_key") or "").strip()
    target_cell = str(payload.get("target_cell") or "").strip()
    expression = str(payload.get("expression") or "").strip()
    formula_type = str(payload.get("formula_type") or "").strip()
    if not page_key or not target_cell:
        raise HTTPException(400, "page_key 与 target_cell 不能为空")
    if not expression:
        raise HTTPException(400, "expression 不能为空")
    if formula_type not in VALID_FORMULA_TYPES:
        raise HTTPException(
            400,
            f"无效公式类型 {formula_type!r}（须为 {sorted(VALID_FORMULA_TYPES)} 之一）",
        )

    raw_refs = payload.get("refs")
    refs_in = raw_refs if isinstance(raw_refs, list) else None

    # 复用 import-data 的 full_resolve 校验路径（悬空 → 422 不落库）
    normalized_refs, dangling = await validate_single_formula_refs(
        expression=expression,
        refs=refs_in,
        project_id=project_id,
        db=db,
    )
    if dangling:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "公式引用悬空（无法经 ACNR 解析），未保存",
                "dangling_refs": dangling,
            },
        )

    stats = upsert_custom_presets(
        [
            PresetEntry(
                page_key=page_key,
                target_cell=target_cell,
                expression=expression,
                formula_type=formula_type,
                refs=normalized_refs,
                source="custom",
                description=str(payload.get("description") or ""),
                variant=payload.get("variant"),
            )
        ]
    )
    return {"ok": True, **stats}


# ── 说明文档单一源（Req 23.6 / 25.2 / 25.3） ─────────────────────────────────
@router.get("/reporting-instructions")
async def get_reporting_instructions_doc(
    fmt: str = Query(default="json", pattern="^(json|markdown)$"),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """返回公式管理编报说明/说明文档（单一源，与导出模板编报说明同源，Req 23.6/25.3）。

    ``fmt=json``（默认）返回结构化区块；``fmt=markdown`` 附带 Markdown 文本，供前端
    说明弹窗直接渲染。
    """
    doc = instructions_as_dict()
    if fmt == "markdown":
        doc["markdown"] = instructions_as_markdown()
    doc["version"] = DOC_VERSION
    return doc
