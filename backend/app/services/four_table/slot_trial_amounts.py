"""按语义槽从 `trial_balance` 取金额 —— 原值槽内混入的备抵码按报表行语义相减。

**为什么需要这个共享件**（2026-08-07 H9 真实库实测定案）

`resolve_semantic_accounts` 走**客户科目表**命中原值科目后，会经 `to_standard_codes`
反解出标准码。当客户把备抵记成原值科目的**子科目**时，一个槽会同时拿到原值码与备抵码::

    项目 c8621493 / H9 租赁负债
      tb_balance:  2651 租赁负债              credit  94,219.84   ← 父行
                   2651.01 租赁付款额         credit  98,176.48
                   2651.02 未确认融资费用      debit    3,956.64   ← 族内 contra
      account_mapping 反解:  2651 → {2601, 2602}
      ⇒ gross 槽 standard_codes = ['2601', '2602']

此时按集合**相加**求 `trial_balance` 是错的 —— 报表行语义是相减::

    report_config: BS-063 租赁负债 = TB('2601','期末余额') - TB('2602','期末余额')

    相加  98,176.48 + 3,956.64 = 102,133.12   ✗
    相减  98,176.48 − 3,956.64 =  94,219.84   ✓ = tb_balance 叶子和 = 父科目额

这个 7,913.28（= 2 × 3,956.64）的差曾被误归因为「`trial_balance` recalc 父子双算」。

**判据来源**：备抵码集合 = 全部 ``is_provision=True`` 槽认领的 ``standard_codes``。
不去解析 `report_config` 公式的符号 —— 槽定义里的 ``is_provision`` 已经是**声明式真源**
（`h{n}_account_scope.py`），比重新解析公式更稳，也不会因公式被改错而跟着错。

**零回归的结构性保证**：只有当「原值槽的 ``standard_codes`` 与某个备抵槽的
``standard_codes`` 有交集」时行为才变。原值与备抵是**独立一级科目**的循环
（H1 的 1601/1602/1603、H8 的 1641/1642/1643 旧族等）交集为空 ⇒ 逐分不变。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/ Task 18
"""
from __future__ import annotations

#: 空扣减清单（避免调用方误判 `None` 与 `[]`）
_NO_NET_OF: tuple[str, ...] = ()


def provision_standard_codes(slots) -> set[str]:
    """收集全部 ``is_provision=True`` 且 ``found=True`` 槽认领的标准码。

    Args:
        slots: ``{slot_key: ResolvedSlot}``（`SemanticAccountResult.slots`）。

    Returns:
        标准码集合；无备抵槽时为空集 ⇒ 下游 :func:`net_trial_for_slot` 退化为原样求和。
    """
    out: set[str] = set()
    for slot in (slots or {}).values():
        if not getattr(slot, "is_provision", False):
            continue
        if not getattr(slot, "found", False):
            continue
        for code in getattr(slot, "standard_codes", None) or []:
            c = str(code or "").strip()
            if c:
                out.add(c)
    return out


def net_trial_for_slot(
    slot,
    trial_map: dict[str, float],
    provision_std: set[str] | None = None,
) -> tuple[float, list[str]]:
    """按槽取 `trial_balance` 金额，原值槽内混入的备抵码相减。纯函数。

    Args:
        slot: :class:`ResolvedSlot`（需 ``standard_codes`` / ``is_provision``）。
        trial_map: ``{标准码: 金额}``（同码已累加）。
        provision_std: :func:`provision_standard_codes` 的结果；``None`` 视为空集
            ⇒ 原样求和（与引入本模块前逐字等价）。

    Returns:
        ``(金额, 被扣减的备抵标准码列表)``。第二个返回值供审计追溯展示，
        为空列表表示「原样求和」。

    Note:
        **备抵槽自身照原样求和** —— 它的码全在 ``provision_std`` 里，
        若一起减会得到负数（备抵槽的展示口径是正数）。
    """
    prov = provision_std or set()
    is_prov = bool(getattr(slot, "is_provision", False))
    total = 0.0
    net_of: list[str] = []
    for raw in getattr(slot, "standard_codes", None) or []:
        code = str(raw or "").strip()
        if not code:
            continue
        val = (trial_map or {}).get(code)
        if val is None:
            continue
        if not is_prov and code in prov:
            total -= abs(float(val))
            net_of.append(code)
        else:
            total += float(val)
    return total, net_of


__all__ = ["net_trial_for_slot", "provision_standard_codes"]
