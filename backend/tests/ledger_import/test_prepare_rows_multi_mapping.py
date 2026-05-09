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


# S6-19: 边界场景补充


def test_three_columns_mixed_empty():
    """3 列同映射，第 2 列空，第 3 列非空 → 第 1 非空保留，第 3 进 discarded。"""
    col_mapping = {
        "账簿类型": "voucher_type",
        "凭证类型": "voucher_type",
        "来源类型": "voucher_type",
    }
    headers = ["账簿类型", "凭证类型", "来源类型"]
    rows = [
        {"账簿类型": "主账簿", "凭证类型": "", "来源类型": "自动转账"},
    ]
    result, _ = prepare_rows_with_raw_extra(rows, col_mapping, headers)
    assert result[0]["voucher_type"] == "主账簿"
    discarded = result[0]["raw_extra"]["_discarded_mappings"]["voucher_type"]
    # 空"凭证类型"不进 discarded，只有非空"来源类型"进
    assert len(discarded) == 1
    assert discarded[0]["header"] == "来源类型"
    assert discarded[0]["value"] == "自动转账"


def test_multi_mapping_with_raw_extra_merge():
    """多列映射 + 未映射列同时存在，两者合并到 raw_extra。"""
    col_mapping = {
        "核算维度": "aux_dimensions",
        "主表项目": "aux_dimensions",
    }
    headers = ["核算维度", "主表项目", "备注", "操作员"]
    rows = [
        {
            "核算维度": "客户:001 A客户",
            "主表项目": "项目:P01 研发",  # 被丢弃
            "备注": "测试",               # 进 raw_extra
            "操作员": "张三",             # 进 raw_extra
        },
    ]
    result, _ = prepare_rows_with_raw_extra(rows, col_mapping, headers)
    assert result[0]["aux_dimensions"] == "客户:001 A客户"
    extra = result[0]["raw_extra"]
    assert extra["备注"] == "测试"
    assert extra["操作员"] == "张三"
    # 丢弃项也在
    assert extra["_discarded_mappings"]["aux_dimensions"][0]["value"] == "项目:P01 研发"


def test_all_empty_no_discarded_key():
    """所有列都空时，raw_extra 不会出现 _discarded_mappings 空字典。"""
    col_mapping = {
        "核算维度": "aux_dimensions",
        "主表项目": "aux_dimensions",
    }
    headers = ["核算维度", "主表项目"]
    rows = [{"核算维度": None, "主表项目": ""}]
    result, _ = prepare_rows_with_raw_extra(rows, col_mapping, headers)
    # 没有任何非空值 → std_row 的 aux_dimensions 也保持 None/""
    # raw_extra 应为 None（无未映射列、无丢弃列）
    assert result[0]["raw_extra"] is None
