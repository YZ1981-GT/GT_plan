"""Small real XLSX carrier for publish-hash tests (no database)."""
import io
import uuid
from openpyxl import Workbook
from openpyxl.worksheet.table import Table
from app.services.workpaper_sync.excel_instrumentation import GT_SYNC_SHEET_NAME


def workbook_fixture(sheet_key="g7-disclosure", rows=2):
    anchors = dict(sheet_key=sheet_key, table_name="GT_G1_ROWS",
                   uuid_column_letter="N", metadata_sheet=GT_SYNC_SHEET_NAME)
    wb = Workbook()
    ws = wb.active
    ws.title = "Managed"
    for col in range(1, 15):
        ws.cell(7, col, f"column_{col}")
    for row in range(8, 8 + rows):
        ws.cell(row, 7, f"row_{row}")
        ws.cell(row, 8, row * 10)
        ws.cell(row, 14, str(uuid.UUID(int=row)))
    ws.column_dimensions["N"].hidden = True
    ws.add_table(Table(displayName=anchors["table_name"], ref=f"A7:N{7 + rows}"))
    wb.create_sheet(GT_SYNC_SHEET_NAME).sheet_state = "veryHidden"
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue(), anchors
