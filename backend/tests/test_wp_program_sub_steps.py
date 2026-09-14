"""子程序步骤解析单测"""

from app.services.wp_program_sub_steps import enrich_program_row, parse_sub_steps


def test_parse_multiline_d4_style():
    content = (
        "获取或编制主营业务收入明细表，并完成以下工作：\n"
        "（1）复核加计正确，将总金额与总账、明细账合计数核对相符；\n"
        "（2）检查以非记账本位币结算的营业收入的折算汇率及折算是否正确。"
    )
    parent, steps = parse_sub_steps(content)
    assert "主营业务收入" in parent
    assert len(steps) == 2
    assert steps[0]["no"] == 1
    assert "复核加计" in steps[0]["text"]


def test_parse_inline_g4_style():
    content = (
        "获取或编制债权投资明细表，完成以下工作："
        "（1）检查债权投资初始确认是否正确；"
        "（2）与总账核对相符；"
        "（3）编制审定表。"
    )
    parent, steps = parse_sub_steps(content)
    assert "债权投资" in parent
    assert len(steps) == 3
    assert steps[1]["no"] == 2


def test_enrich_program_row_splits_desc():
    row = {
        "program_no": 1,
        "program_desc": "总体程序：（1）步骤一；（2）步骤二。",
    }
    out = enrich_program_row(row)
    assert out["sub_steps"]
    assert out["program_desc"] == "总体程序"
    assert len(out["sub_steps"]) == 2
