"""Unit tests for ExportService.export_xlsx (advanced-query-module Task 13.1).

Covers R7.1/7.2/7.4/7.5/7.6:
- Header titles/order preserved + data-source identity columns for drillable cols.
- Display values written per row in column order.
- 0 rows → header-only + empty notice row.
- Row/column capacity guard → EXPORT_CAPACITY (HTTP 400), no file.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO

import openpyxl
import pytest
from fastapi import HTTPException

from app.services.custom_query.export_service import (
    XLSX_MAX_COLS,
    XLSX_MAX_ROWS,
    ExportService,
    _EMPTY_NOTICE,
)
from app.services.custom_query.query_orchestrator import ColumnMeta, QueryResult


def _load(data: bytes):
    wb = openpyxl.load_workbook(BytesIO(data))
    ws = wb.active
    grid = [[c.value for c in row] for row in ws.iter_rows()]
    wb.close()
    return grid


def _run(coro):
    return asyncio.run(coro)


def test_header_order_and_display_values_preserved():
    svc = ExportService()
    result = QueryResult(
        columns=[
            ColumnMeta(key="acct", title="科目"),
            ColumnMeta(key="amt", title="金额", dtype="number"),
        ],
        rows=[
            {"acct": "库存现金", "amt": Decimal("100.50")},
            {"acct": "银行存款", "amt": Decimal("200")},
        ],
        total=2,
    )
    grid = _load(_run(svc.export_xlsx(result)))
    # header row preserves titles + order
    assert grid[0] == ["科目", "金额"]
    assert grid[1] == ["库存现金", 100.5]
    assert grid[2] == ["银行存款", 200]


def test_drillable_column_emits_source_identity_column():
    svc = ExportService()
    result = QueryResult(
        columns=[
            ColumnMeta(
                key="v",
                title="期末余额",
                addr_id="D2-1/sheet1/B5",
                semantic_label="应收账款期末余额",
            ),
        ],
        rows=[{"v": 999}],
        total=1,
    )
    grid = _load(_run(svc.export_xlsx(result)))
    # main column + source identity column
    assert grid[0] == ["期末余额", "期末余额·来源(addr_id)"]
    assert grid[1][0] == 999
    assert grid[1][1] == "D2-1/sheet1/B5｜应收账款期末余额"


def test_non_drillable_column_no_source_column():
    svc = ExportService()
    result = QueryResult(
        columns=[ColumnMeta(key="v", title="备注")],
        rows=[{"v": "x"}],
        total=1,
    )
    grid = _load(_run(svc.export_xlsx(result)))
    assert grid[0] == ["备注"]  # no trailing source column


def test_zero_rows_header_only_plus_empty_notice():
    svc = ExportService()
    result = QueryResult(
        columns=[ColumnMeta(key="a", title="A"), ColumnMeta(key="b", title="B")],
        rows=[],
        total=0,
    )
    grid = _load(_run(svc.export_xlsx(result)))
    assert grid[0] == ["A", "B"]
    assert grid[1][0] == _EMPTY_NOTICE


def test_tz_aware_datetime_and_uuid_coerced():
    import uuid

    svc = ExportService()
    dt = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    uid = uuid.uuid4()
    result = QueryResult(
        columns=[ColumnMeta(key="d", title="日期"), ColumnMeta(key="u", title="ID")],
        rows=[{"d": dt, "u": uid}],
        total=1,
    )
    grid = _load(_run(svc.export_xlsx(result)))
    assert grid[1][0] == datetime(2026, 1, 2, 3, 4, 5)  # tzinfo stripped
    assert grid[1][1] == str(uid)


def test_row_capacity_exceeded_raises_export_capacity():
    svc = ExportService()

    class _BigRows:
        """Fake rows container reporting > XLSX_MAX_ROWS length without allocating."""

        def __len__(self):
            return XLSX_MAX_ROWS + 1

        def __iter__(self):
            return iter(())

    result = QueryResult(columns=[ColumnMeta(key="a", title="A")])
    result.rows = _BigRows()  # type: ignore[assignment]

    with pytest.raises(HTTPException) as exc:
        _run(svc.export_xlsx(result))
    assert exc.value.status_code == 400
    assert exc.value.detail["error_code"] == "EXPORT_CAPACITY"


def test_col_capacity_exceeded_raises_export_capacity():
    svc = ExportService()
    cols = [ColumnMeta(key=f"c{i}", title=f"C{i}") for i in range(XLSX_MAX_COLS + 1)]
    result = QueryResult(columns=cols, rows=[], total=0)
    with pytest.raises(HTTPException) as exc:
        _run(svc.export_xlsx(result))
    assert exc.value.status_code == 400
    assert exc.value.detail["error_code"] == "EXPORT_CAPACITY"
    assert exc.value.detail["actual_cols"] == XLSX_MAX_COLS + 1


# ─── build_content_disposition — RFC 5987 文件名编码（Task 13.2, R7.3）──────
from urllib.parse import unquote  # noqa: E402


def _parse_filename_star(header: str) -> str:
    """从 Content-Disposition 头解析 filename* 并解码还原（P13 round-trip 辅助）。"""
    marker = "filename*=UTF-8''"
    assert marker in header
    encoded = header.split(marker, 1)[1]
    return unquote(encoded)


def test_content_disposition_has_ascii_fallback_and_filename_star():
    svc = ExportService()
    header = svc.build_content_disposition("高级查询_应收账款.xlsx")
    # ASCII 回退名 + RFC 5987 filename*
    assert 'filename="query.xlsx"' in header
    assert "filename*=UTF-8''" in header
    assert header.startswith("attachment; ")


def test_content_disposition_chinese_roundtrips():
    svc = ExportService()
    name = "高级查询_2026年度_期末余额.xlsx"
    header = svc.build_content_disposition(name)
    # 中文名经百分号编码后不得以裸中文出现在头值中
    assert name not in header
    # filename* 解码后完全还原（中文安全）
    assert _parse_filename_star(header) == name


def test_content_disposition_encodes_special_chars():
    svc = ExportService()
    # 空格 / 斜杠 / 引号等必须被百分号编码，保证头值合法
    header = svc.build_content_disposition('a b/c".xlsx')
    star = header.split("filename*=UTF-8''", 1)[1]
    assert " " not in star and "/" not in star and '"' not in star
    assert _parse_filename_star(header) == 'a b/c".xlsx'


def test_content_disposition_blank_falls_back_to_query_xlsx():
    svc = ExportService()
    header = svc.build_content_disposition("   ")
    assert _parse_filename_star(header) == "query.xlsx"
