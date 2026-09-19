"""F2 存货明细 — 导入导出（按 sheet 实际列结构）."""

from __future__ import annotations

import io
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    import_rows_generic,
    load_json_rows,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_rows,
    workbook_to_response,
    col_val,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f2-import-export"])

# 与前端 f2DetailSheetConfigs.ts 对齐
_F2_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "F2-3": {"category": "原材料", "account": "1401", "has_quantity": True, "extra_column": None, "kind": "detail"},
    "F2-4": {"category": "材料采购在途", "account": "1402", "has_quantity": True, "extra_column": None, "kind": "detail"},
    "F2-5": {"category": "周转材料", "account": "1403", "has_quantity": True, "extra_column": None, "kind": "detail"},
    "F2-6": {"category": "自制半成品", "account": "1404", "has_quantity": True, "extra_column": None, "kind": "detail"},
    "F2-7": {"category": "委托加工物资", "account": "1405", "has_quantity": True, "extra_column": None, "kind": "detail"},
    "F2-8": {"category": "库存商品", "account": "1406", "has_quantity": True, "extra_column": "出库方式", "kind": "detail"},
    "F2-9": {"category": "发出商品", "account": "1407", "has_quantity": True, "extra_column": None, "kind": "detail"},
    "F2-10": {"category": "开发产品", "account": "1408", "has_quantity": True, "extra_column": None, "kind": "detail"},
    "F2-11": {"category": "开发成本", "account": "1409", "has_quantity": True, "extra_column": None, "kind": "detail"},
    "F2-12": {"category": "合同履约成本", "account": "1410", "has_quantity": False, "extra_column": None, "kind": "detail"},
    "F2-13": {"category": "消耗性生物资产", "account": "1411", "has_quantity": True, "extra_column": None, "kind": "detail"},
    "F2-14": {"kind": "adjustment", "title": "调整分录 F2-14"},
    "F2-19": {"kind": "production_sales", "title": "产销量变动 F2-19"},
    "F2-20": {"kind": "cost_comparison", "title": "成本比较 F2-20"},
    "F2-29": {"kind": "cutoff", "title": "存货(原材料/产成品)截止-入库(账→单) F2-29"},
    "F2-30": {"kind": "cutoff", "title": "存货(原材料/产成品)截止-入库(单→账) F2-30"},
    "F2-31": {"kind": "cutoff", "title": "存货(原材料/产成品)截止-出库(账→单) F2-31"},
    "F2-32": {"kind": "cutoff", "title": "存货(原材料/产成品)截止-出库(单→账) F2-32"},
}

from ._f2_disclosure_import_export import (
    SHEET_LISTED as _SHEET_NOTE_LISTED,
    SHEET_SOE as _SHEET_NOTE_SOE,
    build_disclosure_workbook,
    export_disclosure_data,
    import_disclosure_data,
)

# 附注披露（多区块：一区块一 sheet + 文本域集中一 sheet）
_DISCLOSURE_SHEETS: dict[str, str] = {
    _SHEET_NOTE_LISTED: "listed",
    _SHEET_NOTE_SOE: "soe",
}

_SUPPORTED_SHEETS = set(_F2_SHEET_CONFIGS.keys()) | {"F2-1"} | set(_DISCLOSURE_SHEETS)

_STORAGE_FIELD = "remark"

# ─── F2-1 审定表 导入导出（per-field item_id，非 JSON 数组） ─────────────────
from ._f2_inventory_main import F2_CATEGORIES

_F2_1_GROSS_CATEGORIES = [c for c in F2_CATEGORIES if c["rowKey"] != "impairment-provision"]
_F2_1_IMPAIRMENT_CATEGORIES = [c for c in F2_CATEGORIES if c["rowKey"] == "impairment-provision"]

_F2_1_HEADERS = ["类别名", "科目编码", "期初未审数", "本期增加", "本期减少", "账项调整"]
_F2_1_FIELD_MAP = {
    "期初未审数": "opening",
    "本期增加": "increase",
    "本期减少": "decrease",
    "账项调整": "adjustment",
}
_F2_1_NUMERIC_FIELDS = {"opening", "increase", "decrease", "adjustment"}

_F2_1_LABEL_TO_ROW_KEY = {c["label"]: c["rowKey"] for c in F2_CATEGORIES}
_F2_1_ROW_KEY_TO_LABEL = {c["rowKey"]: c["label"] for c in F2_CATEGORIES}
_F2_1_ROW_KEY_TO_ACCOUNT = {c["rowKey"]: c["account"] for c in F2_CATEGORIES}


def _f2_1_item_id(block: str, row_key: str, field: str) -> str:
    return f"F2-1-{block}-{row_key}-{field}"


async def _export_f2_1_template(db: AsyncSession, wp_id: str) -> StreamingResponse:
    """导出 F2-1 审定表模板（编制说明 + 原值 + 跌价准备）."""
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    # Sheet 1: 编制说明
    ws_guide = wb.active
    ws_guide.title = "编制说明"
    ws_guide.append(["F2-1 存货审定表 — 导入模板编制说明"])
    ws_guide.append([])
    ws_guide.append(["一、本模板含两张数据工作表：「原值」和「跌价准备」。"])
    ws_guide.append(["二、按「类别名」匹配行，不匹配的行将被跳过。"])
    ws_guide.append(["三、空值/非数值字段不覆盖已有数据（只写有效数字）。"])
    ws_guide.append(["四、「科目编码」列仅供参考，导入按「类别名」定位。"])
    ws_guide.append(["五、四表取数提示：期初未审数=TB(科目,期初余额), 增加=TB(科目,借方发生额), 减少=TB(科目,贷方发生额)"])
    ws_guide.append([])
    ws_guide.append(["字段说明："])
    ws_guide.append(["  期初未审数 — 本年期初余额（未审数）"])
    ws_guide.append(["  本期增加 — 本期借方发生额（增加）"])
    ws_guide.append(["  本期减少 — 本期贷方发生额（减少）"])
    ws_guide.append(["  账项调整 — 审计调整净额（AJE 影响）"])

    # Sheet 2: 原值
    ws_gross = wb.create_sheet("原值")
    ws_gross.append(_F2_1_HEADERS)
    # 表头加粗
    for cell in ws_gross[1]:
        cell.font = Font(bold=True)
    for cat in _F2_1_GROSS_CATEGORIES:
        ws_gross.append([cat["label"], cat["account"], None, None, None, None])

    # Sheet 3: 跌价准备
    ws_imp = wb.create_sheet("跌价准备")
    ws_imp.append(_F2_1_HEADERS)
    for cell in ws_imp[1]:
        cell.font = Font(bold=True)
    for cat in _F2_1_IMPAIRMENT_CATEGORIES:
        ws_imp.append([cat["label"], cat["account"], None, None, None, None])

    return workbook_to_response(wb, "F2-1 存货审定表_模板.xlsx")


async def _export_f2_1_data(db: AsyncSession, wp_id: str) -> StreamingResponse:
    """导出 F2-1 审定表当前数据."""
    from openpyxl.styles import Font
    import sqlalchemy as sa

    # 查 checklist_responses 中以 F2-1- 开头的 item_id
    from app.models.checklist_response_models import ChecklistResponse as CR

    stmt = sa.select(CR.item_id, CR.conclusion).where(
        CR.wp_id == wp_id,
        CR.item_id.like("F2-1-%"),
    )
    result = await db.execute(stmt)
    rows_raw = result.all()

    # 按 block/rowKey/field 解析
    data: dict[str, dict[str, dict[str, float]]] = {}  # block -> rowKey -> field -> value
    for item_id, conclusion in rows_raw:
        # F2-1-{block}-{rowKey}-{field}
        parts = item_id.split("-", 3)  # ['F2', '1', '{block}-{rowKey}-{field}']
        if len(parts) < 3:
            continue
        rest = item_id[len("F2-1-"):]  # e.g. "gross-raw-materials-opening"
        # block is first segment, field is last segment, rowKey is middle
        # Pattern: {block}-{rowKey}-{field}
        # field is one of: opening/increase/decrease/adjustment
        for field in _F2_1_NUMERIC_FIELDS:
            suffix = f"-{field}"
            if rest.endswith(suffix):
                prefix = rest[: -len(suffix)]
                # prefix = "gross-raw-materials" → split on first "-" to get block+rowKey
                dash_idx = prefix.find("-")
                if dash_idx < 0:
                    continue
                block = prefix[:dash_idx]
                row_key = prefix[dash_idx + 1:]
                data.setdefault(block, {}).setdefault(row_key, {})[field] = safe_float(conclusion)
                break

    wb = Workbook()
    ws_guide = wb.active
    ws_guide.title = "编制说明"
    ws_guide.append(["F2-1 存货审定表 — 数据导出"])
    ws_guide.append([f"底稿 ID: {wp_id}"])

    # Sheet 2: 原值
    ws_gross = wb.create_sheet("原值")
    ws_gross.append(_F2_1_HEADERS)
    for cell in ws_gross[1]:
        cell.font = Font(bold=True)
    for cat in _F2_1_GROSS_CATEGORIES:
        rk = cat["rowKey"]
        row_data = data.get("gross", {}).get(rk, {})
        ws_gross.append([
            cat["label"],
            cat["account"],
            row_data.get("opening"),
            row_data.get("increase"),
            row_data.get("decrease"),
            row_data.get("adjustment"),
        ])

    # Sheet 3: 跌价准备
    ws_imp = wb.create_sheet("跌价准备")
    ws_imp.append(_F2_1_HEADERS)
    for cell in ws_imp[1]:
        cell.font = Font(bold=True)
    for cat in _F2_1_IMPAIRMENT_CATEGORIES:
        rk = cat["rowKey"]
        row_data = data.get("impairment", {}).get(rk, {})
        ws_imp.append([
            cat["label"],
            cat["account"],
            row_data.get("opening"),
            row_data.get("increase"),
            row_data.get("decrease"),
            row_data.get("adjustment"),
        ])

    return workbook_to_response(wb, "F2-1 存货审定表_数据.xlsx")


async def _import_f2_1_data(db: AsyncSession, wp_id: str, content: bytes) -> dict[str, Any]:
    """导入 F2-1 审定表数据（按类别名匹配行，逐字段 UPSERT）."""
    import openpyxl
    import sqlalchemy as sa

    from app.models.checklist_response_models import ChecklistResponse as CR
    from app.models.workpaper_models import WorkingPaper

    # 反查 project_id
    wp_result = await db.execute(
        sa.select(WorkingPaper.project_id).where(WorkingPaper.id == wp_id)
    )
    wp_row = wp_result.first()
    if not wp_row:
        raise HTTPException(404, "底稿不存在")
    project_id = str(wp_row[0])

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)

    _SHEET_BLOCK_MAP = {"原值": "gross", "跌价准备": "impairment"}

    imported_count = 0
    skipped_count = 0
    field_count = 0
    warnings: list[str] = []

    for sheet_name, block in _SHEET_BLOCK_MAP.items():
        if sheet_name not in wb.sheetnames:
            warnings.append(f"未找到工作表「{sheet_name}」")
            continue
        ws = wb[sheet_name]
        rows_iter = ws.iter_rows(min_row=2, values_only=True)  # skip header
        for row_values in rows_iter:
            if not row_values or not row_values[0]:
                continue
            category_name = str(row_values[0]).strip()
            # 按类别名或 rowKey 匹配
            row_key = _F2_1_LABEL_TO_ROW_KEY.get(category_name)
            if not row_key:
                # 尝试直接作为 rowKey
                if category_name in _F2_1_ROW_KEY_TO_LABEL:
                    row_key = category_name
                else:
                    skipped_count += 1
                    warnings.append(f"未知类别「{category_name}」已跳过")
                    continue

            # 逐字段解析（列索引 2-5 对应 期初未审数/本期增加/本期减少/账项调整）
            field_names = ["opening", "increase", "decrease", "adjustment"]
            row_has_data = False
            for col_idx, field in enumerate(field_names, start=2):
                val = row_values[col_idx] if col_idx < len(row_values) else None
                if val is None:
                    continue
                try:
                    num_val = float(val)
                except (ValueError, TypeError):
                    continue
                # UPSERT
                item_id = _f2_1_item_id(block, row_key, field)
                stmt = sa.text("""
                    INSERT INTO checklist_responses (wp_id, item_id, project_id, conclusion)
                    VALUES (:wp_id, :item_id, :project_id, :val)
                    ON CONFLICT (wp_id, item_id)
                    DO UPDATE SET conclusion = :val
                """)
                await db.execute(stmt, {
                    "wp_id": wp_id,
                    "item_id": item_id,
                    "project_id": project_id,
                    "val": str(num_val),
                })
                field_count += 1
                row_has_data = True
            if row_has_data:
                imported_count += 1

    wb.close()
    await db.commit()

    result: dict[str, Any] = {
        "ok": True,
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "field_count": field_count,
        "errors": [],
    }
    if warnings:
        result["warnings"] = warnings
    return result


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}")


def _sheet_kind(sheet: str) -> str:
    return _F2_SHEET_CONFIGS[sheet].get("kind", "detail")


def _headers(sheet: str) -> list[str]:
    cfg = _F2_SHEET_CONFIGS[sheet]
    kind = _sheet_kind(sheet)
    if kind == "adjustment":
        return ["调整事项说明", "科目编码", "科目名称", "借方金额", "贷方金额", "分录类型", "索引", "备注"]
    if kind == "production_sales":
        return ["产品名称", "本期产量", "上期产量", "本期销量", "上期销量", "期初库存", "入库", "出库", "期末库存"]
    if kind == "cost_comparison":
        return ["产品名称", "产量", "材料", "人工", "制造费用", "上期合计", "异常说明"]
    if kind == "cutoff":
        return [
            "存货类别",
            "供应商/部门",
            "凭证日期",
            "凭证号",
            "业务内容",
            "品名",
            "金额",
            "单据号",
            "单据日期",
            "单据金额",
            "质检编号",
            "质检日期",
            "其他单号",
            "其他日期",
            "是否跨期",
            "截止正确",
            "备注",
        ]
    headers = ["品名"]
    if cfg["has_quantity"]:
        headers.extend(["期初数量", "期初金额", "增加数量", "增加金额", "减少数量", "减少金额"])
    else:
        headers.extend(["期初金额", "增加金额", "减少金额"])
    headers.extend(["1年以内", "1-2年", "2-3年", "3年以上"])
    if cfg.get("extra_column"):
        headers.append(cfg["extra_column"])
    return headers


def _field_keys(sheet: str) -> list[str]:
    cfg = _F2_SHEET_CONFIGS[sheet]
    kind = _sheet_kind(sheet)
    if kind == "adjustment":
        return ["summary", "accountCode", "accountName", "debitAmount", "creditAmount", "entryType", "indexRef", "remark"]
    if kind == "production_sales":
        return ["productName", "currentProduction", "priorProduction", "currentSales", "priorSales", "openingStock", "inbound", "outbound", "closingStock"]
    if kind == "cost_comparison":
        return ["productName", "currentQty", "currentMaterial", "currentLabor", "currentOverhead", "priorTotal", "anomalyNote"]
    if kind == "cutoff":
        return [
            "invCategory",
            "party",
            "bookDate",
            "voucherNo",
            "businessContent",
            "itemName",
            "amount",
            "docNo",
            "docDate",
            "docAmount",
            "inspectNo",
            "inspectDate",
            "otherDocNo",
            "otherDocDate",
            "isCrossPeriod",
            "isCorrect",
            "remark",
        ]
    keys = ["itemName"]
    if cfg["has_quantity"]:
        keys.extend(["openingQty", "openingAmt", "increaseQty", "increaseAmt", "decreaseQty", "decreaseAmt"])
    else:
        keys.extend(["openingAmt", "increaseAmt", "decreaseAmt"])
    keys.extend(["agingLt1", "aging1to2", "aging2to3", "agingGt3"])
    if cfg.get("extra_column"):
        keys.append("extra")
    return keys


def _template_meta(sheet: str) -> tuple[str, str, list[str]]:
    cfg = _F2_SHEET_CONFIGS[sheet]
    kind = _sheet_kind(sheet)
    if kind != "detail":
        title = cfg["title"]
        guidance = [f"{title} 编制说明", "", "列结构与 HTML 底稿一致。", "导入后请核对公式自动计算字段。"]
        return title, "", guidance
    title = f"{cfg['category']}明细表 {sheet}"
    subtitle = f"科目代码: {cfg['account']}"
    guidance = [
        f"{title} 编制说明",
        "",
        "1. 本模板列结构与 HTML 底稿 F2 明细表一致（按 sheet 区分是否含数量列）。",
        "2. 带数量 sheet：品名|期初/增减(数量+金额)|库龄四段|附加列(如有)。",
        "3. 无数量 sheet（F2-12）：品名|期初/增减(仅金额)|库龄四段。",
        "4. 期末数量/金额、单价、库龄合计由系统公式自动计算，无需填写。",
        "5. 库龄四段之和应等于期末金额。",
    ]
    if cfg.get("extra_column"):
        guidance.append(f"6. 「{cfg['extra_column']}」列仅 {sheet} 需要填写。")
    return title, subtitle, guidance


def _header_row_index() -> int:
    return 3  # title + subtitle + headers


def _parse_f2_row(sheet: str, row: tuple, headers: list[str]) -> dict:
    from uuid import uuid4

    kind = _sheet_kind(sheet)
    cfg = _F2_SHEET_CONFIGS[sheet]

    if kind == "adjustment":
        return {
            "rowId": str(uuid4()),
            "seq": 0,
            "summary": safe_str(col_val(row, headers, "调整事项说明")),
            "accountCode": safe_str(col_val(row, headers, "科目编码")),
            "accountName": safe_str(col_val(row, headers, "科目名称")),
            "debitAmount": safe_float(col_val(row, headers, "借方金额")),
            "creditAmount": safe_float(col_val(row, headers, "贷方金额")),
            "entryType": safe_str(col_val(row, headers, "分录类型")) or "AJE",
            "indexRef": safe_str(col_val(row, headers, "索引")),
            "remark": safe_str(col_val(row, headers, "备注")),
            "noteItem": "",
        }
    if kind == "production_sales":
        return {
            "rowId": str(uuid4()),
            "productName": safe_str(col_val(row, headers, "产品名称")),
            "currentProduction": safe_float(col_val(row, headers, "本期产量")),
            "priorProduction": safe_float(col_val(row, headers, "上期产量")),
            "currentSales": safe_float(col_val(row, headers, "本期销量")),
            "priorSales": safe_float(col_val(row, headers, "上期销量")),
            "openingStock": safe_float(col_val(row, headers, "期初库存")),
            "inbound": safe_float(col_val(row, headers, "入库")),
            "outbound": safe_float(col_val(row, headers, "出库")),
            "closingStock": safe_float(col_val(row, headers, "期末库存")),
        }
    if kind == "cost_comparison":
        prior_total = safe_float(col_val(row, headers, "上期合计"))
        return {
            "rowId": str(uuid4()),
            "productName": safe_str(col_val(row, headers, "产品名称")),
            "currentQty": safe_float(col_val(row, headers, "产量")),
            "currentMaterial": safe_float(col_val(row, headers, "材料")),
            "currentLabor": safe_float(col_val(row, headers, "人工")),
            "currentOverhead": safe_float(col_val(row, headers, "制造费用")),
            "priorQty": 0,
            "priorMaterial": prior_total,
            "priorLabor": 0,
            "priorOverhead": 0,
            "anomalyNote": safe_str(col_val(row, headers, "异常说明")),
        }
    if kind == "cutoff":
        correct_raw = safe_str(col_val(row, headers, "截止正确")).lower()
        is_correct = correct_raw in ("是", "true", "1", "yes", "y")
        cross_raw = safe_str(col_val(row, headers, "是否跨期")).lower()
        is_cross = cross_raw in ("是", "true", "1", "yes", "y") if cross_raw else not is_correct
        cat_raw = safe_str(col_val(row, headers, "存货类别"))
        if cat_raw in ("原材料", "raw"):
            inv_category = "raw"
        elif cat_raw in ("产成品", "库存商品", "finished"):
            inv_category = "finished"
        else:
            inv_category = ""
        return {
            "id": str(uuid4()),
            "seq": 0,
            "invCategory": inv_category,
            "party": safe_str(col_val(row, headers, "供应商/部门")),
            "bookDate": safe_str(col_val(row, headers, "凭证日期"))
            or safe_str(col_val(row, headers, "记账日期")),
            "voucherNo": safe_str(col_val(row, headers, "凭证号")),
            "businessContent": safe_str(col_val(row, headers, "业务内容")),
            "itemName": safe_str(col_val(row, headers, "品名")),
            "amount": safe_float(col_val(row, headers, "金额")),
            "quantity": safe_float(col_val(row, headers, "数量")),
            "docNo": safe_str(col_val(row, headers, "单据号"))
            or safe_str(col_val(row, headers, "单号")),
            "docDate": safe_str(col_val(row, headers, "单据日期")),
            "docAmount": safe_float(col_val(row, headers, "单据金额")),
            "inspectNo": safe_str(col_val(row, headers, "质检编号")),
            "inspectDate": safe_str(col_val(row, headers, "质检日期")),
            "otherDocNo": safe_str(col_val(row, headers, "其他单号")),
            "otherDocDate": safe_str(col_val(row, headers, "其他日期")),
            "isCorrect": is_correct,
            "remark": safe_str(col_val(row, headers, "备注")),
            "isCrossPeriod": is_cross,
            "correctPeriod": "",
            "bookedPeriod": "",
            "suggestion": "",
        }

    data: dict[str, Any] = {"id": str(uuid4()), "itemName": safe_str(col_val(row, headers, "品名"))}
    if cfg["has_quantity"]:
        data.update({
            "openingQty": safe_float(col_val(row, headers, "期初数量")),
            "openingAmt": safe_float(col_val(row, headers, "期初金额")),
            "increaseQty": safe_float(col_val(row, headers, "增加数量")),
            "increaseAmt": safe_float(col_val(row, headers, "增加金额")),
            "decreaseQty": safe_float(col_val(row, headers, "减少数量")),
            "decreaseAmt": safe_float(col_val(row, headers, "减少金额")),
        })
    else:
        data.update({
            "openingQty": 0,
            "openingAmt": safe_float(col_val(row, headers, "期初金额")),
            "increaseQty": 0,
            "increaseAmt": safe_float(col_val(row, headers, "增加金额")),
            "decreaseQty": 0,
            "decreaseAmt": safe_float(col_val(row, headers, "减少金额")),
        })
    data.update({
        "agingLt1": safe_float(col_val(row, headers, "1年以内")),
        "aging1to2": safe_float(col_val(row, headers, "1-2年")),
        "aging2to3": safe_float(col_val(row, headers, "2-3年")),
        "agingGt3": safe_float(col_val(row, headers, "3年以上")),
    })
    extra = cfg.get("extra_column")
    if extra:
        data["extra"] = safe_str(col_val(row, headers, extra))
    return data


def _export_f2_row(sheet: str, data: dict) -> list:
    headers = _headers(sheet)
    keys = _field_keys(sheet)
    row: list[Any] = []
    kind = _sheet_kind(sheet)
    for h, k in zip(headers, keys):
        val = data.get(k)
        if kind == "cost_comparison" and k == "priorTotal":
            val = (data.get("priorMaterial") or 0) + (data.get("priorLabor") or 0) + (data.get("priorOverhead") or 0)
        if kind == "cutoff" and k == "isCorrect":
            val = "是" if data.get("isCorrect") else "否"
        if isinstance(val, (int, float)):
            row.append(val)
        elif val is None:
            row.append("")
        else:
            row.append(val)
    return row


@router.post("/api/workpapers/{wp_id}/f2/export-template")
async def f2_export_template(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    if sheet in _DISCLOSURE_SHEETS:
        variant = _DISCLOSURE_SHEETS[sheet]
        wb = build_disclosure_workbook(variant)  # type: ignore[arg-type]
        return workbook_to_response(wb, f"{sheet}_模板.xlsx")
    if sheet == "F2-1":
        return await _export_f2_1_template(db, wp_id)
    headers = _headers(sheet)
    title, subtitle, guidance = _template_meta(sheet)
    wb = build_workbook_template(sheet, headers, title=title, subtitle=subtitle, guidance=guidance)
    return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/f2/export-data")
async def f2_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    if sheet in _DISCLOSURE_SHEETS:
        variant = _DISCLOSURE_SHEETS[sheet]
        wb = await export_disclosure_data(db, wp_id, variant)  # type: ignore[arg-type]
        return workbook_to_response(wb, f"{sheet}_数据.xlsx")
    if sheet == "F2-1":
        return await _export_f2_1_data(db, wp_id)
    headers = _headers(sheet)
    item_id = f"{sheet}-rows"
    rows_data = await load_json_rows(db, wp_id, item_id, field=_STORAGE_FIELD)
    title, subtitle, guidance = _template_meta(sheet)
    wb = build_workbook_template(sheet, headers, title=title, subtitle=subtitle, guidance=guidance)
    ws = wb[sheet]
    for d in rows_data:
        ws.append(_export_f2_row(sheet, d))
    return workbook_to_response(wb, f"{sheet}_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/f2/import-data")
async def f2_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _validate_sheet(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")
    # 披露页走多区块逻辑（一区块一 sheet）
    if sheet in _DISCLOSURE_SHEETS:
        return await import_disclosure_data(
            db, wp_id, _DISCLOSURE_SHEETS[sheet], content,  # type: ignore[arg-type]
        )
    # F2-1 走自定义逻辑（per-field item_id）
    if sheet == "F2-1":
        return await _import_f2_1_data(db, wp_id, content)
    headers = _headers(sheet)
    try:
        actual, raw_rows = parse_upload_xlsx(content, headers, header_row=_header_row_index())
    except ValueError as e:
        return {"ok": False, "errors": [str(e)], "imported_count": 0}
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件")
    rows_data, truncated = import_rows_generic(
        raw_rows, actual, _field_keys(sheet), parse_fn=lambda r, h: _parse_f2_row(sheet, r, h),
    )
    await upsert_json_rows(db, wp_id, f"{sheet}-rows", rows_data, field=_STORAGE_FIELD)
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows_data), "errors": []}
    if truncated:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
