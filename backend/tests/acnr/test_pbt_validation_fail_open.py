"""Property 15: Formula Validation Fail-Open on Infra Error (PBT)

# Feature: acnr-consumer-wiring, Property 15: Formula Validation Fail-Open on Infra Error

验证 `acnr.formula_validation.validate_refs_via_acnr()` 的 fail-open 语义：
当 ACNR `full_resolve` 因基础设施故障抛出异常时，整体校验必须**回退**到
legacy `address_registry.validate_formula_refs`，并返回**恰好**与 legacy 相同
的 issue 列表 —— 绝不因 resolver 挂掉而产生虚假 `not_found`（fail-open on
infra error），从而不阻断保存。

策略：
- 用 Hypothesis 生成随机公式表达式（至少含一个 `WP(...)` 引用，以触发
  `full_resolve` 路径），可混合非 WP 域引用（TB/ROW/NOTE/AUX）。
- monkeypatch `app.services.acnr.resolver.full_resolve` 抛异常（模拟 resolver
  基础设施不可用）。
- monkeypatch `address_registry.validate_formula_refs` 返回受控 sentinel issue
  列表。
- 断言 `validate_refs_via_acnr` 返回结果 == legacy sentinel（fail-open），且
  不含任何超出 sentinel 的 spurious `not_found` 项。

由于 `validate_refs_via_acnr` 是 async，通过 `asyncio.run` 驱动。

**Validates: Requirements 9.3**

Testing framework: hypothesis
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.formula_validation import validate_refs_via_acnr  # noqa: E402
from app.services.address_registry import address_registry  # noqa: E402

# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------
# formula_validation 内部通过 `from app.services.acnr.resolver import full_resolve`
# 延迟导入，故打桩 resolver 模块上的符号即可影响其解析路径。
_RESOLVER_TARGET = "app.services.acnr.resolver.full_resolve"

# ---------------------------------------------------------------------------
# Generators — 智能约束到公式输入空间（无单引号/逗号/括号的安全 token）
# ---------------------------------------------------------------------------

# 单参 token：字母数字、连字符，1~6 字符，且非空、无单引号（匹配 grammar `[^']+`）
_ident = st.from_regex(r"[A-Za-z0-9]{1,6}", fullmatch=True)
# 报表行次码风格（BS-002 等）
_row_code = st.from_regex(r"[A-Z]{2}-[0-9]{3}", fullmatch=True)


@st.composite
def _wp_ref(draw) -> str:
    """WP 域引用 —— 2 参 custom_flat 或 3 参 standard。"""
    if draw(st.booleans()):
        a, b, c = draw(_ident), draw(_ident), draw(_ident)
        return f"WP('{a}','{b}','{c}')"
    a, b = draw(_ident), draw(_ident)
    return f"WP('{a}','{b}')"


@st.composite
def _non_wp_ref(draw) -> str:
    """非 WP 域引用 —— TB / ROW / NOTE / AUX 之一。"""
    kind = draw(st.sampled_from(["TB", "ROW", "NOTE", "AUX"]))
    if kind == "TB":
        return f"TB('{draw(_ident)}','{draw(_ident)}')"
    if kind == "ROW":
        return f"ROW('{draw(_row_code)}')"
    if kind == "NOTE":
        return f"NOTE('{draw(_ident)}','{draw(_ident)}','{draw(_ident)}')"
    return f"AUX('{draw(_ident)}','{draw(_ident)}','{draw(_ident)}')"


@st.composite
def _expression_with_wp(draw) -> str:
    """生成至少含一个 WP 引用、可混合非 WP 引用的表达式。"""
    wp_tokens = draw(st.lists(_wp_ref(), min_size=1, max_size=3))
    non_wp_tokens = draw(st.lists(_non_wp_ref(), min_size=0, max_size=3))
    tokens = wp_tokens + non_wp_tokens
    # 打乱顺序，用算术运算符拼接成表达式
    tokens = draw(st.permutations(tokens))
    ops = draw(
        st.lists(
            st.sampled_from([" + ", " - ", " * ", " / "]),
            min_size=max(0, len(tokens) - 1),
            max_size=max(0, len(tokens) - 1),
        )
    )
    parts: list[str] = []
    for i, tok in enumerate(tokens):
        parts.append(tok)
        if i < len(tokens) - 1:
            parts.append(ops[i])
    return "".join(parts)


# legacy sentinel issue 生成器 —— 模拟 legacy validate_formula_refs 的返回。
@st.composite
def _legacy_issue(draw) -> dict:
    ref = draw(_ident)
    return {
        "ref": f"TB('{ref}','审定数')",
        "uri": f"tb://{ref}#审定数",
        "status": "not_found",
        "message": f"引用地址 tb://{ref}#审定数 在当前项目中不存在",
    }


_legacy_result = st.lists(_legacy_issue(), min_size=0, max_size=4)


def _extract_wp_refs(expr: str) -> list[str]:
    from app.services.formula_grammar import RELAXED_FORMULA_PATTERNS

    return [m.group(0) for m in RELAXED_FORMULA_PATTERNS["WP"].finditer(expr)]


# ---------------------------------------------------------------------------
# Property Test
# ---------------------------------------------------------------------------


class TestValidationFailOpen:
    """Property 15: full_resolve 抛异常时整体回退 legacy，无 spurious not_found。"""

    # Feature: acnr-consumer-wiring, Property 15: Formula Validation Fail-Open on Infra Error

    @given(expression=_expression_with_wp(), legacy_issues=_legacy_result)
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )
    def test_fail_open_returns_exactly_legacy(
        self, expression: str, legacy_issues: list[dict]
    ):
        """full_resolve 抛异常 → 返回结果恰好等于 legacy validate_formula_refs。

        **Validates: Requirements 9.3**
        """
        # resolver 基础设施故障：full_resolve await 时抛异常
        resolver_spy = AsyncMock(side_effect=RuntimeError("resolver infra down"))
        # legacy 校验返回受控 sentinel（深拷贝以便对比原始输入）
        expected = [dict(issue) for issue in legacy_issues]
        legacy_spy = AsyncMock(return_value=[dict(issue) for issue in legacy_issues])

        with patch(_RESOLVER_TARGET, resolver_spy), patch.object(
            address_registry, "validate_formula_refs", legacy_spy
        ):
            result = asyncio.run(
                validate_refs_via_acnr(
                    db=AsyncMock(),
                    project_id="proj-p15",
                    year=2025,
                    expression=expression,
                    template_type="soe",
                )
            )

        # (a) fail-open：结果恰好等于 legacy 返回（不多不少）
        assert result == expected, (
            f"fail-open 未原样返回 legacy 结果: got={result} expected={expected} "
            f"(expr={expression!r})"
        )

        # (b) 表达式含 WP 引用 → full_resolve 至少被尝试一次（触发 fail-open）
        assert resolver_spy.await_count >= 1, (
            f"full_resolve 未被调用，fail-open 路径未触发 (expr={expression!r})"
        )

        # (c) legacy fallback 被调用恰好一次（整体回退，非逐引用）
        assert legacy_spy.await_count == 1, (
            f"legacy validate_formula_refs 未被调用恰好一次: "
            f"await_count={legacy_spy.await_count} (expr={expression!r})"
        )

    @given(expression=_expression_with_wp())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )
    def test_no_spurious_not_found_when_legacy_clean(self, expression: str):
        """legacy 认为通过（空 issues）时，即便含 WP 引用且 full_resolve 抛异常，
        结果也必须为空 —— 绝不产生虚假 not_found。

        **Validates: Requirements 9.3**
        """
        resolver_spy = AsyncMock(side_effect=RuntimeError("resolver infra down"))
        legacy_spy = AsyncMock(return_value=[])

        with patch(_RESOLVER_TARGET, resolver_spy), patch.object(
            address_registry, "validate_formula_refs", legacy_spy
        ):
            result = asyncio.run(
                validate_refs_via_acnr(
                    db=AsyncMock(),
                    project_id="proj-p15",
                    year=2025,
                    expression=expression,
                    template_type="soe",
                )
            )

        # 无 spurious not_found：legacy 空 → 结果必空
        assert result == [], (
            f"resolver 故障时产生了 spurious issue（应 fail-open 为空）: "
            f"got={result} (expr={expression!r}, wp_refs={_extract_wp_refs(expression)})"
        )
