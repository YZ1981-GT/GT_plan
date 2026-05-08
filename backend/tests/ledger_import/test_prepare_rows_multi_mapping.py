"""验证 prepare_rows_with_raw_extra 多列映射到同一 standard_field 时不覆盖非空值。

触发场景（真实数据 YG36 序时账）：
- "核算维度"列 = "客户:041108,重庆医药..." 
- "主表项目"列 = None
- 两列都映射到 aux_dimensions
- 修复前：后者 None 覆盖前者有效值 → aux_dimensions=None → aux_ledger=0
- 修复后：第一个非空值保留 → aux_dimensions 正确保留
"""
from backend.app.services.ledger_import.writer import prepare_rows_with_raw_extra


def test_multi_column_same_field_keeps_non_empty():
    """两列映射到同一 standard_field，后者 None 不覆盖前者值。"""
    col_mapping = {
        "核算维度": "aux_dimensions",
        "主表项目": "aux_dimensions",
    }
    headers = ["核算维度", "主表项目"]
    rows = [
        {"核算维度": "客户:001 北京A", "主表项目": None},
        {"核算维度": None, "主表项目": "项目:P01 产品"},
        {"核算维度": "", "主表项目": "有值"},  # 空串也算空
    ]
    result, _ = prepare_rows_with_raw_extra(rows, col_mapping, headers)
    assert result[0]["aux_dimensions"] == "客户:001 北京A"
    assert result[1]["aux_dimensions"] == "项目:P01 产品"
    assert result[2]["aux_dimensions"] == "有值"


def test_multi_column_same_field_first_non_empty_wins():
    """当两列都非空时，保留第一个，后者进 raw_extra._discarded_mappings。"""
    col_mapping = {
        "账簿类型": "voucher_type",
        "凭证类型": "voucher_type",
        "来源类型": "voucher_type",
    }
    headers = ["账簿类型", "凭证类型", "来源类型"]
    rows = [
        {"账簿类型": "主账簿", "凭证类型": "ZZ", "来源类型": "自动转账"},
    ]
    result, _ = prepare_rows_with_raw_extra(rows, col_mapping, headers)
    # 第一个非空值保留
    assert result[0]["voucher_type"] == "主账簿"
    # 被丢弃的"凭证类型"和"来源类型"值进 raw_extra._discarded_mappings
    discarded = result[0]["raw_extra"]["_discarded_mappings"]["voucher_type"]
    assert len(discarded) == 2
    assert {d["header"] for d in discarded} == {"凭证类型", "来源类型"}
    assert {d["value"] for d in discarded} == {"ZZ", "自动转账"}


def test_single_column_no_discarded():
    """单列映射——无 _discarded_mappings 字段。"""
    col_mapping = {"科目编码": "account_code"}
    headers = ["科目编码", "无关列"]
    rows = [{"科目编码": "1001", "无关列": "val"}]
    result, _ = prepare_rows_with_raw_extra(rows, col_mapping, headers)
    assert result[0]["account_code"] == "1001"
    # 无关列进 raw_extra
    assert result[0]["raw_extra"] == {"无关列": "val"}
    # 无丢弃映射
    assert "_discarded_mappings" not in result[0]["raw_extra"]
