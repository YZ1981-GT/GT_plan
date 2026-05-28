"""单测 — CI-11：Jinja 模板必有变量声明（Sprint A.4.6 验收）.

Spec:    .kiro/specs/note-dynamic-tables-and-template-inheritance/ Sprint A.4
Design:  D7 文字段落 Jinja 渲染 — CI-11 卡点
Reqs:    所有 Jinja 段落模板必须声明用到的变量（避免 strict 模式漏变量崩）

CI-11 契约（铁律）：
- ``extract_template_variables`` 能把 ``{{ var }}`` / ``{% if var %}`` /
  ``{% for x in var %}`` 等所有引用变量找出来
- strict 模式下未声明变量必须抛 ``UndefinedError``
- 非 strict 模式下未声明变量按 ChainableUndefined 渲染为空字符串
- 自带 filter（format_amount/cn_number/date_cn）和全局函数（ref）不算变量
"""

from __future__ import annotations

import pytest
from jinja2 import UndefinedError

from app.services.note_text_template_engine import (
    extract_template_variables,
    render_text_paragraph,
)


class TestCI11VariableDeclarations:
    """CI-11: 所有 Jinja 段落模板必须声明用到的变量."""

    # ---- extract_template_variables 提取面 ----

    def test_extract_simple_variable(self):
        assert extract_template_variables("{{ company_name }}") == {"company_name"}

    def test_extract_filter_variable(self):
        # filter 名（format_amount）不算变量
        assert extract_template_variables(
            "{{ amount | format_amount }}"
        ) == {"amount"}

    def test_extract_conditional_variable(self):
        result = extract_template_variables(
            "{% if is_listed %}上市公司{% endif %}"
        )
        assert "is_listed" in result

    def test_extract_for_loop_variable(self):
        result = extract_template_variables(
            "{% for s in subsidiaries %}{{ s.name }}{% endfor %}"
        )
        assert "subsidiaries" in result
        # 循环变量 s 不在外部空间
        assert "s" not in result

    def test_extract_nested_attribute(self):
        result = extract_template_variables("{{ user.profile.name }}")
        assert result == {"user"}

    def test_extract_filter_chain(self):
        result = extract_template_variables(
            "{{ amount | format_amount | upper }}"
        )
        assert result == {"amount"}

    def test_extract_ref_arg_is_literal_not_var(self):
        # ref() 是全局函数，参数 'section_cash' 是字面量
        result = extract_template_variables("{{ ref('section_cash') }}")
        # ref 是全局名，不是模板变量
        assert "section_cash" not in result

    def test_extract_multiple_vars(self):
        tmpl = (
            "{{ company_name }}于{{ inception_date | date_cn }}成立，"
            "{% if is_listed %}股票代码{{ stock_code }}{% endif %}"
        )
        result = extract_template_variables(tmpl)
        assert result == {"company_name", "inception_date", "is_listed", "stock_code"}

    def test_extract_empty_template(self):
        assert extract_template_variables("") == set()
        assert extract_template_variables("纯文本无变量") == set()

    # ---- strict 模式契约 ----

    def test_strict_mode_raises_on_undefined(self):
        """CI-11: strict 模式下未声明变量必须抛 UndefinedError."""
        with pytest.raises(UndefinedError):
            render_text_paragraph(
                "本公司{{ never_declared }}。",
                {},
                strict=True,
            )

    def test_strict_mode_passes_when_all_declared(self):
        out = render_text_paragraph(
            "本公司{{ company_name }}。",
            {"company_name": "X"},
            strict=True,
        )
        assert out == "本公司X。"

    def test_lenient_mode_substitutes_empty(self):
        """非 strict 模式下未声明变量 → 空字符串."""
        out = render_text_paragraph(
            "本公司{{ never_declared }}。",
            {},
            strict=False,
        )
        assert out == "本公司。"

    def test_template_with_extracted_vars_renders_strict(self):
        """提取到的所有变量都填上，strict 模式必通过（CI-11 闭环）."""
        tmpl = (
            "{{ company_name }}于{{ inception_date | date_cn }}注册，"
            "下设子公司{{ subsidiary_count | cn_number }}家。"
        )
        required_vars = extract_template_variables(tmpl)
        # 用 extract 出来的全集去填，不漏一个
        all_filled = {var: "占位" if var != "subsidiary_count" else 3 for var in required_vars}
        all_filled["inception_date"] = "2020-01-01"
        out = render_text_paragraph(tmpl, all_filled, strict=True)
        assert "占位" in out  # company_name
        assert "2020年1月1日" in out
        assert "三家" in out
