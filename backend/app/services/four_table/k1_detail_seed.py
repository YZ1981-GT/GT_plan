"""K1-3 坏账准备明细表 ← `tb_balance` 备抵科目叶子（transient seed，纯函数为主）.

备抵科目（实证标准码 `1231-03` / 原始码 `1231.03`）在 `tb_balance` 里是**贷方备抵**：

    期末备抵 = 期初备抵 + 贷方发生额（计提）− 借方发生额（转回/核销）

故可干净映射到 K1-3 主行的 `priorBook` / `currentProvision` / `currentReversal`。
**三阶段拆分不做 seed**（客户科目表无信用风险阶段维度，阶段划分来自 K1-7）——
宁缺勿造，避免把全额堆进第一阶段造成假披露。

与 D1 的 `d_cycle_extraction/d1_detail_seed.py` 同款范式：transient seed 写进 render 的
`responses_snapshot`，前端零改动即可消费；已有手工数据不覆盖；fail-open。

spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
"""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

logger = logging.getLogger(__name__)

#: K1-3 持久化键（前端 `useK1BadDebt.STORAGE_KEY`）
K1_BAD_DEBT_ITEM_ID = "K1-3-baddebt-rows"

#: 金额比较容差（元）
_EPS = 0.005


def _round2(n: float) -> float:
    return round(float(n or 0) * 100) / 100


def _fixed_row(category: str, label: str, **over: float) -> dict:
    """构造 K1-3 固定主行（字段名逐字对齐前端 `K1BadDebtMainRow`）。"""
    row: dict[str, Any] = {
        "id": f"fixed-{category}",
        "category": category,
        "label": label,
        "isSubRow": False,
        "isFixed": True,
        "priorBook": 0.0,
        "priorAdj": 0.0,
        "priorAudited": 0.0,
        "currentProvision": 0.0,
        "currentOtherIncrease": 0.0,
        "currentReversal": 0.0,
        "currentWriteOff": 0.0,
        "currentOtherDecrease": 0.0,
        "currentBook": 0.0,
        "currentAdj": 0.0,
        "currentAudited": 0.0,
        "reason": "",
    }
    row.update({k: _round2(v) for k, v in over.items()})
    # 与前端 `recalcK1BadDebtMainRow` 同口径派生（保证首屏与重算后一致）
    row["priorAudited"] = _round2(row["priorBook"] + row["priorAdj"])
    row["currentBook"] = _round2(
        row["priorAudited"]
        + row["currentProvision"]
        + row["currentOtherIncrease"]
        - row["currentReversal"]
        - row["currentWriteOff"]
        - row["currentOtherDecrease"]
    )
    row["currentAudited"] = _round2(row["currentBook"] + row["currentAdj"])
    return row


def build_k1_bad_debt_seed_from_tb(
    leaves: Sequence[Any],
    provision_prefixes: Sequence[str],
    *,
    aggregate: Any = None,
) -> dict | None:
    """备抵叶子 → K1-3 payload（`mainRows` 三行；不含 `stageMovements`）。

    Args:
        leaves: `four_table.leaf_aggregation.LeafRow` 序列（已 `select_leaves`）。
        provision_prefixes: 备抵侧原始码前缀（`tb_source_codes.provision`）。
        aggregate: 注入点，缺省用 `leaf_aggregation.aggregate_leaves`（单测可注入）。

    Returns:
        ``{"version": 2, "mainRows": [...], "_seeded_from": "tb_balance"}``；
        无数据（全零）返回 ``None``（宁缺勿造）。

    不变量（Property 3）：``priorAudited + currentProvision − currentReversal
    == 期末备抵``（差额记入 `currentOtherIncrease` / `currentOtherDecrease` 兜住）。
    """
    if not leaves or not provision_prefixes:
        return None
    if aggregate is None:
        from app.services.four_table.leaf_aggregation import aggregate_leaves as aggregate

    agg = aggregate(leaves, provision_prefixes, absolute=True)
    opening = _round2(agg.get("opening", 0.0))
    closing = _round2(agg.get("closing", 0.0))
    # 贷方 = 计提（备抵增加）；借方 = 转回/核销（备抵减少）
    provision = _round2(agg.get("credit", 0.0))
    reversal = _round2(agg.get("debit", 0.0))

    if all(abs(v) < _EPS for v in (opening, closing, provision, reversal)):
        return None

    # roll-forward 兜底：残差进「其他增加/其他减少」，保证期末账面 == tb 期末备抵
    residual = _round2(closing - (opening + provision - reversal))
    other_increase = residual if residual > _EPS else 0.0
    other_decrease = -residual if residual < -_EPS else 0.0

    portfolio = _fixed_row(
        "portfolio",
        "按组合计提",
        priorBook=opening,
        currentProvision=provision,
        currentReversal=reversal,
        currentOtherIncrease=other_increase,
        currentOtherDecrease=other_decrease,
    )
    total = _fixed_row(
        "total",
        "合计",
        priorBook=opening,
        currentProvision=provision,
        currentReversal=reversal,
        currentOtherIncrease=other_increase,
        currentOtherDecrease=other_decrease,
    )
    return {
        "version": 2,
        "mainRows": [
            _fixed_row("individual", "单项评估计提"),
            portfolio,
            total,
        ],
        # 溯源标记：供 UI 提示「本表未审数由四表库带入，请按 K1-7/K1-8 复核阶段拆分」
        "_seeded_from": "tb_balance",
        "_seeded_provision_codes": list(provision_prefixes),
    }


def _has_manual_bad_debt(raw: Any) -> bool:
    """K1-3 是否已有手工数据（任一主行金额非零 或 存在单项子行）。"""
    if raw in (None, "", "null"):
        return False
    parsed: Any = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return False
    if not isinstance(parsed, dict):
        return bool(parsed)
    rows = parsed.get("mainRows")
    if not isinstance(rows, list):
        return False
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("isSubRow"):
            return True
        for key in (
            "priorBook", "priorAdj", "currentProvision", "currentOtherIncrease",
            "currentReversal", "currentWriteOff", "currentOtherDecrease", "currentAdj",
        ):
            try:
                if abs(float(r.get(key) or 0)) >= _EPS:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def seed_k1_bad_debt(responses_snapshot: dict, payload: dict | None) -> bool:
    """把 K1-3 seed 写进 `responses_snapshot`（**手工优先**，已有数据不覆盖）。

    Returns:
        是否实际写入（供守卫断言 / 日志）。
    """
    if not payload:
        return False
    existing = (responses_snapshot or {}).get(K1_BAD_DEBT_ITEM_ID) or {}
    raw = existing.get("remark") or existing.get("conclusion") or ""
    if _has_manual_bad_debt(raw):
        return False
    try:
        responses_snapshot[K1_BAD_DEBT_ITEM_ID] = {
            "conclusion": existing.get("conclusion") or "",
            "remark": json.dumps(payload, ensure_ascii=False),
        }
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("K1-3 seed 写入失败: %s", e)
        return False
    return True
