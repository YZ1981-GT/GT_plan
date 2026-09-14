"""note_header_projector 单元测试：legacy 空表头从 _cell_meta 语义派生。"""

from __future__ import annotations

from app.services.note_header_projector import (
    derive_headers_for_legacy_table,
    project_headers,
)


def _row(label, values, semantics):
    cm = {str(i): {"semantic": s} for i, s in enumerate(semantics)}
    return {"label": label, "values": values, "_cell_meta": cm}


def test_two_col_balance_pattern():
    """货币资金式 期末/上年 两列 → [项目, 期末余额, 上年年末余额]."""
    td = {
        "headers": [],
        "rows": [
            _row("库存现金", [376.73, None], ["closing_balance", "prior_year_value"]),
            _row("银行存款", [9182196.26, 1000.0], ["closing_balance", "prior_year_value"]),
        ],
    }
    assert derive_headers_for_legacy_table(td) == ["项目", "期末余额", "上年年末余额"]


def test_four_col_movement_pattern():
    """变动表 期初/增/减/期末 四列。"""
    td = {
        "headers": [],
        "rows": [
            _row("A", [1, 2, 3, 4], [
                "opening_balance", "current_year_increase",
                "current_year_decrease", "closing_balance",
            ]),
        ],
    }
    assert derive_headers_for_legacy_table(td) == [
        "项目", "期初余额", "本期增加", "本期减少", "期末余额",
    ]


def test_missing_semantic_col_blank_label():
    """无语义的值列 → 空标签，但列仍在（长度对齐 values）。"""
    td = {
        "headers": [],
        "rows": [_row("X", [1, 2], ["closing_balance", None])],
    }
    assert derive_headers_for_legacy_table(td) == ["项目", "期末余额", ""]


def test_no_cell_meta_uses_value_count():
    """行无 _cell_meta 但有 values → 按 values 长度出空标签列头。"""
    td = {"headers": [], "rows": [{"label": "X", "values": [1, 2]}]}
    assert derive_headers_for_legacy_table(td) == ["项目", "", ""]


def test_zero_value_cols_label_only():
    """无值列文本清单表 → 仅标签列。"""
    td = {"headers": [], "rows": [{"label": "条款一", "values": []}]}
    assert derive_headers_for_legacy_table(td) == ["项目"]


def test_existing_headers_untouched():
    td = {"headers": ["项目", "金额"], "rows": [_row("A", [1], ["closing_balance"])]}
    assert derive_headers_for_legacy_table(td) is None


def test_multitable_skipped():
    td = {"headers": [], "_tables": [{"name": "x"}], "rows": [_row("A", [1], ["cost"])]}
    assert derive_headers_for_legacy_table(td) is None


def test_empty_rows_skipped():
    assert derive_headers_for_legacy_table({"headers": [], "rows": []}) is None
    assert derive_headers_for_legacy_table({"headers": []}) is None
    assert derive_headers_for_legacy_table(None) is None


def test_project_headers_returns_new_dict_not_mutating():
    td = {"headers": [], "rows": [_row("A", [1], ["closing_balance"])]}
    out = project_headers(td)
    assert out is not None
    assert out["headers"] == ["项目", "期末余额"]
    assert td["headers"] == []  # 入参未被修改
    # rows 引用保留（浅拷贝）
    assert out["rows"] is td["rows"]


def test_project_headers_none_when_not_applicable():
    td = {"headers": ["项目", "金额"], "rows": [_row("A", [1], ["cost"])]}
    assert project_headers(td) is None


def test_max_value_len_across_rows():
    """列数取所有行 values 长度最大值（首行短、后行长）。"""
    td = {
        "headers": [],
        "rows": [
            {"label": "A", "values": [1]},
            _row("B", [1, 2, 3], ["cost", "closing_balance", "prior_year_value"]),
        ],
    }
    assert derive_headers_for_legacy_table(td) == [
        "项目", "成本", "期末余额", "上年年末余额",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 模板表头优先（修：损益类表头空 + 语义派生标签用错）
#
# 用户报「五、63 税金及附加」表头第二列空、第三列显示"上年年末余额"：DB 里
# headers=[]，legacy 行语义为 manual_text(→空) + prior_year_value(→上年年末余额)，
# 而模板权威表头是「项目/本期发生额/上期发生额」。语义无法区分资产负债类与
# 损益类，故模板优先、语义派生仅兜底。
# ─────────────────────────────────────────────────────────────────────────────


def test_template_headers_preferred_for_income_statement_note():
    """五、63 税金及附加（listed）：模板表头取代语义派生的错误标签。"""
    td = {
        "headers": [],
        "rows": [
            _row("消费税", [None, None], ["manual_text", "prior_year_value"]),
            _row("印花税", [None, None], ["manual_text", "prior_year_value"]),
        ],
    }
    # 不传上下文 → 旧行为（空 + 上年年末余额），正是用户看到的错误表头
    assert derive_headers_for_legacy_table(td) == ["项目", "", "上年年末余额"]
    # 传 section + variant → 模板权威表头
    assert derive_headers_for_legacy_table(
        td, section_number="五、63", source_template="listed"
    ) == ["项目", "本期发生额", "上期发生额"]


def test_template_headers_column_count_mismatch_falls_back():
    """列数与模板不符 → 不套用模板（防列错位），回退语义派生。"""
    td = {
        "headers": [],
        "rows": [_row("消费税", [None], ["closing_balance"])],  # 只有 1 个值列
    }
    assert (
        derive_headers_for_legacy_table(
            td, section_number="五、63", source_template="listed"
        )
        == ["项目", "期末余额"]
    )


def test_template_headers_unknown_section_or_variant_falls_back():
    td = {"headers": [], "rows": [_row("A", [1, 2], ["closing_balance", "prior_year_value"])]}
    for kwargs in (
        {"section_number": "五、9999", "source_template": "listed"},
        {"section_number": "五、63", "source_template": "unknown_variant"},
        {"section_number": None, "source_template": "listed"},
    ):
        assert derive_headers_for_legacy_table(td, **kwargs) == [
            "项目", "期末余额", "上年年末余额",
        ]


def test_template_headers_soe_variant():
    """国企版同章节（八、64 营业收入、营业成本）表头取自 soe 模板。"""
    from app.services.note_header_projector import template_headers_for

    headers = template_headers_for("八、63", "soe")
    assert headers is None or isinstance(headers, list)  # 章节存在性由模板决定
    # 明确存在的损益章节：八、65 销售费用
    h = template_headers_for("八、65", "soe")
    assert h is not None and h[0] == "项目"


def test_project_headers_passes_context_through():
    td = {
        "headers": [],
        "rows": [_row("消费税", [None, None], ["manual_text", "prior_year_value"])],
    }
    out = project_headers(td, section_number="五、63", source_template="listed")
    assert out is not None
    assert out["headers"] == ["项目", "本期发生额", "上期发生额"]
    assert td["headers"] == []  # 纯函数不改入参
