"""`tb_balance` 叶子科目聚合（跨循环共享，纯函数）。

**为什么必须是「叶子」而不是「最深层级」**

客户科目表是**参差的多级树**：同一父科目下，有的子科目还有孙科目，有的没有。实证项目
`0ec33ac9`/2025 的 `1221 其他应收款`::

    1221                      父（= 269,885,933.03）
    ├─ 1221.11 个人往来        叶子（3,597,359.45）        ← 无子科目
    ├─ 1221.12 保证金及押金    叶子（55,035,942.52）       ← 无子科目
    ├─ 1221.13 代收代付款项    非叶子
    │   ├─ 1221.13.01 …       叶子
    │   └─ …
    ├─ 1221.15 资金往来        非叶子 → 1221.15.01/.02/.04/.06/.08 叶子
    └─ 1221.98 其他            非叶子 → 1221.98.01…99 叶子

「只取最深层级（depth == max_depth）」会**整段丢掉** `1221.11` 与 `1221.12`
（合计 58,633,301.97 = 21.7%），而这两支恰好是 K1「款项性质分布」最核心的
个人往来 / 保证金押金桶 → 性质预填恒 0。正确口径 = 叶子（无子科目的最明细行），
其金额之和等于父科目行金额（Property 1，实测逐分相等）。

叶子判定与 `trial_balance_service.recalc_unadjusted` 同语义（同数据集 + 存在
`code + '.'` 前缀的兄弟行即非叶子）。

**不做方向翻转**：`trial_balance_service` 会按 `closing_direction` 把余额归一为
「借正贷负」（`debit → +ABS()`）。K1 侧**不采用** —— 实测存在 `direction='debit'`
且余额合法为负的叶子（项目 `2aa00f57` 的 `1221.98.07 = -227,132.40`），`+ABS()` 会
把它翻正，破坏「叶子和 == 父科目额」勾稽。备抵科目改在**聚合结果**上取绝对值即可
（`tb_balance` 存在「无符号 + 方向列」与「已带符号」两种约定并存，两者 `abs()` 同解）。

spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/
      Requirements 2.1~2.4 / Property 1
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeafRow:
    """`tb_balance` 单行的取数视图（只保留聚合需要的列）。"""

    account_code: str
    account_name: str = ""
    opening: float = 0.0
    closing: float = 0.0
    debit: float = 0.0
    credit: float = 0.0
    direction: str = ""
    dataset_id: str | None = None


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def to_leaf_rows(rows) -> list[LeafRow]:
    """把 SQLAlchemy Row / dict 序列归一为 :class:`LeafRow`（缺列按 0 / 空串）。"""
    out: list[LeafRow] = []
    for r in rows or []:
        get = r.get if isinstance(r, dict) else (lambda k, _r=r: getattr(_r, k, None))
        code = str(get("account_code") or "").strip()
        if not code:
            continue
        ds = get("dataset_id")
        out.append(
            LeafRow(
                account_code=code,
                account_name=str(get("account_name") or "").strip(),
                opening=_f(get("opening_balance")),
                closing=_f(get("closing_balance")),
                debit=_f(get("debit_amount")),
                credit=_f(get("credit_amount")),
                direction=str(get("closing_direction") or "").strip(),
                dataset_id=None if ds is None else str(ds),
            )
        )
    return out


def select_leaves(rows: list[LeafRow]) -> list[LeafRow]:
    """筛出叶子行：不存在以 ``本码 + '.'`` 开头的**同数据集**兄弟行。纯函数。

    同一 ``account_code`` 可能在多个 ``dataset_id`` 下各有一行（staged / active /
    superseded）；子科目须与父级同数据集才算其子科目，故按 ``dataset_id`` 分桶判定。
    调用方应先用 ``get_active_filter`` 锁定 active 数据集，此处的分桶只是兜底。
    """
    by_dataset: dict[str | None, list[LeafRow]] = {}
    for r in rows or []:
        by_dataset.setdefault(r.dataset_id, []).append(r)

    out: list[LeafRow] = []
    for _ds, group in by_dataset.items():
        codes = {r.account_code for r in group}
        for r in group:
            prefix = r.account_code + "."
            if any(c != r.account_code and c.startswith(prefix) for c in codes):
                continue
            out.append(r)
    return out


def filter_by_prefixes(rows: list[LeafRow], prefixes) -> list[LeafRow]:
    """按科目码前缀集过滤（``code == p`` 或 ``code.startswith(p + '.')``）。

    严格要求点号边界 —— 否则前缀 ``1221`` 会误命中 ``12210``（不同科目）。
    """
    ps = [str(p or "").strip() for p in (prefixes or []) if str(p or "").strip()]
    if not ps:
        return []
    out: list[LeafRow] = []
    for r in rows or []:
        code = r.account_code
        if any(code == p or code.startswith(p + ".") for p in ps):
            out.append(r)
    return out


def aggregate_leaves(
    leaves: list[LeafRow],
    prefixes,
    *,
    absolute: bool = False,
) -> dict[str, float]:
    """按前缀集过滤叶子后求和 opening / closing / debit / credit。

    Args:
        leaves: 已经 :func:`select_leaves` 过的叶子行。
        prefixes: 原始码前缀集。
        absolute: 备抵科目置 ``True`` —— 对**聚合结果**取绝对值
            （不在行级翻转，见模块 docstring）。

    Returns:
        ``{"opening","closing","debit","credit"}``；无命中行时全 0。
    """
    picked = filter_by_prefixes(leaves, prefixes)
    agg = {
        "opening": sum(r.opening for r in picked),
        "closing": sum(r.closing for r in picked),
        "debit": sum(r.debit for r in picked),
        "credit": sum(r.credit for r in picked),
    }
    if absolute:
        agg = {k: abs(v) for k, v in agg.items()}
    return agg


def parent_totals(rows: list[LeafRow], prefix: str) -> dict[str, float]:
    """取父科目行本身的金额（供「叶子和 == 父额」勾稽自检）。无该行返全 0。"""
    p = (prefix or "").strip()
    picked = [r for r in rows or [] if r.account_code == p]
    return {
        "opening": sum(r.opening for r in picked),
        "closing": sum(r.closing for r in picked),
        "debit": sum(r.debit for r in picked),
        "credit": sum(r.credit for r in picked),
    }


__all__ = [
    "LeafRow",
    "aggregate_leaves",
    "filter_by_prefixes",
    "parent_totals",
    "select_leaves",
    "to_leaf_rows",
]
