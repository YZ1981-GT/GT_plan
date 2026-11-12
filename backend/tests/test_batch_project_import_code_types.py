"""批量导入真实 Excel 三码单元格类型回归（consol-group-code-entry-consistency R3）。"""
from __future__ import annotations

import zipfile
from io import BytesIO
from xml.etree import ElementTree

import pytest
from openpyxl import load_workbook

ROOT = "91110000100000000R"
PARENT = "911100002000000005"
CHILD = "91110000300000000G"


def row(
    name: str,
    code: str,
    year: int | float,
    scope: str = "单户",
    *,
    parent: str = "",
    ultimate: str = "",
    relation: str = "",
) -> list:
    return [
        name,
        code,
        name[:20],
        year,
        "年报审计",
        "企业会计准则",
        scope,
        parent,
        ultimate,
        relation,
        "新建",
        "",
        "",
    ]


def _to_fullwidth(value: str) -> str:
    return "".join(
        chr(ord(char) + 0xFEE0) if "!" <= char <= "~" else char
        for char in value
    )


def _set_formula_cached_value(
    file_bytes: bytes, *, cell_ref: str, value: str
) -> bytes:
    """给 openpyxl 写出的真实公式补 OOXML 缓存值。

    openpyxl 没有公开的公式缓存写入 API；测试先用 openpyxl 写公式，再只修改
    ``数据`` sheet 的 ``<v>``，从而仍通过真实 xlsx → load_data_sheet 读取链验证。
    """
    source = BytesIO(file_bytes)
    output = BytesIO()
    with zipfile.ZipFile(source, "r") as source_zip, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED
    ) as output_zip:
        for info in source_zip.infolist():
            payload = source_zip.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                root = ElementTree.fromstring(payload)
                namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                cell = next(
                    item
                    for item in root.iter(f"{namespace}c")
                    if item.attrib.get("r") == cell_ref
                )
                cached = cell.find(f"{namespace}v")
                if cached is None:
                    cached = ElementTree.SubElement(cell, f"{namespace}v")
                cell.attrib["t"] = "str"
                cached.text = value
                payload = ElementTree.tostring(
                    root, encoding="utf-8", xml_declaration=True
                )
            output_zip.writestr(info, payload)
    return output.getvalue()


@pytest.mark.parametrize(
    ("kind", "column", "raw_value", "expected_code"),
    [
        ("int", 1, 911100003000000005, None),
        ("float", 7, 9.111000020000000e17, None),
        ("formula without cache", 7, "=1+1", None),
        ("formula with cache", 1, f'="{CHILD}"', CHILD),
        ("text", 7, f"  {PARENT.lower()}  ", PARENT),
    ],
)
def test_generated_template_code_cell_types_use_real_load_and_parse_chain(
    kind: str, column: int, raw_value: object, expected_code: str | None,
):
    """五类 Excel 单元格均经模板、openpyxl、load_data_sheet、parse_row 读取。"""
    from app.services.batch_project_workbook import (
        generate_template as generate_workbook_template,
        load_data_sheet,
        parse_row,
    )

    workbook_bytes = generate_workbook_template(mode="project").getvalue()
    workbook = load_workbook(BytesIO(workbook_bytes), data_only=False)
    sheet = workbook["数据"]
    values = row(
        "代码类型测试",
        CHILD,
        2050,
        parent=PARENT,
        ultimate=ROOT,
        relation="子公司",
    )
    values[column] = raw_value
    for index, value in enumerate(values, start=1):
        sheet.cell(row=2, column=index).value = value
    changed = BytesIO()
    workbook.save(changed)
    changed_bytes = changed.getvalue()
    if kind == "formula with cache":
        changed_bytes = _set_formula_cached_value(
            changed_bytes, cell_ref=f"{chr(65 + column)}2", value=expected_code or ""
        )

    loaded = load_data_sheet(changed_bytes)
    parsed, errors = parse_row(loaded.rows[0], row_number=2)

    if kind in {"int", "float"}:
        assert any("单元格被 Excel 识别为数字" in error for error in errors)
        parsed_field = {
            1: "company_code",
            7: "parent_company_code",
            8: "ultimate_company_code",
        }[column]
        assert getattr(parsed, parsed_field) == str(
            getattr(loaded.rows[0][column], "raw", loaded.rows[0][column])
        ).strip()
    elif kind == "formula without cache":
        assert (
            "上级企业代码：公式没有计算结果，请在 Excel 中重新计算保存或粘贴为值"
            in errors
        )
        assert parsed.parent_company_code == "=1+1"
    elif kind == "formula with cache":
        assert errors == []
        assert parsed.company_code == CHILD
    else:
        assert errors == []
        assert parsed.parent_company_code == PARENT


@pytest.mark.parametrize(
    ("column", "label", "invalid_code", "reason"),
    [
        (
            1,
            "企业代码",
            "91110000100000000Z",
            "统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）",
        ),
        (
            7,
            "上级企业代码",
            "91110000 100000000R",
            "统一社会信用代码必须为 18 位",
        ),
        (
            8,
            "最终控制方代码",
            "91110000100000000Z",
            "统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）",
        ),
    ],
)
def test_parse_row_code_errors_use_field_label_and_fullwidth_colon(
    column: int, label: str, invalid_code: str, reason: str,
):
    values = row("测试企业", ROOT, 2025)
    values[column] = invalid_code

    from app.services.batch_project_workbook import parse_row

    _, errors = parse_row(values)

    assert f"{label}：{reason}" in errors
    assert f"{label}格式错误：" not in "；".join(errors)


@pytest.mark.parametrize("column", [1, 7, 8])
@pytest.mark.parametrize(
    "raw_code",
    [
        f"  {ROOT.lower()}  ",
        _to_fullwidth(ROOT.lower()),
        f"  {_to_fullwidth(ROOT.lower())}  ",
    ],
)
def test_parse_row_normalizes_valid_codes_before_validation(
    column: int, raw_code: str
):
    values = row("测试企业", ROOT, 2025)
    values[column] = raw_code

    from app.services.batch_project_workbook import parse_row

    parsed, errors = parse_row(values)

    assert not any(
        error.startswith(("企业代码：", "上级企业代码：", "最终控制方代码："))
        for error in errors
    )
    field = {
        1: "company_code",
        7: "parent_company_code",
        8: "ultimate_company_code",
    }[column]
    assert getattr(parsed, field) == ROOT


def test_parse_row_keeps_required_and_optional_empty_code_messages():
    values = row("测试企业", "", 2025)
    values[7] = ""
    values[8] = ""

    from app.services.batch_project_workbook import parse_row

    _, errors = parse_row(values)

    assert "企业代码为必填项" in errors
    assert not any(
        error.startswith(("企业代码：", "上级企业代码：", "最终控制方代码："))
        for error in errors
    )
    assert not any(error.startswith("上级企业代码：") for error in errors)
    assert not any(error.startswith("最终控制方代码：") for error in errors)
