"""Sprint A.4.7 — 附注文字段落 Jinja 渲染引擎单元测试（18 用例）.

Spec:    .kiro/specs/note-dynamic-tables-and-template-inheritance/ Sprint A.4
Design:  D7 文字段落 Jinja 渲染（v0.3 新增）
Reqs:    A.4.1 / A.4.6（CI-11）/ A.4.7
Module:  app.services.note_text_template_engine
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from jinja2 import UndefinedError
from jinja2.exceptions import TemplateSyntaxError

from app.services.note_text_template_engine import (
    extract_template_variables,
    format_amount,
    format_date_cn,
    get_jinja_env,
    jinja_cn_number_filter,
    render_text_paragraph,
)


# ---------------------------------------------------------------------------
# format_amount filter（4 用例）
# ---------------------------------------------------------------------------


class TestFormatAmount:
    def test_int_and_float_basic(self):
        assert format_amount(1234567) == "1,234,567.00"
        assert format_amount(1234567.89) == "1,234,567.89"
        assert format_amount(0) == "0.00"

    def test_decimal_preserves_2_decimals(self):
        assert format_amount(Decimal("1234567.89")) == "1,234,567.89"
        # 大金额保持千分位
        assert format_amount(Decimal("12345678901234.56")) == "12,345,678,901,234.56"

    def test_none_and_string(self):
        assert format_amount(None) == ""
        assert format_amount("") == ""
        # 数字字符串
        assert format_amount("1234567.89") == "1,234,567.89"
        assert format_amount("1,234,567.89") == "1,234,567.89"

    def test_non_numeric_string_passes_through(self):
        # CN 字面量不抛错，原样返回
        assert format_amount("一千两百") == "一千两百"
        # 占位符也不抛
        assert format_amount("N/A") == "N/A"


# ---------------------------------------------------------------------------
# cn_number filter（2 用例）
# ---------------------------------------------------------------------------


class TestCnNumberFilter:
    def test_small_and_medium(self):
        assert jinja_cn_number_filter(1) == "一"
        assert jinja_cn_number_filter(10) == "十"
        assert jinja_cn_number_filter(35) == "三十五"
        assert jinja_cn_number_filter(99) == "九十九"

    def test_overflow_and_invalid(self):
        # 100+ 回退原数字
        assert jinja_cn_number_filter(100) == "100"
        # None / 非数 → ""
        assert jinja_cn_number_filter(None) == ""
        assert jinja_cn_number_filter("abc") == ""


# ---------------------------------------------------------------------------
# date_cn filter（3 用例）
# ---------------------------------------------------------------------------


class TestDateCnFilter:
    def test_date_and_datetime_obj(self):
        assert format_date_cn(date(2025, 12, 31)) == "2025年12月31日"
        assert format_date_cn(datetime(2025, 1, 5, 23, 59)) == "2025年1月5日"

    def test_iso_string(self):
        assert format_date_cn("2025-12-31") == "2025年12月31日"
        assert format_date_cn("2025-12-31T00:00:00") == "2025年12月31日"
        assert format_date_cn("2025-12-31T08:30:00+08:00") == "2025年12月31日"

    def test_invalid_returns_empty(self):
        assert format_date_cn(None) == ""
        assert format_date_cn("") == ""
        assert format_date_cn("not-a-date") == ""


# ---------------------------------------------------------------------------
# render_text_paragraph（5 用例）
# ---------------------------------------------------------------------------


class TestRenderTextParagraph:
    def test_simple_variable_substitution(self):
        out = render_text_paragraph(
            "本公司是{{ company_name }}。",
            {"company_name": "首汽租车"},
        )
        assert out == "本公司是首汽租车。"

    def test_if_else_branch(self):
        tmpl = (
            "{% if is_listed %}本公司是上市公司。"
            "{% else %}本公司是非上市公司。{% endif %}"
        )
        assert render_text_paragraph(tmpl, {"is_listed": True}) == "本公司是上市公司。"
        assert (
            render_text_paragraph(tmpl, {"is_listed": False})
            == "本公司是非上市公司。"
        )

    def test_filter_chain_combination(self):
        tmpl = (
            "注册资本{{ capital | format_amount }}元，"
            "成立日期{{ inception_date | date_cn }}，"
            "下设子公司{{ count | cn_number }}家。"
        )
        out = render_text_paragraph(
            tmpl,
            {
                "capital": Decimal("50000000.00"),
                "inception_date": "2018-06-15",
                "count": 5,
            },
        )
        assert out == (
            "注册资本50,000,000.00元，"
            "成立日期2018年6月15日，"
            "下设子公司五家。"
        )

    def test_ref_function_injection(self):
        rendered_numbers = {"section_cash": "五、（一）"}
        out = render_text_paragraph(
            "现金详见{{ ref('section_cash') }}。",
            {},
            rendered_numbers=rendered_numbers,
        )
        assert out == "现金详见五、（一）。"

    def test_strict_undefined_raises(self):
        with pytest.raises(UndefinedError):
            render_text_paragraph(
                "本公司{{ never_defined }}。",
                {"company_name": "X"},
                strict=True,
            )

    def test_lenient_mode_substitutes_chainable_undefined(self):
        # ChainableUndefined 渲染为空字符串
        out = render_text_paragraph(
            "本公司{{ never_defined }}。",
            {},
            strict=False,
        )
        assert out == "本公司。"


# ---------------------------------------------------------------------------
# extract_template_variables（3 用例）
# ---------------------------------------------------------------------------


class TestExtractTemplateVariables:
    def test_simple_variable(self):
        assert extract_template_variables("{{ company_name }}") == {"company_name"}

    def test_with_filter(self):
        assert extract_template_variables(
            "{{ amount | format_amount }} 元 / {{ d | date_cn }}"
        ) == {"amount", "d"}

    def test_conditional_and_loop(self):
        tmpl = (
            "{% if is_listed %}{{ stock_code }}{% endif %}"
            "{% for s in subsidiaries %}{{ s.name }}{% endfor %}"
        )
        result = extract_template_variables(tmpl)
        assert "is_listed" in result
        assert "stock_code" in result
        assert "subsidiaries" in result


# ---------------------------------------------------------------------------
# Sanity：env 工厂 + ref 占位（额外保险）
# ---------------------------------------------------------------------------


class TestEnvSanity:
    def test_default_env_has_filters_and_ref_placeholder(self):
        env = get_jinja_env()
        assert "format_amount" in env.filters
        assert "cn_number" in env.filters
        assert "date_cn" in env.filters
        # 没注入 rendered_numbers，应该是占位 ref
        out = env.from_string("{{ ref('xyz') }}").render()
        assert "未注入序号" in out

    def test_env_respects_trim_blocks(self):
        # trim_blocks + lstrip_blocks 让块结构不引入冗余空白
        tmpl = (
            "A\n"
            "{% if x %}\n"
            "B\n"
            "{% endif %}\n"
            "C"
        )
        out = render_text_paragraph(tmpl, {"x": True}, strict=False)
        assert out == "A\nB\nC"
