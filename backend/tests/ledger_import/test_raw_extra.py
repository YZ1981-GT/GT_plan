"""raw_extra 写入逻辑验证 — Task 75a。

验证：
- 关键/次关键已映射列不重复存入 raw_extra
- 非关键列原样保留
- 超 8KB 截断 + EXTRA_TRUNCATED warning
- 空值列不存入 raw_extra
- 全部映射时 raw_extra = None
"""

from __future__ import annotations

import pytest

from app.services.ledger_import.writer import (
    RAW_EXTRA_MAX_BYTES,
    build_raw_extra,
    prepare_rows_with_raw_extra,
)


class TestBuildRawExtra:
    """build_raw_extra 单元测试。"""

    def test_mapped_fields_excluded(self):
        """已映射列不出现在 raw_extra 中。"""
        row = {
            "科目编码": "1001",
            "科目名称": "库存现金",
            "期初余额": "10000",
            "自定义备注": "测试备注",
            "审核人": "张三",
        }
        mapped = {"科目编码", "科目名称", "期初余额"}
        headers = ["科目编码", "科目名称", "期初余额", "自定义备注", "审核人"]

        extra, warning = build_raw_extra(row, mapped, headers)

        assert extra is not None
        assert "科目编码" not in extra
        assert "科目名称" not in extra
        assert "期初余额" not in extra
        assert extra["自定义备注"] == "测试备注"
        assert extra["审核人"] == "张三"
        assert warning is None

    def test_all_mapped_returns_none(self):
        """所有列都已映射时返回 None（不存空 dict）。"""
        row = {"科目编码": "1001", "科目名称": "现金"}
        mapped = {"科目编码", "科目名称"}
        headers = ["科目编码", "科目名称"]

        extra, warning = build_raw_extra(row, mapped, headers)

        assert extra is None
        assert warning is None

    def test_empty_values_excluded(self):
        """空值列不存入 raw_extra。"""
        row = {
            "科目编码": "1001",
            "备注": "",
            "审核人": None,
            "标记": "  ",
            "有效列": "有值",
        }
        mapped = {"科目编码"}
        headers = ["科目编码", "备注", "审核人", "标记", "有效列"]

        extra, warning = build_raw_extra(row, mapped, headers)

        assert extra is not None
        assert "备注" not in extra
        assert "审核人" not in extra
        assert "标记" not in extra
        assert extra["有效列"] == "有值"

    def test_truncation_at_8kb(self):
        """超 8KB 时截断并生成 EXTRA_TRUNCATED warning。"""
        # 构造一个超大 row：100 个列，每列 200 字符
        headers = [f"col_{i:03d}" for i in range(100)]
        row = {h: "X" * 200 for h in headers}
        mapped: set[str] = set()  # 无映射，全部进 raw_extra

        extra, warning = build_raw_extra(row, mapped, headers)

        assert extra is not None
        assert warning is not None
        assert warning.code == "EXTRA_TRUNCATED"
        # 截断后的 extra 应小于 8KB
        import json
        serialized = json.dumps(extra, ensure_ascii=False)
        assert len(serialized.encode("utf-8")) <= RAW_EXTRA_MAX_BYTES
        # 应该保留了部分列但不是全部
        assert len(extra) < 100
        assert len(extra) > 0

    def test_preserves_original_values(self):
        """非关键列的原始值类型保留（数字/字符串）。"""
        row = {
            "科目编码": "1001",
            "金额": 12345.67,
            "序号": 42,
            "备注": "测试",
        }
        mapped = {"科目编码"}
        headers = ["科目编码", "金额", "序号", "备注"]

        extra, warning = build_raw_extra(row, mapped, headers)

        assert extra["金额"] == 12345.67
        assert extra["序号"] == 42
        assert extra["备注"] == "测试"


class TestPrepareRowsWithRawExtra:
    """prepare_rows_with_raw_extra 集成测试。"""

    def test_standard_transformation(self):
        """标准转换：映射列→标准字段，未映射列→raw_extra。"""
        raw_rows = [
            {"科目编码": "1001", "科目名称": "现金", "期初余额": "10000", "自定义": "备注1"},
            {"科目编码": "1002", "科目名称": "银行", "期初余额": "50000", "自定义": "备注2"},
        ]
        column_mapping = {
            "科目编码": "account_code",
            "科目名称": "account_name",
            "期初余额": "opening_balance",
        }
        headers = ["科目编码", "科目名称", "期初余额", "自定义"]

        transformed, warnings = prepare_rows_with_raw_extra(raw_rows, column_mapping, headers)

        assert len(transformed) == 2
        assert len(warnings) == 0

        row0 = transformed[0]
        assert row0["account_code"] == "1001"
        assert row0["account_name"] == "现金"
        assert row0["opening_balance"] == "10000"
        assert row0["raw_extra"] == {"自定义": "备注1"}

    def test_no_unmapped_columns(self):
        """全部列都映射时 raw_extra = None。"""
        raw_rows = [{"科目编码": "1001", "科目名称": "现金"}]
        column_mapping = {"科目编码": "account_code", "科目名称": "account_name"}
        headers = ["科目编码", "科目名称"]

        transformed, warnings = prepare_rows_with_raw_extra(raw_rows, column_mapping, headers)

        assert transformed[0]["raw_extra"] is None

    def test_real_sample_pattern(self):
        """模拟真实样本模式：14 列余额表，9 列映射 + 5 列进 raw_extra。"""
        raw_rows = [{
            "科目编码": "1001",
            "科目名称": "库存现金",
            "核算维度": "",
            "组织编码": "ORG001",
            "年初余额.借方金额": "10000",
            "年初余额.贷方金额": "0",
            "期初余额.借方金额": "10000",
            "期初余额.贷方金额": "0",
            "本期发生额.借方金额": "5000",
            "本期发生额.贷方金额": "3000",
            "本年累计.借方金额": "5000",
            "本年累计.贷方金额": "3000",
            "期末余额.借方金额": "12000",
            "期末余额.贷方金额": "0",
        }]
        # 假设映射了 9 列
        column_mapping = {
            "科目编码": "account_code",
            "科目名称": "account_name",
            "组织编码": "company_code",
            "年初余额.借方金额": "opening_debit",
            "年初余额.贷方金额": "opening_credit",
            "本期发生额.借方金额": "debit_amount",
            "本期发生额.贷方金额": "credit_amount",
            "期末余额.借方金额": "closing_debit",
            "期末余额.贷方金额": "closing_credit",
        }
        headers = list(raw_rows[0].keys())

        transformed, warnings = prepare_rows_with_raw_extra(raw_rows, column_mapping, headers)

        row = transformed[0]
        assert row["account_code"] == "1001"
        assert row["closing_debit"] == "12000"

        # raw_extra 应包含未映射的列（非空值）
        extra = row["raw_extra"]
        assert extra is not None
        # 核算维度为空不应出现
        assert "核算维度" not in extra
        # 期初余额和本年累计应在 raw_extra 中
        assert "期初余额.借方金额" in extra
        assert "本年累计.借方金额" in extra
