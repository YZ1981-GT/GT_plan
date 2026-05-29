"""P4: cross_wp_references.json ref_id 唯一性 — 属性测试（spec workpaper-d-sales-cycle PBT-4）。

Validates: Requirements F8

Property P4: cross_wp_references.json 任两条 ref_id 不重复（uniqueness invariant）。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from hypothesis import given, settings, strategies as st

CROSS_WP_PATH = Path(__file__).parent.parent / "data" / "cross_wp_references.json"


def _load_references() -> list[dict]:
    """加载 cross_wp_references.json 的 references 数组。"""
    data = json.loads(CROSS_WP_PATH.read_text(encoding="utf-8"))
    return data["references"]


def test_property_p4_all_ref_ids_unique() -> None:
    """P4: cross_wp_references.json 中所有 ref_id 唯一。"""
    refs = _load_references()
    ids = [r["ref_id"] for r in refs]
    duplicates = [x for x in ids if ids.count(x) > 1]
    assert len(ids) == len(set(ids)), f"重复 ref_id: {sorted(set(duplicates))}"


@given(subset_size=st.integers(min_value=1, max_value=50))
@settings(max_examples=15, deadline=None)
def test_property_p4_random_subset_unique(subset_size: int) -> None:
    """P4: 任意子集的 ref_id 也唯一（验证无隐藏重复）。"""
    refs = _load_references()
    sample = random.sample(refs, min(subset_size, len(refs)))
    ids = [r["ref_id"] for r in sample]
    assert len(ids) == len(set(ids)), (
        f"子集中发现重复 ref_id: {[x for x in ids if ids.count(x) > 1]}"
    )
