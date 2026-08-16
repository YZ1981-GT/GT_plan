"""L 类 render 取数编排（8 个循环共用一份，禁各抄一遍）。

每个 `_lN_*.py` 的 render 只需一行::

    tb_payload = await build_l_tb_payload(ctx, "L3")
    return {..., **tb_payload}

产出四个键：

``trial_balance``
    审定表 TB 核对行数据（键名沿用改造前，前端零改动）。
``tb_source_codes``
    取数溯源（报表行 / 标准码 / 反解前缀 / 来源 / 勾稽自检）。
    前端 `WpFourTableSourcePanel` 消费 —— **不是 dead output**。
``adjudication_prefill``
    按叶子科目名归类的分类行预填（``{bucket_key: {...}}``）。
``l_bucket_defs``
    桶定义（中文标签单一真源下发，前端不抄第二份）。

**灰度**：`LMN_FOUR_TABLE_EXTRACTION_ENABLED=False` 时 helper 返回全 0 且不查库，
本模块随之产出零值 payload，与改造前逐字节等价（Property 4）。

spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/
      Requirements 1.4, 1.5, 3.5, 4.1, 4.5 / Property 1, 4, 14
"""

from __future__ import annotations

import logging
from typing import Any

from app.routers.wp_render_strategies._lmn_tb_helper import (
    fetch_leaf_rows,
    fetch_parent_rows,
    fetch_tb_for_balance,
    fetch_tb_for_income,
)
from app.services.four_table.leaf_aggregation import LeafRow

from .account_scope import (
    BUCKET_CURRENT_PORTION,
    L_CYCLE_SPECS,
    ResolvedScope,
    bucket_defs_payload,
    classify_l_leaf,
    resolve_l_scope,
)

logger = logging.getLogger(__name__)

_TOLERANCE = 0.01

_ZERO_TB: dict[str, Any] = {
    "account_code": "",
    "begin_balance": 0,
    "end_balance": 0,
    "debit_amount": 0,
    "credit_amount": 0,
}


def build_adjudication_prefill(
    wp_code: str, leaves: list[LeafRow]
) -> dict[str, dict[str, Any]]:
    """叶子行 → 分类行预填。纯函数。

    未命中任何桶的叶子归入 ``other``（金额不丢弃）。无叶子时返回 ``{}``
    —— 调用方据此判断「无四表数据」，不预填（宁缺勿造）。
    """
    spec = L_CYCLE_SPECS.get(wp_code)
    if spec is None or not leaves:
        return {}

    label_by_key = {b["key"]: b["label"] for b in bucket_defs_payload(wp_code)}
    out: dict[str, dict[str, Any]] = {}
    for row in leaves:
        key = classify_l_leaf(wp_code, row.account_name)
        entry = out.setdefault(
            key,
            {
                "bucket_key": key,
                "label": label_by_key.get(key, "其他"),
                "opening": 0.0,
                "closing": 0.0,
                "debit": 0.0,
                "credit": 0.0,
                "account_codes": [],
            },
        )
        entry["opening"] += row.opening
        entry["closing"] += row.closing
        entry["debit"] += row.debit
        entry["credit"] += row.credit
        if row.account_code not in entry["account_codes"]:
            entry["account_codes"].append(row.account_code)

    for entry in out.values():
        for k in ("opening", "closing", "debit", "credit"):
            entry[k] = round(entry[k], 2)
        entry["account_codes"].sort()
    return out


def build_current_portion(
    wp_code: str, prefill: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """「非流动部分 / 一年内到期部分」拆分（Property 14）。

    🔴 不用 ``BS-057/BS-080`` 的 ``TB('2502')`` —— 该报表行公式与应付债券撞码，
    取的是应付债券余额而非一年内到期部分。改由子科目名称识别。

    Returns:
        ``None`` = 该循环不需拆分；否则 ``{"current","non_current","total"}``。
    """
    spec = L_CYCLE_SPECS.get(wp_code)
    if spec is None or not spec.split_current_portion:
        return None
    current = prefill.get(BUCKET_CURRENT_PORTION, {})
    current_closing = float(current.get("closing") or 0)
    total_closing = round(
        sum(float(v.get("closing") or 0) for v in prefill.values()), 2
    )
    return {
        "current": round(current_closing, 2),
        "non_current": round(total_closing - current_closing, 2),
        "total": total_closing,
        "current_account_codes": list(current.get("account_codes") or []),
    }


def build_parent_check(
    scope: ResolvedScope,
    leaves: list[LeafRow],
    parents: list[LeafRow],
) -> dict[str, Any]:
    """「叶子和 == 父科目额」勾稽自检（Property 1）。

    父行不存在时 ``parent_amount`` 为 ``None``、``diff`` 为 ``None``（不臆造 0，
    否则会伪造出「差异 = -叶子合计」的假告警）。
    """
    leaf_closing = round(sum(r.closing for r in leaves), 2)
    if not parents:
        return {
            "parent_codes": list(scope.gross_query),
            "parent_amount": None,
            "leaf_amount": leaf_closing,
            "diff": None,
            "ok": None,
        }
    parent_closing = round(sum(r.closing for r in parents), 2)
    diff = round(parent_closing - leaf_closing, 2)
    return {
        "parent_codes": sorted({r.account_code for r in parents}),
        "parent_amount": parent_closing,
        "leaf_amount": leaf_closing,
        "diff": diff,
        "ok": abs(diff) <= _TOLERANCE,
    }


async def build_l_tb_payload(ctx, wp_code: str) -> dict[str, Any]:
    """编排某 L 循环的四表取数产物。全程 fail-open。

    Args:
        ctx: `RenderContext`（需 ``db`` / ``project_id`` / ``year``）。
        wp_code: ``L1``…``L8``。

    Returns:
        ``{"trial_balance","tb_source_codes","adjudication_prefill","l_bucket_defs"}``。
    """
    spec = L_CYCLE_SPECS.get(wp_code)
    if spec is None:
        logger.warning("L render 取数: 未登记的循环 %s", wp_code)
        return {
            "trial_balance": dict(_ZERO_TB),
            "tb_source_codes": {},
            "adjudication_prefill": {},
            "l_bucket_defs": [],
        }

    try:
        scope = await resolve_l_scope(ctx, wp_code)
    except Exception as e:  # noqa: BLE001 — 解析失败不阻断 render
        logger.warning("L render 取数: %s 科目解析失败: %s", wp_code, e)
        scope = ResolvedScope(
            wp_code=wp_code,
            account_label=spec.account_label,
            prefill_supported=False,
            note=f"科目解析异常: {e}",
        )

    source = scope.as_dict()
    source["account_label"] = spec.account_label
    # 前端 WpFourTableSourcePanel 期望 `row_code`（不是 `report_row_code`）
    source["row_code"] = scope.report_row_code
    source["row_name"] = spec.account_label

    # 宁缺勿造（L7）：不取数、不预填，但仍下发溯源说明供 UI 解释「为什么没有数据」
    if not scope.prefill_supported or not scope.gross_query:
        # 🔴 前端 isTbSourceAbsent 检查 `empty_reason` 非空即判 absent
        source["empty_reason"] = scope.note or None
        source.update(
            {
                "leaf_total": 0,
                "parent_check": {
                    "parent_codes": [],
                    "parent_amount": None,
                    "leaf_amount": 0,
                    "diff": None,
                    "ok": None,
                },
                "current_portion": None,
                "leaf_count": 0,
            }
        )
        return {
            "trial_balance": {**_ZERO_TB, "account_code": ""},
            "tb_source_codes": source,
            "adjudication_prefill": {},
            "l_bucket_defs": bucket_defs_payload(wp_code),
        }

    codes = list(scope.gross_query)
    if spec.kind == "income":
        tb = await fetch_tb_for_income(ctx, codes)
    else:
        tb = await fetch_tb_for_balance(ctx, codes)

    leaves = await fetch_leaf_rows(ctx, codes)
    parents = await fetch_parent_rows(ctx, codes)

    prefill = build_adjudication_prefill(wp_code, leaves)
    source["leaf_total"] = round(sum(r.closing for r in leaves), 2)
    source["leaf_count"] = len(leaves)
    source["parent_check"] = build_parent_check(scope, leaves, parents)
    source["current_portion"] = build_current_portion(wp_code, prefill)
    source["tb_source"] = tb.get("source")
    source["empty_reason"] = None

    return {
        "trial_balance": tb,
        "tb_source_codes": source,
        "adjudication_prefill": prefill,
        "l_bucket_defs": bucket_defs_payload(wp_code),
    }


__all__ = [
    "build_adjudication_prefill",
    "build_current_portion",
    "build_l_tb_payload",
    "build_parent_check",
]
