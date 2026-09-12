"""账龄空骨架 Property 5/8 合并守卫 —— Phase 2 / Task 14.

spec: .kiro/specs/four-table-extraction-entry-completion/  (Task 14, Requirements 6.1, 6.2, 7.2, 7.4)
Properties:
  * Property 5（无账龄来源不伪造）：任意非零余额行，`sum(agingAudited.values()) == 0`，
    且**不存在**单段 == 期初/期末余额（不整额落首段，红基线④）。
  * Property 8（账龄骨架与枚举联动）：取数骨架的键集（有序）逐项等于账龄配置为该 subject
    返回的段键；驱动 builder 用不同段列表（三年 / 五年 / 自定义）时骨架键集**随之变化**。

分工（🔴 明确不重复 Task 11/12 已断言项）：
  * Task 11 `test_k1_aux_detail.py`：K1 纯函数字段名 / 关联方 / 性质分类 / merge 幂等 /
    "段为空不臆造 within1"，及 `test_aging_buckets_follow_segments_and_stay_empty`
    （FIVE/THREE 两组下 sum==0 与键==段）。
  * Task 12 `d_cycle_extraction/test_d_cycle_aging_skeleton.py`：D3/D7（2-period）端点行为
    与 `build_two_period_aging_skeleton`/`_empty_aging`/`_segment_keys` 纯函数。
  * 本文件（Task 14）**只补两处 Task 11/12 都未覆盖的行为**：
    ① Property 5 的"单段 == 余额"反证（Task 11 只断 sum==0，未断"无任一段等于余额"——
       若未来有人把余额均摊到最后一段，sum 仍可 != 余额但首段守卫漏网；本文件补
       "非零余额行不存在任一段等于 opening/closing"这条更强的不伪造断言，且覆盖 K1 3-period
       + 复用 D 循环 2-period builder 一并断，形成跨 period 统一 Property 5）。
    ② Property 8 的"枚举联动"驱动：Task 11 只用固定的 FIVE/THREE 两个常量列表各测一次，
       **未断言"同一 builder 喂不同枚举 → 键集跟着变"这条联动语义**；本文件用
       THREE_YEAR→FIVE_YEAR→CUSTOM 三种 `resolve_segments` 产物驱动同一 builder，
       断言骨架键集逐项 == 各自枚举、且三者互不相同（改一处枚举不变则红）。

🔴 断言的是**行为**（builder 真 emit 的骨架键集 / 各段之和），不是"函数存在"。
"""
from __future__ import annotations

import itertools

import pytest

from app.services.aging_config_service import (
    AgingPreset,
    AgingSegment,
    resolve_segments,
)
from app.services.d_cycle_extraction.d_aux_import import (
    build_two_period_aging_skeleton,
)
from app.services.four_table.aux_aggregation import AuxEntry
from app.services.four_table.k1_aux_detail import build_k1_detail_rows_from_aux

# 3 组账龄字段（K1 是 3-period 参照实现）
_K1_AGING_FIELDS = ("agingPrior", "agingCurrent", "agingAudited")
# 2 组账龄字段（D3/D5/D6/D7 是 2-period）
_D_AGING_FIELDS = ("agingPrior", "agingAudited")


def _ids():
    c = itertools.count(1)
    return lambda: f"row-{next(c)}"


def _preset_keys(preset: AgingPreset, custom=None) -> list[str]:
    return [s.key for s in resolve_segments(preset, custom)]


# 自定义段（模拟项目自定义 2-10 段：这里 3 段，键与三年/五年都不同）
_CUSTOM_SEGMENTS = [
    AgingSegment(key="seg_a", label="A档", dayFrom=0, dayTo=180),
    AgingSegment(key="seg_b", label="B档", dayFrom=181, dayTo=540),
    AgingSegment(key="seg_c", label="C档", dayFrom=541, dayTo=None),
]


# ─────────────────────────────────────────────────────────────────────────────
# Property 5（跨 period 统一）：非零余额行不存在"任一段 == 余额"（比 sum==0 更强）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("preset", [AgingPreset.THREE_YEAR, AgingPreset.FIVE_YEAR])
def test_property5_k1_no_single_segment_equals_balance(preset):
    """K1 3-period：非零余额行，任一账龄段都不得等于期初/期末余额（不整额落任何一档）。

    Task 11 只断 `sum(agingAudited)==0`；本条更强 —— 即使有人把余额挪到**非首段**
    （sum 仍可能因正负抵消看似 0，或落到末段绕过首段断言），只要"存在一段==余额"就红。
    """
    segs = resolve_segments(preset, None)
    opening, closing = 70.0, 130.0
    rows = build_k1_detail_rows_from_aux(
        [AuxEntry("甲公司", opening, 0.0, 0.0, closing)], segs, row_id_factory=_ids()
    )
    r = rows[0]
    assert r["beginBalance"] == opening and r["endBalance"] == closing
    for field in _K1_AGING_FIELDS:
        bucket = r[field]
        # 不伪造：任一段都不等于余额（防"整额落某档"）
        assert opening not in bucket.values(), f"{field} 出现整额落段(=opening)"
        assert closing not in bucket.values(), f"{field} 出现整额落段(=closing)"
        # 空骨架：各段之和为 0
        assert sum(bucket.values()) == 0.0, field


def test_property5_d_cycle_no_single_segment_equals_balance():
    """D 循环 2-period 骨架：任一段都不得等于余额，各段之和 0（与 K1 同一 Property 5）。"""
    segs = resolve_segments(AgingPreset.THREE_YEAR, None)
    skel = build_two_period_aging_skeleton(segs)
    assert set(skel.keys()) == set(_D_AGING_FIELDS)
    for field in _D_AGING_FIELDS:
        bucket = skel[field]
        assert sum(bucket.values()) == 0.0, field
        # 任意非零金额都不应出现在骨架里（骨架恒空）
        assert not any(v != 0.0 for v in bucket.values()), field


# ─────────────────────────────────────────────────────────────────────────────
# Property 8：驱动同一 builder 用不同枚举 → 键集跟着变（枚举联动，非固定常量两测）
# ─────────────────────────────────────────────────────────────────────────────


def _k1_skeleton_keys(segs) -> dict[str, list[str]]:
    rows = build_k1_detail_rows_from_aux(
        [AuxEntry("甲", 0.0, 0.0, 0.0, 10.0)], segs, row_id_factory=_ids()
    )
    return {f: list(rows[0][f].keys()) for f in _K1_AGING_FIELDS}


def test_property8_k1_skeleton_keys_track_enum():
    """同一 K1 builder 喂三年 / 五年 / 自定义三种段列表 → 每组骨架键集逐项等于该枚举，
    且三者互不相同（改一处枚举，骨架键随之变；硬编码常量则此断言必红，Property 8）。"""
    three_keys = _preset_keys(AgingPreset.THREE_YEAR)
    five_keys = _preset_keys(AgingPreset.FIVE_YEAR)
    custom_keys = [s.key for s in _CUSTOM_SEGMENTS]

    three = _k1_skeleton_keys(resolve_segments(AgingPreset.THREE_YEAR, None))
    five = _k1_skeleton_keys(resolve_segments(AgingPreset.FIVE_YEAR, None))
    custom = _k1_skeleton_keys(_CUSTOM_SEGMENTS)

    for field in _K1_AGING_FIELDS:
        assert three[field] == three_keys, f"{field} 三年段键集不符"
        assert five[field] == five_keys, f"{field} 五年段键集不符"
        assert custom[field] == custom_keys, f"{field} 自定义段键集不符"

    # 联动：三种枚举的键集必须彼此不同（若 builder 硬编码单一常量则三者全等 → 红）
    assert three["agingAudited"] != five["agingAudited"], "三年↔五年键集应不同"
    assert three["agingAudited"] != custom["agingAudited"], "三年↔自定义键集应不同"
    assert five["agingAudited"] != custom["agingAudited"], "五年↔自定义键集应不同"
    # 段数随枚举变（4 / 6 / 3）
    assert (len(three_keys), len(five_keys), len(custom_keys)) == (4, 6, 3)


def test_property8_d_cycle_skeleton_keys_track_enum():
    """D 循环 2-period 骨架键集也随枚举变（三年 4 键 / 五年 6 键 / 自定义 3 键）。"""
    three = build_two_period_aging_skeleton(resolve_segments(AgingPreset.THREE_YEAR, None))
    five = build_two_period_aging_skeleton(resolve_segments(AgingPreset.FIVE_YEAR, None))
    custom = build_two_period_aging_skeleton(_CUSTOM_SEGMENTS)

    for field in _D_AGING_FIELDS:
        assert list(three[field].keys()) == _preset_keys(AgingPreset.THREE_YEAR), field
        assert list(five[field].keys()) == _preset_keys(AgingPreset.FIVE_YEAR), field
        assert list(custom[field].keys()) == [s.key for s in _CUSTOM_SEGMENTS], field

    assert list(three["agingAudited"].keys()) != list(five["agingAudited"].keys())
    assert list(three["agingAudited"].keys()) != list(custom["agingAudited"].keys())
