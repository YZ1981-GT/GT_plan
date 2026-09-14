"""G 循环审定表「从四表库带入未审数」的统一预填载荷构建 —— 跨 G1~G14 单一真源。

**为什么下发逐叶子明细而不是预聚合的桶**

平台铁律：*预聚合是有损表示，凡下游可改归属的分类结果都必须下发逐项明细*
（E1 受限资金实证）。G 循环的审定表行维度普遍**比四表能提供的信息更细**：

- G1-1 是 ``(投资成本 / 累计公允价值变动) × (交易性 / 划分为 / 指定为) × 7 品种``
  —— 「交易性 / 划分为 / 指定为」是**会计判断**，四表里没有；
- G2-1 是 ``(原值 / 坏账准备) × (单项计提 / 按组合计提)``
  —— 计提方法同样是判断；且坏账在 ``1231`` 族、不在 ``1132``；
- G11-1 是 18 行投资收益细目（权益法收益 / 处置收益 / 持有期间利息 …）
  —— 只有客户恰好按此设了子科目才可能对上。

若在后端把叶子按某套桶预聚合再下发，审计师在前端改了某笔的归属就**无法重算**
（载荷里没有逐笔金额）。故本模块只**如实下发每个叶子的金额与所属语义槽**。

**为什么「叶子 → 审定表行」的建议归类在前端做**

审定表的 rowKey 分类体系（`g11Constants.G11_ADJUDICATION_ITEMS` 等）是**前端资产**。
在后端再写一份 rowKey 字面量就是跨语言双真源，改一侧必漏另一侧。故建议归类由
`composables/gCycleAdjudicationSeed.ts` 按科目名做，未命中的叶子进「待归类」面板
由审计师分配 —— 绝不兜底塞进「其他」行凑数。

**损益类的口径**

``G_PL_CYCLES``（G11~G14）的未审数是**本期发生额**，不是期末余额：实证
``tb_balance.closing_balance`` 在 6101/6111/6701/6702 全项目全为 0（含年末结转损益的
全年账，损益类余额结转后归零）。且「Σ借 − Σ贷」在这类账上**结构性恒为 0**
（必有结转损益分录使借贷两侧相等）→ 本模块按 ``G_PL_POSITIVE_SIDE`` 声明的
**正方向单侧**取数（收益类取贷方、损失类取借方），与 `trial_balance` 的
``本期发生额`` 口径一致。

**兼容两种科目定位结果**

G 循环的主 render 目前**两种定位件并存**（Wave 2 只迁了 G6/G8/G9/G14）：
`SemanticAccountResult`（语义驱动，有 ``slots``）与 `ReportLineAccounts`
（报表行驱动，只有扁平 ``gross`` / ``provision``）。:func:`normalize_slots`
把两者归一成同一槽视图，故本模块无需等 Wave 2 迁移完成即可接入。

spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
      Requirements 3.3, 3.4, 3.5 / Task 3.3
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .g_cycle_specs import G_PL_CYCLES, G_PL_POSITIVE_SIDE, spec_of
from .leaf_aggregation import LeafRow, filter_by_prefixes, parent_totals, select_leaves

#: 金额四舍五入位数（分）
_ROUND = 2

#: 期间口径标识（前端据此决定写「期初/期末未审」还是「本期未审」）
PERIOD_BALANCE = "balance"
PERIOD_CURRENT = "current"


def _r(v: float) -> float:
    return round(float(v or 0), _ROUND)


@dataclass(frozen=True)
class SlotView:
    """槽的最小视图（两种定位结果归一后的形态）。"""

    key: str
    label: str
    is_provision: bool = False
    codes: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(self.codes)


def normalize_slots(accounts) -> dict[str, SlotView]:
    """把 `SemanticAccountResult` 或 `ReportLineAccounts` 归一为 ``{key: SlotView}``。

    - 语义结果：直接取 ``slots``（保持声明序）。
    - 报表行结果：合成 ``gross`` / ``provision`` 两槽（``provision`` 仅在非空时出现）。

    未知类型 / ``None`` 返回 ``{}``（fail-open，调用方据此返空预填）。
    """
    if accounts is None:
        return {}
    slots = getattr(accounts, "slots", None)
    if isinstance(slots, dict) and slots:
        out: dict[str, SlotView] = {}
        for key, slot in slots.items():
            out[str(key)] = SlotView(
                key=str(key),
                label=str(getattr(slot, "label", "") or ""),
                is_provision=bool(getattr(slot, "is_provision", False)),
                codes=[str(c) for c in (getattr(slot, "codes", None) or [])],
            )
        return out
    gross = [str(c) for c in (getattr(accounts, "gross", None) or [])]
    provision = [str(c) for c in (getattr(accounts, "provision", None) or [])]
    out = {}
    # 🔴 label 用中性措辞：`ReportLineAccounts` 路径不区分资产 / 损益，
    #    写「原值」会让 G11~G14 这类损益循环在提示里显示「原值 本项目无此科目」。
    if gross:
        out["gross"] = SlotView(key="gross", label="本科目", codes=gross)
    if provision:
        out["provision"] = SlotView(
            key="provision", label="备抵科目", is_provision=True, codes=provision
        )
    return out


def pl_occurrence(leaf: LeafRow, positive_side: str) -> float:
    """损益类叶子的**本期发生额**（按声明的正方向单侧取数）。

    Args:
        leaf: `tb_balance` 叶子行。
        positive_side: ``'credit'``（收益类，如投资收益）或 ``'debit'``
            （损失类，如信用减值损失）。

    Returns:
        正方向金额。🔴 **不用** ``debit - credit`` —— 含年末结转损益的全年账上
        两侧恒相等，差额结构性为 0。
    """
    return _r(leaf.credit if positive_side == "credit" else leaf.debit)


def balance_amounts(leaf: LeafRow, *, is_provision: bool) -> tuple[float, float]:
    """资产 / 负债类叶子的期初、期末金额。

    备抵槽取 ``abs()`` —— `tb_balance` 对备抵科目存在两种符号约定
    （实证 G7 的 ``1512`` 期末存 ``-4,790,032.97``），而审定表「减值准备」段是
    **正数口径**，不归一会让减值列显示负数、与原值段方向相反。
    """
    opening, closing = _r(leaf.opening), _r(leaf.closing)
    if is_provision:
        return abs(opening), abs(closing)
    return opening, closing


def slot_of_code(slots: dict[str, SlotView], code: str) -> str | None:
    """某原始码属于哪个语义槽（按**最长前缀**归属）。

    🔴 多槽可能声明同一前缀（原值与备抵常在同一族），故取最长命中前缀；长度相同时
    保持槽声明顺序（``slots`` 是插入序 dict，先声明者优先）。
    """
    best: tuple[int, str] | None = None
    for key, slot in (slots or {}).items():
        for prefix in slot.codes or []:
            if code == prefix or code.startswith(prefix + "."):
                if best is None or len(prefix) > best[0]:
                    best = (len(prefix), key)
    return None if best is None else best[1]


def build_g_adjudication_prefill(wp_code: str, accounts, rows: list[LeafRow]) -> dict:
    """构建 G 循环审定表预填载荷。

    Args:
        wp_code: ``G1`` ~ ``G14``（决定期间口径与损益正方向）。
        accounts: `SemanticAccountResult` 或 `ReportLineAccounts`
            （见 :func:`normalize_slots`）。
        rows: `tb_balance` **整棵子树**（含父行，供叶子判定与父额勾稽）。

    Returns:
        ``{}``（未登记 wp_code / 无槽命中 / 无有值叶子时，宁缺勿造）或::

            {
              "period": "balance" | "current",
              "positive_side": "debit" | "credit" | "",
              "slots": {slot_key: {label, found, is_provision, codes,
                                   opening, closing, current}},
              "leaves": [{code, name, slot, opening, closing, current}],
              "total": {opening, closing, current},
              "parent_check": {leaf_sum, parent, diff} | None,
            }
    """
    code = str(wp_code or "").strip().upper()
    if spec_of(code) is None:
        return {}

    is_pl = code in G_PL_CYCLES
    positive_side = G_PL_POSITIVE_SIDE.get(code, "") if is_pl else ""

    slots = normalize_slots(accounts)
    all_prefixes: list[str] = []
    for slot in slots.values():
        for p in slot.codes:
            if p not in all_prefixes:
                all_prefixes.append(p)
    if not all_prefixes:
        # 本项目没有这一族科目 —— 返空由前端显示「四表库暂无该科目数据」
        return {}

    leaves = filter_by_prefixes(select_leaves(rows or []), all_prefixes)

    slot_totals: dict[str, dict] = {
        key: {
            "label": slot.label,
            "found": slot.found,
            "is_provision": slot.is_provision,
            "codes": list(slot.codes),
            "opening": 0.0,
            "closing": 0.0,
            "current": 0.0,
        }
        for key, slot in slots.items()
    }

    leaf_payload: list[dict] = []
    for leaf in leaves:
        slot_key = slot_of_code(slots, leaf.account_code)
        if slot_key is None:
            continue
        is_provision = slots[slot_key].is_provision
        if is_pl:
            current = pl_occurrence(leaf, positive_side)
            opening = closing = 0.0
            # 损益类本期无发生额的叶子不下发（避免用零行淹没「待归类」面板）
            if current == 0:
                continue
        else:
            current = 0.0
            opening, closing = balance_amounts(leaf, is_provision=is_provision)
            if opening == 0 and closing == 0:
                continue
        leaf_payload.append({
            "code": leaf.account_code,
            "name": leaf.account_name,
            "slot": slot_key,
            "opening": opening,
            "closing": closing,
            "current": current,
        })
        bucket = slot_totals[slot_key]
        bucket["opening"] = _r(bucket["opening"] + opening)
        bucket["closing"] = _r(bucket["closing"] + closing)
        bucket["current"] = _r(bucket["current"] + current)

    if not leaf_payload:
        return {}

    total = {
        "opening": _r(sum(x["opening"] for x in leaf_payload)),
        "closing": _r(sum(x["closing"] for x in leaf_payload)),
        "current": _r(sum(x["current"] for x in leaf_payload)),
    }

    # 「叶子和 == 父额」自检（只在单前缀且父行有值时可判）
    parent_check = None
    if not is_pl and len(all_prefixes) == 1:
        parent = parent_totals(rows or [], all_prefixes[0])
        if parent.get("closing", 0) or parent.get("opening", 0):
            leaf_sum = _r(sum(x["closing"] for x in leaf_payload))
            parent_closing = _r(parent.get("closing", 0))
            parent_check = {
                "leaf_sum": leaf_sum,
                "parent": parent_closing,
                "diff": _r(leaf_sum - parent_closing),
            }

    return {
        "period": PERIOD_CURRENT if is_pl else PERIOD_BALANCE,
        "positive_side": positive_side,
        "slots": slot_totals,
        "leaves": leaf_payload,
        "total": total,
        "parent_check": parent_check,
    }


__all__ = [
    "PERIOD_BALANCE",
    "PERIOD_CURRENT",
    "SlotView",
    "balance_amounts",
    "build_g_adjudication_prefill",
    "normalize_slots",
    "pl_occurrence",
    "slot_of_code",
]
