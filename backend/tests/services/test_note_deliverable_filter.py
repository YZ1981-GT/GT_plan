"""附注交付过滤（spec deliverable-trio-generation-accuracy §2.6）。样本取自四个真实项目库内正文（2026-10-16）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.note_deliverable_filter import (
    FilterStats,
    deliverable_text_blocks,
    note_has_deliverable_content,
    structured_tables_nonempty,
)
from app.services.note_text_word_render import _Para, _Table


def _note(text, *, code="八、2", title="交易性金融资产", table_data=None):
    return SimpleNamespace(note_section=code, section_title=title, text_content=text, table_data=table_data)


def _lines(blocks) -> list[str]:
    out = []
    for b in blocks:
        if isinstance(b, _Table):
            out.append("<表>")
        elif isinstance(b, _Para):
            out.extend((b.prefix + "".join(r.text for r in b.runs)).split("\n"))
    return [x for x in out if x.strip()]


def test_hint_tail_dup_title_and_meta_are_removed():
    text = (
        "八、2 交易性金融资产\n\n截至 2025 年 12 月 31 日，本公司无交易性金融资产。\n\n"
        "附注说明：\n本期及上期交易性金融资产余额均为 0.00 元。\n审计师提示：\n若未来期间持有交易性金融资产，本附注需补充披露以下信息：\n1. 按投资品种分类"
    )
    st = FilterStats()
    assert _lines(deliverable_text_blocks(_note(text), stats=st)) == ["截至 2025 年 12 月 31 日，本公司无交易性金融资产。"]
    assert st.hint_tail_cut


@pytest.mark.parametrize(
    "line",
    [
        "【审计师提示：需补充信息】",
        "【审计师备注 - 待补充信息】",
        "审计师提示（需补充信息清单）：",
        "⚠️ 数据缺失提示：",
        "【重要提示：数据补充说明】",
        "编制说明：本附注依据《企业会计准则第 8 号——资产减值》编制。请根据实际审计底稿数据替换上述部分。",
        "4. 重要提示",
    ],
)
def test_hint_headers_cut_the_rest(line):
    text = f"本公司货币资金均为银行存款。\n\n{line}\n1. 请补充期末余额。\n2. 若存在受限资金，需说明。"
    assert _lines(deliverable_text_blocks(_note(text, code="八、1", title="货币资金"))) == ["本公司货币资金均为银行存款。"]


@pytest.mark.parametrize(
    "line",
    [
        "请提供上述数据后，我将为您生成最终版的附注正文。",
        "由于您未提供具体的财务数据，文中关键数据处已标注。",
        "若贵司存在境外经营实体，请补充以下具体数据以完善本附注：",
        "（注：以上文本为基于通用企业会计准则的标准模板。）",
        "注：请明确本公司 2025 年度采用的具体存货发出计价方法。",
        "若 2025 年度无资本化支出，本章节应注明：“本公司研究开发支出全部予以费用化。”",
        "[或：本公司记账本位币为美元。]",
        "[ ] 公司成立的具体日期、注册地。",
        "[待补充：具体风险描述]",
        "（说明存货的分类、取得和发出的计价方法。）",
        "（《企业数据资源相关会计处理暂行规定》：企业应当披露确定发出数据资源存货成本所采用的方法。）",
        "建议后续完善股东明细表。",
    ],
)
def test_guidance_and_ai_lines_are_dropped(line):
    text = f"本公司以人民币为记账本位币。\n{line}\n本公司会计年度自公历1月1日起至12月31日止。"
    assert _lines(deliverable_text_blocks(_note(text, code="四、记账本位币", title="记账本位币"))) == [
        "本公司以人民币为记账本位币。", "本公司会计年度自公历1月1日起至12月31日止。",
    ]


def test_bracket_guidance_spans_lines_until_closing():
    text = "存货按实际成本计价。\n【注：如为房地产开发企业，应采用下列披露：\n存货主要包括开发产品。\n为订立合同而发生的差旅费计入当期损益。】\n周转材料采用一次转销法。"
    assert _lines(deliverable_text_blocks(_note(text, code="四、存货", title="存货"))) == [
        "存货按实际成本计价。", "周转材料采用一次转销法。",
    ]


def test_inline_guidance_parenthetical_removed_and_placeholders_counted():
    st = FilterStats()
    text = "本公司营业期限自[XX]年至长期。（如未限定经营期限，请删除）\n本公司注册地址为 [详细地址]。"
    lines = _lines(deliverable_text_blocks(_note(text, code="一、1", title="公司基本情况"), stats=st))
    assert lines == ["本公司营业期限自[XX]年至长期。", "本公司注册地址为 [详细地址]。"]
    assert st.placeholders_left == 2


def test_legit_parentheses_and_notes_are_kept():
    text = "1年以内（含1年）的应收账款计提比例为5%。\n注：期末余额中无持本公司5%以上表决权股份的股东单位欠款。\n实收资本（或股本）期末余额为1.5亿元。"
    assert len(_lines(deliverable_text_blocks(_note(text, code="八、5", title="应收账款")))) == 3


def test_text_tables_dropped_when_structured_or_placeholder_and_intros_follow():
    table = "| 项目 | 期末 |\n| --- | --- |\n| 银行存款 | [待补充] |"
    text = f"1. 货币资金构成\n截至期末，货币资金构成如下：\n\n{table}\n\n本公司无受限资金。"
    st = FilterStats()
    lines = _lines(deliverable_text_blocks(_note(text, code="八、1", title="货币资金"), stats=st))
    assert lines == ["本公司无受限资金。"]  # 表删掉后「…如下：」与其上悬空小标题一并删
    assert st.dropped_tables == 1

    real = "| 项目 | 期末 |\n| --- | --- |\n| 银行存款 | 100.00 |"
    lines = _lines(deliverable_text_blocks(_note(f"构成如下：\n\n{real}", code="八、1", title="货币资金")))
    assert lines == ["构成如下：", "<表>"]
    with_struct = _note(f"构成如下：\n\n{real}", code="八、1", title="货币资金",
                        table_data={"headers": ["项目", "期末"], "rows": [{"label": "银行存款", "values": [100]}]})
    assert _lines(deliverable_text_blocks(with_struct)) == []  # 有结构化表：正文表重复，删


def test_jumble_line_from_old_import_is_dropped():
    text = "10\n存货\n10存货存货分类本期无此项业务。八、10 存货1. 存货分类\n本期无此项业务。"
    # 序号 / 标题粘连残片删掉；「本期无此项业务。」也不出具（无业务的项目整节不进交付件）
    assert _lines(deliverable_text_blocks(_note(text, code="八、10", title="存货"))) == []
    assert note_has_deliverable_content(_note(text, code="八、10", title="存货")) is False
    keep = "本期末存货均为库存商品。\n本期无此项业务。"
    assert _lines(deliverable_text_blocks(_note(keep, code="八、10", title="存货"))) == ["本期末存货均为库存商品。"]


def test_old_import_captions_and_paren_guidance_are_dropped():
    """旧导入（华氏）：正文里抄了模板表题 + 「本期无此项业务。」+ 跨行（…）编制指引 → 交付过滤后无内容。"""
    text = ("无形资产情况\n本期无此项业务。\n"
            "（①披露未办妥产权证书的土地使用权有关情况，说明原因和预计办结时间。\n"
            "②本公司使用寿命不确定的无形资产的判断依据。\n"
            "⑤本期发生以明显高于账面价值的价格出售无形资产交易的，应详细说明交易作价的基础和依据。）\n"
            "确认为无形资产的数据资源\n本期无此项业务。\n"
            "企业对数据资源进行评估且评估结果对企业财务报表具有重要影响的，应当披露评估依据等信息。）")
    note = _note(text, code="八、29", title="无形资产")
    structure = ("（1）无形资产情况", "确认为无形资产的数据资源")
    assert _lines(deliverable_text_blocks(note, structure_titles=structure)) == []
    assert note_has_deliverable_content(note, structure_titles=structure) is False


def test_has_deliverable_content_and_structured_tables():
    assert note_has_deliverable_content(_note("审计师提示：请补充全部数据。")) is False
    assert note_has_deliverable_content(_note("截至期末无余额。")) is True
    filled = {"headers": ["项目", "期末"], "rows": [{"label": "银行存款", "values": [5]}]}
    empty = {"headers": ["项目", "期末"], "rows": [{"label": "银行存款", "values": [None]}]}
    assert structured_tables_nonempty(_note("", table_data=filled)) is True
    assert structured_tables_nonempty(_note("", table_data=empty)) is False
    assert note_has_deliverable_content(_note("", table_data=filled)) is True


# ── 第二轮真实导出（重药安徽 2026-10-16）抓到的残留形态 ───────────────────────────────


@pytest.mark.parametrize(
    "line",
    [
        "具体构成明细：请提供库存现金、银行存款及短期投资的具体金额。",
        "4. 账龄分析：需按账龄（如 1 年以内、1-2 年等）列示应收票据的分布情况。",
        "受限资金说明：若存在使用受限的现金（如质押存款、保证金等），需单独列示并说明受限原因及金额。",
        "说明：3. 若数据缺失，请根据实际工商登记信息及股权架构补充上述表格中的具体数值。",
        "* （需补充：2025 年度末，本集团按预期信用损失模型计提的坏账准备具体金额及账龄分析数据。）",
        "可收回性评估：经审计师评估，该部分款项 [请补充：预计可全额收回]。",
        "4.应披露与持有待售的非流动资产或处置组有关的其他综合收益累计金额。】",
        "期末余额：[请补充金额] 元",
    ],
)
def test_second_round_guidance_lines_are_dropped(line):
    text = f"本公司应收票据均为银行承兑汇票。\n{line}\n本公司无已质押的应收票据。"
    assert _lines(deliverable_text_blocks(_note(text, code="八、4", title="应收票据"))) == [
        "本公司应收票据均为银行承兑汇票。", "本公司无已质押的应收票据。"]


def test_template_intro_cuts_the_sample_that_follows():
    text = ("截至 2025 年 12 月 31 日，公司应收票据期末余额为 20,209,198.18 元。\n"
            "若上述数据暂缺，建议先按以下标准模板表述，待数据齐备后替换：\n"
            "“截至 2025 年 12 月 31 日，公司应收票据期末余额为 [待补充] 元。”")
    st = FilterStats()
    assert _lines(deliverable_text_blocks(_note(text, code="八、4", title="应收票据"), stats=st)) == [
        "截至 2025 年 12 月 31 日，公司应收票据期末余额为 20,209,198.18 元。"]
    assert st.hint_tail_cut


def test_heading_whose_content_was_all_dropped_goes_with_it_but_list_items_stay():
    text = ("3. 重要披露事项（需补充信息）\n增加来源：需说明本期增加的投资性房地产来源。\n"
            "折旧政策：需补充投资性房地产的折旧方法。\n"
            "1、本公司无受限资金\n（注：若有受限资金，请补充明细。）\n"
            "2、其他货币资金为保证金")
    assert _lines(deliverable_text_blocks(_note(text, code="八、1", title="货币资金"))) == [
        "1、本公司无受限资金", "2、其他货币资金为保证金"]


def test_text_table_with_only_zeros_is_dropped():
    table = "| 项目 | 期末余额 | 期初余额 |\n| --- | --- | --- |\n| 在建工程 | 0.00 | 0.00 |\n| 合计 | 0.00 | 0.00 |"
    text = f"截至 2025 年 12 月 31 日，本公司在建工程账面余额为 0.00 元。\n\n{table}"
    st = FilterStats()
    assert _lines(deliverable_text_blocks(_note(text, code="四、在建工程", title="在建工程"), stats=st)) == [
        "截至 2025 年 12 月 31 日，本公司在建工程账面余额为 0.00 元。"]
    assert st.dropped_tables == 1


def test_chapter_title_copied_into_text_is_dropped_via_extra_titles():
    from app.services.note_deliverable_filter import make_block_filter
    from app.services.note_text_word_render import _as_html, _parse

    note = _note("九、或有事项\n截至 2025 年 12 月 31 日，本公司无需要披露的重大或有事项。", code="九、1、或有负债",
                 title="或有负债")
    blocks = _parse(_as_html(note.text_content))
    assert _lines(make_block_filter(note)(blocks))[0] == "九、或有事项"  # 不给章标题时留着
    assert _lines(make_block_filter(note, extra_titles=("或有事项",))(blocks)) == [
        "截至 2025 年 12 月 31 日，本公司无需要披露的重大或有事项。"]


def test_legit_sentences_with_ying_shou_and_labels_are_kept():
    text = ("说明：应收账款按账龄披露如下：\n\n| 账龄 | 期末 |\n| --- | --- |\n| 1年以内 | 100.00 |\n\n"
            "信用风险：主要源于交易对手方未能履行合同义务。")
    assert _lines(deliverable_text_blocks(_note(text, code="八、5", title="应收账款"))) == [
        "说明：应收账款按账龄披露如下：", "<表>", "信用风险：主要源于交易对手方未能履行合同义务。"]


def test_template_like_lines_and_trailing_headings_are_dropped():
    text = ("截至 2025 年 12 月 31 日，其他应收款账面余额为 88,769,805.29 元。\n"
            "款项性质期末余额押金及保证金[需补充数据][需补充数据]备用金[需补充数据][需补充数据]\n"
            "（1）需补充“账面余额”与“坏账准备”的具体数值。\n"
            "本期核销其他应收款 [需补充] 元。\n"
            "（5）其他说明")
    st = FilterStats()
    assert _lines(deliverable_text_blocks(_note(text, code="八、9", title="其他应收款"), stats=st)) == [
        "截至 2025 年 12 月 31 日，其他应收款账面余额为 88,769,805.29 元。", "本期核销其他应收款 [需补充] 元。"]
    assert st.placeholders_left == 1  # 单个占位的句子保留并计数（出具前补全）


def test_lines_repeating_template_subheadings_are_dropped():
    from app.services.note_deliverable_filter import make_block_filter
    from app.services.note_text_word_render import _as_html, _parse

    note = _note("1. 预付款项按账龄列示\n截至期末，预付款项账龄均在一年以内。", code="八、7", title="预付款项")
    blocks = _parse(_as_html(note.text_content))
    assert _lines(make_block_filter(note, structure_titles=("（1）预付款项按账龄列示",))(blocks)) == [
        "截至期末，预付款项账龄均在一年以内。"]


def test_structured_table_with_only_zero_values_is_blank_for_delivery():
    from app.services.note_deliverable_filter import table_blank_for_delivery

    zeros = [{"label": "1年以内", "values": [0, "0.00", None]}, {"label": "合计", "values": [0], "is_total": True}]
    assert table_blank_for_delivery(zeros) is True  # 模块页口径（无列定义时 0 算填了）这里按交付口径算空
    # 合计行有数（公式推送的合计行兜底）：有业务，出具（spec note-pull-header-formula-closure R5）
    pushed = [{"label": "1年以内", "values": [0, None]}, {"label": "合计", "values": [5], "is_total": True}]
    assert table_blank_for_delivery(pushed) is False
    assert table_blank_for_delivery([{"label": "合计", "values": ["—"], "is_total": True}]) is True
    assert table_blank_for_delivery([{"label": "1年以内", "values": [0, "12.50"]}]) is False
    assert table_blank_for_delivery([{"label": "单位", "values": ["银行承兑汇票"]}]) is False


# ── 【…】编制指引 / 补充清单（2026-10-16 Phase D 复验：四项目交付件 PDF 仍见 26 处「【」）────────────


def test_supplement_hint_label_and_its_list_items_dropped():
    """和平「应付账款」：【需补充信息】+ 待填账龄清单 / 问句清单删除，其后的正文小节保留。"""
    text = (
        "截至 2025 年 12 月 31 日，本公司应付账款期末余额为人民币 267,308,976.77 元。\n\n"
        "2. 账龄分析\n【需补充信息】：根据《企业会计准则》披露要求，需补充应付账款的账龄结构数据（如：1 年以内、1-2 年）。\n"
        "*   1 年以内：[待补充金额] 元，占比 [待补充]%\n*   合计：267,308,976.77 元\n\n"
        "4. 应付账款变动分析\n2025 年度，应付账款期末余额较期初增加 36,847,280.52 元。\n"
        "【需补充信息】：\n* 是否存在涉及诉讼、仲裁的应付账款？\n* 是否存在关联方应付账款？如有，需单独披露关联方名称及金额。"
    )
    st = FilterStats()
    out = _lines(deliverable_text_blocks(_note(text, code="八、37", title="应付账款"), stats=st))
    assert out == [
        "截至 2025 年 12 月 31 日，本公司应付账款期末余额为人民币 267,308,976.77 元。",
        "4. 应付账款变动分析",
        "2025 年度，应付账款期末余额较期初增加 36,847,280.52 元。",
    ]
    assert not st.hint_tail_cut  # 只删清单，不截断本章其后内容


def test_supplement_hint_list_stops_at_paragraph_boundary():
    text = (
        "【需补充信息】\n请提供以下具体数据以完善披露：\n*   持有待售资产的具体类别（如：固定资产、无形资产等）。\n"
        "*   预计出售时间及交易对手方（如已确定）。\n\n2. 终止经营\n\n终止经营是指企业已处置或划分为持有待售的组成部分。"
    )
    out = _lines(deliverable_text_blocks(_note(text, code="四、持有待售及终止经营", title="持有待售及终止经营")))
    assert out == ["2. 终止经营", "终止经营是指企业已处置或划分为持有待售的组成部分。"]


@pytest.mark.parametrize(
    "guide",
    [
        "【或者，按地理区域、产品类型、客户评级、担保物以及客户类型（如批发和零售）划分组合】",
        "【《关于严格执行企业会计准则 切实做好企业2025年年报工作的通知》（财会〔2025〕号）要求企业披露】",
        "【存在下列情况的，可能说明企业是结构化主体的发起人：\n（1）企业的名称出现在结构化主体的名称中；\n（2）企业为结构化主体提供担保。】",
    ],
)
def test_long_bracket_guidance_lines_dropped_even_across_lines(guide):
    text = f"本公司无此类结构化主体。\n\n{guide}\n\n其他说明：无。"
    assert _lines(deliverable_text_blocks(_note(text, code="十、3", title="在未纳入合并财务报表范围的结构化主体中的权益"))) == [
        "本公司无此类结构化主体。", "其他说明：无。"]


def test_inline_long_bracket_stripped_closed_and_unclosed():
    text = (
        "其他事项调整的内容和原因。【包括其他调整事项的陈述、调整原因以及调整方法等内容】\n"
        "本财务报表均以历史成本为计量基础。【持有待售的非流动资产，按公允价值减去出售费用后的净额\n"
        "与原账面价值孰低计量。】\n下一句正文。"
    )
    out = _lines(deliverable_text_blocks(_note(text, code="四、2", title="会计基础")))
    assert out == ["其他事项调整的内容和原因。", "本财务报表均以历史成本为计量基础。", "下一句正文。"]


def test_supplement_hint_list_does_not_eat_next_paragraph_bullets():
    """补充清单只删同段的清单项：空行之后另起一段的「* …」是正文列表。"""
    text = "【需补充信息】：\n* 是否存在关联方应付账款？\n\n* 本公司持有待售资产为闲置设备一台。"
    out = _lines(deliverable_text_blocks(_note(text, code="八、12", title="持有待售资产")))
    assert len(out) == 1 and out[0].endswith("本公司持有待售资产为闲置设备一台。")  # 列表记号渲染与否不在此判


def test_long_bracket_at_line_start_keeps_following_text():
    text = "【以下内容仅适用于存在结构化主体的企业，不适用的请删除】本公司无此类结构化主体。"
    assert _lines(deliverable_text_blocks(_note(text, code="十、3", title="结构化主体"))) == ["本公司无此类结构化主体。"]


def test_short_bracket_is_a_placeholder_kept_and_counted():
    st = FilterStats()
    text = "本公司会计核算以权责发生制为基础。除某些金融工具【和投资性房地产】外，本财务报表均以历史成本为计量基础。"
    assert _lines(deliverable_text_blocks(_note(text, code="四、2", title="会计基础"), stats=st)) == [text]
    assert st.placeholders_left == 1


# ── 占位正文判定（spec consol-note-header-library-and-node-reaggregate R7.3：上年导入 / 继承共用） ──


@pytest.mark.parametrize("text", [
    "本期无此项业务。", "本期无此项业务", "  本期无此项业务。\n", "不适用。", "本年无此类业务。",
    "报告期内无此业务", "* 本期无此项业务。", "<p>本期无此项业务。</p>", "本期无此项业务。\n\n不适用。",
])
def test_placeholder_text_is_recognised(text):
    from app.services.note_deliverable_filter import is_placeholder_text

    assert is_placeholder_text(text)


@pytest.mark.parametrize("text", [
    "", None, "   ", "截至 2025 年 12 月 31 日，本公司无交易性金融资产。", "本期无此项业务。期末余额 100 元。",
    "本期无此项业务。\n本公司本期新增应收票据 300 万元。", "<p>上年货币资金说明正文。</p>", "本期无此情形。",
])
def test_real_text_is_not_placeholder(text):
    from app.services.note_deliverable_filter import is_placeholder_text

    assert not is_placeholder_text(text)
