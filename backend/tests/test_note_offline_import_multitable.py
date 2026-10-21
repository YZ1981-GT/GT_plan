"""离线导入每 sheet 多表解析 + 并回生成链结构 + 真实落库（spec Phase 8 Task 9）。

覆盖：
- extract_sheet_tables：一个 sheet 多张表全部解析（旧实现只读第一张）
- merge_imported_tables_into_section：按表序并回、只改 values、保留 row_type/is_total/_cell_meta/绑定、首表镜像
- 导出→导入 round-trip：多表章节导出后再抽取，表数 / 行标签一致
- apply_import OVERWRITE 写回 _tables（不是扁平单表），回执 tables_written 如实
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.note_offline_import_tables import (  # noqa: E402
    extract_sheet_tables,
    merge_imported_tables_into_section,
)


def test_structure_driven_two_tables_with_in_table_blank_rows() -> None:
    """结构驱动：表内有空明细行也不会被误切（真实验收 2→4 的根因回归）。"""
    grid = [
        ["其他权益工具投资情况"],
        ["项目", "期末余额", "期初余额"],
        [None, None, None],   # 表内空明细行
        [None, None, None],
        ["合计", 0, 0],
        [None, None, None],   # 表间空行
        ["期末其他权益工具投资情况"],
        ["项目名称", "本期确认的股利收入"],
        [None, None],
        ["合计", 0],
    ]
    expected = [
        {"name": "其他权益工具投资情况", "headers": ["项目", "期末余额", "期初余额"],
         "rows": [{"label": "", "values": [None, None]}, {"label": "", "values": [None, None]},
                  {"label": "合计", "values": [0, 0]}]},
        {"name": "期末其他权益工具投资情况", "headers": ["项目名称", "本期确认的股利收入"],
         "rows": [{"label": "", "values": [None]}, {"label": "合计", "values": [0]}]},
    ]
    tables = extract_sheet_tables(grid, expected=expected)
    assert len(tables) == 2, f"结构驱动应仍为 2 张表（表内空行不切），实为 {len(tables)}"
    assert len(tables[0]["rows"]) == 3 and len(tables[1]["rows"]) == 2
    assert tables[0]["rows"][2]["cells"] == ["合计", 0, 0]
    assert tables[1]["rows"][1]["cells"] == ["合计", 0]


def test_fallback_two_tables_in_one_sheet() -> None:
    """无既有结构（IMPORT_ONLY）退回空行分块：表A 空行 表B。"""
    grid = [
        ["表A"],
        ["项目", "期末", "期初"],
        ["货币资金", 100, 90],
        ["银行存款", 80, 70],
        [None, None, None],
        ["表B"],
        ["项目", "本期"],
        ["销售费用", 50],
    ]
    tables = extract_sheet_tables(grid)
    assert len(tables) == 2, f"应解析出 2 张表，实为 {len(tables)}"
    assert tables[0]["name"] == "表A" and tables[1]["name"] == "表B"
    assert [r["cells"][0] for r in tables[0]["rows"]] == ["货币资金", "银行存款"]
    assert [r["cells"][0] for r in tables[1]["rows"]] == ["销售费用"]


def test_extract_tables_split_by_blank_row() -> None:
    """两表以空行分隔（导出固定在表间空一行）；块内第一行是表头、其余是数据行。"""
    grid = [
        ["项目", "期末"],
        ["A", 1],
        ["合计", 1],
        [None, None],
        ["项目", "本期"],
        ["B", 2],
    ]
    tables = extract_sheet_tables(grid)
    assert len(tables) == 2
    assert [r["cells"][0] for r in tables[0]["rows"]] == ["A", "合计"]
    assert [r["cells"][0] for r in tables[1]["rows"]] == ["B"]


def test_extract_ignores_single_column_only_block() -> None:
    """纯单列块（章首指引，无 value 列头）不当作表。"""
    grid = [["【提示：本章仅在…时填列】"], [None, None], ["项目", "期末"], ["A", 1]]
    tables = extract_sheet_tables(grid)
    assert len(tables) == 1 and [r["cells"][0] for r in tables[0]["rows"]] == ["A"]


def test_merge_updates_values_and_preserves_non_value_fields() -> None:
    existing = {
        "_tables": [
            {
                "name": "货币资金", "headers": ["项目", "期末", "期初"],
                "rows": [
                    {"label": "库存现金", "values": [0, 0], "row_type": "data",
                     "_cell_meta": {"0": {"binding_id": "八、1.库存现金.end"}}},
                    {"label": "合计", "values": [None, None], "is_total": True},
                ],
            },
            {"name": "受限", "headers": ["项目", "金额"], "rows": [{"label": "质押", "values": [0]}]},
        ],
        "headers": ["项目", "期末", "期初"], "rows": [{"label": "库存现金", "values": [0, 0]}],
    }
    imported = [
        {"name": "货币资金", "headers": ["项目", "期末", "期初"],
         "rows": [{"cells": ["库存现金", 100, 90]}, {"cells": ["合计", 100, 90]}]},
        {"name": "受限", "headers": ["项目", "金额"], "rows": [{"cells": ["质押", 50]}]},
    ]
    out = merge_imported_tables_into_section(existing, imported)
    t0 = out["_tables"][0]
    assert t0["rows"][0]["values"] == [100, 90], "明细值未并入"
    assert t0["rows"][0]["row_type"] == "data", "row_type 丢失"
    assert t0["rows"][0]["_cell_meta"]["0"]["binding_id"] == "八、1.库存现金.end", "绑定丢失"
    assert t0["rows"][1]["is_total"] is True, "is_total 丢失"
    assert out["_tables"][1]["rows"][0]["values"] == [50], "第二张表未并入"
    # 首表镜像
    assert out["rows"] == t0["rows"] and out["headers"] == t0["headers"]
    # 不改入参
    assert existing["_tables"][0]["rows"][0]["values"] == [0, 0]


def test_merge_single_table_stays_flat() -> None:
    existing = {"headers": ["项目", "期末"], "rows": [{"label": "A", "values": [0]}]}
    imported = [{"name": "", "headers": ["项目", "期末"], "rows": [{"cells": ["A", 7]}]}]
    out = merge_imported_tables_into_section(existing, imported)
    assert "_tables" not in out, "单表章节不应平白升级为 _tables"
    assert out["rows"][0]["values"] == [7]


def test_merge_import_only_builds_structure_from_scratch() -> None:
    out = merge_imported_tables_into_section({}, [
        {"name": "表1", "headers": ["项目", "本期"], "rows": [{"cells": ["X", 3]}]},
        {"name": "表2", "headers": ["项目", "本期"], "rows": [{"cells": ["Y", 4]}]},
    ])
    assert len(out["_tables"]) == 2
    assert out["_tables"][0]["rows"][0] == {"label": "X", "values": [3]}
    assert out["rows"] == out["_tables"][0]["rows"]


def test_roundtrip_export_then_extract_all_tables() -> None:
    """多表章节导出 → 再抽取，表数与各表行标签一致（证明 export↔extract 口径对齐）。"""
    from openpyxl import load_workbook
    from io import BytesIO

    from app.services.note_offline_export_service import export_sections_to_xlsx

    section = {
        "section_id": "八、1", "note_section": "八、1", "section_title": "货币资金",
        "table_data": {
            "_tables": [
                {"name": "货币资金", "headers": ["项目", "期末", "期初"],
                 "rows": [{"label": "库存现金", "values": [100, 90]}, {"label": "银行存款", "values": [80, 70]}]},
                {"name": "受限货币资金", "headers": ["项目", "金额"],
                 "rows": [{"label": "保证金", "values": [5]}]},
            ],
        },
    }
    xlsx_bytes, _names = export_sections_to_xlsx([section], project_name="测试", include_formulas=False)
    # 定位该 section 的 sheet：第 1 行标题 / 第 2 行 section_id
    wb = load_workbook(BytesIO(xlsx_bytes), data_only=True)
    target = None
    for ws in wb.worksheets:
        c = ws.cell(row=2, column=1).value
        if c and str(c).startswith("section_id:八、1"):
            target = ws
            break
    assert target is not None, "导出包里找不到八、1 的 sheet"
    grid = [[target.cell(row=r, column=col).value for col in range(1, target.max_column + 1)]
            for r in range(3, target.max_row + 1)]
    # 结构驱动：传既有 _tables 作锚点（真实路径即如此，表内空行不会被误切）
    tables = extract_sheet_tables(grid, expected=section["table_data"]["_tables"])
    assert len(tables) == 2, f"round-trip 后应仍为 2 张表，实为 {len(tables)}"
    assert [r["cells"][0] for r in tables[0]["rows"]] == ["库存现金", "银行存款"]
    assert [r["cells"][0] for r in tables[1]["rows"]] == ["保证金"]


def test_apply_import_writes_tables_not_flat() -> None:
    """apply_import OVERWRITE 后 table_data 带 _tables（多表），tables_written 回执如实。"""
    from io import BytesIO

    from openpyxl import load_workbook  # noqa: F401 (确保依赖在)

    from app.services.note_offline_export_service import export_sections_to_xlsx
    from app.services.note_offline_import_service import apply_import, ConflictResolution

    section = {
        "section_id": "八、1", "note_section": "八、1", "section_title": "货币资金",
        "table_data": {
            "_tables": [
                {"name": "货币资金", "headers": ["项目", "期末", "期初"],
                 "rows": [{"label": "库存现金", "values": [0, 0]}]},
                {"name": "受限货币资金", "headers": ["项目", "金额"],
                 "rows": [{"label": "保证金", "values": [0]}]},
            ],
        },
    }
    xlsx_bytes, _ = export_sections_to_xlsx([section], project_name="测试", include_formulas=False)
    result = apply_import(xlsx_bytes, [section], {"八、1": ConflictResolution.OVERWRITE})
    assert result.sections_imported == 1
    assert result.tables_written == 2, f"回执应报 2 张表写入，实为 {result.tables_written}"
    td = result.applied_sections["八、1"]
    assert isinstance(td.get("_tables"), list) and len(td["_tables"]) == 2, "未写回多表结构"
