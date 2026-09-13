# -*- coding: utf-8 -*-
"""D4-1 公式单元格裁决（HTML/OO 同定义求值 + 失败闭环 + 来源 tooltip）。

Task 3.2 / Requirements 3.2, 3.4, 2.2, 1.4：

> 接入 HTML/OO 同定义求值与来源 tooltip；公式失败标 failed/blocked，不写值、不转零。

═══ 为什么需要这一层 ═══

- 有效公式解析（:mod:`effective_formula`）只回答「此刻的有效公式是什么、来自哪、什么
  状态（custom/preset/…/corrupt/blocked/stale）」，**不产出数值**。
- 底层求值器 :func:`app.services.wp_formula_eval_service.evaluate_wp_formula_expression`
  会求出数值，但**失败时返回 ``(Decimal('0'), errors)``** —— 这正是 Req 3.4 禁止的
  「转零」。直接把它的返回值投影到 HTML/OO 会把「求值失败」伪装成「结果=0」。

- 本模块是 HTML 与 OO **共用的唯一裁决入口**：给定同一 effective definition + 同一
  求值结果，产出同一个 :class:`FormulaCellVerdict`。它保证：
    * 失败/损坏/blocked/stale → ``value=None``（**绝不转零**）、``applied=False``；
    * 成功 → ``value`` 为 Decimal、``applied=True``；
    * 每个 verdict 携带**中文来源 tooltip**（预设/自定义 + 表达式 + 状态原因），
      HTML 悬浮与 OO 批注消费同一段文本，避免两侧口径漂移。

═══ 状态到裁决的映射（Req 3.4 失败闭环）═══

    effective state → verdict outcome
    ─────────────────────────────────
    corrupt           → 'failed'   （表达式非法/含 eval/外链；不求值、不写值、不转零）
    blocked           → 'blocked'  （能力门控；只读、不写值）
    preset_missing    → 'pending'  （页面 pending；无有效公式，不写值）
    stale             → 'stale'    （上游已变、待重算；不写当前值）
    custom / preset   → 求值：errors 非空 → 'failed'（不转零）；否则 'ok'（写值）

依赖项失败传播（Req 3.4「该公式及依赖项为 failed/blocked」）由调用方按 DAG 传入
``dependency_failed=True`` 时短路为 ``failed``；无依赖公式不受影响。

Spec: d4-1-adjudication-bidirectional-writeback-and-formula-io Task 3.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from app.services.formula_management.effective_formula import EffectiveFormula

__all__ = [
    "FormulaCellOutcome",
    "FormulaCellVerdict",
    "build_source_tooltip",
    "verdict_from_effective",
    "verdict_from_evaluation",
]

FormulaCellOutcome = Literal["ok", "failed", "blocked", "pending", "stale"]

# effective state → 非求值直达裁决（不进入求值路径的态）。
_NON_EVAL_OUTCOME: dict[str, FormulaCellOutcome] = {
    "corrupt": "failed",
    "blocked": "blocked",
    "preset_missing": "pending",
    "stale": "stale",
}


def build_source_tooltip(eff: EffectiveFormula) -> str:
    """构造 HTML 悬浮 / OO 批注共用的中文来源 tooltip。

    口径单一：来源（自定义/预设）+ 有效表达式 + 状态原因。HTML 与 OO 读同一段，
    避免两侧口径漂移（Req 2.2 逐 cell 一致的延伸：连来源说明也一致）。
    """
    src = eff.source or "none"
    if src == "custom":
        origin = "来源：用户自定义公式"
    elif src.startswith("preset:"):
        origin = f"来源：预设公式（{src.split(':', 1)[1]}）"
    else:
        origin = "来源：无（该单元格无预设且未编辑）"

    parts = [origin]
    if eff.expression:
        parts.append(f"公式：{eff.expression}")
    elif eff.preset_expression:
        parts.append(f"预设公式：{eff.preset_expression}（当前未生效）")
    if eff.reason:
        parts.append(f"状态：{eff.reason}")
    return "\n".join(parts)


@dataclass(frozen=True)
class FormulaCellVerdict:
    """一个公式单元格此刻的统一裁决（HTML/OO 共用）。

    ``applied=True`` 仅当 ``outcome == 'ok'``；此时 ``value`` 为 Decimal。
    其余一切态 ``value is None``、``applied=False`` —— **绝不转零**（Req 3.4）。
    """

    key: str
    outcome: FormulaCellOutcome
    value: Decimal | None
    applied: bool
    source: str
    tooltip: str
    reason: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "outcome": self.outcome,
            # 序列化为字符串，避免 JSON 丢精度；None 保持 null（前端据此不渲染 0）。
            "value": (str(self.value) if self.value is not None else None),
            "applied": self.applied,
            "source": self.source,
            "tooltip": self.tooltip,
            "reason": self.reason,
            "errors": list(self.errors),
        }


def verdict_from_effective(eff: EffectiveFormula) -> FormulaCellVerdict | None:
    """非求值态的直达裁决（corrupt/blocked/preset_missing/stale）。

    命中这些态时返回裁决（value=None、applied=False）；对可求值态（custom/preset）
    返回 ``None``，交由 :func:`verdict_from_evaluation` 携求值结果裁决。
    """
    outcome = _NON_EVAL_OUTCOME.get(eff.state)
    if outcome is None:
        return None
    return FormulaCellVerdict(
        key=eff.key,
        outcome=outcome,
        value=None,
        applied=False,
        source=eff.source,
        tooltip=build_source_tooltip(eff),
        reason=eff.reason,
        errors=[],
    )


def verdict_from_evaluation(
    eff: EffectiveFormula,
    *,
    value: Decimal | None,
    errors: list[str] | None = None,
    dependency_failed: bool = False,
) -> FormulaCellVerdict:
    """把有效公式 + 求值结果裁决为统一 verdict（HTML/OO 共用）。

    先处理非求值态（corrupt/blocked/preset_missing/stale）；对可求值态：

    - ``dependency_failed`` 或 ``errors`` 非空 → ``failed``：``value=None``、
      ``applied=False``（**不转零** —— 底层求值器的 ``Decimal('0')`` 在此被丢弃）。
    - 否则 → ``ok``：写值。

    Args:
        value: 底层求值器算出的值。**失败时调用方仍可能传入 0**（求值器的转零默认值），
            本函数在 errors 非空时**主动丢弃它**，杜绝「失败伪装成 0」。
        errors: 求值器返回的 errors；非空即失败。
        dependency_failed: 依赖项已 failed/blocked 时传 True → 本公式短路为 failed。
    """
    non_eval = verdict_from_effective(eff)
    if non_eval is not None:
        return non_eval

    errs = list(errors or [])
    tooltip = build_source_tooltip(eff)

    if dependency_failed:
        return FormulaCellVerdict(
            key=eff.key,
            outcome="failed",
            value=None,
            applied=False,
            source=eff.source,
            tooltip=tooltip,
            reason="依赖项求值失败，本公式不产出值（不转零）",
            errors=errs,
        )

    if errs:
        return FormulaCellVerdict(
            key=eff.key,
            outcome="failed",
            value=None,
            applied=False,
            source=eff.source,
            tooltip=tooltip,
            reason="公式求值失败，保留原内容、不写值、不转零",
            errors=errs,
        )

    # outcome == 'ok'（可求值态 custom/preset 且无 error/依赖失败）→ 唯一写值路径。
    return FormulaCellVerdict(
        key=eff.key,
        outcome="ok",
        value=value,
        applied=True,
        source=eff.source,
        tooltip=tooltip,
        reason="",
        errors=[],
    )
