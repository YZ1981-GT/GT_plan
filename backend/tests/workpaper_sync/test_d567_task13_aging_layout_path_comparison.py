# -*- coding: utf-8 -*-
"""Task 13 欠账：裁决 G2「两条账龄路径对照」的可执行落点。

spec: d567-sync-coverage-via-row-table-engine · Task 13 / Task 11 · Requirements 3.7, 6.1

═══ 为什么原来判成「无对照分母」，以及为什么那个结论需要补一层 ═══

Task 13 原文如实登记：`D7-5`/`D7-6` 实测 `aging_layout=None`（sheet 自身无账龄组）
⇒ **本轮新增 sheet 上没有 nested/flat 对照分母**。这个事实**成立**（本文件现算复核：
D5-2 / D7-5 / D7-6 三张的 `expand_aging_fields()` 均为 0 条）。

但裁决 G2 的对照价值并没有因此消失 —— 两条路径由**已接入**的 `D6-2`(flat) 与
`D7-2`(nested) 承载，对照完全可以离线做，而且做得出比「没有分母」更硬的结论。

═══ 现算得到的路径差异（2026-09-30 实测）═══

                     flat（D6-2）                     nested（D7-2 / D3-2）
  segments 元组数     **3**（flat_key, col, label）    **2**（seg_key, col）
  leaf_labels         **空**（label 在 segment 里）     **非空**（与 segments 并行）
  json_prefix         **空串**                         `agingPrior` / `agingAudited`
  key 派生            `snake(flat_key)`                `{snake(json_prefix)}_{seg.lower()}`
  json_key            `agePrior1y`（**无 `/`**）        `agingPrior/within1`（**有 `/`**）
  展开条数            8（2 组 × 4 段）                  8（2 组 × 4 段）

🔴 **两条路径的展开条数相同、只有命名规则不同** —— 这正是「差异必须能归因到
   `aging_layout` 而非别处」的精确表述：数量维度不受 layout 影响，命名维度完全由它决定。

═══ 🔴 归因的决定性证据：只翻 `aging_layout` 会**响亮失败**，不会静默产错键 ═══

  `dataclasses.replace(SPEC_D62, aging_layout=nested)` → `ValueError: 账龄组 有 4 段，
      但 leaf_labels 有 0 个 —— 段与标签必须一一对应`
  `dataclasses.replace(SPEC_D72, aging_layout=flat)`   → `ValueError: not enough values
      to unpack (expected 3, got 2)`

  ⇒ layout 与 `aging_groups` 的形态**结构耦合**（元组数 / leaf_labels / json_prefix 三处同时不同），
    不存在「layout 写错但键照样产出」的静默路径。这比「输出差异能归因到 layout」更强：
    **形态错配根本走不到产键那一步**。故裁决 G2 的对照在本文件转为可执行判据。
"""
from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    AgingLayout,
    expand_aging_fields,
)
from app.services.workpaper_sync.phase5_d3_prepaid_receipts import SPEC_D32  # noqa: E402
from app.services.workpaper_sync.phase5_d5_receivables_financing import SPEC_D52  # noqa: E402
from app.services.workpaper_sync.phase5_d6_contract_assets import SPEC_D62  # noqa: E402
from app.services.workpaper_sync.phase5_d7_05_long_term import SPEC_D705  # noqa: E402
from app.services.workpaper_sync.phase5_d7_06_related_party import SPEC_D706  # noqa: E402
from app.services.workpaper_sync.phase5_d7_contract_liabilities import SPEC_D72  # noqa: E402

#: 7 元组下标（`expand_aging_fields` 的返回形态）。
_KEY, _COL, _MODE, _VTYPE, _JSON_KEY, _LEAF, _HDR = range(7)

#: 🔴 实测键清单（2026-09-30）。**这不是可随手改的数字** —— 它们是落库 store 键的
#:    组成部分，改动即破坏既有项目数据的读取。变更必须走迁移，不得直接改本期望。
_FLAT_KEYS_D62 = (
    "age_prior1y", "age_prior1to2y", "age_prior2to3y", "age_prior3y_above",
    "age_end1y", "age_end1to2y", "age_end2to3y", "age_end3y_above",
)
_NESTED_KEYS_D72 = (
    "aging_prior_within1", "aging_prior_y1to2", "aging_prior_y2to3", "aging_prior_over3",
    "aging_audited_within1", "aging_audited_y1to2", "aging_audited_y2to3", "aging_audited_over3",
)


# ═══════════════════════════════════════════════════════════════════════════
# 一、两条路径各自的形态与产键（裁决 G2 的对照本体）
# **Validates: Requirements 3.7**
# ═══════════════════════════════════════════════════════════════════════════


def test_flat_path_shape_and_keys_d62() -> None:
    """flat 路径（D6-2，引擎 flat 唯一样本）：3 元 segments / 空 leaf_labels / json_key 无 `/`。"""
    assert SPEC_D62.aging_layout is AgingLayout.flat
    for group in SPEC_D62.aging_groups:
        assert group.json_prefix == "", "flat 路径的 json_prefix 应为空串（键不带前缀）"
        assert group.leaf_labels == (), "flat 路径的 leaf_labels 应为空（label 在 segment 第 3 位）"
        for seg in group.segments:
            assert len(seg) == 3, f"flat segment 应为 3 元 (key, col, label)，实得 {len(seg)} 元"
    expanded = expand_aging_fields(SPEC_D62)
    assert tuple(f[_KEY] for f in expanded) == _FLAT_KEYS_D62
    for f in expanded:
        assert "/" not in f[_JSON_KEY], f"flat 的 json_key 不应含 `/`，实得 {f[_JSON_KEY]!r}"
        assert f[_MODE] == "editable" and f[_VTYPE] == "amount"
        assert f[_LEAF], "leaf_label 不应为空（前端表头要用）"


def test_nested_path_shape_and_keys_d72() -> None:
    """nested 路径（D7-2）：2 元 segments / 非空 leaf_labels / json_key 形如 `prefix/seg`。"""
    assert SPEC_D72.aging_layout is AgingLayout.nested
    for group in SPEC_D72.aging_groups:
        assert group.json_prefix, "nested 路径的 json_prefix 必须非空（键要带它）"
        assert len(group.leaf_labels) == len(group.segments), "nested 的段与标签必须一一对应"
        for seg in group.segments:
            assert len(seg) == 2, f"nested segment 应为 2 元 (key, col)，实得 {len(seg)} 元"
    expanded = expand_aging_fields(SPEC_D72)
    assert tuple(f[_KEY] for f in expanded) == _NESTED_KEYS_D72
    for f in expanded:
        assert "/" in f[_JSON_KEY], f"nested 的 json_key 应含 `/`，实得 {f[_JSON_KEY]!r}"
        prefix, _, seg = f[_JSON_KEY].partition("/")
        assert prefix and seg, "nested json_key 两侧都应非空"


def test_expansion_count_is_layout_independent() -> None:
    """🔴 归因的量化面：两条路径的**展开条数相同**（组数 × 段数），只有命名规则不同。

    这是「差异必须能归因到 `aging_layout` 而非别处」的精确表述 —— 若 layout 还影响条数，
    就说明它耦合了几何，那对照就不干净了。
    """
    for label, spec in (("D6-2/flat", SPEC_D62), ("D7-2/nested", SPEC_D72), ("D3-2/nested", SPEC_D32)):
        expected = sum(len(g.segments) for g in spec.aging_groups)
        actual = len(expand_aging_fields(spec))
        assert actual == expected, f"{label}: 展开 {actual} 条 ≠ 组×段 {expected} 条"


def test_nested_rule_is_a_rule_not_a_coincidence() -> None:
    """nested 规则跨 entry 一致：D3-2 与 D7-2 的 **key 集合完全相同**（只有列不同）。

    若 nested 的键派生依赖 entry 而非规则，这条会红 —— 它证明 `expand_aging_fields`
    的 nested 分支是通用规则，不是某家的特例。
    """
    k32 = tuple(f[_KEY] for f in expand_aging_fields(SPEC_D32))
    k72 = tuple(f[_KEY] for f in expand_aging_fields(SPEC_D72))
    assert k32 == k72 == _NESTED_KEYS_D72
    # 列**必须**不同（否则两家几何撞了，说明取错了 spec）。
    c32 = tuple(f[_COL] for f in expand_aging_fields(SPEC_D32))
    c72 = tuple(f[_COL] for f in expand_aging_fields(SPEC_D72))
    assert c32 != c72, "D3-2 与 D7-2 的账龄列不应完全相同（几何应各自实测）"


def test_flat_and_nested_key_sets_are_disjoint() -> None:
    """两条路径的键空间**不相交** ⇒ 同一 store 里不会互相顶掉（跨路径污染的反证）。"""
    flat = set(f[_KEY] for f in expand_aging_fields(SPEC_D62))
    nested = set(f[_KEY] for f in expand_aging_fields(SPEC_D72))
    assert flat & nested == set(), f"两路径键空间相交：{sorted(flat & nested)}"


# ═══════════════════════════════════════════════════════════════════════════
# 二、🔴 归因的决定性证据：只翻 layout ⇒ 响亮失败，不静默产错键
# **Validates: Requirements 3.7, 6.1**
# ═══════════════════════════════════════════════════════════════════════════


def test_flipping_layout_on_flat_spec_raises_loudly() -> None:
    """flat → nested：`leaf_labels` 为空 ⇒ 引擎抛 ValueError 并点名「段与标签必须一一对应」。"""
    flipped = dataclasses.replace(SPEC_D62, aging_layout=AgingLayout.nested)
    with pytest.raises(ValueError) as ei:
        expand_aging_fields(flipped)
    assert "leaf_labels" in str(ei.value), f"错误文案未点名 leaf_labels：{ei.value}"


def test_flipping_layout_on_nested_spec_raises_loudly() -> None:
    """nested → flat：segments 是 2 元而 flat 分支要解 3 元 ⇒ 抛 ValueError（解包失败）。"""
    flipped = dataclasses.replace(SPEC_D72, aging_layout=AgingLayout.flat)
    with pytest.raises(ValueError) as ei:
        expand_aging_fields(flipped)
    assert "unpack" in str(ei.value), f"错误文案不是解包失败：{ei.value}"


def test_layout_is_structurally_coupled_in_three_observable_ways() -> None:
    """🔴 归因总纲：layout 与 `aging_groups` 形态在**三处**同时不同 ⇒ 不存在静默混淆路径。

    三处 = ①segments 元组数 ②leaf_labels 是否为空 ③json_prefix 是否为空。
    任一处被改成「两路径相同」，上面两条 flip 判据就会失去意义 ⇒ 本条把三处一起钉死。
    """
    flat_arity = {len(s) for g in SPEC_D62.aging_groups for s in g.segments}
    nested_arity = {len(s) for g in SPEC_D72.aging_groups for s in g.segments}
    assert flat_arity == {3} and nested_arity == {2}, (
        f"segments 元组数不再二分：flat={flat_arity} nested={nested_arity}"
    )
    assert all(g.leaf_labels == () for g in SPEC_D62.aging_groups)
    assert all(g.leaf_labels != () for g in SPEC_D72.aging_groups)
    assert all(g.json_prefix == "" for g in SPEC_D62.aging_groups)
    assert all(g.json_prefix != "" for g in SPEC_D72.aging_groups)


# ═══════════════════════════════════════════════════════════════════════════
# 三、第三条路径（layout=None）与 Task 13 原判断的复核
# **Validates: Requirements 3.7**
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "label,spec",
    [("D5-2", SPEC_D52), ("D7-5", SPEC_D705), ("D7-6", SPEC_D706)],
)
def test_layout_none_expands_to_nothing(label: str, spec: object) -> None:
    """🔴 复核 Task 13 原判断：`D7-5`/`D7-6` 确实 `aging_layout=None` ⇒ 展开 0 条。

    这条同时是「本轮新增 sheet 上没有 nested/flat 对照分母」这一如实登记的**可执行依据**
    —— 不是凭注释声明，而是现算复核。D5-2 作为引擎「无分组」路径基准一并在案。
    """
    assert spec.aging_layout is None  # type: ignore[attr-defined]
    assert spec.aging_groups == ()  # type: ignore[attr-defined]
    assert expand_aging_fields(spec) == ()  # type: ignore[arg-type]


def test_three_paths_are_all_covered_by_wired_entries() -> None:
    """三条路径（flat / nested / None）都有**已接入**的承载 entry ⇒ 引擎分派无未覆盖分支。

    `expand_aging_fields` 的 if 只有这三个分支；本条钉住每个分支都有真实样本，
    防止「某条路径没有任何 entry 走」导致回归门看不见它。
    """
    by_layout = {
        AgingLayout.flat: [SPEC_D62],
        AgingLayout.nested: [SPEC_D72, SPEC_D32],
        None: [SPEC_D52, SPEC_D705, SPEC_D706],
    }
    for layout, specs in by_layout.items():
        assert specs, f"路径 {layout} 无承载样本"
        for spec in specs:
            assert spec.aging_layout is layout
    # 分派分支数 = 3（None / nested / flat），与引擎 if 结构一致。
    assert len(by_layout) == 3


# ═══════════════════════════════════════════════════════════════════════════
# 四、变异自检：判据有牙齿
# ═══════════════════════════════════════════════════════════════════════════


def test_mutation_expected_key_list_has_teeth() -> None:
    """🔴 变异：把 flat 的期望键换成 nested 的那套 ⇒ 必不相等（证明键清单不是恒真装饰）。"""
    flat = tuple(f[_KEY] for f in expand_aging_fields(SPEC_D62))
    assert flat == _FLAT_KEYS_D62
    assert flat != _NESTED_KEYS_D72, "flat 与 nested 的键清单竟相同 ⇒ 对照失去意义"


def test_mutation_json_key_slash_discriminator_has_teeth() -> None:
    """🔴 变异：`/` 判别器必须真能区分两路径（flat 全无 `/`、nested 全有）。"""
    flat_has_slash = [f[_JSON_KEY] for f in expand_aging_fields(SPEC_D62) if "/" in f[_JSON_KEY]]
    nested_no_slash = [f[_JSON_KEY] for f in expand_aging_fields(SPEC_D72) if "/" not in f[_JSON_KEY]]
    assert flat_has_slash == [], f"flat 出现带 `/` 的 json_key：{flat_has_slash}"
    assert nested_no_slash == [], f"nested 出现不带 `/` 的 json_key：{nested_no_slash}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v", "--tb=short"]))
