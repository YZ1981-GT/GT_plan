"""守卫：附注章节标题匹配器（Property 18~21）。

spec: soe-listed-note-conversion-correctness / Requirements 5.1~5.5

不连库、纯函数 + 源码级断言，可进 CI。

核心防护：
- Property 18：禁止相似度实现（源码级）
- Property 19：5 对别名生效
- Property 20：禁止对返回 False（含反向自检）
- Property 21：每条别名 evidence 非空且指向源 docx
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.services.note_section_matcher import (
    FORBIDDEN_MATCH_PAIRS,
    SECTION_TITLE_ALIASES,
    AliasPair,
    match_section,
    normalize_for_match,
    resolve_alias_counterpart,
)

_MODULE_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "app"
    / "services"
    / "note_section_matcher.py"
)


def _strip_comments_and_docstrings(src: str) -> str:
    """剥掉 ``#`` 注释与三引号 docstring。

    本模块的 docstring 与注释里**必然**提到 ``SequenceMatcher``/``0.87``（那是禁止
    相似度的理由说明），不剥就会把说明文字当成真实实现 —— 与平台已登记的
    「读源码型守卫必须先 stripComments」同族。
    """
    # 先剥三引号块（含 r""" 前缀）
    src = re.sub(r'([rRbBuU]{0,2})"""[\s\S]*?"""', '""', src)
    src = re.sub(r"([rRbBuU]{0,2})'''[\s\S]*?'''", "''", src)
    # 再剥行注释
    out_lines: list[str] = []
    for line in src.splitlines():
        idx = line.find("#")
        if idx >= 0:
            # 粗判：# 不在字符串里（本模块无内联 # 字符串字面量）
            out_lines.append(line[:idx])
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


@pytest.fixture(scope="module")
def module_src() -> str:
    assert _MODULE_PATH.exists(), f"matcher 模块不存在: {_MODULE_PATH}"
    return _MODULE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def module_code(module_src: str) -> str:
    return _strip_comments_and_docstrings(module_src)


# ---------------------------------------------------------------------------
# Property 18：禁止相似度实现
# ---------------------------------------------------------------------------


class TestNoSimilarityImplementation:
    """Requirement 5.1：不得引入相似度/模糊匹配。"""

    FORBIDDEN_TOKENS = (
        "difflib",
        "SequenceMatcher",
        "get_close_matches",
        "rapidfuzz",
        "fuzzywuzzy",
        "Levenshtein",
        "jellyfish",
        "textdistance",
    )

    def test_no_similarity_library_imported(self, module_code: str) -> None:
        for token in self.FORBIDDEN_TOKENS:
            assert token not in module_code, (
                f"matcher 引入了相似度实现 {token!r} —— 实证 0.87(禁止对) > 0.80(需救回) "
                f"⇒ 任何阈值都不安全，必须穷举配对"
            )

    def test_no_ratio_call(self, module_code: str) -> None:
        assert not re.search(r"\.ratio\s*\(", module_code), (
            "matcher 出现 .ratio() 调用 —— 禁止相似度打分"
        )

    def test_no_threshold_constant(self, module_code: str) -> None:
        """禁止出现 0.x 阈值常量（相似度阈值的典型形态）。"""
        hits = re.findall(r"(?<![\w.])0\.\d+", module_code)
        assert not hits, f"matcher 出现疑似相似度阈值常量 {hits} —— 禁止阈值法"

    def test_module_does_not_expose_similarity_api(self) -> None:
        import app.services.note_section_matcher as mod

        exported = set(getattr(mod, "__all__", ()))
        for name in exported:
            assert "similar" not in name.lower(), (
                f"matcher 导出了相似度接口 {name} —— Requirement 5.1 禁止"
            )

    def test_strip_helper_actually_strips(self, module_src: str, module_code: str) -> None:
        """反向自检：原始源码确实含被禁字样（否则上面断言是空转）。"""
        assert "SequenceMatcher" in module_src, (
            "原始源码里没有 SequenceMatcher —— 说明 docstring 的理由说明被删了，"
            "此时 Property 18 的断言变成空转，必须恢复说明或改判据"
        )
        assert "SequenceMatcher" not in module_code, (
            "_strip_comments_and_docstrings 没能剥掉 docstring —— 守卫解析失效"
        )


# ---------------------------------------------------------------------------
# Property 19：别名生效
# ---------------------------------------------------------------------------


class TestAliasPairsWork:
    """Requirement 5.2：5 对已实证别名必须匹配成功。"""

    EXPECTED_PAIRS = (
        ("财务报表编制基础", "财务报表的编制基础"),
        ("递延所得税资产和递延所得税负债", "递延所得税资产与递延所得税负债"),
        ("所有权和使用权受到限制的资产", "所有权或使用权受到限制的资产"),
        ("营业收入、营业成本", "营业收入和营业成本"),
        ("研究开发支出", "研发支出"),
    )

    def test_alias_count_at_least_five(self) -> None:
        assert len(SECTION_TITLE_ALIASES) >= 5, (
            f"别名清单只有 {len(SECTION_TITLE_ALIASES)} 条，Requirement 5.2 要求至少 5 对"
        )

    @pytest.mark.parametrize("soe,listed", EXPECTED_PAIRS)
    def test_expected_pair_matches(self, soe: str, listed: str) -> None:
        assert match_section(soe, listed) is True, f"别名未生效: {soe} ↔ {listed}"

    @pytest.mark.parametrize("soe,listed", EXPECTED_PAIRS)
    def test_expected_pair_is_registered(self, soe: str, listed: str) -> None:
        registered = {(p.soe_title, p.listed_title) for p in SECTION_TITLE_ALIASES}
        assert (soe, listed) in registered, f"清单缺少实证别名对: {soe} ↔ {listed}"

    @pytest.mark.parametrize("soe,listed", EXPECTED_PAIRS)
    def test_counterpart_resolvable_both_ways(self, soe: str, listed: str) -> None:
        assert resolve_alias_counterpart(soe, "listed") == listed
        assert resolve_alias_counterpart(listed, "soe") == soe

    def test_exact_same_title_matches(self) -> None:
        assert match_section("货币资金", "货币资金") is True

    def test_whitespace_only_diff_matches(self) -> None:
        assert match_section("货币 资金", "货币资金") is True
        assert match_section("　货币资金　", "货币资金") is True

    def test_unrelated_titles_do_not_match(self) -> None:
        assert match_section("货币资金", "应收账款") is False
        assert match_section("固定资产", "在建工程") is False

    def test_empty_titles_never_match(self) -> None:
        assert match_section("", "") is False
        assert match_section(None, None) is False
        assert match_section("货币资金", None) is False
        assert match_section(None, "货币资金") is False

    def test_alias_is_not_transitive_to_unrelated(self) -> None:
        """别名不得产生传递性误配。"""
        assert match_section("研究开发支出", "开发支出") is False
        assert match_section("研发支出", "开发支出") is False


# ---------------------------------------------------------------------------
# Property 20：禁止对
# ---------------------------------------------------------------------------


class TestForbiddenPairs:
    """Requirement 5.3 / 5.4：禁止对必须返回 False，且反向自检可打红。"""

    def test_forbidden_list_covers_parent_company_chapter(self) -> None:
        joined = " | ".join(f"{a}~{b}" for a, b, _ in FORBIDDEN_MATCH_PAIRS)
        assert "财务报表主要项目注释" in joined, (
            "禁止对清单未覆盖「财务报表主要项目注释」—— 该对相似度 0.87，"
            "配错会把 soe 合并章数据落进 listed 母公司章"
        )

    def test_both_spellings_of_parent_company_title_registered(self) -> None:
        """源 docx 是「公司财务报表主要项目注释」，JSON 是「母公司…」⇒ 两种都要登记。"""
        listed_titles = {b for _a, b, _r in FORBIDDEN_MATCH_PAIRS}
        assert "公司财务报表主要项目注释" in listed_titles, (
            "缺源 docx 写法（无「母」字）—— docx 实测 Heading 1 就是这个"
        )
        assert "母公司财务报表主要项目注释" in listed_titles, (
            "缺 note_template_listed.json 现值写法（带「母」字）"
        )

    @pytest.mark.parametrize("soe,listed,_reason", FORBIDDEN_MATCH_PAIRS)
    def test_forbidden_pair_rejected(self, soe: str, listed: str, _reason: str) -> None:
        assert match_section(soe, listed) is False, f"禁止对被误判为同一章: {soe} ↔ {listed}"

    @pytest.mark.parametrize("soe,listed,_reason", FORBIDDEN_MATCH_PAIRS)
    def test_forbidden_pair_rejected_reversed(
        self, soe: str, listed: str, _reason: str
    ) -> None:
        """方向无关：反向传入同样必须拒绝。"""
        assert match_section(listed, soe) is False

    @pytest.mark.parametrize("_soe,_listed,reason", FORBIDDEN_MATCH_PAIRS)
    def test_forbidden_pair_has_reason(self, _soe: str, _listed: str, reason: str) -> None:
        assert isinstance(reason, str) and len(reason) >= 20, (
            f"禁止对理由过短（{len(reason)} 字），必须写清为何不可匹配"
        )

    def test_forbidden_overrides_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """反向自检：把禁止对塞进 ALIASES，禁止对仍须优先拒绝（Requirement 5.4）。

        这条是 Requirement 5.4 的字面实现 —— 「若把禁止匹配对加入允许清单必须打红」。
        此处不是让守卫红，而是证明**实现层面**禁止对优先级高于别名：
        即便有人误加别名，match_section 仍返回 False。
        """
        import app.services.note_section_matcher as mod

        soe, listed, _ = FORBIDDEN_MATCH_PAIRS[0]
        injected = SECTION_TITLE_ALIASES + (
            AliasPair(soe_title=soe, listed_title=listed, evidence="mutation-probe"),
        )
        monkeypatch.setattr(mod, "SECTION_TITLE_ALIASES", injected)
        monkeypatch.setattr(mod, "_ALIAS_KEYS", mod._alias_key_pairs())

        assert mod.match_section(soe, listed) is False, (
            "禁止对被别名清单绕过 —— match_section 必须先查 FORBIDDEN 再查 ALIASES"
        )

    def test_alias_and_forbidden_are_disjoint(self) -> None:
        """两清单不得有交集（否则判据自相矛盾）。"""
        alias_keys = {
            (normalize_for_match(p.soe_title), normalize_for_match(p.listed_title))
            for p in SECTION_TITLE_ALIASES
        }
        forbidden_keys = {
            (normalize_for_match(a), normalize_for_match(b))
            for a, b, _ in FORBIDDEN_MATCH_PAIRS
        }
        overlap = alias_keys & forbidden_keys
        assert not overlap, f"别名清单与禁止对清单有交集: {overlap}"


# ---------------------------------------------------------------------------
# Property 21：evidence 质量
# ---------------------------------------------------------------------------


class TestEvidenceQuality:
    """Requirement 5.5：每条配对须附源 docx 依据。"""

    @pytest.mark.parametrize("pair", SECTION_TITLE_ALIASES, ids=lambda p: p.soe_title)
    def test_evidence_non_empty(self, pair: AliasPair) -> None:
        assert isinstance(pair.evidence, str) and len(pair.evidence.strip()) >= 20, (
            f"别名 {pair.soe_title}↔{pair.listed_title} 的 evidence 过短"
        )

    @pytest.mark.parametrize("pair", SECTION_TITLE_ALIASES, ids=lambda p: p.soe_title)
    def test_evidence_cites_source_docx(self, pair: AliasPair) -> None:
        assert "docx" in pair.evidence, (
            f"别名 {pair.soe_title} 的 evidence 未引用源 docx —— "
            "判据真源必须是 docs/模版/ 两份 docx"
        )

    @pytest.mark.parametrize("pair", SECTION_TITLE_ALIASES, ids=lambda p: p.soe_title)
    def test_evidence_quotes_both_titles(self, pair: AliasPair) -> None:
        """evidence 必须含两侧标题原文，便于人工复核。"""
        assert pair.soe_title in pair.evidence, f"evidence 未引用 soe 标题原文"
        assert pair.listed_title in pair.evidence, f"evidence 未引用 listed 标题原文"

    def test_no_placeholder_evidence(self) -> None:
        bad = ["TODO", "TBD", "待补充", "占位", "mutation-probe"]
        for pair in SECTION_TITLE_ALIASES:
            for token in bad:
                assert token not in pair.evidence, (
                    f"别名 {pair.soe_title} 的 evidence 是占位文本 {token!r}"
                )


# ---------------------------------------------------------------------------
# 归一化行为
# ---------------------------------------------------------------------------


class TestNormalization:
    """Requirement 5.1：归一化仅去空白。"""

    def test_strips_all_whitespace_kinds(self) -> None:
        assert normalize_for_match(" 货\t币\u3000资\u00a0金 ") == "货币资金"

    def test_does_not_strip_particles(self) -> None:
        """虚词不得被归一化去掉（否则等价于隐式模糊匹配）。"""
        assert normalize_for_match("财务报表的编制基础") == "财务报表的编制基础"
        assert normalize_for_match("营业收入、营业成本") == "营业收入、营业成本"

    def test_does_not_fold_fullwidth_punctuation(self) -> None:
        assert normalize_for_match("（一）其他") == "（一）其他"

    def test_none_and_non_string(self) -> None:
        assert normalize_for_match(None) == ""
        assert normalize_for_match(123) == ""  # type: ignore[arg-type]
