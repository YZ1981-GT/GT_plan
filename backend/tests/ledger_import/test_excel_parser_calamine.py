"""B3: excel_parser_calamine 与 openpyxl 版行为等价性。

- data_start_row 生效一致
- chunk_size 边界一致
- forward_fill_cols 合并单元格向下填充一致
- 空 sheet / 缺失 sheet 错误一致
"""
from __future__ import annotations

import io

import openpyxl
import pytest

from app.services.ledger_import.parsers.excel_parser import (
    iter_excel_rows_from_path as iter_openpyxl,
)
from app.services.ledger_import.parsers.excel_parser_calamine import (
    iter_excel_rows_from_path_calamine as iter_calamine,
)


def _build_xlsx(rows: list[list], tmp_path, sheet_name: str = "sheet1") -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    for row in rows:
        ws.append(row)
    path = tmp_path / "test.xlsx"
    wb.save(str(path))
    return str(path)


def test_basic_rows_match(tmp_path):
    """基础数据行：calamine 和 openpyxl 读出值**数值语义**相等（允许 int vs float 类型差异）。"""
    from decimal import Decimal

    rows = [
        ["code", "name", "amount"],  # header
        ["1001", "cash", 100],
        ["1002", "bank", 200],
        ["1003", "ar", 300],
    ]
    path = _build_xlsx(rows, tmp_path)
    op = list(iter_openpyxl(path, "sheet1", data_start_row=1))
    ca = list(iter_calamine(path, "sheet1", data_start_row=1))
    assert len(op) == 1 and len(ca) == 1  # 一个 chunk
    assert len(op[0]) == 3 and len(ca[0]) == 3

    def _norm(v):
        """把值规范化为可比较形式：数字→Decimal，空→None，否则 str。"""
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        return str(v)

    for i in range(3):
        for col in range(3):
            assert _norm(op[0][i][col]) == _norm(ca[0][i][col]), (
                f"行 {i} 列 {col}: openpyxl={op[0][i][col]!r} calamine={ca[0][i][col]!r}"
            )


def test_data_start_row_zero(tmp_path):
    rows = [
        ["a", "b"],
        ["c", "d"],
    ]
    path = _build_xlsx(rows, tmp_path)
    # data_start_row=0 应包含 header 行
    op = list(iter_openpyxl(path, "sheet1", data_start_row=0))
    ca = list(iter_calamine(path, "sheet1", data_start_row=0))
    assert len(op[0]) == 2 and len(ca[0]) == 2


def test_chunk_size_boundary(tmp_path):
    rows = [["col"]] + [[i] for i in range(10)]  # 10 data rows
    path = _build_xlsx(rows, tmp_path)
    op = list(iter_openpyxl(path, "sheet1", data_start_row=1, chunk_size=3))
    ca = list(iter_calamine(path, "sheet1", data_start_row=1, chunk_size=3))
    # 都应切成 4 chunks: 3+3+3+1
    assert [len(c) for c in op] == [3, 3, 3, 1]
    assert [len(c) for c in ca] == [3, 3, 3, 1]


def test_forward_fill_cols(tmp_path):
    # 模拟科目编码合并单元格：第 0 列只在第 1/4 行有值
    rows = [
        ["code", "detail"],  # header
        ["1001", "a"],
        [None, "b"],
        [None, "c"],
        ["1002", "d"],
    ]
    path = _build_xlsx(rows, tmp_path)
    op = list(iter_openpyxl(path, "sheet1", data_start_row=1, forward_fill_cols=[0]))
    ca = list(iter_calamine(path, "sheet1", data_start_row=1, forward_fill_cols=[0]))
    # 两个引擎都应把前 3 行 code 都填为 1001
    assert [str(r[0]) for r in op[0]] == ["1001", "1001", "1001", "1002"]
    assert [str(r[0]) for r in ca[0]] == ["1001", "1001", "1001", "1002"]


def test_sheet_not_found(tmp_path):
    path = _build_xlsx([["a"]], tmp_path)
    with pytest.raises(RuntimeError, match="not found"):
        list(iter_openpyxl(path, "missing", data_start_row=0))
    with pytest.raises(RuntimeError, match="not found"):
        list(iter_calamine(path, "missing", data_start_row=0))


def test_empty_data_rows(tmp_path):
    # 只有 header，无数据行
    rows = [["col1", "col2"]]
    path = _build_xlsx(rows, tmp_path)
    op = list(iter_openpyxl(path, "sheet1", data_start_row=1))
    ca = list(iter_calamine(path, "sheet1", data_start_row=1))
    # 不 yield 空 chunk
    assert op == [] and ca == []


def test_mixed_types_preserved(tmp_path):
    """数字/字符串/None 类型应被保留（不强制转 str）。"""
    rows = [
        ["col1", "col2", "col3"],
        ["text", 123, None],
        [None, 45.67, "end"],
    ]
    path = _build_xlsx(rows, tmp_path)
    op = list(iter_openpyxl(path, "sheet1", data_start_row=1))
    ca = list(iter_calamine(path, "sheet1", data_start_row=1))
    # openpyxl: 保留原类型
    assert op[0][0][0] == "text"
    assert op[0][0][1] == 123
    assert op[0][0][2] is None
    # calamine: 数字可能是 int 或 float，None 保留
    assert ca[0][0][0] == "text"
    assert ca[0][0][1] in (123, 123.0)
    # calamine 将 None 可能读为空字符串 ""；允许两种
    assert ca[0][0][2] in (None, "")



# ══════════════════════════════════════════════════════════════════════════════
# B3-D: prepare_rows_with_raw_extra 快路径优化（所有列都已映射时跳过）
# ══════════════════════════════════════════════════════════════════════════════


def test_skip_raw_extra_when_all_mapped():
    """所有原始列都已映射到 standard_field → raw_extra 应为 None（跳过构建）。"""
    from app.services.ledger_import.writer import prepare_rows_with_raw_extra

    raw_rows = [
        {"科目编码": "1001", "科目名称": "cash", "金额": 100},
        {"科目编码": "1002", "科目名称": "bank", "金额": 200},
    ]
    column_mapping = {
        "科目编码": "account_code",
        "科目名称": "account_name",
        "金额": "debit_amount",
    }
    original_headers = ["科目编码", "科目名称", "金额"]
    transformed, warnings = prepare_rows_with_raw_extra(
        raw_rows, column_mapping, original_headers
    )
    assert len(transformed) == 2
    assert warnings == []
    for row in transformed:
        assert row["raw_extra"] is None
        assert row["account_code"] in ("1001", "1002")


def test_raw_extra_still_built_when_unmapped_exists():
    """有未映射列时仍正常构建 raw_extra（回归测试）。"""
    from app.services.ledger_import.writer import prepare_rows_with_raw_extra

    raw_rows = [
        {"科目编码": "1001", "备注": "cash 备注文字"},
    ]
    column_mapping = {"科目编码": "account_code"}  # "备注" 未映射
    original_headers = ["科目编码", "备注"]
    transformed, _ = prepare_rows_with_raw_extra(
        raw_rows, column_mapping, original_headers
    )
    assert transformed[0]["raw_extra"] is not None
    assert "备注" in transformed[0]["raw_extra"]
    assert transformed[0]["raw_extra"]["备注"] == "cash 备注文字"


def test_raw_extra_multi_source_still_built():
    """多对一映射（同一 standard_field 多个原始列）时仍要走非快路径保留 discarded。"""
    from app.services.ledger_import.writer import prepare_rows_with_raw_extra

    # "核算维度" 和 "主表项目" 都映射到 aux_dimensions
    raw_rows = [
        {"核算维度": "客户:A001", "主表项目": "项目:P001"},
    ]
    column_mapping = {"核算维度": "aux_dimensions", "主表项目": "aux_dimensions"}
    original_headers = ["核算维度", "主表项目"]
    transformed, _ = prepare_rows_with_raw_extra(
        raw_rows, column_mapping, original_headers
    )
    # 第一个非空保留，第二个进 _discarded_mappings
    assert transformed[0]["aux_dimensions"] == "客户:A001"
    assert transformed[0]["raw_extra"] is not None
    assert "_discarded_mappings" in transformed[0]["raw_extra"]
    assert "aux_dimensions" in transformed[0]["raw_extra"]["_discarded_mappings"]
