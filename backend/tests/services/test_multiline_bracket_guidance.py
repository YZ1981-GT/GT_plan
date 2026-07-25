"""跨段/跨行括号指引块合并 — 修复「提示内容漏进附注正文文本框」缺陷。

问题：货币资金等模板的 `【提示：… (1)… (2)…】` 被拆成 text_sections 多个数组元素
（或单串内含 `\\n`），而 `is_guidance_paragraph` 只认首尾同段成对的括号段，导致整块
指引漏进 substantive（可编辑正文），未归入 guidance（编制提示）。

修复：`_merge_bracket_blocks` 先把未闭合的括号块合并为单段再分流。
"""

from __future__ import annotations

from app.services.disclosure_engine import (
    classify_template_content,
    identify_guidance,
    is_guidance_paragraph,
    _merge_bracket_blocks,
)


# 货币资金（listed）真实 text_sections（提示块被拆成多个数组元素）
CASH_TEXT_SECTIONS = [
    "（外币信息，在“附注五、81、外币货币性项目”中披露）",
    "【提示：",
    "（1）根据《企业会计准则解释第15号》（财会〔2021〕35号），成员单位可以在“货币资金”项目之下增设“其中：存放财务公司款项”项目单独列示。",
    "（2）企业持有由中国人民银行发行的数字人民币的，可以增设“数字货币”二级科目进行核算，在资产负债表中将其列报在“货币资金”项目。】",
    "期末，本公司不存在抵押、质押或冻结、或存放在境外且资金汇回受到限制的款项。",
    "（披露因抵押、质押或冻结等对使用有限制的款项，以及存放在境外的款项总额。）",
    "【提示-关于存款利息的披露：",
    "（1）银行存款包括应计利息：指基于实际利率法计提的应计但未到付息期的银行存款利息。",
    "（2）可以在表格下方增加说明：银行存款中含应计利息XXX元。",
    "（3）这部分利息不属于“现金及现金等价物”。】",
]


class TestMergeBracketBlocks:
    def test_multi_element_block_merged_into_single_paragraph(self):
        merged = _merge_bracket_blocks(CASH_TEXT_SECTIONS)
        # 两个提示块各合并为 1 段
        tip_blocks = [p for p in merged if p.startswith("【提示")]
        assert len(tip_blocks) == 2
        assert tip_blocks[0].startswith("【提示：")
        assert tip_blocks[0].rstrip().endswith("】")
        assert "（2）企业持有" in tip_blocks[0]
        # 合并后可被判为指引
        assert is_guidance_paragraph(tip_blocks[0])
        assert is_guidance_paragraph(tip_blocks[1])

    def test_multiline_single_string_block_merged(self):
        """单个 text_section 内含 \\n 的提示块（soe 风格）同样合并。"""
        merged = _merge_bracket_blocks([
            "【提示：",
            "1、承租人确认的租赁负债发生的利息费用适用借款费用准则。",
            "2、相关增值税税额不属于租赁付款额的范畴。】",
        ])
        assert len(merged) == 1
        assert merged[0].startswith("【提示：") and merged[0].rstrip().endswith("】")

    def test_balanced_and_plain_paragraphs_passthrough(self):
        merged = _merge_bracket_blocks([
            "（注：单行完整指引。）",
            "本公司执行企业会计准则。",
        ])
        assert merged == ["（注：单行完整指引。）", "本公司执行企业会计准则。"]

    def test_unterminated_block_not_swallowing_following_text(self):
        """残缺（无闭合】）→ 逐段原样输出，不吞并后续正文（零回归）。"""
        merged = _merge_bracket_blocks([
            "【提示：缺失闭合",
            "本公司实质正文不应被吞并。",
        ])
        assert "本公司实质正文不应被吞并。" in merged


class TestCashGuidanceExtraction:
    def test_single_table_guidance_extracted_substantive_clean(self):
        """单表：两个提示块 + 两段(…)全部归 guidance_text，正文仅剩实质叙述。"""
        substantive, section_guidance, per_table = classify_template_content(
            CASH_TEXT_SECTIONS, None, [{"name": "货币资金"}],
        )
        assert per_table == {}
        # 正文仅保留真正可编辑的实质叙述
        assert substantive == "期末，本公司不存在抵押、质押或冻结、或存放在境外且资金汇回受到限制的款项。"
        # 提示块进入编制提示
        assert section_guidance is not None
        assert "【提示：" in section_guidance
        assert "【提示-关于存款利息的披露：" in section_guidance
        assert "数字货币" in section_guidance
        # 正文里不再混入任何提示内容
        assert "提示" not in (substantive or "")
        assert "数字货币" not in (substantive or "")

    def test_multi_table_guidance_goes_per_table(self):
        """多表：提示块归当前表 guidance，正文仍归章节级 text_content。"""
        substantive, section_guidance, per_table = classify_template_content(
            CASH_TEXT_SECTIONS, None,
            [{"name": "货币资金"}, {"name": "受限制的货币资金明细"}],
        )
        assert section_guidance is None
        assert 0 in per_table
        assert "【提示：" in per_table[0]
        assert substantive == "期末，本公司不存在抵押、质押或冻结、或存放在境外且资金汇回受到限制的款项。"


class TestExistingNoteMigration:
    def test_identify_guidance_splits_merged_content(self):
        """存量迁移：text_content 里以 \\n\\n 分段的提示块被拆到 guidance。"""
        text_content = "\n\n".join(CASH_TEXT_SECTIONS)
        result = identify_guidance(text_content)
        assert result is not None
        guidance, remaining = result
        assert "【提示：" in guidance
        assert "【提示-关于存款利息的披露：" in guidance
        assert remaining.strip() == "期末，本公司不存在抵押、质押或冻结、或存放在境外且资金汇回受到限制的款项。"
        assert "提示" not in remaining
