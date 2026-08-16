"""L 循环公式预设科目一致性守卫（Wave 1 Task 1，"先打红"）。

spec: .kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/
      Requirements 3.1~3.8 / Design Property 1~6

判据分两类，失败消息里必须写明是哪一类：

类 A = 独立口径判据
    源 xlsx 的 visible tab 名集合、L_CYCLE_SPECS 的兜底码与科目中文名、
    区间抽取器自身的 fixture 自检、跨循环白名单条目的理由与新鲜度、
    替身块反向自检、扫描面非空。
    这些判据不依赖被测数据是否已修好，**现在就应该全绿**。
    一旦转红说明本文件的判据基础设施有问题（而不是被测实现有问题），必须先修判据。

类 B = 被测实现
    backend/data/prefill_formula_mapping.json 里 L 类块的 cells 公式实参、
    description 科目中文名、sheet 存在性、区间健全性、PREV 第二实参。
    **现在应该全红**，每条 fail 消息都写明这是预期的 Wave 1 打红结果。

三条实现约束（踩坑铁律，改本文件前必读）：

1. 禁在模块顶层 import 生产模块。顶层 import 失败会让整文件 collection error、
   零断言执行，那时"全红"既可能是功能没做也可能是守卫写坏。改为测试内 try-import
   后 pytest.fail（不是 skip）。
2. 抽科目码前必须先把 SUM_TB('a~b') / TB_SUM('a~b') 的区间**整体消费掉**再抽剩余
   单码。区间的 a/b 是边界不是被引用科目，朴素抽码会把上界误判成"引用了别的循环
   科目"。本文件配 test_range_extractor_self_check 钉死这一点。
3. 失败消息体只用 ASCII 符号 + 中文汉字，禁用 GBK 不可编码字符（那会让整条消息被
   转义成 \\uXXXX，完全无法判读）。

模块级纯函数对外导出，Wave 2 的幂等脚本直接 import 复用，避免同一判据两处各写一份。
"""

from __future__ import annotations

import re

import pytest

# 🔴 判据层已拆到 `_l_preset_criteria.py`（原单文件超 800 行门禁）。
#    下面这份 import 清单由拆分脚本**按 tail 实际引用**算出，非手写 ——
#    手写清单漏一个名字就是 collection error，而本文件 collection error
#    意味着 39 条断言零执行（比断言变红更糟，见本文件顶部约束 1）。
from ._l_preset_criteria import (  # noqa: F401
    CLEAN_BLOCK_BASELINE,
    CROSS_CYCLE_ALLOWLIST,
    MIN_L_BLOCK_COUNT,
    MIN_REASON_CHARS,
    PREFILL_PATH,
    TEMPLATE_DIR,
    WP_CODES_WITHOUT_SPEC,
    _CLASS_A,
    _CLASS_B,
    _WAVE1_RED,
    _block_key,
    _fmt_key,
    build_code_owner_index,
    build_label_index,
    codes_within_range,
    detect_description_label_conflicts,
    evaluate_block_code_coherence,
    evaluate_block_description_coherence,
    evaluate_block_prev_targets,
    evaluate_block_range_health,
    evaluate_block_sheet_existence,
    evaluate_range_health,
    extract_formula_codes,
    extract_prev_targets,
    is_code_allowed,
    load_l_cycle_specs,
    load_l_prefill_blocks,
    load_visible_sheet_names,
    parent_code,
)

@pytest.fixture(scope="module")
def l_specs() -> dict:
    return load_l_cycle_specs()


@pytest.fixture(scope="module")
def l_blocks() -> list:
    return load_l_prefill_blocks()


@pytest.fixture(scope="module")
def visible_sheets() -> dict:
    return load_visible_sheet_names()


# ---------------------------------------------------------------------------
# 报错组装
# ---------------------------------------------------------------------------


def _fail_class_b(title: str, offenders: dict) -> None:
    lines = [f"{_CLASS_B} {title}", f"{_WAVE1_RED}。", f"命中块数: {len(offenders)}"]
    for key in sorted(offenders):
        lines.append(f"  - {_fmt_key(key)}")
        for msg in offenders[key]:
            lines.append(f"      {msg}")
    pytest.fail("\n".join(lines))


def _fail_regression(title: str, offenders: dict, regressions: list) -> None:
    lines = [
        f"{_CLASS_B} 零回归基线被打破：{title}",
        "以下块在改造前是正确的（CLEAN_BLOCK_BASELINE），现在被判红，"
        "这不是预期的 Wave 1 打红结果，而是回归，必须先查改动。",
    ]
    for key in regressions:
        lines.append(f"  - {_fmt_key(key)}")
        for msg in offenders[key]:
            lines.append(f"      {msg}")
    pytest.fail("\n".join(lines))


def _collect(blocks: list, fn) -> dict:
    out = {}
    for block in blocks:
        problems = fn(block)
        if problems:
            out[_block_key(block)] = problems
    return out


def _report(title: str, offenders: dict) -> None:
    regressions = sorted(k for k in offenders if k in CLEAN_BLOCK_BASELINE)
    if regressions:
        _fail_regression(title, offenders, regressions)
    if offenders:
        _fail_class_b(title, offenders)


# ===========================================================================
# 类 A：独立口径判据（现在就应全绿）
# ===========================================================================


class TestClassAInfrastructure:
    """判据基础设施自检。任一条转红说明守卫本身有问题，必须先修守卫。"""

    def test_data_and_template_paths_exist(self):
        assert PREFILL_PATH.exists(), (
            f"{_CLASS_A} 公式预设文件不存在: {PREFILL_PATH}。"
            "注意真实路径是 backend/data/ 不是 backend/data/ledger_adapters/"
        )
        assert TEMPLATE_DIR.is_dir(), f"{_CLASS_A} 源模板目录不存在: {TEMPLATE_DIR}"

    def test_l_cycle_specs_has_eight_keys(self, l_specs):
        expected = {f"L{i}" for i in range(1, 9)}
        assert set(l_specs) == expected, (
            f"{_CLASS_A} L_CYCLE_SPECS 键集应为 L1~L8，实际 {sorted(l_specs)}"
        )
        for wp, spec in sorted(l_specs.items()):
            assert spec.wp_code == wp, f"{_CLASS_A} {wp} 的 spec.wp_code={spec.wp_code!r} 不自洽"
            assert spec.account_label, f"{_CLASS_A} {wp} 缺 account_label"
            assert isinstance(spec.fallback_codes, tuple), (
                f"{_CLASS_A} {wp} 的 fallback_codes 应为 tuple，实际 "
                f"{type(spec.fallback_codes).__name__}"
            )

    def test_l7_fallback_codes_is_empty(self, l_specs):
        """L7 其他非流动负债宁缺勿造：兜底码为空元组，判据必须容纳"空集合"。"""
        assert l_specs["L7"].fallback_codes == (), (
            f"{_CLASS_A} L7 兜底码应为空元组（宁缺勿造），实际 "
            f"{l_specs['L7'].fallback_codes!r}。若确要给它兜底码，"
            "必须先在 spec 里裁决并同步本守卫。"
        )

    def test_account_labels_are_mutually_non_substring(self, l_specs):
        """description 冲突检测用朴素子串匹配，前提是没有一个科目名是另一个的子串。"""
        labels = sorted(build_label_index(l_specs))
        assert len(labels) == 8, f"{_CLASS_A} 应有 8 个科目中文名，实际 {labels}"
        for a in labels:
            for b in labels:
                if a != b:
                    assert a not in b, (
                        f"{_CLASS_A} 科目名 {a!r} 是 {b!r} 的子串，"
                        "朴素子串匹配不再可靠，detect_description_label_conflicts 需改判据"
                    )

    def test_code_owner_index_has_no_duplicate_owner(self, l_specs):
        seen = {}
        for wp, spec in sorted(l_specs.items()):
            for code in spec.fallback_codes or ():
                assert code not in seen, (
                    f"{_CLASS_A} 兜底码 {code} 同时属于 {seen[code]} 与 {wp}，"
                    "区间健全性判据的 code_owner 映射不再唯一"
                )
                seen[code] = wp
        assert seen, f"{_CLASS_A} code_owner 映射为空，区间判据会空转"

    def test_visible_sheet_names_loadable(self, visible_sheets):
        assert set(visible_sheets) >= {f"L{i}" for i in range(0, 9)}, (
            f"{_CLASS_A} 未能读到全部 L0~L8 的源 xlsx，实际 {sorted(visible_sheets)}"
        )
        for wp, names in sorted(visible_sheets.items()):
            assert names, f"{_CLASS_A} {wp} 的 visible sheet 集合为空"

    def test_visible_sheet_landmarks(self, visible_sheets):
        """锚点断言：证明直读结果是真的，且已知的形态（空格 / 半角括号 / 同名）都在。"""
        l1 = visible_sheets["L1"]
        assert "审定表L1-1" in l1
        assert "调整分录汇总L1-3" in l1, f"{_CLASS_A} L1 应有 调整分录汇总L1-3，实际 {l1}"
        assert "分析程序L1-3" not in l1, (
            f"{_CLASS_A} L1 不应有 分析程序L1-3（该 sheet 在源 xlsx 不存在），实际 {l1}"
        )
        assert " 短期借款实质性程序表L1A" in l1, (
            f"{_CLASS_A} L1A 的真实 tab 名首字符是空格，直读结果应保留原样，实际 {l1}"
        )
        l4 = visible_sheets["L4"]
        assert "应付债券实质性程序表L4A " in l4, f"{_CLASS_A} L4A 尾部空格丢失，实际 {l4}"
        assert (
            len([n for n in l4 if n.endswith("L4-7")]) == 2
        ), f"{_CLASS_A} L4 应有两个尾码 L4-7 的 sheet，实际 {l4}"
        assert "附注披露信息(国企)" in visible_sheets["L7"], (
            f"{_CLASS_A} L7 国企披露 sheet 是半角括号，实际 {visible_sheets['L7']}"
        )

    def test_scan_surface_non_empty(self, l_blocks):
        assert len(l_blocks) >= MIN_L_BLOCK_COUNT, (
            f"{_CLASS_A} L 类预设块只扫到 {len(l_blocks)} 个，少于下限 "
            f"{MIN_L_BLOCK_COUNT}，扫描面可疑（判据会空转）"
        )
        codes = sorted({str(b.get("wp_code")) for b in l_blocks})
        assert len(codes) >= 8, f"{_CLASS_A} L 类块只覆盖 {codes}，扫描面可疑"

    def test_clean_baseline_blocks_all_present(self, l_blocks):
        """零回归对照块必须真实存在，否则对照断言会静默空转。"""
        actual = {_block_key(b) for b in l_blocks}
        missing = sorted(CLEAN_BLOCK_BASELINE - actual)
        assert not missing, (
            f"{_CLASS_A} CLEAN_BLOCK_BASELINE 里这些块在数据里找不到: "
            f"{[_fmt_key(k) for k in missing]}；基线过期，先核实数据再改基线"
        )

    def test_cross_cycle_allowlist_entries_have_reason(self):
        assert CROSS_CYCLE_ALLOWLIST, f"{_CLASS_A} 跨循环白名单为空，Property 1 的白名单机制未生效"
        for key, allow in sorted(CROSS_CYCLE_ALLOWLIST.items()):
            assert allow.reason and len(allow.reason.strip()) >= MIN_REASON_CHARS, (
                f"{_CLASS_A} 白名单条目 {_fmt_key(key)} 的理由过短"
                f"（{len(allow.reason.strip())} 字，下限 {MIN_REASON_CHARS}），"
                "白名单不写理由就会变成逃逸阀"
            )
            assert allow.codes or allow.labels, (
                f"{_CLASS_A} 白名单条目 {_fmt_key(key)} 既不放行科目码也不放行科目名，是空条目"
            )

    def test_cross_cycle_allowlist_is_not_stale(self, l_blocks):
        actual = {_block_key(b) for b in l_blocks}
        stale = sorted(k for k in CROSS_CYCLE_ALLOWLIST if k not in actual)
        assert not stale, (
            f"{_CLASS_A} 白名单里这些块已不存在: {[_fmt_key(k) for k in stale]}；"
            "条目过期必须删除，否则会掩盖新出现的同名块"
        )

    def test_wp_codes_without_spec_registry(self, l_specs):
        for wp, reason in sorted(WP_CODES_WITHOUT_SPEC.items()):
            assert wp not in l_specs, (
                f"{_CLASS_A} {wp} 已在 L_CYCLE_SPECS 中，应从 WP_CODES_WITHOUT_SPEC 移出，"
                "否则它会被永久豁免本循环科目判定"
            )
            assert len(reason.strip()) >= MIN_REASON_CHARS, (
                f"{_CLASS_A} {wp} 的豁免理由过短（{len(reason.strip())} 字）"
            )


class TestClassAExtractorSelfCheck:
    """抽码器 / 区间校验 / 冲突检测的 fixture 自检。"""

    def test_range_extractor_consumes_range_wholly(self):
        formula = "=TB_SUM('2001~2501','期末余额')"
        got = extract_formula_codes(formula)
        assert got.ranges == (("2001", "2501"),), f"{_CLASS_A} 区间未被整体识别: {got}"
        assert got.singles == (), (
            f"{_CLASS_A} 区间上下界泄漏进了单码集合: {got.singles}；"
            "这正是【上界被误判成引用了别的循环科目】的成因"
        )
        assert "2001~2501" not in got.residual, (
            f"{_CLASS_A} 区间未从 residual 中消费掉: {got.residual!r}"
        )

    def test_naive_extraction_would_leak_range_upper_bound(self):
        """反向自检：朴素抽码会把区间上界 2501（L3 科目）当成 L1 块的引用。"""
        formula = "=TB_SUM('2001~2501','期末余额')"
        naive = re.findall(r"\d{4}", formula)
        assert "2501" in naive, f"{_CLASS_A} 朴素抽码样本构造失败: {naive}"
        proper = extract_formula_codes(formula)
        assert "2501" not in proper.singles, (
            f"{_CLASS_A} 正确抽码器不应把区间上界当单码，实际 {proper.singles}"
        )

    def test_mixed_formula_separates_range_and_single(self):
        formula = "=TB('2501','期末余额')+TB_SUM('2001~2101','期末余额')"
        got = extract_formula_codes(formula)
        assert got.singles == ("2501",), f"{_CLASS_A} 单码抽取不正确: {got.singles}"
        assert got.ranges == (("2001", "2101"),), f"{_CLASS_A} 区间抽取不正确: {got.ranges}"

    def test_sum_tb_alias_is_recognized(self):
        """预设侧写 TB_SUM、report_config 侧写 SUM_TB，两个词汇表都要认。"""
        got = extract_formula_codes("=SUM_TB('1401~1499','期末余额')")
        assert got.ranges == (("1401", "1499"),), f"{_CLASS_A} SUM_TB 未被识别: {got}"
        assert got.singles == ()

    def test_subaccount_parent_code(self):
        got = extract_formula_codes("=TB('2501.01','期初余额')")
        assert got.singles == ("2501.01",)
        assert parent_code("2501.01") == "2501"
        assert parent_code("1511.04.02") == "1511"
        assert is_code_allowed("2501.01", ("2501",)) is True
        assert is_code_allowed("2501.01", ("2502",)) is False

    def test_empty_allowed_set_rejects_everything(self):
        """L7 兜底码为空：任何科目码都不放行（宁缺勿造）。"""
        assert is_code_allowed("2801", ()) is False
        assert is_code_allowed("2801", None) is False

    def test_aux_and_ledger_detail_take_first_arg_only(self):
        got = extract_formula_codes("=AUX('2001','金融机构','TOP1','期初余额')")
        assert got.singles == ("2001",), f"{_CLASS_A} AUX 抽码应只取首实参: {got.singles}"
        got2 = extract_formula_codes("=LEDGER_DETAIL('6603','利息测算表L1-5','1月','借方发生额')")
        assert got2.singles == ("6603",), f"{_CLASS_A} LEDGER_DETAIL 抽码不正确: {got2.singles}"

    def test_prev_and_wp_first_arg_is_not_account_code(self):
        got = extract_formula_codes("=PREV('L1','审定表L1-1','审定数')")
        assert got.singles == (), (
            f"{_CLASS_A} PREV 首实参是 wp_code 不是科目码，不应被抽成科目: {got.singles}"
        )
        assert extract_prev_targets("=PREV('L1','审定表L1-1','审定数')") == (
            ("L1", "审定表L1-1"),
        )

    def test_malformed_code_is_recorded(self):
        got = extract_formula_codes("=TB('abc','期末余额')")
        assert got.malformed == ("abc",), f"{_CLASS_A} 形态异常实参未被记录: {got}"
        assert got.singles == ()

    def test_codes_within_range(self):
        assert codes_within_range("2001", "2501", ["2001", "2231", "2501", "2502"]) == (
            "2001",
            "2231",
            "2501",
        )
        assert codes_within_range("2500", "2510", ["2001", "2501", "6603"]) == ("2501",)
        # 形态异常时保守全报
        assert codes_within_range("a", "b", ["2001"]) == ("2001",)

    def test_range_health_flags_pathological_range(self, l_specs):
        owner = build_code_owner_index(l_specs)
        problems = evaluate_range_health("2001", "2501", "L1", owner)
        assert problems, f"{_CLASS_A} 病态区间 2001~2501 未被打红"
        assert "2231" in problems[0], (
            f"{_CLASS_A} 报错未指出 2231（L2 自己的科目）被扫进合计: {problems}"
        )

    def test_range_health_passes_single_cycle_range(self, l_specs):
        """区间只落在本循环科目上时必须放行。

        样本用 2500~2501 而非 2500~2510 —— 后者同时含 2501（L3 长期借款）与
        2502（L4 应付债券），判「横跨」才是正确行为；用它当"应放行"样本会
        让这条自检以假红形态失败。
        """
        owner = build_code_owner_index(l_specs)
        assert evaluate_range_health("2500", "2501", "L3", owner) == (), (
            f"{_CLASS_A} 只落在本循环科目上的区间被误判"
        )

    def test_range_health_flags_foreign_cycle_range(self, l_specs):
        owner = build_code_owner_index(l_specs)
        problems = evaluate_range_health("2500", "2501", "L1", owner)
        assert problems, f"{_CLASS_A} 只落在别的循环科目上的区间未被打红"
        assert "L3" in problems[0], f"{_CLASS_A} 报错未指出该区间实际归属 L3: {problems}"

    def test_range_health_flags_l3_l4_adjacent_span(self, l_specs):
        """2500~2510 会同时扫进 L3(2501) 与 L4(2502)，必须打红。"""
        owner = build_code_owner_index(l_specs)
        problems = evaluate_range_health("2500", "2510", "L3", owner)
        assert problems, f"{_CLASS_A} 相邻循环区间 2500~2510 未被打红"
        assert "2502" in problems[0], f"{_CLASS_A} 报错未指出 2502 被扫进合计: {problems}"

    def test_description_conflict_detection(self, l_specs):
        known = set(build_label_index(l_specs))
        assert detect_description_label_conflicts(
            "从试算表取长期借款审定表期初余额", "应付利息", known
        ) == ("长期借款",)
        assert (
            detect_description_label_conflicts(
                "从试算表取应付利息审定表期初余额", "应付利息", known
            )
            == ()
        )
        assert (
            detect_description_label_conflicts(
                "财务费用-利息支出本期借方发生额合计",
                "短期借款",
                known,
                allowed_labels={"财务费用"},
            )
            == ()
        ), f"{_CLASS_A} 白名单科目名未被放行"
        assert detect_description_label_conflicts(
            "财务费用-利息支出本期借方发生额合计", "短期借款", known
        ) == ("财务费用",), f"{_CLASS_A} 去掉白名单后应打红（证明白名单不是空转）"


class TestClassASurrogateReverseCheck:
    """替身块反向自检：内存构造 dict，不改真实数据文件。"""

    @staticmethod
    def _surrogate_l4_wrong_code() -> dict:
        """复现 审定表L4-1 写 TB('2601') 的形态。"""
        return {
            "wp_code": "L4",
            "sheet": "审定表L4-1",
            "wp_name": "应付债券审定表",
            "account_codes": ["2502"],
            "cells": [
                {
                    "cell_ref": "未审数",
                    "formula_type": "TB",
                    "formula": "=TB('2601','期末余额')",
                    "description": "从试算表取应付债券审定表期末余额（未审）",
                }
            ],
        }

    @staticmethod
    def _surrogate_l4_wrong_description() -> dict:
        """复现 description 写"租赁负债审定表"而 account_label 是"应付债券"的形态。

        注意 租赁负债 是 H9 的科目名、不在 L_CYCLE_SPECS 里，所以按 account_label
        派生的闭集合抓不到它；本替身用 长期应付款（已登记的 L5 科目名）复现同一
        形态，并另用一条断言如实登记"跨 L 循环的科目名由科目码判据兜住"。
        """
        return {
            "wp_code": "L4",
            "sheet": "审定表L4-1",
            "wp_name": "应付债券审定表",
            "account_codes": ["2502"],
            "cells": [
                {
                    "cell_ref": "未审数",
                    "formula_type": "TB",
                    "formula": "=TB('2502','期末余额')",
                    "description": "从试算表取长期应付款审定表期末余额（未审）",
                }
            ],
        }

    @staticmethod
    def _surrogate_correct() -> dict:
        return {
            "wp_code": "L4",
            "sheet": "审定表L4-1",
            "wp_name": "应付债券审定表",
            "account_codes": ["2502"],
            "cells": [
                {
                    "cell_ref": "期初余额",
                    "formula_type": "TB",
                    "formula": "=TB('2502','期初余额')",
                    "description": "从试算表取应付债券审定表期初余额",
                },
                {
                    "cell_ref": "利息调整_期末",
                    "formula_type": "TB",
                    "formula": "=TB('2502.02','期末余额')",
                    "description": "应付债券-利息调整明细科目期末余额",
                },
                {
                    "cell_ref": "上年审定数",
                    "formula_type": "PREV",
                    "formula": "=PREV('L4','审定表L4-1','审定数')",
                    "description": "上年同底稿应付债券审定数",
                },
            ],
        }

    def test_surrogate_wrong_code_is_flagged(self, l_specs):
        problems = evaluate_block_code_coherence(self._surrogate_l4_wrong_code(), l_specs)
        assert problems, f"{_CLASS_A} 替身块 TB('2601') 未被科目码判据打红"
        assert "2601" in problems[0], f"{_CLASS_A} 报错未指出错误科目码: {problems}"

    def test_surrogate_wrong_description_is_flagged(self, l_specs):
        problems = evaluate_block_description_coherence(
            self._surrogate_l4_wrong_description(), l_specs
        )
        assert problems, f"{_CLASS_A} 替身块 description 科目名错位未被打红"
        assert "长期应付款" in problems[0], f"{_CLASS_A} 报错未指出冲突科目名: {problems}"

    def test_cross_l_cycle_label_is_covered_by_code_criterion(self, l_specs):
        """如实登记：租赁负债 / 预计负债 这类非 L 科目名不在 description 判据覆盖内。"""
        block = {
            "wp_code": "L4",
            "sheet": "审定表L4-1",
            "wp_name": "应付债券审定表",
            "account_codes": ["2502"],
            "cells": [
                {
                    "cell_ref": "未审数",
                    "formula_type": "TB",
                    "formula": "=TB('2601','期末余额')",
                    "description": "从试算表取租赁负债审定表期末余额（未审）",
                }
            ],
        }
        assert evaluate_block_description_coherence(block, l_specs) == (), (
            f"{_CLASS_A} 租赁负债 不在 L_CYCLE_SPECS 派生的闭集合里，"
            "description 判据本就抓不到它（禁手写第二份科目名清单）"
        )
        assert evaluate_block_code_coherence(block, l_specs), (
            f"{_CLASS_A} 这种形态必须由科目码判据兜住，否则整块逃逸"
        )

    def test_surrogate_correct_block_passes_all_criteria(self, l_specs, visible_sheets):
        block = self._surrogate_correct()
        assert evaluate_block_code_coherence(block, l_specs) == ()
        assert evaluate_block_description_coherence(block, l_specs) == ()
        assert evaluate_block_sheet_existence(block, visible_sheets) == ()
        assert evaluate_block_prev_targets(block, visible_sheets) == ()
        assert evaluate_block_range_health(block, l_specs) == ()

    def test_surrogate_bad_sheet_is_flagged(self, visible_sheets):
        block = {"wp_code": "L1", "sheet": "分析程序L1-3", "cells": []}
        problems = evaluate_block_sheet_existence(block, visible_sheets)
        assert problems, f"{_CLASS_A} 不存在的 sheet 未被打红"

    def test_surrogate_bad_prev_is_flagged(self, visible_sheets):
        block = {
            "wp_code": "L1",
            "sheet": "审定表L1-1",
            "cells": [
                {
                    "cell_ref": "上年审定数",
                    "formula_type": "PREV",
                    "formula": "=PREV('L1','不存在的表L1-99','审定数')",
                    "description": "上年同底稿审定数",
                }
            ],
        }
        assert evaluate_block_prev_targets(block, visible_sheets), (
            f"{_CLASS_A} PREV 指向不存在的 tab 未被打红"
        )

    def test_surrogate_placeholder_description_length(self, l_specs):
        short = {
            "wp_code": "L7",
            "sheet": "审定表L7-1",
            "cells": [
                {
                    "cell_ref": "未审数",
                    "formula_type": "PLACEHOLDER",
                    "formula": "=PLACEHOLDER('其他非流动负债')",
                    "description": "手工填列",
                }
            ],
        }
        problems = evaluate_block_code_coherence(short, l_specs)
        assert problems, f"{_CLASS_A} PLACEHOLDER 说明过短未被打红"
        assert "PLACEHOLDER" in problems[0]

        long_desc = (
            "其他非流动负债在 CAS 下没有专属一级科目，2801 是预计负债、2901 是递延所得税负债，"
            "均不得采用；本格由审计师按报表重分类结果手工填列，溯源面板显示"
            "本项目无此科目，需手工填列"
        )
        ok = {
            "wp_code": "L7",
            "sheet": "审定表L7-1",
            "cells": [
                {
                    "cell_ref": "未审数",
                    "formula_type": "PLACEHOLDER",
                    "formula": "=PLACEHOLDER('其他非流动负债')",
                    "description": long_desc,
                }
            ],
        }
        assert evaluate_block_code_coherence(ok, l_specs) == (), (
            f"{_CLASS_A} 说明充分的 PLACEHOLDER 应被放行（L7 修复后会走这条路）"
        )


# ===========================================================================
# 类 B：被测实现（现在应全红）
# ===========================================================================


class TestClassBPresetImplementation:
    """被测实现判据。Wave 1 阶段这些应当全部打红。"""

    def test_cells_account_codes_belong_to_cycle(self, l_blocks, l_specs):
        """Property 1 / 2 / 6：cells 公式实参必须属于本循环科目族。"""
        offenders = _collect(
            l_blocks, lambda b: evaluate_block_code_coherence(b, l_specs)
        )
        _report("公式实参引用了别的循环的科目（或 PLACEHOLDER 说明不足）", offenders)

    def test_cell_description_account_name_is_consistent(self, l_blocks, l_specs):
        """Property 3：description 里的科目中文名必须与本块 account_label 一致。"""
        offenders = _collect(
            l_blocks, lambda b: evaluate_block_description_coherence(b, l_specs)
        )
        _report("description 里的科目中文名与本块所属循环不一致", offenders)

    def test_preset_sheet_exists_in_source_xlsx(self, l_blocks, visible_sheets):
        """Property 4：块的 sheet 必须是源 xlsx 真实 visible tab。"""
        offenders = _collect(
            l_blocks, lambda b: evaluate_block_sheet_existence(b, visible_sheets)
        )
        _report("预设块的 sheet 在源 xlsx 里不存在", offenders)

    def test_prev_second_arg_is_real_tab(self, l_blocks, visible_sheets):
        """Property 4（后半）：PREV 第二实参必须是真实 tab 名。"""
        offenders = _collect(
            l_blocks, lambda b: evaluate_block_prev_targets(b, visible_sheets)
        )
        _report("PREV 第二实参不是该 wp_code 源 xlsx 的真实 tab 名", offenders)

    def test_range_formula_does_not_span_cycles(self, l_blocks, l_specs):
        """Property 5：区间函数不得跨循环。"""
        offenders = _collect(l_blocks, lambda b: evaluate_block_range_health(b, l_specs))
        _report("区间函数横跨多个 L 循环（病态区间）", offenders)
