"""附注正文确定性变量替换计划。

spec: disclosure-note-doc-upload-and-batch-fill Phase 2 Task 13

仅替换明确 token 和精确来源值（公司名/年度/期间/币种/单位）；
地址/法定代表人/金额缺目标值时只 warning 不猜测。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from html import escape
from typing import Any

__all__ = [
    "ReplacementPlan",
    "ReplacementItem",
    "build_replacement_plan",
    "apply_replacement_plan",
]


@dataclass
class ReplacementItem:
    replacement_id: str
    variable: str
    old_value: str
    new_value: str
    reversible: bool = True


@dataclass
class ReplacementPlan:
    items: list[ReplacementItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── 确定性变量 token ────────────────────────────────────────────────────────

_TOKEN_VARS: tuple[tuple[str, str], ...] = (
    ("{公司名称}", "company_name"),
    ("{年度}", "year"),
    ("{报表期间}", "report_period"),
    ("{币种}", "currency"),
    ("{金额单位}", "amount_unit"),
)


def build_replacement_plan(
    html: str,
    *,
    target_vars: dict[str, Any],
    source_entity_name: str | None = None,
    scope: str = "",
) -> ReplacementPlan:
    """从 HTML 正文生成确定性替换计划。

    - token 变量（如 {公司名称}）：若目标值存在，生成替换项。
    - 来源企业名精确命中：生成替换项（目标为 target_vars["company_name"]）。
    - 地址/人名/金额等不可确定残留：只进 warning，不生成替换项。
    """
    plan = ReplacementPlan()
    if not html:
        return plan

    # 1. token 变量（正文是消毒后的 canonical HTML ⇒ 按转义形态匹配）
    for token, var_key in _TOKEN_VARS:
        if escape(token) not in html:
            continue
        target_val = target_vars.get(var_key)
        if target_val is not None and str(target_val).strip():
            plan.items.append(_item(var_key, token, str(target_val), scope))
        else:
            plan.warnings.append(f"变量 {token} 缺少目标值，保留原文")

    # 2. 来源企业名精确替换（名称可能含 & 等字符，同样按转义形态匹配）
    if source_entity_name and escape(source_entity_name) in html:
        target_name = target_vars.get("company_name")
        if target_name and str(target_name) != source_entity_name:
            plan.items.append(_item("source_entity_name", source_entity_name, str(target_name), scope))
        elif not target_name:
            plan.warnings.append(
                f"来源企业名「{source_entity_name}」存在于正文，但缺少目标企业名"
            )

    return plan


def _item(variable: str, old_value: str, new_value: str, scope: str = "") -> ReplacementItem:
    """确定性替换项 ID：apply 端按同一来源复算计划时，用户撤销的 ID 才能对上。

    ``scope``（通常为来源章节 ID）让同一 token 在不同章节有不同 ID ⇒ 撤销按章节逐项生效（AC-10.2）。
    """
    digest = hashlib.sha256(f"{scope}\x1f{variable}\x1f{old_value}".encode("utf-8")).hexdigest()[:16]
    return ReplacementItem(
        replacement_id=f"r-{digest}",
        variable=variable,
        old_value=old_value,
        new_value=new_value,
    )


def apply_replacement_plan(
    html: str,
    plan: ReplacementPlan,
    *,
    revoked_ids: set[str] | None = None,
) -> str:
    """按计划执行替换，跳过用户撤销的项。

    - 新值一律 HTML 转义后插入（企业名含 ``&``/``<`` 时不破坏结构、不能注入标签）；
    - 单遍正则替换：已替换出的文本不会被后续替换项二次扫描。
    """
    if not html or not plan.items:
        return html
    revoked = revoked_ids or set()
    mapping = {
        escape(item.old_value): escape(item.new_value)
        for item in plan.items
        if item.replacement_id not in revoked
    }
    if not mapping:
        return html
    pattern = re.compile("|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)))
    return pattern.sub(lambda m: mapping[m.group(0)], html)
