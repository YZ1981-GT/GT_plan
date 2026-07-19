"""G7 长期股权投资(权益法组) — 导入导出（7张表×3端点=21端点）.

支持 7 张动态行表格：
  G7-4 被投资单位基本信息(原底稿单sheet) / G7-5 财务信息(10列) / G7-13 投资成本测试(17列→2sheet)
  G7-14 权益法测算(20列→2sheet) / G7-15 内部交易(14列) / G7-16 未确认损失(17列→2sheet)
  G7-17 减值测试(9列)

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

router = APIRouter(tags=["g7-equity-method-import-export"])


# ═══════════════════════════════════════════════════════════════════════════════
# G7-4 被投资单位基本信息（按原底稿A:T语义建模）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_4_HEADERS = [
    "投资关系", "公司名称", "级次（国企适用）", "企业类型（国企适用）",
    "是否为本期新纳入合并范围的子公司（国企适用）", "主要经营地", "注册地", "业务性质",
    "注册资本", "投资额", "期末净资产", "本期净利润",
    "直接持股比例/享有份额(%)", "间接持股比例/享有份额(%)", "表决权比例(%)",
    "持股比例与表决权比例不一致的原因",
    "表决权比例不足半数但能形成控制的原因",
    "拥有半数以上表决权但未形成控制的原因",
    "取得方式", "会计处理方法",
]
_G7_4_KEYS = [
    "groupType", "investeeName", "level", "enterpriseType",
    "newlyConsolidated", "principalPlace", "registeredPlace", "businessNature",
    "registeredCapital", "investmentAmount", "endingNetAssets", "currentNetProfit",
    "directHoldingRatio", "indirectHoldingRatio", "votingRatio",
    "holdingVotingDifferenceReason", "lessThanHalfControlReason",
    "majorityNoControlReason", "acquisitionMethod", "accountingMethod",
]

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
]
_G7_14_SEG2_KEYS = [
    "investeeName", "investeeId", "costOpening", "costChange", "costClosing",
    "pnlAdjOpening", "pnlAdjChange", "pnlAdjClosing",
    "ociBalOpening", "otherEqBalOpening", "auditedNetAssets",
    "shareOfAuditedNetAssets", "lteiBookBalance", "netAssetShareVariance",
]

# 区段3: 差额拆解与滚存
_G7_14_SEG3_HEADERS = [
    "被投资单位", "被投资单位ID", "OCI变动", "享有OCI", "其他权益变动", "享有其他权益",
    "商誉/初始差额", "累计公允价值调整", "减值准备", "未解释差额",
    "差额性质", "差额解释", "期初权益法余额", "期末权益法余额", "审计结论",
]
_G7_14_SEG3_KEYS = [
    "investeeName", "investeeId", "ociChange", "ociShare", "otherEquityChange", "otherEquityShare",
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
        d = dict(r)
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
    "confirmedOci", "confirmedOtherEquity",
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
    """解析多sheet或单sheet宽表导入文件。

    多区段按「被投资单位」键合并（不再按行号），避免区段行序不一致时错配。
    """
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    rows_by_key: dict[str, dict] = {}
    key_order: list[str] = []

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
            missing = [h for h in seg_headers if h not in actual_headers]
            if missing:
                errors.append(f"工作表[{seg_name}]缺少列: {', '.join(missing)}")
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                if len(key_order) >= ROW_LIMIT:
                    # 仅在新增键时截断；已有键允许补全字段
                    pass
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                partial: dict[str, Any] = {}
                for col_i, key in enumerate(seg_keys):
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
        (DataValidation(type="list", formula1='"1,2,3,4,5"', allow_blank=True), "D3:D502"),
        (DataValidation(type="list", formula1='"是,否"', allow_blank=True), "E3:E502"),
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
            ws.append(export_row_by_keys(row, _G7_4_KEYS))

    for col_idx in (13, 14, 15):
        for cell in ws.iter_cols(min_col=col_idx, max_col=col_idx, min_row=3, max_row=max(502, ws.max_row)):
            for item in cell:
                item.number_format = '0.0000"%"'
    return wb


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

        row["groupType"] = group_type
        row["accountingMethod"] = _G7_4_ACCOUNTING_METHODS[group_type]
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
    "对齐原底稿：本期权益法调整 / 期末余额审核 / 差额拆解与滚存 / 多公司净资产调整。",
    "调整后净利润 = 报告净利润 - 内部交易 - FV折旧 + 政策调整 + 其他调整。",
    "测算投资收益⑤ = 调整后净利润 × 持股比例。",
    "投资收益差异⑩ = 账面确认⑨ - 测算⑤ + 已宣告股利⑧（⑨建议取损益调整本期净增加）。",
    "长投账面余额 = 投资成本 + 损益调整 + OCI + 其他权益变动。",
    "与享有净资产差额 = 长投账面余额 - 经审计净资产×持股比例。",
    "未解释差额 = 与享有净资产差额 - 商誉 - 累计公允价值调整 + 减值准备（应接近0）。",
    "持股比例(%)：Excel 填百分数（如30）；系统内部存小数（0.3）。",
    "差额性质：pending/skip/investmentIncome/impairment/oci/capitalReserve/priorPeriod/goodwill/fvAdj。",
    "「净资产调整」sheet 按被投资单位+项目滚存，导入后回写经审计净资产。",
    "超重要性差异可生成借贷平衡建议分录并推送至 G7-3。",
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
# 单sheet表配置（G7-4 / G7-5 / G7-15 / G7-17）
# ═══════════════════════════════════════════════════════════════════════════════

_SINGLE_SHEET_SPECS: dict[str, dict[str, Any]] = {
    "G7-4": {
        "headers": _G7_4_HEADERS,
        "field_keys": _G7_4_KEYS,
        "title": "G7-4 被投资单位基本信息",
        "guidance": _G7_4_GUIDANCE,
    },
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

# 多sheet表配置（G7-13 / G7-14 / G7-16）
_MULTI_SHEET_SPECS: dict[str, dict[str, Any]] = {
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
        export_rows = _prepare_g7_14_rows_export(rows) if sheet == "G7-14" else rows
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

    if sheet == "G7-4":
        rows, validation_errors = _normalize_g7_4_rows(rows)
        errors.extend(validation_errors)

    na_from_file: list[dict] | None = None
    gwf_from_file: list[dict] | None = None
    if sheet == "G7-14":
        rows = _normalize_g7_14_rows_import(rows)
        na_from_file = _parse_g7_14_na_sheet(content)
        if not na_from_file:
            na_from_file = None  # 保留旧 payload 中的 NA
        gwf_from_file = _parse_g7_14_gwf_sheet(content)  # None=无sheet保留旧；[]=明确清空

    if errors and not rows:
        return {"ok": False, "errors": errors, "imported_count": 0}

    await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
    # G7-14：同步写入页面保存键，并保留既有重要性/结论；有 NA/GWF sheet 则覆盖对应扩展
    if sheet == "G7-14":
        old_page = await load_json_payload(db, wp_id, _G7_14_PAGE_ITEM_ID, field="conclusion")
        page_payload = _merge_preserve_g7_14_page(
            old_page, rows, na_list=na_from_file, gwf_list=gwf_from_file,
        )
        await upsert_json_payload(db, wp_id, _G7_14_PAGE_ITEM_ID, page_payload, field="conclusion")

    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
    if len(rows) >= ROW_LIMIT:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
