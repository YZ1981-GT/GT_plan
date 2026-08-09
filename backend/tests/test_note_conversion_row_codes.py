"""守卫：跨变体 row_code 双清单（Property 11~13）。

spec: soe-listed-note-conversion-correctness / Requirements 3.1~3.8, 4.4

不连库（清单是冻结常量），可进 CI。另有一个 opt-in 的连库对账测试。

核心防护：
1. 12 条同义两码逐条冻结（数据一改即打红）
2. 禁止改写清单钉死初稿三条错误映射（反向自检）
3. 两清单互斥（Requirement 3.8 —— 按已修正口径：MAP ∩ FORBIDDEN = ∅）
4. **真不变量**：MAP 的 key/value 都不得是「稳定码」（两侧同名）
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.services.note_conversion_row_codes import (
    CROSS_VARIANT_ROW_CODE_MAP,
    LISTED_TO_SOE_ROW_CODE_MAP,
    FORMULA_REWRITE_REASON,
    ONE_CODE_TWO_MEANINGS_FORBIDDEN,
    STABLE_ROW_CODES_MUST_NOT_BE_MAPPED,
    is_forbidden_rewrite,
    rewrite_row_code,
    rewrite_row_refs_in_formula,
)

_MODULE_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "app"
    / "services"
    / "note_conversion_row_codes.py"
)


# ---------------------------------------------------------------------------
# Property 11：12 条同义两码冻结
# ---------------------------------------------------------------------------


class TestSynonymTwoCodesFrozen:
    """Requirement 3.1：12 条实证映射逐条冻结。"""

    EXPECTED = {
        "BS-111": "BS-077",
        "BS-112": "BS-078",
        "CFS-038": "CFS-016",
        "IS-055": "IS-033",
        "IS-056": "IS-034",
        "IS-057": "IS-035",
        "IS-058": "IS-036",
        "IS-059": "IS-037",
        "IS-062": "IS-039",
        "IS-066": "IS-043",
        "IS-068": "IS-045",
        "IS-071": "IS-048",
    }

    def test_map_size_is_twelve(self) -> None:
        assert len(CROSS_VARIANT_ROW_CODE_MAP) == 12, (
            f"同义两码清单有 {len(CROSS_VARIANT_ROW_CODE_MAP)} 条，实证为 12 条。"
            "新增/删除必须先跑 diagnose_cross_variant_row_codes.py 复核"
        )

    def test_map_matches_evidence_exactly(self) -> None:
        actual = {k: v.listed for k, v in CROSS_VARIANT_ROW_CODE_MAP.items()}
        assert actual == self.EXPECTED, (
            "同义两码清单与 report_config 实证不符 —— 逐条差异见 diff"
        )

    @pytest.mark.parametrize("soe,listed", sorted(EXPECTED.items()))
    def test_entry_has_evidence(self, soe: str, listed: str) -> None:
        entry = CROSS_VARIANT_ROW_CODE_MAP[soe]
        assert entry.listed == listed
        assert entry.row_name.strip(), f"{soe} 缺 row_name"
        assert entry.report_type in {
            "balance_sheet",
            "income_statement",
            "cash_flow_statement",
            "equity_statement",
        }, f"{soe} 的 report_type 非法: {entry.report_type}"
        assert len(entry.evidence.strip()) >= 20, f"{soe} 的 evidence 过短"

    def test_reverse_map_is_bijective(self) -> None:
        assert len(LISTED_TO_SOE_ROW_CODE_MAP) == len(CROSS_VARIANT_ROW_CODE_MAP), (
            "反向映射条数不等 —— 说明 listed 侧有重复目标码，映射非双射"
        )
        for soe, entry in CROSS_VARIANT_ROW_CODE_MAP.items():
            assert LISTED_TO_SOE_ROW_CODE_MAP[entry.listed] == soe

    def test_report_type_prefix_consistency(self) -> None:
        """row_code 前缀必须与 report_type 一致（防抄错行）。"""
        prefix_of = {
            "balance_sheet": "BS-",
            "income_statement": "IS-",
            "cash_flow_statement": "CFS-",
            "equity_statement": "EQ-",
        }
        for soe, entry in CROSS_VARIANT_ROW_CODE_MAP.items():
            want = prefix_of[entry.report_type]
            assert soe.startswith(want), f"{soe} 前缀与 {entry.report_type} 不符"
            assert entry.listed.startswith(want), (
                f"{entry.listed} 前缀与 {entry.report_type} 不符"
            )


# ---------------------------------------------------------------------------
# Property 12：禁止改写清单（反向自检）
# ---------------------------------------------------------------------------


class TestForbiddenRewrites:
    """Requirement 3.6 / 3.7：初稿三条错误映射必须被钉死。"""

    DRAFT_ERRORS = (("BS-013", "BS-016"), ("BS-053", "BS-058"), ("BS-043", "BS-059"))

    def test_forbidden_covers_three_codes(self) -> None:
        assert set(ONE_CODE_TWO_MEANINGS_FORBIDDEN) >= {"BS-016", "BS-058", "BS-059"}, (
            "禁止改写清单缺少实证的三条一码两义目标码"
        )

    @pytest.mark.parametrize("code", ["BS-016", "BS-058", "BS-059"])
    def test_forbidden_entry_has_both_side_names(self, code: str) -> None:
        entry = ONE_CODE_TWO_MEANINGS_FORBIDDEN[code]
        assert entry.soe_row_name.strip(), f"{code} 缺 soe 侧 row_name"
        assert entry.listed_row_name.strip(), f"{code} 缺 listed 侧 row_name"
        assert entry.soe_row_name != entry.listed_row_name, (
            f"{code} 两侧 row_name 相同 —— 那它就不是一码两义，登记有误"
        )
        assert len(entry.reason.strip()) >= 20, f"{code} 理由过短"

    def test_forbidden_predicate_works(self) -> None:
        assert is_forbidden_rewrite("BS-016") is True
        assert is_forbidden_rewrite("BS-058") is True
        assert is_forbidden_rewrite("BS-059") is True
        assert is_forbidden_rewrite("BS-111") is False
        assert is_forbidden_rewrite("IS-055") is False

    @pytest.mark.parametrize("src,dst", DRAFT_ERRORS)
    def test_draft_error_not_in_map(self, src: str, dst: str) -> None:
        """反向自检核心：初稿三条错误映射不得出现在 MAP 里。

        Requirement 3.7 —— 把任一条加入 MAP 即须打红。此处正向断言其不存在；
        `test_mutation_adding_draft_error_is_detected` 证明检测手段有效。
        """
        entry = CROSS_VARIANT_ROW_CODE_MAP.get(src)
        assert entry is None or entry.listed != dst, (
            f"初稿错误映射 {src}→{dst} 出现在清单里！"
            f"{src} 是稳定码（两侧同名）压根不需改写，{dst} 是一码两义会指向另一科目"
        )

    def test_mutation_adding_draft_error_is_detected(self) -> None:
        """证明上一条的检测手段真的能抓住变异（不是空转）。"""
        from app.services.note_conversion_row_codes import RowCodePair

        mutated = dict(CROSS_VARIANT_ROW_CODE_MAP)
        mutated["BS-013"] = RowCodePair(
            soe="BS-013",
            listed="BS-016",
            report_type="balance_sheet",
            row_name="一年内到期的非流动资产",
            evidence="mutation probe: 初稿错误映射",
        )
        # 同一判据施加于变异版本 → 必须能识别出问题
        entry = mutated.get("BS-013")
        assert entry is not None and entry.listed == "BS-016", "变异未生效，自检无意义"

        # 稳定码判据同样能抓住它
        assert "BS-013" in STABLE_ROW_CODES_MUST_NOT_BE_MAPPED, (
            "BS-013 未登记为稳定码 —— 那条真不变量抓不到初稿错误"
        )

    def test_map_and_forbidden_are_disjoint(self) -> None:
        """Requirement 3.8：两清单键值集合无交集。"""
        map_codes = set(CROSS_VARIANT_ROW_CODE_MAP) | {
            e.listed for e in CROSS_VARIANT_ROW_CODE_MAP.values()
        }
        overlap = map_codes & set(ONE_CODE_TWO_MEANINGS_FORBIDDEN)
        assert not overlap, (
            f"同义两码清单与禁止改写清单有交集 {overlap} —— 判据自相矛盾"
        )


# ---------------------------------------------------------------------------
# 真不变量：稳定码不得被映射
# ---------------------------------------------------------------------------


class TestStableCodesNeverMapped:
    """实证推导的真不变量（比 Requirement 3.8 的字面表述更强）。

    12 条映射的 value **全部**是「两侧异名」码（码位偏移的必然结果），故
    「MAP ∩ 全部 78 条两侧异名码 = ∅」不可满足。真正的判据是：
    MAP 的 key/value 都不得是「稳定码」（两侧同名 ⇒ 压根不需改写）。
    """

    def test_stable_codes_registered(self) -> None:
        assert set(STABLE_ROW_CODES_MUST_NOT_BE_MAPPED) >= {
            "BS-013",
            "BS-043",
            "BS-053",
        }, "稳定码清单缺少初稿三条的源码"

    @pytest.mark.parametrize("code", sorted(STABLE_ROW_CODES_MUST_NOT_BE_MAPPED))
    def test_stable_code_not_used_as_map_key(self, code: str) -> None:
        assert code not in CROSS_VARIANT_ROW_CODE_MAP, (
            f"稳定码 {code} 出现在映射清单的 key 上 —— 两侧同名不需改写"
        )

    @pytest.mark.parametrize("code", sorted(STABLE_ROW_CODES_MUST_NOT_BE_MAPPED))
    def test_stable_code_not_used_as_map_value(self, code: str) -> None:
        targets = {e.listed for e in CROSS_VARIANT_ROW_CODE_MAP.values()}
        assert code not in targets, (
            f"稳定码 {code} 出现在映射清单的 value 上 —— 会把另一行的值指到它"
        )

    def test_stable_code_entry_has_reason(self) -> None:
        for code, reason in STABLE_ROW_CODES_MUST_NOT_BE_MAPPED.items():
            assert len(reason.strip()) >= 10, f"稳定码 {code} 缺理由"


# ---------------------------------------------------------------------------
# Property 13：改写函数行为
# ---------------------------------------------------------------------------


class TestRewriteBehaviour:
    """Requirement 3.3 / 3.5：清单内改写、清单外不变。"""

    def test_rewrite_soe_to_listed(self) -> None:
        assert rewrite_row_code("IS-055", "soe", "listed") == "IS-033"
        assert rewrite_row_code("BS-111", "soe", "listed") == "BS-077"

    def test_rewrite_listed_to_soe(self) -> None:
        assert rewrite_row_code("IS-033", "listed", "soe") == "IS-055"
        assert rewrite_row_code("BS-077", "listed", "soe") == "BS-111"

    def test_out_of_list_code_unchanged(self) -> None:
        for code in ("BS-002", "BS-013", "BS-043", "BS-053", "IS-001", "CFSS-016"):
            assert rewrite_row_code(code, "soe", "listed") == code, (
                f"清单外 row_code {code} 被改写"
            )

    def test_forbidden_code_never_rewritten(self) -> None:
        for code in ONE_CODE_TWO_MEANINGS_FORBIDDEN:
            assert rewrite_row_code(code, "soe", "listed") == code
            assert rewrite_row_code(code, "listed", "soe") == code

    def test_same_direction_is_noop(self) -> None:
        assert rewrite_row_code("IS-055", "soe", "soe") == "IS-055"
        assert rewrite_row_code("IS-033", "listed", "listed") == "IS-033"

    def test_formula_rewrite_positive(self) -> None:
        """Requirement 3.5 正向断言。"""
        out, n = rewrite_row_refs_in_formula("ROW('IS-055')", "soe", "listed")
        assert out == "ROW('IS-033')"
        assert n == 1

    def test_formula_rewrite_multiple_refs(self) -> None:
        src = "ROW('IS-055') + ROW('IS-062') - ROW('BS-002')"
        out, n = rewrite_row_refs_in_formula(src, "soe", "listed")
        assert out == "ROW('IS-033') + ROW('IS-039') - ROW('BS-002')"
        assert n == 2, "只应改写清单内的两条，BS-002 保持不变"

    def test_formula_rewrite_negative(self) -> None:
        """Requirement 3.5 反面断言：清单外保持不变。"""
        src = "ROW('BS-002')"
        out, n = rewrite_row_refs_in_formula(src, "soe", "listed")
        assert out == src
        assert n == 0

    def test_formula_rewrite_leaves_forbidden_alone(self) -> None:
        src = "ROW('BS-013') + ROW('BS-016')"
        out, n = rewrite_row_refs_in_formula(src, "soe", "listed")
        assert out == src, "稳定码与禁止码都不得改写"
        assert n == 0

    def test_formula_rewrite_handles_sum_row(self) -> None:
        src = "SUM_ROW('IS-055','IS-062')"
        out, n = rewrite_row_refs_in_formula(src, "soe", "listed")
        assert out == "SUM_ROW('IS-033','IS-039')"
        assert n == 2

    def test_formula_rewrite_empty_input(self) -> None:
        assert rewrite_row_refs_in_formula("", "soe", "listed") == ("", 0)
        assert rewrite_row_refs_in_formula(None, "soe", "listed") == (None, 0)

    def test_formula_rewrite_does_not_touch_tb(self) -> None:
        src = "TB('1001','期末余额')+SUM_TB('1401~1499','期末余额')"
        out, n = rewrite_row_refs_in_formula(src, "soe", "listed")
        assert out == src
        assert n == 0


# ---------------------------------------------------------------------------
# Requirement 4.4：原因码可区分
# ---------------------------------------------------------------------------


class TestReasonCode:
    """`no_mapping_needed` 与 `not_implemented` 必须可区分。"""

    def test_reason_code_is_no_mapping_needed(self) -> None:
        assert FORMULA_REWRITE_REASON == "no_mapping_needed", (
            "report_config 实证 0 条公式引用那 12 组 row_code ⇒ 原因码应为 "
            "no_mapping_needed（无可改写对象），而非 not_implemented（没做）"
        )

    def test_reason_code_not_placeholder(self) -> None:
        assert FORMULA_REWRITE_REASON not in {"", "TODO", "not_implemented"}


# ---------------------------------------------------------------------------
# 源码级：禁止模糊推断
# ---------------------------------------------------------------------------


class TestNoFuzzyInference:
    """Requirement 3.2：不得按名称模糊或按 row_code 数字相邻推断。"""

    @pytest.fixture(scope="class")
    def code(self) -> str:
        src = _MODULE_PATH.read_text(encoding="utf-8")
        src = re.sub(r'([rRbBuU]{0,2})"""[\s\S]*?"""', '""', src)
        src = re.sub(r"([rRbBuU]{0,2})'''[\s\S]*?'''", "''", src)
        return "\n".join(line.split("#", 1)[0] for line in src.splitlines())

    def test_no_similarity_library(self, code: str) -> None:
        for token in ("difflib", "SequenceMatcher", "rapidfuzz", "Levenshtein"):
            assert token not in code, f"row_code 清单模块引入了 {token}"

    def test_no_numeric_adjacency_inference(self, code: str) -> None:
        """禁止「数字 ±N」式推断（如 int(code[3:]) - 22）。"""
        assert not re.search(r"int\s*\(\s*\w+\s*\[", code), (
            "出现对 row_code 做数字切片解析 —— 禁止按编号相邻推断映射"
        )

    def test_map_is_frozen_literal(self, code: str) -> None:
        """清单必须是字面量，不得由循环/推导式生成。"""
        assert "CROSS_VARIANT_ROW_CODE_MAP: " in code or "CROSS_VARIANT_ROW_CODE_MAP =" in code
        # 反向映射由 MAP 反转生成是允许的；正向 MAP 不得来自推导式
        m = re.search(
            r"CROSS_VARIANT_ROW_CODE_MAP[^=]*=\s*(.{0,80})", code, re.S
        )
        assert m, "未找到 CROSS_VARIANT_ROW_CODE_MAP 声明"
        head = m.group(1)
        assert "for " not in head, (
            "正向映射由推导式生成 —— Requirement 3.2 要求人工确认后冻结为字面量"
        )
