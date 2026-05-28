"""A.0.6 验证：Jinja ref() 函数 + make_jinja_ref_function 闭包."""

from jinja2 import Environment, BaseLoader

from app.services.note_section_numbering_service import (
    jinja_ref,
    make_jinja_ref_function,
)


def test_jinja_ref_found():
    nums = {"section_cash": "一、（一）", "section_ar": "一、（二）"}
    assert jinja_ref("section_cash", nums) == "一、（一）"
    assert jinja_ref("section_ar", nums) == "一、（二）"


def test_jinja_ref_not_found():
    nums = {"section_cash": "一、（一）"}
    result = jinja_ref("unknown_id", nums)
    assert "未知章节" in result
    assert "unknown_id" in result


def test_make_jinja_ref_function_in_template():
    nums = {"section_cash": "五、（一）", "section_fa": "八、（三）2."}
    env = Environment(loader=BaseLoader())
    env.globals["ref"] = make_jinja_ref_function(nums)

    tmpl = env.from_string("详见 {{ ref('section_cash') }}")
    assert tmpl.render() == "详见 五、（一）"

    tmpl2 = env.from_string("固定资产详见 {{ ref('section_fa') }}。")
    assert tmpl2.render() == "固定资产详见 八、（三）2.。"


def test_make_jinja_ref_function_unknown():
    nums = {}
    env = Environment(loader=BaseLoader())
    env.globals["ref"] = make_jinja_ref_function(nums)
    tmpl = env.from_string("{{ ref('no_such') }}")
    assert "[未知章节: no_such]" in tmpl.render()
