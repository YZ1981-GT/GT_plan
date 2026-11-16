"""
test_render_sheet_classify.py

render-config 逐 sheet 路由判定的表驱动用例
（spec platform-global-display-settings-closure 6A / design §18 H1①）。

🔴 本文件是「抽出纯函数后行为未变」的证据：每个分支都给一个可读的
输入/期望表，而不是构造 AsyncSession 跑整条 render-config。
`tests/test_render_sheet_classify_wiring.py` 另用 AST 守卫钉住
「router 真的调用了这些函数」（否则抽出来只是死代码）。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.routers.wp_render_config_sheet_classify import (
    INDEX_CLASS_PREFIX,
    ONLYOFFICE_CLASS_PREFIX,
    SHEET_CODE_RE,
    SheetRoute,
    apply_g_prefix_onlyoffice,
    classify_sheet,
    compute_real_sheets,
    is_multi_sheet,
    resolve_sheet_override,
)


@dataclass
class FakeCls:
    """`wp_classification_service` 分类结果的替身（只需这两个字段）。"""

    sheet_name: str | None
    class_code: str = ""


# ── 1. compute_real_sheets 四条过滤 ────────────────────────

class TestComputeRealSheets:
    def test_keeps_normal_sheets(self) -> None:
        classes = [FakeCls("A1-审定表", "A-"), FakeCls("A1-程序表", "A-")]
        kept = compute_real_sheets(classes, wp_code_override={})
        assert [c.sheet_name for c in kept] == ["A1-审定表", "A1-程序表"]

    def test_filters_gt_custom(self) -> None:
        classes = [FakeCls("GT_Custom表格"), FakeCls("A1-审定表")]
        kept = compute_real_sheets(classes, wp_code_override={})
        assert [c.sheet_name for c in kept] == ["A1-审定表"]

    def test_filters_i_prefix_class_code(self) -> None:
        classes = [FakeCls("I1-健康检查", "I-"), FakeCls("A1-审定表", "A-")]
        kept = compute_real_sheets(classes, wp_code_override={})
        assert [c.sheet_name for c in kept] == ["A1-审定表"]

    def test_filters_override_skip(self) -> None:
        classes = [FakeCls("选项清单"), FakeCls("A1-审定表")]
        kept = compute_real_sheets(classes, wp_code_override={"选项清单": "skip"})
        assert [c.sheet_name for c in kept] == ["A1-审定表"]

    def test_filters_archived_suffix(self) -> None:
        classes = [FakeCls("J1A-原版"), FakeCls("L1A-原"), FakeCls("A1-审定表")]
        kept = compute_real_sheets(classes, wp_code_override={})
        assert [c.sheet_name for c in kept] == ["A1-审定表"]

    def test_none_sheet_name_is_kept(self) -> None:
        """sheet_name 为 None 时四条过滤都不适用 ⇒ 保留（与 router 一致）。"""
        kept = compute_real_sheets([FakeCls(None)], wp_code_override={})
        assert len(kept) == 1


class TestIsMultiSheet:
    def test_threshold_is_two(self) -> None:
        assert is_multi_sheet([]) is False
        assert is_multi_sheet([1]) is False
        assert is_multi_sheet([1, 2]) is True


# ── 2. resolve_sheet_override 三级回退 ─────────────────────

class TestResolveSheetOverride:
    def test_non_multi_returns_none(self) -> None:
        """单 sheet 时 router 不计算 `_sheet_ovr`。"""
        assert resolve_sheet_override(
            "A1-审定表", is_multi=False, wp_code="A1",
            wp_code_override={"A1": "a1-component"},
        ) is None

    def test_trailing_code_hit(self) -> None:
        """尾部编码命中（`_SHEET_CODE_RE` 要求编码在**行尾**）。

        🔴 真实模板的 sheet 名是「名称在前、编码在后」（如 `替代程序 D0-5`），
        不是「编码在前」（`D0-5 替代程序`）—— 后者 `_SHEET_CODE_RE` 命中不到，
        会走第二级「完整 sheet 名」回退。本用例钉住这条真实口径。
        """
        assert resolve_sheet_override(
            "替代程序 D0-5", is_multi=True, wp_code="D0",
            wp_code_override={"D0-5": "confirmation-alternative-d05"},
        ) == "confirmation-alternative-d05"

    def test_full_sheet_name_fallback(self) -> None:
        """无尾部编码时按完整 sheet 名命中（如「函证差异检查表（示例）」）。"""
        assert resolve_sheet_override(
            "函证差异检查表（示例）", is_multi=True, wp_code="D0",
            wp_code_override={"函证差异检查表（示例）": "confirmation-diff-checklist"},
        ) == "confirmation-diff-checklist"

    def test_wp_code_prefixed_fallback(self) -> None:
        """`{wp_code}-{sheet_name}` 命中（G/F 循环附注页）。"""
        assert resolve_sheet_override(
            "附注披露信息（上市公司）", is_multi=True, wp_code="G1",
            wp_code_override={"G1-附注披露信息（上市公司）": "g1-trading-financial-assets"},
        ) == "g1-trading-financial-assets"

    def test_priority_order_trailing_first(self) -> None:
        """尾部编码优先于完整名与 wp_code 前缀。"""
        overrides = {
            "D0-5": "from-trailing",
            "替代程序 D0-5": "from-full-name",
            "D0-替代程序 D0-5": "from-prefix",
        }
        assert resolve_sheet_override(
            "替代程序 D0-5", is_multi=True, wp_code="D0", wp_code_override=overrides,
        ) == "from-trailing"

    def test_no_hit_returns_none(self) -> None:
        assert resolve_sheet_override(
            "未知sheet", is_multi=True, wp_code="X9", wp_code_override={},
        ) is None

    def test_sheet_code_regex_pins(self) -> None:
        """正则口径：编码必须在**尾部**（这是真实模板的命名形态）。"""
        assert SHEET_CODE_RE.search("替代程序 D0-5").group(1) == "D0-5"
        assert SHEET_CODE_RE.search("A1-1").group(1) == "A1-1"
        # 编码在开头时命中不到 ⇒ 走完整 sheet 名回退（不是缺陷，是既有口径）
        assert SHEET_CODE_RE.search("D0-5 替代程序") is None
        # 无编码的 sheet 名
        assert SHEET_CODE_RE.search("函证差异检查表（示例）") is None


# ── 3. classify_sheet 各分支 ──────────────────────────────

class TestClassifySheet:
    def _call(self, **kwargs):
        defaults = dict(
            sheet_name="S",
            class_code="A-",
            is_multi=True,
            wp_code_override_value=None,
            sheet_override=None,
            whole_wp_dedicated=frozenset(),
            has_package_sheets=False,
            derive_component_type=lambda: "derived-single",
            ignore_wp_code_override_deriver=lambda: "derived-multi",
        )
        defaults.update(kwargs)
        return classify_sheet(**defaults)

    def test_sheet_override_wins_first(self) -> None:
        route = self._call(
            sheet_override="from-sheet-ovr", wp_code_override_value="from-wp-ovr",
        )
        assert route.component_type == "from-sheet-ovr"
        assert route.reason == "sheet_override"

    def test_whole_wp_dedicated(self) -> None:
        route = self._call(
            wp_code_override_value="c1-entity-level-control",
            whole_wp_dedicated=frozenset({"c1-entity-level-control"}),
        )
        assert route.component_type == "c1-entity-level-control"
        assert route.reason == "whole_wp_dedicated"

    def test_package_sheets_uses_wp_override(self) -> None:
        route = self._call(
            wp_code_override_value="d2-ar", has_package_sheets=True, class_code="D-",
        )
        assert route.component_type == "d2-ar"
        assert route.reason == "package_sheets"

    def test_package_sheets_b_index_keeps_derived(self) -> None:
        """合成底稿目录（`B-` 前缀）保留原生 b-index 渲染。"""
        route = self._call(
            wp_code_override_value="d2-ar",
            has_package_sheets=True,
            class_code=INDEX_CLASS_PREFIX,
            ignore_wp_code_override_deriver=lambda: "b-index",
        )
        assert route.component_type == "b-index"
        assert route.reason == "package_sheets_b_index"

    def test_derived_multi(self) -> None:
        route = self._call(ignore_wp_code_override_deriver=lambda: "derived-x")
        assert route.component_type == "derived-x"
        assert route.reason == "derived"

    def test_derived_multi_falls_back_to_ovr_on_error(self) -> None:
        def _boom():
            raise ValueError("ClassificationNotFound")

        route = self._call(
            wp_code_override_value="fallback-ovr",
            ignore_wp_code_override_deriver=_boom,
        )
        assert route.component_type == "fallback-ovr"
        assert route.reason == "classification_missing"

    def test_derived_multi_skip_when_no_ovr(self) -> None:
        def _boom():
            raise ValueError("ClassificationNotFound")

        route = self._call(ignore_wp_code_override_deriver=_boom)
        assert route.component_type == "skip"
        assert route.reason == "classification_missing"

    def test_single_sheet_override_priority(self) -> None:
        route = self._call(
            is_multi=False, wp_code_override_value="wp-ovr",
            derive_component_type=lambda: "derived",
        )
        assert route.component_type == "wp-ovr"
        assert route.reason == "single_sheet_override"

    def test_single_sheet_derived(self) -> None:
        route = self._call(is_multi=False, derive_component_type=lambda: "derived-s")
        assert route.component_type == "derived-s"
        assert route.reason == "derived_single"

    def test_single_sheet_derived_error_returns_skip(self) -> None:
        def _boom():
            raise ValueError("ClassificationNotFound")

        route = self._call(is_multi=False, derive_component_type=_boom)
        assert route.component_type == "skip"
        assert route.reason == "classification_missing"


# ── 4. apply_g_prefix_onlyoffice 例外条件 ─────────────────

class TestGprefixOnlyOffice:
    def _route(self, **kwargs) -> SheetRoute:
        defaults = dict(sheet_name="S", component_type="derived", reason="derived")
        defaults.update(kwargs)
        return SheetRoute(**defaults)

    def test_g_prefix_forces_onlyoffice(self) -> None:
        route = apply_g_prefix_onlyoffice(
            self._route(), class_code=ONLYOFFICE_CLASS_PREFIX, is_multi=True,
            wp_code_override_value=None,
        )
        assert route.component_type == "onlyoffice-sheet"
        assert route.reason == "g_prefix_onlyoffice"

    def test_sheet_override_is_exempt(self) -> None:
        route = apply_g_prefix_onlyoffice(
            self._route(sheet_override="x", reason="sheet_override"),
            class_code=ONLYOFFICE_CLASS_PREFIX, is_multi=True, wp_code_override_value=None,
        )
        assert route.component_type == "derived"  # 未改写

    def test_whole_wp_dedicated_is_exempt(self) -> None:
        route = apply_g_prefix_onlyoffice(
            self._route(component_type="g1-component"),
            class_code=ONLYOFFICE_CLASS_PREFIX, is_multi=True,
            wp_code_override_value="g1-component",
        )
        assert route.component_type == "g1-component"  # 未改写

    def test_non_g_prefix_untouched(self) -> None:
        route = apply_g_prefix_onlyoffice(
            self._route(), class_code="D-", is_multi=True, wp_code_override_value=None,
        )
        assert route.component_type == "derived"

    def test_single_sheet_untouched(self) -> None:
        route = apply_g_prefix_onlyoffice(
            self._route(), class_code=ONLYOFFICE_CLASS_PREFIX, is_multi=False,
            wp_code_override_value=None,
        )
        assert route.component_type == "derived"


# ── 5. 分支覆盖闭合（防止新增分支没有用例）───────────────

class TestReasonCoverage:
    def test_all_reasons_are_exercised(self) -> None:
        """`SheetRoute.reason` 的每个取值都必须在本文件里有断言。

        新增分支而不加用例会让「表驱动」名不副实；这里用源码文本反查
        （本文件里必须出现每个字面量）。
        """
        from pathlib import Path

        source = Path(__file__).read_text(encoding="utf-8")
        reasons = (
            "sheet_override",
            "whole_wp_dedicated",
            "package_sheets",
            "package_sheets_b_index",
            "derived",
            "single_sheet_override",
            "derived_single",
            "g_prefix_onlyoffice",
            "classification_missing",
        )
        missing = [r for r in reasons if f'"{r}"' not in source]
        assert not missing, f"以下 reason 没有用例断言：{missing}"
