"""G6 其他债权投资(ECL组) — 导入导出端点

支持 5 张动态表格：
  G6-11 三阶段划分 /
  G6-12 减值准备测算表(22列→2区段Tab) /
  G6-13 预期信用损失计量测试(多区块payload) /
  G6-14 转回核销检查表(转回检查 / 核销检查 2 Tab) /
  G6-15 凭证检查表(v2：样本标准 / 本期发生额 / 期后处置新增)

字段键与前端 composable（useG6EclStageClassification / useG6EclImpairmentCalc /
useG6EclReversalWriteOff / useG6EclVoucherCheck 的行接口）严格对齐，保证 round-trip。

G6-11 单sheet导出。
G6-12 按2区段分sheet导出（未审+调整 / 审定数）。
G6-13 按多区块分sheet导出（方法评价/组合划分/PD-LGD/损失率/参数评价 + 审计结论）。
G6-14 按2 Tab分sheet导出（转回检查 / 核销检查）。
G6-15 按样本标准及两个测试期间分sheet导出。
"""

from __future__ import annotations

import io
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    export_row_by_keys,
    load_json_payload,
    load_json_rows,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_payload,
    upsert_json_rows,
    workbook_to_response,
)

router = APIRouter(tags=["g6-ecl-import-export"])


# ═══════════════════════════════════════════════════════════════════════════════
# G6-11 三阶段划分（单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

_G6_11_HEADERS = [
    "投资项目", "跨表投资ID", "账面余额",
    "显著增加(是/否)", "低风险(是/否)", "已减值(是/否)",
    "企业划分阶段", "审计判断阶段", "一致性(是/否)",
    "差异说明", "索引",
    "SICR分析结论", "低风险分析结论", "减值分析结论",
]
_G6_11_KEYS = [
    "investProject", "crossSheetInvestmentId", "bookBalance",
    "hasSignificantIncrease", "hasLowCreditRisk", "hasCreditImpairment",
    "companyStage", "auditStage", "isConsistent",
    "discrepancyNote", "indexRef",
    "sicrConclusion", "lowRiskConclusion", "impairmentConclusion",
]
_G6_11_REQUIRED_HEADERS = [h for h in _G6_11_HEADERS if h != "跨表投资ID"]
_G6_11_BOOL_KEYS = {
    "hasSignificantIncrease", "hasLowCreditRisk", "hasCreditImpairment", "isConsistent",
}
_G6_11_NUMERIC_KEYS = {"bookBalance"}


# ═══════════════════════════════════════════════════════════════════════════════
# G6-12 减值准备测算表（22列 → 2区段Tab多sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 未审+调整
_G6_12_SEG1_HEADERS = [
    "投资项目", "跨表投资ID", "摊余成本余额①", "公允价值", "预期信用损失率②",
    "坏账准备③", "账面价值④", "余额调整⑤",
    "调整后损失率②A", "坏账调整⑥", "阶段", "OCI影响", "索引",
]
_G6_12_SEG1_KEYS = [
    "investProject", "crossSheetInvestmentId", "amortizedCost", "fairValue", "creditLossRate",
    "impairmentProvision", "bookValue", "balanceAdjustment",
    "adjustedCreditLossRate", "impairmentAdjustment", "stage", "ociImpact", "indexRef",
]

# 区段2: 审定数
_G6_12_SEG2_HEADERS = [
    "投资项目", "跨表投资ID", "审定余额⑦", "审定坏账⑧", "审定账面价值⑨",
    "审定公允价值", "上年坏账", "本年计提",
    "本年转回", "OCI调整", "差异说明",
]
_G6_12_SEG2_KEYS = [
    "investProject", "crossSheetInvestmentId", "adjBalance", "adjImpairment", "adjBookValue",
    "adjFairValue", "priorImpairment", "currentProvision",
    "currentReversal", "ociAdjustment", "differenceNote",
]

# 全列合并（用于导入解析）
_G6_12_ALL_HEADERS = [
    "投资项目", "跨表投资ID", "摊余成本余额①", "公允价值", "预期信用损失率②",
    "坏账准备③", "账面价值④", "余额调整⑤",
    "调整后损失率②A", "坏账调整⑥", "阶段", "OCI影响",
    "审定余额⑦", "审定坏账⑧", "审定账面价值⑨",
    "审定公允价值", "上年坏账", "本年计提",
    "本年转回", "OCI调整", "差异说明", "索引",
]
_G6_12_ALL_KEYS = [
    "investProject", "crossSheetInvestmentId", "amortizedCost", "fairValue", "creditLossRate",
    "impairmentProvision", "bookValue", "balanceAdjustment",
    "adjustedCreditLossRate", "impairmentAdjustment", "stage", "ociImpact",
    "adjBalance", "adjImpairment", "adjBookValue",
    "adjFairValue", "priorImpairment", "currentProvision",
    "currentReversal", "ociAdjustment", "differenceNote", "indexRef",
]

_G6_12_SEGMENTS = [
    ("未审+调整", _G6_12_SEG1_HEADERS, _G6_12_SEG1_KEYS),
    ("审定数", _G6_12_SEG2_HEADERS, _G6_12_SEG2_KEYS),
]

# G6-12 数值字段
_G6_12_NUMERIC_KEYS = {
    "amortizedCost", "fairValue", "creditLossRate",
    "impairmentProvision", "bookValue", "balanceAdjustment",
    "adjustedCreditLossRate", "impairmentAdjustment", "ociImpact",
    "adjBalance", "adjImpairment", "adjBookValue",
    "adjFairValue", "priorImpairment", "currentProvision",
    "currentReversal", "ociAdjustment",
}


# ═══════════════════════════════════════════════════════════════════════════════
# G6-14 转回核销检查表（2 Tab多sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

_G6_14_TAB1_HEADERS = [
    "序号", "单位名称", "跨表投资ID", "类型(转回/收回)", "转回原因", "收回方式",
    "原确定减值准备的依据", "收回或转回金额", "收回或转回前累计已计提",
    "合理性分析", "是否合理", "索引号",
]
_G6_14_TAB1_KEYS = [
    "seq", "unitName", "crossSheetInvestmentId", "kind", "reversalReason", "recoveryMethod",
    "originalBasis", "reversalAmount", "accumulatedProvision",
    "reasonAnalysis", "isReasonable", "indexRef",
]

_G6_14_TAB2_HEADERS = [
    "序号", "单位名称", "债权投资的性质", "核销金额", "核销原因",
    "履行的核销程序", "是否由关联交易产生(是/否)", "合理性分析", "是否合理", "索引号",
]
_G6_14_TAB2_KEYS = [
    "seq", "unitName", "writeOffType", "writeOffAmount", "writeOffReason",
    "writeOffProcedure", "isRelatedParty", "reasonAnalysis", "isReasonable", "indexRef",
]

_G6_14_TABS = [
    ("转回检查", _G6_14_TAB1_HEADERS, _G6_14_TAB1_KEYS),
    ("核销检查", _G6_14_TAB2_HEADERS, _G6_14_TAB2_KEYS),
]

# G6-14 数值字段
_G6_14_NUMERIC_KEYS = {
    "seq", "reversalAmount", "accumulatedProvision", "writeOffAmount",
}

# 旧版 8 列单 sheet
_G6_14_LEGACY_HEADERS = [
    "序号", "投资项目", "转回/核销类型", "金额",
    "原因", "审批程序", "合理性结论", "索引",
]
_G6_14_LEGACY_KEYS = [
    "seq", "investProject", "type", "amount",
    "reason", "approvalProcedure", "reasonConclusion", "indexRef",
]


# ═══════════════════════════════════════════════════════════════════════════════
# G6-15 凭证检查表（22列 → 3区段Tab多sheet导出）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 凭证基础(8列)
_G6_15_SEG1_HEADERS = [
    "日期", "凭证号", "业务内容", "对方科目",
    "明细", "借方", "贷方", "附件",
]
_G6_15_SEG1_KEYS = [
    "date", "voucherNo", "businessContent", "counterAccount",
    "detailAccount", "debitAmount", "creditAmount", "attachment",
]

# 区段2: 核对内容(8列)
_G6_15_SEG2_HEADERS = [
    "凭证号", "支持性文件",
    "核对1-原始凭证(是/否)", "核对2-授权(是/否)",
    "核对3-账务(是/否)", "核对4-金额(是/否)",
    "核对5-分类(是/否)", "核对6-减值(是/否)", "核对7-利息(是/否)",
]
_G6_15_SEG2_KEYS = [
    "voucherNo", "supportingDoc",
    "checkOriginal", "checkAuthorized",
    "checkAccounting", "checkAmount",
    "checkClassification", "checkImpairment", "checkInterest",
]

# 区段3: 结论(6列)
_G6_15_SEG3_HEADERS = [
    "凭证号", "索引", "是否异常(是/否)", "异常说明",
    "风险等级", "处理建议", "备注",
]
_G6_15_SEG3_KEYS = [
    "voucherNo", "indexRef", "isAbnormal", "abnormalNote",
    "riskLevel", "suggestion", "remark",
]

_G6_15_SEGMENTS = [
    ("凭证基础", _G6_15_SEG1_HEADERS, _G6_15_SEG1_KEYS),
    ("核对内容", _G6_15_SEG2_HEADERS, _G6_15_SEG2_KEYS),
    ("结论", _G6_15_SEG3_HEADERS, _G6_15_SEG3_KEYS),
]

# 全列合并（用于导入解析）
_G6_15_ALL_HEADERS = [
    "日期", "凭证号", "业务内容", "对方科目",
    "明细", "借方", "贷方", "附件",
    "支持性文件",
    "核对1-原始凭证(是/否)", "核对2-授权(是/否)",
    "核对3-账务(是/否)", "核对4-金额(是/否)",
    "核对5-分类(是/否)", "核对6-减值(是/否)", "核对7-利息(是/否)",
    "索引", "是否异常(是/否)", "异常说明",
    "风险等级", "处理建议", "备注",
]
_G6_15_ALL_KEYS = [
    "date", "voucherNo", "businessContent", "counterAccount",
    "detailAccount", "debitAmount", "creditAmount", "attachment",
    "supportingDoc",
    "checkOriginal", "checkAuthorized",
    "checkAccounting", "checkAmount",
    "checkClassification", "checkImpairment", "checkInterest",
    "indexRef", "isAbnormal", "abnormalNote",
    "riskLevel", "suggestion", "remark",
]

# G6-15 数值字段
_G6_15_NUMERIC_KEYS = {"debitAmount", "creditAmount"}

# G6-15 布尔字段
_G6_15_BOOL_KEYS = {
    "checkOriginal", "checkAuthorized", "checkAccounting",
    "checkAmount", "checkClassification", "checkImpairment",
    "checkInterest", "isAbnormal",
}

# G6-15 v2：按“样本标准 / 本期发生额 / 期后处置新增”组织，逐笔表保留源模板六项核对。
_G6_15_V2_HEADERS = [
    "日期", "凭证编号", "业务内容", "业务类型", "对方科目", "对方明细科目",
    "借方金额", "贷方金额", "支持性文件",
    "1.原始凭证内容完整", "2.有授权批准", "3.账务处理正确",
    "4.初始成本计算正确", "5.利息计算正确", "6.公允价值符合准则要求",
    "索引号", "人工标记异常", "是否异常", "异常说明", "风险等级",
    "处理建议", "备注说明", "来源", "选样原因", "抽样方法", "选样类别",
    "来源ID", "附件", "附件ID",
]
_G6_15_V2_KEYS = [
    "date", "voucherNo", "businessContent", "businessType", "counterAccount", "detailAccount",
    "debitAmount", "creditAmount", "supportingDoc",
    "checkOriginal", "checkAuthorized", "checkAccounting",
    "checkInitialCost", "checkInterest", "checkFairValue",
    "indexRef", "manualAbnormal", "isAbnormal", "abnormalNote", "riskLevel",
    "suggestion", "remark", "source", "selectionReason", "samplingMethod", "selectionCategory",
    "sourceId", "attachment", "attachmentId",
]
_G6_15_V2_NUMERIC_KEYS = {"debitAmount", "creditAmount"}
_G6_15_V2_BOOL_KEYS = {"manualAbnormal", "isAbnormal"}
_G6_15_V2_CHECK_KEYS = {
    "checkOriginal", "checkAuthorized", "checkAccounting",
    "checkInitialCost", "checkInterest", "checkFairValue",
}
_G6_15_CRITERIA_HEADERS = ["项目", "值"]
_G6_15_CRITERIA_ROWS = [
    ("借方总体笔数", "populationDebitCount"),
    ("借方总体金额", "populationDebitAmount"),
    ("贷方总体笔数", "populationCreditCount"),
    ("贷方总体金额", "populationCreditAmount"),
    ("特定样本", "specificSample"),
    ("特定样本笔数", "specificSampleCount"),
    ("特定样本金额", "specificSampleAmount"),
    ("抽样总体笔数", "samplingPopulationCount"),
    ("抽样总体金额", "samplingPopulationAmount"),
    ("确定的样本量", "sampleSize"),
    ("抽样方法", "samplingMethod"),
    ("抽样过程", "samplingProcess"),
    ("本期借方发生额", "bookDebitOccurrence"),
    ("本期贷方发生额", "bookCreditOccurrence"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G6-11": "G6-11-rows",
    "G6-12": "G6-12-rows",
    "G6-14": "G6-14-rows",
    "G6-15": "G6-15-rows",
}

# G6-13 为 payload 型（非行型），使用独立常量存储键
_G6_13_ITEM_ID = "G6-13-ecl-measurement"
_G6_14_PRIMARY_ITEM_ID = "G6-14-reversal-writeoff-data"

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys()) | {"G6-13"}


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


def _parse_bool(val: Any) -> bool:
    """解析布尔值：'是'/True/'true'/'1' → True, 其他 → False."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("是", "true", "1", "yes", "✓", "√")


def _export_bool(val: Any) -> str:
    """导出布尔值：True→'是', False→'否'."""
    return "是" if val else "否"


def _parse_row_with_types(
    row: tuple,
    headers: list[str],
    field_keys: list[str],
    numeric_keys: set[str],
    bool_keys: set[str] | None = None,
) -> dict[str, Any]:
    """通用行解析，支持数值/布尔/字符串三种类型."""
    values = list(row) + [None] * max(0, len(headers) - len(row))
    out: dict[str, Any] = {"id": str(uuid4())}
    for i, key in enumerate(field_keys):
        if key == "id":
            continue
        raw = values[i] if i < len(values) else None
        if key in numeric_keys:
            out[key] = safe_float(raw)
        elif bool_keys and key in bool_keys:
            out[key] = _parse_bool(raw)
        else:
            out[key] = safe_str(raw)
    return out


def _export_row_with_types(
    data: dict,
    field_keys: list[str],
    bool_keys: set[str] | None = None,
) -> list:
    """通用行导出，布尔字段导出为"是/否"."""
    row: list[Any] = []
    for key in field_keys:
        val = data.get(key)
        if bool_keys and key in bool_keys:
            row.append(_export_bool(val))
        elif isinstance(val, (float, int)):
            row.append(val)
        elif val is None:
            row.append("")
        else:
            row.append(val)
    return row


# ═══════════════════════════════════════════════════════════════════════════════
# G6-14 多sheet导出（2 Tab → 转回检查 + 核销检查）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g6_14_multi_sheet_workbook(
    reversals: list[dict],
    writeoffs: list[dict],
    *,
    template_only: bool = False,
) -> Workbook:
    """G6-14 按转回检查、核销检查两个 Tab 分 sheet 导出。"""
    wb = Workbook()
    wb.remove(wb.active)

    for tab_name, headers, keys in _G6_14_TABS:
        ws = wb.create_sheet(title=tab_name)
        ws.append([f"G6-14 减值准备转回（收回）、核销检查表 — {tab_name}"])
        ws.merge_cells(
            start_row=1,
            start_column=1,
            end_row=1,
            end_column=max(len(headers), 1),
        )
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 18

        if template_only:
            continue
        source_rows = reversals if tab_name == "转回检查" else writeoffs
        for row_data in source_rows:
            if not isinstance(row_data, dict):
                continue
            if tab_name == "核销检查":
                ws.append(_export_row_with_types(
                    row_data,
                    keys,
                    bool_keys={"isRelatedParty"},
                ))
            else:
                ws.append(export_row_by_keys(row_data, keys))

    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G6-14 减值准备转回（收回）、核销检查表 编制说明"])
    ws_guide.append([])
    for line in (
        "本表采用双表结构：转回检查 / 核销检查；转回检查同时记录转回与收回。",
        "转回检查「类型」填：转回 / 收回。",
        "收回或转回金额不得超过收回或转回前累计已计提金额。",
        "核销检查「是否由关联交易产生」填 是/否；关联核销必须填写合理性分析。",
        "是否合理填：合理 / 不合理。",
    ):
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 90
    return wb


def _parse_g6_14_tab(
    ws: Any,
    tab_name: str,
    headers: list[str],
    keys: list[str],
) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    rows: list[dict] = []
    header_values = next(ws.iter_rows(min_row=2, max_row=2, values_only=True), ())
    actual_headers = [safe_str(value) for value in header_values]
    missing = [header for header in headers if header != "跨表投资ID" and header not in actual_headers]
    if missing:
        return [], [{
            "row_number": 2,
            "field": tab_name,
            "reason": f"缺少列: {', '.join(missing)}",
        }]

    key_by_header = dict(zip(headers, keys))
    for row_number, raw_row in enumerate(
        ws.iter_rows(min_row=3, values_only=True),
        start=3,
    ):
        if not any(value is not None and str(value).strip() for value in raw_row):
            continue
        if len(rows) >= ROW_LIMIT:
            errors.append({
                "row_number": row_number,
                "field": tab_name,
                "reason": f"数据行超过{ROW_LIMIT}行限制，已截断",
            })
            break
        ordered_values = []
        for header in headers:
            if header not in actual_headers:
                ordered_values.append(None)
                continue
            col_idx = actual_headers.index(header)
            ordered_values.append(raw_row[col_idx] if col_idx < len(raw_row) else None)
        parsed = _parse_row_with_types(
            tuple(ordered_values),
            headers,
            keys,
            _G6_14_NUMERIC_KEYS,
            bool_keys={"isRelatedParty"} if tab_name == "核销检查" else None,
        )
        cid = safe_str(parsed.get("crossSheetInvestmentId"))
        if cid:
            parsed["crossSheetInvestmentId"] = cid
        if tab_name == "转回检查":
            kind = parsed.get("kind")
            if kind and kind not in ("转回", "收回"):
                errors.append({
                    "row_number": row_number,
                    "field": "kind",
                    "reason": f"类型'{kind}'无效，应为 转回/收回",
                })
        rows.append(parsed)
    return rows, errors


def _legacy_g6_14_row(row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """将旧 8 列扁平行转换为前端双表行。"""
    row_type = safe_str(row.get("type"))
    common = {
        "id": row.get("id") or str(uuid4()),
        "seq": safe_float(row.get("seq")),
        "unitName": safe_str(row.get("investProject")),
        "indexRef": safe_str(row.get("indexRef")),
    }
    if row_type == "核销":
        return "writeOffs", {
            **common,
            "writeOffType": "",
            "writeOffAmount": safe_float(row.get("amount")),
            "writeOffReason": safe_str(row.get("reason")),
            "writeOffProcedure": safe_str(row.get("approvalProcedure")),
            "isRelatedParty": False,
            "reasonAnalysis": safe_str(row.get("reasonConclusion")),
            "isReasonable": safe_str(row.get("reasonConclusion")),
        }
    return "reversals", {
        **common,
        "kind": row_type if row_type in ("转回", "收回") else "转回",
        "reversalReason": safe_str(row.get("reason")),
        "recoveryMethod": safe_str(row.get("approvalProcedure")),
        "originalBasis": "",
        "reversalAmount": safe_float(row.get("amount")),
        "accumulatedProvision": 0.0,
        "reasonAnalysis": safe_str(row.get("reasonConclusion")),
        "isReasonable": safe_str(row.get("reasonConclusion")),
    }


def _parse_g6_14_import(
    content: bytes,
) -> tuple[list[dict], list[dict], list[dict]]:
    """解析 G6-14 双 Tab 文件，并兼容旧 8 列单 sheet 扁平格式。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    reversals: list[dict] = []
    writeoffs: list[dict] = []
    has_tabs = (
        any("转回检查" in name for name in wb.sheetnames)
        and any("核销检查" in name for name in wb.sheetnames)
    )

    if has_tabs:
        for tab_name, headers, keys in _G6_14_TABS:
            sheet_name = next(
                (name for name in wb.sheetnames if tab_name in name),
                None,
            )
            if sheet_name is None:
                errors.append({
                    "row_number": 0,
                    "field": tab_name,
                    "reason": f"缺少工作表: {tab_name}",
                })
                continue
            rows, tab_errors = _parse_g6_14_tab(
                wb[sheet_name],
                tab_name,
                headers,
                keys,
            )
            errors.extend(tab_errors)
            if tab_name == "转回检查":
                reversals.extend(rows)
            else:
                writeoffs.extend(rows)
    else:
        ws = wb.active
        if ws is None:
            wb.close()
            return [], [], [{
                "row_number": 0,
                "field": "",
                "reason": "xlsx文件中无活动工作表",
            }]
        header_row_idx = 1
        actual_headers: list[str] = []
        for row_idx in range(1, min(5, (ws.max_row or 1) + 1)):
            values = next(
                ws.iter_rows(
                    min_row=row_idx,
                    max_row=row_idx,
                    values_only=True,
                ),
                (),
            )
            candidate = [safe_str(value) for value in values]
            if "转回/核销类型" in candidate or "投资项目" in candidate:
                header_row_idx = row_idx
                actual_headers = candidate
                break
        if not actual_headers:
            errors.append({
                "row_number": header_row_idx,
                "field": "",
                "reason": "无法识别旧版表头，缺少'转回/核销类型'或'投资项目'列",
            })
        else:
            key_by_header = dict(zip(_G6_14_LEGACY_HEADERS, _G6_14_LEGACY_KEYS))
            for row_number, raw_row in enumerate(
                ws.iter_rows(min_row=header_row_idx + 1, values_only=True),
                start=header_row_idx + 1,
            ):
                if not any(value is not None and str(value).strip() for value in raw_row):
                    continue
                if len(reversals) + len(writeoffs) >= ROW_LIMIT:
                    errors.append({
                        "row_number": row_number,
                        "field": "",
                        "reason": f"数据行超过{ROW_LIMIT}行限制，已截断",
                    })
                    break
                parsed: dict[str, Any] = {"id": str(uuid4())}
                for col_idx, header in enumerate(actual_headers):
                    key = key_by_header.get(header)
                    if not key:
                        continue
                    raw = raw_row[col_idx] if col_idx < len(raw_row) else None
                    parsed[key] = (
                        safe_float(raw) if key in {"seq", "amount"} else safe_str(raw)
                    )
                row_type = safe_str(parsed.get("type"))
                if row_type not in ("转回", "核销", "收回"):
                    errors.append({
                        "row_number": row_number,
                        "field": "type",
                        "reason": f"类型'{row_type}'无效，应为 转回/核销/收回",
                    })
                    continue
                target, converted = _legacy_g6_14_row(parsed)
                (writeoffs if target == "writeOffs" else reversals).append(converted)

    wb.close()
    return reversals, writeoffs, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G6-12 多sheet导出（2区段→2 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g6_12_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G6-12 按2区段分sheet导出，每个区段一个worksheet."""
    wb = Workbook()
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G6_12_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        # 标题行
        ws.append([f"G6-12 其他债权投资减值准备测算表 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        # 表头行
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16

        if not template_only:
            for row_data in rows:
                ws.append(export_row_by_keys(row_data, seg_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G6-12 其他债权投资减值准备测算表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "22列拆为2区段Tab：未审+调整 / 审定数；另含跨表投资ID列。",
        "跨表投资ID 用于跨表稳定匹配，可留空；导入后优先按该 ID 对齐。",
        "公式列（③=①×②, ④=①-③, ⑥=⑤×②A+①×(②A-②), ⑦=①+⑤, ⑧=③+⑥, ⑨=⑦-⑧）导入后前端自动重算。",
        "阶段填：Stage1 / Stage2 / Stage3。",
        "预期信用损失率②和调整后损失率②A填小数（如 0.05 表示 5%）。",
        "坏账调整⑥可为负数（当审计师调低信用损失率时=冲回）。",
        "OCI影响/OCI调整为其他债权投资特有列（FVOCI类减值通过OCI调整）。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g6_12_import(content: bytes) -> tuple[list[dict], list[dict]]:
    """解析G6-12导入文件，支持多sheet或单sheet两种格式。返回(rows, errors)."""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet格式（2区段分sheet）
    multi_sheet = len(wb.sheetnames) >= 2 and any("未审" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G6_12_SEGMENTS:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append({"row_number": 0, "field": "", "reason": f"缺少工作表: {seg_name}"})
                continue
            header_row_idx = 2
            actual_headers = [
                str(c.value).strip() if c.value else ""
                for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
            ]
            missing = [h for h in seg_headers if h != "跨表投资ID" and h not in actual_headers]
            if missing:
                errors.append({"row_number": 0, "field": seg_name, "reason": f"缺少列: {', '.join(missing)}"})
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                if row_idx not in rows_dict:
                    rows_dict[row_idx] = {"id": str(uuid4())}
                values = list(row)
                for header, key in zip(seg_headers, seg_keys):
                    if key == "id" or header not in actual_headers:
                        continue
                    col_i = actual_headers.index(header)
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_12_NUMERIC_KEYS:
                        rows_dict[row_idx][key] = safe_float(raw)
                    else:
                        rows_dict[row_idx][key] = safe_str(raw)
                cid = safe_str(rows_dict[row_idx].get("crossSheetInvestmentId"))
                if cid:
                    rows_dict[row_idx]["crossSheetInvestmentId"] = cid
                    rows_dict[row_idx]["id"] = cid
    else:
        # 策略2: 单sheet宽表
        ws = wb.active
        if ws is None:
            wb.close()
            return [], [{"row_number": 0, "field": "", "reason": "xlsx文件中无活动工作表"}]
        header_row_idx = 1
        for r in range(1, min(5, (ws.max_row or 1) + 1)):
            row_cells = list(ws.iter_rows(min_row=r, max_row=r))
            if not row_cells:
                continue
            test_row = [str(c.value).strip() if c.value else "" for c in row_cells[0]]
            if "投资项目" in test_row or "摊余成本" in test_row:
                header_row_idx = r
                break
        header_cells = list(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        if not header_cells:
            errors.append({"row_number": 0, "field": "", "reason": "xlsx文件中无有效表头行"})
            wb.close()
            return [], errors
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in header_cells[0]
        ]
        if "投资项目" not in actual_headers:
            errors.append({"row_number": header_row_idx, "field": "", "reason": "无法识别表头，缺少'投资项目'列"})
            wb.close()
            return [], errors
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append({"row_number": row_idx + header_row_idx + 1, "field": "", "reason": f"数据行超过{ROW_LIMIT}行限制，已截断"})
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in _G6_12_ALL_HEADERS:
                    key_idx = _G6_12_ALL_HEADERS.index(h)
                    key = _G6_12_ALL_KEYS[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_12_NUMERIC_KEYS:
                        parsed[key] = safe_float(raw)
                    else:
                        parsed[key] = safe_str(raw)
            cid = safe_str(parsed.get("crossSheetInvestmentId"))
            if cid:
                parsed["crossSheetInvestmentId"] = cid
                parsed["id"] = cid
            rows_dict[row_idx] = parsed

    wb.close()
    result = list(rows_dict.values())
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append({"row_number": ROW_LIMIT, "field": "", "reason": f"数据行超过{ROW_LIMIT}行限制，已截断"})
    return result, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G6-13 预期信用损失计量测试（payload JSON → 多 worksheet，对齐 G4-11）
# ═══════════════════════════════════════════════════════════════════════════════

_G6_13_METHOD_HEADERS = ["检查项目", "检查内容", "企业采用方法", "审计评价", "说明"]
_G6_13_METHOD_KEYS = ["checkItem", "checkContent", "companyMethod", "auditEvaluation", "note"]

_G6_13_GROUP_HEADERS = ["组合名称", "划分依据", "信用风险特征", "样本量", "审计评价", "说明"]
_G6_13_GROUP_KEYS = ["groupName", "basis", "riskCharacteristic", "sampleSize", "auditEvaluation", "note"]

_G6_13_PDLGD_HEADERS = [
    "投资项目/组合", "跨表投资ID", "账面余额", "剩余月数", "阶段", "评级",
    "外部映射PD", "期限折算PD", "LGD", "ECL率", "预期信用损失",
    "上期历史损失率", "说明",
]
_G6_13_PDLGD_KEYS = [
    "projectName", "crossSheetInvestmentId", "bookBalance", "remainingMonths", "stage", "rating",
    "externalMappedPd", "termAdjustedPd", "lgd", "eclRate", "eclAmount",
    "priorHistoricalLossRate", "note",
]

_G6_13_LOSS_HEADERS = [
    "投资项目/组合", "跨表投资ID", "账面余额", "剩余月数", "阶段", "评级",
    "损失率", "说明", "前瞻性调整", "ECL率", "预期信用损失",
    "上期历史损失率", "备注",
]
_G6_13_LOSS_KEYS = [
    "projectName", "crossSheetInvestmentId", "bookBalance", "remainingMonths", "stage", "rating",
    "lossRate", "description", "forwardLookingAdj", "eclRate", "eclAmount",
    "priorHistoricalLossRate", "note",
]

_G6_13_PARAM_HEADERS = ["参数名称", "数据来源", "计算方法", "审计验证结果", "审计评价", "说明"]
_G6_13_PARAM_KEYS = [
    "paramName", "dataSource", "calcMethod", "verificationResult", "auditEvaluation", "note",
]

_G6_13_SEGMENTS = [
    ("方法评价", _G6_13_METHOD_HEADERS, _G6_13_METHOD_KEYS, "methodEvaluation"),
    ("组合划分", _G6_13_GROUP_HEADERS, _G6_13_GROUP_KEYS, "groupBasis"),
    ("PD-LGD测算", _G6_13_PDLGD_HEADERS, _G6_13_PDLGD_KEYS, "pdLgdRows"),
    ("损失率法", _G6_13_LOSS_HEADERS, _G6_13_LOSS_KEYS, "lossRateRows"),
    ("参数评价", _G6_13_PARAM_HEADERS, _G6_13_PARAM_KEYS, "parameterEvaluation"),
]

_G6_13_NUMERIC_KEYS = {
    "sampleSize", "bookBalance", "remainingMonths",
    "externalMappedPd", "termAdjustedPd", "lgd", "eclRate", "eclAmount",
    "priorHistoricalLossRate", "lossRate", "forwardLookingAdj",
}


def _empty_g6_13_payload() -> dict[str, Any]:
    return {
        "methodEvaluation": [],
        "groupBasis": [],
        "parameterEvaluation": [],
        "pdLgdRows": [],
        "lossRateRows": [],
        "conclusion": "",
    }


def _normalize_g6_13_payload(raw: Any) -> dict[str, Any]:
    base = _empty_g6_13_payload()
    if not isinstance(raw, dict):
        return base
    for key in (
        "methodEvaluation",
        "groupBasis",
        "parameterEvaluation",
        "pdLgdRows",
        "lossRateRows",
    ):
        val = raw.get(key)
        base[key] = val if isinstance(val, list) else []
    conclusion = raw.get("conclusion")
    base["conclusion"] = safe_str(conclusion) if conclusion is not None else ""
    return base


def _build_g6_13_multi_sheet_workbook(payload: dict[str, Any], *, template_only: bool = False) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    data = _normalize_g6_13_payload(payload)

    for seg_name, headers, keys, payload_key in _G6_13_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        ws.append([f"G6-13 预期信用损失计量测试 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16
        if not template_only:
            for row_data in data.get(payload_key) or []:
                if isinstance(row_data, dict):
                    ws.append(export_row_by_keys(row_data, keys))

    ws_conc = wb.create_sheet(title="审计结论")
    ws_conc.append(["G6-13 审计结论"])
    ws_conc["A1"].font = Font(bold=True, size=12)
    ws_conc.append(["结论"])
    if not template_only:
        ws_conc.append([data.get("conclusion") or ""])
    else:
        ws_conc.append([""])
    ws_conc.column_dimensions["A"].width = 80

    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G6-13 预期信用损失计量测试 编制说明"])
    ws_guide.append([])
    for line in (
        "本表含：方法评价 / 组合划分 / PD-LGD测算 / 损失率法 / 参数评价 / 审计结论。",
        "比率一律按小数录入（1%=0.01）。",
        "Stage1 的 PD 期限上限为12个月，由前端自动处理，无需在表中折算。",
        "跨表投资ID用于与 G6-12 减值测算表行关联；留空则按投资项目名称匹配。",
        "PD/LGD：ECL率≈期限折算PD×LGD；损失率法：ECL率≈损失率+前瞻性调整。",
        "测算结果可回写 G6-12「预期信用损失率②」；Stage3 已减值项目回写时默认跳过。",
        "评级→外部映射PD可参考前端「参考映射表」，实际项目须替换当期违约率数据版本。",
    ):
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 90
    return wb


def _parse_g6_13_sheet_rows(
    ws: Any,
    headers: list[str],
    keys: list[str],
) -> tuple[list[dict], list[dict]]:
    """从单个 worksheet 解析行（标题行1 + 表头行2）。"""
    errors: list[dict] = []
    rows: list[dict] = []
    header_row = None
    for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        values = list(row)
        if idx == 1:
            continue
        if idx == 2:
            header_row = [safe_str(v) for v in values[: len(headers)]]
            continue
        if not any(v is not None and str(v).strip() != "" for v in values):
            continue
        if len(rows) >= ROW_LIMIT:
            errors.append({
                "row_number": idx,
                "field": "",
                "reason": f"数据行超过{ROW_LIMIT}行限制，已截断",
            })
            break
        # 按标准 headers 位置解析；若表头不完全匹配仍按列序
        parsed = _parse_row_with_types(
            tuple(values),
            headers,
            keys,
            _G6_13_NUMERIC_KEYS,
        )
        if not parsed.get("id"):
            parsed["id"] = str(uuid4())
        rows.append(parsed)
    if header_row and header_row[:3] != headers[:3]:
        # 软提示，不阻断
        errors.append({
            "row_number": 2,
            "field": "",
            "reason": f"表头与模板不完全一致（期望以 {headers[:3]} 开头），已按列序解析",
        })
    return rows, errors


def _parse_g6_13_import(content: bytes) -> tuple[dict[str, Any], list[dict], int]:
    """解析 G6-13 多sheet 导入。返回 (payload, errors, imported_count)。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    payload = _empty_g6_13_payload()
    errors: list[dict] = []
    total = 0

    name_to_seg = {seg[0]: seg for seg in _G6_13_SEGMENTS}
    for ws_name in wb.sheetnames:
        if ws_name in ("编制说明",):
            continue
        if ws_name == "审计结论":
            ws = wb[ws_name]
            # 第3行 A 列为结论正文
            for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                if idx == 3:
                    payload["conclusion"] = safe_str(row[0] if row else "")
                    if payload["conclusion"]:
                        total += 1
                    break
            continue
        seg = name_to_seg.get(ws_name)
        if not seg:
            continue
        _, headers, keys, payload_key = seg
        rows, sheet_errors = _parse_g6_13_sheet_rows(wb[ws_name], headers, keys)
        errors.extend(sheet_errors)
        payload[payload_key] = rows
        total += len(rows)

    wb.close()
    return payload, errors, total


# ═══════════════════════════════════════════════════════════════════════════════
# G6-15 多sheet导出（3区段→3 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _export_g6_15_v2_row(row_data: dict) -> list[Any]:
    values: list[Any] = []
    for key in _G6_15_V2_KEYS:
        value = row_data.get(key)
        if key in _G6_15_V2_CHECK_KEYS:
            values.append(value if value in ("Y", "N", "NA") else "")
        elif key in _G6_15_V2_BOOL_KEYS:
            values.append("是" if value else "否")
        else:
            values.append(value if value is not None else "")
    return values


def _build_g6_15_multi_sheet_workbook(
    rows: list[dict],
    *,
    criteria: dict | None = None,
    template_only: bool = False,
) -> Workbook:
    """G6-15 v2：样本标准 + 本期发生额 + 期后处置新增。"""
    wb = Workbook()
    wb.remove(wb.active)

    ws_criteria = wb.create_sheet("样本标准")
    ws_criteria.append(["G6-15 样本选取标准与规模"])
    ws_criteria.merge_cells("A1:B1")
    ws_criteria["A1"].font = Font(bold=True, size=12)
    ws_criteria.append(_G6_15_CRITERIA_HEADERS)
    criteria = criteria or {}
    for label, key in _G6_15_CRITERIA_ROWS:
        ws_criteria.append([label, "" if template_only else criteria.get(key, "")])
    ws_criteria.column_dimensions["A"].width = 24
    ws_criteria.column_dimensions["B"].width = 70

    for period, sheet_name in (("occurrence", "本期发生额"), ("post", "期后处置新增")):
        ws = wb.create_sheet(title=sheet_name)
        ws.append([f"G6-15 凭证检查表 — {sheet_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(_G6_15_V2_HEADERS))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(_G6_15_V2_HEADERS)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(_G6_15_V2_HEADERS) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16
        if not template_only:
            for row_data in rows:
                row_period = row_data.get("period") or "occurrence"
                if row_period == period:
                    ws.append(_export_g6_15_v2_row(row_data))

    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G6-15 凭证检查表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "先填写样本标准：测试总体 → 特定项目全部测试 → 剩余总体实施抽样。",
        "本期发生额与期后处置、新增分别记录，期后凭证日期应晚于资产负债表日。",
        "六项核对填 Y/N/NA；留空表示尚未检查，N 表示检查不通过，NA 表示不适用。",
        "检查比例分别按本期借方、贷方抽查金额除以对应发生额计算，不要求抽样集合借贷相等。",
        "风险等级填：高 / 中 / 低。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g6_15_import(content: bytes) -> tuple[list[dict], list[dict], dict]:
    """解析G6-15导入文件。兼容 v2 分期间表与旧版三区段表。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[dict] = []
    rows_dict: dict[int, dict] = {}
    criteria: dict[str, Any] = {}

    # v2：样本标准 + 两张期间表
    if "本期发生额" in wb.sheetnames or "期后处置新增" in wb.sheetnames:
        if "样本标准" in wb.sheetnames:
            ws_criteria = wb["样本标准"]
            key_by_label = dict(_G6_15_CRITERIA_ROWS)
            numeric_criteria = {
                "populationDebitCount", "populationDebitAmount",
                "populationCreditCount", "populationCreditAmount",
                "specificSampleCount", "specificSampleAmount",
                "samplingPopulationCount", "samplingPopulationAmount",
                "sampleSize", "bookDebitOccurrence", "bookCreditOccurrence",
            }
            for row in ws_criteria.iter_rows(min_row=3, values_only=True):
                label = safe_str(row[0] if row else "")
                key = key_by_label.get(label)
                if not key:
                    continue
                raw = row[1] if len(row) > 1 else None
                criteria[key] = safe_float(raw) if key in numeric_criteria else safe_str(raw)

        result: list[dict] = []
        for sheet_name, period in (("本期发生额", "occurrence"), ("期后处置新增", "post")):
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            header_cells = list(ws.iter_rows(min_row=2, max_row=2, values_only=True))
            actual_headers = [safe_str(v) for v in (header_cells[0] if header_cells else [])]
            missing = [h for h in ("日期", "凭证编号") if h not in actual_headers]
            if missing:
                errors.append({"row_number": 2, "field": sheet_name, "reason": f"缺少列: {', '.join(missing)}"})
                continue
            for row_number, raw_row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
                if all(v is None for v in raw_row):
                    continue
                if len(result) >= ROW_LIMIT:
                    errors.append({"row_number": row_number, "field": sheet_name, "reason": f"数据行超过{ROW_LIMIT}行限制，已截断"})
                    break
                parsed: dict[str, Any] = {"id": str(uuid4()), "period": period}
                values = list(raw_row)
                for header, key in zip(_G6_15_V2_HEADERS, _G6_15_V2_KEYS):
                    if header not in actual_headers:
                        continue
                    raw = values[actual_headers.index(header)] if actual_headers.index(header) < len(values) else None
                    if key in _G6_15_V2_NUMERIC_KEYS:
                        parsed[key] = safe_float(raw)
                    elif key in _G6_15_V2_BOOL_KEYS:
                        parsed[key] = _parse_bool(raw)
                    elif key in _G6_15_V2_CHECK_KEYS:
                        raw_check = safe_str(raw).strip()
                        value = raw_check.upper().replace("N/A", "NA")
                        if raw_check and value not in ("Y", "N", "NA", ""):
                            errors.append({
                                "row_number": row_number,
                                "field": key,
                                "reason": f"核对值'{raw_check}'无效，应为 Y/N/NA 或空",
                            })
                            parsed[key] = ""
                        else:
                            parsed[key] = value if value in ("Y", "N", "NA") else ""
                    else:
                        parsed[key] = safe_str(raw)
                result.append(parsed)
        wb.close()
        return result, errors, criteria

    # 策略1: 多sheet
    multi_sheet = len(wb.sheetnames) >= 3 and any("凭证基础" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G6_15_SEGMENTS:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append({"row_number": 0, "field": seg_name, "reason": f"缺少工作表: {seg_name}"})
                continue
            header_row_idx = 2
            actual_headers = [
                str(c.value).strip() if c.value else ""
                for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
            ]
            missing = [h for h in seg_headers if h not in actual_headers]
            if missing:
                errors.append({"row_number": 0, "field": seg_name, "reason": f"缺少列: {', '.join(missing)}"})
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                if row_idx not in rows_dict:
                    rows_dict[row_idx] = {"id": str(uuid4())}
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                for col_i, key in enumerate(seg_keys):
                    if key == "id":
                        continue
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_15_NUMERIC_KEYS:
                        rows_dict[row_idx][key] = safe_float(raw)
                    elif key in _G6_15_BOOL_KEYS:
                        rows_dict[row_idx][key] = _parse_bool(raw)
                    else:
                        rows_dict[row_idx][key] = safe_str(raw)
    else:
        # 策略2: 单sheet宽表
        ws = wb.active
        if ws is None:
            wb.close()
            return [], [{"row_number": 0, "field": "", "reason": "xlsx文件中无活动工作表"}], criteria
        header_row_idx = 1
        for r in range(1, min(5, (ws.max_row or 1) + 1)):
            row_cells = list(ws.iter_rows(min_row=r, max_row=r))
            if not row_cells:
                continue
            test_row = [str(c.value).strip() if c.value else "" for c in row_cells[0]]
            if "凭证号" in test_row or "日期" in test_row:
                header_row_idx = r
                break
        header_cells = list(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        if not header_cells:
            errors.append({"row_number": 0, "field": "", "reason": "xlsx文件中无有效表头行"})
            wb.close()
            return [], errors, criteria
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in header_cells[0]
        ]
        if "凭证号" not in actual_headers and "日期" not in actual_headers:
            errors.append({"row_number": header_row_idx, "field": "", "reason": "无法识别表头，缺少'凭证号'或'日期'列"})
            wb.close()
            return [], errors, criteria
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append({"row_number": row_idx + header_row_idx + 1, "field": "", "reason": f"数据行超过{ROW_LIMIT}行限制，已截断"})
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in _G6_15_ALL_HEADERS:
                    key_idx = _G6_15_ALL_HEADERS.index(h)
                    key = _G6_15_ALL_KEYS[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if key in _G6_15_NUMERIC_KEYS:
                        parsed[key] = safe_float(raw)
                    elif key in _G6_15_BOOL_KEYS:
                        parsed[key] = _parse_bool(raw)
                    else:
                        parsed[key] = safe_str(raw)
            rows_dict[row_idx] = parsed

    wb.close()
    result = list(rows_dict.values())
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append({"row_number": ROW_LIMIT, "field": "", "reason": f"数据行超过{ROW_LIMIT}行限制，已截断"})
    # 旧版数据全部归入本期。
    # 旧 boolean false 同时表示「未检查」与「不通过」：仅当整行已标异常时转为 N，否则转为空。
    for row in result:
        row["period"] = "occurrence"
        explicitly_abnormal = _parse_bool(row.get("isAbnormal"))
        for old_key, new_key in (
            ("checkOriginal", "checkOriginal"),
            ("checkAuthorized", "checkAuthorized"),
            ("checkAccounting", "checkAccounting"),
            ("checkAmount", "checkInitialCost"),
            ("checkInterest", "checkInterest"),
            ("checkClassification", "checkFairValue"),
            ("checkImpairment", "checkFairValue"),
        ):
            if old_key not in row and new_key not in row:
                continue
            raw = row.get(old_key, row.get(new_key))
            if raw is True or raw in ("Y", "是", "✓"):
                row[new_key] = "Y"
            elif raw is False:
                row[new_key] = "N" if explicitly_abnormal else ""
            elif raw in ("N", "否", "✗"):
                row[new_key] = "N"
            elif raw in ("NA", "N/A", "不适用"):
                row[new_key] = "NA"
            else:
                row[new_key] = ""
    return result, errors, criteria


def _normalize_g6_11_export_row(row: dict) -> dict:
    """展开 sectionConclusions，供导出列使用."""
    conclusions = row.get("sectionConclusions") or {}
    if not isinstance(conclusions, dict):
        conclusions = {}
    out = dict(row)
    out.setdefault("sicrConclusion", conclusions.get("significantIncrease", ""))
    out.setdefault("lowRiskConclusion", conclusions.get("lowCreditRisk", ""))
    out.setdefault("impairmentConclusion", conclusions.get("creditImpairment", ""))
    return out


def _hydrate_g6_11_import_row(parsed: dict) -> dict:
    """导入行补全前端 StageClassificationRow 兼容字段."""
    row = dict(parsed)
    row["sectionConclusions"] = {
        "significantIncrease": safe_str(row.pop("sicrConclusion", "")),
        "lowCreditRisk": safe_str(row.pop("lowRiskConclusion", "")),
        "creditImpairment": safe_str(row.pop("impairmentConclusion", "")),
    }
    # 一致性与三项综合判定由前端按检查项重算；Excel 汇总列仅作参考
    row.pop("isConsistent", None)
    row.pop("hasSignificantIncrease", None)
    row.pop("hasLowCreditRisk", None)
    row.pop("hasCreditImpairment", None)
    # 保留 Excel 填写的审计阶段，避免空检查项把阶段冲回 Stage1
    if row.get("auditStage"):
        row["auditStageManualOverride"] = True
    cid = safe_str(row.get("crossSheetInvestmentId"))
    if cid:
        row["crossSheetInvestmentId"] = cid
        row["id"] = cid
    elif not row.get("id"):
        row["id"] = str(uuid4())
    return row


async def _upsert_dual_rows(db: AsyncSession, wp_id: str, item_id: str, rows: list[dict]) -> None:
    await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
    await upsert_json_rows(db, wp_id, item_id, rows, field="remark")


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g6-ecl/export-template")
async def g6_ecl_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空模板（含表头+编制说明）."""
    _validate_sheet(sheet)

    if sheet == "G6-11":
        wb = build_workbook_template(
            "G6-11",
            _G6_11_HEADERS,
            title="G6-11 其他债权投资三阶段划分",
            guidance=[
                "G6-11 三阶段划分 编制说明",
                "",
                "每行一个投资项目，填写三阶段判定相关信息。",
                "企业划分阶段和审计判断阶段填：Stage1 / Stage2 / Stage3。",
                "显著增加/低风险/已减值/一致性 填：是/否。",
                "判定优先级：已减值(Stage3) > SICR且非低风险豁免(Stage2) > 其余(Stage1)。",
                "不一致时差异说明为必填项。",
                "跨表投资ID 用于跨表稳定匹配，可留空；建议从 G6-2/G6-12 带入后保留。",
                "完整逐项检查明细请在前端底稿中填写；本表用于汇总导入导出。",
            ],
        )
        return workbook_to_response(wb, "G6-11_三阶段划分_模板.xlsx")
    if sheet == "G6-12":
        wb = _build_g6_12_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G6-12_减值准备测算表_模板.xlsx")
    elif sheet == "G6-13":
        wb = _build_g6_13_multi_sheet_workbook(_empty_g6_13_payload(), template_only=True)
        return workbook_to_response(wb, "G6-13_预期信用损失计量测试_模板.xlsx")
    elif sheet == "G6-14":
        wb = _build_g6_14_multi_sheet_workbook([], [], template_only=True)
        return workbook_to_response(wb, "G6-14_转回核销检查表_模板.xlsx")
    else:  # G6-15
        wb = _build_g6_15_multi_sheet_workbook([], criteria={}, template_only=True)
        return workbook_to_response(wb, "G6-15_凭证检查表_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g6-ecl/export-data")
async def g6_ecl_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出已填写数据."""
    _validate_sheet(sheet)

    if sheet == "G6-11":
        item_id = _ITEM_IDS["G6-11"]
        rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
        if not rows:
            rows = await load_json_rows(db, wp_id, item_id, field="remark")
        wb = build_workbook_template(
            "G6-11",
            _G6_11_HEADERS,
            title="G6-11 其他债权投资三阶段划分",
            guidance=["每行一个投资项目。Stage填Stage1/Stage2/Stage3。"],
        )
        ws = wb["G6-11"]
        for d in rows:
            ws.append(
                _export_row_with_types(
                    _normalize_g6_11_export_row(d),
                    _G6_11_KEYS,
                    bool_keys=_G6_11_BOOL_KEYS,
                )
            )
        return workbook_to_response(wb, "G6-11_三阶段划分_数据.xlsx")

    if sheet == "G6-12":
        item_id = _ITEM_IDS["G6-12"]
        rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
        if not rows:
            rows = await load_json_rows(db, wp_id, item_id, field="remark")
        if not rows:
            # 前端权威键 G6-12-impairment-calc-data：{ rows, conclusion }
            payload = await load_json_payload(db, wp_id, "G6-12-impairment-calc-data", field="conclusion")
            if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
                rows = payload["rows"]
            elif isinstance(payload, list):
                rows = payload
        wb = _build_g6_12_multi_sheet_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G6-12_减值准备测算表_数据.xlsx")

    elif sheet == "G6-13":
        raw_payload = await load_json_payload(db, wp_id, _G6_13_ITEM_ID, field="conclusion")
        if raw_payload is None:
            raw_payload = await load_json_payload(db, wp_id, _G6_13_ITEM_ID, field="remark")
        wb = _build_g6_13_multi_sheet_workbook(_normalize_g6_13_payload(raw_payload), template_only=False)
        return workbook_to_response(wb, "G6-13_预期信用损失计量测试_数据.xlsx")

    elif sheet == "G6-14":
        raw_payload: Any = None
        for field in ("conclusion", "remark"):
            raw_payload = await load_json_payload(
                db,
                wp_id,
                _G6_14_PRIMARY_ITEM_ID,
                field=field,
            )
            if raw_payload is not None:
                break
        if raw_payload is None:
            for field in ("conclusion", "remark"):
                raw_payload = await load_json_payload(
                    db,
                    wp_id,
                    _ITEM_IDS["G6-14"],
                    field=field,
                )
                if raw_payload is not None:
                    break

        reversals: list[dict] = []
        writeoffs: list[dict] = []
        if isinstance(raw_payload, dict):
            raw_reversals = raw_payload.get("reversals")
            raw_writeoffs = raw_payload.get("writeOffs")
            reversals = raw_reversals if isinstance(raw_reversals, list) else []
            writeoffs = raw_writeoffs if isinstance(raw_writeoffs, list) else []
        elif isinstance(raw_payload, list):
            for raw_row in raw_payload:
                if not isinstance(raw_row, dict):
                    continue
                target, converted = _legacy_g6_14_row(raw_row)
                (writeoffs if target == "writeOffs" else reversals).append(converted)

        wb = _build_g6_14_multi_sheet_workbook(
            reversals,
            writeoffs,
            template_only=False,
        )
        return workbook_to_response(wb, "G6-14_转回核销检查表_数据.xlsx")

    else:  # G6-15
        item_id = _ITEM_IDS["G6-15"]
        rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
        criteria = await load_json_payload(db, wp_id, "G6-15-criteria", field="conclusion")
        wb = _build_g6_15_multi_sheet_workbook(
            rows,
            criteria=criteria if isinstance(criteria, dict) else {},
            template_only=False,
        )
        return workbook_to_response(wb, "G6-15_凭证检查表_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g6-ecl/import-data")
async def g6_ecl_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx数据."""
    _validate_sheet(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    if sheet == "G6-11":
        try:
            # 跨表投资ID 为新增可选列：旧模板无此列仍可导入
            actual, raw = parse_upload_xlsx(
                content,
                _G6_11_REQUIRED_HEADERS,
                header_row=2,
                require_all_headers=True,
            )
        except ValueError as e:
            return {"ok": False, "errors": [{"row_number": 0, "field": "", "reason": str(e)}], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        rows: list[dict] = []
        errors: list[dict] = []
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append({"row_number": i + 2, "field": "", "reason": f"数据行超过{ROW_LIMIT}行限制，已截断"})
                break
            ordered = []
            for header in _G6_11_HEADERS:
                if header not in actual:
                    ordered.append(None)
                    continue
                col_idx = actual.index(header)
                ordered.append(r[col_idx] if col_idx < len(r) else None)
            parsed = _parse_row_with_types(
                tuple(ordered),
                _G6_11_HEADERS,
                _G6_11_KEYS,
                _G6_11_NUMERIC_KEYS,
                _G6_11_BOOL_KEYS,
            )
            for stage_field in ("companyStage", "auditStage"):
                val = parsed.get(stage_field, "")
                if val and val not in ("Stage1", "Stage2", "Stage3", ""):
                    errors.append({
                        "row_number": i + 2,
                        "field": stage_field,
                        "reason": f"阶段值'{val}'无效，应为Stage1/Stage2/Stage3",
                    })
            rows.append(_hydrate_g6_11_import_row(parsed))
        if errors and not rows:
            return {"ok": False, "errors": errors, "imported_count": 0}
        await _upsert_dual_rows(db, wp_id, _ITEM_IDS["G6-11"], rows)
        return {"ok": True, "imported_count": len(rows), "errors": errors}

    if sheet == "G6-12":
        rows, errors = _parse_g6_12_import(content)
        if errors and not rows:
            return {"ok": False, "errors": errors, "imported_count": 0}
        item_id = _ITEM_IDS["G6-12"]
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
        await upsert_json_rows(db, wp_id, item_id, rows, field="remark")
        # 同步前端权威键，避免旧 G6-12-impairment-calc-data 遮蔽导入结果
        await upsert_json_payload(
            db,
            wp_id,
            "G6-12-impairment-calc-data",
            {"rows": rows, "conclusion": ""},
            field="conclusion",
        )
        out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
        if len(rows) >= ROW_LIMIT:
            out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
        return out

    elif sheet == "G6-13":
        payload, errors, imported_count = _parse_g6_13_import(content)
        if errors and imported_count == 0:
            return {"ok": False, "errors": errors, "imported_count": 0}
        await upsert_json_payload(db, wp_id, _G6_13_ITEM_ID, payload, field="conclusion")
        await upsert_json_payload(db, wp_id, _G6_13_ITEM_ID, payload, field="remark")
        return {"ok": True, "imported_count": imported_count, "errors": errors}

    elif sheet == "G6-14":
        try:
            reversals, writeoffs, errors = _parse_g6_14_import(content)
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        if errors and not reversals and not writeoffs:
            return {"ok": False, "errors": errors, "imported_count": 0}
        payload = {
            "schemaVersion": 2,
            "reversals": reversals,
            "writeOffs": writeoffs,
            "conclusion": "",
        }
        for item_id in (_G6_14_PRIMARY_ITEM_ID, _ITEM_IDS["G6-14"]):
            await upsert_json_payload(
                db,
                wp_id,
                item_id,
                payload,
                field="conclusion",
            )
            await upsert_json_payload(
                db,
                wp_id,
                item_id,
                payload,
                field="remark",
            )
        return {
            "ok": True,
            "imported_count": len(reversals) + len(writeoffs),
            "errors": errors,
        }

    else:  # G6-15
        rows, errors, criteria = _parse_g6_15_import(content)
        if errors and not rows:
            return {"ok": False, "errors": errors, "imported_count": 0}
        item_id = _ITEM_IDS["G6-15"]
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
        await upsert_json_rows(db, wp_id, item_id, rows, field="remark")
        if criteria:
            await upsert_json_payload(db, wp_id, "G6-15-criteria", criteria, field="conclusion")
            await upsert_json_payload(db, wp_id, "G6-15-criteria", criteria, field="remark")
        out = {"ok": True, "imported_count": len(rows), "errors": errors}
        if len(rows) >= ROW_LIMIT:
            out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
        return out
