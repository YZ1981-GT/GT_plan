"""调试：测试余额表解析结果"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import openpyxl, io
from app.services.smart_import_engine import (
    smart_parse_sheet, smart_match_column, _guess_data_type,
    detect_header_rows, merge_header_rows,
)

# 读取余额表文件
filepath = r"D:\GT_workplan\科目余额表-重庆和平药房连锁有限责任公司2024.xlsx"
if not os.path.exists(filepath):
    # 尝试其他可能的路径
    import glob
    candidates = glob.glob(r"D:\**\科目余额表*2024*.xlsx", recursive=True)
    if candidates:
        filepath = candidates[0]
    else:
        print("找不到余额表文件，请手动指定路径")
        sys.exit(1)

print(f"文件: {filepath}")
wb = openpyxl.load_workbook(filepath, data_only=True)

for ws in wb.worksheets:
    print(f"\n=== Sheet: {ws.title} ===")
    
    # 表头检测
    hs, hc = detect_header_rows(ws)
    print(f"  header_start={hs}, header_count={hc}")
    
    headers = merge_header_rows(ws, hs, hc)
    print(f"  headers ({len(headers)}): {headers[:15]}...")
    
    # 列名映射
    cm = {}
    for h in headers:
        mapped = smart_match_column(h)
        if mapped:
            cm[h] = mapped
    print(f"  mapped ({len(cm)}): {cm}")
    
    # 数据类型
    mapped_fields = set(cm.values())
    dt = _guess_data_type(mapped_fields)
    print(f"  mapped_fields: {mapped_fields}")
    print(f"  data_type: {dt}")
    
    # 解析前5行数据
    parsed = smart_parse_sheet(ws)
    print(f"  parsed row_count: {parsed['row_count']}")
    print(f"  parsed data_type: {parsed['data_type']}")
    if parsed['rows']:
        print(f"  first row keys: {list(parsed['rows'][0].keys())[:10]}")
        print(f"  first row vals: {list(parsed['rows'][0].values())[:10]}")

wb.close()
