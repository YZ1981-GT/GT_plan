"""F4 账龄枚举统一 — 后端期间注册与 F4-2 动态账龄导入导出。

Spec: .kiro/specs/f4-aging-enum-unification/ Task 6.1 / 6.2

- Property 11：`subject_aging_periods('F4')` 恒返回 `['current','audited']`，
  列头后缀恒为「期末未审」「期末审定」，不含「期初」。
- Property 9：任意段集合下 F4-2 导出→导入账龄金额不变（Round_Trip）。
- Property 10：不属于生效段的账龄列被跳过并出现在 unmatched。
- Property 12：前后端 F4 默认预设一致（THREE_YEAR）。
"""
from __future__ import annotations

import pytest

from app.routers.wp_render_strategies._cycle_import_export_common import (
    aging_export_values,
    build_aging_headers,
    match_import_aging,
    subject_aging_periods,
)
from app.routers.wp_render_strategies._f4_import_export import (
    _F4_2_BASE_HEADERS,
    _F4_2_BASE_KEYS,
    _F4_SPECS,
)
from app.services import aging_config_service as acs

THREE = acs.resolve_segments(acs.AgingPreset.THREE_YEAR, None)
FIVE = acs.resolve_segments(acs.AgingPreset.FIVE_YEAR, None)
F4_PERIODS = subject_aging_periods("F4")


class TestF4Periods:
    def test_f4_periods_are_closing_two_period(self) -> None:
        """Property 11：F4 = 期末未审 + 期末审定（无期初）。"""
        assert F4_PERIODS == ["current", "audited"]

    @pytest.mark.parametrize("segments", [THREE, FIVE])
    def test_headers_have_no_prior_suffix(self, segments: list) -> None:
        headers = build_aging_headers(segments, F4_PERIODS)
        assert len(headers) == 2 * len(segments)
        assert all("(期初)" not in h for h in headers)
        for seg in segments:
            assert f"{seg.label}(期末未审)" in headers
            assert f"{seg.label}(期末审定)" in headers

    def test_other_subjects_unchanged(self) -> None:
        """additive：不改三期科目与 D3 既有行为。"""
        assert subject_aging_periods("D2") == ["prior", "current", "audited"]
        assert subject_aging_periods("F1") == ["prior", "current", "audited"]
        assert subject_aging_periods("D3") == ["prior", "audited"]
        assert subject_aging_periods("D7") == ["prior", "audited"]

    def test_backend_default_preset_is_three_year(self) -> None:
        """Property 12：后端 F4 默认预设 = THREE_YEAR（与前端一致）。"""
        assert acs.DEFAULT_SUBJECT_PRESETS.get("F4") == acs.AgingPreset.THREE_YEAR


class TestF42Spec:
    def test_spec_uses_aging_descriptor(self) -> None:
        sp = _F4_SPECS["F4-2"]
        aging = sp.get("aging")
        assert aging and aging["subject"] == "F4"
        assert aging["base_headers"] == _F4_2_BASE_HEADERS
        assert aging["base_field_keys"] == _F4_2_BASE_KEYS
        assert len(_F4_2_BASE_HEADERS) == len(_F4_2_BASE_KEYS)

    def test_base_headers_contain_no_static_aging_columns(self) -> None:
        assert all("账龄" not in h for h in _F4_2_BASE_HEADERS)
        assert all(not k.endswith(("AgingLt1", "Aging1to2", "Aging2to3", "AgingGt3"))
                   for k in _F4_2_BASE_KEYS)


class TestF42AgingRoundTrip:
    @pytest.mark.parametrize("segments", [THREE, FIVE])
    def test_round_trip_preserves_amounts(self, segments: list) -> None:
        """Property 9：导出→导入各段金额不变。"""
        row = {
            "agingCurrent": {seg.key: 100.0 + i for i, seg in enumerate(segments)},
            "agingAudited": {seg.key: 200.0 + i for i, seg in enumerate(segments)},
        }
        headers = build_aging_headers(segments, F4_PERIODS)
        values = aging_export_values(row, segments, F4_PERIODS)
        assert len(headers) == len(values)
        cells = dict(zip(headers, values))

        nested, unmatched = match_import_aging(
            cells.get, list(cells.keys()), segments, F4_PERIODS,
        )
        assert unmatched == []
        assert nested["agingCurrent"] == row["agingCurrent"]
        assert nested["agingAudited"] == row["agingAudited"]
        assert "agingPrior" not in nested

    def test_unmatched_aging_column_skipped(self) -> None:
        """Property 10：外来账龄列跳过并进 unmatched。"""
        cells = {f"{seg.label}(期末未审)": 1.0 for seg in THREE}
        cells.update({f"{seg.label}(期末审定)": 2.0 for seg in THREE})
        cells["4-5年(期末未审)"] = 999.0
        nested, unmatched = match_import_aging(
            cells.get, list(cells.keys()), THREE, F4_PERIODS,
        )
        assert "4-5年(期末未审)" in unmatched
        assert set(nested["agingCurrent"].keys()) == {s.key for s in THREE}
        assert 999.0 not in nested["agingCurrent"].values()

    def test_missing_segment_column_defaults_zero(self) -> None:
        """配置变更后旧模板缺段 → 初始化 0（不丢整行）。"""
        cells = {f"{seg.label}(期末未审)": 5.0 for seg in THREE}
        nested, _ = match_import_aging(cells.get, list(cells.keys()), FIVE, F4_PERIODS)
        assert nested["agingCurrent"]["within1"] == 5.0
        assert nested["agingCurrent"]["y4to5"] == 0.0
        assert nested["agingAudited"]["within1"] == 0.0
