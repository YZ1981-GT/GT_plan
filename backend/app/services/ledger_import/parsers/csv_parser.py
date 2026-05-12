"""CSV 流式解析器。

职责（见 design.md §11 / §17 / Sprint 2 Task 22）：

- 调用 `encoding_detector.decode_content` 自适应编码。
- generator 流式读（`csv.reader` + chunked yield），避免一次性加载大文件。
- 支持 `,` / `;` / `\\t` 多分隔符自动探测（csv.Sniffer 前 4KB 采样）。

每个 chunk 是一个 list[list[str]]，每行是一个 list of string values。
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Generator

from ..encoding_detector import decode_content

__all__ = ["iter_csv_rows", "CHUNK_SIZE"]

logger = logging.getLogger(__name__)

CHUNK_SIZE = 50_000  # rows per chunk (design §11)

# Bytes to sample for delimiter sniffing
_SNIFF_BYTES = 4096


def _detect_delimiter(text: str) -> str:
    """Detect CSV delimiter using csv.Sniffer on first 4KB, fallback to ','."""
    sample = text[:_SNIFF_BYTES]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def iter_csv_rows(
    content: bytes,
    *,
    data_start_row: int = 1,
    chunk_size: int = CHUNK_SIZE,
    delimiter: str | None = None,
) -> Generator[list[list[str]], None, None]:
    """Yield chunks of CSV rows as lists of strings.

    Uses encoding_detector.decode_content for encoding detection.
    Uses csv.Sniffer for delimiter detection if not provided.
    Skips rows before data_start_row (0-based).
    Generator-based: only holds one chunk in memory at a time.

    Parameters
    ----------
    content : bytes
        Raw CSV/TSV file content.
    data_start_row : int
        0-based row index where data starts. Rows before this (e.g. header
        rows already processed by detector) are skipped.
    chunk_size : int
        Maximum number of rows per yielded chunk.
    delimiter : str | None
        Explicit delimiter. If None, auto-detected via csv.Sniffer.

    Yields
    ------
    list[list[str]]
        A chunk of rows, each row being a list of string cell values.
    """
    # Decode bytes to text using encoding detector
    text, encoding, confidence = decode_content(content)

    if text is None:
        raise RuntimeError(
            "CSV encoding detection failed: unable to decode file content. "
            f"Best guess encoding: {encoding} (confidence: {confidence:.2f})"
        )

    logger.debug(
        "CSV decoded with encoding=%s confidence=%.2f", encoding, confidence
    )

    # Detect delimiter if not provided
    if delimiter is None:
        delimiter = _detect_delimiter(text)
        logger.debug("CSV delimiter auto-detected: %r", delimiter)

    # Wrap in StringIO for csv.reader
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)

    # Skip rows before data_start_row
    for _ in range(data_start_row):
        try:
            next(reader)
        except StopIteration:
            # File has fewer rows than data_start_row — nothing to yield
            return

    # Stream rows in chunks
    chunk: list[list[str]] = []

    for row in reader:
        chunk.append(row)

        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []

    # Yield final partial chunk
    if chunk:
        yield chunk


def iter_csv_rows_from_path(
    path: str,
    *,
    encoding: str = "utf-8",
    data_start_row: int = 1,
    chunk_size: int = CHUNK_SIZE,
    delimiter: str | None = None,
) -> Generator[list[list[str]], None, None]:
    """Yield chunks of CSV rows from file path — 支持 600MB+ 不全量读入内存。

    Parameters
    ----------
    path : str
        File path to the CSV/TSV file.
    encoding : str
        File encoding (from detector's encoding detection result).
    data_start_row : int
        0-based row index where data starts.
    chunk_size : int
        Maximum number of rows per yielded chunk.
    delimiter : str | None
        Explicit delimiter. If None, auto-detected from first 4KB.

    Yields
    ------
    list[list[str]]
        A chunk of rows.
    """
    with open(path, "r", encoding=encoding, errors="replace", newline="") as f:
        # Detect delimiter if not provided
        if delimiter is None:
            sample = f.read(_SNIFF_BYTES)
            f.seek(0)
            delimiter = _detect_delimiter(sample)
            logger.debug("CSV delimiter auto-detected from path: %r", delimiter)

        reader = csv.reader(f, delimiter=delimiter)

        # Skip rows before data_start_row
        for _ in range(data_start_row):
            try:
                next(reader)
            except StopIteration:
                return

        # Stream rows in chunks
        chunk: list[list[str]] = []
        for row in reader:
            chunk.append(row)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []

        if chunk:
            yield chunk
