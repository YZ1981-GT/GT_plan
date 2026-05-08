"""Excel 流式解析器（openpyxl `read_only=True`）。

职责（见 design.md §11 / Sprint 2 Task 21）：

- 按 chunk 生成行数据（50,000 行/chunk，经验值兼顾内存与 COPY 效率）。
- 复用 `detector.detect_header_row` 的表头结果，从 `data_start_row` 开始流式读。
- 使用 openpyxl read_only=True + iter_rows 避免将整个文件加载到内存。

每个 chunk 是一个 list[list[Any]]，每行是一个 list of cell values
（str/int/float/None — 不在此处强制转 str，由 writer 负责类型转换）。
"""

from __future__ import annotations

import io
import logging
from typing import Any, Generator

import openpyxl

__all__ = ["iter_excel_rows", "CHUNK_SIZE"]

logger = logging.getLogger(__name__)

CHUNK_SIZE = 50_000  # rows per chunk (design §11)


def iter_excel_rows(
    content: bytes,
    sheet_name: str,
    *,
    data_start_row: int = 1,
    chunk_size: int = CHUNK_SIZE,
) -> Generator[list[list[Any]], None, None]:
    """Yield chunks of rows (each chunk is a list of up to chunk_size rows).

    Each row is a list of cell values (str/int/float/None — NOT coerced to str
    here; that's the writer's job).

    Uses openpyxl read_only=True + iter_rows to avoid loading entire file into
    memory. Skips rows before data_start_row (0-based index).

    Parameters
    ----------
    content : bytes
        Raw xlsx/xlsm file content.
    sheet_name : str
        Name of the worksheet to read.
    data_start_row : int
        0-based row index where data starts (rows before this are skipped).
        openpyxl uses 1-based indexing, so we convert internally.
    chunk_size : int
        Maximum number of rows per yielded chunk.

    Yields
    ------
    list[list[Any]]
        A chunk of rows, each row being a list of cell values.
    """
    wb = None
    try:
        wb = openpyxl.load_workbook(
            io.BytesIO(content),
            read_only=True,
            data_only=True,
        )

        if sheet_name not in wb.sheetnames:
            raise RuntimeError(
                f"Sheet '{sheet_name}' not found in workbook. "
                f"Available sheets: {wb.sheetnames}"
            )

        ws = wb[sheet_name]

        # openpyxl is 1-based; data_start_row is 0-based
        # So data starts at openpyxl row = data_start_row + 1
        min_row = data_start_row + 1

        chunk: list[list[Any]] = []

        for row_tuple in ws.iter_rows(min_row=min_row, values_only=True):
            # Convert tuple to list for mutability downstream
            chunk.append(list(row_tuple))

            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []

        # Yield final partial chunk
        if chunk:
            yield chunk

    except RuntimeError:
        # Re-raise our own RuntimeError (sheet not found, etc.)
        raise
    except Exception as exc:
        logger.exception("Excel parsing failed for sheet '%s'", sheet_name)
        raise RuntimeError(
            f"Excel parsing failed for sheet '{sheet_name}': {exc}"
        ) from exc
    finally:
        if wb is not None:
            try:
                wb.close()
            except Exception:  # noqa: BLE001
                pass


def iter_excel_rows_from_path(
    path: str,
    sheet_name: str,
    *,
    data_start_row: int = 1,
    chunk_size: int = CHUNK_SIZE,
) -> Generator[list[list[Any]], None, None]:
    """Yield chunks of rows from xlsx file path — 不全量读入内存。

    openpyxl read_only=True 直接打开文件路径，内存占用与文件大小无关。
    """
    wb = None
    try:
        wb = openpyxl.load_workbook(
            path,  # 直接传路径
            read_only=True,
            data_only=True,
        )

        if sheet_name not in wb.sheetnames:
            raise RuntimeError(
                f"Sheet '{sheet_name}' not found. Available: {wb.sheetnames}"
            )

        ws = wb[sheet_name]
        min_row = data_start_row + 1
        chunk: list[list[Any]] = []

        for row_tuple in ws.iter_rows(min_row=min_row, values_only=True):
            chunk.append(list(row_tuple))
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []

        if chunk:
            yield chunk

    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception("Excel parsing from path failed for sheet '%s'", sheet_name)
        raise RuntimeError(
            f"Excel parsing failed for sheet '{sheet_name}': {exc}"
        ) from exc
    finally:
        if wb is not None:
            try:
                wb.close()
            except Exception:  # noqa: BLE001
                pass
