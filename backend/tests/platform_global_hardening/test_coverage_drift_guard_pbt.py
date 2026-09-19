"""Feature: platform-global-hardening, Property 3

Property 3: CI_Drift_Guard 仅在正向检出时阻断、在不确定时放行
对任意底稿接线状态组合（shellWrapped、detected 各能力真值、是否登记 exemption、
扫描是否可解析）：CI_Drift_Guard SHALL 遵循——若 shellWrapped==true（auto-covered）
或已登记 exemption 或扫描无法确定接线状态（detection uncertainty），则放行（fail-open）；
当且仅当被正向检出为「应接却未接」且无豁免时，才阻断（fail-closed）。

Validates: Requirements 2.4, 2.5, 2.7, 2.8
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

# ─── 以文件路径加载被测守卫脚本 ──────────────────────────────────────────────
_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts" / "check" / "check_coverage_ledger.py"
)
_spec = importlib.util.spec_from_file_location("check_coverage_ledger", _SCRIPT)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

# ─── 能力清单（与守卫脚本保持一致）─────────────────────────────────────────────
CAPABILITIES = guard.CAPABILITIES  # ['displayPrefs', 'agingConfig', ...]
# 有触发特征定义的能力（仅这些能力可能产生"应接却未接"判定）
TRIGGERABLE_CAPS = list(guard.TRIGGER_PATTERNS.keys())


# ─── Hypothesis 策略 ─────────────────────────────────────────────────────────

# 生成 detected dict：每个能力 → True/False
_detected_strategy = st.fixed_dictionaries(
    {cap: st.booleans() for cap in CAPABILITIES}
)

# 生成 exemption：None 或有效豁免对象
_exemption_strategy = st.one_of(
    st.none(),
    st.fixed_dictionaries({
        "reason": st.text(min_size=1, max_size=50),
        "approvedBy": st.sampled_from(["manager", "partner", "admin"]),
        "at": st.text(min_size=10, max_size=10),  # 日期格式
    }),
)

# 生成 ledger entry 组合
_entry_strategy = st.fixed_dictionaries({
    "shellWrapped": st.booleans(),
    "detected": _detected_strategy,
    "exemption": _exemption_strategy,
})

# 源码是否可读/可解析（控制 fail-open 路径）
_source_readable = st.booleans()
# 触发特征是否存在（控制"应接"判定）
_trigger_present = st.booleans()


# ─── 辅助函数 ────────────────────────────────────────────────────────────────

def _build_source_with_triggers(trigger_present: bool) -> str:
    """构造含/不含触发特征的源码片段。"""
    if trigger_present:
        # 含 displayPrefs 和 agingConfig 的触发特征
        return """
<template>
  <el-table :data="tableData">
    <el-table-column prop="amount" label="金额"/>
    <el-table-column prop="balance" label="余额"/>
    <el-table-column prop="aging" label="账龄"/>
  </el-table>
</template>
"""
    else:
        # 不含任何触发特征的纯展示组件
        return """
<template>
  <div class="info-panel">
    <p>{{ description }}</p>
    <span>{{ status }}</span>
  </div>
</template>
"""


def _compute_expected_violations(
    root_code: str,
    entry: dict[str, Any],
    source_readable: bool,
    trigger_present: bool,
) -> list[tuple[str, str]]:
    """计算给定组合下预期的违规列表（手工实现判定逻辑作为 oracle）。

    判定规则（Req 2.4/2.5/2.7/2.8）：
    - shellWrapped=True → 放行，无违规
    - exemption 存在 → 放行，无违规
    - 源码不可读 → 无法判定 → fail-open，无违规
    - 对每个有触发特征定义的能力：
      - 触发特征不存在 → 不应接 → 无违规
      - 触发特征存在 + detected=True → 已接线 → 无违规
      - 触发特征存在 + detected=False + 无 exemption → 正向检出 → 阻断
    - 无触发特征定义的能力 → 无法判定是否应接 → fail-open
    """
    violations: list[tuple[str, str]] = []

    # shellWrapped → auto-covered (Req 2.7)
    if entry.get("shellWrapped", False):
        return []

    # exemption → 放行
    if entry.get("exemption"):
        return []

    # 源码不可读 → 无法判定 → fail-open (Req 2.8)
    if not source_readable:
        return []

    detected = entry.get("detected", {})
    for cap in CAPABILITIES:
        # 已检出接入 → 无问题
        if detected.get(cap, False):
            continue

        # 仅有触发特征定义的能力才可能产生违规
        if cap not in TRIGGERABLE_CAPS:
            # 无触发特征定义 → 无法判定 → fail-open
            continue

        if not trigger_present:
            # 不具备触发特征 → 不应接 → 无违规
            continue

        # 正向检出：有触发特征 + detected=false + 无 exemption → 违规
        violations.append((root_code, cap))

    return violations


# ─── 属性测试 ────────────────────────────────────────────────────────────────

@settings(max_examples=100)
@given(
    entry=_entry_strategy,
    source_readable=_source_readable,
    trigger_present=_trigger_present,
)
def test_drift_guard_fail_open_and_fail_closed(
    entry: dict[str, Any],
    source_readable: bool,
    trigger_present: bool,
) -> None:
    """CI_Drift_Guard 仅在正向检出时阻断、在不确定时放行。

    验证对任意接线状态组合：
    - shellWrapped=True → 永远不出现在违规列表
    - exemption 存在 → 永远不出现在违规列表
    - 源码不可读（detection uncertainty）→ 永远不出现在违规列表
    - 正向检出"应接却未接" → 必须出现在违规列表
    """
    root_code = "T1"  # 测试用固定 wp_code
    root_codes = {root_code}

    # 构造 ledger
    ledger = {"entries": {root_code: entry}}

    # 构造源码
    source = _build_source_with_triggers(trigger_present) if source_readable else None

    # Mock find_main_entry 和 read_source_safe 以控制 I/O
    mock_entry_path = Path("/fake/GtT1TestWorkpaper.vue") if source_readable else None

    with patch.object(guard, "find_main_entry", return_value=mock_entry_path):
        with patch.object(guard, "read_source_safe", return_value=source):
            actual = guard.check_violations(root_codes, ledger)

    expected = _compute_expected_violations(root_code, entry, source_readable, trigger_present)

    assert sorted(actual) == sorted(expected), (
        f"判定不一致！\n"
        f"  entry: {entry}\n"
        f"  source_readable: {source_readable}\n"
        f"  trigger_present: {trigger_present}\n"
        f"  expected: {expected}\n"
        f"  actual: {actual}"
    )


@settings(max_examples=100)
@given(entry=_entry_strategy, trigger_present=_trigger_present)
def test_shell_wrapped_always_passes(
    entry: dict[str, Any],
    trigger_present: bool,
) -> None:
    """shellWrapped=True 的底稿恒不产生违规（Req 2.7 auto-covered）。"""
    # 强制 shellWrapped=True
    entry = {**entry, "shellWrapped": True}
    root_code = "S1"
    root_codes = {root_code}
    ledger = {"entries": {root_code: entry}}
    source = _build_source_with_triggers(trigger_present)

    with patch.object(guard, "find_main_entry", return_value=Path("/fake/GtS1.vue")):
        with patch.object(guard, "read_source_safe", return_value=source):
            violations = guard.check_violations(root_codes, ledger)

    assert violations == [], (
        f"shellWrapped=True 不应产生违规，但得到 {violations}"
    )


@settings(max_examples=100)
@given(entry=_entry_strategy, trigger_present=_trigger_present)
def test_exemption_always_passes(
    entry: dict[str, Any],
    trigger_present: bool,
) -> None:
    """有 exemption 的底稿恒不产生违规。"""
    # 强制 exemption 存在
    entry = {
        **entry,
        "shellWrapped": False,
        "exemption": {"reason": "测试豁免", "approvedBy": "manager", "at": "2026-07-12"},
    }
    root_code = "E1"
    root_codes = {root_code}
    ledger = {"entries": {root_code: entry}}
    source = _build_source_with_triggers(trigger_present)

    with patch.object(guard, "find_main_entry", return_value=Path("/fake/GtE1.vue")):
        with patch.object(guard, "read_source_safe", return_value=source):
            violations = guard.check_violations(root_codes, ledger)

    assert violations == [], (
        f"有 exemption 不应产生违规，但得到 {violations}"
    )


@settings(max_examples=100)
@given(entry=_entry_strategy)
def test_unreadable_source_always_passes(entry: dict[str, Any]) -> None:
    """源码不可读时恒放行（fail-open, Req 2.8）。"""
    # 强制无 exemption、非 shellWrapped（最大化触发路径）
    entry = {**entry, "shellWrapped": False, "exemption": None}
    root_code = "U1"
    root_codes = {root_code}
    ledger = {"entries": {root_code: entry}}

    # 场景 1：找不到主入口文件
    with patch.object(guard, "find_main_entry", return_value=None):
        violations = guard.check_violations(root_codes, ledger)
    assert violations == [], "找不到主入口时应 fail-open"

    # 场景 2：主入口文件存在但不可读
    with patch.object(guard, "find_main_entry", return_value=Path("/fake/GtU1.vue")):
        with patch.object(guard, "read_source_safe", return_value=None):
            violations = guard.check_violations(root_codes, ledger)
    assert violations == [], "源码不可读时应 fail-open"


@settings(max_examples=100)
@given(
    detected=_detected_strategy,
)
def test_positive_detection_blocks(detected: dict[str, bool]) -> None:
    """正向检出"应接却未接"且无豁免时必须阻断（fail-closed）。"""
    # 构造：非套壳、无豁免、源码可读、触发特征全存在
    entry = {
        "shellWrapped": False,
        "detected": detected,
        "exemption": None,
    }
    root_code = "P1"
    root_codes = {root_code}
    ledger = {"entries": {root_code: entry}}
    # 源码含所有触发特征
    source = _build_source_with_triggers(trigger_present=True)

    with patch.object(guard, "find_main_entry", return_value=Path("/fake/GtP1.vue")):
        with patch.object(guard, "read_source_safe", return_value=source):
            violations = guard.check_violations(root_codes, ledger)

    # 对每个有触发特征且 detected=False 的能力，应在违规列表中
    for cap in TRIGGERABLE_CAPS:
        if not detected.get(cap, False):
            assert (root_code, cap) in violations, (
                f"detected[{cap}]=False 且有触发特征，应阻断但未阻断"
            )
        else:
            assert (root_code, cap) not in violations, (
                f"detected[{cap}]=True，不应阻断但被阻断"
            )
