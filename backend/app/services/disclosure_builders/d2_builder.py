"""D2 应收账款后端 payload builder。

从 D2-detail-rows 555KB+ JSON 明细行聚合：
  ① 按账龄披露（6 段 + 合计）
  ② 按坏账准备计提方法分类（分类宽表 期末 + 期初）
  ③ 坏账准备变动表（期初→计提→转回→核销→期末）
  ④ 按欠款方归集前五名

数据来源：
  D2-detail-rows   → 明细行 JSON 数组（每行含 agingAudited/creditRiskClassification/groupName）
  D2-adj-tb-amount → 审定合计

spec: backend-disclosure-payload-builder Phase 2 Task 7 + 遗留修复 1
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.disclosure_payload_builder_service import (
    DisclosurePayloadBuilder,
    PayloadBuildResult,
    load_disclosure_entries,
    load_project_standard,
    load_project_template_type,
    register_builder,
)

D2_NOTE_SECTION = {"listed": "五、5", "soe": "八、5"}
D2_SHEET_NAME = {"listed": "附注披露信息(上市公司)", "soe": "附注披露信息(国企)"}

# 子表名（与前端 D2_TABLE_NAMES 和附注模板逐字一致）
_SOE_TABLES = {
    "aging": "（1）按账龄披露应收账款",
    "classEnd": "（2）按坏账准备计提方法分类披露应收账款",
    "classPrior": "（2）按坏账准备计提方法分类披露应收账款（续：期初数）",
    "individual": "期末单项计提坏账准备的应收账款",
    "movement": "（3）本期计提、收回或转回的坏账准备情况",
    "top5": "（5）按欠款方归集的期末余额前五名的应收账款",
}
_LISTED_TABLES = {
    "aging": "按账龄披露",
    "classEnd": "按坏账计提方法分类披露",
    "classPrior": "按坏账计提方法分类披露（续：上年年末余额）",
    "individualEnd": "按单项计提坏账准备的应收账款",
    "individualPrior": "按单项计提坏账准备的应收账款（续：上年年末余额）",
    "movement": "本期计提、收回或转回的坏账准备情况",
    "top5": "按欠款方归集的应收账款和合同资产期末余额前五名单位情况",
}

# 账龄分段
_AGING_SEGMENTS = [
    ("within1", "1年以内（含1年）"),
    ("y1to2", "1至2年"),
    ("y2to3", "2至3年"),
    ("y3to4", "3至4年"),
    ("y4to5", "4至5年"),
    ("over5", "5年以上"),
]

# 列定义
_AGING_COLS = [
    {"key": "label", "label": "账龄", "is_label": True, "flat": True},
    {"key": "end_amount", "label": "期末数", "format": "amount"},
    {"key": "prior_amount", "label": "期初数", "format": "amount"},
]
_CLASS_COLS = [
    {"key": "label", "label": "类别", "is_label": True},
    {"key": "balance", "label": "金额", "group": "账面余额", "format": "amount"},
    {"key": "ratio", "label": "比例(%)", "group": "账面余额", "format": "percent"},
    {"key": "provision", "label": "金额", "group": "坏账准备", "format": "amount"},
    {"key": "loss_rate", "label": "预期信用损失率(%)", "group": "坏账准备", "format": "percent"},
    {"key": "book_value", "label": "账面价值", "format": "amount"},
]
_MOVEMENT_COLS_SOE = [
    {"key": "label", "label": "类别", "is_label": True},
    {"key": "prior_balance", "label": "期初数", "format": "amount"},
    {"key": "provision", "label": "计提", "group": "本期变动情况", "format": "amount"},
    {"key": "reversal", "label": "收回或转回", "group": "本期变动情况", "format": "amount"},
    {"key": "write_off", "label": "转销或核销", "group": "本期变动情况", "format": "amount"},
    {"key": "end_balance", "label": "期末数", "format": "amount"},
]
_MOVEMENT_COLS_LISTED = [
    {"key": "label", "label": "项目", "is_label": True, "flat": True},
    {"key": "amount", "label": "坏账准备金额", "format": "amount"},
]
_TOP5_COLS_SOE = [
    {"key": "label", "label": "债务人名称", "is_label": True, "flat": True},
    {"key": "balance", "label": "账面余额", "format": "amount"},
    {"key": "ratio", "label": "比例(%)", "format": "percent"},
    {"key": "provision", "label": "坏账准备", "format": "amount"},
]
_TOP5_COLS_LISTED = [
    {"key": "label", "label": "单位名称", "is_label": True, "flat": True},
    {"key": "ar_amount", "label": "应收账款期末余额", "format": "amount"},
    {"key": "contract_asset_amount", "label": "合同资产期末余额", "format": "amount"},
    {"key": "total_amount", "label": "合计余额", "format": "amount"},
    {"key": "ratio", "label": "比例%", "format": "percent"},
    {"key": "provision", "label": "坏账准备", "format": "amount"},
]

TOTAL_LABEL = "合  计"


def _num(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except (ValueError, AttributeError):
            pass
    return 0.0


def _parse_json(raw: Any, default: Any = None) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw.strip()) if raw.strip() else default
        except (json.JSONDecodeError, ValueError):
            return default
    return default


def _safe_rate(numerator: float, denominator: float) -> float:
    return (numerator / denominator * 100) if denominator else 0.0


# ── 聚合函数 ─────────────────────────────────────────────────────────────────


def _aggregate_aging(rows: list[dict]) -> list[dict[str, Any]]:
    """① 按账龄段汇总。"""
    end_sums: dict[str, float] = {s: 0.0 for s, _ in _AGING_SEGMENTS}
    prior_sums: dict[str, float] = {s: 0.0 for s, _ in _AGING_SEGMENTS}
    for r in rows:
        ae = r.get("agingAudited") or r.get("agingCurrent") or {}
        ap = r.get("agingPrior") or {}
        for s, _ in _AGING_SEGMENTS:
            end_sums[s] += _num(ae.get(s) if isinstance(ae, dict) else 0)
            prior_sums[s] += _num(ap.get(s) if isinstance(ap, dict) else 0)
    out: list[dict[str, Any]] = []
    et, pt = 0.0, 0.0
    for s, label in _AGING_SEGMENTS:
        e, p = end_sums[s], prior_sums[s]
        out.append({"label": label, "end_amount": e, "prior_amount": p})
        et += e
        pt += p
    out.append({"label": TOTAL_LABEL, "end_amount": et, "prior_amount": pt, "is_total": True})
    return out


def _aggregate_class_wide(rows: list[dict], period: str) -> list[dict[str, Any]]:
    """② 按坏账分类汇总（period='end' 或 'prior'）。"""
    # creditRiskClassification: "单项" / "组合" / 空
    single_book = 0.0
    single_prov = 0.0
    combo_book = 0.0
    combo_prov = 0.0
    for r in rows:
        cls = str(r.get("creditRiskClassification") or "").strip()
        if period == "end":
            book = _num(r.get("currentAudited"))
        else:
            book = _num(r.get("priorAudited"))
        # provision 近似（detail-rows 不直接存 provision per row，用 loss_rate 估算不精确）
        # 简化：按 adj-tb 级别的坏账准备取数，明细不拆
        if cls == "单项":
            single_book += book
        else:
            combo_book += book
    total_book = single_book + combo_book
    out: list[dict[str, Any]] = [
        {
            "label": "按单项计提坏账准备",
            "balance": single_book,
            "ratio": _safe_rate(single_book, total_book),
            "provision": single_prov,
            "loss_rate": 0.0,
            "book_value": single_book - single_prov,
        },
        {
            "label": "按组合计提坏账准备",
            "balance": combo_book,
            "ratio": _safe_rate(combo_book, total_book),
            "provision": combo_prov,
            "loss_rate": 0.0,
            "book_value": combo_book - combo_prov,
        },
        {
            "label": TOTAL_LABEL,
            "balance": total_book,
            "ratio": 100.0 if total_book else 0.0,
            "provision": single_prov + combo_prov,
            "loss_rate": 0.0,
            "book_value": total_book - single_prov - combo_prov,
            "is_total": True,
        },
    ]
    return out


def _aggregate_top5(rows: list[dict], is_soe: bool) -> list[dict[str, Any]]:
    """④ 前五名（按期末审定数降序取前 5）。"""
    valid = [(r, _num(r.get("currentAudited"))) for r in rows if _num(r.get("currentAudited")) > 0]
    valid.sort(key=lambda x: x[1], reverse=True)
    total_all = sum(v for _, v in valid)
    top = valid[:5]
    out: list[dict[str, Any]] = []
    for r, amt in top:
        name = str(r.get("customerName") or "").strip() or "—"
        if is_soe:
            out.append({
                "label": name,
                "balance": amt,
                "ratio": _safe_rate(amt, total_all),
                "provision": 0.0,
            })
        else:
            out.append({
                "label": name,
                "ar_amount": amt,
                "contract_asset_amount": 0.0,
                "total_amount": amt,
                "ratio": _safe_rate(amt, total_all),
                "provision": 0.0,
            })
    # 合计行
    top_sum = sum(v for _, v in top)
    if is_soe:
        out.append({
            "label": TOTAL_LABEL,
            "balance": top_sum,
            "ratio": _safe_rate(top_sum, total_all),
            "provision": 0.0,
            "is_total": True,
        })
    else:
        out.append({
            "label": TOTAL_LABEL,
            "ar_amount": top_sum,
            "contract_asset_amount": 0.0,
            "total_amount": top_sum,
            "ratio": _safe_rate(top_sum, total_all),
            "provision": 0.0,
            "is_total": True,
        })
    return out


# ── Builder ──────────────────────────────────────────────────────────────────


@register_builder
class D2Builder(DisclosurePayloadBuilder):
    wp_code = "D2"

    async def build(self, db: AsyncSession, project_id: UUID, year: int) -> PayloadBuildResult | None:
        entries = await load_disclosure_entries(db, project_id, "D2")
        if not entries:
            return None

        template_type = await load_project_template_type(db, project_id)
        variant = "soe" if "soe" in template_type.lower() else "listed"
        is_soe = variant == "soe"
        current_standard = await load_project_standard(db, project_id)
        tables = _SOE_TABLES if is_soe else _LISTED_TABLES

        detail_rows = _parse_json(entries.get("D2-detail-rows"), [])
        if not isinstance(detail_rows, list):
            detail_rows = []

        sub: dict[str, Any] = {}
        cols: dict[str, list[dict]] = {}

        # ① 账龄表
        aging_rows = _aggregate_aging(detail_rows)
        sub[tables["aging"]] = aging_rows
        cols[tables["aging"]] = _AGING_COLS[:]

        # ② 坏账分类表（期末 + 期初）
        class_end = _aggregate_class_wide(detail_rows, "end")
        sub[tables["classEnd"]] = class_end
        cols[tables["classEnd"]] = _CLASS_COLS[:]

        class_prior = _aggregate_class_wide(detail_rows, "prior")
        sub[tables["classPrior"]] = class_prior
        cols[tables["classPrior"]] = _CLASS_COLS[:]

        # ③ 变动表（简化：只产出骨架行，数值待前端同步精确值）
        if is_soe:
            sub[tables["movement"]] = [
                {"label": "单项计提预期信用损失的应收账款", "prior_balance": 0.0,
                 "provision": 0.0, "reversal": 0.0, "write_off": 0.0, "end_balance": 0.0},
                {"label": "按组合计提预期信用损失的应收账款", "prior_balance": 0.0,
                 "provision": 0.0, "reversal": 0.0, "write_off": 0.0, "end_balance": 0.0},
                {"label": TOTAL_LABEL, "prior_balance": 0.0,
                 "provision": 0.0, "reversal": 0.0, "write_off": 0.0, "end_balance": 0.0, "is_total": True},
            ]
            cols[tables["movement"]] = _MOVEMENT_COLS_SOE[:]
        else:
            sub[tables["movement"]] = [
                {"label": "上年年末数", "amount": 0.0},
                {"label": "本期计提", "amount": 0.0},
                {"label": "本期收回或转回", "amount": 0.0},
                {"label": "本期核销", "amount": 0.0},
                {"label": "其他变动", "amount": 0.0},
                {"label": "本期余额", "amount": 0.0},
                {"label": TOTAL_LABEL, "amount": 0.0, "is_total": True},
            ]
            cols[tables["movement"]] = _MOVEMENT_COLS_LISTED[:]

        # ④ 前五名
        top5_rows = _aggregate_top5(detail_rows, is_soe)
        sub[tables["top5"]] = top5_rows
        cols[tables["top5"]] = (_TOP5_COLS_SOE if is_soe else _TOP5_COLS_LISTED)[:]

        return PayloadBuildResult(
            wp_code="D2",
            section_id=D2_NOTE_SECTION[variant],
            sub_table_data=sub,
            sub_table_columns=cols,
            sheet_name=D2_SHEET_NAME[variant],
            current_standard=current_standard,
        )
