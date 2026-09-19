"""Unit tests for ExportService.stream_xlsx + resolve_export_mode
(advanced-query-module Task 13.3).

Covers R8.1/8.2/8.3/8.4/8.6 + R7.6/7.7 for the streaming path:
- resolve_export_mode auto-routing (pivot/small → materialized, large flat → stream).
- Hard row limit (EXPORT_ROW_HARD_LIMIT) — pre-flight and defensive mid-iteration.
- Streaming produces a valid .xlsx with header + source-identity columns.
- Streaming accepts async cursor batches and sync iterables; rows flatten correctly.
- Stream row content matches non-streaming export_xlsx (R8.5 consistency).
- Column capacity guard (EXPORT_CAPACITY) before first byte.
- Mid-stream error raises before any byte is yielded (R7.7/R8.6) — no partial file.
"""

from __future__ import annotations

import asyncio
from io import BytesIO

import openpyxl
import pytest
from fastapi import HTTPException

from app.services.custom_query.export_service import (
    EXPORT_MODE_MATERIALIZED,
    EXPORT_MODE_STREAM,
    EXPORT_ROW_HARD_LIMIT,
    STREAM_ROW_THRESHOLD,
    XLSX_MAX_COLS,
    ExportService,
    _EMPTY_NOTICE,
)
from app.services.custom_query.query_orchestrator import ColumnMeta, QueryResult


# ─── helpers ─────────────────────────────────────────────────────────────────
def _collect(coro_gen) -> bytes:
    """Drain an async byte generator into a single bytes blob."""

    async def _drain() -> bytes:
        chunks = []
        async for c in coro_gen:
            assert isinstance(c, (bytes, bytearray))
            chunks.append(bytes(c))
        return b"".join(chunks)

    return asyncio.run(_drain())


def _grid(data: bytes):
    wb = openpyxl.load_workbook(BytesIO(data), read_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return rows


def _cols(with_addr: bool = False):
    return [
        ColumnMeta(key="acct", title="科目", dtype="text"),
        ColumnMeta(
            key="amt",
            title="金额",
            addr_id="D2-1/sheet1/B5" if with_addr else None,
            dtype="number",
            semantic_label="期末余额",
        ),
    ]


def _rows(n: int):
    return [{"acct": f"行{i}", "amt": i} for i in range(n)]


# ─── resolve_export_mode 自动择路（R8.1/R8.4）────────────────────────────────
def test_resolve_export_mode_large_flat_streams():
    svc = ExportService()
    assert (
        svc.resolve_export_mode(row_count=STREAM_ROW_THRESHOLD + 1, materialized=False)
        == EXPORT_MODE_STREAM
    )


def test_resolve_export_mode_small_flat_materializes():
    svc = ExportService()
    assert (
        svc.resolve_export_mode(row_count=STREAM_ROW_THRESHOLD, materialized=False)
        == EXPORT_MODE_MATERIALIZED
    )


def test_resolve_export_mode_pivot_always_materializes():
    svc = ExportService()
    # 透视/分组结果即便超大也物化（design §Components 6）
    assert (
        svc.resolve_export_mode(row_count=999_999, materialized=True)
        == EXPORT_MODE_MATERIALIZED
    )


def test_resolve_export_mode_hard_limit_rejects_before_start():
    svc = ExportService()
    with pytest.raises(HTTPException) as exc:
        svc.resolve_export_mode(row_count=EXPORT_ROW_HARD_LIMIT + 1, materialized=False)
    assert exc.value.status_code == 400
    assert exc.value.detail["error_code"] == "EXPORT_ROW_HARD_LIMIT"


# ─── stream_xlsx 产出有效 xlsx（R8.2）────────────────────────────────────────
def test_stream_produces_valid_xlsx_with_headers_and_source_col():
    svc = ExportService()
    cols = _cols(with_addr=True)
    data = _collect(svc.stream_xlsx(_rows(20), cols, memory_row_cap=7, chunk_rows=7))
    grid = _grid(data)
    assert grid[0] == ["科目", "金额", "金额·来源(addr_id)"]
    assert len(grid) == 21  # header + 20 rows
    assert grid[1][0] == "行0"
    assert grid[1][2] == "D2-1/sheet1/B5｜期末余额"


def test_stream_accepts_async_cursor_batches():
    svc = ExportService()
    cols = _cols()
    all_rows = _rows(30)

    async def cursor():
        # 模拟 DB 游标：每次 yield 一批行（list[dict]），需自动展平
        for i in range(0, len(all_rows), 8):
            yield all_rows[i : i + 8]

    data = _collect(svc.stream_xlsx(cursor(), cols))
    grid = _grid(data)
    assert len(grid) == 31  # header + 30
    assert grid[0] == ["科目", "金额"]
    assert grid[30][0] == "行29"


def test_stream_matches_materialized_row_content():
    """R8.5: 流式与非流式对同一结果集行内容逐行一致。"""
    svc = ExportService()
    cols = _cols(with_addr=True)
    rows = _rows(40)

    materialized = _grid(
        asyncio.run(svc.export_xlsx(QueryResult(columns=cols, rows=rows, total=40)))
    )

    async def gen():
        for r in rows:
            yield r

    streamed = _grid(_collect(svc.stream_xlsx(gen(), cols, memory_row_cap=5)))
    assert materialized == streamed


def test_stream_empty_result_header_plus_notice():
    svc = ExportService()
    data = _collect(svc.stream_xlsx([], _cols()))
    grid = _grid(data)
    assert grid[0] == ["科目", "金额"]
    assert grid[1][0] == _EMPTY_NOTICE


# ─── 容量 / 硬上限守卫（R7.6/R8.4）──────────────────────────────────────────
def test_stream_col_capacity_guard_before_first_byte():
    svc = ExportService()
    cols = [ColumnMeta(key=f"c{i}", title=f"C{i}") for i in range(XLSX_MAX_COLS + 1)]
    with pytest.raises(HTTPException) as exc:
        _collect(svc.stream_xlsx(_rows(1), cols))
    assert exc.value.detail["error_code"] == "EXPORT_CAPACITY"


def test_stream_defensive_hard_limit_mid_iteration():
    svc = ExportService()
    cols = _cols()
    # 用极小硬上限触发防御式中断（total 未知场景），首字节前 raise
    with pytest.raises(HTTPException) as exc:
        _collect(svc.stream_xlsx(_rows(10), cols, row_hard_limit=3))
    assert exc.value.detail["error_code"] == "EXPORT_ROW_HARD_LIMIT"


# ─── 中途错误：首字节前 raise，无部分文件（R7.7/R8.6）───────────────────────
def test_stream_mid_iteration_error_raises_before_any_byte():
    svc = ExportService()
    cols = _cols()
    yielded = {"n": 0}

    async def bad():
        yield {"acct": "x", "amt": 1}
        raise RuntimeError("db read error mid-stream")

    async def _run():
        async for _c in svc.stream_xlsx(bad(), cols):
            yielded["n"] += 1

    with pytest.raises(RuntimeError, match="db read error"):
        asyncio.run(_run())
    # 生成器在写盘完成前 raise，未产出任何字节 → 客户端不会得到可误认为完整的文件
    assert yielded["n"] == 0
