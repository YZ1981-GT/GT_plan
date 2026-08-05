"""语义槽取数的三口径自检（`parent_check`）—— 跨循环共享纯函数。

**为什么需要三个口径而不是两个**（2026-08-03 H8 实测定论）

design 原本只要求「叶子和 vs 父科目行金额」，但真实数据暴露了第三个口径的必要性：

项目 `2aa00f57`（重庆和平药房）H8 使用权资产::

    tb_balance 叶子（1651.02）  = 176,203,072.87
    tb_balance 父行（1651）     = 176,203,072.87   ← 与叶子相等，勾稽通过
    trial_balance（1651）       = 352,406,145.74   ← **正好 2 倍**

即「叶子和 == 父额」这条勾稽**完全成立**，问题出在 `trial_balance` recalc 把
父科目 `1651` 与叶子 `1651.02` 各算了一遍（违反平台「recalc 只汇总叶子」铁律）。
只比对前两个口径**发现不了这个 1.76 亿的差异**。

故本模块同时下发三个数，三者互不相等时全部暴露，不静默取其一 ——
审计师据此判断是客户科目树被改动、数据集版本不一致，还是 recalc 双算。

**损益类循环（`occurrence=True`）**：余额口径无意义，改用 `debit`/`credit`
的正方向单侧值与 `trial_balance` 发生额对照。

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/ Requirement 3.4
"""
from __future__ import annotations

from .leaf_aggregation import (
    LeafRow,
    aggregate_leaves,
    parent_totals,
    select_leaves,
    to_leaf_rows,
)

#: 三口径互认容差（元）
TOLERANCE = 0.01


def _trial_by_code(trial_rows, field: str = "unadjusted_amount") -> dict[str, float]:
    """`trial_balance` 行 → ``{标准码: 金额}``（同码累加）。"""
    out: dict[str, float] = {}
    for row in trial_rows or []:
        get = row.get if isinstance(row, dict) else (lambda k, _r=row: getattr(_r, k, None))
        code = str(get("standard_account_code") or "").strip()
        if not code:
            continue
        out[code] = out.get(code, 0.0) + float(get(field) or 0)
    return out


def build_parent_check(
    accounts,
    tb_rows,
    trial_rows,
    slot_keys,
    *,
    occurrence: bool = False,
) -> dict[str, dict[str, float]]:
    """构造各语义槽的三口径自检。纯函数（无 DB）。

    Args:
        accounts: :class:`SemanticAccountResult`。
        tb_rows: `tb_balance` **全量**行（叶子判定需看到全部兄弟行）。
        trial_rows: `trial_balance` 行。
        slot_keys: 要检查的槽键（通常 = ``X_SLOT_KEY_PREFIX`` 的键集）。
        occurrence: 损益类置 ``True`` —— 用发生额而非期末余额。

    Returns:
        ``{slot_key: {"leaf_sum", "parent", "trial_balance",
        "diff_parent", "diff_trial", "consistent"}}``。
        某槽 ``found=False`` 时**不产生该键**（宁缺勿造，与 `tb_values` 同口径）。
    """
    all_rows: list[LeafRow] = to_leaf_rows(tb_rows)
    leaves = select_leaves(all_rows)
    trial_map = _trial_by_code(trial_rows)

    out: dict[str, dict[str, float]] = {}
    for slot_key in slot_keys:
        slot = getattr(accounts, "slots", {}).get(slot_key)
        if slot is None or not slot.found:
            continue

        agg = aggregate_leaves(leaves, slot.codes)
        if occurrence:
            # 损益类：正方向单侧（贷方为主的取 credit，借方为主取 debit）
            # 两侧都给，由调用方按科目方向选；leaf_sum 取绝对值较大的一侧
            leaf_sum = agg["credit"] if abs(agg["credit"]) >= abs(agg["debit"]) else agg["debit"]
        else:
            leaf_sum = agg["closing"]

        # tb_balance 父科目行（多码时逐个取并求和）
        parent = 0.0
        for code in slot.codes:
            pt = parent_totals(all_rows, code)
            parent += (
                (pt["credit"] if abs(pt["credit"]) >= abs(pt["debit"]) else pt["debit"])
                if occurrence
                else pt["closing"]
            )

        wanted = set(slot.standard_codes)
        trial = sum(v for c, v in trial_map.items() if c in wanted)

        diff_parent = leaf_sum - parent
        diff_trial = leaf_sum - trial
        out[slot_key] = {
            "leaf_sum": leaf_sum,
            "parent": parent,
            "trial_balance": trial,
            "diff_parent": diff_parent,
            "diff_trial": diff_trial,
            # 三口径一致（父行/trial 缺失时该侧不参与判定）
            "consistent": bool(
                (abs(diff_parent) <= TOLERANCE or parent == 0.0)
                and (abs(diff_trial) <= TOLERANCE or trial == 0.0)
            ),
        }
    return out


__all__ = ["build_parent_check", "TOLERANCE"]
