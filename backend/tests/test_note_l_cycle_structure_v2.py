"""L 循环附注结构 v2 —— 用例层。

判据（常量 / 登记表 / 纯函数 / loader / fixture）见
`backend/tests/l_cycle_extraction/_l_note_v2_criteria.py`。
拆分原因：原单文件 954 行 > pre-commit 800 行门禁，且白名单仅限历史大文件。
"""

from __future__ import annotations

import pytest

from tests.l_cycle_extraction._l_note_v2_criteria import (
    MIN_SECTION_COUNT,
    MIN_TARGET_COUNT,
    SOURCE_DIR,
    SourceTableFacts,
    TARGET_SPECS,
    TEMPLATE_JSON,
    _CLASS_A,
    _fail_class_b,
    _resolve_section,
    _resolve_table,
    _target_key,
    evaluate_column_key_shape,
    evaluate_flat_placement,
    evaluate_header_matches_source,
    evaluate_label_column_count,
    evaluate_text_sections_present,
    evaluate_two_level_group,
    load_source_sheet_cells,
    section_index,
    templates,
)

__all__ = [
    "MIN_SECTION_COUNT",
    "MIN_TARGET_COUNT",
    "SOURCE_DIR",
    "SourceTableFacts",
    "TARGET_SPECS",
    "TEMPLATE_JSON",
    "_CLASS_A",
    "_fail_class_b",
    "_resolve_section",
    "_resolve_table",
    "_target_key",
    "evaluate_column_key_shape",
    "evaluate_flat_placement",
    "evaluate_header_matches_source",
    "evaluate_label_column_count",
    "evaluate_text_sections_present",
    "evaluate_two_level_group",
    "load_source_sheet_cells",
    "section_index",
    "templates",
]


class TestClassAInfrastructure:
    def test_template_and_source_paths_exist(self):
        for variant, path in sorted(TEMPLATE_JSON.items()):
            assert path.exists(), f"{_CLASS_A} {variant} 附注模板不存在: {path}"
        assert SOURCE_DIR.is_dir(), f"{_CLASS_A} L 类源模板目录不存在: {SOURCE_DIR}"

    def test_templates_have_enough_sections(self, templates):
        for variant, tpl in sorted(templates.items()):
            n = len(tpl.get("sections") or [])
            assert n >= MIN_SECTION_COUNT, (
                f"{_CLASS_A} {variant} 模板只有 {n} 个 section，少于下限 "
                f"{MIN_SECTION_COUNT}，扫描面可疑（判据会空转）"
            )

    def test_target_registry_non_empty(self):
        assert len(TARGET_SPECS) >= MIN_TARGET_COUNT, (
            f"{_CLASS_A} 目标登记表只有 {len(TARGET_SPECS)} 条，"
            f"少于 spec 声明的 {MIN_TARGET_COUNT} 处"
        )
        for spec in TARGET_SPECS:
            assert len(spec.evidence.strip()) >= 30, (
                f"{_CLASS_A} {_target_key(spec)} 的 evidence 过短"
                f"（{len(spec.evidence.strip())} 字），登记不写依据就会变成逃逸阀"
            )
            assert len(spec.expect_keys) == len(spec.expect_labels) == len(
                spec.expect_groups
            ), (
                f"{_CLASS_A} {_target_key(spec)} 的 expect_keys / expect_labels / "
                "expect_groups 长度不一致"
            )
            # 🔴 evidence（散文）与 expect_text_sections（机器可读字段）必须同向。
            # 八、57 曾出现 evidence 写「无说明段故如实登记为零」而字段写 True 的
            # 自相矛盾 —— 散文没人执行，字段才决定判红判绿，于是正确的数据被打红。
            # 凡 evidence 里明说「无说明段 / 登记为零」的，字段必须是 False。
            declares_zero = any(
                kw in spec.evidence for kw in ("无说明段", "确无说明段", "登记为零")
            )
            assert not (declares_zero and spec.expect_text_sections), (
                f"{_CLASS_A} {_target_key(spec)} 的 evidence 声明源侧无说明段，"
                "而 expect_text_sections=True —— 散文与字段矛盾，字段才是被执行的那个"
            )

    def test_all_targets_resolvable_by_pair_index(self, section_index):
        """按 (章节号, 表名) 二元组索引必须唯一命中，证明索引方式有效。"""
        for spec in TARGET_SPECS:
            tbl = _resolve_table(section_index, spec)
            assert tbl.get("name") == spec.table_name

    def test_table_name_is_ambiguous_globally(self, templates):
        """反向自检：证明"按表名全局索引"确实不可靠（故必须用二元组）。"""
        counts = {}
        for sec in templates["listed"].get("sections") or []:
            for tbl in sec.get("tables") or []:
                name = str(tbl.get("name") or "")
                if name:
                    counts[name] = counts.get(name, 0) + 1
        dup = sorted(n for n, c in counts.items() if c > 1)
        assert dup, (
            f"{_CLASS_A} listed 模板里没有重名表，"
            "「必须按二元组索引」这条前提需要重新核实"
        )
        assert "其他非流动负债" in dup or len(dup) >= 10, (
            f"{_CLASS_A} 重名表只有 {len(dup)} 个，与已知事实（63 个）差距过大"
        )

    def test_source_sheets_readable_and_visible(self):
        for spec in TARGET_SPECS:
            cells = load_source_sheet_cells(spec.wp_code, spec.source_sheet)
            assert cells, (
                f"{_CLASS_A} {spec.wp_code}!{spec.source_sheet} 直读到空内容"
            )

    def test_source_header_row_landmarks(self):
        """锚点断言：证明直读到的表头行就是判据依据那一行。"""
        l7 = load_source_sheet_cells("L7", "附注披露信息(国企)")
        assert l7.get((6, 1)) == "项目", f"{_CLASS_A} L7 国企 A6 应为 项目，实际 {l7.get((6,1))!r}"
        assert l7.get((6, 2)) == "年初余额", (
            f"{_CLASS_A} L7 国企 B6 应为 年初余额（不是 期初余额），实际 {l7.get((6,2))!r}"
        )
        assert l7.get((6, 3)) == "期末余额", (
            f"{_CLASS_A} L7 国企 C6 应为 期末余额，实际 {l7.get((6,3))!r}"
        )

        l7_listed = load_source_sheet_cells("L7", "附注披露信息（上市公司）")
        assert l7_listed.get((6, 2)) == "期末数", (
            f"{_CLASS_A} L7 上市 B6 应为 期末数，实际 {l7_listed.get((6,2))!r}"
        )
        assert l7_listed.get((6, 3)) == "上年年末数", (
            f"{_CLASS_A} L7 上市 C6 应为 上年年末数，实际 {l7_listed.get((6,3))!r}"
        )

        l3 = load_source_sheet_cells("L3", "附注披露（国企）信息核对")
        assert l3.get((21, 1)) == "借款类别", (
            f"{_CLASS_A} L3 国企 A21 应为 借款类别（不是 项目），实际 {l3.get((21,1))!r}"
        )

        l4 = load_source_sheet_cells("L4", "附注披露信息核对（上市公司）")
        assert l4.get((63, 1)) == "发行在外的金融工具"
        assert l4.get((63, 2)) == "期初余额", f"{_CLASS_A} L4 上市 B63 应为父表头 期初余额"
        assert l4.get((64, 2)) == "数量", f"{_CLASS_A} L4 上市 B64 应为叶子列 数量"
        assert l4.get((64, 3)) == "账面价值", (
            f"{_CLASS_A} L4 上市 C64 应为叶子列 账面价值 —— 这正是模板丢掉的那 4 列之一"
        )

    def test_two_version_l7_headers_differ(self):
        """L7 两版列名本就不同构，禁为统一而对齐。"""
        soe = load_source_sheet_cells("L7", "附注披露信息(国企)")
        listed = load_source_sheet_cells("L7", "附注披露信息（上市公司）")
        soe_hdr = tuple(soe.get((6, c)) for c in (1, 2, 3))
        listed_hdr = tuple(listed.get((6, c)) for c in (1, 2, 3))
        assert soe_hdr != listed_hdr, (
            f"{_CLASS_A} L7 两版表头相同（{soe_hdr}），"
            "而源模板事实是两版不同构，判据需重新核实"
        )

    def test_l4_listed_two_level_header_is_nine_columns(self):
        """源模板事实：4 组 x (数量/账面价值) + 标签列 = 9 列。"""
        l4 = load_source_sheet_cells("L4", "附注披露信息核对（上市公司）")
        leaf = [l4.get((64, c)) for c in range(2, 10)]
        assert leaf == ["数量", "账面价值"] * 4, (
            f"{_CLASS_A} L4 上市第 64 行叶子列应是 数量/账面价值 各 4 组，实际 {leaf}"
        )
        parents = [l4.get((63, c)) for c in (2, 4, 6, 8)]
        assert parents == ["期初余额", "本期增加", "本期减少", "期末余额"], (
            f"{_CLASS_A} L4 上市第 63 行父表头不符预期，实际 {parents}"
        )

    def test_l7_soe_source_has_no_text_paragraph(self):
        """钉死 expect_text_sections=False 的源侧依据。

        八、57 的 expect_text_sections 曾误写 True，把正确的数据打成红 ——
        「守卫把错值当基线锁死」。仅把字段改回 False 是不够的：那只是让红变绿，
        没有任何东西证明「源侧确实没有说明段」。所以在这里对源 xlsx 直接取证，
        将来源模板真的补了说明段时，本断言会先红，提示同步改期望值。

        判据形态：说明段的特征是「独立于表格的长文本格」。该 sheet 的非空格
        只有表头、指向 明细表L7-2 的取数公式、合计行，无长文本。
        """
        cells = load_source_sheet_cells("L7", "附注披露信息(国企)")
        max_row = max(r for r, _ in cells)
        assert max_row <= 14, (
            f"{_CLASS_A} L7 国企源 sheet 行数由 {max_row} 增长，"
            "可能新增了说明段，须复核 expect_text_sections"
        )
        # 表头行与合计行之外，不应存在长文本（说明段）格
        long_text = {
            (r, c): v
            for (r, c), v in cells.items()
            if r > 6 and isinstance(v, str) and not v.startswith("=") and len(v.strip()) >= 12
        }
        assert not long_text, (
            f"{_CLASS_A} L7 国企源 sheet 表格区之后出现长文本格 {long_text}，"
            "疑为说明段，须把 expect_text_sections 改回 True 并补模板"
        )


class TestClassASurrogateReverseCheck:
    """替身 fixture 反向自检：不改真实模板文件。"""

    @staticmethod
    def _cjk_key_table() -> dict:
        return {
            "name": "替身表",
            "headers": ["项目", "期末余额"],
            "columns": [
                {"key": "项目", "label": "项目", "is_label": True, "flat": True},
                {"key": "期末余额", "label": "期末余额", "flat": True},
            ],
        }

    @staticmethod
    def _clean_table() -> dict:
        return {
            "name": "替身表",
            "headers": ["项目", "期末余额"],
            "columns": [
                {"key": "label", "label": "项目", "is_label": True, "flat": True},
                {"key": "end_amount", "label": "期末余额", "format": "amount"},
            ],
        }

    def test_cjk_key_is_flagged(self):
        problems = evaluate_column_key_shape(self._cjk_key_table())
        assert len(problems) == 2, f"{_CLASS_A} 中文 key 未被全部打红: {problems}"
        assert "含中文字符" in problems[0]

    def test_clean_key_passes(self):
        assert evaluate_column_key_shape(self._clean_table()) == ()

    def test_flat_on_every_column_is_flagged(self):
        problems = evaluate_flat_placement(self._cjk_key_table())
        assert problems, f"{_CLASS_A} flat 标在每一列未被打红"
        assert "非标签列" in problems[0]

    def test_flat_only_on_label_column_passes(self):
        assert evaluate_flat_placement(self._clean_table()) == ()

    def test_two_level_group_missing_is_flagged(self):
        """5 列想当 9 列两级表头用：必须先报列数不符（丢列不是丢分组）。"""
        five_col = {
            "name": "替身两级表",
            "headers": ["工具", "期初", "本期增加", "本期减少", "期末"],
            "columns": [
                {"key": "label", "label": "工具", "is_label": True, "flat": True},
                {"key": "begin_count", "label": "期初"},
                {"key": "increase_count", "label": "本期增加"},
                {"key": "decrease_count", "label": "本期减少"},
                {"key": "end_count", "label": "期末"},
            ],
        }
        expect = (None, "期初余额", "期初余额", "本期增加", "本期增加", "本期减少",
                  "本期减少", "期末余额", "期末余额")
        problems = evaluate_two_level_group(five_col, expect)
        assert problems, f"{_CLASS_A} 列数不符未被打红"
        assert "列数" in problems[0], f"{_CLASS_A} 报错应先指出列数不符: {problems}"

    def test_two_level_flat_on_label_defeats_group(self):
        """标签列带 flat 会让整表 group 失效，必须打红（否则加了 group 也不生效）。"""
        nine_col = {
            "name": "替身两级表",
            "headers": ["工具"] + ["数量", "账面价值"] * 4,
            "columns": [
                {"key": "label", "label": "工具", "is_label": True, "flat": True},
                {"key": "begin_count", "label": "数量", "group": "期初余额"},
                {"key": "begin_value", "label": "账面价值", "group": "期初余额"},
                {"key": "increase_count", "label": "数量", "group": "本期增加"},
                {"key": "increase_value", "label": "账面价值", "group": "本期增加"},
                {"key": "decrease_count", "label": "数量", "group": "本期减少"},
                {"key": "decrease_value", "label": "账面价值", "group": "本期减少"},
                {"key": "end_count", "label": "数量", "group": "期末余额"},
                {"key": "end_value", "label": "账面价值", "group": "期末余额"},
            ],
        }
        expect = (None, "期初余额", "期初余额", "本期增加", "本期增加", "本期减少",
                  "本期减少", "期末余额", "期末余额")
        problems = evaluate_two_level_group(nine_col, expect)
        assert problems, f"{_CLASS_A} 标签列带 flat 未被打红"
        assert "flat" in problems[0]

        del nine_col["columns"][0]["flat"]
        assert evaluate_two_level_group(nine_col, expect) == (), (
            f"{_CLASS_A} 去掉标签列 flat 后应放行（证明该判据不是空转）"
        )

    def test_label_column_count(self):
        two_labels = {
            "name": "替身表",
            "columns": [
                {"key": "label", "is_label": True},
                {"key": "sub_label", "is_label": True},
            ],
        }
        assert evaluate_label_column_count(two_labels), (
            f"{_CLASS_A} 两个 is_label 列未被打红"
        )
        assert evaluate_label_column_count(self._clean_table()) == ()

        no_label = {"name": "替身表", "columns": [{"key": "a"}, {"key": "b"}]}
        assert evaluate_label_column_count(no_label), f"{_CLASS_A} 零个 is_label 列未被打红"

    def test_text_sections_criterion_is_bidirectional(self):
        assert evaluate_text_sections_present({"text_sections": []}, True), (
            f"{_CLASS_A} 应有说明段而为空未被打红"
        )
        assert evaluate_text_sections_present({"text_sections": ["x"]}, True) == ()
        assert evaluate_text_sections_present({"text_sections": ["x"]}, False), (
            f"{_CLASS_A} 登记为零而实际有段落未被打红（防自造披露内容）"
        )
        assert evaluate_text_sections_present({"text_sections": []}, False) == ()

    def test_header_mismatch_is_flagged(self):
        src = SourceTableFacts("附注披露信息(国企)", 6, ("项目", "年初余额", "期末余额"),
                               "L7!附注披露信息(国企)!A6")
        wrong = {
            "name": "其他非流动负债",
            "headers": ["项目", "期末余额", "期初余额"],
            "columns": [
                {"key": "label", "label": "项目", "is_label": True, "flat": True},
                {"key": "end_amount", "label": "期末余额"},
                {"key": "prior_amount", "label": "期初余额"},
            ],
        }
        problems = evaluate_header_matches_source(
            wrong, src, ("项目", "年初余额", "期末余额")
        )
        assert len(problems) == 2, (
            f"{_CLASS_A} headers 与 columns[].label 两侧都应被打红: {problems}"
        )

        right = {
            "name": "其他非流动负债",
            "headers": ["项目", "年初余额", "期末余额"],
            "columns": [
                {"key": "label", "label": "项目", "is_label": True, "flat": True},
                {"key": "begin_amount", "label": "年初余额"},
                {"key": "end_amount", "label": "期末余额"},
            ],
        }
        assert evaluate_header_matches_source(
            right, src, ("项目", "年初余额", "期末余额")
        ) == ()


# ===========================================================================
# 类 B：被测实现（现在应全红）
# ===========================================================================


class TestClassBNoteStructure:
    def test_column_keys_are_not_cjk_literals(self, section_index):
        """Property 15：列 key 不得是中文字面量。"""
        offenders = {}
        for spec in TARGET_SPECS:
            tbl = _resolve_table(section_index, spec)
            problems = evaluate_column_key_shape(tbl)
            if problems:
                offenders[_target_key(spec)] = problems
        if offenders:
            _fail_class_b("附注列 key 是中文字面量（应为 snake_case）", offenders)

    def test_flat_is_only_on_label_column(self, section_index):
        """Property 16：flat 只标标签列。"""
        offenders = {}
        for spec in TARGET_SPECS:
            tbl = _resolve_table(section_index, spec)
            problems = evaluate_flat_placement(tbl)
            if problems:
                offenders[_target_key(spec)] = problems
        if offenders:
            _fail_class_b("flat 被标在非标签列上（平台惯例只标 columns[0]）", offenders)

    def test_headers_match_source_template(self, section_index):
        """Property 17：模板 headers / columns[].label 必须与源 xlsx 表头一致。"""
        offenders = {}
        for spec in TARGET_SPECS:
            tbl = _resolve_table(section_index, spec)
            src = SourceTableFacts(
                spec.source_sheet,
                spec.source_header_row,
                spec.expect_labels,
                f"{spec.wp_code}!{spec.source_sheet}!row{spec.source_header_row}",
            )
            problems = evaluate_header_matches_source(tbl, src, spec.expect_labels)
            if problems:
                offenders[_target_key(spec)] = problems
        if offenders:
            _fail_class_b("模板列名/列序与源 xlsx 表头不一致", offenders)

    def test_two_level_header_is_expressed_by_group(self, section_index):
        """Property 18：两级表头必须补齐列后靠 group 表达。"""
        offenders = {}
        for spec in TARGET_SPECS:
            if not any(spec.expect_groups):
                continue
            tbl = _resolve_table(section_index, spec)
            problems = evaluate_two_level_group(tbl, spec.expect_groups)
            if problems:
                offenders[_target_key(spec)] = problems
        if offenders:
            _fail_class_b(
                "两级表头未成立（丢列或 group 缺失；注意丢的是列不是分组）", offenders
            )

    def test_label_column_flag_is_singular(self, section_index):
        """is_label 列数恰为 1（防 group 索引整体偏移一位）。"""
        offenders = {}
        for spec in TARGET_SPECS:
            tbl = _resolve_table(section_index, spec)
            problems = evaluate_label_column_count(tbl)
            if problems:
                offenders[_target_key(spec)] = problems
        if offenders:
            _fail_class_b("is_label 列数不为 1", offenders)

    def test_text_sections_are_present_where_expected(self, section_index):
        """Property 19：应有说明段的章节 text_sections 非空。"""
        offenders = {}
        for spec in TARGET_SPECS:
            sec = _resolve_section(section_index, spec)
            problems = evaluate_text_sections_present(sec, spec.expect_text_sections)
            if problems:
                offenders[_target_key(spec)] = problems
        if offenders:
            _fail_class_b("text_sections 与登记的期望不符", offenders)
