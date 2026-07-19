"""G4 债权投资(SPPI组) — 导入导出端点

支持 4 张动态行表格：
  G4-5 业务模式问卷 / G4-6 合同现金流量特征分析(八段产品表) /
  G4-7 盘点表 / G4-8 倒轧表

字段键与前端 composable (useG4SppiBusinessModel / useG4SppiTest /
useG4SppiInventory / useG4SppiReconciliation) 行接口严格对齐，保证 round-trip。

G4-8 按 3 区段分 sheet 导出（盘点日实存/增减变动/报表日实存+差异）。
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
    is_numeric_field_key,
    load_json_rows,
    parse_row_by_headers,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_rows,
    workbook_to_response,
)

router = APIRouter(tags=["g4-sppi-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# G4-5 业务模式分析问卷（6列）
# ═══════════════════════════════════════════════════════════════════════════════

_G4_5_HEADERS = [
    "问题ID", "序号", "题号", "问题", "回答(是/否)", "说明",
]
_G4_5_KEYS = ["id", "seq", "displaySeq", "question", "answer", "explanation"]

_G4_5_DEFAULT_ROWS: list[dict[str, Any]] = [
    {"id": "q1", "seq": 1, "displaySeq": "1", "question": "被审计单位是否涉及大额且频繁的债权投资出售？", "answer": None, "explanation": ""},
    {"id": "q2", "seq": 2, "displaySeq": "2", "question": "被审计单位持有债权投资的目的是交易性的？", "answer": None, "explanation": ""},
    {"id": "q2_1", "seq": 3, "displaySeq": "2.1", "question": "取得相关金融资产的目的，主要是为了近期出售或回购？", "answer": None, "explanation": ""},
    {"id": "q2_2", "seq": 4, "displaySeq": "2.2", "question": "相关金融资产在初始确认时属于集中管理的可辨认金融工具组合的一部分，且有客观证据表明近期实际存在短期获利模式？", "answer": None, "explanation": ""},
    {"id": "q2_3", "seq": 5, "displaySeq": "2.3", "question": "相关金融资产属于衍生工具（但符合财务担保合同定义的衍生工具以及被指定为有效套期工具的衍生工具除外）？", "answer": None, "explanation": ""},
    {"id": "q3", "seq": 6, "displaySeq": "3", "question": "被审计单位基于债权投资的公允价值作出决策并对其进行管理？", "answer": None, "explanation": ""},
    {"id": "q4", "seq": 7, "displaySeq": "4", "question": "未来是否预期会进行大额且频繁的债权投资出售？", "answer": None, "explanation": ""},
    {"id": "q5", "seq": 8, "displaySeq": "5", "question": "未来是否预期持有债权投资的目的是交易性的或基于债权投资的公允价值作出决策并对其进行管理？", "answer": None, "explanation": ""},
]

_G4_5_ID_BY_SEQ = {int(r["seq"]): str(r["id"]) for r in _G4_5_DEFAULT_ROWS}

# ═══════════════════════════════════════════════════════════════════════════════
# G4-6 合同现金流量特征分析（部分一 + 部分二三步合并）
# ═══════════════════════════════════════════════════════════════════════════════

# 部分(一): 债券投资 SPPI（含偿付顺序）
_G4_6_BOND_HEADERS = [
    "投资项目", "票面价值总额", "票面利率(%)", "偿付顺序",
    "提前回售选择权(是/否)", "展期选择权(是/否)", "权益转换特征(是/否)", "杠杆因素(是/否)",
    "结论", "分析项目", "判断逻辑",
]
_G4_6_BOND_KEYS = [
    "investProject", "faceValue", "couponRate", "repaymentOrder",
    "hasEarlyRedemption", "hasExtension", "hasEquityConversion", "hasLeverage",
    "conclusion", "analysisType", "methodologyText",
]

# 部分(三)～(六)
_G4_6_PREFERRED_HEADERS = [
    "投资项目", "投资总额", "期限", "票面利率", "递延付息(是/否)",
    "利息累积(是/否)", "利率跳升", "可转股(是/否)", "结论", "判断说明",
]
_G4_6_PREFERRED_KEYS = [
    "investProject", "totalAmount", "term", "couponRate", "deferredInterest",
    "interestCumulative", "rateStepUp", "convertibleToEquity", "conclusion", "judgmentNote",
]
_G4_6_CONVERTIBLE_HEADERS = [
    "投资项目", "投资总额", "期限", "票面利率", "初始转股价", "结论", "判断说明",
]
_G4_6_CONVERTIBLE_KEYS = [
    "investProject", "totalAmount", "term", "couponRate", "conversionPrice", "conclusion", "judgmentNote",
]
_G4_6_PROJECT_HEADERS = [
    "投资项目", "投资总额", "期限", "票面利率", "基础资产现金流", "结论", "判断说明",
]
_G4_6_PROJECT_KEYS = [
    "investProject", "totalAmount", "term", "couponRate", "underlyingCashFlow", "conclusion", "judgmentNote",
]
_G4_6_ABS_HEADERS = [
    "投资项目", "投资份额", "期限", "票面利率", "级次",
    "基础资产现金流", "信用风险分担", "结论", "判断说明",
]
_G4_6_ABS_KEYS = [
    "investProject", "shareAmount", "term", "couponRate", "tranche",
    "underlyingCashFlow", "creditRiskSharing", "conclusion", "judgmentNote",
]

# 兼容旧模板表头
_G4_6_BOND_HEADER_ALIASES = {
    "票面价值": "票面价值总额",
    "提前回售(是/否)": "提前回售选择权(是/否)",
    "展期(是/否)": "展期选择权(是/否)",
    "权益转换(是/否)": "权益转换特征(是/否)",
    "杠杆(是/否)": "杠杆因素(是/否)",
}

# 部分(二) 第一步: 保本保收益（8列）
_G4_6_STEP1_HEADERS = [
    "投资项目", "投资总额", "保证本金(是/否)", "固定收益(是/否)",
    "固定收益率(%)", "约定浮动收益(是/否)", "浮动收益率(%)", "结论",
]
_G4_6_STEP1_KEYS = [
    "investProject", "totalAmount", "guaranteesPrincipal", "hasFixedReturn",
    "fixedReturnRate", "hasFloatingReturn", "floatingReturnRate", "conclusion",
]

# 部分(二) 第二步: 浮动收益不现实（6列）
_G4_6_STEP2_HEADERS = [
    "投资项目", "固定收益率(%)", "浮动收益确定方式",
    "基础变量历史变动", "是否不现实(是/否)", "结论",
]
_G4_6_STEP2_KEYS = [
    "investProject", "fixedReturnRate", "floatingMethod",
    "baseVariableHistory", "isUnrealistic", "conclusion",
]

# 部分(二) 第三步: 穿透底层资产（4列）
_G4_6_STEP3_HEADERS = [
    "投资项目", "底层资产类型", "底层资产SPPI特征", "穿透结论",
]
_G4_6_STEP3_KEYS = [
    "investProject", "underlyingAssetType", "underlyingSppiFeature", "conclusion",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G4-7 有价证券盘点表（7列）
# ═══════════════════════════════════════════════════════════════════════════════

_G4_7_HEADERS = [
    "序号", "证券名称", "面值", "数量", "总计", "票面利率(%)", "到期日",
]
_G4_7_KEYS = [
    "seq", "securitiesName", "faceValue", "quantity", "total", "couponRate", "maturityDate",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G4-8 盘点倒轧表（3区段分sheet）
# 公式：报表日 = 盘点日 − 增加 + 减少（增减口径：资产负债表日→盘点日）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 盘点日实存(6列)
_G4_8_SEG1_HEADERS = ["证券名称", "数量", "面值", "总计", "票面利率(%)", "到期日"]
_G4_8_SEG1_KEYS = ["securitiesName", "countQuantity", "countFaceValue", "countTotal", "countCouponRate", "countMaturityDate"]

# 区段2: 增减变动（增加/减少拆分 + 证据索引）
_G4_8_SEG2_HEADERS = [
    "证券名称", "增加·数量", "增加·面值总额", "减少·数量", "减少·面值总额", "证据索引",
]
_G4_8_SEG2_KEYS = [
    "securitiesName", "increaseQuantity", "increaseFaceTotal",
    "decreaseQuantity", "decreaseFaceTotal", "changeEvidenceRef",
]

# 区段3: 报表日实存+差异
_G4_8_SEG3_HEADERS = [
    "证券名称", "报表日数量", "报表日面值", "报表日总计", "票面利率(%)", "到期日",
    "账面结存数量", "账面结存面值", "账面结存总计", "账面摊余成本",
    "差异·数量", "差异·面值", "备注",
]
_G4_8_SEG3_KEYS = [
    "securitiesName", "reportQuantity", "reportFaceValue", "reportTotal",
    "reportCouponRate", "reportMaturityDate",
    "bookQuantity", "bookFaceValue", "bookTotal", "bookCarryingAmount",
    "varianceQuantity", "variance", "remark",
]

# 全列（用于单sheet导入解析）
_G4_8_ALL_HEADERS = (
    _G4_8_SEG1_HEADERS
    + _G4_8_SEG2_HEADERS[1:]
    + _G4_8_SEG3_HEADERS[1:]
)
_G4_8_ALL_KEYS = (
    _G4_8_SEG1_KEYS
    + _G4_8_SEG2_KEYS[1:]
    + _G4_8_SEG3_KEYS[1:]
)

# 旧版列名别名 → 新 key（导入兼容）
_G4_8_HEADER_ALIASES = {
    "增减数量": "changeQuantity",
    "增减面值总额": "changeFaceValueTotal",
    "差异": "variance",
    "账面结存数量": "bookQuantity",
    "账面结存面值": "bookFaceValue",
    "账面结存总计": "bookTotal",
    "差异数量": "varianceQuantity",
    "差异·金额": "variance",
    "证据索引": "changeEvidenceRef",
    "账面摊余成本": "bookCarryingAmount",
}

_G4_8_SEGMENTS = [
    ("盘点日实存有价证券", _G4_8_SEG1_HEADERS, _G4_8_SEG1_KEYS),
    ("资产负债表日到盘点日增减", _G4_8_SEG2_HEADERS, _G4_8_SEG2_KEYS),
    ("报表日实存+账面差异", _G4_8_SEG3_HEADERS, _G4_8_SEG3_KEYS),
]

# 兼容旧区段名
_G4_8_SEG_ALIASES = {
    "盘点日实存": "盘点日实存有价证券",
    "增减变动": "资产负债表日到盘点日增减",
    "报表日实存+差异": "报表日实存+账面差异",
}

# 区段2 旧模板（仅增减数量/面值总额，无证券名称列）
_G4_8_SEG2_LEGACY_HEADERS = ["增减数量", "增减面值总额"]
_G4_8_SEG2_LEGACY_KEYS = ["changeQuantity", "changeFaceValueTotal"]

# 区段3 旧模板
_G4_8_SEG3_LEGACY_HEADERS = [
    "报表日数量", "报表日面值", "报表日总计", "票面利率(%)", "到期日",
    "账面结存数量", "账面结存面值", "账面结存总计", "差异", "备注",
]
_G4_8_SEG3_LEGACY_KEYS = [
    "reportQuantity", "reportFaceValue", "reportTotal", "reportCouponRate", "reportMaturityDate",
    "bookQuantity", "bookFaceValue", "bookTotal", "variance", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G4-5": "G4-5-questionnaire",
    "G4-6": "G4-6-bond-items",
    "G4-7": "G4-7-items",
    "G4-8": "G4-8-items",
}

_G4_6_SECTION_ITEM_IDS = {
    "债券投资SPPI": "G4-6-bond-items",
    "第一步-保本保收益": "G4-6-step1-items",
    "第二步-浮动收益不现实": "G4-6-step2-items",
    "第三步-穿透底层资产": "G4-6-step3-items",
    "优先股永续债": "G4-6-preferred-items",
    "可转换债券": "G4-6-convertible-items",
    "项目收益债信托": "G4-6-project-trust-items",
    "资产支持证券": "G4-6-abs-items",
}

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())


def _normalize_header(h: str) -> str:
    s = (h or "").strip()
    return _G4_6_BOND_HEADER_ALIASES.get(s, s)


def _match_sheet_name(sheetnames: list[str], *candidates: str) -> str | None:
    for cand in candidates:
        for name in sheetnames:
            if cand in name:
                return name
    return None


def _bool_fields_for_keys(keys: list[str]) -> set[str]:
    return {
        k for k in keys
        if k.startswith("has") or k.startswith("is") or k in {
            "guaranteesPrincipal", "hasFixedReturn", "hasFloatingReturn",
            "isUnrealistic", "hasEarlyRedemption", "hasExtension",
            "hasEquityConversion", "hasLeverage",
            "deferredInterest", "interestCumulative", "convertibleToEquity",
        }
    }


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


async def _load_canonical_rows(
    db: AsyncSession,
    wp_id: str,
    item_id: str,
) -> list[dict]:
    """优先 conclusion，兼容旧 remark。"""
    rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
    if rows:
        return rows
    return await load_json_rows(db, wp_id, item_id, field="remark")


async def _upsert_dual_rows(
    db: AsyncSession,
    wp_id: str,
    item_id: str,
    rows: list[dict],
) -> None:
    """conclusion + remark 双写，兼容旧读者。"""
    await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
    await upsert_json_rows(db, wp_id, item_id, rows, field="remark")


def _bool_to_str(val: Any) -> str:
    """布尔值转中文"是/否"用于导出。"""
    if val is True or val == "true" or val == "True":
        return "是"
    return "否"


def _str_to_bool(val: Any) -> bool:
    """中文"是/否"或True/False转布尔用于导入。"""
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("是", "true", "1", "yes")


def _export_row_bool_aware(row_data: dict, keys: list[str]) -> list[Any]:
    bool_keys = _bool_fields_for_keys(keys)
    out: list[Any] = []
    for k in keys:
        v = row_data.get(k)
        if k in bool_keys:
            out.append(_bool_to_str(v))
        else:
            out.append(v if v is not None else "")
    return out


def _g4_5_answer_to_str(val: Any) -> str:
    if val is True or val == "true" or val == "True":
        return "是"
    if val is False or val == "false" or val == "False":
        return "否"
    return ""


def _g4_5_str_to_answer(val: Any) -> bool | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    low = s.lower()
    if low in ("是", "true", "1", "yes"):
        return True
    if low in ("否", "false", "0", "no"):
        return False
    return None


def _export_g4_5_row(row_data: dict) -> list[Any]:
    out: list[Any] = []
    for k in _G4_5_KEYS:
        v = row_data.get(k)
        if k == "answer":
            out.append(_g4_5_answer_to_str(v))
        elif k == "seq":
            out.append(v if v is not None else "")
        else:
            out.append(v if v is not None else "")
    return out


async def _load_g4_5_rows(db: AsyncSession, wp_id: str) -> list[dict]:
    """读取 G4-5 问卷；优先 conclusion，兼容旧 remark。"""
    return await _load_canonical_rows(db, wp_id, _ITEM_IDS["G4-5"])


def _parse_g4_5_row(row: tuple, headers: list[str]) -> dict[str, Any]:
    parsed = parse_row_by_headers(row, headers, _G4_5_KEYS, expected_headers=_G4_5_HEADERS)
    raw_id = safe_str(parsed.get("id"))
    if raw_id:
        parsed["id"] = raw_id
    else:
        seq_val = parsed.get("seq")
        try:
            seq_int = int(float(seq_val)) if seq_val not in (None, "") else None
        except (TypeError, ValueError):
            seq_int = None
        parsed["id"] = _G4_5_ID_BY_SEQ.get(seq_int, str(uuid4()))
    seq_raw = parsed.get("seq")
    try:
        parsed["seq"] = int(float(seq_raw)) if seq_raw not in (None, "") else parsed.get("seq")
    except (TypeError, ValueError):
        pass
    parsed["answer"] = _g4_5_str_to_answer(parsed.get("answer"))
    parsed["explanation"] = safe_str(parsed.get("explanation"))
    parsed["displaySeq"] = safe_str(parsed.get("displaySeq"))
    parsed["question"] = safe_str(parsed.get("question"))
    return parsed


def _g4_5_guidance_lines() -> list[str]:
    return [
        "G4-5 业务模式分析问卷 编制说明",
        "",
        "否定筛查问卷：全「否」→ AC；「是」可能指向 FVOCI/FVTPL。",
        "回答列填「是」或「否」，留空表示未答。",
        "题2由子题2.1～2.3自动汇总，导入后前端重算。",
        "存储字段：conclusion（兼容旧 remark）。",
        "次级组合/审计评价等头信息在系统内填写，不在本表导入。",
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# G4-6 多sheet导出（部分一+部分二三步 → 4 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g4_6_workbook(
    section_rows: dict[str, list[dict]] | None = None,
    *,
    template_only: bool = False,
) -> Workbook:
    """G4-6 按八段产品表分 sheet 导出。"""
    wb = Workbook()
    wb.remove(wb.active)
    section_rows = section_rows or {}

    sections = [
        ("债券投资SPPI", _G4_6_BOND_HEADERS, _G4_6_BOND_KEYS),
        ("第一步-保本保收益", _G4_6_STEP1_HEADERS, _G4_6_STEP1_KEYS),
        ("第二步-浮动收益不现实", _G4_6_STEP2_HEADERS, _G4_6_STEP2_KEYS),
        ("第三步-穿透底层资产", _G4_6_STEP3_HEADERS, _G4_6_STEP3_KEYS),
        ("优先股永续债", _G4_6_PREFERRED_HEADERS, _G4_6_PREFERRED_KEYS),
        ("可转换债券", _G4_6_CONVERTIBLE_HEADERS, _G4_6_CONVERTIBLE_KEYS),
        ("项目收益债信托", _G4_6_PROJECT_HEADERS, _G4_6_PROJECT_KEYS),
        ("资产支持证券", _G4_6_ABS_HEADERS, _G4_6_ABS_KEYS),
    ]
    for sec_name, sec_headers, sec_keys in sections:
        ws = wb.create_sheet(title=sec_name)
        ws.append([f"G4-6 合同现金流量特征分析 — {sec_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(sec_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(sec_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(sec_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14

        if not template_only:
            for row_data in section_rows.get(sec_name, []):
                ws.append(_export_row_bool_aware(row_data, sec_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G4-6 合同现金流量特征分析 编制说明"])
    ws_guide.append([])
    for line in [
        "部分(一)：债券投资/委托贷款 SPPI（含偿付顺序）。",
        "部分(二)：银行理财三步（保本保收益/浮动收益不现实/穿透底层）。",
        "部分(三)～(六)：优先股永续债 / 可转债 / 项目收益债信托 / ABS。",
        '布尔列填"是"或"否"。',
        "结论列填：PASS / FAIL / FURTHER_ANALYSIS（也可写「通过SPPI测试」等中文）。",
        "分析项目填：simple/floating_rate/rate_adjustment/prepayment/extension/non_recourse/linked_instrument。",
        "导入时按 sheet 名写回对应存储键。",
    ]:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g4_6_import(content: bytes) -> tuple[dict[str, list[dict]], list[str]]:
    """解析 G4-6 各产品段 sheet，返回 {section_name: rows}。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    result: dict[str, list[dict]] = {}

    sections = [
        ("债券投资SPPI", _G4_6_BOND_HEADERS, _G4_6_BOND_KEYS, ("债券投资", "部分一", "SPPI")),
        ("第一步-保本保收益", _G4_6_STEP1_HEADERS, _G4_6_STEP1_KEYS, ("第一步", "保本保收益")),
        ("第二步-浮动收益不现实", _G4_6_STEP2_HEADERS, _G4_6_STEP2_KEYS, ("第二步", "浮动收益")),
        ("第三步-穿透底层资产", _G4_6_STEP3_HEADERS, _G4_6_STEP3_KEYS, ("第三步", "穿透")),
        ("优先股永续债", _G4_6_PREFERRED_HEADERS, _G4_6_PREFERRED_KEYS, ("优先股", "永续债")),
        ("可转换债券", _G4_6_CONVERTIBLE_HEADERS, _G4_6_CONVERTIBLE_KEYS, ("可转换", "可转债")),
        ("项目收益债信托", _G4_6_PROJECT_HEADERS, _G4_6_PROJECT_KEYS, ("项目收益", "信托计划")),
        ("资产支持证券", _G4_6_ABS_HEADERS, _G4_6_ABS_KEYS, ("资产支持", "ABS")),
    ]

    for sec_name, sec_headers, sec_keys, aliases in sections:
        matched = _match_sheet_name(list(wb.sheetnames), sec_name, *aliases)
        if matched is None:
            # 债券段缺失视为错误；其余段可缺省
            if sec_name == "债券投资SPPI":
                errors.append(f"缺少工作表: {sec_name}")
            result[sec_name] = []
            continue

        ws = wb[matched]
        header_row_idx = 2
        actual_raw = [
            str(c.value).strip() if c.value else ""
            for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        ]
        actual = [_normalize_header(h) for h in actual_raw]
        # 允许旧表头经 alias 归一
        missing = [h for h in sec_headers if h not in actual]
        if missing and sec_name == "债券投资SPPI":
            if "投资项目" not in actual_raw and "投资项目" not in actual:
                errors.append(f"工作表[{matched}]缺少列: {', '.join(missing)}")
                result[sec_name] = []
                continue

        bool_keys = _bool_fields_for_keys(sec_keys)
        rows: list[dict] = []
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append(f"{sec_name}: 数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_raw) - len(row))
            # map by header name
            header_to_idx = { _normalize_header(h): i for i, h in enumerate(actual_raw) if h }
            # also keep raw headers
            for i, h in enumerate(actual_raw):
                if h and h not in header_to_idx:
                    header_to_idx[h] = i

            for key, header in zip(sec_keys, sec_headers):
                col_i = header_to_idx.get(header)
                if col_i is None:
                    # try reverse alias
                    for old, new in _G4_6_BOND_HEADER_ALIASES.items():
                        if new == header and old in header_to_idx:
                            col_i = header_to_idx[old]
                            break
                raw = values[col_i] if col_i is not None and col_i < len(values) else None
                if key in bool_keys:
                    parsed[key] = _str_to_bool(raw)
                elif is_numeric_field_key(key):
                    parsed[key] = safe_float(raw)
                else:
                    parsed[key] = safe_str(raw)
            rows.append(parsed)
        result[sec_name] = rows

    wb.close()
    return result, errors

# ═══════════════════════════════════════════════════════════════════════════════
# G4-8 多sheet导出（3区段 → 3 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g4_8_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G4-8 按3区段分sheet导出。"""
    wb = Workbook()
    wb.remove(wb.active)

    for seg_name, seg_headers, seg_keys in _G4_8_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        ws.append([f"G4-8 盘点倒轧表 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14

        if not template_only:
            for row_data in rows:
                ws.append(export_row_by_keys(row_data, seg_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G4-8 盘点倒轧表 编制说明"])
    ws_guide.append([])
    for line in [
        "3区段：盘点日实存 / 资产负债表日→盘点日增减（增加·减少拆分） / 报表日实存+账面差异。",
        "公式列（总计/报表日数量/报表日总计/差异）导入后前端自动重算。",
        "总计 = 面值 × 数量。",
        "报表日数量 = 盘点日数量 − 增加数量 + 减少数量（增减口径：资产负债表日→盘点日）。",
        "报表日总计 = 报表日面值 × 报表日数量。",
        "差异·数量 = 报表日数量 − 账面数量；差异·面值 = 报表日总计 − 账面总计。",
        "票面利率/到期日以盘点日为准；账面摊余成本为参照列，便于与债权投资账面价值勾对。",
        "增减须填写证据索引（交割单/对账单等）。差异非零时备注必填。",
        "兼容旧模板列名：增减数量/增减面值总额/差异。",
    ]:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _g4_8_header_to_key(header: str) -> str | None:
    """将表头映射到字段 key，兼容新旧列名。"""
    h = (header or "").strip()
    if not h:
        return None
    if h in _G4_8_ALL_HEADERS:
        return _G4_8_ALL_KEYS[_G4_8_ALL_HEADERS.index(h)]
    if h in _G4_8_HEADER_ALIASES:
        return _G4_8_HEADER_ALIASES[h]
    # 区段内重复“证券名称”一律映射
    if h == "证券名称":
        return "securitiesName"
    return None


def _parse_g4_8_sheet_rows(
    ws,
    header_row_idx: int,
    rows_dict: dict[int, dict],
) -> list[str]:
    """按表头名解析工作表行，写入 rows_dict（按行号合并多区段）。"""
    errors: list[str] = []
    actual_headers = [
        str(c.value).strip() if c.value else ""
        for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
    ]
    if not any(_g4_8_header_to_key(h) for h in actual_headers):
        errors.append(f"工作表[{getattr(ws, 'title', '')}]无法识别表头列")
        return errors

    for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
        if all(v is None for v in row):
            continue
        if row_idx >= ROW_LIMIT:
            errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
            break
        if row_idx not in rows_dict:
            rows_dict[row_idx] = {"id": str(uuid4()), "seq": row_idx + 1}
        values = list(row) + [None] * max(0, len(actual_headers) - len(row))
        for col_i, h in enumerate(actual_headers):
            key = _g4_8_header_to_key(h)
            if not key:
                continue
            raw = values[col_i] if col_i < len(values) else None
            if is_numeric_field_key(key):
                rows_dict[row_idx][key] = safe_float(raw)
            else:
                rows_dict[row_idx][key] = safe_str(raw)
    return errors


def _parse_g4_8_import(content: bytes) -> tuple[list[dict], list[str]]:
    """解析G4-8导入文件，支持多sheet或单sheet；兼容新旧表头。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    rows_dict: dict[int, dict] = {}

    multi_sheet = len(wb.sheetnames) >= 3 and any(
        ("盘点日实存" in s) for s in wb.sheetnames
    )

    if multi_sheet:
        for seg_name, _seg_headers, _seg_keys in _G4_8_SEGMENTS:
            alias_cand = [seg_name] + [k for k, v in _G4_8_SEG_ALIASES.items() if v == seg_name]
            matched = _match_sheet_name(list(wb.sheetnames), *alias_cand)
            if matched is None:
                errors.append(f"缺少工作表: {seg_name}")
                continue
            ws = wb[matched]
            errors.extend(_parse_g4_8_sheet_rows(ws, 2, rows_dict))
    else:
        ws = wb.active
        if ws is None:
            wb.close()
            return [], ["xlsx文件中无活动工作表"]
        header_row_idx = 1
        for r in range(1, 5):
            test_row = [
                str(c.value).strip() if c.value else ""
                for c in next(ws.iter_rows(min_row=r, max_row=r))
            ]
            if "证券名称" in test_row:
                header_row_idx = r
                break
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        ]
        if "证券名称" not in actual_headers:
            errors.append("无法识别表头，缺少'证券名称'列")
            wb.close()
            return [], errors
        errors.extend(_parse_g4_8_sheet_rows(ws, header_row_idx, rows_dict))

    wb.close()
    result = list(rows_dict.values())
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
    return result, errors


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g4-sppi/export-template")
async def g4_sppi_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)

    if sheet == "G4-5":
        wb = build_workbook_template(
            "G4-5",
            _G4_5_HEADERS,
            title="G4-5 业务模式分析问卷",
            guidance=_g4_5_guidance_lines(),
        )
        ws = wb["G4-5"]
        for d in _G4_5_DEFAULT_ROWS:
            ws.append(_export_g4_5_row(d))
        return workbook_to_response(wb, "G4-5_业务模式分析问卷_模板.xlsx")
    elif sheet == "G4-6":
        wb = _build_g4_6_workbook(None, template_only=True)
        return workbook_to_response(wb, "G4-6_合同现金流量特征分析_模板.xlsx")
    elif sheet == "G4-7":
        wb = build_workbook_template(
            "G4-7",
            _G4_7_HEADERS,
            title="G4-7 有价证券盘点表",
            guidance=[
                "G4-7 有价证券盘点表 编制说明",
                "",
                "逐行记录实际盘点到的有价证券（证券名称/面值/数量/票面利率/到期日）。",
                "总计 = 面值 × 数量（导入后前端自动重算）。",
                "利率以百分数填写（如 5.25 表示 5.25%）。",
                "到期日格式：YYYY-MM-DD。",
                "盘点单位/日期/地点/人员等头信息在系统内「盘点信息」弹窗填写，不在本表导入。",
                "盘点应与现金同时进行；多地点应同时盘点；盘点日≠报表日须衔接 G4-8 倒轧表。",
            ],
        )
        return workbook_to_response(wb, "G4-7_有价证券盘点表_模板.xlsx")
    else:  # G4-8
        wb = _build_g4_8_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G4-8_盘点倒轧表_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g4-sppi/export-data")
async def g4_sppi_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)

    if sheet == "G4-5":
        rows = await _load_g4_5_rows(db, wp_id)
        wb = build_workbook_template(
            "G4-5",
            _G4_5_HEADERS,
            title="G4-5 业务模式分析问卷",
            guidance=_g4_5_guidance_lines(),
        )
        ws = wb["G4-5"]
        for d in rows:
            ws.append(_export_g4_5_row(d))
        return workbook_to_response(wb, "G4-5_业务模式分析问卷_数据.xlsx")
    elif sheet == "G4-6":
        section_rows: dict[str, list[dict]] = {}
        for sec_name, item_key in _G4_6_SECTION_ITEM_IDS.items():
            section_rows[sec_name] = await _load_canonical_rows(db, wp_id, item_key)
        wb = _build_g4_6_workbook(section_rows, template_only=False)
        return workbook_to_response(wb, "G4-6_合同现金流量特征分析_数据.xlsx")

    item_id = _ITEM_IDS[sheet]
    rows = await _load_canonical_rows(db, wp_id, item_id)

    if sheet == "G4-7":
        wb = build_workbook_template(
            "G4-7",
            _G4_7_HEADERS,
            title="G4-7 有价证券盘点表",
            guidance=["逐行记录实际盘点到的有价证券。总计=面值×数量。"],
        )
        ws = wb["G4-7"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G4_7_KEYS))
        return workbook_to_response(wb, "G4-7_有价证券盘点表_数据.xlsx")
    else:  # G4-8
        wb = _build_g4_8_multi_sheet_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G4-8_盘点倒轧表_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g4-sppi/import-data")
async def g4_sppi_import_data(
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

    errors: list[str] = []

    if sheet == "G4-5":
        try:
            actual, raw = parse_upload_xlsx(content, _G4_5_HEADERS, header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        rows: list[dict] = []
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            rows.append(_parse_g4_5_row(r, actual))
        if errors and not rows:
            return {"ok": False, "errors": errors, "imported_count": 0}
        await _upsert_dual_rows(db, wp_id, _ITEM_IDS["G4-5"], rows)
        out = {"ok": True, "imported_count": len(rows), "errors": errors}
        if len(rows) >= ROW_LIMIT:
            out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
        return out

    if sheet == "G4-6":
        section_rows, errors = _parse_g4_6_import(content)
        bond_rows = section_rows.get("债券投资SPPI", [])
        if errors and not bond_rows and not any(section_rows.values()):
            return {"ok": False, "errors": errors, "imported_count": 0}

        total = 0
        for sec_name, item_key in _G4_6_SECTION_ITEM_IDS.items():
            sec_data = section_rows.get(sec_name, [])
            if sec_data or sec_name == "债券投资SPPI":
                await _upsert_dual_rows(db, wp_id, item_key, sec_data)
                total += len(sec_data)

        out: dict[str, Any] = {
            "ok": True,
            "imported_count": total,
            "errors": errors,
            "sections": {k: len(v) for k, v in section_rows.items()},
        }
        return out

    item_id = _ITEM_IDS[sheet]
    rows: list[dict] = []

    if sheet == "G4-7":
        try:
            actual, raw = parse_upload_xlsx(content, _G4_7_HEADERS, header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            rows.append(parse_row_by_headers(r, actual, _G4_7_KEYS))
    else:  # G4-8
        rows, errors = _parse_g4_8_import(content)

    if errors and not rows:
        return {"ok": False, "errors": errors, "imported_count": 0}

    await _upsert_dual_rows(db, wp_id, item_id, rows)
    out = {"ok": True, "imported_count": len(rows), "errors": errors}
    if len(rows) >= ROW_LIMIT:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out