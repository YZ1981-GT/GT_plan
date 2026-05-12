"""B3 剖析：YG2101 级别真实数据各阶段耗时分布。

用真实尺寸（650k 行 × 45 列 × 17 映射）模拟 pipeline 各阶段。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    print(f"\n=== pipeline 各阶段耗时分布（YG2101 级别） ===\n")

    # 1. calamine 解析 650k 行序时账
    from python_calamine import CalamineWorkbook

    t = time.time()
    wb = CalamineWorkbook.from_path(str(
        ROOT / "数据/YG2101-重庆医药集团四川医药有限公司2025年-科目余额表+序时账.xlsx"
    ))
    sheet = wb.get_sheet_by_name("序时账")
    rows = sheet.to_python()
    parse_elapsed = time.time() - t
    print(f"1. calamine 解析序时账: {parse_elapsed:.1f}s  {len(rows)} 行")

    # 2. 按 pipeline 流程：dict 化 + prepare + validate + convert
    from app.services.ledger_import.writer import prepare_rows_with_raw_extra
    from app.services.ledger_import.validator import validate_l1
    from app.services.ledger_import.converter import convert_ledger_rows

    headers = [str(c) for c in rows[0]]
    data = rows[1:]
    chunk_size = 50_000

    # 构造 mapping（按真实 17/45 比例）
    col_mapping = {
        "科目编码": "account_code",
        "科目名称": "account_name",
        "凭证日期": "voucher_date",
        "凭证号": "voucher_no",
        "借方发生额": "debit_amount",
        "贷方发生额": "credit_amount",
        "摘要": "summary",
    }
    # 只保留 headers 中存在的
    col_mapping = {k: v for k, v in col_mapping.items() if k in headers}
    print(f"   实际列 {len(headers)} | 映射 {len(col_mapping)} = {len(col_mapping)/len(headers)*100:.0f}%")

    prepare_tot = 0.0
    validate_tot = 0.0
    convert_tot = 0.0
    dict_tot = 0.0
    total_ledger = 0
    total_aux = 0

    for chunk_start in range(0, len(data), chunk_size):
        chunk = data[chunk_start:chunk_start + chunk_size]

        t = time.time()
        dict_rows = []
        for r in chunk:
            row_dict = {}
            for i, val in enumerate(r):
                if i < len(headers):
                    row_dict[headers[i]] = val
                else:
                    row_dict[f"col_{i}"] = val
            dict_rows.append(row_dict)
        dict_tot += time.time() - t

        t = time.time()
        std_rows, _ = prepare_rows_with_raw_extra(dict_rows, col_mapping, headers)
        prepare_tot += time.time() - t

        t = time.time()
        findings, cleaned = validate_l1(
            std_rows, "ledger", column_mapping=col_mapping,
            file_name="yg2101", sheet_name="序时账",
        )
        validate_tot += time.time() - t

        t = time.time()
        ledger, aux, _ = convert_ledger_rows(cleaned)
        convert_tot += time.time() - t
        total_ledger += len(ledger)
        total_aux += len(aux)

    print(f"2. dict 化: {dict_tot:.1f}s")
    print(f"3. prepare_rows_with_raw_extra: {prepare_tot:.1f}s")
    print(f"4. validate_l1: {validate_tot:.1f}s")
    print(f"5. convert_ledger_rows: {convert_tot:.1f}s → ledger={total_ledger} aux={total_aux}")
    print(f"\n合计 Python 后处理: {dict_tot+prepare_tot+validate_tot+convert_tot:.1f}s")
    print(f"Python 后处理 + calamine 解析: {dict_tot+prepare_tot+validate_tot+convert_tot+parse_elapsed:.1f}s")

    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
