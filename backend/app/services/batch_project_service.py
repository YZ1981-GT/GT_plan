"""批量建项兼容入口；实现按工作簿、规划、执行和导出拆分。"""
from io import BytesIO

import anyio

from app.services import batch_project_workbook as workbook_io
from app.services.batch_project_export import export_group_tree, export_projects
from app.services.batch_project_plan import analyze_batch, parse_and_import, validate_batch
from app.services.batch_project_types import (
    BatchActionSummary,
    BatchImportFailure,
    BatchImportResult,
    BatchValidateResponse,
    RowError,
    RowWarning,
)

_TEMPLATE_COLUMNS = workbook_io.EXTENDED_COLUMNS
ParsedRow = workbook_io.ParsedRow
_load_data_sheet = lambda file_bytes: workbook_io.load_data_sheet(file_bytes).rows
_is_blank_row = workbook_io.is_blank_row
_parse_row = workbook_io.parse_row


async def generate_template(*, mode: str = "project") -> BytesIO:
    return await anyio.to_thread.run_sync(lambda: workbook_io.generate_template(mode=mode))


__all__ = [
    "BatchActionSummary", "BatchImportFailure", "BatchImportResult",
    "BatchValidateResponse", "ParsedRow", "RowError", "RowWarning",
    "_TEMPLATE_COLUMNS", "_is_blank_row", "_load_data_sheet", "_parse_row",
    "analyze_batch", "export_group_tree", "export_projects", "generate_template",
    "parse_and_import", "validate_batch",
]
