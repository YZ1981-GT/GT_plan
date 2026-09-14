"""I 类循环的四表预填构建（纯函数，零 IO）。

把「分段科目定位」（:mod:`.i_cycle_accounts`）+「叶子聚合」（:mod:`.leaf_aggregation`）
拼成审定表 / 披露表可直接消费的行集。

**动态口径三条**

1. **段方向按声明**：备抵段（``credit_is_increase=True``）的增加取 ``credit``、减少取
   ``debit``；原值段相反。备抵段对聚合结果取 ``abs()``（``absolute=True``）。
2. **类别按项目实际叶子名派生**：默认 11 类来自 :mod:`.i1_asset_categories`，但项目若有
   第 12 类（如 ``无形资产_排污权``），:func:`build_i1_category_rows` 会**新建一个
   ``custom:排污权`` 行**并跨三段对齐，而不是静默塞进「其他」。
3. **宁缺勿造**：段无科目 / 无命中叶子 → 不产生行，不产生 0 占位。

**为什么类别键要从名称后缀派生**

同一类别在三段里是三个不同科目码（``1701.01`` / ``1702.01`` / ``1703.01``），要让三段的
类别行对齐只能用**名称后缀**做键。且客户编码顺序跨项目不同（平台已有 `6403` 税种、
`1405/1406` 存货编码冲突实证），编码不能当键。

spec: .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/
      Requirements 2.1 / 2.2 / 3.3 / 4.1~4.5，Property 1 / 4 / 5
"""
from __future__ import annotations

from .i1_asset_categories import CATEGORY_OTHER, category_label, classify_i1_leaf
from .i_cycle_accounts import ICycleAccounts, ISegmentAccounts
from .leaf_aggregation import LeafRow, aggregate_leaves, filter_by_prefixes, parent_totals

#: 动态类别键前缀（项目自有类别，非平台默认 11 类）
CUSTOM_CATEGORY_PREFIX = "custom:"

#: 金额比较容差（元）
TOLERANCE = 0.01


def _round(v: float) -> float:
    return round(float(v or 0.0), 2)


def leaf_label(name: str, fallback: str = "") -> str:
    """从 `tb_balance.account_name` 取展示标签 —— 末级下划线后缀。纯函数。

    ``无形资产_土地使用权`` → ``土地使用权``；``长期待摊费用_装修费`` → ``装修费``；
    无下划线时原样返回；空名返回 ``fallback``（通常传科目码）。
    """
    nm = str(name or "").strip()
    if not nm:
        return str(fallback or "").strip()
    for sep in ("_", "－", "-"):
        if sep in nm:
            tail = nm.rsplit(sep, 1)[-1].strip()
            if tail:
                return tail
    return nm


def segment_amounts(
    leaves: list[LeafRow], seg: ISegmentAccounts
) -> dict[str, float]:
    """某段的聚合金额（按段的方向语义产出 increase / decrease）。纯函数。

    Returns:
        ``{"opening","closing","increase","decrease","debit","credit"}``；
        段无科目时全 0。
    """
    if not seg.original:
        return {k: 0.0 for k in ("opening", "closing", "increase", "decrease", "debit", "credit")}
    agg = aggregate_leaves(leaves, seg.original, absolute=seg.absolute)
    debit, credit = agg["debit"], agg["credit"]
    increase, decrease = (credit, debit) if seg.credit_is_increase else (debit, credit)
    return {
        "opening": _round(agg["opening"]),
        "closing": _round(agg["closing"]),
        "increase": _round(increase),
        "decrease": _round(decrease),
        "debit": _round(debit),
        "credit": _round(credit),
    }


def build_parent_check(
    all_rows: list[LeafRow],
    leaves: list[LeafRow],
    accounts: ICycleAccounts,
) -> dict[str, dict[str, float]]:
    """「叶子和 == 父科目行金额」自检（R3.3 / Property 1）。纯函数。

    Returns:
        ``{原始码: {"leaf_sum","parent","diff"}}``。父行不存在时 ``parent`` 为 0，
        此时 ``diff`` 等于叶子和 —— 调用方据 ``abs(diff) > TOLERANCE`` 提示。
    """
    out: dict[str, dict[str, float]] = {}
    for seg in accounts.segments:
        for code in seg.original:
            if code in out:
                continue
            leaf_sum = aggregate_leaves(leaves, [code], absolute=seg.absolute)["closing"]
            par = parent_totals(all_rows, code)["closing"]
            if seg.absolute:
                par = abs(par)
            out[code] = {
                "leaf_sum": _round(leaf_sum),
                "parent": _round(par),
                "diff": _round(leaf_sum - par),
            }
    return out


def _category_key_of(name: str, code: str) -> tuple[str, str]:
    """叶子 →（类别键, 展示标签）。未命中默认 11 类则派生 ``custom:{后缀}``。纯函数。"""
    hit = classify_i1_leaf(name, code)
    if hit:
        return hit, category_label(hit)
    label = leaf_label(name, code)
    return f"{CUSTOM_CATEGORY_PREFIX}{label}", label


def build_i1_category_rows(
    leaves: list[LeafRow],
    accounts: ICycleAccounts,
    *,
    default_keys: list[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """I1 三段 × 类别的预填行（跨段类别对齐）。纯函数。

    Args:
        leaves: 已 `select_leaves` 的叶子行。
        accounts: :func:`.i_cycle_accounts.resolve_i_cycle_accounts` 的结果。
        default_keys: 默认类别键序列（`i1_asset_categories.default_category_keys()`）。
            仅用于**排序**；不在四表里出现的默认类别**不会**产生空行（宁缺勿造）。

    Returns:
        ``(segments, unmapped)``：

        - ``segments``: ``[{"segment","label","rows":[{key,label,codes,opening,closing,
          increase,decrease}, ...]}, ...]``，段序 = 声明序。
        - ``unmapped``: 未命中默认 11 类的叶子科目码（供溯源面板列出，R4.2）。
    """
    order = list(default_keys or [])
    order_index = {k: i for i, k in enumerate(order)}
    unmapped: list[str] = []
    out_segments: list[dict] = []

    for seg in accounts.segments:
        if not seg.original:
            continue
        picked = filter_by_prefixes(leaves, seg.original)
        buckets: dict[str, dict] = {}
        for row in picked:
            key, label = _category_key_of(row.account_name, row.account_code)
            if key.startswith(CUSTOM_CATEGORY_PREFIX) and row.account_code not in unmapped:
                unmapped.append(row.account_code)
            b = buckets.setdefault(
                key,
                {
                    "key": key,
                    "label": label,
                    "codes": [],
                    "opening": 0.0,
                    "closing": 0.0,
                    "debit": 0.0,
                    "credit": 0.0,
                },
            )
            if row.account_code not in b["codes"]:
                b["codes"].append(row.account_code)
            b["opening"] += row.opening
            b["closing"] += row.closing
            b["debit"] += row.debit
            b["credit"] += row.credit

        rows: list[dict] = []
        for b in buckets.values():
            debit, credit = b["debit"], b["credit"]
            increase, decrease = (credit, debit) if seg.credit_is_increase else (debit, credit)
            sign = abs if seg.absolute else (lambda v: v)
            rows.append(
                {
                    "key": b["key"],
                    "label": b["label"],
                    "codes": b["codes"],
                    "opening": _round(sign(b["opening"])),
                    "closing": _round(sign(b["closing"])),
                    "increase": _round(sign(increase)),
                    "decrease": _round(sign(decrease)),
                }
            )
        rows.sort(
            key=lambda r: (
                order_index.get(r["key"], len(order) + 1),
                0 if r["key"] != CATEGORY_OTHER else 1,
                r["label"],
            )
        )
        if rows:
            out_segments.append(
                {"segment": seg.segment, "label": seg.label, "rows": rows}
            )
    return out_segments, unmapped


def build_leaf_project_rows(
    leaves: list[LeafRow], seg: ISegmentAccounts
) -> list[dict]:
    """按叶子科目逐行产出项目行（I4 长期待摊费用 / I2 / I3 / I5 通用）。纯函数。

    每个叶子一行，标签取名称后缀（``长期待摊费用_装修费`` → ``装修费``）。
    段无科目或无命中叶子 → 返回 ``[]``（宁缺勿造）。
    """
    if not seg.original:
        return []
    picked = filter_by_prefixes(leaves, seg.original)
    merged: dict[str, dict] = {}
    for row in picked:
        label = leaf_label(row.account_name, row.account_code)
        b = merged.setdefault(
            label,
            {
                "key": row.account_code,
                "label": label,
                "codes": [],
                "opening": 0.0,
                "closing": 0.0,
                "debit": 0.0,
                "credit": 0.0,
            },
        )
        if row.account_code not in b["codes"]:
            b["codes"].append(row.account_code)
        b["opening"] += row.opening
        b["closing"] += row.closing
        b["debit"] += row.debit
        b["credit"] += row.credit

    out: list[dict] = []
    for b in merged.values():
        debit, credit = b["debit"], b["credit"]
        increase, decrease = (credit, debit) if seg.credit_is_increase else (debit, credit)
        sign = abs if seg.absolute else (lambda v: v)
        out.append(
            {
                "key": b["key"],
                "label": b["label"],
                "codes": sorted(b["codes"]),
                "opening": _round(sign(b["opening"])),
                "closing": _round(sign(b["closing"])),
                "increase": _round(sign(increase)),
                "decrease": _round(sign(decrease)),
            }
        )
    out.sort(key=lambda r: r["codes"][0] if r["codes"] else r["label"])
    return out


def build_adjudication_prefill(
    leaves: list[LeafRow],
    accounts: ICycleAccounts,
    *,
    default_category_keys: list[str] | None = None,
) -> dict | None:
    """审定表未审数预填（六循环统一入口）。纯函数。

    I1 走类别维度（三段 × 类别）；其余循环走叶子项目行。全空则返回 ``None``
    —— render 据此**不输出** `adjudication_prefill` 键（R4.5 宁缺勿造）。
    """
    if accounts.wp_code == "I1":
        segments, unmapped = build_i1_category_rows(
            leaves, accounts, default_keys=default_category_keys
        )
        if not segments:
            return None
        return {"mode": "category", "segments": segments, "unmapped": unmapped}

    segments = []
    for seg in accounts.segments:
        rows = build_leaf_project_rows(leaves, seg)
        totals = segment_amounts(leaves, seg)
        if not rows and not any(totals.values()):
            continue
        segments.append(
            {
                "segment": seg.segment,
                "label": seg.label,
                "rows": rows,
                "totals": totals,
            }
        )
    if not segments:
        return None
    return {"mode": "leaf", "segments": segments, "unmapped": []}


def build_tb_values(
    leaves: list[LeafRow], accounts: ICycleAccounts, key_map: dict[str, str]
) -> dict[str, float]:
    """按段产出既有 `tb_values` 键（键名由调用方给，保持前端零改动）。纯函数。

    Args:
        key_map: ``{段键: tb_values 键前缀}``，如 ``{'cost': 'cost_unadjusted'}``；
            产出 ``{前缀}_opening`` / ``_closing`` / ``_debit`` / ``_credit``。
    """
    out: dict[str, float] = {}
    for seg in accounts.segments:
        prefix = key_map.get(seg.segment)
        if not prefix:
            continue
        amt = segment_amounts(leaves, seg)
        out[f"{prefix}_opening"] = amt["opening"]
        out[f"{prefix}_closing"] = amt["closing"]
        out[f"{prefix}_debit"] = amt["debit"]
        out[f"{prefix}_credit"] = amt["credit"]
        out[f"{prefix}_increase"] = amt["increase"]
        out[f"{prefix}_decrease"] = amt["decrease"]
    return out


__all__ = [
    "CUSTOM_CATEGORY_PREFIX",
    "TOLERANCE",
    "build_adjudication_prefill",
    "build_i1_category_rows",
    "build_leaf_project_rows",
    "build_parent_check",
    "build_tb_values",
    "leaf_label",
    "segment_amounts",
]
