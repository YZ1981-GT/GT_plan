# -*- coding: utf-8 -*-
import sys, time, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print("1. importing...", flush=True)
from app.services.smart_import_engine import smart_parse_sheet
print("2. import done", flush=True)

import openpyxl
p = Path(__file__).resolve().parent.parent.parent / "数据" / "科目余额表-重庆和平药房连锁有限责任公司2025.xlsx"
print(f"3. reading file: {p}", flush=True)
with open(p, "rb") as f:
    content = f.read()
print(f"4. file read: {len(content)} bytes", flush=True)

wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
ws = wb["sheet1"]
print(f"5. workbook opened: max_row={ws.max_row}", flush=True)

t0 = time.time()
result = smart_parse_sheet(ws)
print(f"6. done: {time.time()-t0:.1f}s, rows={result['row_count']}", flush=True)
wb.close()
