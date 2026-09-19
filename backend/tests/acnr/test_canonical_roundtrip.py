"""PBT: CanonicalAddress round-trip — from_addr_id(ca.addr_id) == ca [P9]

**Validates: Requirements Req-6**

Property: 对于任意合法 CanonicalAddress，序列化为 addr_id 再反序列化回来，
得到的 CanonicalAddress 应与原始值相等（值对象 round-trip 无损）。
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.acnr.canonical import CanonicalAddress


# ─── Strategies ──────────────────────────────────────────────────────────────

# wp 域的合法字符（字母、数字、中文、连字符、下划线，不含 / 和 ://）
_wp_parent = st.from_regex(r"[A-Z][A-Z0-9]{0,5}", fullmatch=True)
_wp_sheet = st.from_regex(r"[A-Z0-9\u4e00-\u4e03][A-Za-z0-9\u4e00-\u9fff\-]{0,15}", fullmatch=True)
_wp_coordinate = st.from_regex(r"[A-Z][0-9]{1,4}", fullmatch=True)

# 非 wp 域
_non_wp_domains = st.sampled_from(["tb", "report", "note", "aux"])
_non_wp_parent = st.from_regex(r"[A-Za-z0-9\u4e00-\u9fff\-]{1,10}", fullmatch=True)
_non_wp_sheet = st.from_regex(r"[A-Za-z0-9\u4e00-\u9fff\-]{1,10}", fullmatch=True)
_non_wp_coordinate = st.from_regex(r"[A-Za-z0-9\u4e00-\u9fff\-]{1,10}", fullmatch=True)


@st.composite
def canonical_wp_addresses(draw: st.DrawFn) -> CanonicalAddress:
    """生成合法的 wp 域 CanonicalAddress。"""
    parent = draw(_wp_parent)
    # 三种形态: 有coordinate, 仅sheet, 仅parent
    variant = draw(st.integers(min_value=0, max_value=2))
    if variant == 0:
        # 完整三段
        sheet = draw(_wp_sheet)
        coordinate = draw(_wp_coordinate)
        return CanonicalAddress(domain="wp", parent=parent, sheet=sheet, coordinate=coordinate)
    elif variant == 1:
        # 两段（sheet 无 coordinate）
        sheet = draw(_wp_sheet)
        return CanonicalAddress(domain="wp", parent=parent, sheet=sheet, coordinate="")
    else:
        # 仅 parent
        return CanonicalAddress(domain="wp", parent=parent, sheet="", coordinate="")


@st.composite
def canonical_non_wp_addresses(draw: st.DrawFn) -> CanonicalAddress:
    """生成合法的非 wp 域 CanonicalAddress。"""
    domain = draw(_non_wp_domains)
    parent = draw(_non_wp_parent)
    # 确保 parent 不含 "://" 子串
    assume("//" not in parent)
    variant = draw(st.integers(min_value=0, max_value=2))
    if variant == 0:
        sheet = draw(_non_wp_sheet)
        assume("//" not in sheet)
        coordinate = draw(_non_wp_coordinate)
        assume("//" not in coordinate)
        return CanonicalAddress(domain=domain, parent=parent, sheet=sheet, coordinate=coordinate)
    elif variant == 1:
        sheet = draw(_non_wp_sheet)
        assume("//" not in sheet)
        return CanonicalAddress(domain=domain, parent=parent, sheet=sheet, coordinate="")
    else:
        return CanonicalAddress(domain=domain, parent=parent, sheet="", coordinate="")


# 合并策略
canonical_addresses = st.one_of(canonical_wp_addresses(), canonical_non_wp_addresses())


# ─── Property Tests ──────────────────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(ca=canonical_addresses)
def test_roundtrip_from_addr_id(ca: CanonicalAddress) -> None:
    """P9: from_addr_id(ca.addr_id) == ca — addr_id round-trip 无损。"""
    addr_id = ca.addr_id
    recovered = CanonicalAddress.from_addr_id(addr_id)
    assert recovered == ca, (
        f"Round-trip 失败:\n"
        f"  原始: {ca}\n"
        f"  addr_id: {addr_id!r}\n"
        f"  恢复: {recovered}"
    )


@settings(max_examples=5, deadline=None)
@given(ca=canonical_wp_addresses())
def test_wp_addr_id_no_domain_prefix(ca: CanonicalAddress) -> None:
    """wp 域 addr_id 不含 domain:// 前缀（兼容现有 catalog 格式）。"""
    addr_id = ca.addr_id
    assert "://" not in addr_id, f"wp 域 addr_id 不应含 ://: {addr_id}"


@settings(max_examples=5, deadline=None)
@given(ca=canonical_non_wp_addresses())
def test_non_wp_addr_id_has_domain_prefix(ca: CanonicalAddress) -> None:
    """非 wp 域 addr_id 必须含 domain:// 前缀。"""
    addr_id = ca.addr_id
    assert "://" in addr_id, f"非 wp 域 addr_id 应含 ://: {addr_id}"
    assert addr_id.startswith(f"{ca.domain}://"), (
        f"前缀不匹配: expected {ca.domain}://, got {addr_id}"
    )


@settings(max_examples=5, deadline=None)
@given(ca=canonical_addresses)
def test_frozen_immutable(ca: CanonicalAddress) -> None:
    """CanonicalAddress 是 frozen dataclass，不可修改字段。"""
    with pytest.raises(Exception):  # FrozenInstanceError
        ca.domain = "hacked"  # type: ignore[misc]
