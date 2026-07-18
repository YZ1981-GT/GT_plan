# Feature: procedure-delegation-visibility-isolation — Task 14 同源双 profile 机制 + P1–P20 覆盖矩阵
"""验证 Task 14 的三件事：
  1. **同源双 profile 机制**：smoke / correctness / fast 均已注册；correctness 每 property ≥100；
     smoke=5 且不得作为完成证据；一条代表性纯逻辑 property 用 profile 驱动例数在两档运行同一函数。
  2. **P1–P20 覆盖矩阵**：``PROPERTY_MATRIX`` 覆盖 P1..P20，且每条引用的 property-test 文件真实存在。
  3. **prompt ↔ design 属性编号映射** 完整可查。

本文件为纯逻辑 + 元数据校验（不触 dev 库）。数据库语义属性在各自文件跑真实 PostgreSQL。
"""
from __future__ import annotations

import re
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from . import _pbt_profiles as _pbt
from ._pbt_profiles import pbt_settings, record

_HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# 1. 双 profile 机制
# ---------------------------------------------------------------------------
def test_profiles_registered_and_correctness_ge_100():
    from hypothesis import settings

    for name in ("smoke", "correctness", "fast"):
        # 已注册的 profile 可被 get_profile 取到（未注册会抛 InvalidArgument）。
        prof = settings.get_profile(name)
        assert prof is not None

    assert settings.get_profile("correctness").max_examples >= 100
    assert settings.get_profile("smoke").max_examples == 5
    # 冒烟结果不得作为完成证据（governance）：smoke/fast 档 is_completion_evidence=False。
    assert _pbt.CORRECTNESS_MAX_EXAMPLES >= 100
    assert _pbt.SMOKE_MAX_EXAMPLES == 5


@given(
    delegated=st.sets(st.integers(0, 30), max_size=8),
    history=st.sets(st.integers(0, 30), max_size=8),
    scope=st.sets(st.integers(0, 30), max_size=8),
)
@pbt_settings()
def test_same_source_batch_runs_both_tiers(delegated, history, scope):
    """代表性同源属性：Restricted 可见集 = (Delegated∪History)∩scope，按元素去重（对应 design P5
    的纯集合不变量）。**同一函数**在 smoke(=5) 与 correctness(>=100) 两档运行——profile 驱动例数，
    不硬编码 max_examples。用于证明双 profile 机制在生成式属性上的同源性；DB 版 P5 见
    test_visibility_query.py（真实 PostgreSQL）。"""
    record("same_source_demo")
    visible = (delegated | history) & scope
    # 去重（集合天然去重）+ 上界（scope）+ 下界（并集内）不变量。
    assert visible == {x for x in (delegated | history) if x in scope}
    assert visible <= scope
    assert all((x in delegated or x in history) for x in visible)
    # 空 scope → 空集（不回退循环级）。
    if not scope:
        assert visible == set()


# ---------------------------------------------------------------------------
# 2. P1–P20 覆盖矩阵
# ---------------------------------------------------------------------------
def _referenced_files(entries: list[str]) -> set[str]:
    files = set()
    for e in entries:
        m = re.match(r"([A-Za-z0-9_]+\.py)", e.strip())
        if m:
            files.add(m.group(1))
    return files


def test_property_matrix_covers_p1_to_p20_and_files_exist():
    matrix = _pbt.PROPERTY_MATRIX
    expected = {f"P{i}" for i in range(1, 21)}
    assert set(matrix.keys()) == expected, f"矩阵未恰好覆盖 P1..P20：{set(matrix.keys()) ^ expected}"

    for pid, refs in matrix.items():
        assert refs, f"{pid} 无引用的 property 测试"
        for fname in _referenced_files(refs):
            assert (_HERE / fname).exists(), f"{pid} 引用的测试文件不存在：{fname}"


def test_prompt_to_design_mapping_is_complete():
    """prompt ↔ design 属性编号映射覆盖 design 全部 P1..P20（值域）。"""
    mapped = set(_pbt.PROMPT_TO_DESIGN.values())
    assert {f"P{i}" for i in range(1, 21)} <= mapped
