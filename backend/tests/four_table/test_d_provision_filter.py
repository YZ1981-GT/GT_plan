"""备抵名称过滤守卫 —— Property 9 / 35。

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 2.1, 2.2, 2.3, 2.4, 2.8

不连库（纯函数 + 源码级断言），可进 CI。

**每条断言都配了反向自检** —— 复现「改造前的做法」时必须打红，否则守卫本身是空转。
"""
from __future__ import annotations

import inspect
import re

import pytest

from app.services.d_cycle_extraction.d_account_resolver import (
    D_ACCOUNT_SPECS,
    D_SUBJECT_KEYWORDS,
    NOT_IN_SCOPE,
)
from app.services.four_table.d_provision_filter import (
    REASON_NAME_MISSING,
    filter_provision_codes,
    normalize_account_name,
)

# 真实库实证的错映射（account_mapping 的 auto_fuzzy，2 个项目）
_WRONG_MAPPING_CODE = "1231.05"
_WRONG_MAPPING_NAME = "坏账准备_长期应收款"
_RIGHT_CODE = "1231.02"
_RIGHT_NAME = "坏账准备_应收账款"

_NAMES = {_RIGHT_CODE: _RIGHT_NAME, _WRONG_MAPPING_CODE: _WRONG_MAPPING_NAME}


# ─────────────────────── Property 9：过滤生效且如实记录 ───────────────────────


class TestFilterCorrectness:
    def test_wrong_mapping_is_dropped(self):
        """D2 的关键词必须拦住错映射进来的长期应收款坏账。"""
        r = filter_provision_codes(
            [_RIGHT_CODE, _WRONG_MAPPING_CODE], _NAMES, D_SUBJECT_KEYWORDS["D2"]
        )
        assert r.kept == (_RIGHT_CODE,)
        assert [d.code for d in r.dropped] == [_WRONG_MAPPING_CODE]
        assert r.applied is True

    def test_dropped_records_三字段(self):
        """被剔除的条目必须含 code / name / reason（供溯源面板展示，不得静默丢弃）。"""
        r = filter_provision_codes(
            [_RIGHT_CODE, _WRONG_MAPPING_CODE], _NAMES, D_SUBJECT_KEYWORDS["D2"]
        )
        d = r.dropped[0].as_dict()
        assert set(d) == {"code", "name", "reason"}
        assert d["name"] == _WRONG_MAPPING_NAME
        assert "应收账款" in d["reason"], "reason 须写明所用关键词"

    def test_kept_and_dropped_disjoint(self):
        r = filter_provision_codes(
            [_RIGHT_CODE, _WRONG_MAPPING_CODE], _NAMES, D_SUBJECT_KEYWORDS["D2"]
        )
        assert not (set(r.kept) & {d.code for d in r.dropped})

    def test_name_missing_goes_to_warnings_not_dropped(self):
        """名称缺失 → **保留**该码并进 warnings；混进 dropped 会让面板把保留行算成剔除。"""
        r = filter_provision_codes(
            [_RIGHT_CODE, "9999.99"], {_RIGHT_CODE: _RIGHT_NAME},
            D_SUBJECT_KEYWORDS["D2"],
        )
        assert "9999.99" in r.kept
        assert not r.dropped
        assert [w.code for w in r.warnings] == ["9999.99"]
        assert r.warnings[0].reason == REASON_NAME_MISSING
        # warnings ⊆ kept
        assert {w.code for w in r.warnings} <= set(r.kept)

    def test_separator_normalized_both_ways(self):
        """standard 表用横杠、client 表用下划线，两种写法都要认。"""
        for code, name in (
            ("1231-01", "坏账准备-应收票据"),
            ("1231.01", "坏账准备_应收票据"),
        ):
            r = filter_provision_codes([code], {code: name}, ("应收票据", "票据"))
            assert r.kept == (code,), (code, name)

    def test_dedupe_and_order_preserved(self):
        r = filter_provision_codes(
            ["1231.02", "1231.02", "1231.03"],
            {"1231.02": _RIGHT_NAME, "1231.03": "坏账准备_其他应收款"},
            D_SUBJECT_KEYWORDS["D2"],
        )
        assert r.kept == ("1231.02",)


# ─────────────────── Property 35：关键词粒度足以区分同族科目 ───────────────────


class TestKeywordGranularity:
    def test_d2_keyword_is_not_too_broad(self):
        """🔴 D2 的关键词只能是「应收账款」——「应收」会让过滤完全空转。"""
        assert D_SUBJECT_KEYWORDS["D2"] == ("应收账款",)
        for kw in D_SUBJECT_KEYWORDS["D2"]:
            assert kw != "应收", "关键词写宽成「应收」会放过长期应收款坏账"

    def test_每个备抵循环都声明了关键词(self):
        for wp, spec in D_ACCOUNT_SPECS.items():
            has_provision = bool(spec.fallback_provision or spec.provision_row_code)
            if has_provision:
                assert D_SUBJECT_KEYWORDS.get(wp), "%s 有备抵却没声明主体关键词" % wp
            else:
                assert wp not in D_SUBJECT_KEYWORDS, "%s 无备抵却声明了关键词" % wp


# ───────────────────────────── 反向自检（必须打红） ─────────────────────────────


class TestReverseSelfChecks:
    def test_反向_关键词写宽成应收则过滤空转(self):
        """复现「关键词粒度不足」→ 错映射的码会被保留（证明粒度断言不是空话）。"""
        r = filter_provision_codes(
            [_RIGHT_CODE, _WRONG_MAPPING_CODE], _NAMES, ("应收",)
        )
        assert _WRONG_MAPPING_CODE in r.kept, "关键词写宽后本该空转 —— 断言失效"

    def test_反向_不传关键词是空操作(self):
        """复现「既有 28 个消费方接入时的行为」→ 原样返回、applied=False。"""
        r = filter_provision_codes([_RIGHT_CODE, _WRONG_MAPPING_CODE], _NAMES, ())
        assert r.kept == (_RIGHT_CODE, _WRONG_MAPPING_CODE)
        assert r.applied is False
        assert not r.dropped and not r.warnings

    def test_反向_归一化不做过度处理(self):
        """只去空白与分隔符 —— 再激进会放过真错位。"""
        assert normalize_account_name("坏账准备_应收账款") == normalize_account_name(
            "坏账准备-应收账款"
        )
        # 「其他」不得被吃掉，否则「坏账准备_其他应收款」会命中「应收款」类关键词判断
        assert "其他" in normalize_account_name("坏账准备_其他应收款")
        # 主体不同的两个名字归一后必须仍不相等
        assert normalize_account_name("坏账准备_应收账款") != normalize_account_name(
            "坏账准备_长期应收款"
        )


# ───────────────── Property 9（源码级）：D2~D7 无条件叠过滤 ─────────────────


class TestUnconditionalFilterWiring:
    """备抵过滤必须**无条件**执行，不得以 `use_provision_name_filter` 为门。

    理由（真实库实证）：`1231.05 → 1231-02` 是 `auto_fuzzy` 错映射，此时
    `provision_resolved_from == 'report_config'` ⇒ 共享件的
    `use_provision_name_filter` 为 **False** ⇒ 既有机制不叠过滤 ⇒ 污染进入。
    """

    @staticmethod
    def _src_without_comments(mod) -> str:
        src = inspect.getsource(mod)
        return "\n".join(
            l for l in src.split("\n") if not l.strip().startswith("#")
        )

    def test_编排件不以_use_provision_name_filter_为门(self):
        from app.services.d_cycle_extraction import d_tb_fetch

        code = self._src_without_comments(d_tb_fetch)
        assert "filter_provision_codes" in code, "编排件未调用过滤"
        assert "use_provision_name_filter" not in code, (
            "🔴 过滤被 use_provision_name_filter 门控 —— 那条 auto_fuzzy 错映射会漏过"
        )

    def test_过滤只作用于备抵槽(self):
        """原值槽不得叠主体关键词过滤（关键词是备抵专用）。

        🔴 截取函数调用的实参必须按**圆括号配对**扫，不能用 `(.*?)\\)` ——
        非贪婪会停在实参里第一个 `)` 上（`subject_keywords=()` 的空元组），
        截出来的片段是 `subject_keywords=(` 从而断言失效（本守卫首版即中招）。
        """
        from app.services.d_cycle_extraction import d_tb_fetch

        code = self._src_without_comments(d_tb_fetch)
        start = code.find("SLOT_GROSS, gross_codes, rows,")
        assert start > 0, "未找到原值槽的构造调用"
        # 从调用起点向后按圆括号配对找到实参结束位置
        depth = 1
        i = start
        while i < len(code) and depth > 0:
            if code[i] == "(":
                depth += 1
            elif code[i] == ")":
                depth -= 1
            i += 1
        args = " ".join(code[start:i].split())
        assert "subject_keywords=()" in args, (
            "原值槽必须显式传空关键词，实参片段=%r" % args[:160]
        )
        # 反向自检：备抵槽那处**必须**传真实关键词（否则本断言等于什么都没约束）
        pstart = code.find("SLOT_PROVISION, provision_codes, rows,")
        assert pstart > 0
        depth, j = 1, pstart
        while j < len(code) and depth > 0:
            if code[j] == "(":
                depth += 1
            elif code[j] == ")":
                depth -= 1
            j += 1
        pargs = " ".join(code[pstart:j].split())
        assert "subject_keywords=subject_keywords" in pargs, (
            "备抵槽未传主体关键词，实参片段=%r" % pargs[:160]
        )


# ───────────────── Property 34：语义规格保留但不接线且理由在册 ─────────────────


class TestSemanticSpecNotWired:
    def test_d_cycle_specs_docstring_写明不接线理由(self):
        from app.services.four_table import d_cycle_specs

        doc = d_cycle_specs.__doc__ or ""
        assert "不接线" in doc, (
            "🔴 `four_table/d_cycle_specs.py` 必须在模块 docstring 写明「当前不接线」"
            "及其实证理由，否则下个会话会又发起一轮迁移"
        )

    def test_不在范围内的循环已登记去处(self):
        """D1 / D4 有意不纳入 `d_account_resolver`，必须登记去处（防「顺手统一」）。"""
        assert set(NOT_IN_SCOPE) == {"D1", "D4"}
        for wp, reason in NOT_IN_SCOPE.items():
            assert len(reason) >= 10, "%s 的不纳入理由太短" % wp
        assert not (set(D_ACCOUNT_SPECS) & set(NOT_IN_SCOPE))
        assert set(D_ACCOUNT_SPECS) | set(NOT_IN_SCOPE) == {
            "D%d" % i for i in range(1, 8)
        }


@pytest.mark.parametrize("wp", sorted(D_ACCOUNT_SPECS))
def test_备抵兜底码非空时必有关键词(wp):
    spec = D_ACCOUNT_SPECS[wp]
    if spec.fallback_provision:
        assert D_SUBJECT_KEYWORDS.get(wp), "%s 有备抵兜底码却无关键词" % wp
