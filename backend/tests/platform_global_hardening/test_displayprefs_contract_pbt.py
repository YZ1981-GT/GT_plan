"""Feature: platform-global-hardening, Property 2

Property 2: DisplayPrefs 守卫检出反模式、放行合规写法
对任意底稿源码片段：当且仅当片段包含反模式 A（inject('displayPrefs', {含本地
格式化实现}）) 或反模式 B（硬编码 font-size: 13px 及 11/12/14px 字面量）时，
check_displayprefs_contract 判定为违规；对使用 inject(DisplayPrefs_Key, ...) 或
var(--wp-font-size) 的合规片段放行。

Validates: Requirements 1.3, 1.7
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# ─── 以文件路径加载被测守卫脚本 ──────────────────────────────────────────────
_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts" / "check" / "check_displayprefs_contract.py"
)
_spec = importlib.util.spec_from_file_location("check_displayprefs_contract", _SCRIPT)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


# ─── 生成器：违规片段 A / B 与合规片段 ───────────────────────────────────────
def _anti_a(quote: str, typed: bool, formatter: str) -> str:
    generic = "<{ fmtAmount: (v: number) => string }>" if typed else ""
    if formatter == "toLocaleString":
        body = "fmtAmount: (v) => v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })"
    else:
        body = "fmtAmount: (v) => String(v)"
    return f"const dp = inject{generic}({quote}displayPrefs{quote}, {{ {body} }})"


_anti_a_strategy = st.builds(
    _anti_a,
    quote=st.sampled_from(["'", '"']),
    typed=st.booleans(),
    formatter=st.sampled_from(["toLocaleString", "fmtAmount"]),
)

_anti_b_strategy = st.builds(
    lambda size, indent: f"{' ' * indent}font-size: {size}px;",
    size=st.sampled_from([11, 12, 13, 14]),
    indent=st.integers(min_value=0, max_value=8),
)


@settings(max_examples=100)
@given(anti=st.one_of(_anti_a_strategy, _anti_b_strategy))
def test_antipatterns_flagged(anti: str) -> None:
    """反模式 A 或 B 片段 SHALL 被判定为违规（非空）。"""
    violations = guard.scan_text(anti)
    assert violations, f"未检出反模式：{anti!r}"


@settings(max_examples=100)
@given(
    quote=st.sampled_from(["'", '"']),
    typed=st.booleans(),
    formatter=st.sampled_from(["toLocaleString", "fmtAmount"]),
)
def test_pattern_a_detected_and_kind(quote: str, typed: bool, formatter: str) -> None:
    """反模式 A 命中 kind 为 'A'（含/不含 TS 泛型两种形态都检出）。"""
    src = _anti_a(quote, typed, formatter)
    kinds = {k for k, _ in guard.scan_text(src)}
    assert "A" in kinds, f"pattern A 漏检：{src!r}"


@settings(max_examples=100)
@given(size=st.sampled_from([11, 12, 13, 14]), indent=st.integers(0, 8))
def test_pattern_b_detected(size: int, indent: int) -> None:
    """硬编码 font-size 字面量命中 kind 为 'B'。"""
    src = f"{' ' * indent}font-size: {size}px;"
    kinds = {k for k, _ in guard.scan_text(src)}
    assert "B" in kinds, f"pattern B 漏检：{src!r}"


def test_key_inject_and_var_font_allowed() -> None:
    """合规写法（类型化 key / null fallback / var(--wp-font-size)）SHALL 放行。"""
    for compliant in [
        "const dp = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()",
        "const dp = inject(DisplayPrefs_Key, useDisplayPrefsStore())",
        "const dp = inject('displayPrefs', null)",
        "  font-size: var(--wp-font-size, 13px);",
        "  font-size: var(--wp-font-size);",
        "const x = 1;",
    ]:
        assert guard.scan_text(compliant) == [], f"合规片段被误报：{compliant!r}"
