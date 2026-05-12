"""Excel 流式解析器（python-calamine / Rust）— B3 大账套加速方案 A。

职责：
- 与 `excel_parser.py`（openpyxl）行为等价，纯粹替换底层解析引擎。
- 真实样本实测（见 `scripts/b3_calamine_smoke.py`）比 openpyxl 快 ~3.2-3.4×，
  YG2101 128MB 从 76s → 22s。

契约：
- `iter_excel_rows_from_path(path, sheet_name, *, data_start_row, chunk_size,
  forward_fill_cols)` — 与 openpyxl 版签名完全一致。
- 支持 forward_fill_cols（合并单元格向下填充）。
- chunk_size 默认 50k 行（与 openpyxl 对齐）。

注意：
- calamine 一次性把整个 sheet 读为 list（不是真流式），对 YG2101 Sheet1
  内存占用约 100-200MB（673k 行），可接受（远低于 xlsx 原始 ZIP 解压后 ~600MB）。
- calamine 不支持"只读模式"vs"full-load"的回退概念，它总是全量读；对
  合并表头的处理比 openpyxl 稳定（直接返回展平值）。
- 空行（全 None）calamine 保留，与 openpyxl 一致；由 detector/validator 处理。
"""

from __future__ import annotations

import logging
from typing import Any, Generator

__all__ = [
    "iter_excel_rows_from_path_calamine",
    "iter_excel_rows_calamine",
    "CHUNK_SIZE",
]

logger = logging.getLogger(__name__)

CHUNK_SIZE = 50_000  # 对齐 openpyxl 版


def _iter_sheet_rows(
    sheet_data: list[list[Any]],
    *,
    data_start_row: int,
    chunk_size: int,
    forward_fill_cols: list[int] | None = None,
) -> Generator[list[list[Any]], None, None]:
    """sheet 完整数据（已 to_python）→ 按 chunk 切片 + forward-fill。"""
    ff_cols = set(forward_fill_cols or [])
    prev_values: dict[int, Any] = {}
    chunk: list[list[Any]] = []

    # data_start_row 是 0-based header 之后的第一行
    for idx, row in enumerate(sheet_data):
        if idx < data_start_row:
            continue
        row_list = list(row)

        if ff_cols:
            for col_idx in ff_cols:
                if col_idx < len(row_list):
                    val = row_list[col_idx]
                    if val is None or (isinstance(val, str) and not val.strip()):
                        if col_idx in prev_values:
                            row_list[col_idx] = prev_values[col_idx]
                    else:
                        prev_values[col_idx] = val

        chunk.append(row_list)
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []

    if chunk:
        yield chunk


def _load_sheet(path_or_bytes, sheet_name: str) -> list[list[Any]]:
    """用 calamine 读取整个 sheet 为 list of rows。

    calamine cell 类型：str / int / float / bool / datetime / None。
    保持原值不强制转字符串（与 openpyxl 行为一致）。
    """
    from python_calamine import CalamineWorkbook

    if isinstance(path_or_bytes, (bytes, bytearray)):
        # calamine 有 from_filelike 或 from_path；bytes 场景用 BytesIO
        import io as _io

        wb = CalamineWorkbook.from_filelike(_io.BytesIO(path_or_bytes))
    else:
        wb = CalamineWorkbook.from_path(str(path_or_bytes))

    if sheet_name not in wb.sheet_names:
        raise RuntimeError(
            f"Sheet '{sheet_name}' not found. Available: {list(wb.sheet_names)}"
        )

    sheet = wb.get_sheet_by_name(sheet_name)
    return sheet.to_python()


def iter_excel_rows_from_path_calamine(
    path: str,
    sheet_name: str,
    *,
    data_start_row: int = 1,
    chunk_size: int = CHUNK_SIZE,
    forward_fill_cols: list[int] | None = None,
) -> Generator[list[list[Any]], None, None]:
    """Yield chunks from xlsx path via calamine.

    接口与 `excel_parser.iter_excel_rows_from_path` 完全一致，可直接替换。
    """
    logger.info("calamine loading sheet '%s' from %s", sheet_name, path)
    try:
        sheet_data = _load_sheet(path, sheet_name)
    except Exception as exc:
        logger.exception("calamine load failed for '%s'", sheet_name)
        raise RuntimeError(
            f"calamine parsing failed for sheet '{sheet_name}': {exc}"
        ) from exc

    yield from _iter_sheet_rows(
        sheet_data,
        data_start_row=data_start_row,
        chunk_size=chunk_size,
        forward_fill_cols=forward_fill_cols,
    )


def iter_excel_rows_calamine(
    content: bytes,
    sheet_name: str,
    *,
    data_start_row: int = 1,
    chunk_size: int = CHUNK_SIZE,
    forward_fill_cols: list[int] | None = None,
) -> Generator[list[list[Any]], None, None]:
    """Yield chunks from xlsx bytes via calamine。"""
    logger.info("calamine loading sheet '%s' from bytes (%d)",
                sheet_name, len(content))
    try:
        sheet_data = _load_sheet(content, sheet_name)
    except Exception as exc:
        logger.exception("calamine load failed for '%s'", sheet_name)
        raise RuntimeError(
            f"calamine parsing failed for sheet '{sheet_name}': {exc}"
        ) from exc

    yield from _iter_sheet_rows(
        sheet_data,
        data_start_row=data_start_row,
        chunk_size=chunk_size,
        forward_fill_cols=forward_fill_cols,
    )
