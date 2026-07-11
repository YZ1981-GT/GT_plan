"""模板库预设公式引用 ACNR 地址坐标名称库归一化（Task 14.5 / Req 24）。

把模板库（``template_library_mgmt`` 的 ``/prefill-formulas``、``preset_library``
收敛源）中的**预设公式引用**统一到 ACNR ``grammar_v1``（``formula_ref`` / ``addr_id``），
使其经 ``full_resolve`` 可解析（禁裸 ``wp_code+sheet+cell`` 串）。

归一化（硬编码旧格式 → ACNR canonical）
--------------------------------------
模板库历史沉淀的 prefill 公式使用与 ACNR/L1 内核不同的函数别名，需归一化：

- ``TB_SUM('a~b','col')`` → ``SUM_TB('a~b','col')``（ACNR resolver 识别 ``SUM_TB(``）
- ``TB_AUX('code','dim','col')`` → ``AUX('code','dim','col')``（canonical ``AUX(``）

其余已是 canonical（``TB`` / ``PREV`` / ``WP`` / ``NOTE`` / ``ROW`` / ``AUX`` /
``SUM_TB`` / ``SUM_ROW`` / ``REPORT``，以及控制函数 ``IF/ABS/ROUND/MAX/MIN``）。

未迁移（无 ACNR canonical 等价 → Ledger 标待迁移 ``pending``）
------------------------------------------------------------
- ``ADJ`` / ``LEDGER`` / ``LEDGER_DETAIL`` / ``COUNT_LEDGER``：审计调整分录/序时账
  取数语义，尚无 ACNR ``grammar_v1`` 函数头 → ``status='pending'``（增量迁移，无回归）。
- 空 / ``PLACEHOLDER`` / 裸坐标（无函数调用，如 ``A5`` / ``D2!E100``）→ ``pending``。

单一真源
--------
ACNR 已注册函数集 = ``formula_engine._REGISTRY.known_function_names()``（L1 内核）。
本模块**不**直接引用 legacy ``address_registry``（改由 ACNR grammar/kernel 判定），
因此不新增 legacy 消费点；模板库预设作为 ACNR 消费点纳入
``.kiro/specs/acnr-consumer-wiring/design.md`` §Coverage Ledger（Req 24.3）。

Requirements: 24.1, 24.2, 24.3, 24.4
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# 硬编码旧格式函数别名 → ACNR canonical 函数头（Req 24.4 归一化）
LEGACY_ALIAS_MAP: dict[str, str] = {
    "TB_SUM": "SUM_TB",
    "TB_AUX": "AUX",
}

# 未迁移函数白名单（Ledger 标待迁移，Req 24.3/24.4）——尚无 ACNR grammar_v1 等价。
# 新增未登记的未迁移函数 → drift guard CI 失败（见
# tests/formula_management/test_preset_acnr_migration_drift_guard.py）。
PENDING_FUNCTION_ALLOWLIST: frozenset[str] = frozenset(
    {"ADJ", "LEDGER", "LEDGER_DETAIL", "COUNT_LEDGER"}
)

# 归一化状态
STATUS_MIGRATED = "migrated"
STATUS_PENDING = "pending"

# pending 细分原因
REASON_EMPTY = "empty_or_placeholder"
REASON_NO_FUNCTION = "no_function_call"  # 裸坐标 / 硬编码旧格式
REASON_UNMAPPED = "unmapped_function"  # 已知别名之外、无 ACNR 等价的函数（待迁移）

# 静态兜底函数集（formula_engine 不可用时 fail-open，与 L1 内核当前注册保持一致）
_FALLBACK_KNOWN_FUNCS: frozenset[str] = frozenset(
    {
        "TB", "SUM_TB", "ROW", "SUM_ROW", "REPORT", "NOTE", "WP", "PREV", "AUX",
        "IF", "ABS", "ROUND", "MAX", "MIN",
    }
)

# 函数头提取：匹配 ``FUNC(`` 形态的函数名（大小写不敏感，取原样后归一）
_FUNC_HEAD_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")


@lru_cache(maxsize=1)
def _known_acnr_funcs() -> frozenset[str]:
    """ACNR/L1 内核已注册函数集（单一真源，fail-open 兜底）。"""
    try:
        from app.services.formula_engine import _REGISTRY

        names = {n.upper() for n in _REGISTRY.known_function_names()}
        if names:
            return frozenset(names)
    except Exception as exc:  # noqa: BLE001 — 内核不可用不阻断归一化
        logger.warning("formula_engine 注册函数集不可用，回退静态兜底: %s", exc)
    return _FALLBACK_KNOWN_FUNCS


@dataclass
class NormalizedRef:
    """单条预设公式引用的 ACNR 归一化结果。"""

    original: str | None
    formula_ref: str | None  # 归一化后的 canonical formula_ref（pending 时可为原串或 None）
    status: str  # migrated | pending
    reason: str  # acnr_grammar_v1 | empty_or_placeholder | no_function_call | unmapped_function
    unmapped_functions: tuple[str, ...] = ()

    @property
    def migrated(self) -> bool:
        return self.status == STATUS_MIGRATED

    def to_ref_dict(self) -> dict[str, Any] | None:
        """转为 refs 列表中的规范化引用项（addr_id/formula_ref + acnr_status）。

        空/占位返回 None（无引用）。
        """
        if not self.formula_ref:
            return None
        return {"formula_ref": self.formula_ref, "acnr_status": self.status}


def _extract_func_heads(expr: str) -> list[str]:
    return [m.group(1).upper() for m in _FUNC_HEAD_RE.finditer(expr)]


def _apply_alias(expr: str) -> str:
    """把旧格式函数别名归一化为 ACNR canonical（词边界 + 后随左括号）。"""
    normalized = expr
    for legacy, canonical in LEGACY_ALIAS_MAP.items():
        normalized = re.sub(
            rf"\b{legacy}\s*\(", f"{canonical}(", normalized, flags=re.IGNORECASE
        )
    return normalized


def normalize_ref(expression: str | None) -> NormalizedRef:
    """归一化单条预设公式引用为 ACNR ``formula_ref``，并判定迁移状态（Req 24.1/24.4）。

    - 含函数调用且（别名归一后）全部函数头 ∈ ACNR 已注册集 → ``migrated``。
    - 含未映射函数（无 ACNR 等价，如 ADJ/LEDGER）→ ``pending``（Ledger 待迁移）。
    - 空/占位/裸坐标（无函数调用）→ ``pending``。
    """
    if expression is None or not str(expression).strip():
        return NormalizedRef(
            original=expression, formula_ref=None, status=STATUS_PENDING, reason=REASON_EMPTY
        )

    expr = str(expression).strip()
    if expr.startswith("="):
        expr = expr[1:].strip()
    if not expr:
        return NormalizedRef(
            original=expression, formula_ref=None, status=STATUS_PENDING, reason=REASON_EMPTY
        )

    heads = _extract_func_heads(expr)
    if not heads:
        # 裸坐标 / 硬编码旧格式（无函数调用）→ 待迁移
        return NormalizedRef(
            original=expression,
            formula_ref=expr,
            status=STATUS_PENDING,
            reason=REASON_NO_FUNCTION,
        )

    normalized = _apply_alias(expr)
    norm_heads = [LEGACY_ALIAS_MAP.get(h, h) for h in heads]
    known = _known_acnr_funcs()
    unmapped = tuple(sorted({h for h in norm_heads if h not in known}))
    if unmapped:
        return NormalizedRef(
            original=expression,
            formula_ref=normalized,
            status=STATUS_PENDING,
            reason=REASON_UNMAPPED,
            unmapped_functions=unmapped,
        )

    return NormalizedRef(
        original=expression,
        formula_ref=normalized,
        status=STATUS_MIGRATED,
        reason="acnr_grammar_v1",
    )


def build_migration_ledger(
    expressions: Iterable[str | None] | None = None,
) -> dict[str, Any]:
    """扫描模板库预设公式并产出 ACNR 迁移 Ledger（Req 24.3/24.4）。

    Args:
        expressions: 待扫描表达式集合；缺省则从 ``prefill_formula_mapping.json``
            + 预设库收敛条目汇总。

    Returns:
        {
          "total", "migrated", "pending",
          "coverage_percent",
          "pending_functions": {func: count},   # 待迁移函数分布
          "pending_reasons": {reason: count},
          "examples": [{original, formula_ref, status, reason}, ...]  # 前若干条 pending 样例
        }
    """
    exprs = list(expressions) if expressions is not None else _collect_template_library_expressions()

    total = 0
    migrated = 0
    pending = 0
    pending_functions: dict[str, int] = {}
    pending_reasons: dict[str, int] = {}
    examples: list[dict[str, Any]] = []

    for e in exprs:
        total += 1
        nr = normalize_ref(e)
        if nr.migrated:
            migrated += 1
            continue
        pending += 1
        pending_reasons[nr.reason] = pending_reasons.get(nr.reason, 0) + 1
        for fn in nr.unmapped_functions:
            pending_functions[fn] = pending_functions.get(fn, 0) + 1
        if len(examples) < 20:
            examples.append(
                {
                    "original": nr.original,
                    "formula_ref": nr.formula_ref,
                    "status": nr.status,
                    "reason": nr.reason,
                    "unmapped_functions": list(nr.unmapped_functions),
                }
            )

    return {
        "total": total,
        "migrated": migrated,
        "pending": pending,
        "coverage_percent": round(migrated / total * 100, 1) if total > 0 else 0.0,
        "pending_functions": dict(sorted(pending_functions.items())),
        "pending_reasons": dict(sorted(pending_reasons.items())),
        "examples": examples,
    }


def _collect_template_library_expressions() -> list[str | None]:
    """汇总模板库预设公式表达式（prefill 映射 + 预设库收敛条目）。"""
    exprs: list[str | None] = []

    # 1) prefill_formula_mapping.json 全部 cells
    try:
        from app.services.formula_management.preset_library import DATA_DIR, _safe_load_json

        data = _safe_load_json(DATA_DIR / "prefill_formula_mapping.json")
        if isinstance(data, dict):
            for m in data.get("mappings", []) or []:
                for cell in m.get("cells", []) or []:
                    exprs.append(cell.get("formula"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("采集 prefill 表达式失败: %s", exc)

    # 2) 预设库显式 seed 条目表达式
    try:
        from app.services.formula_management.preset_library import load_seed_presets

        for e in load_seed_presets():
            exprs.append(e.expression)
    except Exception as exc:  # noqa: BLE001
        logger.warning("采集 seed 预设表达式失败: %s", exc)

    return exprs
