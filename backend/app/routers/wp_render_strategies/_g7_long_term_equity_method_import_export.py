"""G7 长期股权投资(权益法组) — 导入导出（含 G7-6 会计政策）.

支持动态行表格：
  G7-4 被投资单位基本信息(原底稿单sheet) / G7-5 财务信息(10列) / G7-6 会计政策(8列)
  G7-13 投资成本测试(17列→2sheet) / G7-14 权益法测算(主表3区段+净资产/商誉附表)
  G7-15 内部交易(17列) / G7-16 未确认损失(17列→2sheet) / G7-17 减值测试(9列)

宽表按区段分sheet导出：G7-13(2) / G7-14(2) / G7-16(2)。
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
from openpyxl.worksheet.datavalidation import DataValidation
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
    load_json_payload,
    load_json_rows,
    parse_row_by_headers,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_payload,
    upsert_json_rows,
    workbook_to_response,
)
from ._g7_long_term_equity_method_service import G7LongTermEquityMethodService

router = APIRouter(tags=["g7-equity-method-import-export"])


# ═══════════════════════════════════════════════════════════════════════════════
# G7-4 被投资单位基本信息（按原底稿A:T语义建模）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_4_HEADERS = [
    "投资关系", "公司名称", "被投资单位ID", "级次（国企适用）", "企业类型（国企适用）",
    "是否为本期新纳入合并范围的子公司（国企适用）", "主要经营地", "注册地", "业务性质",
    "注册资本", "投资额", "期末净资产", "本期净利润",
    "直接持股比例/享有份额(%)", "间接持股比例/享有份额(%)", "表决权比例(%)",
    "持股比例与表决权比例不一致的原因",
    "表决权比例不足半数但能形成控制的原因",
    "拥有半数以上表决权但未形成控制的原因",
    "取得方式", "会计处理方法",
]
_G7_4_KEYS = [
    "groupType", "investeeName", "id", "level", "enterpriseType",
    "newlyConsolidated", "principalPlace", "registeredPlace", "businessNature",
    "registeredCapital", "investmentAmount", "endingNetAssets", "currentNetProfit",
    "directHoldingRatio", "indirectHoldingRatio", "votingRatio",
    "holdingVotingDifferenceReason", "lessThanHalfControlReason",
    "majorityNoControlReason", "acquisitionMethod", "accountingMethod",
]
_G7_4_CORE_HEADERS = [
    "投资关系", "公司名称", "级次（国企适用）", "企业类型（国企适用）",
    "是否为本期新纳入合并范围的子公司（国企适用）", "主要经营地", "注册地", "业务性质",
    "注册资本", "投资额", "期末净资产", "本期净利润",
    "直接持股比例/享有份额(%)", "间接持股比例/享有份额(%)", "表决权比例(%)",
    "持股比例与表决权比例不一致的原因",
    "表决权比例不足半数但能形成控制的原因",
    "拥有半数以上表决权但未形成控制的原因",
    "取得方式", "会计处理方法",
]
_G7_4_OPTIONAL_HEADERS = ("被投资单位ID",)
_G7_4_HEADER_ALIASES = {
    "被投资单位ID": ["id", "investeeId", "被投资单位Id", "行ID"],
}

_G7_4_GROUP_LABELS = {
    "subsidiary": "子公司",
    "joint_venture": "合营企业（共同控制）",
    "associate": "联营企业（重大影响）",
    "joint_operation": "共同经营（共同控制）",
}
_G7_4_GROUP_ALIASES = {
    **{key: key for key in _G7_4_GROUP_LABELS},
    **{label: key for key, label in _G7_4_GROUP_LABELS.items()},
    "合营企业": "joint_venture",
    "联营企业": "associate",
    "共同经营": "joint_operation",
}
_G7_4_ACCOUNTING_METHODS = {
    "subsidiary": "成本法",
    "joint_venture": "权益法",
    "associate": "权益法",
    "joint_operation": "各项单独确认",
}


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
# G7-6 被投资公司会计政策（扁平多行；导入后重建 groups）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_6_HEADERS = [
    "被投资单位", "被投资单位ID", "会计政策事项", "被投资方政策", "投资方政策",
    "是否一致", "调整金额", "调整说明",
]
_G7_6_KEYS = [
    "investeeName", "investeeId", "policyItem", "investeePolicy", "investorPolicy",
    "isConsistent", "adjustmentAmount", "adjustmentNote",
]
_G7_6_GUIDANCE = [
    "1. 每个被投资单位可多行事项；「是否一致」填：一致 / 不一致 / 不适用。",
    "2. 仅「不一致」行的调整金额会同步至 G7-14「会计政策调整」。",
    "3. 公允价值/可辨认净资产调整属 G7-13，勿写入本表。",
    "4. 导入后按「被投资单位」重建分组；空被投资单位行将被忽略。",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G7-13 投资成本测试（17列→2区段Tab）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 初始计量（含 ID / 持股比例，与前端行内 investmentRatio 对齐）
_G7_13_SEG1_HEADERS = [
    "被投资单位名称", "被投资单位ID", "持股比例(%)", "投资日期", "合并/非合并", "支付对价",
    "直接相关费用", "初始投资成本", "被投资方可辨认净资产公允价值",
    "享有份额", "差额",
]
_G7_13_SEG1_KEYS = [
    "investeeName", "investeeId", "investmentRatio", "investDate", "mergeType", "consideration",
    "directCosts", "initialCost", "netAssetFairValue",
    "shareOfNetAssets", "difference",
]

# 区段2: 商誉计算+调整
_G7_13_SEG2_HEADERS = [
    "被投资单位名称", "被投资单位ID", "差额性质", "会计处理", "公允价值调整明细",
    "调整后净资产", "调整后享有份额", "审计结论", "索引",
]
_G7_13_SEG2_KEYS = [
    "investeeName", "investeeId", "differenceNature", "accountingTreatment", "fvAdjustmentDetail",
    "adjustedNetAssets", "adjustedShareOfNetAssets", "auditConclusion", "indexRef",
]

_G7_13_ALL_HEADERS = _G7_13_SEG1_HEADERS + _G7_13_SEG2_HEADERS[1:]
_G7_13_ALL_KEYS = _G7_13_SEG1_KEYS + _G7_13_SEG2_KEYS[1:]

_G7_13_SEGMENTS = [
    ("初始计量", _G7_13_SEG1_HEADERS, _G7_13_SEG1_KEYS),
    ("商誉计算", _G7_13_SEG2_HEADERS, _G7_13_SEG2_KEYS),
]


# ═══════════════════════════════════════════════════════════════════════════════
# G7-14 权益法测算表（对齐原底稿三段：本期调整 / 期末余额 / 差额拆解）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 本期权益法调整
_G7_14_SEG1_HEADERS = [
    "被投资单位", "被投资单位ID", "被投资方报告净利润", "内部交易抵销", "公允价值折旧摊销",
    "会计政策调整", "其他调整", "调整后净利润", "持股比例(%)",
    "测算投资收益", "账面确认投资收益", "已宣告股利", "投资收益差异",
]
_G7_14_SEG1_KEYS = [
    "investeeName", "investeeId", "reportedNetProfit", "internalTransactionAdj", "fvDepreciationAdj",
    "accountingPolicyAdj", "otherAdj", "adjustedNetProfit", "investmentRatio",
    "equityShare", "confirmedIncome", "dividendDistributed", "incomeDifference",
]

# 区段2: 期末余额审核
_G7_14_SEG2_HEADERS = [
    "被投资单位", "被投资单位ID", "成本期初", "成本增减", "成本期末",
    "损益调整期初", "损益调整增减", "损益调整期末",
    "OCI期初", "其他权益期初", "经审计净资产",
    "应享净资产", "长投账面余额", "与享有净资产差额",
    "G7-2期初总额", "期初勾稽差异", "G7-2期末总额", "期末勾稽差异",
]
_G7_14_SEG2_KEYS = [
    "investeeName", "investeeId", "costOpening", "costChange", "costClosing",
    "pnlAdjOpening", "pnlAdjChange", "pnlAdjClosing",
    "ociBalOpening", "otherEqBalOpening", "auditedNetAssets",
    "shareOfAuditedNetAssets", "lteiBookBalance", "netAssetShareVariance",
    "g72OpeningTotal", "openingReconVariance", "g72ClosingTotal", "closingReconVariance",
]

# 区段3: 差额拆解与滚存
_G7_14_SEG3_HEADERS = [
    "被投资单位", "被投资单位ID", "OCI变动", "享有OCI", "账面确认OCI", "OCI差异",
    "其他权益变动", "享有其他权益", "账面确认其他权益", "其他权益差异",
    "商誉/初始差额", "累计公允价值调整", "减值准备", "未解释差额",
    "差额性质", "差额解释", "期初权益法余额", "期末权益法余额", "审计结论",
]
_G7_14_SEG3_KEYS = [
    "investeeName", "investeeId", "ociChange", "ociShare", "confirmedOci", "ociDifference",
    "otherEquityChange", "otherEquityShare", "confirmedOtherEquity", "otherEquityDifference",
    "goodwill", "cumulativeFvAdj", "impairment", "unexplainedVariance",
    "unexplainedNature", "varianceExplanation", "openingBalance", "closingBalance", "auditConclusion",
]

# 宽表拼接时跳过区段2/3的被投资单位+ID列，避免重复
_G7_14_ALL_HEADERS = _G7_14_SEG1_HEADERS + _G7_14_SEG2_HEADERS[2:] + _G7_14_SEG3_HEADERS[2:]
_G7_14_ALL_KEYS = _G7_14_SEG1_KEYS + _G7_14_SEG2_KEYS[2:] + _G7_14_SEG3_KEYS[2:]

_G7_14_SEGMENTS = [
    ("本期权益法调整", _G7_14_SEG1_HEADERS, _G7_14_SEG1_KEYS),
    ("期末余额审核", _G7_14_SEG2_HEADERS, _G7_14_SEG2_KEYS),
    ("差额拆解与滚存", _G7_14_SEG3_HEADERS, _G7_14_SEG3_KEYS),
]

# 区段4: 多公司净资产调整（独立 sheet，扁平行）
_G7_14_NA_SHEET = "净资产调整"
_G7_14_NA_HEADERS = [
    "被投资单位", "被投资单位ID", "项目", "项目键", "期初", "本期增加", "本期减少", "期末", "持股比例(%)",
]
_G7_14_NA_LINE_DEFS = [
    ("shareCapital", "实收资本（或股本）"),
    ("capitalReserve", "资本公积"),
    ("treasuryStock", "减：库存股"),
    ("oci", "其他综合收益"),
    ("surplusReserve", "盈余公积"),
    ("specialReserve", "专项储备"),
    ("retainedEarnings", "未分配利润"),
    ("nonControllingInterest", "少数股东权益（展示）"),
    ("fvDiffAtAcquisition", "加：取得投资时公允价值差额"),
    ("otherProfitAdj", "加：其他需调整损益的项目"),
    ("openingFvDiffCumulative", "加：期初累计公允价值调整"),
    ("unrealizedInternalElim", "减：未实现内部交易损益"),
]

# 区段5: 商誉 / 累计 FV 明细（独立 sheet）
_G7_14_GWF_SHEET = "商誉FV明细"
_G7_14_GWF_HEADERS = [
    "明细ID", "被投资单位ID", "被投资单位", "类型", "说明",
    "期初未摊销", "本期摊销", "其他变动", "期末/金额", "索引",
]
_G7_14_GWF_KEYS = [
    "id", "investeeId", "investeeName", "kind", "description",
    "openingUnamortized", "currentDepreciationAdj", "otherChange", "amount", "indexRef",
]


# ═══════════════════════════════════════════════════════════════════════════════
# G7-15 内部交易抵销测算表（16列，单sheet；含 investeeId + 毛利率）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_15_HEADERS = [
    "被投资单位", "被投资单位ID", "交易类型", "交易内容", "交易金额",
    "毛利率(%)", "未实现利润", "未实现利润手工覆盖", "持股比例(%)", "应抵销金额", "上年抵销",
    "本年变动", "抵销分录", "是否关联交易", "审计结论",
    "索引", "备注",
]
_G7_15_KEYS = [
    "investeeName", "investeeId", "transactionType", "transactionContent", "transactionAmount",
    "grossMargin", "unrealizedProfit", "unrealizedProfitManual", "investmentRatio", "eliminationAmount", "priorElimination",
    "currentChange", "eliminationEntry", "isRelatedParty", "auditConclusion",
    "indexRef", "remark",
]

# 旧 14 列模板必填列（无毛利率 / 被投资单位ID / 手工覆盖）；新模板亦包含这些列
_G7_15_CORE_HEADERS = [
    "被投资单位", "交易类型", "交易内容", "交易金额",
    "未实现利润", "持股比例(%)", "应抵销金额", "上年抵销",
    "本年变动", "抵销分录", "是否关联交易", "审计结论",
    "索引", "备注",
]
_G7_15_OPTIONAL_HEADERS = ("被投资单位ID", "毛利率(%)", "未实现利润手工覆盖")
_G7_15_HEADER_ALIASES = {
    "持股比例(%)": ["持股比例", "持股比例%"],
    "毛利率(%)": ["毛利率", "毛利率%"],
    "被投资单位ID": ["investeeId", "被投资单位Id", "investee_id"],
    "未实现利润手工覆盖": ["手工覆盖", "unrealizedProfitManual"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# G7-16 未确认投资损失（17列→2区段Tab）
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 长期权益分析
_G7_16_SEG1_HEADERS = [
    "被投资单位", "被投资单位ID", "投资账面", "长期应收款", "其他实质长期权益",
    "预计负债", "合计长期权益", "累计亏损", "超额亏损", "分配顺序说明",
]
_G7_16_SEG1_KEYS = [
    "investeeName", "investeeId", "investmentBookValue", "longTermReceivable", "otherLongTermEquity",
    "estimatedLiability", "totalLongTermEquity", "cumulativeLoss", "excessLoss", "allocationOrder",
]

# 区段2: 超额亏损分配
_G7_16_SEG2_HEADERS = [
    "被投资单位", "冲减投资", "冲减长应收", "冲减其他权益",
    "确认预计负债", "未确认损失", "上期累计未确认", "本期变动",
    "分配手工锁定", "变动手工覆盖", "审计结论",
]
_G7_16_SEG2_KEYS = [
    "investeeName", "reduceInvestment", "reduceLongTermReceivable", "reduceOtherEquity",
    "recognizeEstimatedLiability", "unrecognizedLoss", "priorCumulative", "currentChange",
    "allocationManual", "currentChangeManual", "auditConclusion",
]

_G7_16_ALL_HEADERS = _G7_16_SEG1_HEADERS + _G7_16_SEG2_HEADERS[1:]
_G7_16_ALL_KEYS = _G7_16_SEG1_KEYS + _G7_16_SEG2_KEYS[1:]

_G7_16_SEGMENTS = [
    ("长期权益分析", _G7_16_SEG1_HEADERS, _G7_16_SEG1_KEYS),
    ("超额亏损分配", _G7_16_SEG2_HEADERS, _G7_16_SEG2_KEYS),
]


# ═══════════════════════════════════════════════════════════════════════════════
# G7-17 减值测试（导出全列；导入 CORE 必填，扩展列可选）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_17_CORE_HEADERS = [
    "被投资单位", "账面价值", "可收回金额", "减值迹象",
    "减值金额", "公允价值-处置费用", "使用价值", "审计结论", "索引",
]
_G7_17_CORE_KEYS = [
    "investeeName", "bookValue", "recoverableAmount", "hasImpairmentSign",
    "impairmentAmount", "fvLessDisposalCost", "valueInUse", "auditConclusion", "indexRef",
]
_G7_17_OPTIONAL_HEADERS = ("期初已提减值", "手工覆盖可收回", "覆盖原因", "附件")
_G7_17_HEADERS = [
    "被投资单位", "账面价值", "期初已提减值", "可收回金额", "减值迹象",
    "减值金额", "公允价值-处置费用", "使用价值", "审计结论", "索引",
    "手工覆盖可收回", "覆盖原因", "附件",
]
_G7_17_KEYS = [
    "investeeName", "bookValue", "openingImpairment", "recoverableAmount", "hasImpairmentSign",
    "impairmentAmount", "fvLessDisposalCost", "valueInUse", "auditConclusion", "indexRef",
    "recoverableManual", "recoverableOverrideReason", "attachmentName",
]

# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G7-4": "G7-4-rows",
    "G7-5": "G7-5-rows",
    "G7-6": "G7-6-rows",
    "G7-13": "G7-13-rows",
    "G7-14": "G7-14-rows",
    "G7-15": "G7-15-rows",
    "G7-16": "G7-16-rows",
    "G7-17": "G7-17-rows",
}

# 页面保存键（与导入导出键并存时，导出优先 rows，回退页面 payload）
_G7_14_PAGE_ITEM_ID = "G7-14-equity-method-calc"

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


def _rows_from_g7_14_page_payload(payload: Any) -> list[dict]:
    """从页面 checklist payload 提取扁平 rows。"""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    rows = payload.get("rows")
    if isinstance(rows, list) and rows:
        return [r for r in rows if isinstance(r, dict)]
    groups = payload.get("groups") or payload.get("Groups") or []
    out: list[dict] = []
    if isinstance(groups, list):
        for g in groups:
            if not isinstance(g, dict):
                continue
            for r in g.get("rows") or []:
                if isinstance(r, dict):
                    out.append(r)
    return out


async def _load_sheet_rows(db: AsyncSession, wp_id: str, sheet: str) -> list[dict]:
    item_id = _ITEM_IDS[sheet]
    rows = await load_json_rows(db, wp_id, item_id, field="conclusion")
    if sheet == "G7-14":
        # 页面 SECTION 为权威源（含跨表同步最新值）；ROWS 仅作回退
        page_payload = await load_json_payload(db, wp_id, _G7_14_PAGE_ITEM_ID, field="conclusion")
        page_rows = _rows_from_g7_14_page_payload(page_payload)
        if page_rows:
            return page_rows
    if rows:
        return rows
    # G7-15：ROWS 空时回退页面 section 双写键
    if sheet == "G7-15":
        section = await load_json_payload(db, wp_id, "G7-15-internal-transaction", field="conclusion")
        if isinstance(section, list):
            return [r for r in section if isinstance(r, dict)]
        if isinstance(section, dict):
            candidate = section.get("rows")
            if isinstance(candidate, list):
                return [r for r in candidate if isinstance(r, dict)]
    return []


def _merge_preserve_g7_14_page(
    old_payload: Any,
    rows: list[dict],
    na_list: list[dict] | None = None,
    gwf_list: list[dict] | None = None,
) -> dict[str, Any]:
    """导入时保留重要性、结论、净资产调整、商誉/FV明细等页面扩展字段。"""
    old = old_payload if isinstance(old_payload, dict) else {}
    group_map: dict[str, list[dict]] = {}
    for r in rows:
        name = str(r.get("investeeName") or r.get("investee_name") or "未分组")
        group_map.setdefault(name, []).append(r)
    preserved_na = na_list if na_list is not None else (
        old.get("netAssetAdjustments") or old.get("net_asset_adjustments") or []
    )
    preserved_gwf = gwf_list if gwf_list is not None else (
        old.get("goodwillFvDetails") or old.get("goodwill_fv_details") or []
    )
    out: dict[str, Any] = {
        "rows": rows,
        "materialityLevel": old.get("materialityLevel", old.get("materiality_level", 0)) or 0,
        "conclusion": old.get("conclusion") or "",
        "groups": [
            {"investeeName": name, "rows": group_rows}
            for name, group_rows in group_map.items()
        ],
        "netAssetAdjustments": preserved_na,
        "goodwillFvDetails": preserved_gwf,
    }
    if old.get("lastCrossSheetSync") or old.get("last_cross_sheet_sync"):
        out["lastCrossSheetSync"] = old.get("lastCrossSheetSync") or old.get("last_cross_sheet_sync")
    return out


def _normalize_ratio_to_fraction(raw: Any) -> float:
    """Excel 持股比例(%) → 小数；已是小数则保持。"""
    v = safe_float(raw)
    if abs(v) > 1.0000001:
        return round(v / 100.0, 8)
    return v


def _ratio_to_percent_display(raw: Any) -> float:
    v = safe_float(raw)
    if abs(v) <= 1.0000001:
        return round(v * 100.0, 4)
    return v


def _prepare_g7_14_rows_export(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        d = _g7_14_recalculate(dict(r))
        if "investmentRatio" in d:
            d["investmentRatio"] = _ratio_to_percent_display(d.get("investmentRatio"))
        out.append(d)
    return out


def _normalize_g7_14_rows_import(rows: list[dict]) -> list[dict]:
    for r in rows:
        if "investmentRatio" in r:
            r["investmentRatio"] = _normalize_ratio_to_fraction(r.get("investmentRatio"))
        nature = str(r.get("unexplainedNature") or "").strip()
        if not nature:
            r["unexplainedNature"] = "pending"
    return rows


def _prepare_g7_15_rows_export(rows: list[dict]) -> list[dict]:
    """导出前：持股比例/毛利率 小数 → 百分数；布尔 → 是/否；公式列权威重算。"""
    out: list[dict] = []
    for r in rows:
        d = _recalculate_g7_15_row(dict(r))
        if "investmentRatio" in d:
            d["investmentRatio"] = _ratio_to_percent_display(d.get("investmentRatio"))
        if "grossMargin" in d:
            d["grossMargin"] = _ratio_to_percent_display(d.get("grossMargin"))
        for bool_key in ("isRelatedParty", "unrealizedProfitManual"):
            if bool_key in d:
                val = d.get(bool_key)
                if isinstance(val, bool):
                    d[bool_key] = "是" if val else "否"
                elif val is not None and not isinstance(val, str):
                    d[bool_key] = "是" if bool(val) else "否"
        out.append(d)
    return out


def _recalculate_g7_15_row(row: dict) -> dict:
    """与前端 recalcInternalTransactionRow 口径一致。"""
    svc = G7LongTermEquityMethodService
    amount = safe_float(row.get("transactionAmount"))
    margin = safe_float(row.get("grossMargin"))
    profit = safe_float(row.get("unrealizedProfit"))
    ratio = safe_float(row.get("investmentRatio"))
    prior = safe_float(row.get("priorElimination"))
    manual = _yes_no_to_bool(row.get("unrealizedProfitManual"))
    # 毛利率为空/0 但已有未实现利润 → 视为手工覆盖，避免公式清零
    if not manual and abs(margin) < 1e-12 and abs(profit) > 0.005:
        manual = True
    row["unrealizedProfitManual"] = manual
    if not manual:
        profit = svc.calc_unrealized_profit(amount, margin)
        row["unrealizedProfit"] = profit
    else:
        row["unrealizedProfit"] = round(profit, 2)

    t = str(row.get("transactionType") or "").strip()
    if t == "顺流":
        row["eliminationAmount"] = svc.calc_elimination_amount("downstream", profit, ratio)
    elif t == "逆流":
        row["eliminationAmount"] = svc.calc_elimination_amount("upstream", profit, ratio)
    else:
        row["eliminationAmount"] = 0.0

    if t in ("顺流", "逆流"):
        row["currentChange"] = round(safe_float(row["eliminationAmount"]) - prior, 2)
    else:
        row["currentChange"] = 0.0
    return row


def _normalize_g7_15_rows_import(rows: list[dict]) -> list[dict]:
    """导入后：比例归一 + 关联/手工布尔 + 公式列权威重算。"""
    for r in rows:
        if "investmentRatio" in r:
            r["investmentRatio"] = _normalize_ratio_to_fraction(r.get("investmentRatio"))
        if "grossMargin" in r:
            r["grossMargin"] = _normalize_ratio_to_fraction(r.get("grossMargin"))
        if "isRelatedParty" in r:
            r["isRelatedParty"] = _yes_no_to_bool(r.get("isRelatedParty"))
        if "unrealizedProfitManual" in r:
            r["unrealizedProfitManual"] = _yes_no_to_bool(r.get("unrealizedProfitManual"))
        _recalculate_g7_15_row(r)
    return rows


def _parse_g7_15_sheet_rows(content: bytes) -> tuple[list[dict], list[str], list[str]]:
    """按表头名解析 G7-15。

    - 强制旧 14 列（CORE）；毛利率 / 被投资单位ID / 手工覆盖 可缺（兼容旧 Excel）
    - 列顺序无关；缺可选列填空并给出 warning
    """
    try:
        actual, raw = parse_upload_xlsx(
            content,
            _G7_15_CORE_HEADERS,
            header_row=2,
            header_aliases=_G7_15_HEADER_ALIASES,
            require_all_headers=True,
        )
    except ValueError as e:
        return [], [str(e)], []

    warnings: list[str] = []
    missing_opt = [h for h in _G7_15_OPTIONAL_HEADERS if h not in actual]
    if missing_opt:
        warnings.append(f"兼容旧模板：缺列 {', '.join(missing_opt)} 已按空值导入")

    errors: list[str] = []
    rows: list[dict] = []
    header_idx = {h: i for i, h in enumerate(actual)}
    for i, r in enumerate(raw, start=1):
        if i > ROW_LIMIT:
            errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
            break
        values = list(r)
        parsed: dict[str, Any] = {"id": str(uuid4())}
        for h, key in zip(_G7_15_HEADERS, _G7_15_KEYS):
            idx = header_idx.get(h)
            raw_val = values[idx] if idx is not None and idx < len(values) else None
            if key in ("isRelatedParty", "unrealizedProfitManual"):
                parsed[key] = safe_str(raw_val)
            elif _is_numeric(key):
                parsed[key] = safe_float(raw_val)
            else:
                parsed[key] = safe_str(raw_val)
        # 旧模板无毛利率列但已有未实现利润 → 标记手工覆盖
        if "毛利率(%)" not in actual and safe_float(parsed.get("unrealizedProfit")):
            parsed["unrealizedProfitManual"] = True
        rows.append(parsed)
    return rows, errors, warnings


def _g7_14_recalculate(row: dict) -> dict:
    """导入/导出前覆盖公式列，与前端 recalcRow 口径一致。"""
    return G7LongTermEquityMethodService.recalculate_g7_14_row(row)


def _flatten_na_for_export(na_list: list[dict]) -> list[dict]:
    flat: list[dict] = []
    for adj in na_list or []:
        if not isinstance(adj, dict):
            continue
        name = str(adj.get("investeeName") or adj.get("investee_name") or "")
        investee_id = str(adj.get("investeeId") or adj.get("investee_id") or "")
        ratio_pct = _ratio_to_percent_display(adj.get("ownershipRatio") or adj.get("ownership_ratio") or 0)
        for key, label in _G7_14_NA_LINE_DEFS:
            item = adj.get(key) or {}
            if not isinstance(item, dict):
                item = {}
            begin = safe_float(item.get("begin"))
            increase = safe_float(item.get("increase"))
            decrease = safe_float(item.get("decrease"))
            flat.append({
                "investeeName": name,
                "investeeId": investee_id,
                "lineItem": label,
                "lineItemKey": key,
                "begin": begin,
                "increase": increase,
                "decrease": decrease,
                "end": round(begin + increase - decrease, 2),
                "ownershipRatio": ratio_pct,
            })
    return flat


def _append_g7_14_na_sheet(wb: Workbook, na_list: list[dict], *, template_only: bool = False) -> None:
    ws = wb.create_sheet(title=_G7_14_NA_SHEET)
    ws.append(["G7-14 — 净资产调整（多公司）"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(_G7_14_NA_HEADERS))
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(_G7_14_NA_HEADERS)
    ws.freeze_panes = "A3"
    for col_idx in range(1, len(_G7_14_NA_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 16
    if template_only:
        return
    for row in _flatten_na_for_export(na_list):
        ws.append([
            row.get("investeeName"),
            row.get("investeeId"),
            row.get("lineItem"),
            row.get("lineItemKey"),
            row.get("begin"),
            row.get("increase"),
            row.get("decrease"),
            row.get("end"),
            row.get("ownershipRatio"),
        ])


def _parse_g7_14_na_sheet(content: bytes) -> list[dict]:
    """从导入文件解析净资产调整 sheet → NetAssetAdjustment 列表。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = None
    for name in wb.sheetnames:
        if _G7_14_NA_SHEET in name or "净资产调整" in name:
            ws = wb[name]
            break
    if ws is None:
        wb.close()
        return []

    header_row_idx = 2
    actual = [
        str(c.value).strip() if c.value else ""
        for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
    ]
    label_to_key = {label: key for key, label in _G7_14_NA_LINE_DEFS}
    by_name: dict[str, dict] = {}

    def _blank_rf() -> dict:
        return {"begin": 0.0, "increase": 0.0, "decrease": 0.0}

    for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
        if all(v is None for v in row):
            continue
        values = list(row) + [None] * max(0, len(actual) - len(row))
        mapped = {actual[i]: values[i] for i in range(min(len(actual), len(values)))}
        name = str(mapped.get("被投资单位") or "").strip()
        investee_id = str(mapped.get("被投资单位ID") or "").strip()
        if not name and not investee_id:
            continue
        bucket_key = f"id:{investee_id}" if investee_id else name
        if bucket_key not in by_name:
            by_name[bucket_key] = {
                "id": str(uuid4()),
                "investeeName": name or investee_id,
                "investeeId": investee_id or None,
                "ownershipRatio": 0.0,
                **{k: _blank_rf() for k, _ in _G7_14_NA_LINE_DEFS},
            }
        adj = by_name[bucket_key]
        if investee_id and not adj.get("investeeId"):
            adj["investeeId"] = investee_id
        if name:
            adj["investeeName"] = name
        ratio_raw = mapped.get("持股比例(%)")
        if ratio_raw is not None and str(ratio_raw).strip() != "":
            adj["ownershipRatio"] = _normalize_ratio_to_fraction(ratio_raw)
        key = str(mapped.get("项目键") or "").strip()
        label = str(mapped.get("项目") or "").strip()
        field = key if key in adj and isinstance(adj.get(key), dict) else label_to_key.get(label)
        if not field:
            continue
        adj[field] = {
            "begin": safe_float(mapped.get("期初")),
            "increase": safe_float(mapped.get("本期增加")),
            "decrease": safe_float(mapped.get("本期减少")),
        }

    wb.close()
    return list(by_name.values())


def _normalize_gwf_kind(raw: Any) -> str:
    text = str(raw or "").strip()
    if text in ("fvAdj", "累计FV", "累计公允价值", "公允价值调整"):
        return "fvAdj"
    return "goodwill"


def _append_g7_14_gwf_sheet(wb: Workbook, gwf_list: list[dict], *, template_only: bool = False) -> None:
    ws = wb.create_sheet(title=_G7_14_GWF_SHEET)
    ws.append(["G7-14 — 商誉 / 累计公允价值调整明细"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(_G7_14_GWF_HEADERS))
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(_G7_14_GWF_HEADERS)
    ws.freeze_panes = "A3"
    for col_idx in range(1, len(_G7_14_GWF_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 14
    if template_only:
        return
    for row in gwf_list or []:
        if not isinstance(row, dict):
            continue
        kind = _normalize_gwf_kind(row.get("kind"))
        kind_label = "累计FV" if kind == "fvAdj" else "商誉"
        ws.append([
            str(row.get("id") or ""),
            str(row.get("investeeId") or row.get("investee_id") or ""),
            str(row.get("investeeName") or row.get("investee_name") or ""),
            kind_label,
            str(row.get("description") or ""),
            safe_float(row.get("openingUnamortized") or row.get("opening_unamortized")),
            safe_float(row.get("currentDepreciationAdj") or row.get("current_depreciation_adj")),
            safe_float(row.get("otherChange") or row.get("other_change")),
            safe_float(row.get("amount")),
            str(row.get("indexRef") or row.get("index_ref") or ""),
        ])


def _parse_g7_14_gwf_sheet(content: bytes) -> list[dict] | None:
    """解析商誉/FV明细 sheet。

    返回 None 表示文件无该 sheet（保留旧数据）；返回 list（可空）表示 sheet 存在。
    """
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = None
    for name in wb.sheetnames:
        if _G7_14_GWF_SHEET in name or "商誉FV" in name or "商誉" in name and "FV" in name:
            ws = wb[name]
            break
    if ws is None:
        wb.close()
        return None

    header_row_idx = 2
    actual = [
        str(c.value).strip() if c.value else ""
        for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
    ]
    out: list[dict] = []
    for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
        if all(v is None for v in row):
            continue
        values = list(row) + [None] * max(0, len(actual) - len(row))
        mapped = {actual[i]: values[i] for i in range(min(len(actual), len(values)))}
        name = str(mapped.get("被投资单位") or "").strip()
        investee_id = str(mapped.get("被投资单位ID") or "").strip()
        if not name and not investee_id:
            continue
        detail_id = str(mapped.get("明细ID") or "").strip() or str(uuid4())
        out.append({
            "id": detail_id,
            "investeeId": investee_id or None,
            "investeeName": name or investee_id,
            "kind": _normalize_gwf_kind(mapped.get("类型")),
            "description": safe_str(mapped.get("说明")),
            "openingUnamortized": safe_float(mapped.get("期初未摊销")),
            "currentDepreciationAdj": safe_float(mapped.get("本期摊销")),
            "otherChange": safe_float(mapped.get("其他变动")),
            "amount": safe_float(mapped.get("期末/金额")),
            "indexRef": safe_str(mapped.get("索引")),
        })
    wb.close()
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 权益法组数值字段判断（补充 _cycle_import_export_common 未覆盖的 keys）
# ═══════════════════════════════════════════════════════════════════════════════

_EQUITY_METHOD_NUMERIC_KEYS = {
    # G7-4
    "registeredCapital", "investmentAmount", "endingNetAssets", "currentNetProfit",
    "directHoldingRatio", "indirectHoldingRatio", "votingRatio",
    # G7-5
    "priorAmount", "currentAmount", "changeAmount", "changeRate",
    # G7-13
    "consideration", "directCosts", "initialCost", "netAssetFairValue",
    "shareOfNetAssets", "difference", "adjustedNetAssets", "adjustedShareOfNetAssets",
    "investmentRatio",
    # G7-14
    "reportedNetProfit", "internalTransactionAdj", "fvDepreciationAdj",
    "accountingPolicyAdj", "otherAdj", "adjustedNetProfit", "investmentRatio",
    "equityShare", "confirmedIncome", "incomeDifference", "ociChange",
    "ociShare", "otherEquityChange", "otherEquityShare", "dividendDistributed",
    "openingBalance", "closingBalance",
    "costOpening", "costChange", "costClosing",
    "pnlAdjOpening", "pnlAdjChange", "pnlAdjClosing",
    "ociBalOpening", "otherEqBalOpening", "auditedNetAssets",
    "shareOfAuditedNetAssets", "lteiBookBalance", "netAssetShareVariance",
    "goodwill", "cumulativeFvAdj", "impairment", "unexplainedVariance",
    "confirmedOci", "confirmedOtherEquity", "ociDifference", "otherEquityDifference",
    "g72OpeningTotal", "g72ClosingTotal", "openingReconVariance", "closingReconVariance",
    # G7-15
    "transactionAmount", "grossMargin", "unrealizedProfit", "eliminationAmount",
    "priorElimination", "currentChange",
    # G7-16
    "investmentBookValue", "longTermReceivable", "otherLongTermEquity",
    "estimatedLiability", "totalLongTermEquity", "cumulativeLoss", "excessLoss",
    "reduceInvestment", "reduceLongTermReceivable", "reduceOtherEquity",
    "recognizeEstimatedLiability", "unrecognizedLoss", "priorCumulative",
    # G7-17
    "bookValue", "recoverableAmount", "impairmentAmount",
    "fvLessDisposalCost", "valueInUse", "openingImpairment",
    # G7-6
    "adjustmentAmount",
}


def _is_numeric(key: str) -> bool:
    """判断字段是否为数值类型（先查本地集合，再 fallback 通用规则）。"""
    if key in _EQUITY_METHOD_NUMERIC_KEYS:
        return True
    return is_numeric_field_key(key)


def _normalize_g7_6_rows_to_payload(rows: list[dict]) -> dict[str, Any]:
    """扁平行按被投资单位重建 {groups, rows}，与前端 G7-6 落库形态一致。"""
    group_map: dict[str, dict[str, Any]] = {}
    flat: list[dict] = []
    for index, source in enumerate(rows):
        name = str(source.get("investeeName") or source.get("investee_name") or "").strip()
        if not name:
            continue
        investee_id = str(source.get("investeeId") or source.get("investee_id") or "").strip()
        consistent = str(source.get("isConsistent") or source.get("is_consistent") or "").strip()
        if consistent not in {"一致", "不一致", "不适用", ""}:
            consistent = ""
        amount = safe_float(source.get("adjustmentAmount") or source.get("adjustment_amount"))
        if consistent != "不一致":
            amount = 0.0
        row = {
            "id": str(source.get("id") or uuid4()),
            "seq": int(source.get("seq") or (len(group_map.get(name, {}).get("rows") or []) + 1)),
            "policyItem": safe_str(source.get("policyItem") or source.get("policy_item")),
            "investeePolicy": safe_str(source.get("investeePolicy") or source.get("investee_policy")),
            "investorPolicy": safe_str(source.get("investorPolicy") or source.get("investor_policy")),
            "isConsistent": consistent,
            "adjustmentAmount": amount,
            "adjustmentNote": safe_str(source.get("adjustmentNote") or source.get("adjustment_note")),
            "investeeName": name,
            "investeeId": investee_id,
        }
        if name not in group_map:
            group_map[name] = {
                "investeeName": name,
                "investeeId": investee_id or None,
                "rows": [],
            }
        elif investee_id and not group_map[name].get("investeeId"):
            group_map[name]["investeeId"] = investee_id
        group_map[name]["rows"].append(row)
        flat.append(row)
        _ = index  # keep enumerate for future row-level errors
    for group in group_map.values():
        for i, row in enumerate(group["rows"], start=1):
            row["seq"] = i
    return {"groups": list(group_map.values()), "rows": flat}


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
    optional_headers: tuple[str, ...] | list[str] = (),
) -> tuple[list[dict], list[str]]:
    """解析多sheet或单sheet宽表导入文件。

    多区段按「被投资单位」键合并（不再按行号），避免区段行序不一致时错配。
    列按表头名映射（兼容列序变化）；optional_headers 缺失不阻断。
    """
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    rows_by_key: dict[str, dict] = {}
    key_order: list[str] = []
    optional_set = set(optional_headers)

    # 识别主键字段名（各区段通常第一列为被投资单位）
    identifier_key = "investeeName"
    for _seg_name, seg_headers, seg_keys in segments:
        if identifier_header in seg_headers:
            identifier_key = seg_keys[seg_headers.index(identifier_header)]
            break
        if "被投资单位" in seg_headers:
            identifier_key = seg_keys[seg_headers.index("被投资单位")]
            break

    def _upsert_partial(partial: dict, fallback_key: str) -> None:
        name = str(partial.get(identifier_key) or "").strip()
        investee_id = str(partial.get("investeeId") or partial.get("investee_id") or "").strip()
        key = f"id:{investee_id}" if investee_id else (name or fallback_key)
        if not name and not investee_id:
            partial[identifier_key] = ""
            errors.append(f"存在未填写被投资单位的行，已按临时键合并: {fallback_key}")
        if key not in rows_by_key:
            rows_by_key[key] = {"id": str(uuid4()), **partial}
            if not rows_by_key[key].get(identifier_key) and name:
                rows_by_key[key][identifier_key] = name
            if investee_id:
                rows_by_key[key]["investeeId"] = investee_id
            key_order.append(key)
        else:
            rows_by_key[key].update(partial)
            if name:
                rows_by_key[key][identifier_key] = name
            if investee_id:
                rows_by_key[key]["investeeId"] = investee_id

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
            header_to_idx = {h: i for i, h in enumerate(actual_headers) if h}
            missing = [
                h for h in seg_headers
                if h not in header_to_idx and h not in optional_set
            ]
            if missing:
                errors.append(f"工作表[{seg_name}]缺少列: {', '.join(missing)}")
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                values = list(row)
                partial: dict[str, Any] = {}
                for header, key in zip(seg_headers, seg_keys):
                    col_i = header_to_idx.get(header)
                    if col_i is None:
                        continue
                    raw = values[col_i] if col_i < len(values) else None
                    if _is_numeric(key):
                        partial[key] = safe_float(raw)
                    else:
                        partial[key] = safe_str(raw)
                name = str(partial.get(identifier_key) or "").strip()
                fallback = f"__anon_{seg_name}_{row_idx}"
                if name and name not in rows_by_key and len(key_order) >= ROW_LIMIT:
                    errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                    break
                if (not name) and fallback not in rows_by_key and len(key_order) >= ROW_LIMIT:
                    errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                    break
                _upsert_partial(partial, fallback)
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
            if len(key_order) >= ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {}
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
            _upsert_partial(parsed, f"__anon_wide_{row_idx}")

    wb.close()
    result = [rows_by_key[k] for k in key_order]
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
    return result, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G7-4 原底稿单sheet构建及校验
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g7_4_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """生成与G7-4原底稿字段、分类及枚举一致的单工作表。"""
    wb = build_workbook_template(
        "G7-4",
        _G7_4_HEADERS,
        title="G7-4 被投资单位基本信息",
        guidance=_G7_4_GUIDANCE,
    )
    ws = wb["G7-4"]

    group_labels = ",".join(_G7_4_GROUP_LABELS.values())
    validations = [
        (DataValidation(type="list", formula1=f'"{group_labels}"', allow_blank=False), "A3:A502"),
        (DataValidation(type="list", formula1='"1,2,3,4,5"', allow_blank=True), "E3:E502"),
        (DataValidation(type="list", formula1='"是,否"', allow_blank=True), "F3:F502"),
    ]
    for validation, target_range in validations:
        validation.error = "请选择下拉列表中的有效值"
        validation.errorTitle = "无效选项"
        validation.showErrorMessage = True
        ws.add_data_validation(validation)
        validation.add(target_range)

    if not template_only:
        for source in rows:
            row = dict(source)
            group_type = _G7_4_GROUP_ALIASES.get(safe_str(row.get("groupType")), "associate")
            row["groupType"] = _G7_4_GROUP_LABELS[group_type]
            row["accountingMethod"] = _G7_4_ACCOUNTING_METHODS[group_type]
            # 导出 id，便于跨表 investeeId round-trip
            if not safe_str(row.get("id")):
                row["id"] = str(uuid4())
            ws.append(export_row_by_keys(row, _G7_4_KEYS))

    for col_idx in (14, 15, 16):
        for cell in ws.iter_cols(min_col=col_idx, max_col=col_idx, min_row=3, max_row=max(502, ws.max_row)):
            for item in cell:
                item.number_format = '0.0000"%"'
    return wb


def _merge_g7_4_ids_by_name(rows: list[dict], existing: list[dict]) -> tuple[list[dict], int]:
    """无 ID 时按公司名称匹配库内行，保留既有 id，避免下游 investeeId 断裂。"""
    name_to_id: dict[str, str] = {}
    for old in existing:
        name = safe_str(old.get("investeeName") or old.get("investee_name"))
        oid = safe_str(old.get("id") or old.get("investeeId") or old.get("investee_id"))
        if name and oid and name not in name_to_id:
            name_to_id[name] = oid
    reused = 0
    out: list[dict] = []
    for row in rows:
        item = dict(row)
        rid = safe_str(item.get("id") or item.get("investeeId") or item.get("investee_id"))
        name = safe_str(item.get("investeeName") or item.get("investee_name"))
        if not rid and name and name in name_to_id:
            item["id"] = name_to_id[name]
            reused += 1
        elif not rid:
            item["id"] = str(uuid4())
        else:
            item["id"] = rid
        out.append(item)
    return out, reused


def _normalize_g7_4_rows(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """规范分类、枚举和会计处理方法，避免导入数据破坏底稿判断逻辑。"""
    normalized: list[dict] = []
    errors: list[str] = []
    for index, source in enumerate(rows, start=1):
        row = dict(source)
        group_raw = safe_str(row.get("groupType"))
        group_type = _G7_4_GROUP_ALIASES.get(group_raw)
        if not group_type:
            errors.append(f"第{index}行投资关系无效：{group_raw or '空'}")
            continue
        if not safe_str(row.get("investeeName")):
            errors.append(f"第{index}行公司名称不能为空")
            continue

        enterprise_type = safe_str(row.get("enterpriseType"))
        newly_consolidated = safe_str(row.get("newlyConsolidated"))
        if enterprise_type and enterprise_type not in {"1", "2", "3", "4", "5"}:
            errors.append(f"第{index}行企业类型必须为1至5")
            continue
        if newly_consolidated and newly_consolidated not in {"是", "否"}:
            errors.append(f"第{index}行是否新纳入合并范围必须为“是”或“否”")
            continue

        # id 可空：导入阶段再按名匹配；仍无则生成 uuid
        row_id = safe_str(row.get("id") or row.get("investeeId") or row.get("investee_id"))
        if row_id:
            row["id"] = row_id
        else:
            row.pop("id", None)
        row["groupType"] = group_type
        row["accountingMethod"] = _G7_4_ACCOUNTING_METHODS[group_type]
        row["ratioScale"] = "percent"
        if group_type != "subsidiary":
            row["level"] = ""
            row["enterpriseType"] = ""
            row["newlyConsolidated"] = ""
            row["lessThanHalfControlReason"] = ""
        if group_type == "joint_operation":
            row["votingRatio"] = 0.0
            row["holdingVotingDifferenceReason"] = ""
            row["majorityNoControlReason"] = ""
        normalized.append(row)
    return normalized, errors


def _parse_g7_4_sheet_rows(content: bytes) -> tuple[list[dict], list[str], list[str]]:
    """按表头名解析；强制旧 20 列，被投资单位ID 可缺。"""
    try:
        actual, raw = parse_upload_xlsx(
            content,
            _G7_4_CORE_HEADERS,
            header_row=2,
            header_aliases=_G7_4_HEADER_ALIASES,
            require_all_headers=True,
        )
    except ValueError as e:
        return [], [str(e)], []

    warnings: list[str] = []
    missing_opt = [h for h in _G7_4_OPTIONAL_HEADERS if h not in actual]
    if missing_opt:
        warnings.append(
            f"兼容旧模板：缺列 {', '.join(missing_opt)} 已按空值导入"
            "（无 ID 时按公司名称匹配保留旧 ID，无匹配则生成新 ID）"
        )

    errors: list[str] = []
    rows: list[dict] = []
    header_idx = {h: i for i, h in enumerate(actual)}
    for i, r in enumerate(raw, start=1):
        if i > ROW_LIMIT:
            errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
            break
        values = list(r)
        parsed: dict[str, Any] = {}
        for h, key in zip(_G7_4_HEADERS, _G7_4_KEYS):
            idx = header_idx.get(h)
            raw_val = values[idx] if idx is not None and idx < len(values) else None
            if key == "id":
                parsed[key] = safe_str(raw_val)
            elif is_numeric_field_key(key) or key in {
                "registeredCapital", "investmentAmount", "endingNetAssets", "currentNetProfit",
                "directHoldingRatio", "indirectHoldingRatio", "votingRatio",
            }:
                parsed[key] = safe_float(raw_val)
            else:
                parsed[key] = safe_str(raw_val)
        # 无 ID 时留给导入合并阶段按名匹配，勿提前 uuid
        if not safe_str(parsed.get("id")):
            parsed.pop("id", None)
        rows.append(parsed)
    return rows, errors, warnings


# ═══════════════════════════════════════════════════════════════════════════════
# 编制说明
# ═══════════════════════════════════════════════════════════════════════════════

_G7_4_GUIDANCE = [
    "G7-4 被投资单位基本信息",
    "",
    "按投资关系分为：子公司、合营企业、联营企业、共同经营。",
    "企业类型：1境内非金融子企业、2境内金融子企业、3境外子企业、4事业单位、5基建单位。",
    "是否为本期新纳入合并范围的子公司填：是 / 否。",
    "持股比例和表决权比例按百分数填写（如30表示30%）。",
    "会计处理方法由投资关系确定：成本法 / 权益法 / 各项单独确认。",
    "被投资单位ID：与行 id 对齐，供 G7-13/14/15 等跨表同步；旧模板可缺，导入时自动生成。",
]

_G7_5_GUIDANCE = [
    "G7-5 被投资单位财务信息",
    "",
    "10列：被投资单位/报表项目/上年金额/本年金额/变动额/变动率/分析说明/数据来源/审计状态/备注。",
    "变动额 = 本年金额 - 上年金额（公式列，导入后服务端重算）。",
    "变动率(%)：Excel 填百分数（如50表示50%）；系统内部存小数（0.5）；上年=0时为空。",
    "审计状态填：已审 / 未审 / 待确认。",
    "按被投资单位分组，组内含资产/负债/净资产/收入/利润等关键指标。",
    "|变动率|超过50%时须填写分析说明。",
]


def _g7_5_recalculate(row: dict[str, Any]) -> dict[str, Any]:
    prior = safe_float(row.get("priorAmount"))
    current = safe_float(row.get("currentAmount"))
    change = round(current - prior, 2)
    row["changeAmount"] = change
    if abs(prior) < 1e-12:
        row["changeRate"] = None
    else:
        row["changeRate"] = round(change / prior, 6)
    return row


def _prepare_g7_5_rows_export(rows: list[dict]) -> list[dict]:
    """导出：变动率小数 → 百分数。"""
    out: list[dict] = []
    for raw in rows:
        row = _g7_5_recalculate(dict(raw))
        rate = row.get("changeRate")
        if rate is not None and rate != "":
            try:
                row["changeRate"] = round(float(rate) * 100, 4)
            except (TypeError, ValueError):
                row["changeRate"] = None
        out.append(row)
    return out


def _normalize_g7_5_rows_import(rows: list[dict]) -> list[dict]:
    """导入：变动率(%) → 小数；重算变动额/率。"""
    out: list[dict] = []
    for raw in rows:
        row = dict(raw)
        rate_raw = row.get("changeRate")
        if rate_raw not in (None, ""):
            try:
                rate = float(rate_raw)
                # |rate|>1 视为百分数；否则兼容已是小数的旧导出
                if abs(rate) > 1 + 1e-9:
                    rate = rate / 100.0
                row["changeRate"] = rate
            except (TypeError, ValueError):
                row["changeRate"] = None
        out.append(_g7_5_recalculate(row))
    return out


_G7_13_GUIDANCE = [
    "G7-13 合营联营企业投资成本测试表",
    "",
    "区段Tab：初始计量 / 商誉计算+调整；含被投资单位ID与持股比例(%)。",
    "初始投资成本 = 支付对价 + 直接相关费用（公式列，导入后服务端重算）。",
    "享有份额 = 被投资方可辨认净资产公允价值 × 持股比例（公式列）。",
    "调整后享有份额 = 调整后净资产 × 持股比例（公式列，导入后服务端重算）。",
    "差额 = 初始投资成本 - 享有份额（正=商誉，负=营业外收入/廉价购买）。",
    "持股比例(%)：Excel 填百分数（如30）；系统内部存小数（0.3）。",
    "合并/非合并填：合并 / 非合并。",
    "审计结论填：无差异 / 存在差异-可接受 / 存在差异-需调整。",
]

_G7_14_GUIDANCE = [
    "G7-14 权益法测算表",
    "",
    "对齐原底稿：本期权益法调整 / 期末余额审核 / 差额拆解与滚存 / 多公司净资产调整。",
    "调整后净利润 = 报告净利润 - 内部交易 - FV折旧 + 政策调整 + 其他调整。",
    "测算投资收益⑤ = 调整后净利润 × 持股比例。",
    "投资收益差异⑩ = 账面确认⑨ - 测算⑤ + 已宣告股利⑧（⑨建议取损益调整本期净增加）。",
    "OCI差异 = 账面确认OCI − 享有OCI；其他权益差异 = 账面确认其他权益 − 享有其他权益。",
    "长投账面余额 = 投资成本 + 损益调整 + OCI + 其他权益变动。",
    "与享有净资产差额 = 长投账面余额 - 经审计净资产×持股比例。",
    "期初勾稽差异P = (成本+损益调整+OCI+其他权益)期初合计 − G7-2审定期初总额；期末勾稽差异S = 长投账面余额 − G7-2审定期末总额。",
    "未解释差额 = 与享有净资产差额 - 商誉 - 累计公允价值调整 + 减值准备（应接近0）。",
    "公式列（⑤/⑩/R/S/⑮及期末余额等）导入后由服务端统一重算，不信任 Excel 公式值。",
    "持股比例(%)：Excel 填百分数（如30）；系统内部存小数（0.3）。",
    "差额性质：pending/skip/investmentIncome/impairment/oci/capitalReserve/priorPeriod/goodwill/fvAdj。",
    "「净资产调整」sheet 按被投资单位+项目滚存，导入后回写经审计净资产。",
    "超重要性差异可生成借贷平衡建议分录并推送至 G7-3。",
    "审计结论填：无差异 / 差异可接受 / 差异需调整。",
]

_G7_15_GUIDANCE = [
    "G7-15 权益法未实现内部交易抵销测算表",
    "",
    "17列，单sheet导出（含被投资单位ID、毛利率、未实现利润手工覆盖）。",
    "未实现利润 = 交易金额 × 毛利率（也可直接填写覆盖；手工覆盖填「是」）。",
    "顺流交易（投资方→被投资方）：应抵销 = 未实现利润（全额）。",
    "逆流交易（被投资方→投资方）：应抵销 = 未实现利润 × 持股比例。",
    "毛利率(%)、持股比例(%)：Excel 填百分数（如 20 表示 20%）；系统存小数。",
    "被投资单位ID：与 G7-4 行 id 对齐，便于跨表同步（可空，按名称匹配）。",
    "交易类型填：顺流 / 逆流。",
    "审计结论填：合理 / 基本合理 / 不合理。",
    "是否关联交易 / 未实现利润手工覆盖填：是 / 否。",
]

_G7_16_GUIDANCE = [
    "G7-16 未确认投资损失测试表",
    "",
    "拆为2区段Tab：长期权益分析 / 超额亏损分配。",
    "被投资单位ID：与 G7-4 行 id 对齐，便于跨表同步（可空，按名称匹配）。",
    "合计长期权益 = 投资账面 + 长期应收款 + 其他实质长期权益 + 预计负债（公式列，导入时重算）。",
    "超额亏损 = MAX(0, 累计亏损 - 合计长期权益)（公式列，导入时重算）。",
    "超额亏损抵减顺序：①冲减投资 ②冲减长应收 ③冲减其他权益；预计负债需职业判断手工确认。",
    "未确认损失 = MAX(0, 超额亏损 - 各项冲减)（公式列，非负）。",
    "本期变动 = 未确认损失 − 上期累计未确认（公式列；「变动手工覆盖」=是时保留导入值）。",
    "分配手工锁定/变动手工覆盖填：是 / 否（旧模板无此列时默认否，导入仍会重算公式列）。",
    "审计结论填：合理 / 基本合理 / 不合理。",
]

_G7_17_GUIDANCE = [
    "G7-17 减值测试表",
    "",
    "扩展列含：期初已提减值（consol→open_impairment）、手工覆盖可收回、覆盖原因、附件。",
    "存在减值迹象时：填写公允价值-处置费用与使用价值；可收回金额=二者取高（公式），减值金额=MAX(0,账面-可收回)（公式）。",
    "手工覆盖可收回=是时保留导入的可收回金额，并建议填写覆盖原因。",
    "减值迹象 / 手工覆盖可收回填：是 / 否。",
    "审计结论填：无需计提 / 需计提 / 已充分计提。",
]


def _yes_no_to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    s = str(raw or "").strip().lower()
    return s in {"是", "true", "1", "y", "yes"}


def _normalize_g7_17_rows(rows: list[dict]) -> list[dict]:
    """导入归一：减值迹象→bool；有迹象时重算可收回金额与减值金额（尊重手工覆盖）。"""
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row = dict(r)
        sign = _yes_no_to_bool(row.get("hasImpairmentSign"))
        row["hasImpairmentSign"] = sign
        book = safe_float(row.get("bookValue"))
        fv = safe_float(row.get("fvLessDisposalCost"))
        viu = safe_float(row.get("valueInUse"))
        row["bookValue"] = book
        row["fvLessDisposalCost"] = fv
        row["valueInUse"] = viu
        row["openingImpairment"] = round(safe_float(row.get("openingImpairment")), 2)
        row["recoverableOverrideReason"] = str(row.get("recoverableOverrideReason") or "")
        row["attachmentName"] = str(row.get("attachmentName") or "")
        manual = _yes_no_to_bool(row.get("recoverableManual"))
        row["recoverableManual"] = manual
        if sign:
            if manual:
                recoverable = round(safe_float(row.get("recoverableAmount")), 2)
            else:
                recoverable = round(max(fv, viu), 2)
            row["recoverableAmount"] = recoverable
            row["impairmentAmount"] = round(max(0.0, book - recoverable), 2)
        else:
            row["recoverableAmount"] = 0.0
            row["fvLessDisposalCost"] = 0.0
            row["valueInUse"] = 0.0
            row["impairmentAmount"] = 0.0
            row["recoverableManual"] = False
        out.append(row)
    return out


def _prepare_g7_17_rows_export(rows: list[dict]) -> list[dict]:
    """导出：减值迹象/手工覆盖布尔→是/否。"""
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row = dict(r)
        row["hasImpairmentSign"] = "是" if _yes_no_to_bool(row.get("hasImpairmentSign")) else "否"
        row["recoverableManual"] = "是" if _yes_no_to_bool(row.get("recoverableManual")) else "否"
        out.append(row)
    return out


def _parse_g7_17_sheet_rows(content: bytes) -> tuple[list[dict], list[str], list[str]]:
    """按表头名解析 G7-17：旧 9 列 CORE 必填；扩展列可缺。"""
    try:
        actual, raw = parse_upload_xlsx(
            content,
            _G7_17_CORE_HEADERS,
            header_row=2,
            require_all_headers=True,
        )
    except ValueError as e:
        return [], [str(e)], []

    warnings: list[str] = []
    missing_opt = [h for h in _G7_17_OPTIONAL_HEADERS if h not in actual]
    if missing_opt:
        warnings.append(f"兼容旧模板：缺列 {', '.join(missing_opt)} 已按空值导入")

    errors: list[str] = []
    rows: list[dict] = []
    header_idx = {h: i for i, h in enumerate(actual)}
    for i, r in enumerate(raw, start=1):
        if i > ROW_LIMIT:
            errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
            break
        values = list(r)
        parsed: dict[str, Any] = {"id": str(uuid4())}
        for h, key in zip(_G7_17_HEADERS, _G7_17_KEYS):
            idx = header_idx.get(h)
            raw_val = values[idx] if idx is not None and idx < len(values) else None
            if key in ("hasImpairmentSign", "recoverableManual"):
                parsed[key] = safe_str(raw_val)
            elif _is_numeric(key):
                parsed[key] = safe_float(raw_val)
            else:
                parsed[key] = safe_str(raw_val)
        rows.append(parsed)
    return rows, errors, warnings


def _normalize_g7_13_rows_import(rows: list[dict]) -> list[dict]:
    """导入归一：比例→小数；重算初始成本/享有份额/差额/差额性质。"""
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row = dict(r)
        ratio = _normalize_ratio_to_fraction(row.get("investmentRatio"))
        row["investmentRatio"] = ratio
        consideration = safe_float(row.get("consideration"))
        direct_costs = safe_float(row.get("directCosts"))
        net_fv = safe_float(row.get("netAssetFairValue"))
        initial = round(consideration + direct_costs, 2)
        share = round(net_fv * ratio, 2)
        diff = round(initial - share, 2)
        row["consideration"] = consideration
        row["directCosts"] = direct_costs
        row["netAssetFairValue"] = net_fv
        row["initialCost"] = initial
        row["shareOfNetAssets"] = share
        row["difference"] = diff
        row["differenceNature"] = "商誉" if diff >= 0 else "营业外收入"
        adj_net = safe_float(row.get("adjustedNetAssets"))
        row["adjustedNetAssets"] = adj_net
        # 调整后享有份额 = 调整后净资产 × 比例（权威重算，不信任 Excel）
        if abs(adj_net) > 0.005 and ratio:
            row["adjustedShareOfNetAssets"] = round(adj_net * ratio, 2)
        else:
            row["adjustedShareOfNetAssets"] = 0.0
        if row.get("investeeId") is not None:
            row["investeeId"] = safe_str(row.get("investeeId"))
        out.append(row)
    return out


def _prepare_g7_13_rows_export(rows: list[dict]) -> list[dict]:
    """导出：持股比例小数 → 百分数；公式列权威重算。"""
    normalized = _normalize_g7_13_rows_import(rows)
    out: list[dict] = []
    for row in normalized:
        d = dict(row)
        d["investmentRatio"] = _ratio_to_percent_display(d.get("investmentRatio"))
        out.append(d)
    return out


def _normalize_g7_16_rows_import(rows: list[dict]) -> list[dict]:
    """导入归一：手工标志→bool；重算合计/超额/未确认；非手工覆盖时重算本期变动。"""
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row = dict(r)
        row["allocationManual"] = _yes_no_to_bool(row.get("allocationManual"))
        row["currentChangeManual"] = _yes_no_to_bool(row.get("currentChangeManual"))
        inv = safe_float(row.get("investmentBookValue"))
        lt_rec = safe_float(row.get("longTermReceivable"))
        other_eq = safe_float(row.get("otherLongTermEquity"))
        est_liab = safe_float(row.get("estimatedLiability"))
        cum_loss = safe_float(row.get("cumulativeLoss"))
        prior = safe_float(row.get("priorCumulative"))
        row["investmentBookValue"] = inv
        row["longTermReceivable"] = lt_rec
        row["otherLongTermEquity"] = other_eq
        row["estimatedLiability"] = est_liab
        row["cumulativeLoss"] = cum_loss
        row["priorCumulative"] = prior

        total = round(inv + lt_rec + other_eq + est_liab, 2)
        excess = round(max(0.0, cum_loss - total), 2)
        row["totalLongTermEquity"] = total
        row["excessLoss"] = excess

        if not row["allocationManual"] and excess > 0:
            rem = excess
            r1 = round(min(rem, max(0.0, inv)), 2)
            rem = round(rem - r1, 2)
            r2 = round(min(rem, max(0.0, lt_rec)), 2)
            rem = round(rem - r2, 2)
            r3 = round(min(rem, max(0.0, other_eq)), 2)
            row["reduceInvestment"] = r1
            row["reduceLongTermReceivable"] = r2
            row["reduceOtherEquity"] = r3
            # 预计负债不自动确认
            row["recognizeEstimatedLiability"] = safe_float(row.get("recognizeEstimatedLiability"))
        else:
            row["reduceInvestment"] = safe_float(row.get("reduceInvestment"))
            row["reduceLongTermReceivable"] = safe_float(row.get("reduceLongTermReceivable"))
            row["reduceOtherEquity"] = safe_float(row.get("reduceOtherEquity"))
            row["recognizeEstimatedLiability"] = safe_float(row.get("recognizeEstimatedLiability"))

        unrecognized = round(max(0.0, excess
            - row["reduceInvestment"]
            - row["reduceLongTermReceivable"]
            - row["reduceOtherEquity"]
            - row["recognizeEstimatedLiability"]), 2)
        row["unrecognizedLoss"] = unrecognized
        if not row["currentChangeManual"]:
            row["currentChange"] = round(unrecognized - prior, 2)
        else:
            row["currentChange"] = safe_float(row.get("currentChange"))
        out.append(row)
    return out


def _prepare_g7_16_rows_export(rows: list[dict]) -> list[dict]:
    """导出：手工标志布尔→是/否。"""
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row = dict(r)
        row["allocationManual"] = "是" if _yes_no_to_bool(row.get("allocationManual")) else "否"
        row["currentChangeManual"] = "是" if _yes_no_to_bool(row.get("currentChangeManual")) else "否"
        out.append(row)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 单sheet表配置（G7-4 / G7-5 / G7-15 / G7-17）
# ═══════════════════════════════════════════════════════════════════════════════

_SINGLE_SHEET_SPECS: dict[str, dict[str, Any]] = {
    "G7-4": {
        "headers": _G7_4_HEADERS,
        "field_keys": _G7_4_KEYS,
        "title": "G7-4 被投资单位基本信息",
        "guidance": _G7_4_GUIDANCE,
        "allow_missing_headers": True,
    },
    "G7-5": {
        "headers": _G7_5_HEADERS,
        "field_keys": _G7_5_KEYS,
        "title": "G7-5 被投资单位财务信息",
        "guidance": _G7_5_GUIDANCE,
    },
    "G7-6": {
        "headers": _G7_6_HEADERS,
        "field_keys": _G7_6_KEYS,
        "title": "G7-6 被投资公司会计政策一致性检查",
        "guidance": _G7_6_GUIDANCE,
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

# 多sheet表配置（G7-13 / G7-14 / G7-16）
_MULTI_SHEET_SPECS: dict[str, dict[str, Any]] = {
    "G7-13": {
        "segments": _G7_13_SEGMENTS,
        "all_headers": _G7_13_ALL_HEADERS,
        "all_keys": _G7_13_ALL_KEYS,
        "guidance": _G7_13_GUIDANCE,
        "identifier_header": "被投资单位名称",
        "optional_headers": ("被投资单位ID", "持股比例(%)"),
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
    """导出空模板：G7-4按原底稿单sheet，其余按既有宽表规则。"""
    _validate_sheet(sheet)

    if sheet == "G7-4":
        wb = _build_g7_4_workbook([], template_only=True)
        return workbook_to_response(wb, "G7-4_被投资单位基本信息_模板.xlsx")
    elif sheet in _MULTI_SHEET_SPECS:
        spec = _MULTI_SHEET_SPECS[sheet]
        wb = _build_multi_sheet_workbook(
            sheet, spec["segments"], [], template_only=True, guidance_lines=spec["guidance"],
        )
        if sheet == "G7-14":
            _append_g7_14_na_sheet(wb, [], template_only=True)
            _append_g7_14_gwf_sheet(wb, [], template_only=True)
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
    """导出数据：G7-4按原底稿单sheet，其余按既有宽表规则。"""
    _validate_sheet(sheet)
    rows = await _load_sheet_rows(db, wp_id, sheet)

    if sheet == "G7-4":
        wb = _build_g7_4_workbook(rows)
        return workbook_to_response(wb, "G7-4_被投资单位基本信息_数据.xlsx")
    elif sheet in _MULTI_SHEET_SPECS:
        spec = _MULTI_SHEET_SPECS[sheet]
        export_rows = rows
        if sheet == "G7-13":
            export_rows = _prepare_g7_13_rows_export(rows)
        elif sheet == "G7-14":
            export_rows = _prepare_g7_14_rows_export(rows)
        elif sheet == "G7-16":
            export_rows = _prepare_g7_16_rows_export(rows)
        wb = _build_multi_sheet_workbook(
            sheet, spec["segments"], export_rows, template_only=False, guidance_lines=spec["guidance"],
        )
        if sheet == "G7-14":
            page_payload = await load_json_payload(db, wp_id, _G7_14_PAGE_ITEM_ID, field="conclusion")
            na_list: list[dict] = []
            gwf_list: list[dict] = []
            if isinstance(page_payload, dict):
                raw_na = page_payload.get("netAssetAdjustments") or page_payload.get("net_asset_adjustments") or []
                if isinstance(raw_na, list):
                    na_list = [x for x in raw_na if isinstance(x, dict)]
                raw_gwf = page_payload.get("goodwillFvDetails") or page_payload.get("goodwill_fv_details") or []
                if isinstance(raw_gwf, list):
                    gwf_list = [x for x in raw_gwf if isinstance(x, dict)]
            _append_g7_14_na_sheet(wb, na_list, template_only=False)
            _append_g7_14_gwf_sheet(wb, gwf_list, template_only=False)
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
        if sheet == "G7-15":
            export_rows = _prepare_g7_15_rows_export(rows)
        elif sheet == "G7-17":
            export_rows = _prepare_g7_17_rows_export(rows)
        elif sheet == "G7-5":
            export_rows = _prepare_g7_5_rows_export(rows)
        else:
            export_rows = rows
        for d in export_rows:
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
    warnings: list[str] = []

    if sheet == "G7-15":
        rows, errors, warnings = _parse_g7_15_sheet_rows(content)
    elif sheet == "G7-17":
        rows, errors, warnings = _parse_g7_17_sheet_rows(content)
    elif sheet == "G7-4":
        rows, errors, warnings = _parse_g7_4_sheet_rows(content)
    elif sheet in _MULTI_SHEET_SPECS:
        spec = _MULTI_SHEET_SPECS[sheet]
        rows, errors = _parse_multi_sheet_import(
            content,
            spec["segments"],
            spec["all_headers"],
            spec["all_keys"],
            identifier_header=spec["identifier_header"],
            optional_headers=spec.get("optional_headers") or (),
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
                    raw_val = values[col_i] if col_i < len(values) else None
                else:
                    raw_val = None
                if _is_numeric(key):
                    parsed[key] = safe_float(raw_val)
                else:
                    parsed[key] = safe_str(raw_val)
            rows.append(parsed)

    if sheet == "G7-4":
        rows, validation_errors = _normalize_g7_4_rows(rows)
        errors.extend(validation_errors)
        existing_g74 = await _load_sheet_rows(db, wp_id, sheet)
        rows, reused_ids = _merge_g7_4_ids_by_name(rows, existing_g74)
        if reused_ids:
            warnings.append(f"已按公司名称保留 {reused_ids} 条被投资单位既有 ID")

    if sheet == "G7-5":
        rows = _normalize_g7_5_rows_import(rows)

    if sheet == "G7-13":
        rows = _normalize_g7_13_rows_import(rows)

    if sheet == "G7-15":
        rows = _normalize_g7_15_rows_import(rows)

    if sheet == "G7-16":
        rows = _normalize_g7_16_rows_import(rows)

    if sheet == "G7-17":
        rows = _normalize_g7_17_rows(rows)

    na_from_file: list[dict] | None = None
    gwf_from_file: list[dict] | None = None
    if sheet == "G7-14":
        rows = _normalize_g7_14_rows_import(rows)
        rows = [_g7_14_recalculate(r) for r in rows]
        na_from_file = _parse_g7_14_na_sheet(content)
        if not na_from_file:
            na_from_file = None  # 保留旧 payload 中的 NA
        gwf_from_file = _parse_g7_14_gwf_sheet(content)  # None=无sheet保留旧；[]=明确清空

    if errors and not rows:
        return {"ok": False, "errors": errors, "imported_count": 0}

    if sheet == "G7-6":
        payload = _normalize_g7_6_rows_to_payload(rows)
        await upsert_json_payload(db, wp_id, item_id, payload, field="conclusion")
        rows = payload["rows"]
    else:
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
    # G7-15：同步写入页面 section 键，与前端双写对齐
    if sheet == "G7-15":
        await upsert_json_payload(
            db, wp_id, "G7-15-internal-transaction",
            {"rows": rows}, field="conclusion",
        )
    # G7-14：同步写入页面保存键，并保留既有重要性/结论；有 NA/GWF sheet 则覆盖对应扩展
    if sheet == "G7-14":
        old_page = await load_json_payload(db, wp_id, _G7_14_PAGE_ITEM_ID, field="conclusion")
        page_payload = _merge_preserve_g7_14_page(
            old_page, rows, na_list=na_from_file, gwf_list=gwf_from_file,
        )
        await upsert_json_payload(db, wp_id, _G7_14_PAGE_ITEM_ID, page_payload, field="conclusion")

    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
    if warnings:
        out["warning"] = "；".join(warnings)
    if len(rows) >= ROW_LIMIT:
        trunc = f"数据行数超过{ROW_LIMIT}行限制，已截断"
        out["warning"] = f"{out['warning']}；{trunc}" if out.get("warning") else trunc
    return out
