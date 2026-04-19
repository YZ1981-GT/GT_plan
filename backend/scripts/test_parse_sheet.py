# -*- coding: utf-8 -*-
import sys, time, io, openpyxl
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.smart_import_engine import smart_parse_sheet, convert_balance_rows

with open(Path(__file__).resolve().parent.parent.parent / "数据" / "科目余额表-重庆和平药房连锁有限责任公司2025.xlsx", "rb") as f:
    content = f.read()
wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
ws = wb["sheet1"]

t0 = time.time()
result = smart_parse_sheet(ws)
t1 = time.time()
print(f"smart_parse_sheet: {t1-t0:.1f}s")
print(f"data_type={result['data_type']}, rows={result['row_count']}, year={result['year']}")
print(f"headers: {result['headers']}")

t2 = time.time()
bal, aux_bal = convert_balance_rows(result["rows"])
print(f"convert_balance_rows: {time.time()-t2:.1f}s")
print(f"balance: {len(bal)}, aux_balance: {len(aux_bal)}")
wb.close()
