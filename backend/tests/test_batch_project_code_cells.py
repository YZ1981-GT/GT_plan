"""批量建项 Excel 三码列保护（spec consol-group-code-entry-consistency R3）。"""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook
from openpyxl.worksheet._read_only import ReadOnlyWorksheet

from app.services.batch_project_export import _project_export_row
from app.services.batch_project_workbook import (
    entity_group_fields_hash,
    generate_error_workbook,
    generate_template,
    load_data_sheet,
    parse_row,
)

CHILD = "91110000300000000G"
PARENT = "911100002000000005"
GROUP = "91110000100000000R"


def _valid_row(**overrides):
    row = [
        "测试公司", CHILD, "测试", 2025, "年报审计", "企业会计准则", "单户",
        PARENT, GROUP, "子公司", "新建", "", "",
    ]
    for key, value in overrides.items():
        row[{"company": 1, "parent": 7, "ultimate": 8}[key]] = value
    return row


def _workbook_with_row(row):
    output = generate_template(mode="project")
    workbook = load_workbook(output)
    sheet = workbook["数据"]
    for column, value in enumerate(row, start=1):
        sheet.cell(row=2, column=column).value = value
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_template_code_columns_are_text_format_and_examples_are_strings():
    workbook = load_workbook(generate_template(mode="project"), data_only=False)
    assert {"数据", "填写示例"}.issubset(workbook.sheetnames)
    data = workbook["数据"]
    examples = workbook["填写示例"]
    for column in (2, 8, 9):
        assert all(
            data.cell(row=row, column=column).number_format == "@"
            for row in range(2, 502)
        )
        assert all(
            data.cell(row=row, column=column).value in (None, "")
            or (
                isinstance(data.cell(row=row, column=column).value, str)
                and data.cell(row=row, column=column).data_type == "s"
            )
            for row in range(2, 502)
        )
        assert all(examples.cell(row=row, column=column).number_format == "@" for row in range(2, 6))
        assert all(
            cell.value in (None, "")
            or (isinstance(cell.value, str) and cell.data_type == "s")
            for row in range(2, 6)
            for cell in [examples.cell(row=row, column=column)]
        )
    assert isinstance(examples["B2"].value, str)
    assert isinstance(examples["H3"].value, str)
    assert isinstance(examples["I4"].value, str)


@pytest.mark.parametrize(
    "column, label, raw",
    [
        (2, "企业代码", 91110000300000000),
        (8, "上级企业代码", 911100002000000005),
        (9, "最终控制方代码", 91110000100000000),
    ],
)
def test_numeric_code_cell_reports_excel_numeric_error_and_preserves_raw(column, label, raw):
    row = _valid_row()
    row[column - 1] = raw
    loaded = load_data_sheet(_workbook_with_row(row))
    parsed, errors = parse_row(loaded.rows[0], row_number=2)
    assert any(label in error and "Excel 识别为数字" in error for error in errors)
    error_book = load_workbook(
        generate_error_workbook([(parsed, errors)]), data_only=False
    )
    # 错误明细仍回写平台实际读到的原值，且代码列为文本格式。
    code_cell = error_book["错误明细"].cell(row=2, column=column)
    assert code_cell.number_format == "@"
    assert code_cell.data_type == "s"
    assert str(code_cell.value) in {str(raw), str(float(raw))}
    assert any(str(raw) in error or str(float(raw)) in error for error in errors)


@pytest.mark.parametrize(
    "column, label",
    [(2, "企业代码"), (8, "上级企业代码"), (9, "最终控制方代码")],
)
def test_error_workbook_preserves_uncached_formula_for_each_code_column(column, label):
    row = _valid_row()
    formula = f"={column}+1"
    row[column - 1] = formula
    loaded = load_data_sheet(_workbook_with_row(row))
    parsed, errors = parse_row(loaded.rows[0], row_number=2)

    assert f"{label}：公式没有计算结果，请在 Excel 中重新计算保存或粘贴为值" in errors
    code_cell = load_workbook(
        generate_error_workbook([(parsed, errors)]), data_only=False
    )["错误明细"].cell(row=2, column=column)
    assert code_cell.value == formula
    assert code_cell.data_type == "s"
    assert code_cell.number_format == "@"


def test_formula_without_cached_value_reports_targeted_error():
    row = _valid_row(company="=1+1")
    loaded = load_data_sheet(_workbook_with_row(row))
    _, errors = parse_row(loaded.rows[0], row_number=2)
    assert "企业代码：公式没有计算结果，请在 Excel 中重新计算保存或粘贴为值" in errors


def test_text_code_is_normalized_and_accepted():
    row = _valid_row(company=f"  {CHILD.lower()} ", parent=f" {PARENT} ")
    loaded = load_data_sheet(_workbook_with_row(row))
    parsed, errors = parse_row(loaded.rows[0], row_number=2)
    assert not errors
    assert parsed.company_code == CHILD
    assert parsed.parent_company_code == PARENT


@pytest.mark.parametrize("missing_baseline", [None, ""])
def test_update_export_requires_entity_group_baseline_and_writes_it(missing_baseline):
    project = SimpleNamespace(
        id="project-1", client_name="测试公司", company_code=CHILD,
        short_name="测试", audit_year=2025, project_type="annual",
        wizard_state={}, report_scope="standalone", parent_company_code=PARENT,
        ultimate_company_code=GROUP, relation_to_parent="subsidiary",
    )
    with pytest.raises(ValueError, match="entity_group_fields_hash"):
        _project_export_row(project, action="update", base_hash=missing_baseline)
    baseline = entity_group_fields_hash([project])
    row = _project_export_row(project, action="update", base_hash=baseline)
    assert row[12] == baseline
    assert row[1] == CHILD
    assert row[7] == PARENT
    assert row[8] == GROUP


def test_formula_rescan_reads_only_code_columns_and_keeps_other_empty_formula_semantics(monkeypatch):
    """二次公式读取只查三码列，普通字段的无缓存公式仍按普通缺失处理。"""
    calls: list[dict[str, object]] = []
    original_iter_rows = ReadOnlyWorksheet.iter_rows

    def record_formula_scans(self, *args, **kwargs):
        if getattr(getattr(self, "parent", None), "data_only", None) is False:
            calls.append(dict(kwargs))
        return original_iter_rows(self, *args, **kwargs)

    monkeypatch.setattr(ReadOnlyWorksheet, "iter_rows", record_formula_scans)
    row = _valid_row()
    row[4] = "=1+1"  # 非代码列的无缓存公式
    loaded = load_data_sheet(_workbook_with_row(row))
    _, errors = parse_row(loaded.rows[0], row_number=2)

    assert len(calls) == 3
    assert {(call["min_col"], call["max_col"]) for call in calls} == {(2, 2), (8, 8), (9, 9)}
    assert "项目类型为必填项" in errors
    assert not any("公式没有计算结果" in error for error in errors)
