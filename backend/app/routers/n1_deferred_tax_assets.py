"""N1 递延所得税资产 — 导入导出三级端点

3个端点：
- GET  /api/n1-deferred-tax-assets/{wp_id}/export-template   空白模板xlsx
- GET  /api/n1-deferred-tax-assets/{wp_id}/export-data        当前数据xlsx
- POST /api/n1-deferred-tax-assets/{wp_id}/import-data        解析xlsx写入（multipart）

科目编码: 1811递延所得税资产（**借方/资产类**）
导入导出目标: N1-2明细表 / N1-4测算表 / N1-5亏损检查表（均为动态行）
列: 项目名称 / 分类 / 账面价值 / 计税基础 / 可抵扣暂时性差异 / 适用税率 /
    期初递延税资产 / 本期确认 / 本期转回 / 期末递延税资产 / 备注
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 3.4
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/n1-deferred-tax-assets",
    tags=["N1 递延所得税资产"],
)

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

# 🔴 铁律：每张挂了「导入导出 ▾」的 sheet 都必须在此注册。
#    N1-4/N1-5 此前未注册，而前端调用又不传 sheet → 落到 Query 默认值 "N1-2"
#    → 在测算表/亏损表页面导出到的是明细表数据、导入会覆盖 N1-2 明细行（串表+数据破坏）。
_SUPPORTED_SHEETS: set[str] = {"N1-2", "N1-4", "N1-5"}

# ⚠️ 导入导出铁律：表头/字段/item_id/存储列必须与前端 useN1Detail 完全一致，
#    否则导出恒空、导入前端读不到（四重不匹配）。
#    前端真源：item_id="N1-2-detail-rows"，存储列=conclusion（JSON 数组），
#    行字段=N1DetailRow（id/itemName/category/bookValue/taxBase/beginDiff/
#    beginTaxRate/beginAje/beginRje/endDiff/endTaxRate/endAje/endRje/
#    recognized/reversed/remark）；派生列（递延税资产）由前端 engine 计算，不导入。

# N1-2 明细表列头（15列，对应前端可编辑字段）
_SHEET_HEADERS: dict[str, list[str]] = {
    "N1-2": [
        "项目名称", "分类", "账面价值", "计税基础",
        "期初暂时性差异", "期初适用税率", "期初AJE", "期初RJE",
        "期末暂时性差异", "期末适用税率", "期末AJE", "期末RJE",
        "本期确认", "本期转回", "备注",
    ],
    # N1-4 测算表（对应前端 N1CalcTableRow 可编辑字段；派生列由前端 engine 计算不导入）
    "N1-4": [
        "项目名称", "账面价值", "计税基础", "适用税率",
        "递延税资产对方科目", "递延所得税资产期末账面余额",
        "递延税负债对方科目", "递延所得税负债期末账面余额",
    ],
    # N1-5 亏损检查表（重建为源模板结构：按到期年度列示，spec n1-loss-check-source-alignment Task 5.1）
    "N1-5": [
        "到期年度", "上期不确认递延所得税资产的可弥补亏损", "本期账面金额",
        "本期审计调整", "确认递延所得税资产的可弥补亏损", "适用税率",
        "依据", "到期前是否有足够的应纳税所得额",
        "其中：来源于生产经营所得", "其中：来源于以前期间产生的应纳税暂时性差异",
        "其中：来源于其他原因", "检查底稿索引", "备注",
    ],
}

# 中文列名 → JSON 字段名映射（字段名 = 前端 N1DetailRow 字段）
_FIELD_MAPS: dict[str, dict[str, str]] = {
    "N1-2": {
        "项目名称": "itemName",
        "分类": "category",
        "账面价值": "bookValue",
        "计税基础": "taxBase",
        "期初暂时性差异": "beginDiff",
        "期初适用税率": "beginTaxRate",
        "期初AJE": "beginAje",
        "期初RJE": "beginRje",
        "期末暂时性差异": "endDiff",
        "期末适用税率": "endTaxRate",
        "期末AJE": "endAje",
        "期末RJE": "endRje",
        "本期确认": "recognized",
        "本期转回": "reversed",
        "备注": "remark",
    },
    "N1-4": {
        "项目名称": "itemName",
        "账面价值": "bookValue",
        "计税基础": "taxBase",
        "适用税率": "taxRate",
        "递延税资产对方科目": "assetCounterAccount",
        "递延所得税资产期末账面余额": "assetBookBalance",
        "递延税负债对方科目": "liabilityCounterAccount",
        "递延所得税负债期末账面余额": "liabilityBookBalance",
    },
    "N1-5": {
        "到期年度": "expiryYear",
        "上期不确认递延所得税资产的可弥补亏损": "priorUnrecognized",
        "本期账面金额": "bookAmount",
        "本期审计调整": "auditAdjustment",
        "确认递延所得税资产的可弥补亏损": "recognizedAmount",
        "适用税率": "taxRate",
        "依据": "basis",
        "到期前是否有足够的应纳税所得额": "sufficient",
        "其中：来源于生产经营所得": "sourceOperating",
        "其中：来源于以前期间产生的应纳税暂时性差异": "sourceTemporaryDiff",
        "其中：来源于其他原因": "sourceOther",
        "检查底稿索引": "indexRef",
        "备注": "remark",
    },
}

# 数值类型字段
_NUMERIC_FIELDS: dict[str, set[str]] = {
    "N1-2": {
        "bookValue", "taxBase",
        "beginDiff", "beginTaxRate", "beginAje", "beginRje",
        "endDiff", "endTaxRate", "endAje", "endRje",
        "recognized", "reversed",
    },
    "N1-4": {
        "bookValue", "taxBase", "taxRate",
        "assetBookBalance", "liabilityBookBalance",
    },
    "N1-5": {
        "priorUnrecognized", "bookAmount", "auditAdjustment",
        "recognizedAmount", "taxRate",
    },
}

# 整数字段（年度/年限：safe_float 会写成 2025.0，前端直接参与 `lossYear + maxYears` 与展示）
_INT_FIELDS: dict[str, set[str]] = {
    "N1-5": {"expiryYear"},
}

# checklist_responses item_id（= 前端 composable 的持久化键）
_SHEET_ITEM_ID: dict[str, str] = {
    "N1-2": "N1-2-detail-rows",   # useN1Detail   ITEM_PREFIX = 'N1-2-detail'
    "N1-4": "N1-4-calc-rows",     # useN1CalcTable ITEM_PREFIX = 'N1-4-calc'
    "N1-5": "N1-5-rows",           # useN1LossCheck 新键（spec n1-loss-check-source-alignment）
}

# checklist_responses 存储列（= 前端读取的列）
_SHEET_STORAGE_FIELD: dict[str, str] = {
    "N1-2": "conclusion",
    "N1-4": "conclusion",
    "N1-5": "conclusion",
}

# 行 id 前缀（= 前端各 composable addRow 生成的 id 前缀）
_SHEET_ROW_ID_PREFIX: dict[str, str] = {
    "N1-2": "row",
    "N1-4": "calc",
    "N1-5": "loss",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _validate_sheet(sheet_code: str) -> None:
    """校验sheet编码"""
    if sheet_code not in _SUPPORTED_SHEETS:
        raise HTTPException(
            400,
            f"不支持的sheet: {sheet_code}。支持: {sorted(_SUPPORTED_SHEETS)}",
        )


def _safe_float(val: Any) -> float:
    """安全转float"""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_str(val: Any) -> str:
    """安全转str"""
    if val is None:
        return ""
    return str(val).strip()


def _create_template_wb(sheet_code: str) -> Workbook:
    """创建空白模板xlsx（含表头+格式，无数据行）"""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_code

    headers = _SHEET_HEADERS[sheet_code]
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx, col_name in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        ws.column_dimensions[cell.column_letter].width = max(len(col_name) * 2 + 4, 12)

    ws.freeze_panes = "A2"
    return wb


def _get_actual_headers(ws: Any) -> list[str]:
    """获取worksheet实际列头"""
    headers: list[str] = []
    for cell in next(ws.iter_rows(min_row=1, max_row=1)):
        if cell.value is not None:
            headers.append(str(cell.value).strip())
    return headers


def _validate_columns(ws: Any, sheet_code: str) -> list[str]:
    """校验列头，返回不匹配的列名列表"""
    expected = set(_SHEET_HEADERS[sheet_code])
    actual = set(_get_actual_headers(ws))
    missing = [h for h in expected if h not in actual]
    return missing


def _col_val(row: tuple, actual_headers: list[str], col_name: str) -> Any:
    """从行数据中按列名取值"""
    try:
        idx = actual_headers.index(col_name)
        return row[idx] if idx < len(row) else None
    except (ValueError, IndexError):
        return None


def _export_row(sheet_code: str, data: dict) -> list:
    """将JSON dict按列头顺序转为导出行"""
    headers = _SHEET_HEADERS[sheet_code]
    field_map = _FIELD_MAPS.get(sheet_code, {})
    result = []
    for col_name in headers:
        field = field_map.get(col_name, col_name)
        val = data.get(field, "")
        result.append(val if val is not None else "")
    return result


# sufficient 解析集合（是/Y/y/yes/√ → 'yes'，否/N/n/no → 'no'，空 → ''）
_SUFFICIENT_YES = {"是", "Y", "y", "yes", "Yes", "YES", "√", "true", "True", "TRUE"}
_SUFFICIENT_NO = {"否", "N", "n", "no", "No", "NO", "false", "False", "FALSE"}
# 来源三选解析集合（√/是/Y/1/TRUE → true，其余 → false）
_SOURCE_TRUE = {"√", "是", "Y", "y", "1", "true", "True", "TRUE", "yes", "Yes"}

# 是否充足字段
_SUFFICIENT_FIELDS: set[str] = {"sufficient"}
# 来源三选字段
_SOURCE_FLAG_FIELDS: set[str] = {"sourceOperating", "sourceTemporaryDiff", "sourceOther"}


def _parse_sufficient(raw: Any) -> str:
    """解析是否充足字段：是/Y/y/yes/√ → 'yes'，否/N/n/no → 'no'，空 → ''"""
    s = _safe_str(raw).strip()
    if s in _SUFFICIENT_YES:
        return "yes"
    if s in _SUFFICIENT_NO:
        return "no"
    return ""


def _parse_source_flag(raw: Any) -> bool:
    """解析来源三选：√/是/Y/1/TRUE → true，其余 → false"""
    s = _safe_str(raw).strip()
    return s in _SOURCE_TRUE


def _parse_row(sheet_code: str, row: tuple, actual_headers: list[str], seq: int = 1) -> dict:
    """将xlsx行数据按列名映射为JSON dict

    行标识用前端 N1DetailRow 的 `id` 字段（前端按 id 做行操作，rowId 不被消费）。
    """
    field_map = _FIELD_MAPS.get(sheet_code, {})
    prefix = _SHEET_ROW_ID_PREFIX.get(sheet_code, "row")
    result: dict[str, Any] = {"id": f"{prefix}-{seq}"}
    int_fields = _INT_FIELDS.get(sheet_code, set())
    for col_name, field_name in field_map.items():
        raw = _col_val(row, actual_headers, col_name)
        if field_name in int_fields:
            result[field_name] = int(_safe_float(raw))
        elif field_name in _NUMERIC_FIELDS.get(sheet_code, set()):
            result[field_name] = _safe_float(raw)
        elif field_name in _SUFFICIENT_FIELDS:
            result[field_name] = _parse_sufficient(raw)
        elif field_name in _SOURCE_FLAG_FIELDS:
            result[field_name] = _parse_source_flag(raw)
        else:
            result[field_name] = _safe_str(raw)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def n1_export_template(
    wp_id: str,
    sheet: str = Query("N1-2", description="Sheet编码: N1-2 / N1-4 / N1-5"),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（含表头+格式，无数据行）

    Query params:
        sheet: 指定导出sheet（默认N1-2）

    Requirements: 3.4
    """
    _validate_sheet(sheet)

    wb = _create_template_wb(sheet)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"N1递延所得税资产_{sheet}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/{wp_id}/export-data")
async def n1_export_data(
    wp_id: str,
    sheet: str = Query("N1-2", description="Sheet编码: N1-2 / N1-4 / N1-5"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（N1-2明细表动态行数据）

    Query params:
        sheet: 指定导出sheet（默认N1-2）

    Requirements: 3.4
    """
    _validate_sheet(sheet)

    item_id = _SHEET_ITEM_ID[sheet]
    storage_field = _SHEET_STORAGE_FIELD[sheet]
    rows_data: list[dict] = []

    result = await db.execute(
        sa.text(
            f"SELECT {storage_field} AS payload FROM checklist_responses "  # noqa: S608
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": item_id},
    )
    row = result.fetchone()
    if row and row.payload:
        try:
            rows_data = json.loads(row.payload)
        except (json.JSONDecodeError, TypeError):
            pass

    # 生成 xlsx
    wb = _create_template_wb(sheet)
    ws = wb.active

    for data_row in rows_data:
        ws.append(_export_row(sheet, data_row))

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"N1递延所得税资产_{sheet}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/{wp_id}/import-data")
async def n1_import_data(
    wp_id: str,
    sheet: str = Query("N1-2", description="Sheet编码: N1-2 / N1-4 / N1-5"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（N1-2明细表动态行）

    Query params:
        sheet: 指定导入目标sheet（默认N1-2）

    验证：文件大小 ≤ 10MB、文件扩展名(.xlsx/.xls)、列头匹配

    Returns:
        { imported_count: int, field_count: int, warning?: str }

    Requirements: 3.4
    """
    _validate_sheet(sheet)

    # 读取上传文件
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小超过 10MB 限制")

    # 文件扩展名校验
    filename = file.filename or ""
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in ("xlsx", "xls"):
        raise HTTPException(400, f"不支持的文件类型: .{suffix}，仅支持 .xlsx/.xls")

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件")

    ws = wb.active

    # 校验列头
    missing = _validate_columns(ws, sheet)
    if missing:
        raise HTTPException(400, f"列名不匹配，缺少: {missing}")

    actual_headers = _get_actual_headers(ws)

    # 解析数据行
    parsed_rows: list[dict] = []
    warning: str | None = None
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row_idx > _ROW_LIMIT + 1:
            warning = f"数据行超过{_ROW_LIMIT}行限制，已截断"
            break
        # 跳过全空行
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        parsed_rows.append(
            _parse_row(sheet, row, actual_headers, seq=len(parsed_rows) + 1)
        )

    # 写入 checklist_responses
    item_id = _SHEET_ITEM_ID[sheet]
    storage_field = _SHEET_STORAGE_FIELD[sheet]
    json_str = json.dumps(parsed_rows, ensure_ascii=False)

    # ⚠️ checklist_responses.project_id 为 NOT NULL：即使 ON CONFLICT 命中 UPDATE，
    #    PG 也会先校验 INSERT 行的 NOT NULL 约束 → 漏 project_id 必 500。
    proj_row = (
        await db.execute(
            sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id"),
            {"wp_id": wp_id},
        )
    ).fetchone()
    if not proj_row:
        raise HTTPException(404, f"底稿不存在: {wp_id}")

    await db.execute(
        sa.text(
            f"INSERT INTO checklist_responses (id, project_id, wp_id, item_id, {storage_field}) "  # noqa: S608
            "VALUES (:id, :pid, :wp_id, :item_id, :payload) "
            f"ON CONFLICT (wp_id, item_id) DO UPDATE SET {storage_field} = :payload"
        ),
        {
            "id": str(uuid4()),
            "pid": str(proj_row.project_id),
            "wp_id": wp_id,
            "item_id": item_id,
            "payload": json_str,
        },
    )
    await db.commit()

    field_count = len(_FIELD_MAPS.get(sheet, {}))
    result: dict[str, Any] = {
        "imported_count": len(parsed_rows),
        "field_count": field_count,
        "message": f"成功导入 {len(parsed_rows)} 行数据",
    }
    if warning:
        result["warning"] = warning
    return result
