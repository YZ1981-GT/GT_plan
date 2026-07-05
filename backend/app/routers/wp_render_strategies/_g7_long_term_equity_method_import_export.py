"""G7 长期股权投资(权益法组) — 导入导出（7张表×3端点=21端点）.

支持 7 张动态行表格：
  G7-4 基本信息(25列→2sheet) / G7-5 财务信息(10列) / G7-13 投资成本测试(17列→2sheet)
  G7-14 权益法测算(20列→2sheet) / G7-15 内部交易(14列) / G7-16 未确认损失(17列→2sheet)
  G7-17 减值测试(9列)

宽表按区段分sheet导出：G7-4(2) / G7-13(2) / G7-14(2) / G7-16(2)。
字段键与前端 composable 严格对齐，保证 round-trip。
"""

from __future__ import annotations

import io
import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote

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

router = APIRouter(tags=["g7-equity-method-import-export"])


# ═══════════════════════════════════════════════════════════════════════════════
# G7-4 被投资单位基本信息（25列→2区段Tab）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 工商信息(12列)
_G7_4_SEG1_HEADERS = [
    "被投资单位名称", "统一社会信用代码", "成立日期", "注册资本",
    "实缴资本", "注册地", "行业", "主营业务",
    "法定代表人", "控制类型", "持股比例(%)", "投票权比例(%)",
]
_G7_4_SEG1_KEYS = [
    "investeeName", "creditCode", "establishDate", "registeredCapital",
    "paidInCapital", "registeredAddress", "industry", "mainBusiness",
    "legalRepresentative", "controlType", "investmentRatio", "votingRatio",
]

# 区段2: 股权结构+管理层(13列)
_G7_4_SEG2_HEADERS = [
    "被投资单位名称", "其他股东名称", "其他股东持股(%)", "董事会席位",
    "派出董事", "是否有否决权", "是否参与决策", "重大影响判断依据",
    "管理层组成", "最新审计报告日", "审计意见类型", "关联关系", "备注",
]
_G7_4_SEG2_KEYS = [
    "investeeName", "otherShareholderName", "otherShareholderRatio", "boardSeats",
    "appointedDirectors", "hasVeto", "participatesInDecision", "significantInfluenceBasis",
    "managementComposition", "latestAuditReportDate", "auditOpinionType", "relatedPartyRelation", "remark",
]

# 全部列合并（用于单sheet宽表导入）
_G7_4_ALL_HEADERS = _G7_4_SEG1_HEADERS + _G7_4_SEG2_HEADERS[1:]  # 去掉重复的"被投资单位名称"
_G7_4_ALL_KEYS = _G7_4_SEG1_KEYS + _G7_4_SEG2_KEYS[1:]

_G7_4_SEGMENTS = [
    ("工商信息", _G7_4_SEG1_HEADERS, _G7_4_SEG1_KEYS),
    ("股权结构+管理层", _G7_4_SEG2_HEADERS, _G7_4_SEG2_KEYS),
]


# ═══════════════════════════════════════════════════════════════════════════════
# G7-5 被投资单位财务信息（10列，单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_5_HEADERS = [
    "被投资单位", "报表项目", "上年金额", "本年金额",
    "变动额", "变动率(%)", "分析说明", "数据来源",
    "审计状态", "备注",
]
_G7_5_KEYS = [
    "investeeName", "reportItem", "priorAmount", "currentAmount",
    "changeAmount", "changeRate", "analysisNote", "dataSource",
    "auditStatus", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G7-13 投资成本测试（17列→2区段Tab）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 初始计量(9列)
_G7_13_SEG1_HEADERS = [
    "被投资单位名称", "投资日期", "合并/非合并", "支付对价",
    "直接相关费用", "初始投资成本", "被投资方可辨认净资产公允价值",
    "享有份额", "差额",
]
_G7_13_SEG1_KEYS = [
    "investeeName", "investDate", "mergeType", "consideration",
    "directCosts", "initialCost", "netAssetFairValue",
    "shareOfNetAssets", "difference",
]

# 区段2: 商誉计算+调整(8列)
_G7_13_SEG2_HEADERS = [
    "被投资单位名称", "差额性质", "会计处理", "公允价值调整明细",
    "调整后净资产", "调整后享有份额", "审计结论", "索引",
]
_G7_13_SEG2_KEYS = [
    "investeeName", "differenceNature", "accountingTreatment", "fvAdjustmentDetail",
    "adjustedNetAssets", "adjustedShareOfNetAssets", "auditConclusion", "indexRef",
]

_G7_13_ALL_HEADERS = _G7_13_SEG1_HEADERS + _G7_13_SEG2_HEADERS[1:]
_G7_13_ALL_KEYS = _G7_13_SEG1_KEYS + _G7_13_SEG2_KEYS[1:]

_G7_13_SEGMENTS = [
    ("初始计量", _G7_13_SEG1_HEADERS, _G7_13_SEG1_KEYS),
    ("商誉计算", _G7_13_SEG2_HEADERS, _G7_13_SEG2_KEYS),
]


# ═══════════════════════════════════════════════════════════════════════════════
# G7-14 权益法测算表（20列→2区段Tab，★最核心★）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 净利润调整(10列)
_G7_14_SEG1_HEADERS = [
    "被投资单位", "被投资方报告净利润", "内部交易抵销", "公允价值折旧摊销",
    "会计政策调整", "其他调整", "调整后净利润", "持股比例(%)",
    "应享有份额", "企业确认投资收益",
]
_G7_14_SEG1_KEYS = [
    "investeeName", "reportedNetProfit", "internalTransactionAdj", "fvDepreciationAdj",
    "accountingPolicyAdj", "otherAdj", "adjustedNetProfit", "investmentRatio",
    "equityShare", "confirmedIncome",
]

# 区段2: 权益法计算(10列)
_G7_14_SEG2_HEADERS = [
    "被投资单位", "投资收益差异", "其他综合收益变动", "享有OCI",
    "其他权益变动", "享有其他权益", "利润分配(股利)",
    "期初权益法余额", "期末权益法余额", "审计结论",
]
_G7_14_SEG2_KEYS = [
    "investeeName", "incomeDifference", "ociChange", "ociShare",
    "otherEquityChange", "otherEquityShare", "dividendDistributed",
    "openingBalance", "closingBalance", "auditConclusion",
]

_G7_14_ALL_HEADERS = _G7_14_SEG1_HEADERS + _G7_14_SEG2_HEADERS[1:]
_G7_14_ALL_KEYS = _G7_14_SEG1_KEYS + _G7_14_SEG2_KEYS[1:]

_G7_14_SEGMENTS = [
    ("净利润调整", _G7_14_SEG1_HEADERS, _G7_14_SEG1_KEYS),
    ("权益法计算", _G7_14_SEG2_HEADERS, _G7_14_SEG2_KEYS),
]


# ═══════════════════════════════════════════════════════════════════════════════
# G7-15 内部交易抵销测算表（14列，单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_15_HEADERS = [
    "被投资单位", "交易类型", "交易内容", "交易金额",
    "未实现利润", "持股比例(%)", "应抵销金额", "上年抵销",
    "本年变动", "抵销分录", "是否关联交易", "审计结论",
    "索引", "备注",
]
_G7_15_KEYS = [
    "investeeName", "transactionType", "transactionContent", "transactionAmount",
    "unrealizedProfit", "investmentRatio", "eliminationAmount", "priorElimination",
    "currentChange", "eliminationEntry", "isRelatedParty", "auditConclusion",
    "indexRef", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G7-16 未确认投资损失（17列→2区段Tab）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 长期权益分析(9列)
_G7_16_SEG1_HEADERS = [
    "被投资单位", "投资账面", "长期应收款", "其他实质长期权益",
    "预计负债", "合计长期权益", "累计亏损", "超额亏损", "分配顺序说明",
]
_G7_16_SEG1_KEYS = [
    "investeeName", "investmentBookValue", "longTermReceivable", "otherLongTermEquity",
    "estimatedLiability", "totalLongTermEquity", "cumulativeLoss", "excessLoss", "allocationOrder",
]

# 区段2: 超额亏损分配(8列)
_G7_16_SEG2_HEADERS = [
    "被投资单位", "冲减投资", "冲减长应收", "冲减其他权益",
    "确认预计负债", "未确认损失", "本期变动", "审计结论",
]
_G7_16_SEG2_KEYS = [
    "investeeName", "reduceInvestment", "reduceLongTermReceivable", "reduceOtherEquity",
    "recognizeEstimatedLiability", "unrecognizedLoss", "currentChange", "auditConclusion",
]

_G7_16_ALL_HEADERS = _G7_16_SEG1_HEADERS + _G7_16_SEG2_HEADERS[1:]
_G7_16_ALL_KEYS = _G7_16_SEG1_KEYS + _G7_16_SEG2_KEYS[1:]

_G7_16_SEGMENTS = [
    ("长期权益分析", _G7_16_SEG1_HEADERS, _G7_16_SEG1_KEYS),
    ("超额亏损分配", _G7_16_SEG2_HEADERS, _G7_16_SEG2_KEYS),
]


# ═══════════════════════════════════════════════════════════════════════════════
# G7-17 减值测试（9列，单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_17_HEADERS = [
    "被投资单位", "账面价值", "可收回金额", "减值迹象",
    "减值金额", "公允价值-处置费用", "使用价值", "审计结论", "索引",
]
_G7_17_KEYS = [
    "investeeName", "bookValue", "recoverableAmount", "hasImpairmentSign",
    "impairmentAmount", "fvLessDisposalCost", "valueInUse", "auditConclusion", "indexRef",
]

# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G7-4": "G7-4-rows",
    "G7-5": "G7-5-rows",
    "G7-13": "G7-13-rows",
    "G7-14": "G7-14-rows",
    "G7-15": "G7-15-rows",
    "G7-16": "G7-16-rows",
    "G7-17": "G7-17-rows",
}

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


# ═══════════════════════════════════════════════════════════════════════════════
# 权益法组数值字段判断（补充 _cycle_import_export_common 未覆盖的 keys）
# ═══════════════════════════════════════════════════════════════════════════════

_EQUITY_METHOD_NUMERIC_KEYS = {
    # G7-4
    "registeredCapital", "paidInCapital", "investmentRatio", "votingRatio",
    "otherShareholderRatio", "boardSeats", "appointedDirectors",
    # G7-5
    "priorAmount", "currentAmount", "changeAmount", "changeRate",
    # G7-13
    "consideration", "directCosts", "initialCost", "netAssetFairValue",
    "shareOfNetAssets", "difference", "adjustedNetAssets", "adjustedShareOfNetAssets",
    # G7-14
    "reportedNetProfit", "internalTransactionAdj", "fvDepreciationAdj",
    "accountingPolicyAdj", "otherAdj", "adjustedNetProfit", "investmentRatio",
    "equityShare", "confirmedIncome", "incomeDifference", "ociChange",
    "ociShare", "otherEquityChange", "otherEquityShare", "dividendDistributed",
    "openingBalance", "closingBalance",
    # G7-15
    "transactionAmount", "unrealizedProfit", "eliminationAmount",
    "priorElimination", "currentChange",
    # G7-16
    "investmentBookValue", "longTermReceivable", "otherLongTermEquity",
    "estimatedLiability", "totalLongTermEquity", "cumulativeLoss", "excessLoss",
    "reduceInvestment", "reduceLongTermReceivable", "reduceOtherEquity",
    "recognizeEstimatedLiability", "unrecognizedLoss",
    # G7-17
    "bookValue", "recoverableAmount", "impairmentAmount",
    "fvLessDisposalCost", "valueInUse",
}


def _is_numeric(key: str) -> bool:
    """判断字段是否为数值类型（先查本地集合，再 fallback 通用规则）。"""
    if key in _EQUITY_METHOD_NUMERIC_KEYS:
        return True
    return is_numeric_field_key(key)


# ═══════════════════════════════════════════════════════════════════════════════
# 多sheet导出通用构建器（宽表→多worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_multi_sheet_workbook(
    sheet_code: str,
    segments: list[tuple[str, list[str], list[str]]],
    rows: list[dict],
    *,
    template_only: bool = False,
    guidance_lines: list[str] | None = None,
) -> Workbook:
    """通用：按区段分sheet导出，每个区段一个worksheet。"""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    for seg_name, seg_headers, seg_keys in segments:
        ws = wb.create_sheet(title=seg_name)
        # 标题行
        ws.append([f"{sheet_code} — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        # 表头行
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14

        if not template_only:
            for row_data in rows:
                ws.append(export_row_by_keys(row_data, seg_keys))

    # 编制说明
    if guidance_lines:
        ws_guide = wb.create_sheet("编制说明")
        ws_guide.append([f"{sheet_code} 编制说明"])
        ws_guide.append([])
        for line in guidance_lines:
            ws_guide.append([line])
        ws_guide.column_dimensions["A"].width = 80

    return wb


# ═══════════════════════════════════════════════════════════════════════════════
# 多sheet导入解析通用（支持多sheet或单sheet宽表两种格式）
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_multi_sheet_import(
    content: bytes,
    segments: list[tuple[str, list[str], list[str]]],
    all_headers: list[str],
    all_keys: list[str],
    identifier_header: str = "被投资单位名称",
) -> tuple[list[dict], list[str]]:
    """解析多sheet或单sheet宽表导入文件。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet格式
    seg_names = [s[0] for s in segments]
    multi_sheet = len(wb.sheetnames) >= len(segments) and any(
        seg_names[0] in s for s in wb.sheetnames
    )

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in segments:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append(f"缺少工作表: {seg_name}")
                continue
            header_row_idx = 2
            actual_headers = [
                str(c.value).strip() if c.value else ""
                for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
            ]
            missing = [h for h in seg_headers if h not in actual_headers]
            if missing:
                errors.append(f"工作表[{seg_name}]缺少列: {', '.join(missing)}")
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                if row_idx >= ROW_LIMIT:
                    errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                    break
                if row_idx not in rows_dict:
                    rows_dict[row_idx] = {"id": str(uuid4())}
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                for col_i, key in enumerate(seg_keys):
                    raw = values[col_i] if col_i < len(values) else None
                    if _is_numeric(key):
                        rows_dict[row_idx][key] = safe_float(raw)
                    else:
                        rows_dict[row_idx][key] = safe_str(raw)
    else:
        # 策略2: 单sheet宽表
        ws = wb.active
        if ws is None:
            wb.close()
            return [], ["xlsx文件中无活动工作表"]
        header_row_idx = 1
        for r in range(1, 5):
            test_row = [str(c.value).strip() if c.value else "" for c in next(ws.iter_rows(min_row=r, max_row=r))]
            if identifier_header in test_row:
                header_row_idx = r
                break
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        ]
        if identifier_header not in actual_headers:
            errors.append(f"无法识别表头，缺少'{identifier_header}'列")
            wb.close()
            return [], errors
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in all_headers:
                    key_idx = all_headers.index(h)
                    key = all_keys[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if _is_numeric(key):
                        parsed[key] = safe_float(raw)
                    else:
                        parsed[key] = safe_str(raw)
            rows_dict[row_idx] = parsed

    wb.close()
    result = list(rows_dict.values())
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
    return result, errors


# ═══════════════════════════════════════════════════════════════════════════════
# 编制说明
# ═══════════════════════════════════════════════════════════════════════════════

_G7_4_GUIDANCE = [
    "G7-4 被投资单位基本信息",
    "",
    "25列拆为2区段Tab：工商信息(12列) / 股权结构+管理层(13列)。",
    "控制类型填：子公司 / 合营 / 联营。",
    "持股比例/投票权比例以百分数填写（如 30.00 表示 30%）。",
    "是否有否决权/是否参与决策填：是 / 否。",
]

_G7_5_GUIDANCE = [
    "G7-5 被投资单位财务信息",
    "",
    "10列：被投资单位/报表项目/上年金额/本年金额/变动额/变动率/分析说明/数据来源/审计状态/备注。",
    "变动额 = 本年金额 - 上年金额（公式列，导入后前端自动重算）。",
    "变动率 = 变动额 / 上年金额 × 100%（上年=0时显示N/A）。",
    "审计状态填：已审 / 未审 / 待确认。",
    "按被投资单位分组，组内含资产/负债/净资产/收入/利润等关键指标。",
]

_G7_13_GUIDANCE = [
    "G7-13 合营联营企业投资成本测试表",
    "",
    "17列拆为2区段Tab：初始计量(9列) / 商誉计算+调整(8列)。",
    "初始投资成本 = 支付对价 + 直接相关费用（公式列）。",
    "享有份额 = 被投资方可辨认净资产公允价值 × 持股比例（公式列）。",
    "差额 = 初始投资成本 - 享有份额（正=商誉，负=营业外收入）。",
    "合并/非合并填：合并 / 非合并。",
    "审计结论填：无差异 / 存在差异-可接受 / 存在差异-需调整。",
]

_G7_14_GUIDANCE = [
    "G7-14 权益法测算表",
    "",
    "20列拆为2区段Tab：净利润调整(10列) / 权益法计算(10列)。",
    "调整后净利润 = 报告净利润 - 内部交易 - FV折旧 + 政策调整 + 其他调整（公式列）。",
    "应享有份额 = 调整后净利润 × 持股比例（公式列）。",
    "投资收益差异 = 应享有份额 - 企业确认投资收益（公式列）。",
    "享有OCI = OCI变动 × 持股比例（公式列）。",
    "享有其他权益 = 其他权益变动 × 持股比例（公式列）。",
    "期末余额 = 期初 + 投资收益 + OCI份额 + 其他权益份额 - 利润分配（公式列）。",
    "审计结论填：无差异 / 差异可接受 / 差异需调整。",
]

_G7_15_GUIDANCE = [
    "G7-15 权益法未实现内部交易抵销测算表",
    "",
    "14列，单sheet导出。",
    "顺流交易（投资方→被投资方）：应抵销 = 未实现利润（全额）。",
    "逆流交易（被投资方→投资方）：应抵销 = 未实现利润 × 持股比例。",
    "交易类型填：顺流 / 逆流。",
    "审计结论填：合理 / 基本合理 / 不合理。",
    "是否关联交易填：是 / 否。",
]

_G7_16_GUIDANCE = [
    "G7-16 未确认投资损失测试表",
    "",
    "17列拆为2区段Tab：长期权益分析(9列) / 超额亏损分配(8列)。",
    "合计长期权益 = 投资账面 + 长期应收款 + 其他实质长期权益 + 预计负债（公式列）。",
    "超额亏损 = MAX(0, 累计亏损 - 合计长期权益)（公式列）。",
    "超额亏损抵减顺序：①冲减投资 ②冲减长应收 ③冲减其他权益 ④确认预计负债。",
    "未确认损失 = 超额亏损 - 冲减投资 - 冲减长应收 - 冲减其他 - 确认预计负债（公式列）。",
    "审计结论填：合理 / 基本合理 / 不合理。",
]

_G7_17_GUIDANCE = [
    "G7-17 减值测试表",
    "",
    "9列，单sheet导出。",
    "可收回金额 = MAX(公允价值-处置费用, 使用价值)（审计员手动取高）。",
    "减值金额 = MAX(0, 账面价值 - 可收回金额)（公式列）。",
    "减值迹象填：是 / 否。",
    "审计结论填：无需计提 / 需计提 / 已充分计提。",
]


# ═══════════════════════════════════════════════════════════════════════════════
# 单sheet表配置（G7-5 / G7-15 / G7-17）
# ═══════════════════════════════════════════════════════════════════════════════

_SINGLE_SHEET_SPECS: dict[str, dict[str, Any]] = {
    "G7-5": {
        "headers": _G7_5_HEADERS,
        "field_keys": _G7_5_KEYS,
        "title": "G7-5 被投资单位财务信息",
        "guidance": _G7_5_GUIDANCE,
    },
    "G7-15": {
        "headers": _G7_15_HEADERS,
        "field_keys": _G7_15_KEYS,
        "title": "G7-15 内部交易抵销测算表",
        "guidance": _G7_15_GUIDANCE,
    },
    "G7-17": {
        "headers": _G7_17_HEADERS,
        "field_keys": _G7_17_KEYS,
        "title": "G7-17 减值测试表",
        "guidance": _G7_17_GUIDANCE,
    },
}

# 多sheet表配置（G7-4 / G7-13 / G7-14 / G7-16）
_MULTI_SHEET_SPECS: dict[str, dict[str, Any]] = {
    "G7-4": {
        "segments": _G7_4_SEGMENTS,
        "all_headers": _G7_4_ALL_HEADERS,
        "all_keys": _G7_4_ALL_KEYS,
        "guidance": _G7_4_GUIDANCE,
        "identifier_header": "被投资单位名称",
    },
    "G7-13": {
        "segments": _G7_13_SEGMENTS,
        "all_headers": _G7_13_ALL_HEADERS,
        "all_keys": _G7_13_ALL_KEYS,
        "guidance": _G7_13_GUIDANCE,
        "identifier_header": "被投资单位名称",
    },
    "G7-14": {
        "segments": _G7_14_SEGMENTS,
        "all_headers": _G7_14_ALL_HEADERS,
        "all_keys": _G7_14_ALL_KEYS,
        "guidance": _G7_14_GUIDANCE,
        "identifier_header": "被投资单位",
    },
    "G7-16": {
        "segments": _G7_16_SEGMENTS,
        "all_headers": _G7_16_ALL_HEADERS,
        "all_keys": _G7_16_ALL_KEYS,
        "guidance": _G7_16_GUIDANCE,
        "identifier_header": "被投资单位",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g7-equity-method/export-template")
async def g7_equity_method_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空模板：多sheet(G7-4/G7-13/G7-14/G7-16) / 单sheet(G7-5/G7-15/G7-17)。"""
    _validate_sheet(sheet)

    if sheet in _MULTI_SHEET_SPECS:
        spec = _MULTI_SHEET_SPECS[sheet]
        wb = _build_multi_sheet_workbook(
            sheet, spec["segments"], [], template_only=True, guidance_lines=spec["guidance"],
        )
        return workbook_to_response(wb, f"{sheet}_模板.xlsx")
    else:
        spec = _SINGLE_SHEET_SPECS[sheet]
        wb = build_workbook_template(
            sheet,
            spec["headers"],
            title=spec["title"],
            guidance=spec["guidance"],
        )
        return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g7-equity-method/export-data")
async def g7_equity_method_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出数据：多sheet含数据(G7-4/G7-13/G7-14/G7-16) / 单sheet含数据(G7-5/G7-15/G7-17)。"""
    _validate_sheet(sheet)
    item_id = _ITEM_IDS[sheet]
    rows = await load_json_rows(db, wp_id, item_id, field="conclusion")

    if sheet in _MULTI_SHEET_SPECS:
        spec = _MULTI_SHEET_SPECS[sheet]
        wb = _build_multi_sheet_workbook(
            sheet, spec["segments"], rows, template_only=False, guidance_lines=spec["guidance"],
        )
        return workbook_to_response(wb, f"{sheet}_数据.xlsx")
    else:
        spec = _SINGLE_SHEET_SPECS[sheet]
        wb = build_workbook_template(
            sheet,
            spec["headers"],
            title=spec["title"],
            guidance=spec["guidance"],
        )
        ws = wb[sheet]
        keys = spec["field_keys"]
        for d in rows:
            ws.append(export_row_by_keys(d, keys))
        return workbook_to_response(wb, f"{sheet}_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g7-equity-method/import-data")
async def g7_equity_method_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入数据：多sheet或宽表(G7-4/G7-13/G7-14/G7-16) / 单sheet(G7-5/G7-15/G7-17)。"""
    _validate_sheet(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    item_id = _ITEM_IDS[sheet]
    errors: list[str] = []
    rows: list[dict] = []

    if sheet in _MULTI_SHEET_SPECS:
        spec = _MULTI_SHEET_SPECS[sheet]
        rows, errors = _parse_multi_sheet_import(
            content,
            spec["segments"],
            spec["all_headers"],
            spec["all_keys"],
            identifier_header=spec["identifier_header"],
        )
    else:
        spec = _SINGLE_SHEET_SPECS[sheet]
        try:
            actual, raw = parse_upload_xlsx(content, spec["headers"], header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            keys = spec["field_keys"]
            values = list(r) + [None] * max(0, len(actual) - len(r))
            for col_i, key in enumerate(keys):
                if col_i < len(actual):
                    h = actual[col_i] if col_i < len(actual) else ""
                    raw_val = values[col_i] if col_i < len(values) else None
                else:
                    raw_val = None
                if _is_numeric(key):
                    parsed[key] = safe_float(raw_val)
                else:
                    parsed[key] = safe_str(raw_val)
            rows.append(parsed)

    if errors and not rows:
        return {"ok": False, "errors": errors, "imported_count": 0}

    await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
    if len(rows) >= ROW_LIMIT:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
