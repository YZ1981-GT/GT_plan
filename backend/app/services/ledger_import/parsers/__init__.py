"""流式解析器子包 — Excel / CSV / ZIP。

职责：按 chunk 生成行数据供 writer 流式写入 PG（见 design.md §2 / Sprint 2 Task 21-23）。

Public API:
- iter_excel_rows: openpyxl read_only 流式按 chunk 生成 Excel 行数据
- iter_csv_rows: csv.reader generator 流式读 + 编码自适应
- iter_zip_entries: ZIP 解压递归，CP437→gbk 文件名修复
"""

from .csv_parser import CHUNK_SIZE as CSV_CHUNK_SIZE
from .csv_parser import iter_csv_rows
from .excel_parser import CHUNK_SIZE as EXCEL_CHUNK_SIZE
from .excel_parser import iter_excel_rows
from .zip_parser import iter_zip_entries

__all__ = [
    "iter_excel_rows",
    "iter_csv_rows",
    "iter_zip_entries",
    "EXCEL_CHUNK_SIZE",
    "CSV_CHUNK_SIZE",
]
