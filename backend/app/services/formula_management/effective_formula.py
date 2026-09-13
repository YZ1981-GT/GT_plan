# -*- coding: utf-8 -*-
"""有效公式解析（Effective Formula）— 预设 + 用户二次编辑的单一真源治理。

用户要求：*「公式作为单一真源的治理是预设一个的基础上用户二次编辑」*。落地为一个
**有效公式解析器**：给定公式 key，回答「此刻这个单元格的有效公式是什么、来自哪、什么
状态」。这里不新造预设/自定义存储 —— 预设读 :mod:`preset_library`（三源收敛 + seed +
custom presets 的单一真源），用户覆盖由调用方按 key 传入（v2 store / 遗留 parsed_data）。

═══ 公式 key（Req 2.3）═══

    formula_key = wp_id ∷ stable_sheet_key ∷ row_key ∷ field_key ∷ custom_suffix

- ``stable_sheet_key`` 用**稳定 sheet 身份**（不因 sheet 改名而变），非 label。
- ``custom_suffix`` 区分同一 (row,field) 上并存的多条自定义公式（默认空）。
- key 是稳定字符串，可作 v2 store / 遗留键 / 前端 locationDigest 的对齐锚点。

═══ 状态机（Req 2.3 缺失/损坏/stale/blocked 分态）═══

- ``custom``        用户已二次编辑，有效公式 = 用户表达式（预设作为可恢复的底稿）。
- ``preset``        无用户覆盖，有效公式 = 预设表达式。
- ``preset_missing``无用户覆盖且该 key 无预设（页面 pending）。
- ``corrupt``       表达式非法/超白名单/含外链或 eval → fail-closed，不产出有效值。
- ``stale``         有效公式引用的上游已变更、结果待重算（由依赖图判定传入）。
- ``blocked``       能力门控拒绝（无编辑权/快照过期），有效值只读不可改。

「预设升级保留 custom」「删除 custom 恢复 preset」不是这里执行的动作，而是这里给出的
**判据**：只要用户覆盖存在，``resolve`` 恒返回 ``custom``（预设升级不动它）；覆盖被删除
（调用方不再传 override）后，``resolve`` 自动回落 ``preset``（无需显式回填）。

Spec: d4-adjustment-and-analysis-gap-closure Task 3（C2formula）
Requirements: 2.3
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.formula_management.preset_library import (
    PresetEntry,
    find_presets_for_page,
)

__all__ = [
    "EffectiveFormulaState",
    "FormulaKey",
    "EffectiveFormula",
    "make_formula_key",
    "validate_expression",
    "resolve_effective_formula",
]

EffectiveFormulaState = Literal[
    "custom", "preset", "preset_missing", "corrupt", "stale", "blocked"
]

_KEY_SEP = "\u2237"  # '∷' — 不会出现在 wp_id/sheet/row/field 里，避免与内容冲突

# schema 白名单：只允许的函数名（Req 2.3「schema 白名单禁 eval 和外链」）。
# 表间提取（TB/WP/ADJ/PREV/AUX）+ 表内计算（SUM/cell/横平衡）。
_ALLOWED_FUNCTIONS: frozenset[str] = frozenset(
    {"TB", "TB_SUM", "SUM_TB", "WP", "ADJ", "PREV", "AUX", "SUM", "cell", "ABS", "MIN", "MAX", "ROUND"}
)

# 明令禁止的形态：eval/exec/import/属性穿透/网络协议（外链）。
_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "eval", "exec", "__", "import", "lambda", "os.", "sys.", "subprocess",
    "http://", "https://", "file://", "ftp://", "\\\\",
)


@dataclass(frozen=True)
class FormulaKey:
    """公式定位键：稳定、可序列化、可作对齐锚点。"""

    wp_id: str
    stable_sheet_key: str
    row_key: str
    field_key: str
    custom_suffix: str = ""

    def serialize(self) -> str:
        return _KEY_SEP.join(
            [self.wp_id, self.stable_sheet_key, self.row_key, self.field_key, self.custom_suffix]
        )

    @property
    def page_key(self) -> str:
        """预设库按 page_key（``workpaper:{wp_code}`` 等）索引；这里用稳定 sheet 键。"""
        return self.stable_sheet_key


@dataclass(frozen=True)
class EffectiveFormula:
    """一个 key 此刻的有效公式解析结果。"""

    key: str
    state: EffectiveFormulaState
    expression: str | None
    source: str  # 'custom' | 'preset:<source>' | 'none'
    formula_type: str | None = None
    refs: list[Any] = field(default_factory=list)
    preset_expression: str | None = None  # 底稿预设（恢复默认时回落到它）
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "state": self.state,
            "expression": self.expression,
            "source": self.source,
            "formulaType": self.formula_type,
            "refs": self.refs,
            "presetExpression": self.preset_expression,
            "reason": self.reason,
        }


def make_formula_key(
    wp_id: str,
    stable_sheet_key: str,
    row_key: str,
    field_key: str,
    custom_suffix: str = "",
) -> FormulaKey:
    return FormulaKey(
        wp_id=str(wp_id),
        stable_sheet_key=str(stable_sheet_key),
        row_key=str(row_key),
        field_key=str(field_key),
        custom_suffix=str(custom_suffix or ""),
    )


def validate_expression(expression: str | None) -> tuple[bool, str]:
    """schema 白名单校验：禁 eval/外链，函数名须在白名单内。

    返回 ``(ok, reason)``；``ok=False`` 时 reason 是中文原因（供 corrupt 态展示）。
    """
    if expression is None:
        return False, "表达式为空"
    expr = str(expression).strip()
    if not expr:
        return False, "表达式为空"
    lowered = expr.lower()
    for bad in _FORBIDDEN_TOKENS:
        if bad in lowered:
            return False, f"表达式含禁止形态：{bad!r}（禁 eval/外链/属性穿透）"
    # 提取所有「标识符(」形态的函数调用名，校验白名单。
    called = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", expr))
    illegal = sorted(fn for fn in called if fn not in _ALLOWED_FUNCTIONS)
    if illegal:
        return False, f"表达式含白名单外函数：{illegal}"
    return True, ""


def _preset_for_key(
    key: FormulaKey,
    *,
    preset_entries: list[PresetEntry] | None,
    preset_index: dict[str, list[PresetEntry]] | None,
) -> PresetEntry | None:
    """在预设库里按 (page_key, target_cell=row_key∷field_key 或 field_key) 找预设。

    预设库的 target_cell 是单元格引用（如 ``C5``）；这里 row_key/field_key 的组合应
    由调用方对齐到预设的 target_cell 口径。为稳健起见先试 ``field_key``（多数底稿以
    列/单元格为 target），再试 ``row_key`` 兜底。
    """
    presets = find_presets_for_page(
        key.page_key, entries=preset_entries, index=preset_index
    )
    if not presets:
        return None
    for candidate in (key.field_key, key.row_key, f"{key.row_key}:{key.field_key}"):
        for p in presets:
            if p.target_cell == candidate:
                return p
    return None


def resolve_effective_formula(
    key: FormulaKey,
    *,
    custom_expression: str | None = None,
    custom_formula_type: str | None = None,
    custom_refs: list[Any] | None = None,
    is_stale: bool = False,
    is_blocked: bool = False,
    preset_entries: list[PresetEntry] | None = None,
    preset_index: dict[str, list[PresetEntry]] | None = None,
) -> EffectiveFormula:
    """解析 key 此刻的有效公式（custom 优先，回落 preset），并给出状态。

    Args:
        custom_expression: 用户二次编辑的表达式；``None`` 表示无覆盖（自动回落预设）。
        is_stale: 依赖图判定「上游已变、待重算」时传 True → stale 态。
        is_blocked: 能力门控拒绝（无编辑权/快照过期）时传 True → blocked 态（只读）。
        preset_entries / preset_index: 预设库（缺省则按需构建，批量场景传 index 复用）。

    单一真源治理：
      - 有 custom → state=custom，有效值=custom（预设仅作可恢复底稿，升级不覆盖 custom）。
      - 无 custom 有 preset → state=preset，有效值=preset。
      - 无 custom 无 preset → preset_missing。
      - 表达式非法（custom 或 preset）→ corrupt，fail-closed 不产出有效值。
    """
    serialized = key.serialize()
    preset = _preset_for_key(key, preset_entries=preset_entries, preset_index=preset_index)
    preset_expr = preset.expression if preset else None

    # blocked 优先级最高：无权改，但仍展示当前有效值（只读）。
    has_custom = custom_expression is not None and str(custom_expression).strip() != ""
    effective_expr = custom_expression if has_custom else preset_expr
    effective_type = (
        custom_formula_type if has_custom else (preset.formula_type if preset else None)
    )
    effective_refs = (
        list(custom_refs or []) if has_custom else (list(preset.refs) if preset else [])
    )
    source = "custom" if has_custom else (f"preset:{preset.source}" if preset else "none")

    # 有效表达式合法性（白名单）—— custom 或 preset 任一被消费时都要过。
    if effective_expr is not None:
        ok, reason = validate_expression(effective_expr)
        if not ok:
            return EffectiveFormula(
                key=serialized,
                state="corrupt",
                expression=None,
                source=source,
                formula_type=effective_type,
                refs=[],
                preset_expression=preset_expr,
                reason=reason,
            )

    if is_blocked:
        return EffectiveFormula(
            key=serialized,
            state="blocked",
            expression=effective_expr,
            source=source,
            formula_type=effective_type,
            refs=effective_refs,
            preset_expression=preset_expr,
            reason="能力门控拒绝：当前无权编辑，公式只读",
        )

    if not has_custom and preset is None:
        return EffectiveFormula(
            key=serialized,
            state="preset_missing",
            expression=None,
            source="none",
            formula_type=None,
            refs=[],
            preset_expression=None,
            reason="该单元格无预设且用户未编辑（页面为 pending）",
        )

    if is_stale:
        return EffectiveFormula(
            key=serialized,
            state="stale",
            expression=effective_expr,
            source=source,
            formula_type=effective_type,
            refs=effective_refs,
            preset_expression=preset_expr,
            reason="上游已变更，结果待重算",
        )

    return EffectiveFormula(
        key=serialized,
        state="custom" if has_custom else "preset",
        expression=effective_expr,
        source=source,
        formula_type=effective_type,
        refs=effective_refs,
        preset_expression=preset_expr,
        reason="",
    )
