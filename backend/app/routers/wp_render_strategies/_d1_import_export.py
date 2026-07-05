"""D1 应收票据 — 导入导出三级端点

3个端点（通用）：
- POST /api/workpapers/{wp_id}/d1/export-template?sheet={sheet_code}  空白模板xlsx
- POST /api/workpapers/{wp_id}/d1/export-data?sheet={sheet_code}      数据xlsx
- POST /api/workpapers/{wp_id}/d1/import-data?sheet={sheet_code}      解析xlsx写入

3个端点（D1-ECL专用，hardcoded sheet=D1-15）：
- POST /api/workpapers/{wp_id}/d1-ecl/export-template  空白ECL模板xlsx
- POST /api/workpapers/{wp_id}/d1-ecl/export-data      ECL数据xlsx
- POST /api/workpapers/{wp_id}/d1-ecl/import-data      解析ECL xlsx写入

支持sheets: D1-2, D1-3, D1-4, D1-6, D1-7, D1-8, D1-8T, D1-9, D1-10, D1-11, D1-12, D1-13, D1-15
D1-15特殊：双section格式（按组合计提 + 按单项计提），D列(应计提)和F列(差异)为计算列
D1-7特殊：备查簿存储为dict {bankRows, commercialRows}（31列宽表），导出时拼接两组行，
        导入时按"票据类型"列拆分回 bank/commercial 两组，写回 D1-memo-rows
D1-8特殊：贴现背书双表——'D1-8'→D1-endorse-discount-rows（已贴现），
        'D1-8T'→D1-endorse-transfer-rows（已背书），两者共用同一套16列表头与转换函数
D1-9特殊：贴息表含派生列（贴息天数/应计贴现利息/差异），导出时计算供参考，导入时忽略
D1-6特殊：仅处理业务模式依据表（D1-bm-basis-rows）；QA矩阵不适合表格导入导出，跳过
D1-13特殊：多section格式（抽样总体标量 + 特定样本 + 凭证核对 + 测试结论），
        写入 D1-sampling-population-* / D1-sampling-specific-samples /
        D1-sampling-vouching-rows / D1-sampling-tolerable-rate 等 checklist keys
D1-16特殊：双section格式（转回检查 + 核销检查）
格式校验：列名不匹配时返回 400 + 错误列名列表
行数限制：超500行截断 + 返回警告摘要

Requirements: 9.1-9.6, 13.1-13.7, 14.1-14.6
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

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["d1-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

_SUPPORTED_SHEETS: set[str] = {
    "D1-1", "D1-2", "D1-3", "D1-4", "D1-6", "D1-7", "D1-8", "D1-8T", "D1-9",
    "D1-10", "D1-11", "D1-12", "D1-13", "D1-14", "D1-15", "D1-5", "D1-16",
}

_D1_1_ROWS: list[tuple[str, str]] = [
    ("gross-bank", "原值-银行承兑汇票"),
    ("gross-commercial", "原值-商业承兑汇票"),
    ("bd-bank", "坏账准备-银行承兑汇票"),
    ("bd-commercial", "坏账准备-商业承兑汇票"),
    ("tb", "试算平衡表数"),
]
_D1_1_FIELDS: list[tuple[str, str, bool]] = [
    ("prior-unadj", "期初未审", False),
    ("prior-aje", "期初AJE", False),
    ("prior-rje", "期初RJE", False),
    ("current-unadj", "期末未审", False),
    ("current-aje", "期末AJE", False),
    ("current-rje", "期末RJE", False),
    ("reason", "原因分析", True),
]

_D1_14_ROWS: list[tuple[str, str]] = [
    ("D1-policy-overview-left", "政策概述-公司政策描述"),
    ("D1-policy-overview-right", "政策概述-审计师核查意见"),
    ("D1-policy-ecl-portfolio", "ECL模型-组合评估方法"),
    ("D1-policy-ecl-individual", "ECL模型-单项评估标准"),
    ("D1-policy-ecl-migration", "ECL模型-迁徙率法参数"),
    ("D1-policy-ecl-right", "ECL模型-审计师核查意见"),
    ("D1-policy-change-flag", "政策变更-是否变更"),
    ("D1-policy-change-content", "政策变更-变更内容"),
    ("D1-policy-change-reason", "政策变更-变更原因"),
    ("D1-policy-conclusion", "审计结论"),
]
_D1_14_CONCLUSION_ONLY: set[str] = {
    "D1-policy-change-flag",
}
_D1_14_CONCLUSION_AND_REMARK: set[str] = {
    "D1-policy-conclusion",
}

# D1-7 备查簿 31列表头（顺序对齐前端表格列）
_D1_7_HEADERS: list[str] = [
    "票据类型", "票据号", "收到日期", "前手", "出票日", "出票人", "承兑人", "金额",
    "到期日", "流转日", "状态", "被背书人", "贴现银行", "贴现息",
    "是否质押", "审计日已贴现背书", "年初余额", "本期收到", "本期背书",
    "本期到期承兑", "本期贴现", "年末余额", "期末未到期背书贴现",
    "是否终止确认", "信用评级", "审定应收款项融资", "审定应收票据",
    "关联关系", "是否逾期", "逾期转应收金额", "备注",
]

# D1-8 贴现背书 16列表头（贴现表与背书表共用）
_D1_8_HEADERS: list[str] = [
    "票据种类", "收到日期", "出票人", "票据号", "汇票金额", "已计利息",
    "出票日", "到期日", "承兑银行", "信用等级", "贴现银行", "贴现金额",
    "贴现息", "是否终止确认", "会计处理是否正确", "索引号",
]

# D1-9 贴息 13列表头（含派生列，导入时忽略派生列）
_D1_9_HEADERS: list[str] = [
    "票据类型", "票面金额", "票面利率", "出票日期", "到期日", "到期日票据价值",
    "贴现日期", "贴息天数", "贴现率", "应计贴现利息", "账面贴现利息", "差异", "备注",
]

# D1-6 业务模式依据表 5列表头（仅依据表，QA矩阵跳过）
_D1_6_HEADERS: list[str] = [
    "组合名称", "业务模式", "具体依据", "索引号", "备注",
]

_SHEET_HEADERS: dict[str, list[str]] = {
    "D1-1": [
        "行键", "项目",
        "期初未审", "期初AJE", "期初RJE",
        "期末未审", "期末AJE", "期末RJE",
        "原因分析",
    ],
    "D1-2": [
        "票据种类", "期初未审", "期初AJE", "期初RJE",
        "本期增加", "本期减少", "期末AJE", "期末RJE",
    ],
    "D1-3": [
        "客户名称", "公司代码", "关联关系",
        "期初未审", "期初AJE", "期初RJE",
        "本期增加", "本期减少", "期末余额", "重分类",
        "期末AJE", "期末RJE",
    ],
    "D1-4": [
        "项目", "期初未审", "期初AJE", "期初RJE",
        "本期计提", "本期收回", "本期转回", "本期核销", "本期其他",
        "期末AJE", "期末RJE",
    ],
    "D1-6": _D1_6_HEADERS,
    "D1-7": _D1_7_HEADERS,
    "D1-8": _D1_8_HEADERS,
    "D1-8T": _D1_8_HEADERS,
    "D1-9": _D1_9_HEADERS,
    "D1-10": [
        "票据类型", "票据号", "出票日", "出票人", "承兑人", "金额",
        "到期日", "前手", "收到日期", "背书/贴现日", "被背书人/贴现行",
        "票据状态", "是否存在差异", "差异原因", "索引号",
    ],
    "D1-11": [
        "关联方名称", "关联关系", "期初余额", "借方发生", "贷方发生", "期末余额",
        "减：坏账准备", "账面价值", "发生时间及账龄", "发生原因（款项性质）",
        "期后已兑现或已贴现", "索引号", "备注",
    ],
    "D1-12": [
        "票据类型", "票据号码", "收到票据日期", "票据前手名称", "出票日期",
        "出票人名称", "承兑人名称", "票据金额", "票据到期日", "质押金额",
        "质权人", "质押原因", "质押条件", "质押期限", "质押协议", "索引号",
    ],
    "D1-13": [
        "序号", "票据类型", "票据号码", "出票人", "承兑人", "金额", "到期日",
        "存在性验证", "准确性验证", "记录恰当性", "备注", "索引号",
    ],
    "D1-14": [
        "item_id", "项目", "结论", "内容",
    ],
    "D1-5": [
        "序号", "类别", "借方科目", "贷方科目", "金额", "说明",
    ],
    "D1-15": [
        "债务人名称", "审定余额", "预期信用损失率", "应计提",
        "账面余额", "差异", "计提依据", "索引号",
    ],
}

# checklist_responses item_id 映射
# D1-7 存储为 dict {bankRows, commercialRows}，走特殊路径（见 _export_d1_15_data 模式）
_SHEET_ITEM_ID: dict[str, str | list[str]] = {
    "D1-2": "D1-cat-rows",
    "D1-3": "D1-cust-rows",
    "D1-4": ["D1-bd-individual-rows", "D1-bd-portfolio-rows"],
    "D1-6": "D1-bm-basis-rows",
    "D1-7": "D1-memo-rows",
    "D1-8": "D1-endorse-discount-rows",
    "D1-8T": "D1-endorse-transfer-rows",
    "D1-9": "D1-interest-rows",
    "D1-10": "D1-inventory-rows",
    "D1-11": "D1-rp-rows",
    "D1-12": "D1-pledge-rows",
    "D1-13": "D1-sampling-vouching-rows",
    "D1-15": ["D1-ecl-portfolio-rows", "D1-ecl-individual-rows"],
}

_D1_13_SECTION_POPULATION = "--- 抽样总体 ---"
_D1_13_SECTION_SPECIFIC = "--- 特定样本 ---"
_D1_13_SECTION_VOUCHING = "--- 凭证核对 ---"
_D1_13_SECTION_CONCLUSION = "--- 测试结论 ---"
_D1_13_POPULATION_HEADERS: list[str] = [
    "总体描述", "总体笔数", "总体金额", "样本量", "实际抽取", "抽样索引",
]
_D1_13_SPECIFIC_HEADERS: list[str] = [
    "序号", "票据类型", "票据号码", "金额", "选取原因", "索引号",
]
_D1_13_CONCLUSION_HEADERS: list[str] = [
    "可容忍误差率", "测试结论", "审计说明", "审计结论",
]

_D1_16_SECTION_REVERSAL = "--- 转回检查 ---"
_D1_16_SECTION_WRITEOFF = "--- 核销检查 ---"
_D1_16_REVERSAL_HEADERS: list[str] = [
    "单位名称", "转回原因", "收回方式", "原确定坏账准备的依据",
    "收回或转回金额", "收回或转回前累计已计提坏账准备金额", "合理性分析", "索引号",
]
_D1_16_WRITEOFF_HEADERS: list[str] = [
    "单位名称", "应收票据的性质", "核销金额", "核销原因", "履行的核销程序",
]


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _validate_sheet(sheet_code: str) -> None:
    if sheet_code not in _SUPPORTED_SHEETS:
        raise HTTPException(
            400,
            f"不支持的sheet: {sheet_code}。支持: {sorted(_SUPPORTED_SHEETS)}",
        )


def _safe_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _col_val(row: tuple, actual_headers: list[str], col_name: str) -> Any:
    """从行数据中按列名取值"""
    try:
        idx = actual_headers.index(col_name)
        return row[idx] if idx < len(row) else None
    except (ValueError, IndexError):
        return None


def _create_template_wb(sheet_code: str) -> Workbook:
    """创建空白模板xlsx（含表头+格式，无数据行）"""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_code

    if sheet_code == "D1-16":
        section_font = Font(bold=True, size=11, color="333333")
        section_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
        header_font = Font(bold=True, size=11)
        header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        r = 1
        cell = ws.cell(row=r, column=1, value=_D1_16_SECTION_REVERSAL)
        cell.font = section_font
        cell.fill = section_fill
        r = 2
        for col_idx, name in enumerate(_D1_16_REVERSAL_HEADERS, 1):
            cell = ws.cell(row=r, column=col_idx, value=name)
            cell.font = header_font
            cell.fill = header_fill
        r = 4
        cell = ws.cell(row=r, column=1, value=_D1_16_SECTION_WRITEOFF)
        cell.font = section_font
        cell.fill = section_fill
        r = 5
        for col_idx, name in enumerate(_D1_16_WRITEOFF_HEADERS, 1):
            cell = ws.cell(row=r, column=col_idx, value=name)
            cell.font = header_font
            cell.fill = header_fill
        ws.freeze_panes = "A2"
        return wb

    if sheet_code == "D1-13":
        section_font = Font(bold=True, size=11, color="333333")
        section_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
        header_font = Font(bold=True, size=11)
        header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

        def write_section(title: str, headers: list[str], start_row: int) -> int:
            cell = ws.cell(row=start_row, column=1, value=title)
            cell.font = section_font
            cell.fill = section_fill
            hr = start_row + 1
            for col_idx, name in enumerate(headers, 1):
                cell = ws.cell(row=hr, column=col_idx, value=name)
                cell.font = header_font
                cell.fill = header_fill
            return hr + 1

        r = 1
        r = write_section(_D1_13_SECTION_POPULATION, _D1_13_POPULATION_HEADERS, r)
        r += 1
        r = write_section(_D1_13_SECTION_SPECIFIC, _D1_13_SPECIFIC_HEADERS, r)
        r = write_section(_D1_13_SECTION_VOUCHING, _SHEET_HEADERS["D1-13"], r)
        write_section(_D1_13_SECTION_CONCLUSION, _D1_13_CONCLUSION_HEADERS, r)
        ws.freeze_panes = "A2"
        return wb

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

    # D1-15 特殊处理：添加双section分隔行
    if sheet_code == "D1-1":
        for row_key, label in _D1_1_ROWS:
            ws.append([row_key, label, *[None] * (len(headers) - 2)])

    if sheet_code == "D1-14":
        for item_id, label in _D1_14_ROWS:
            ws.append([item_id, label, None, None])

    # D1-15 特殊处理：添加双section分隔行
    if sheet_code == "D1-15":
        section_font = Font(bold=True, size=11, color="333333")
        section_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
        section_align = Alignment(horizontal="center", vertical="center")

        # Row 2: 按组合计提 section header
        cell = ws.cell(row=2, column=1, value="--- 按组合计提 ---")
        cell.font = section_font
        cell.fill = section_fill
        cell.alignment = section_align

        # Rows 3-7: 5 empty placeholder rows for portfolio
        for r in range(3, 8):
            for c in range(1, len(headers) + 1):
                ws.cell(row=r, column=c, value=None)

        # Row 8: 按单项计提 section header
        cell = ws.cell(row=8, column=1, value="--- 按单项计提 ---")
        cell.font = section_font
        cell.fill = section_fill
        cell.alignment = section_align

        # Rows 9-11: 3 empty placeholder rows for individual
        for r in range(9, 12):
            for c in range(1, len(headers) + 1):
                ws.cell(row=r, column=c, value=None)

    ws.freeze_panes = "A2"
    return wb


def _validate_columns(ws: Any, sheet_code: str) -> list[str]:
    """校验列头，返回不匹配的列名列表"""
    expected = set(_SHEET_HEADERS[sheet_code])
    actual: list[str] = []
    for cell in next(ws.iter_rows(min_row=1, max_row=1)):
        if cell.value is not None:
            actual.append(str(cell.value).strip())

    # D1-15 额外校验列数必须为8
    if sheet_code == "D1-15" and len(actual) != 8:
        return [f"列数应为8，实际为{len(actual)}"]

    missing = [h for h in expected if h not in actual]
    return missing


# ═══════════════════════════════════════════════════════════════════════════════
# 导出行转换
# ═══════════════════════════════════════════════════════════════════════════════


def _export_d1_2_row(data: dict) -> list:
    return [
        _safe_str(data.get("category", "")),
        _safe_float(data.get("priorUnadjusted")),
        _safe_float(data.get("priorAje")),
        _safe_float(data.get("priorRje")),
        _safe_float(data.get("currentIncrease")),
        _safe_float(data.get("currentDecrease")),
        _safe_float(data.get("currentAje")),
        _safe_float(data.get("currentRje")),
    ]


def _export_d1_3_row(data: dict) -> list:
    return [
        _safe_str(data.get("customerName", "")),
        _safe_str(data.get("companyCode", "")),
        _safe_str(data.get("relationType", "")),
        _safe_float(data.get("priorUnadjusted")),
        _safe_float(data.get("priorAje")),
        _safe_float(data.get("priorRje")),
        _safe_float(data.get("currentIncrease")),
        _safe_float(data.get("currentDecrease")),
        _safe_float(data.get("currentBalance")),
        _safe_float(data.get("reclassification")),
        _safe_float(data.get("currentAje")),
        _safe_float(data.get("currentRje")),
    ]


def _export_d1_4_row(data: dict) -> list:
    return [
        _safe_str(data.get("label", "")),
        _safe_float(data.get("priorUnadjusted")),
        _safe_float(data.get("priorAje")),
        _safe_float(data.get("priorRje")),
        _safe_float(data.get("currentProvision")),
        _safe_float(data.get("currentRecovery")),
        _safe_float(data.get("currentReversal")),
        _safe_float(data.get("currentWriteOff")),
        _safe_float(data.get("currentOther")),
        _safe_float(data.get("currentAje")),
        _safe_float(data.get("currentRje")),
    ]


def _note_type_is_bank(note_type: str) -> bool:
    """判定票据类型是否为银行承兑（用于D1-7 bank/commercial拆分）"""
    return "银行" in (note_type or "")


def _export_d1_6_row(data: dict) -> list:
    """D1-6 业务模式依据表行导出（仅依据表，不含QA矩阵）"""
    return [
        _safe_str(data.get("combinationName", "")),
        _safe_str(data.get("businessMode", "")),
        _safe_str(data.get("basis", "")),
        _safe_str(data.get("indexRef", "")),
        _safe_str(data.get("remark", "")),
    ]


def _export_d1_7_row(data: dict) -> list:
    """D1-7 备查簿行导出（31列 MemoRow）"""
    return [
        _safe_str(data.get("noteType", "")),
        _safe_str(data.get("noteNumber", "")),
        _safe_str(data.get("receivedDate", "")),
        _safe_str(data.get("endorser", "")),
        _safe_str(data.get("issueDate", "")),
        _safe_str(data.get("issuer", "")),
        _safe_str(data.get("acceptor", "")),
        _safe_float(data.get("amount")),
        _safe_str(data.get("maturityDate", "")),
        _safe_str(data.get("transferDate", "")),
        _safe_str(data.get("status", "")),
        _safe_str(data.get("endorsee", "")),
        _safe_str(data.get("discountBank", "")),
        _safe_float(data.get("discountInterest")),
        _safe_str(data.get("isPledged", "")),
        _safe_str(data.get("isDiscountedEndorsed", "")),
        _safe_float(data.get("beginningBalance")),
        _safe_float(data.get("currentReceived")),
        _safe_float(data.get("currentEndorsed")),
        _safe_float(data.get("currentMatured")),
        _safe_float(data.get("currentDiscounted")),
        _safe_float(data.get("endingBalance")),
        _safe_float(data.get("unexpiredEndorsedDiscounted")),
        _safe_str(data.get("isDerecognized", "")),
        _safe_str(data.get("creditRating", "")),
        _safe_float(data.get("auditedFinancing")),
        _safe_float(data.get("auditedNotes")),
        _safe_str(data.get("relatedParty", "")),
        _safe_str(data.get("isOverdue", "")),
        _safe_float(data.get("overdueTransferAmount")),
        _safe_str(data.get("remarkText", "")),
    ]


def _export_d1_8_row(data: dict) -> list:
    """D1-8 贴现/背书检查表行导出（16列 EndorsementRow，贴现表与背书表共用）"""
    return [
        _safe_str(data.get("noteType", "")),
        _safe_str(data.get("receivedDate", "")),
        _safe_str(data.get("issuer", "")),
        _safe_str(data.get("noteNumber", "")),
        _safe_float(data.get("billAmount")),
        _safe_float(data.get("accruedInterest")),
        _safe_str(data.get("issueDate", "")),
        _safe_str(data.get("maturityDate", "")),
        _safe_str(data.get("acceptorBank", "")),
        _safe_str(data.get("creditRating", "")),
        _safe_str(data.get("discountBank", "")),
        _safe_float(data.get("discountAmount")),
        _safe_float(data.get("discountInterest")),
        _safe_str(data.get("isDerecognized", "")),
        _safe_str(data.get("isCorrect", "")),
        _safe_str(data.get("indexRef", "")),
    ]


def _export_d1_9_row(data: dict) -> list:
    """D1-9 贴息检查表行导出（13列 InterestCheckRow）。

    派生列（贴息天数/应计贴现利息/差异）导出时计算供参考，导入时忽略。
    """
    face_value = _safe_float(data.get("faceValue"))
    discount_rate = _safe_float(data.get("discountRate"))
    booked_interest = _safe_float(data.get("bookedInterest"))
    discount_days = _calc_discount_days(
        _safe_str(data.get("maturityDate", "")),
        _safe_str(data.get("discountDate", "")),
    )
    calculated_interest = face_value * discount_rate * discount_days / 360.0
    difference = calculated_interest - booked_interest
    return [
        _safe_str(data.get("noteType", "")),
        face_value,
        _safe_float(data.get("faceRate")),
        _safe_str(data.get("issueDate", "")),
        _safe_str(data.get("maturityDate", "")),
        _safe_float(data.get("maturityValue")),
        _safe_str(data.get("discountDate", "")),
        discount_days,  # 派生：贴息天数
        discount_rate,
        calculated_interest,  # 派生：应计贴现利息
        booked_interest,
        difference,  # 派生：差异
        _safe_str(data.get("remark", "")),
    ]


def _calc_discount_days(maturity_date: str, discount_date: str) -> int:
    """计算贴息天数 = 到期日 - 贴现日（天）。日期缺失或无法解析时返回0。"""
    from datetime import date

    def _parse(s: str) -> date | None:
        s = (s or "").strip()
        if not s:
            return None
        s = s[:10]
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                from datetime import datetime

                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    m = _parse(maturity_date)
    d = _parse(discount_date)
    if m is None or d is None:
        return 0
    return (m - d).days


def _export_d1_10_row(data: dict) -> list:
    return [
        _safe_str(data.get("noteType", "")),
        _safe_str(data.get("noteNo", "")),
        _safe_str(data.get("issueDate", "")),
        _safe_str(data.get("drawer", "")),
        _safe_str(data.get("acceptor", "")),
        _safe_float(data.get("amount")),
        _safe_str(data.get("maturityDate", "")),
        _safe_str(data.get("predecessor", "")),
        _safe_str(data.get("receiveDate", "")),
        _safe_str(data.get("endorseDate", "")),
        _safe_str(data.get("endorsee", "")),
        _safe_str(data.get("noteStatus", "")),
        _safe_str(data.get("hasDifference", "")),
        _safe_str(data.get("differenceReason", "")),
        _safe_str(data.get("indexRef", "")),
    ]


def _export_d1_11_row(data: dict) -> list:
    opening = _safe_float(data.get("openingBalance"))
    debit = _safe_float(data.get("debitOccurrence"))
    credit = _safe_float(data.get("creditOccurrence"))
    closing = _safe_float(data.get("closingBalance")) or (opening + debit - credit)
    provision = _safe_float(data.get("badDebtProvision"))
    book = _safe_float(data.get("bookValue")) or (closing - provision)
    return [
        _safe_str(data.get("partyName", "")),
        _safe_str(data.get("relationship", "")),
        opening,
        debit,
        credit,
        closing,
        provision,
        book,
        _safe_str(data.get("agingInfo", "")),
        _safe_str(data.get("transactionNature", "")),
        _safe_float(data.get("postHonored")),
        _safe_str(data.get("indexRef", "")),
        _safe_str(data.get("remark", "")),
    ]


def _export_d1_12_row(data: dict) -> list:
    return [
        _safe_str(data.get("noteType", "")),
        _safe_str(data.get("noteNo", "")),
        _safe_str(data.get("receiveDate", "")),
        _safe_str(data.get("predecessor", "")),
        _safe_str(data.get("issueDate", "")),
        _safe_str(data.get("drawer", "")),
        _safe_str(data.get("acceptor", "")),
        _safe_float(data.get("noteAmount")),
        _safe_str(data.get("maturityDate", "")),
        _safe_float(data.get("pledgeAmount")),
        _safe_str(data.get("pledgee", "")),
        _safe_str(data.get("pledgeReason", "")),
        _safe_str(data.get("pledgeCondition", "")),
        _safe_str(data.get("pledgePeriod", "")),
        _safe_str(data.get("pledgeAgreement", "")),
        _safe_str(data.get("indexRef", "")),
    ]


def _export_d1_13_row(data: dict, seq: int = 0) -> list:
    return [
        int(_safe_float(data.get("seq"))) or seq,
        _safe_str(data.get("noteType", "")),
        _safe_str(data.get("noteNo", "")),
        _safe_str(data.get("drawer", "")),
        _safe_str(data.get("acceptor", "")),
        _safe_float(data.get("amount")),
        _safe_str(data.get("maturityDate", "")),
        _safe_str(data.get("existenceCheck", "")),
        _safe_str(data.get("accuracyCheck", "")),
        _safe_str(data.get("appropriatenessCheck", "")),
        _safe_str(data.get("remark", "")),
        _safe_str(data.get("indexRef", "")),
    ]


def _export_d1_13_specific_row(data: dict, seq: int = 0) -> list:
    """特定样本行导出。description 映射至「票据号码」列（前端 SpecificSampleRow 无票据类型/索引字段）。"""
    description = _safe_str(data.get("description", ""))
    note_type = _safe_str(data.get("noteType", ""))
    note_no = _safe_str(data.get("noteNo", "")) or description
    return [
        int(_safe_float(data.get("seq"))) or seq,
        note_type,
        note_no,
        _safe_float(data.get("amount")),
        _safe_str(data.get("reason", "")),
        _safe_str(data.get("indexRef", "")),
    ]


def _export_d1_13_population_row(population: dict[str, Any]) -> list:
    return [
        _safe_str(population.get("populationDesc", "")),
        _safe_float(population.get("totalCount")),
        _safe_float(population.get("totalAmount")),
        _safe_float(population.get("sampleSize")),
        _safe_float(population.get("actualDrawn")),
        _safe_str(population.get("sampleCalcRef", "")),
    ]


def _export_d1_13_conclusion_row(conclusion: dict[str, Any]) -> list:
    return [
        _safe_float(conclusion.get("tolerableErrorRate", 0.05)),
        _safe_str(conclusion.get("testConclusion", "")),
        _safe_str(conclusion.get("auditNote", "")),
        _safe_str(conclusion.get("auditConclusion", "")),
    ]


def _export_d1_15_row(data: dict) -> list:
    """D1-15 ECL测算表行导出。D列(应计提)和F列(差异)为计算列，导出时包含供参考。"""
    balance = _safe_float(data.get("balance"))
    loss_rate = _safe_float(data.get("lossRate"))
    actual_provision = _safe_float(data.get("actualProvision"))
    should_provision = balance * loss_rate  # D = B × C
    difference = actual_provision - should_provision  # F = E - D
    return [
        _safe_str(data.get("debtor", "")),
        balance,
        loss_rate,
        should_provision,
        actual_provision,
        difference,
        _safe_str(data.get("basis", "")),
        _safe_str(data.get("indexRef", "")),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 导入行解析
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_d1_2_row(row: tuple, actual_headers: list[str]) -> dict:
    return {
        "rowId": str(uuid4()),
        "category": _safe_str(_col_val(row, actual_headers, "票据种类")),
        "isFixed": False,
        "priorUnadjusted": _safe_float(_col_val(row, actual_headers, "期初未审")),
        "priorAje": _safe_float(_col_val(row, actual_headers, "期初AJE")),
        "priorRje": _safe_float(_col_val(row, actual_headers, "期初RJE")),
        "currentIncrease": _safe_float(_col_val(row, actual_headers, "本期增加")),
        "currentDecrease": _safe_float(_col_val(row, actual_headers, "本期减少")),
        "currentAje": _safe_float(_col_val(row, actual_headers, "期末AJE")),
        "currentRje": _safe_float(_col_val(row, actual_headers, "期末RJE")),
    }


def _parse_d1_3_row(row: tuple, actual_headers: list[str]) -> dict:
    return {
        "rowId": str(uuid4()),
        "customerName": _safe_str(_col_val(row, actual_headers, "客户名称")),
        "companyCode": _safe_str(_col_val(row, actual_headers, "公司代码")),
        "relationType": _safe_str(_col_val(row, actual_headers, "关联关系")),
        "priorUnadjusted": _safe_float(_col_val(row, actual_headers, "期初未审")),
        "priorAje": _safe_float(_col_val(row, actual_headers, "期初AJE")),
        "priorRje": _safe_float(_col_val(row, actual_headers, "期初RJE")),
        "currentIncrease": _safe_float(_col_val(row, actual_headers, "本期增加")),
        "currentDecrease": _safe_float(_col_val(row, actual_headers, "本期减少")),
        "currentBalance": _safe_float(_col_val(row, actual_headers, "期末余额")),
        "reclassification": _safe_float(_col_val(row, actual_headers, "重分类")),
        "currentAje": _safe_float(_col_val(row, actual_headers, "期末AJE")),
        "currentRje": _safe_float(_col_val(row, actual_headers, "期末RJE")),
    }


def _parse_d1_4_row(row: tuple, actual_headers: list[str]) -> dict:
    return {
        "rowId": str(uuid4()),
        "label": _safe_str(_col_val(row, actual_headers, "项目")),
        "category": "individual",
        "isSubRow": True,
        "priorUnadjusted": _safe_float(_col_val(row, actual_headers, "期初未审")),
        "priorAje": _safe_float(_col_val(row, actual_headers, "期初AJE")),
        "priorRje": _safe_float(_col_val(row, actual_headers, "期初RJE")),
        "currentProvision": _safe_float(_col_val(row, actual_headers, "本期计提")),
        "currentRecovery": _safe_float(_col_val(row, actual_headers, "本期收回")),
        "currentReversal": _safe_float(_col_val(row, actual_headers, "本期转回")),
        "currentWriteOff": _safe_float(_col_val(row, actual_headers, "本期核销")),
        "currentOther": _safe_float(_col_val(row, actual_headers, "本期其他")),
        "currentAje": _safe_float(_col_val(row, actual_headers, "期末AJE")),
        "currentRje": _safe_float(_col_val(row, actual_headers, "期末RJE")),
    }


def _parse_d1_6_row(row: tuple, actual_headers: list[str]) -> dict:
    """D1-6 业务模式依据表行解析（动态行，isFixed=False）"""
    return {
        "rowId": str(uuid4()),
        "combinationName": _safe_str(_col_val(row, actual_headers, "组合名称")),
        "businessMode": _safe_str(_col_val(row, actual_headers, "业务模式")),
        "basis": _safe_str(_col_val(row, actual_headers, "具体依据")),
        "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
        "remark": _safe_str(_col_val(row, actual_headers, "备注")),
        "isFixed": False,
    }


def _parse_d1_7_row(row: tuple, actual_headers: list[str]) -> dict:
    """D1-7 备查簿行解析（返回完整31字段 MemoRow）。

    category 由 noteType 派生（银行承兑→bank，否则→commercial）。
    """
    note_type = _safe_str(_col_val(row, actual_headers, "票据类型"))
    category = "bank" if _note_type_is_bank(note_type) else "commercial"
    return {
        "rowId": str(uuid4()),
        "rowType": "dynamic",
        "category": category,
        "noteType": note_type,
        "noteNumber": _safe_str(_col_val(row, actual_headers, "票据号")),
        "receivedDate": _safe_str(_col_val(row, actual_headers, "收到日期")),
        "endorser": _safe_str(_col_val(row, actual_headers, "前手")),
        "issueDate": _safe_str(_col_val(row, actual_headers, "出票日")),
        "issuer": _safe_str(_col_val(row, actual_headers, "出票人")),
        "acceptor": _safe_str(_col_val(row, actual_headers, "承兑人")),
        "amount": _safe_float(_col_val(row, actual_headers, "金额")),
        "maturityDate": _safe_str(_col_val(row, actual_headers, "到期日")),
        "transferDate": _safe_str(_col_val(row, actual_headers, "流转日")),
        "status": _safe_str(_col_val(row, actual_headers, "状态")),
        "endorsee": _safe_str(_col_val(row, actual_headers, "被背书人")),
        "discountBank": _safe_str(_col_val(row, actual_headers, "贴现银行")),
        "discountInterest": _safe_float(_col_val(row, actual_headers, "贴现息")),
        "isPledged": _safe_str(_col_val(row, actual_headers, "是否质押")),
        "isDiscountedEndorsed": _safe_str(_col_val(row, actual_headers, "审计日已贴现背书")),
        "beginningBalance": _safe_float(_col_val(row, actual_headers, "年初余额")),
        "currentReceived": _safe_float(_col_val(row, actual_headers, "本期收到")),
        "currentEndorsed": _safe_float(_col_val(row, actual_headers, "本期背书")),
        "currentMatured": _safe_float(_col_val(row, actual_headers, "本期到期承兑")),
        "currentDiscounted": _safe_float(_col_val(row, actual_headers, "本期贴现")),
        "endingBalance": _safe_float(_col_val(row, actual_headers, "年末余额")),
        "unexpiredEndorsedDiscounted": _safe_float(
            _col_val(row, actual_headers, "期末未到期背书贴现")
        ),
        "isDerecognized": _safe_str(_col_val(row, actual_headers, "是否终止确认")),
        "creditRating": _safe_str(_col_val(row, actual_headers, "信用评级")),
        "auditedFinancing": _safe_float(_col_val(row, actual_headers, "审定应收款项融资")),
        "auditedNotes": _safe_float(_col_val(row, actual_headers, "审定应收票据")),
        "relatedParty": _safe_str(_col_val(row, actual_headers, "关联关系")),
        "isOverdue": _safe_str(_col_val(row, actual_headers, "是否逾期")),
        "overdueTransferAmount": _safe_float(_col_val(row, actual_headers, "逾期转应收金额")),
        "remarkText": _safe_str(_col_val(row, actual_headers, "备注")),
    }


def _parse_d1_8_row(row: tuple, actual_headers: list[str]) -> dict:
    """D1-8 贴现/背书检查表行解析（16字段 EndorsementRow）"""
    return {
        "rowId": str(uuid4()),
        "rowType": "dynamic",
        "noteType": _safe_str(_col_val(row, actual_headers, "票据种类")),
        "receivedDate": _safe_str(_col_val(row, actual_headers, "收到日期")),
        "issuer": _safe_str(_col_val(row, actual_headers, "出票人")),
        "noteNumber": _safe_str(_col_val(row, actual_headers, "票据号")),
        "billAmount": _safe_float(_col_val(row, actual_headers, "汇票金额")),
        "accruedInterest": _safe_float(_col_val(row, actual_headers, "已计利息")),
        "issueDate": _safe_str(_col_val(row, actual_headers, "出票日")),
        "maturityDate": _safe_str(_col_val(row, actual_headers, "到期日")),
        "acceptorBank": _safe_str(_col_val(row, actual_headers, "承兑银行")),
        "creditRating": _safe_str(_col_val(row, actual_headers, "信用等级")),
        "discountBank": _safe_str(_col_val(row, actual_headers, "贴现银行")),
        "discountAmount": _safe_float(_col_val(row, actual_headers, "贴现金额")),
        "discountInterest": _safe_float(_col_val(row, actual_headers, "贴现息")),
        "isDerecognized": _safe_str(_col_val(row, actual_headers, "是否终止确认")),
        "isCorrect": _safe_str(_col_val(row, actual_headers, "会计处理是否正确")),
        "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
    }


def _parse_d1_9_row(row: tuple, actual_headers: list[str]) -> dict:
    """D1-9 贴息检查表行解析（仅可编辑字段）。

    派生列（贴息天数/应计贴现利息/差异）导入时忽略——前端根据可编辑字段重算。
    """
    return {
        "rowId": str(uuid4()),
        "rowType": "dynamic",
        "noteType": _safe_str(_col_val(row, actual_headers, "票据类型")),
        "faceValue": _safe_float(_col_val(row, actual_headers, "票面金额")),
        "faceRate": _safe_float(_col_val(row, actual_headers, "票面利率")),
        "issueDate": _safe_str(_col_val(row, actual_headers, "出票日期")),
        "maturityDate": _safe_str(_col_val(row, actual_headers, "到期日")),
        "maturityValue": _safe_float(_col_val(row, actual_headers, "到期日票据价值")),
        "discountDate": _safe_str(_col_val(row, actual_headers, "贴现日期")),
        # 贴息天数 - IGNORED (派生: 到期日-贴现日)
        "discountRate": _safe_float(_col_val(row, actual_headers, "贴现率")),
        # 应计贴现利息 - IGNORED (派生: P×R×D/360)
        "bookedInterest": _safe_float(_col_val(row, actual_headers, "账面贴现利息")),
        # 差异 - IGNORED (派生: 应计-账面)
        "remark": _safe_str(_col_val(row, actual_headers, "备注")),
    }


def _parse_d1_10_row(row: tuple, actual_headers: list[str]) -> dict:
    return {
        "id": str(uuid4()),
        "noteType": _safe_str(_col_val(row, actual_headers, "票据类型")),
        "noteNo": _safe_str(_col_val(row, actual_headers, "票据号")),
        "issueDate": _safe_str(_col_val(row, actual_headers, "出票日")),
        "drawer": _safe_str(_col_val(row, actual_headers, "出票人")),
        "acceptor": _safe_str(_col_val(row, actual_headers, "承兑人")),
        "amount": _safe_float(_col_val(row, actual_headers, "金额")),
        "maturityDate": _safe_str(_col_val(row, actual_headers, "到期日")),
        "predecessor": _safe_str(_col_val(row, actual_headers, "前手")),
        "receiveDate": _safe_str(_col_val(row, actual_headers, "收到日期")),
        "endorseDate": _safe_str(_col_val(row, actual_headers, "背书/贴现日")),
        "endorsee": _safe_str(_col_val(row, actual_headers, "被背书人/贴现行")),
        "noteStatus": _safe_str(_col_val(row, actual_headers, "票据状态")),
        "hasDifference": _safe_str(_col_val(row, actual_headers, "是否存在差异")),
        "differenceReason": _safe_str(_col_val(row, actual_headers, "差异原因")),
        "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
    }


def _parse_d1_11_row(row: tuple, actual_headers: list[str]) -> dict:
    opening = _safe_float(_col_val(row, actual_headers, "期初余额"))
    debit = _safe_float(_col_val(row, actual_headers, "借方发生"))
    credit = _safe_float(_col_val(row, actual_headers, "贷方发生"))
    closing = opening + debit - credit
    provision = _safe_float(_col_val(row, actual_headers, "减：坏账准备"))
    return {
        "id": str(uuid4()),
        "partyName": _safe_str(_col_val(row, actual_headers, "关联方名称")),
        "relationship": _safe_str(_col_val(row, actual_headers, "关联关系")),
        "openingBalance": opening,
        "debitOccurrence": debit,
        "creditOccurrence": credit,
        "closingBalance": closing,
        "badDebtProvision": provision,
        "bookValue": closing - provision,
        "agingInfo": _safe_str(_col_val(row, actual_headers, "发生时间及账龄")),
        "transactionNature": _safe_str(_col_val(row, actual_headers, "发生原因（款项性质）")),
        "postHonored": _safe_float(_col_val(row, actual_headers, "期后已兑现或已贴现")),
        "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
        "remark": _safe_str(_col_val(row, actual_headers, "备注")),
    }


def _parse_d1_12_row(row: tuple, actual_headers: list[str]) -> dict:
    return {
        "id": str(uuid4()),
        "noteType": _safe_str(_col_val(row, actual_headers, "票据类型")),
        "noteNo": _safe_str(_col_val(row, actual_headers, "票据号码")),
        "receiveDate": _safe_str(_col_val(row, actual_headers, "收到票据日期")),
        "predecessor": _safe_str(_col_val(row, actual_headers, "票据前手名称")),
        "issueDate": _safe_str(_col_val(row, actual_headers, "出票日期")),
        "drawer": _safe_str(_col_val(row, actual_headers, "出票人名称")),
        "acceptor": _safe_str(_col_val(row, actual_headers, "承兑人名称")),
        "noteAmount": _safe_float(_col_val(row, actual_headers, "票据金额")),
        "maturityDate": _safe_str(_col_val(row, actual_headers, "票据到期日")),
        "pledgeAmount": _safe_float(_col_val(row, actual_headers, "质押金额")),
        "pledgee": _safe_str(_col_val(row, actual_headers, "质权人")),
        "pledgeReason": _safe_str(_col_val(row, actual_headers, "质押原因")),
        "pledgeCondition": _safe_str(_col_val(row, actual_headers, "质押条件")),
        "pledgePeriod": _safe_str(_col_val(row, actual_headers, "质押期限")),
        "pledgeAgreement": _safe_str(_col_val(row, actual_headers, "质押协议")),
        "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
    }


def _parse_d1_13_row(row: tuple, actual_headers: list[str], seq: int) -> dict:
    return {
        "id": str(uuid4()),
        "seq": int(_safe_float(_col_val(row, actual_headers, "序号"))) or seq,
        "noteType": _safe_str(_col_val(row, actual_headers, "票据类型")),
        "noteNo": _safe_str(_col_val(row, actual_headers, "票据号码")),
        "drawer": _safe_str(_col_val(row, actual_headers, "出票人")),
        "acceptor": _safe_str(_col_val(row, actual_headers, "承兑人")),
        "amount": _safe_float(_col_val(row, actual_headers, "金额")),
        "maturityDate": _safe_str(_col_val(row, actual_headers, "到期日")),
        "existenceCheck": _safe_str(_col_val(row, actual_headers, "存在性验证")),
        "accuracyCheck": _safe_str(_col_val(row, actual_headers, "准确性验证")),
        "appropriatenessCheck": _safe_str(_col_val(row, actual_headers, "记录恰当性")),
        "remark": _safe_str(_col_val(row, actual_headers, "备注")),
        "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
    }


def _parse_d1_13_specific_row(row: tuple, actual_headers: list[str], seq: int) -> dict:
    """特定样本行解析。description 优先取「项目描述」，否则取「票据号码」。"""
    desc = _safe_str(_col_val(row, actual_headers, "项目描述"))
    if not desc:
        note_type = _safe_str(_col_val(row, actual_headers, "票据类型"))
        note_no = _safe_str(_col_val(row, actual_headers, "票据号码"))
        if note_type and note_no:
            desc = f"{note_type} {note_no}".strip()
        else:
            desc = note_no or note_type
    return {
        "id": str(uuid4()),
        "description": desc,
        "amount": _safe_float(_col_val(row, actual_headers, "金额")),
        "reason": _safe_str(_col_val(row, actual_headers, "选取原因")),
    }


def _parse_d1_13_population_row(row: tuple, actual_headers: list[str]) -> dict[str, Any]:
    return {
        "populationDesc": _safe_str(_col_val(row, actual_headers, "总体描述")),
        "totalCount": _safe_float(_col_val(row, actual_headers, "总体笔数")),
        "totalAmount": _safe_float(_col_val(row, actual_headers, "总体金额")),
        "sampleSize": _safe_float(_col_val(row, actual_headers, "样本量")),
        "actualDrawn": _safe_float(_col_val(row, actual_headers, "实际抽取")),
        "sampleCalcRef": _safe_str(_col_val(row, actual_headers, "抽样索引")),
    }


def _parse_d1_13_conclusion_row(row: tuple, actual_headers: list[str]) -> dict[str, Any]:
    return {
        "tolerableErrorRate": _safe_float(_col_val(row, actual_headers, "可容忍误差率")) or 0.05,
        "testConclusion": _safe_str(_col_val(row, actual_headers, "测试结论")),
        "auditNote": _safe_str(_col_val(row, actual_headers, "审计说明")),
        "auditConclusion": _safe_str(_col_val(row, actual_headers, "审计结论")),
    }


def _parse_d1_15_row(row: tuple, actual_headers: list[str]) -> dict:
    """D1-15 ECL测算表行导入。D列(应计提)和F列(差异)为计算列，导入时忽略。"""
    return {
        "id": str(uuid4()),
        "debtor": _safe_str(_col_val(row, actual_headers, "债务人名称")),
        "balance": _safe_float(_col_val(row, actual_headers, "审定余额")),
        "lossRate": _safe_float(_col_val(row, actual_headers, "预期信用损失率")),
        # D列(应计提) - IGNORED on import (computed: B×C)
        "actualProvision": _safe_float(_col_val(row, actual_headers, "账面余额")),
        # F列(差异) - IGNORED on import (computed: E-D)
        "basis": _safe_str(_col_val(row, actual_headers, "计提依据")),
        "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# D1-15 专用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_D1_15_SECTION_PORTFOLIO = "--- 按组合计提 ---"
_D1_15_SECTION_INDIVIDUAL = "--- 按单项计提 ---"


def _is_section_marker(row: tuple) -> str | None:
    """检测行是否为section分隔符，返回marker文本或None"""
    if not row:
        return None
    first_cell = str(row[0]).strip() if row[0] is not None else ""
    if "按组合计提" in first_cell:
        return "portfolio"
    if "按单项计提" in first_cell:
        return "individual"
    return None


def _is_d1_16_section_marker(row: tuple) -> str | None:
    if not row:
        return None
    first_cell = str(row[0]).strip() if row[0] is not None else ""
    if "转回检查" in first_cell:
        return "reversal"
    if "核销检查" in first_cell:
        return "writeoff"
    return None


def _is_d1_13_section_marker(row: tuple) -> str | None:
    if not row:
        return None
    first_cell = str(row[0]).strip() if row[0] is not None else ""
    if "抽样总体" in first_cell:
        return "population"
    if "特定样本" in first_cell:
        return "specific"
    if "凭证核对" in first_cell:
        return "vouching"
    if "测试结论" in first_cell:
        return "conclusion"
    return None


def _export_d1_5_row(idx: int, data: dict[str, str | float]) -> list:
    return [
        idx,
        _safe_str(data.get("type", "")),
        _safe_str(data.get("debit", "")),
        _safe_str(data.get("credit", "")),
        _safe_float(data.get("amount")),
        _safe_str(data.get("desc", "")),
    ]


def _export_d1_16_reversal_row(data: dict) -> list:
    return [
        _safe_str(data.get("unitName", "")),
        _safe_str(data.get("reason", "")),
        _safe_str(data.get("recoveryMethod", "")),
        _safe_str(data.get("originalBasis", "")),
        _safe_float(data.get("reversalAmount")),
        _safe_float(data.get("priorProvisionAmount")),
        _safe_str(data.get("reasonabilityAnalysis", "")),
        _safe_str(data.get("indexRef", "")),
    ]


def _export_d1_16_writeoff_row(data: dict) -> list:
    return [
        _safe_str(data.get("unitName", "")),
        _safe_str(data.get("noteNature", "")),
        _safe_float(data.get("writeoffAmount")),
        _safe_str(data.get("writeoffReason", "")),
        _safe_str(data.get("writeoffProcedure", "")),
    ]


def _parse_d1_5_row(row: tuple, actual_headers: list[str], seq: int) -> dict:
    return {
        "type": _safe_str(_col_val(row, actual_headers, "类别")) or "AJE",
        "debit": _safe_str(_col_val(row, actual_headers, "借方科目")),
        "credit": _safe_str(_col_val(row, actual_headers, "贷方科目")),
        "amount": _safe_float(_col_val(row, actual_headers, "金额")),
        "desc": _safe_str(_col_val(row, actual_headers, "说明")),
        "seq": int(_safe_float(_col_val(row, actual_headers, "序号"))) or seq,
    }


def _parse_d1_16_reversal_row(row: tuple, actual_headers: list[str]) -> dict:
    return {
        "id": str(uuid4()),
        "unitName": _safe_str(_col_val(row, actual_headers, "单位名称")),
        "reason": _safe_str(_col_val(row, actual_headers, "转回原因")),
        "recoveryMethod": _safe_str(_col_val(row, actual_headers, "收回方式")),
        "originalBasis": _safe_str(_col_val(row, actual_headers, "原确定坏账准备的依据")),
        "reversalAmount": _safe_float(_col_val(row, actual_headers, "收回或转回金额")),
        "priorProvisionAmount": _safe_float(_col_val(row, actual_headers, "收回或转回前累计已计提坏账准备金额")),
        "reasonabilityAnalysis": _safe_str(_col_val(row, actual_headers, "合理性分析")),
        "indexRef": _safe_str(_col_val(row, actual_headers, "索引号")),
    }


def _parse_d1_16_writeoff_row(row: tuple, actual_headers: list[str]) -> dict:
    return {
        "id": str(uuid4()),
        "unitName": _safe_str(_col_val(row, actual_headers, "单位名称")),
        "noteNature": _safe_str(_col_val(row, actual_headers, "应收票据的性质")),
        "writeoffAmount": _safe_float(_col_val(row, actual_headers, "核销金额")),
        "writeoffReason": _safe_str(_col_val(row, actual_headers, "核销原因")),
        "writeoffProcedure": _safe_str(_col_val(row, actual_headers, "履行的核销程序")),
    }


async def _load_remark_json(wp_id: str, item_id: str, db: AsyncSession) -> Any:
    import sqlalchemy as sa

    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": item_id},
    )
    row = result.fetchone()
    if not row or not row.remark:
        return None
    try:
        return json.loads(row.remark)
    except (json.JSONDecodeError, TypeError):
        return None


async def _load_scalar_remark(wp_id: str, item_id: str, db: AsyncSession) -> str:
    import sqlalchemy as sa

    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": item_id},
    )
    row = result.fetchone()
    if not row or row.remark is None:
        return ""
    return str(row.remark)


async def _fetch_d1_response_map(wp_id: str, db: AsyncSession, prefix: str) -> dict[str, str]:
    import sqlalchemy as sa

    result = await db.execute(
        sa.text(
            "SELECT item_id, remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE :prefix"
        ),
        {"wp_id": wp_id, "prefix": f"{prefix}%"},
    )
    return {row.item_id: (row.remark or "") for row in result.fetchall()}


async def _upsert_d1_cell(db: AsyncSession, wp_id: str, item_id: str, remark: str) -> None:
    import sqlalchemy as sa

    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
            VALUES (:id, :wp_id, :item_id, :remark, NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :remark, updated_at = NOW()
        """),
        {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": remark},
    )


async def _load_d1_5_entries(wp_id: str, db: AsyncSession) -> list[dict]:
    import sqlalchemy as sa

    count_row = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = 'D1-entry-count' LIMIT 1"
        ),
        {"wp_id": wp_id},
    )
    count_val = count_row.fetchone()
    count = int(_safe_float(count_val.remark if count_val and count_val.remark else 0))
    entries: list[dict] = []
    for i in range(1, count + 1):
        fields = ["type", "debit", "credit", "amount", "desc"]
        data: dict[str, str | float] = {}
        for f in fields:
            item_id = f"D1-entry-{i}-{f}"
            if f == "type":
                res = await db.execute(
                    sa.text(
                        "SELECT conclusion, remark FROM checklist_responses "
                        "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
                    ),
                    {"wp_id": wp_id, "item_id": item_id},
                )
                r = res.fetchone()
                data["type"] = _safe_str(r.conclusion if r else "")
            else:
                res = await db.execute(
                    sa.text(
                        "SELECT remark FROM checklist_responses "
                        "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
                    ),
                    {"wp_id": wp_id, "item_id": item_id},
                )
                r = res.fetchone()
                data[f] = r.remark if r and r.remark else (0 if f == "amount" else "")
        entries.append(data)
    return entries


async def _export_d1_5_data(wp_id: str, db: AsyncSession) -> StreamingResponse:
    entries = await _load_d1_5_entries(wp_id, db)
    wb = _create_template_wb("D1-5")
    ws = wb.active
    for i, entry in enumerate(entries, start=1):
        ws.append(_export_d1_5_row(i, entry))
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('D1-5_数据.xlsx')}"},
    )


async def _export_d1_16_data(wp_id: str, db: AsyncSession) -> StreamingResponse:
    reversal_rows = await _load_remark_json(wp_id, "D1-writeoff-reversal-rows", db) or []
    writeoff_rows = await _load_remark_json(wp_id, "D1-writeoff-writeoff-rows", db) or []
    if not isinstance(reversal_rows, list):
        reversal_rows = []
    if not isinstance(writeoff_rows, list):
        writeoff_rows = []

    wb = Workbook()
    ws = wb.active
    ws.title = "D1-16"
    section_font = Font(bold=True, size=11, color="333333")
    section_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

    def write_headers(headers: list[str], start_row: int) -> None:
        for col_idx, name in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col_idx, value=name)
            cell.font = header_font
            cell.fill = header_fill

    r = 1
    cell = ws.cell(row=r, column=1, value=_D1_16_SECTION_REVERSAL)
    cell.font = section_font
    cell.fill = section_fill
    r += 1
    write_headers(_D1_16_REVERSAL_HEADERS, r)
    r += 1
    for data in reversal_rows:
        ws.append(_export_d1_16_reversal_row(data))
        r += 1
    r += 1
    cell = ws.cell(row=r, column=1, value=_D1_16_SECTION_WRITEOFF)
    cell.font = section_font
    cell.fill = section_fill
    r += 1
    write_headers(_D1_16_WRITEOFF_HEADERS, r)
    r += 1
    for data in writeoff_rows:
        ws.append(_export_d1_16_writeoff_row(data))

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('D1-16_数据.xlsx')}"},
    )


async def _export_d1_1_data(wp_id: str, db: AsyncSession) -> StreamingResponse:
    responses = await _fetch_d1_response_map(wp_id, db, "D1-adj-")
    wb = Workbook()
    ws = wb.active
    ws.title = "D1-1"
    ws.append(_SHEET_HEADERS["D1-1"])
    ws.freeze_panes = "A2"
    for row_key, label in _D1_1_ROWS:
        values = [row_key, label]
        for field_key, _header, is_text in _D1_1_FIELDS:
            if row_key == "tb":
                if field_key == "current-unadj":
                    raw_tb = responses.get("D1-adj-tb-amount", "")
                    values.append(_safe_float(raw_tb) if raw_tb else 0.0)
                else:
                    values.append("" if is_text else 0.0)
                continue
            item_id = f"D1-adj-{row_key}-{field_key}"
            raw = responses.get(item_id, "")
            if is_text:
                values.append(raw)
            else:
                values.append(_safe_float(raw) if raw else 0.0)
        ws.append(values)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('D1-1_数据.xlsx')}"},
    )


async def _export_d1_14_data(wp_id: str, db: AsyncSession) -> StreamingResponse:
    import sqlalchemy as sa

    wb = Workbook()
    ws = wb.active
    ws.title = "D1-14"
    ws.append(_SHEET_HEADERS["D1-14"])
    ws.freeze_panes = "A2"
    for item_id, label in _D1_14_ROWS:
        result = await db.execute(
            sa.text(
                "SELECT conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
            ),
            {"wp_id": wp_id, "item_id": item_id},
        )
        row = result.fetchone()
        conclusion = str(row.conclusion) if row and row.conclusion is not None else ""
        remark = str(row.remark) if row and row.remark is not None else ""
        ws.append([item_id, label, conclusion, remark])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('D1-14_数据.xlsx')}"},
    )


async def _import_d1_5_data(
    wp_id: str,
    ws: Any,
    actual_headers: list[str],
    db: AsyncSession,
) -> dict[str, Any]:
    import sqlalchemy as sa

    parsed: list[dict] = []
    row_count = 0
    truncated = False
    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in row):
            continue
        row_count += 1
        if row_count > _ROW_LIMIT:
            truncated = True
            break
        parsed.append(_parse_d1_5_row(row, actual_headers, row_count))

    # 清除旧 entry keys（批量写入新数据）
    await db.execute(
        sa.text("DELETE FROM checklist_responses WHERE wp_id = :wp_id AND item_id LIKE 'D1-entry-%'"),
        {"wp_id": wp_id},
    )

    items_to_write: list[tuple[str, str | None, str | None]] = [
        ("D1-entry-count", None, str(len(parsed))),
    ]
    for i, entry in enumerate(parsed, start=1):
        items_to_write.append((f"D1-entry-{i}-type", entry["type"], None))
        items_to_write.append((f"D1-entry-{i}-debit", None, entry["debit"]))
        items_to_write.append((f"D1-entry-{i}-credit", None, entry["credit"]))
        items_to_write.append((f"D1-entry-{i}-amount", None, str(entry["amount"])))
        items_to_write.append((f"D1-entry-{i}-desc", None, entry["desc"]))

    for item_id, conclusion, remark in items_to_write:
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (id, wp_id, item_id, conclusion, remark, updated_at)
                VALUES (:id, :wp_id, :item_id, :conclusion, :remark, NOW())
                ON CONFLICT (wp_id, item_id)
                DO UPDATE SET conclusion = :conclusion, remark = :remark, updated_at = NOW()
            """),
            {
                "id": str(uuid4()),
                "wp_id": wp_id,
                "item_id": item_id,
                "conclusion": conclusion,
                "remark": remark,
            },
        )
    await db.commit()

    result: dict[str, Any] = {
        "ok": True,
        "imported_count": len(parsed),
        "row_count": len(parsed),
        "field_count": len(_SHEET_HEADERS["D1-5"]),
    }
    if truncated:
        result["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断"
        result["truncated"] = True
    return result


async def _import_d1_1_data(
    wp_id: str,
    ws: Any,
    actual_headers: list[str],
    db: AsyncSession,
) -> dict[str, Any]:
    rows_data: list[dict[str, Any]] = []
    row_count = 0
    truncated = False
    valid_row_keys = {rk for rk, _ in _D1_1_ROWS}

    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in row):
            continue
        parsed_row_key = _safe_str(_col_val(row, actual_headers, "行键"))
        parsed_label = _safe_str(_col_val(row, actual_headers, "项目"))
        if not parsed_row_key:
            for rk, label in _D1_1_ROWS:
                if label == parsed_label:
                    parsed_row_key = rk
                    break
        if not parsed_row_key or parsed_row_key not in valid_row_keys:
            continue
        row_count += 1
        if row_count > _ROW_LIMIT:
            truncated = True
            break
        parsed: dict[str, Any] = {"rowKey": parsed_row_key}
        for field_key, header, is_text in _D1_1_FIELDS:
            val = _col_val(row, actual_headers, header)
            parsed[field_key] = _safe_str(val) if is_text else _safe_float(val)
        rows_data.append(parsed)

    field_count = 0
    for row_data in rows_data:
        row_key = row_data.get("rowKey", "")
        if not row_key:
            continue
        for field_key, _header, is_text in _D1_1_FIELDS:
            val = row_data.get(field_key)
            if val is None or (not is_text and val == ""):
                continue
            if row_key == "tb":
                if field_key != "current-unadj":
                    continue
                await _upsert_d1_cell(db, wp_id, "D1-adj-tb-amount", str(_safe_float(val)))
                field_count += 1
                continue
            item_id = f"D1-adj-{row_key}-{field_key}"
            remark = str(val) if is_text else str(_safe_float(val))
            await _upsert_d1_cell(db, wp_id, item_id, remark)
            field_count += 1

    await db.commit()
    result: dict[str, Any] = {
        "ok": True,
        "imported_count": len(rows_data),
        "row_count": len(rows_data),
        "field_count": field_count,
    }
    if truncated:
        result["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断"
        result["truncated"] = True
    return result


async def _import_d1_14_data(
    wp_id: str,
    ws: Any,
    actual_headers: list[str],
    db: AsyncSession,
) -> dict[str, Any]:
    import sqlalchemy as sa

    rows_count = 0
    truncated = False
    valid_item_ids = {item_id for item_id, _ in _D1_14_ROWS}

    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in row):
            continue
        rows_count += 1
        if rows_count > _ROW_LIMIT:
            truncated = True
            break
        item_id = _safe_str(_col_val(row, actual_headers, "item_id"))
        if not item_id:
            continue
        if item_id not in valid_item_ids:
            continue
        conclusion = _safe_str(_col_val(row, actual_headers, "结论"))
        remark = _safe_str(_col_val(row, actual_headers, "内容"))
        conclusion_val: str | None = None
        remark_val: str | None = None
        if item_id in _D1_14_CONCLUSION_ONLY:
            conclusion_val = conclusion or None
        elif item_id in _D1_14_CONCLUSION_AND_REMARK:
            conclusion_val = conclusion or None
            remark_val = remark
        else:
            remark_val = remark

        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (id, wp_id, item_id, conclusion, remark, updated_at)
                VALUES (:id, :wp_id, :item_id, :conclusion, :remark, NOW())
                ON CONFLICT (wp_id, item_id)
                DO UPDATE SET conclusion = :conclusion, remark = :remark, updated_at = NOW()
            """),
            {
                "id": str(uuid4()),
                "wp_id": wp_id,
                "item_id": item_id,
                "conclusion": conclusion_val,
                "remark": remark_val,
            },
        )

    await db.commit()
    result: dict[str, Any] = {
        "ok": True,
        "imported_count": min(rows_count, _ROW_LIMIT),
        "row_count": min(rows_count, _ROW_LIMIT),
        "field_count": len(_SHEET_HEADERS["D1-14"]),
    }
    if truncated:
        result["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断"
        result["truncated"] = True
    return result


async def _import_d1_16_data(
    wp_id: str,
    ws: Any,
    db: AsyncSession,
) -> dict[str, Any]:
    import sqlalchemy as sa

    reversal_rows: list[dict] = []
    writeoff_rows: list[dict] = []
    current_section: str | None = None
    current_headers: list[str] = []
    truncated = False
    total = 0

    for row in ws.iter_rows(min_row=1, values_only=True):
        if all(v is None for v in row):
            continue
        marker = _is_d1_16_section_marker(row)
        if marker == "reversal":
            current_section = "reversal"
            current_headers = _D1_16_REVERSAL_HEADERS
            continue
        if marker == "writeoff":
            current_section = "writeoff"
            current_headers = _D1_16_WRITEOFF_HEADERS
            continue
        if not current_section:
            continue
        first = str(row[0]).strip() if row[0] is not None else ""
        if first in _D1_16_REVERSAL_HEADERS or first in _D1_16_WRITEOFF_HEADERS:
            current_headers = [str(c).strip() if c else "" for c in row if c is not None]
            continue
        total += 1
        if total > _ROW_LIMIT:
            truncated = True
            break
        if current_section == "reversal":
            reversal_rows.append(_parse_d1_16_reversal_row(row, current_headers))
        else:
            writeoff_rows.append(_parse_d1_16_writeoff_row(row, current_headers))

    for item_id, rows in [
        ("D1-writeoff-reversal-rows", reversal_rows),
        ("D1-writeoff-writeoff-rows", writeoff_rows),
    ]:
        remark_json = json.dumps(rows, ensure_ascii=False)
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
                VALUES (:id, :wp_id, :item_id, :remark, NOW())
                ON CONFLICT (wp_id, item_id)
                DO UPDATE SET remark = :remark, updated_at = NOW()
            """),
            {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": remark_json},
        )
    await db.commit()

    count = len(reversal_rows) + len(writeoff_rows)
    result: dict[str, Any] = {
        "ok": True,
        "imported_count": count,
        "row_count": count,
        "reversal_count": len(reversal_rows),
        "writeoff_count": len(writeoff_rows),
    }
    if truncated:
        result["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断"
        result["truncated"] = True
    return result


async def _export_d1_13_data(wp_id: str, db: AsyncSession) -> StreamingResponse:
    """D1-13 多section导出：抽样总体 + 特定样本 + 凭证核对 + 测试结论"""
    population = {
        "populationDesc": await _load_scalar_remark(wp_id, "D1-sampling-population-desc", db),
        "totalCount": _safe_float(await _load_scalar_remark(wp_id, "D1-sampling-population-count", db)),
        "totalAmount": _safe_float(await _load_scalar_remark(wp_id, "D1-sampling-population-amount", db)),
        "sampleSize": _safe_float(await _load_scalar_remark(wp_id, "D1-sampling-population-size", db)),
        "actualDrawn": _safe_float(await _load_scalar_remark(wp_id, "D1-sampling-population-drawn", db)),
        "sampleCalcRef": await _load_scalar_remark(wp_id, "D1-sampling-population-ref", db),
    }
    specific_rows = await _load_remark_json(wp_id, "D1-sampling-specific-samples", db) or []
    vouching_rows = await _load_remark_json(wp_id, "D1-sampling-vouching-rows", db) or []
    conclusion = {
        "tolerableErrorRate": _safe_float(
            await _load_scalar_remark(wp_id, "D1-sampling-tolerable-rate", db) or "0.05"
        ) or 0.05,
        "testConclusion": await _load_scalar_remark(wp_id, "D1-sampling-test-conclusion", db),
        "auditNote": await _load_scalar_remark(wp_id, "D1-sampling-note", db),
        "auditConclusion": await _load_scalar_remark(wp_id, "D1-sampling-conclusion", db),
    }
    if not isinstance(specific_rows, list):
        specific_rows = []
    if not isinstance(vouching_rows, list):
        vouching_rows = []

    wb = Workbook()
    ws = wb.active
    ws.title = "D1-13"
    section_font = Font(bold=True, size=11, color="333333")
    section_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

    def write_headers(headers: list[str], start_row: int) -> None:
        for col_idx, name in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col_idx, value=name)
            cell.font = header_font
            cell.fill = header_fill

    r = 1
    cell = ws.cell(row=r, column=1, value=_D1_13_SECTION_POPULATION)
    cell.font = section_font
    cell.fill = section_fill
    r += 1
    write_headers(_D1_13_POPULATION_HEADERS, r)
    r += 1
    ws.append(_export_d1_13_population_row(population))

    r += 2
    cell = ws.cell(row=r, column=1, value=_D1_13_SECTION_SPECIFIC)
    cell.font = section_font
    cell.fill = section_fill
    r += 1
    write_headers(_D1_13_SPECIFIC_HEADERS, r)
    r += 1
    for i, data in enumerate(specific_rows, start=1):
        ws.append(_export_d1_13_specific_row(data, i))

    r = ws.max_row + 2
    cell = ws.cell(row=r, column=1, value=_D1_13_SECTION_VOUCHING)
    cell.font = section_font
    cell.fill = section_fill
    r += 1
    write_headers(_SHEET_HEADERS["D1-13"], r)
    r += 1
    for i, data in enumerate(vouching_rows, start=1):
        ws.append(_export_d1_13_row(data, i))

    r = ws.max_row + 2
    cell = ws.cell(row=r, column=1, value=_D1_13_SECTION_CONCLUSION)
    cell.font = section_font
    cell.fill = section_fill
    r += 1
    write_headers(_D1_13_CONCLUSION_HEADERS, r)
    r += 1
    ws.append(_export_d1_13_conclusion_row(conclusion))

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('D1-13_数据.xlsx')}"},
    )


async def _import_d1_13_data(
    wp_id: str,
    ws: Any,
    db: AsyncSession,
) -> dict[str, Any]:
    """D1-13 多section导入：解析各section并写入 checklist_responses"""
    import sqlalchemy as sa

    population: dict[str, Any] = {}
    specific_rows: list[dict] = []
    vouching_rows: list[dict] = []
    conclusion: dict[str, Any] = {}
    current_section: str | None = None
    current_headers: list[str] = []
    truncated = False
    total = 0
    specific_seq = 0
    vouching_seq = 0
    population_parsed = False
    conclusion_parsed = False

    for row in ws.iter_rows(min_row=1, values_only=True):
        if all(v is None for v in row):
            continue
        marker = _is_d1_13_section_marker(row)
        if marker == "population":
            current_section = "population"
            current_headers = _D1_13_POPULATION_HEADERS
            continue
        if marker == "specific":
            current_section = "specific"
            current_headers = _D1_13_SPECIFIC_HEADERS
            continue
        if marker == "vouching":
            current_section = "vouching"
            current_headers = _SHEET_HEADERS["D1-13"]
            continue
        if marker == "conclusion":
            current_section = "conclusion"
            current_headers = _D1_13_CONCLUSION_HEADERS
            continue
        if not current_section:
            continue
        first = str(row[0]).strip() if row[0] is not None else ""
        header_sets = (
            _D1_13_POPULATION_HEADERS,
            _D1_13_SPECIFIC_HEADERS,
            _SHEET_HEADERS["D1-13"],
            _D1_13_CONCLUSION_HEADERS,
        )
        if any(first in hset for hset in header_sets):
            current_headers = [str(c).strip() if c else "" for c in row if c is not None]
            continue
        if current_section == "population":
            if not population_parsed:
                population = _parse_d1_13_population_row(row, current_headers)
                population_parsed = True
            continue
        if current_section == "conclusion":
            if not conclusion_parsed:
                conclusion = _parse_d1_13_conclusion_row(row, current_headers)
                conclusion_parsed = True
            continue
        total += 1
        if total > _ROW_LIMIT:
            truncated = True
            break
        if current_section == "specific":
            specific_seq += 1
            specific_rows.append(_parse_d1_13_specific_row(row, current_headers, specific_seq))
        elif current_section == "vouching":
            vouching_seq += 1
            vouching_rows.append(_parse_d1_13_row(row, current_headers, vouching_seq))

    items_to_write: list[tuple[str, str | None, str | None]] = [
        ("D1-sampling-population-desc", None, population.get("populationDesc", "")),
        ("D1-sampling-population-count", None, str(population.get("totalCount", 0))),
        ("D1-sampling-population-amount", None, str(population.get("totalAmount", 0))),
        ("D1-sampling-population-size", None, str(population.get("sampleSize", 0))),
        ("D1-sampling-population-drawn", None, str(population.get("actualDrawn", 0))),
        ("D1-sampling-population-ref", None, population.get("sampleCalcRef", "")),
        ("D1-sampling-specific-samples", None, json.dumps(specific_rows, ensure_ascii=False)),
        ("D1-sampling-vouching-rows", None, json.dumps(vouching_rows, ensure_ascii=False)),
        (
            "D1-sampling-tolerable-rate",
            None,
            str(conclusion.get("tolerableErrorRate", 0.05)),
        ),
        ("D1-sampling-test-conclusion", None, conclusion.get("testConclusion", "")),
        ("D1-sampling-note", None, conclusion.get("auditNote", "")),
        ("D1-sampling-conclusion", None, conclusion.get("auditConclusion", "")),
    ]

    for item_id, conclusion_val, remark in items_to_write:
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (id, wp_id, item_id, conclusion, remark, updated_at)
                VALUES (:id, :wp_id, :item_id, :conclusion, :remark, NOW())
                ON CONFLICT (wp_id, item_id)
                DO UPDATE SET conclusion = :conclusion, remark = :remark, updated_at = NOW()
            """),
            {
                "id": str(uuid4()),
                "wp_id": wp_id,
                "item_id": item_id,
                "conclusion": conclusion_val,
                "remark": remark,
            },
        )
    await db.commit()

    count = len(specific_rows) + len(vouching_rows)
    result: dict[str, Any] = {
        "ok": True,
        "imported_count": count,
        "row_count": count,
        "specific_count": len(specific_rows),
        "vouching_count": len(vouching_rows),
        "population_imported": population_parsed,
    }
    if truncated:
        result["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断"
        result["truncated"] = True
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/d1/export-template")
async def d1_export_template(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: D1-2, D1-3, D1-4, D1-6, D1-7, D1-8, D1-8T, D1-9, D1-15"),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（含表头+格式，无数据行）"""
    _validate_sheet(sheet)

    wb = _create_template_wb(sheet)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{sheet}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/api/workpapers/{wp_id}/d1/export-data")
async def d1_export_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: D1-2, D1-3, D1-4, D1-6, D1-7, D1-8, D1-8T, D1-9, D1-15"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx"""
    _validate_sheet(sheet)
    import sqlalchemy as sa

    # D1-16 / D1-5 / D1-15 / D1-14 / D1-13 / D1-1 特殊导出
    if sheet == "D1-1":
        return await _export_d1_1_data(wp_id, db)
    if sheet == "D1-14":
        return await _export_d1_14_data(wp_id, db)
    if sheet == "D1-16":
        return await _export_d1_16_data(wp_id, db)
    if sheet == "D1-13":
        return await _export_d1_13_data(wp_id, db)
    if sheet == "D1-5":
        return await _export_d1_5_data(wp_id, db)
    if sheet == "D1-15":
        return await _export_d1_15_data(wp_id, db)

    # D1-7 特殊处理：dict存储 {bankRows, commercialRows}
    if sheet == "D1-7":
        return await _export_d1_7_data(wp_id, db)

    # 加载 checklist_responses 数据
    item_ids = _SHEET_ITEM_ID[sheet]
    rows_data: list[dict] = []

    if isinstance(item_ids, list):
        # D1-4: 合并 individual + portfolio
        for item_id in item_ids:
            result = await db.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
                ),
                {"wp_id": wp_id, "item_id": item_id},
            )
            row = result.fetchone()
            if row and row.remark:
                try:
                    rows_data.extend(json.loads(row.remark))
                except (json.JSONDecodeError, TypeError):
                    pass
    else:
        result = await db.execute(
            sa.text(
                "SELECT remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
            ),
            {"wp_id": wp_id, "item_id": item_ids},
        )
        row = result.fetchone()
        if row and row.remark:
            try:
                rows_data = json.loads(row.remark)
            except (json.JSONDecodeError, TypeError):
                pass

    # 生成 xlsx
    wb = _create_template_wb(sheet)
    ws = wb.active

    export_fn = {
        "D1-2": _export_d1_2_row,
        "D1-3": _export_d1_3_row,
        "D1-4": _export_d1_4_row,
        "D1-6": _export_d1_6_row,
        "D1-8": _export_d1_8_row,
        "D1-8T": _export_d1_8_row,
        "D1-9": _export_d1_9_row,
        "D1-10": _export_d1_10_row,
        "D1-11": _export_d1_11_row,
        "D1-12": _export_d1_12_row,
    }[sheet]
    for i, data_row in enumerate(rows_data, start=1):
        ws.append(export_fn(data_row))

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{sheet}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


async def _export_d1_15_data(wp_id: str, db: AsyncSession) -> StreamingResponse:
    """D1-15 双section格式导出：Header + 组合section + 单项section"""
    import sqlalchemy as sa

    # 分别加载组合行和单项行
    portfolio_rows: list[dict] = []
    individual_rows: list[dict] = []

    for item_id, target_list in [
        ("D1-ecl-portfolio-rows", portfolio_rows),
        ("D1-ecl-individual-rows", individual_rows),
    ]:
        result = await db.execute(
            sa.text(
                "SELECT remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
            ),
            {"wp_id": wp_id, "item_id": item_id},
        )
        row = result.fetchone()
        if row and row.remark:
            try:
                target_list.extend(json.loads(row.remark))
            except (json.JSONDecodeError, TypeError):
                pass

    # 生成 xlsx with dual-section structure
    wb = Workbook()
    ws = wb.active
    ws.title = "D1-15"

    headers = _SHEET_HEADERS["D1-15"]
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Row 1: Headers
    for col_idx, col_name in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        ws.column_dimensions[cell.column_letter].width = max(len(col_name) * 2 + 4, 12)

    section_font = Font(bold=True, size=11, color="333333")
    section_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    section_align = Alignment(horizontal="center", vertical="center")

    # Row 2: 按组合计提 section header
    current_row = 2
    cell = ws.cell(row=current_row, column=1, value=_D1_15_SECTION_PORTFOLIO)
    cell.font = section_font
    cell.fill = section_fill
    cell.alignment = section_align
    current_row += 1

    # Portfolio data rows
    for data_row in portfolio_rows:
        row_values = _export_d1_15_row(data_row)
        for col_idx, val in enumerate(row_values, 1):
            ws.cell(row=current_row, column=col_idx, value=val)
        current_row += 1

    # 按单项计提 section header
    cell = ws.cell(row=current_row, column=1, value=_D1_15_SECTION_INDIVIDUAL)
    cell.font = section_font
    cell.fill = section_fill
    cell.alignment = section_align
    current_row += 1

    # Individual data rows
    for data_row in individual_rows:
        row_values = _export_d1_15_row(data_row)
        for col_idx, val in enumerate(row_values, 1):
            ws.cell(row=current_row, column=col_idx, value=val)
        current_row += 1

    ws.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = "D1-15_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


async def _export_d1_7_data(wp_id: str, db: AsyncSession) -> StreamingResponse:
    """D1-7 备查簿导出：读取dict存储 {bankRows, commercialRows}，拼接为数据行。"""
    import sqlalchemy as sa

    bank_rows: list[dict] = []
    commercial_rows: list[dict] = []

    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": "D1-memo-rows"},
    )
    row = result.fetchone()
    if row and row.remark:
        try:
            parsed = json.loads(row.remark)
            if isinstance(parsed, dict):
                bank_rows = parsed.get("bankRows", []) or []
                commercial_rows = parsed.get("commercialRows", []) or []
            elif isinstance(parsed, list):
                # 兼容：若历史存为纯list，按noteType拆分
                for r in parsed:
                    if _note_type_is_bank(_safe_str(r.get("noteType"))):
                        bank_rows.append(r)
                    else:
                        commercial_rows.append(r)
        except (json.JSONDecodeError, TypeError):
            pass

    wb = _create_template_wb("D1-7")
    ws = wb.active
    for data_row in [*bank_rows, *commercial_rows]:
        ws.append(_export_d1_7_row(data_row))

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = "D1-7_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/api/workpapers/{wp_id}/d1/import-data")
async def d1_import_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: D1-2, D1-3, D1-4, D1-6, D1-7, D1-8, D1-8T, D1-9, D1-15"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """解析上传xlsx，校验格式，写入 checklist_responses"""
    _validate_sheet(sheet)

    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件，请确认文件格式正确")

    ws = wb.active
    if ws is None:
        raise HTTPException(400, "xlsx文件中无活动工作表")

    # 验证列头
    actual_headers = [
        str(cell.value).strip() if cell.value else ""
        for cell in next(ws.iter_rows(min_row=1, max_row=1))
    ]

    missing_cols = _validate_columns(ws, sheet) if sheet not in ("D1-16", "D1-13") else []
    if missing_cols:
        raise HTTPException(400, detail={"message": "列名不匹配", "invalid_columns": missing_cols})

    if sheet == "D1-16":
        result = await _import_d1_16_data(wp_id, ws, db)
        wb.close()
        return result

    if sheet == "D1-1":
        result = await _import_d1_1_data(wp_id, ws, actual_headers, db)
        wb.close()
        return result

    if sheet == "D1-14":
        result = await _import_d1_14_data(wp_id, ws, actual_headers, db)
        wb.close()
        return result

    if sheet == "D1-13":
        result = await _import_d1_13_data(wp_id, ws, db)
        wb.close()
        return result

    if sheet == "D1-5":
        result = await _import_d1_5_data(wp_id, ws, actual_headers, db)
        wb.close()
        return result

    # D1-15 特殊处理：双section格式导入
    if sheet == "D1-15":
        result = await _import_d1_15_data(wp_id, ws, actual_headers, db)
        wb.close()
        return result

    # D1-7 特殊处理：拆分为 {bankRows, commercialRows} dict存储
    if sheet == "D1-7":
        result = await _import_d1_7_data(wp_id, ws, actual_headers, db)
        wb.close()
        return result

    # D1-4 特殊处理：按单项/按组合拆分写入
    if sheet == "D1-4":
        result = await _import_d1_4_data(wp_id, ws, actual_headers, db)
        wb.close()
        return result

    # 解析数据行
    parse_fn_map = {
        "D1-2": _parse_d1_2_row,
        "D1-3": _parse_d1_3_row,
        "D1-6": _parse_d1_6_row,
        "D1-8": _parse_d1_8_row,
        "D1-8T": _parse_d1_8_row,
        "D1-9": _parse_d1_9_row,
        "D1-10": _parse_d1_10_row,
        "D1-11": _parse_d1_11_row,
        "D1-12": _parse_d1_12_row,
    }
    rows_data: list[dict] = []
    truncated = False
    row_count = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in row):
            continue
        row_count += 1
        if row_count > _ROW_LIMIT:
            truncated = True
            break
        rows_data.append(parse_fn_map[sheet](row, actual_headers))

    wb.close()

    # 写入 checklist_responses
    import sqlalchemy as sa

    item_ids = _SHEET_ITEM_ID[sheet]
    if isinstance(item_ids, list):
        item_id = item_ids[0]
    else:
        item_id = item_ids

    remark_json = json.dumps(rows_data, ensure_ascii=False)
    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
            VALUES (:id, :wp_id, :item_id, :remark, NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :remark, updated_at = NOW()
        """),
        {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": remark_json},
    )
    await db.commit()

    result_data: dict[str, Any] = {
        "ok": True,
        "imported_count": len(rows_data),
        "row_count": len(rows_data),
        "field_count": len(_SHEET_HEADERS[sheet]),
    }
    if truncated:
        result_data["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断至{_ROW_LIMIT}行"
        result_data["truncated"] = True

    return result_data


async def _import_d1_4_data(
    wp_id: str,
    ws: Any,
    actual_headers: list[str],
    db: AsyncSession,
) -> dict[str, Any]:
    """D1-4 坏账准备：按「按组合计提」分界拆分为 individual / portfolio 两组写入"""
    import sqlalchemy as sa

    individual_rows: list[dict] = []
    portfolio_rows: list[dict] = []
    current_section = "individual"
    truncated = False
    row_count = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in row):
            continue
        label = _safe_str(_col_val(row, actual_headers, "项目"))
        if label == "按组合计提":
            current_section = "portfolio"
        row_count += 1
        if row_count > _ROW_LIMIT:
            truncated = True
            break
        parsed = _parse_d1_4_row(row, actual_headers)
        parsed["category"] = current_section
        if current_section == "portfolio":
            portfolio_rows.append(parsed)
        else:
            individual_rows.append(parsed)

    for item_id, rows in [
        ("D1-bd-individual-rows", individual_rows),
        ("D1-bd-portfolio-rows", portfolio_rows),
    ]:
        remark_json = json.dumps(rows, ensure_ascii=False)
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
                VALUES (:id, :wp_id, :item_id, :remark, NOW())
                ON CONFLICT (wp_id, item_id)
                DO UPDATE SET remark = :remark, updated_at = NOW()
            """),
            {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": remark_json},
        )
    await db.commit()

    total = len(individual_rows) + len(portfolio_rows)
    result: dict[str, Any] = {
        "ok": True,
        "imported_count": total,
        "row_count": total,
        "field_count": len(_SHEET_HEADERS["D1-4"]),
        "individual_count": len(individual_rows),
        "portfolio_count": len(portfolio_rows),
    }
    if truncated:
        result["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断至{_ROW_LIMIT}行"
        result["truncated"] = True
    return result


async def _import_d1_15_data(
    wp_id: str,
    ws: Any,
    actual_headers: list[str],
    db: AsyncSession,
) -> dict[str, Any]:
    """D1-15 双section格式导入：解析section分隔符，分别写入组合行和单项行"""
    import sqlalchemy as sa

    portfolio_rows: list[dict] = []
    individual_rows: list[dict] = []
    current_section: str | None = None
    truncated = False
    total_count = 0

    # 检测section分隔符是否存在
    found_portfolio_marker = False
    found_individual_marker = False

    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in row):
            continue

        # 检测section marker
        marker = _is_section_marker(row)
        if marker == "portfolio":
            current_section = "portfolio"
            found_portfolio_marker = True
            continue
        elif marker == "individual":
            current_section = "individual"
            found_individual_marker = True
            continue

        # 非marker行：按当前section归类
        if current_section is None:
            # 在第一个marker之前的行忽略（或视为portfolio）
            continue

        total_count += 1
        if total_count > _ROW_LIMIT:
            truncated = True
            break

        parsed = _parse_d1_15_row(row, actual_headers)
        if current_section == "portfolio":
            portfolio_rows.append(parsed)
        else:
            individual_rows.append(parsed)

    # 校验：必须存在section header
    if not found_portfolio_marker or not found_individual_marker:
        missing_markers = []
        if not found_portfolio_marker:
            missing_markers.append(_D1_15_SECTION_PORTFOLIO)
        if not found_individual_marker:
            missing_markers.append(_D1_15_SECTION_INDIVIDUAL)
        raise HTTPException(
            400,
            detail={
                "message": "缺少section分隔符行",
                "invalid_columns": missing_markers,
            },
        )

    # 分别写入两个item_id
    for item_id, rows_data in [
        ("D1-ecl-portfolio-rows", portfolio_rows),
        ("D1-ecl-individual-rows", individual_rows),
    ]:
        remark_json = json.dumps(rows_data, ensure_ascii=False)
        await db.execute(
            sa.text("""
                INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
                VALUES (:id, :wp_id, :item_id, :remark, NOW())
                ON CONFLICT (wp_id, item_id)
                DO UPDATE SET remark = :remark, updated_at = NOW()
            """),
            {"id": str(uuid4()), "wp_id": wp_id, "item_id": item_id, "remark": remark_json},
        )

    await db.commit()

    result_data: dict[str, Any] = {
        "ok": True,
        "imported_count": len(portfolio_rows) + len(individual_rows),
        "field_count": len(_SHEET_HEADERS["D1-15"]),
        "portfolio_count": len(portfolio_rows),
        "individual_count": len(individual_rows),
    }
    if truncated:
        result_data["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断至{_ROW_LIMIT}行"
        result_data["truncated"] = True

    return result_data


async def _import_d1_7_data(
    wp_id: str,
    ws: Any,
    actual_headers: list[str],
    db: AsyncSession,
) -> dict[str, Any]:
    """D1-7 备查簿导入：按"票据类型"列拆分为 bank/commercial 两组，写回dict存储。"""
    import sqlalchemy as sa

    bank_rows: list[dict] = []
    commercial_rows: list[dict] = []
    truncated = False
    total_count = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in row):
            continue
        total_count += 1
        if total_count > _ROW_LIMIT:
            truncated = True
            break
        parsed = _parse_d1_7_row(row, actual_headers)
        if parsed["category"] == "bank":
            bank_rows.append(parsed)
        else:
            commercial_rows.append(parsed)

    remark_json = json.dumps(
        {"bankRows": bank_rows, "commercialRows": commercial_rows},
        ensure_ascii=False,
    )
    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
            VALUES (:id, :wp_id, :item_id, :remark, NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :remark, updated_at = NOW()
        """),
        {"id": str(uuid4()), "wp_id": wp_id, "item_id": "D1-memo-rows", "remark": remark_json},
    )
    await db.commit()

    result_data: dict[str, Any] = {
        "ok": True,
        "imported_count": len(bank_rows) + len(commercial_rows),
        "field_count": len(_SHEET_HEADERS["D1-7"]),
        "bank_count": len(bank_rows),
        "commercial_count": len(commercial_rows),
    }
    if truncated:
        result_data["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断至{_ROW_LIMIT}行"
        result_data["truncated"] = True

    return result_data


# ═══════════════════════════════════════════════════════════════════════════════
# D1-ECL 专用端点（前端直接调用，hardcoded sheet="D1-15"）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/d1-ecl/export-template")
async def d1_ecl_export_template(
    wp_id: str,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """D1-ECL导出空白模板（D1-15 hardcoded）"""
    wb = _create_template_wb("D1-15")
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = "D1-15_ECL模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/api/workpapers/{wp_id}/d1-ecl/export-data")
async def d1_ecl_export_data(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """D1-ECL导出含数据的xlsx（D1-15 hardcoded）"""
    return await _export_d1_15_data(wp_id, db)


@router.post("/api/workpapers/{wp_id}/d1-ecl/import-data")
async def d1_ecl_import_data(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """D1-ECL导入xlsx数据（D1-15 hardcoded）"""
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件，请确认文件格式正确")

    ws = wb.active
    if ws is None:
        raise HTTPException(400, "xlsx文件中无活动工作表")

    # 验证列头
    actual_headers = [
        str(cell.value).strip() if cell.value else ""
        for cell in next(ws.iter_rows(min_row=1, max_row=1))
    ]

    missing_cols = _validate_columns(ws, "D1-15")
    if missing_cols:
        raise HTTPException(400, detail={"message": "列名不匹配", "invalid_columns": missing_cols})

    result = await _import_d1_15_data(wp_id, ws, actual_headers, db)
    wb.close()
    return result
