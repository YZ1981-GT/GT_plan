"""ZIP 解压递归解析器。

职责（见 design.md §11 / Sprint 2 Task 23）：

- 递归解压，逐个文件 yield (filename, content) 供调用方决定用 excel_parser 或 csv_parser。
- 修复中文文件名乱码：ZIP 存储为 CP437 字节时按 `gbk` 解码还原中文（需求 14）。
- 跳过目录和不支持的文件扩展名（只处理 .xlsx/.xlsm/.csv/.tsv）。
"""

from __future__ import annotations

import io
import logging
import os
import zipfile
from typing import Generator

__all__ = ["iter_zip_entries"]

logger = logging.getLogger(__name__)

# Supported file extensions inside ZIP archives
_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".xlsx", ".xlsm", ".csv", ".tsv"})


def _decode_zip_entry_name(info: zipfile.ZipInfo) -> str:
    """Decode ZIP entry name: UTF-8 flag takes priority; otherwise CP437→gbk re-decode.

    Duplicated from detector.py (private helper there) — same 5-line logic,
    kept in sync by design. See detector.py::_decode_zip_entry_name for the
    canonical implementation.
    """
    # flag_bits bit 11 (0x800) = 1 means UTF-8 encoded filename
    if info.flag_bits & 0x800:
        return info.filename

    # zipfile defaults to CP437 decoding; Chinese filenames get garbled.
    # Re-encode to CP437 bytes then decode as gbk.
    try:
        raw = info.filename.encode("cp437")
        return raw.decode("gbk")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return info.filename


def iter_zip_entries(
    content: bytes,
) -> Generator[tuple[str, bytes], None, None]:
    """Yield (entry_filename, entry_content) for each supported file in the ZIP.

    - Skips directories
    - Skips unsupported extensions (only .xlsx/.xlsm/.csv/.tsv)
    - Handles CP437→gbk filename re-decoding for Chinese filenames
    - Yields raw bytes for each entry (caller decides whether to use
      excel_parser or csv_parser)

    Parameters
    ----------
    content : bytes
        Raw ZIP file content.

    Yields
    ------
    tuple[str, bytes]
        (decoded_filename, raw_entry_bytes) for each supported entry.
    """
    zf = None
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))

        for info in zf.infolist():
            # Skip directories
            if info.is_dir():
                continue

            # Decode filename (CP437→gbk fix for Chinese)
            decoded_name = _decode_zip_entry_name(info)

            # Check extension
            ext = os.path.splitext(decoded_name)[1].lower()
            if ext not in _SUPPORTED_EXTENSIONS:
                logger.debug("zip: skipping unsupported entry %s", decoded_name)
                continue

            # Read entry content
            try:
                entry_content = zf.read(info.filename)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "zip: failed to read entry %s", decoded_name
                )
                raise RuntimeError(
                    f"Failed to read ZIP entry '{decoded_name}': {exc}"
                ) from exc

            yield decoded_name, entry_content

    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"Invalid or corrupted ZIP file: {exc}") from exc
    except RuntimeError:
        # Re-raise our own RuntimeErrors
        raise
    except Exception as exc:
        logger.exception("ZIP parsing failed")
        raise RuntimeError(f"ZIP parsing failed: {exc}") from exc
    finally:
        if zf is not None:
            try:
                zf.close()
            except Exception:  # noqa: BLE001
                pass
