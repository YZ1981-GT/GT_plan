"""D4-1 取数状态判定契约测试（Task 2.2）。

纯函数 `classify_d4_source_status(scope)` 无 DB 依赖，独立单测：
- exact 命中（report_config + exact + 无 unmapped）→ status=ok
- fallback / 非 exact / 有 unmapped → status=manual
- 完全无解析（非 report_config 且 revenue_original 空）→ status=blocked
并含**反向自检**（判据不能恒真：构造一个 exact=True 的 scope 断言不会被误判成 manual）。

spec: d4-1-adjudication-bidirectional-writeback-and-formula-io / Req 2.1, Property 5
"""
from __future__ import annotations

from app.services.d4_extraction.account_scope import (
    D4_SOURCE_STATUS_BLOCKED,
    D4_SOURCE_STATUS_MANUAL,
    D4_SOURCE_STATUS_OK,
    D4AccountScope,
    classify_d4_source_status,
)
from app.services.four_table import RESOLVED_FROM_FALLBACK, RESOLVED_FROM_REPORT


def _ok_scope(**overrides) -> D4AccountScope:
    """构造一个「精确命中」的 scope，供各用例按需覆盖字段。"""
    base = dict(
        revenue_standard=("6001~6099",),
        cost_standard=("6401~6499",),
        revenue_standard_expanded=("6001",),
        cost_standard_expanded=("6401",),
        revenue_original=("6001",),
        cost_original=("6401",),
        revenue_resolved_from=RESOLVED_FROM_REPORT,
        cost_resolved_from=RESOLVED_FROM_REPORT,
        revenue_exact=True,
        cost_exact=True,
        unmapped_standard=(),
    )
    base.update(overrides)
    return D4AccountScope(**base)


# ── ok ───────────────────────────────────────────────────────────────────────

def test_exact_report_config_is_ok():
    scope = _ok_scope()
    result = classify_d4_source_status(scope)
    assert result["state"] == D4_SOURCE_STATUS_OK
    assert result["unmapped_standard"] == []
    assert result["revenue_exact"] is True
    assert result["cost_exact"] is True


# ── manual ─────────────────────────────────────────────────────────────────

def test_fallback_resolved_from_is_manual():
    """收入侧走兜底码但仍反解出原始码 → manual（不 blocked）。"""
    scope = _ok_scope(
        revenue_resolved_from=RESOLVED_FROM_FALLBACK,
        revenue_original=("6001",),  # 有原始码 → 非 blocked
    )
    result = classify_d4_source_status(scope)
    assert result["state"] == D4_SOURCE_STATUS_MANUAL
    assert "兜底" in result["reason"]


def test_non_exact_is_manual():
    scope = _ok_scope(revenue_exact=False)
    result = classify_d4_source_status(scope)
    assert result["state"] == D4_SOURCE_STATUS_MANUAL
    assert "未精确" in result["reason"]


def test_cost_non_exact_is_manual():
    scope = _ok_scope(cost_exact=False)
    result = classify_d4_source_status(scope)
    assert result["state"] == D4_SOURCE_STATUS_MANUAL


def test_unmapped_standard_is_manual():
    scope = _ok_scope(unmapped_standard=("6001", "6051"))
    result = classify_d4_source_status(scope)
    assert result["state"] == D4_SOURCE_STATUS_MANUAL
    assert result["unmapped_standard"] == ["6001", "6051"]
    assert "6001" in result["reason"] and "6051" in result["reason"]


# ── blocked ────────────────────────────────────────────────────────────────

def test_completely_unresolvable_is_blocked():
    """收入侧非 report_config 且反解不出任何原始码 → blocked（拒绝取数）。"""
    scope = _ok_scope(
        revenue_resolved_from=RESOLVED_FROM_FALLBACK,
        revenue_original=(),  # 完全无原始码
        revenue_exact=False,
    )
    result = classify_d4_source_status(scope)
    assert result["state"] == D4_SOURCE_STATUS_BLOCKED
    assert "拒绝取数" in result["reason"]


def test_default_scope_is_blocked():
    """默认空 scope（未解析）→ blocked，不臆测科目。"""
    result = classify_d4_source_status(D4AccountScope())
    assert result["state"] == D4_SOURCE_STATUS_BLOCKED


# ── 反向自检（判据不能恒真）──────────────────────────────────────────────────

def test_reverse_guard_ok_not_misclassified_as_manual():
    """构造一个 exact=True 的干净 scope，断言**不会**被误判成 manual/blocked。

    若判据恒返 manual（例如把 exact 判反、或 report_config 常量拼错），此断言必红。
    """
    scope = _ok_scope()
    result = classify_d4_source_status(scope)
    assert result["state"] != D4_SOURCE_STATUS_MANUAL
    assert result["state"] != D4_SOURCE_STATUS_BLOCKED
    assert result["state"] == D4_SOURCE_STATUS_OK


def test_reverse_guard_manual_not_misclassified_as_ok():
    """有 unmapped 的 scope 必须是 manual，不能因判据空转而被判 ok。"""
    scope = _ok_scope(unmapped_standard=("9999",))
    result = classify_d4_source_status(scope)
    assert result["state"] != D4_SOURCE_STATUS_OK


def test_reverse_guard_blocked_precedence_over_manual():
    """blocked 优先级高于 manual：完全无解析时即便有 unmapped 也应 blocked。"""
    scope = _ok_scope(
        revenue_resolved_from=RESOLVED_FROM_FALLBACK,
        revenue_original=(),
        revenue_exact=False,
        unmapped_standard=("6001",),
    )
    result = classify_d4_source_status(scope)
    assert result["state"] == D4_SOURCE_STATUS_BLOCKED
