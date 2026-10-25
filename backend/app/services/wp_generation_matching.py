"""按试算表科目选要生成的底稿（纯函数，无 DB / IO）。

调用方：`chain_orchestrator._step_generate_workpapers`（全链路「生成底稿」步骤）；守卫
`tests/test_wp_account_mapping_single_source.py` 用真实映射表钉住读取方行为。

spec: .kiro/specs/formula-fetch-followup-defect-closure/ R1.6
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


_KEY_FLAG_PREFIX: dict[str, str] = {
    "business_category": "biz_",
    "industry": "ind_",
}


def _normalize_text(value: object) -> str:
    """将业务分类、模板类型和声明值归一化为可比较的小写文本。"""
    if value is None:
        return ""
    return str(value).strip().lower()


def business_category_flags(
    business_category: str | None,
    template_type: str | None,
) -> dict[str, bool]:
    """根据项目业务分类和模板类型生成适用性 flags。

    业务分类可能为空或带大小写/外围空白；分类采用既有的关键字包含语义。
    ``template_type='listed'`` 是独立的上市模板信号，因而即使业务分类为空或为
    ``C``，也必须令 ``biz_listed`` 为真。
    """
    category = _normalize_text(business_category)
    template = _normalize_text(template_type)
    return {
        "biz_ipo": "ipo" in category,
        "biz_listed": "listed" in category or template == "listed",
        "biz_neeq": "neeq" in category,
        "biz_refinancing": "refinancing" in category,
    }


def applicable_when_hit(
    applicable_when: Mapping[str, Any] | None,
    flags: Mapping[str, bool] | None,
    *,
    key_filter: Iterable[str] | None = None,
) -> bool:
    """按 ``applicable_when`` 声明判断是否命中。

    字典键之间、同一键的值之间都是 OR 关系。已知键映射到对应 flag 前缀
    （``business_category`` → ``biz_``、``industry`` → ``ind_``）；未知键仍按
    ``<key>_`` 约定查找，找不到对应 flag 时自然未命中。``key_filter`` 只限制
    参与计算的声明键，不改变声明内的值 OR 语义。
    """
    if not isinstance(applicable_when, Mapping) or not isinstance(flags, Mapping):
        return False

    if key_filter is None:
        selected_keys: set[str] | None = None
    elif isinstance(key_filter, str):
        selected_keys = {key_filter}
    else:
        selected_keys = set(key_filter)

    if selected_keys is not None and not selected_keys:
        return False

    for key, raw_values in applicable_when.items():
        if selected_keys is not None and key not in selected_keys:
            continue

        prefix = _KEY_FLAG_PREFIX.get(key, f"{key}_")
        if raw_values is None:
            continue
        if isinstance(raw_values, str):
            values = (raw_values,)
        else:
            try:
                values = iter(raw_values)
            except TypeError:
                values = (raw_values,)

        for value in values:
            if value is None:
                continue
            suffix = _normalize_text(value)
            if suffix and flags.get(f"{prefix}{suffix}", False):
                return True

    return False


def _lease_codes() -> tuple[str, ...]:
    from app.services.four_table.dual_family_codes import codes_for_slot

    return codes_for_slot("gross") + codes_for_slot("lease_liability")


#: 试算表标准码 → 条件生成开关（映射表 `applies_when` 引用）。
#: 🔴 2026-10-24 改正：has_lease 原取 1631（油气资产）/ 2802（全库不存在）⇒ 改取使用权资产 / 租赁负债双族
#:   1641·1651 / 2601·2651（`dual_family_codes`）；has_rd 原取 5401（standard 侧是主营业务成本）⇒
#:   改取 6604 研发费用 + 1704 开发支出（5301 在两套科目表里分别是研发支出 / 营业外收入，不用）。
TB_ACCOUNT_FLAGS: dict[str, str] = {
    "1001": "has_cash", "1002": "has_cash", "1012": "has_cash",
    "1122": "has_revenue", "6001": "has_revenue",
    "1401": "has_inventory", "1402": "has_inventory", "1403": "has_inventory",
    "1511": "has_investment", "1101": "has_investment",
    "1601": "has_fixed_assets", "1602": "has_fixed_assets",
    "1604": "has_construction",
    "1701": "has_intangibles", "1702": "has_intangibles",
    "6604": "has_rd", "1704": "has_rd",
    "2001": "has_debt", "2501": "has_debt",
    **{code: "has_lease" for code in _lease_codes()},
}


def tb_account_flags(tb_accounts: set[str]) -> dict[str, bool]:
    """试算表里出现的标准码 → 应打开的循环开关（只返回为 True 的开关）。"""
    return {flag: True for acc in tb_accounts if (flag := TB_ACCOUNT_FLAGS.get(acc))}


def match_workpapers(
    mappings: list[dict[str, Any]],
    tb_accounts: set[str],
    project_flags: dict[str, bool],
) -> tuple[set[str], dict[str, list[str]]]:
    """按映射表选要生成的底稿。返回 (主编码集合, 主编码 → 命中的子表编码)。

    - 有 ``account_codes`` 的条目（D~N）：试算表有其中任一标准码即命中（**精确等值**，
      ``1606B`` 这类试算表里不存在的写法永远命中不了，故映射码须与口径单一来源一致）；
    - 否则看 ``trigger``：``must_have`` 恒命中；``conditional`` 看 ``applies_when`` 开关。
    - 有 ``applicable_when`` 的条目按共享 predicate 计算，字典键和值均为 OR。
    子表（D2-2 / E1-1）折叠到主编码（D2 / E1）。
    """
    matched_primary: set[str] = set()
    matched_subtable_info: dict[str, list[str]] = {}
    for m in mappings:
        wp_code = m.get("wp_code", "")
        if not wp_code:
            continue
        primary_code = wp_code.split("-")[0] if "-" in wp_code else wp_code
        is_subtable = wp_code != primary_code

        account_codes = m.get("account_codes", [])
        if account_codes and any(acc in tb_accounts for acc in account_codes):
            hit = True
        elif m.get("trigger") == "must_have":
            hit = True
        elif m.get("trigger") == "conditional":
            applies_when = m.get("applies_when")
            hit = bool(applies_when and project_flags.get(applies_when))
        elif m.get("applicable_when"):
            hit = applicable_when_hit(m["applicable_when"], project_flags)
        else:
            hit = False
        if hit:
            matched_primary.add(primary_code)
            if is_subtable:
                matched_subtable_info.setdefault(primary_code, []).append(wp_code)
    return matched_primary, matched_subtable_info


__all__ = [
    "TB_ACCOUNT_FLAGS",
    "applicable_when_hit",
    "business_category_flags",
    "match_workpapers",
    "tb_account_flags",
]
