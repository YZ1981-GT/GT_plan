"""per-table guidance 分流单元测试 — note-per-table-guidance Phase 1.

覆盖：
- 货币资金（2 表）：tables[0].guidance 含注+提示，tables[1] 无
- 应收账款（11 表，全标题行无 guidance）：per_table_guidance 全空，标题仅用于回填
- 单表章节：guidance 走章节级（零回归铁律 R2）
- _match_title_to_table_idx 四级匹配
- 向后兼容：不传 tables 行为同旧

Validates: Requirements R1, R2
"""

from __future__ import annotations

from app.services.disclosure_engine import (
    classify_template_content,
    _match_title_to_table_idx,
)


# ---------------------------------------------------------------------------
# 货币资金（八、1）— 最小典型（2 表）
# ---------------------------------------------------------------------------
def test_cash_two_tables_guidance_assigned_to_first_table():
    """货币资金：2 个表，2 段提示在 tables[0] 标题行前 → 归 tables[0]，tables[1] 无。"""
    tables = [
        {"name": "货币资金"},
        {"name": "受限制的货币资金明细"},
    ]
    text_sections = [
        "（注：如有因抵押、质押或冻结等对使用有限制的款项，应在受限货币资金中列示。）",
        "（提示：企业持有的货币资金应说明是否存在使用受限情况。）",
        "### 受限制的货币资金明细",
    ]

    substantive, section_guidance, per_table = classify_template_content(
        text_sections, None, tables,
    )

    # 多表场景：提示归 per-table，不进章节级
    assert section_guidance is None
    assert substantive is None
    # 两段提示都归 tables[0]（出现在推进游标的标题行之前）
    assert 0 in per_table
    assert "（注：" in per_table[0]
    assert "（提示：" in per_table[0]
    assert per_table[0].count("\n\n") == 1  # 两段以 \n\n 连接
    # tables[1] 无 guidance
    assert 1 not in per_table


def test_cash_per_table_guidance_written_into_built_tables():
    """模拟生成流程接入：per_table_guidance 写入 built_tables[idx]['guidance']。"""
    tables = [{"name": "货币资金"}, {"name": "受限制的货币资金明细"}]
    text_sections = [
        "（注：如有受限款项应列示。）",
        "### 受限制的货币资金明细",
    ]
    _, _, per_table = classify_template_content(text_sections, None, tables)

    built_tables = [
        {"name": "货币资金", "headers": [], "rows": []},
        {"name": "受限制的货币资金明细", "headers": [], "rows": []},
    ]
    for idx, g in per_table.items():
        if 0 <= idx < len(built_tables) and g:
            built_tables[idx]["guidance"] = g

    assert built_tables[0].get("guidance")
    assert "（注：" in built_tables[0]["guidance"]
    assert "guidance" not in built_tables[1]


# ---------------------------------------------------------------------------
# 应收账款（八、5）— 多表复杂（11 表，全标题行无 guidance）
# ---------------------------------------------------------------------------
def test_receivables_all_titles_no_guidance():
    """应收账款：text_sections 全是标题行，无实质 guidance → per_table 全空。

    注：`_is_table_title_paragraph`（复用，不重写）现对任意长度的 `#` 开头
    markdown 标题都判为标题行，故含长 `####` 标题也被识别并丢弃。
    """
    tables = [{"name": f"表{i}"} for i in range(11)]
    text_sections = [
        "（1）按账龄披露应收账款",
        "（2）按坏账计提方法披露",
        "（3）单项计提坏账准备",
        "（4）组合计提坏账准备",
        "（5）本期计提收回或转回",
        "（6）实际核销的应收账款",
        "#### 期末单项金额重大并单独计提坏账准备",  # >20 字长标题，现也判为标题行
    ]

    substantive, section_guidance, per_table = classify_template_content(
        text_sections, None, tables,
    )

    assert per_table == {}  # 全标题行，无 guidance 归属
    assert section_guidance is None
    assert substantive is None  # 长 #### 标题被丢弃，不留正文


# ---------------------------------------------------------------------------
# 单表章节 — 零回归铁律 R2
# ---------------------------------------------------------------------------
def test_single_table_guidance_goes_section_level():
    """单表章节：per_table_guidance 为空，所有提示归章节级 guidance_text。"""
    tables = [{"name": "固定资产"}]
    text_sections = [
        "（注：应披露固定资产的折旧方法及使用寿命。）",
        "本公司固定资产采用年限平均法计提折旧。",
    ]

    substantive, section_guidance, per_table = classify_template_content(
        text_sections, None, tables,
    )

    assert per_table == {}
    assert section_guidance == "（注：应披露固定资产的折旧方法及使用寿命。）"
    assert substantive == "本公司固定资产采用年限平均法计提折旧。"


def test_no_table_guidance_goes_section_level():
    """无表（tables=None）：所有提示归章节级（向后兼容）。"""
    text_sections = [
        "（注：应披露相关会计政策。）",
        "本公司执行企业会计准则。",
    ]
    substantive, section_guidance, per_table = classify_template_content(
        text_sections, None, None,
    )
    assert per_table == {}
    assert section_guidance == "（注：应披露相关会计政策。）"
    assert substantive == "本公司执行企业会计准则。"


def test_backward_compat_pair_callers_unaffected():
    """旧二元组消费方（解构前两项）行为不变。"""
    substantive, guidance = classify_template_content(
        ["（注：应披露折旧方法。）", "本公司采用年限平均法。"], None,
    )[:2]
    assert guidance == "（注：应披露折旧方法。）"
    assert substantive == "本公司采用年限平均法。"


# ---------------------------------------------------------------------------
# _match_title_to_table_idx 四级匹配
# ---------------------------------------------------------------------------
def test_match_exact():
    names = ["货币资金", "受限制的货币资金明细"]
    assert _match_title_to_table_idx("受限制的货币资金明细", names, 0) == 1
    assert _match_title_to_table_idx("### 受限制的货币资金明细", names, 0) == 1


def test_match_numbered():
    names = ["表A", "表B", "表C"]
    assert _match_title_to_table_idx("（2）xxx", names, 0) == 1
    assert _match_title_to_table_idx("3. yyy", names, 0) == 2


def test_match_containment():
    names = ["按账龄披露应收账款", "其他"]
    assert _match_title_to_table_idx("账龄", names, 1) == 0  # 表名包含标题


def test_match_fallback_cursor_plus_one():
    names = ["表A", "表B", "表C"]
    # 无任何匹配的标题 → 游标 +1
    assert _match_title_to_table_idx("完全不相关标题文字", names, 0) == 1
    assert _match_title_to_table_idx("完全不相关标题文字", names, 1) == 2


def test_match_fallback_out_of_range_returns_none():
    names = ["表A", "表B"]
    # 游标已在末尾，+1 越界 → None
    assert _match_title_to_table_idx("完全不相关标题文字", names, 1) is None


# ---------------------------------------------------------------------------
def test_plain_table_name_lines_routed_as_titles_not_body():
    """应收票据 五、4：text_sections 含与 tables[].name 精确相等的**无编号纯文本**
    子表标题（非 # 非编号），须被判为标题（不进可编辑正文），仅保留真实叙述。

    修复「提示内容漏进正文文本框」——此前 _is_table_title_paragraph 只认 #/编号标题，
    这些纯文本表名标题漏进 substantive。
    """
    from app.services.disclosure_engine import classify_template_content

    text_sections = [
        "如果法律上认定供应链票据属于《商业汇票承兑、贴现与再贴现管理办法》"
        "（中国人民银行中国银行保险监督管理委员会令〔2022〕第4号）的范围、"
        "具备《票据法》规定的要件",
        "期末本公司已质押的应收票据",
        "期末本公司已背书或贴现但尚未到期的应收票据",
        "期末本公司因出票人未履约而将其转应收账款的票据",
        "按坏账计提方法分类",
        "本期计提、收回或转回的坏账准备情况",
        "本期实际核销的应收票据情况",
    ]
    tables = [
        {"name": "应收票据"},
        {"name": "期末本公司已质押的应收票据"},
        {"name": "期末本公司已背书或贴现但尚未到期的应收票据"},
        {"name": "期末本公司因出票人未履约而将其转应收账款的票据"},
        {"name": "按坏账计提方法分类"},
        {"name": "本期计提、收回或转回的坏账准备情况"},
        {"name": "本期实际核销的应收票据情况"},
    ]

    substantive, section_guidance, per_table = classify_template_content(
        text_sections, None, tables,
    )

    # 6 个表名标题不得漏进正文
    for title in text_sections[1:]:
        assert not (substantive and title in substantive), f"表名标题漏进正文: {title}"
    # 仅保留真实叙述句
    assert substantive is not None
    assert substantive.startswith("如果法律上认定供应链票据")


def test_plain_table_name_exact_only_not_substring():
    """精确等于才判标题；含表名子串的实质正文不被误吞（保守，避免误删正文）。"""
    from app.services.disclosure_engine import classify_template_content

    tables = [{"name": "货币资金"}, {"name": "受限制的货币资金明细"}]
    text_sections = [
        "本公司货币资金主要为银行存款，不存在使用受限情况。",  # 含"货币资金"子串但非表名 → 正文
    ]
    substantive, _guidance, _per = classify_template_content(text_sections, None, tables)
    assert substantive == "本公司货币资金主要为银行存款，不存在使用受限情况。"
