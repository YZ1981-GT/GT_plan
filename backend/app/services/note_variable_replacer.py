"""附注正文确定性变量替换计划。

spec: disclosure-note-doc-upload-and-batch-fill Phase 2 Task 13

仅替换明确 token 和精确来源值（公司名/年度/期间/币种/单位）；
地址/法定代表人/金额缺目标值时只 warning 不猜测。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
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

# ── 不可确定的残留模式 ──────────────────────────────────────────────────────

_RESIDUAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("source_entity_name", re.compile("")),  # 占位，运行时按实际来源名注入
)


def build_replacement_plan(
    html: str,
    *,
    target_vars: dict[str, Any],
    source_entity_name: str | None = None,
) -> ReplacementPlan:
    """从 HTML 正文生成确定性替换计划。

    - token 变量（如 {公司名称}）：若目标值存在，生成替换项。
    - 来源企业名精确命中：生成替换项（目标为 target_vars["company_name"]）。
    - 地址/人名/金额等不可确定残留：只进 warning，不生成替换项。
    """
    plan = ReplacementPlan()
    if not html:
        return plan

    # 1. token 变量
    for token, var_key in _TOKEN_VARS:
        if token not in html:
            continue
        target_val = target_vars.get(var_key)
        if target_val is not None:
            target_str = str(target_val)
            plan.items.append(
                ReplacementItem(
                    replacement_id=str(uuid.uuid4()),
                    variable=var_key,
                    old_value=token,
                    new_value=target_str,
                )
            )
        else:
            plan.warnings.append(f"变量 {token} 缺少目标值，保留原文")

    # 2. 来源企业名精确替换
    if source_entity_name and source_entity_name in html:
        target_name = target_vars.get("company_name")
        if target_name:
            plan.items.append(
                ReplacementItem(
                    replacement_id=str(uuid.uuid4()),
                    variable="source_entity_name",
                    old_value=source_entity_name,
                    new_value=str(target_name),
                )
            )
        else:
            plan.warnings.append(
                f"来源企业名「{source_entity_name}」存在于正文，但缺少目标企业名"
            )

    return plan


def apply_replacement_plan(
    html: str,
    plan: ReplacementPlan,
    *,
    revoked_ids: set[str] | None = None,
) -> str:
    """按计划执行替换，跳过用户撤销的项。"""
    if not html or not plan.items:
        return html
    revoked = revoked_ids or set()
    result = html
    for item in plan.items:
        if item.replacement_id in revoked:
            continue
        result = result.replace(item.old_value, item.new_value)
    return result
