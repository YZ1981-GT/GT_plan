"""I 类六循环科目解析纯函数测试。

覆盖 `i_cycle_accounts` 与 `i1_asset_categories` 中的纯函数：
resolve_row_code / row_name_matches / claim_segments / detect_chart_conflict /
build_name_lookup / static_chart_names / classify_i1_leaf / category_defs_payload。

另含 Property 2 反向自检：六个 render 策略源码不得用硬编码科目前缀作取数逻辑。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.services.four_table.i_cycle_accounts import (
    I_CYCLE_EXPECTED_NAMES,
    I_CYCLE_ROW_CODES,
    I_CYCLE_SEGMENTS,
    build_name_lookup,
    claim_segments,
    detect_chart_conflict,
    resolve_row_code,
    row_name_matches,
    static_chart_names,
)
from app.services.four_table.i1_asset_categories import (
    CATEGORY_OTHER,
    I1_ASSET_CATEGORIES,
    category_defs_payload,
    classify_i1_leaf,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. resolve_row_code — 按准则取报表行编码
# ─────────────────────────────────────────────────────────────────────────────


class TestResolveRowCode:
    """6 循环 × 2 变体 = 12 用例。

    .. warning::
       🔴 **本类的期望值曾整体是错的**（2026-08-09 修）。改写前它逐条断言
       ``I1.listed='BS-033'``（开发支出）/ ``I1.soe='BS-045'``（应付账款）等 11 个错码，
       即**守卫在保护错的那一侧** —— 这是 `I_CYCLE_ROW_CODES` 错值长期存活的直接原因：
       任何人把真源改对，这里就会打红，看起来像"改坏了"。

       现期望值全部经 `report_config` 连库对账（见
       ``test_i_cycle_row_code_evidence.py`` 的类 A 断言，它独立查 DB 自行核算行名）。
       两个守卫**互相锁死**：这里改回错码 → 那边 Property 42 打红；真源改回错码 →
       那边 Property 1/2 打红。

       spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ AC 1.8
    """

    @pytest.mark.parametrize(
        "wp_code,standards,expected",
        [
            # listed 变体（I 类实证四准则同码同名同公式 → 与 soe 相同）
            ("I1", ["listed_standalone"], "BS-032"),
            ("I2", ["listed_standalone"], "BS-033"),
            ("I3", ["listed_standalone"], "BS-034"),
            ("I4", ["listed_standalone"], "BS-035"),
            ("I5", ["listed_standalone"], "BS-037"),
            ("I6", ["listed_standalone"], "IS-006"),
            # soe 变体
            ("I1", ["soe_standalone"], "BS-032"),
            ("I2", ["soe_standalone"], "BS-033"),
            ("I3", ["soe_standalone"], "BS-034"),
            ("I4", ["soe_standalone"], "BS-035"),
            ("I5", ["soe_standalone"], "BS-037"),
            ("I6", ["soe_standalone"], "IS-006"),
        ],
        ids=[
            "I1-listed", "I2-listed", "I3-listed", "I4-listed", "I5-listed", "I6-listed",
            "I1-soe", "I2-soe", "I3-soe", "I4-soe", "I5-soe", "I6-soe",
        ],
    )
    def test_resolve_row_code_variants(self, wp_code, standards, expected):
        assert resolve_row_code(wp_code, standards) == expected

    def test_empty_standards_returns_listed(self):
        """无准则时回退 listed。"""
        assert resolve_row_code("I1", []) == "BS-032"

    def test_listed_equals_soe_for_all_cycles(self):
        """I 类两准则同码（防被按 J1「按变体不同」范式误改成两码）。

        实证：`BS-032/033/034/035/037` 与 `IS-006` 在四个 ``applicable_standard``
        下 row_name 与 formula 均相同，故按准则分流对 I 类是**恒等映射**。
        """
        for wp in ("I1", "I2", "I3", "I4", "I5", "I6"):
            listed = resolve_row_code(wp, ["listed_standalone"])
            soe = resolve_row_code(wp, ["soe_standalone"])
            assert listed == soe, f"{wp} 两准则取值不同：listed={listed} soe={soe}"

    def test_unknown_wp_code_returns_empty(self):
        """未知 wp_code 返空串。"""
        assert resolve_row_code("I99", ["soe_standalone"]) == ""


# ─────────────────────────────────────────────────────────────────────────────
# 2. row_name_matches — 行名校验闸
# ─────────────────────────────────────────────────────────────────────────────


class TestRowNameMatches:
    """命中/不命中/空名各 2 用例。"""

    @pytest.mark.parametrize(
        "row_name,wp_code,expected",
        [
            # 命中
            ("无形资产", "I1", True),
            ("开发支出", "I2", True),
            # 不命中
            ("合同负债", "I5", False),
            ("管理费用", "I6", False),
            # 空名
            ("", "I1", False),
            ("  ", "I3", False),
        ],
        ids=[
            "hit-I1-intangible",
            "hit-I2-development",
            "miss-I5-contract-liability",
            "miss-I6-admin-expense",
            "empty-I1",
            "blank-I3",
        ],
    )
    def test_row_name_matches(self, row_name, wp_code, expected):
        expected_names = I_CYCLE_EXPECTED_NAMES.get(wp_code, ())
        assert row_name_matches(row_name, expected_names) is expected


# ─────────────────────────────────────────────────────────────────────────────
# 3. claim_segments — 把标准码分配到段
# ─────────────────────────────────────────────────────────────────────────────


class TestClaimSegments:
    """I1 三段全中、I2 的 1703 被 unclaimed。"""

    def test_i1_all_three_segments_claimed(self):
        """I1: 1701/1702/1703 分别被 cost/amortization/impairment 认领。"""
        name_lookup = {
            "1701": "无形资产",
            "1702": "累计摊销",
            "1703": "无形资产减值准备",
        }
        specs = I_CYCLE_SEGMENTS["I1"]
        claimed, unclaimed = claim_segments(["1701", "1702", "1703"], name_lookup, specs)

        assert "1701" in claimed["cost"]
        assert "1702" in claimed["amortization"]
        assert "1703" in claimed["impairment"]
        assert unclaimed == []

    def test_i2_1703_unclaimed(self):
        """I2: 1703 是无形资产减值准备，不命中开发支出语义 → unclaimed。"""
        name_lookup = {
            "1703": "无形资产减值准备",
            "1704": "开发支出",
        }
        specs = I_CYCLE_SEGMENTS["I2"]
        claimed, unclaimed = claim_segments(["1703", "1704"], name_lookup, specs)

        assert "1704" in claimed["cost"]
        assert "1703" in unclaimed

    def test_unknown_code_no_name_goes_unclaimed(self):
        """无名称的码进 unclaimed。"""
        name_lookup = {"1701": "无形资产"}
        specs = I_CYCLE_SEGMENTS["I1"]
        claimed, unclaimed = claim_segments(["1701", "9999"], name_lookup, specs)

        assert "1701" in claimed["cost"]
        assert "9999" in unclaimed


# ─────────────────────────────────────────────────────────────────────────────
# 4. detect_chart_conflict — 冲突诊断
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectChartConflict:
    """I2 的 1703 与预期「开发支出」冲突；无 name 的码不判冲突。"""

    def test_i2_1703_conflict_with_development(self):
        """1703=无形资产减值准备 与 I2 预期「开发支出/研发支出」冲突。

        .. note::
           ``row_code`` 在 :func:`detect_chart_conflict` 里只作**溯源标签**写进诊断输出，
           不参与冲突判定。此处传 I2 的正确码 ``BS-033``（2026-08-09 修；改前传的
           ``BS-035`` 是 I4「长期待摊费用」的码 = 与被修的真源错值同源的残留）。
        """
        name_lookup = {"1703": "无形资产减值准备"}
        expected = I_CYCLE_EXPECTED_NAMES["I2"]
        conflicts = detect_chart_conflict(
            ["1703"], name_lookup, expected, row_code="BS-033"
        )
        assert len(conflicts) == 1
        assert conflicts[0]["kind"] == "chart_conflict"
        assert conflicts[0]["code"] == "1703"
        assert conflicts[0]["chart_name"] == "无形资产减值准备"

    def test_no_conflict_when_name_missing(self):
        """无名称的码不判冲突（宁漏勿误）。"""
        name_lookup = {}  # 1703 查不到名称
        expected = I_CYCLE_EXPECTED_NAMES["I2"]
        conflicts = detect_chart_conflict(
            ["1703"], name_lookup, expected, row_code="BS-033"
        )
        assert conflicts == []

    def test_no_conflict_when_name_matches_expected(self):
        """名称命中期望关键字则非冲突。"""
        name_lookup = {"1704": "开发支出"}
        expected = I_CYCLE_EXPECTED_NAMES["I2"]
        conflicts = detect_chart_conflict(
            ["1704"], name_lookup, expected, row_code="BS-033"
        )
        assert conflicts == []


# ─────────────────────────────────────────────────────────────────────────────
# 5. build_name_lookup — 项目级覆盖静态表
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildNameLookup:
    """项目级覆盖静态表。"""

    def test_project_overrides_static(self):
        """项目级 chart_rows 覆盖静态表同一码。"""
        chart_rows = [{"account_code": "1701", "account_name": "客户自定义无形资产"}]
        lookup = build_name_lookup(chart_rows)
        # 项目级优先
        assert lookup["1701"] == "客户自定义无形资产"

    def test_static_as_fallback(self):
        """空 chart_rows 时回退静态表。"""
        lookup = build_name_lookup([])
        # 静态表应有 1701
        static = static_chart_names()
        if "1701" in static:
            assert lookup["1701"] == static["1701"]

    def test_empty_chart_rows_none(self):
        """None chart_rows 不崩。"""
        lookup = build_name_lookup(None)
        assert isinstance(lookup, dict)


# ─────────────────────────────────────────────────────────────────────────────
# 6. static_chart_names — 加载静态科目表 ≥ 170 条
# ─────────────────────────────────────────────────────────────────────────────


class TestStaticChartNames:
    """加载静态科目表。"""

    def test_static_chart_names_count(self):
        """静态科目表至少 170 条。"""
        names = static_chart_names()
        assert len(names) >= 170

    def test_key_codes_present(self):
        """关键码应存在（只检查一级科目表中确定存在的码）。"""
        names = static_chart_names()
        # 1701/1702/1703 是一级标准科目，1704/6604 可能不在精简版静态表中
        for code in ("1701", "1702", "1703"):
            assert code in names, f"静态科目表缺少 {code}"

    def test_values_are_nonempty_strings(self):
        """所有值非空。"""
        names = static_chart_names()
        for code, name in names.items():
            assert isinstance(name, str) and name.strip(), f"{code} 名称为空"


# ─────────────────────────────────────────────────────────────────────────────
# 7. classify_i1_leaf — 参数化 9 个实证样本 + 反向自检
# ─────────────────────────────────────────────────────────────────────────────


class TestClassifyI1Leaf:
    """参数化 9 个实证样本 + 反向自检。"""

    @pytest.mark.parametrize(
        "name,expected_key",
        [
            ("无形资产_土地使用权", "land_use_right"),
            ("无形资产_软件", "software"),
            ("无形资产_专利权", "patent"),
            ("无形资产_非专利技术", "patent_free_tech"),
            ("无形资产_商标权", "trademark"),
            ("无形资产_特许经营权", "franchise"),
            ("累计摊销_土地使用权", "land_use_right"),
            ("无形资产减值准备_非专利技术", "patent_free_tech"),
            ("无形资产", None),  # 仅父级、无子科目
        ],
        ids=[
            "land", "software", "patent", "patent_free_tech",
            "trademark", "franchise",
            "amort-land", "impairment-patent_free_tech",
            "parent-only-none",
        ],
    )
    def test_classify_i1_leaf_samples(self, name, expected_key):
        assert classify_i1_leaf(name) == expected_key

    def test_reverse_self_check_order_matters(self):
        """反向自检：打乱 I1_ASSET_CATEGORIES 顺序时至少一条失败。

        验证归类顺序铁律——「非专利技术」必须先于「专利权」。
        如果用乱序执行，则 '无形资产_非专利技术' 可能被「专利权」吃掉。
        """
        # 模拟打乱顺序：把 patent 放到 patent_free_tech 前面
        from app.services.four_table.i1_asset_categories import _ORDERED

        # 找到 patent 和 patent_free_tech 在 _ORDERED 中的位置
        patent_idx = None
        patent_free_idx = None
        for i, c in enumerate(_ORDERED):
            if c.key == "patent":
                patent_idx = i
            elif c.key == "patent_free_tech":
                patent_free_idx = i

        # 验证当前正序：patent_free_tech 在 patent 之前
        assert patent_free_idx is not None
        assert patent_idx is not None
        assert patent_free_idx < patent_idx, (
            "归类顺序铁律被打破：patent_free_tech 必须先于 patent"
        )

        # 用乱序模拟归类：如果 patent 先判，'非专利技术' 会命中 '专利' 关键字
        test_name = "无形资产_非专利技术"
        # patent 的 name_keywords 含 '专利权'/'专利'
        patent_cat = _ORDERED[patent_idx]
        # 验证「非专利技术」确实含「专利」子串 → 打乱后会被误判
        assert any(k in test_name for k in patent_cat.name_keywords)


# ─────────────────────────────────────────────────────────────────────────────
# 8. category_defs_payload — 返回 11 项且 other 在最后
# ─────────────────────────────────────────────────────────────────────────────


class TestCategoryDefsPayload:
    """返回 11 项且 other 在最后。"""

    def test_payload_has_11_items(self):
        payload = category_defs_payload()
        assert len(payload) == 11

    def test_other_is_last(self):
        payload = category_defs_payload()
        assert payload[-1]["key"] == CATEGORY_OTHER

    def test_each_item_has_required_keys(self):
        payload = category_defs_payload()
        for item in payload:
            assert "key" in item
            assert "label" in item
            assert "seq" in item

    def test_keys_unique(self):
        payload = category_defs_payload()
        keys = [item["key"] for item in payload]
        assert len(keys) == len(set(keys))


# ─────────────────────────────────────────────────────────────────────────────
# 9. Property 2 反向自检 — 六个 render 策略源码禁用硬编码前缀取数
# ─────────────────────────────────────────────────────────────────────────────


class TestProperty2ReverseCheck:
    """六个 render 策略源码不得出现 startswith("1717") / startswith("1911") /
    account_code.startswith("6602") 作为取数逻辑。

    docstring / 注释里的引用不算。
    """

    #: 六个 render 策略文件
    _RENDER_DIR = Path(__file__).resolve().parents[2] / "app" / "routers" / "wp_render_strategies"
    _RENDER_FILES = (
        "_i1_intangible_assets.py",
        "_i2_development_expenditure.py",
        "_i3_goodwill.py",
        "_i4_long_term_prepaid.py",
        "_i5_other_noncurrent_assets.py",
        "_i6_research_development_expense.py",
    )

    #: 禁止出现的模式（取数逻辑中的硬编码前缀）
    _FORBIDDEN_PATTERNS = (
        r'startswith\(\s*["\']1717',
        r'startswith\(\s*["\']1911',
        r'account_code\.startswith\(\s*["\']6602',
    )

    def _strip_comments_and_docstrings(self, source: str) -> str:
        """移除 Python 源码中的注释和 docstring，只保留执行代码。"""
        lines = []
        for line in source.splitlines():
            # 去掉行内 # 注释（简化处理：从第一个 # 截断，不考虑字符串内的 #）
            code_part = line.split("#")[0] if "#" in line else line
            lines.append(code_part)
        code = "\n".join(lines)

        # 移除三引号 docstring（简化：非贪婪匹配）
        code = re.sub(r'"""[\s\S]*?"""', '', code)
        code = re.sub(r"'''[\s\S]*?'''", '', code)
        return code

    @pytest.mark.parametrize("filename", _RENDER_FILES)
    def test_no_hardcoded_prefix_in_logic(self, filename):
        """render 策略源码中不得有硬编码科目前缀作为取数逻辑。"""
        filepath = self._RENDER_DIR / filename
        if not filepath.exists():
            pytest.skip(f"{filename} 不存在")

        source = filepath.read_text(encoding="utf-8")
        code_only = self._strip_comments_and_docstrings(source)

        violations = []
        for pattern in self._FORBIDDEN_PATTERNS:
            matches = re.findall(pattern, code_only)
            if matches:
                violations.append(f"{filename}: 发现禁止模式 {pattern} ({len(matches)} 处)")

        assert not violations, "\n".join(violations)

    def test_self_check_render_files_exist(self):
        """反向自检：至少 5 个 render 文件存在（防止路径变更导致测试空转）。"""
        existing = [f for f in self._RENDER_FILES if (self._RENDER_DIR / f).exists()]
        assert len(existing) >= 5, (
            f"只找到 {len(existing)} 个 render 文件，预期至少 5 个"
        )
