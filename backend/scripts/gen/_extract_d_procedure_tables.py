"""一次性脚本：从 D 类 xlsx 模板提取 D0A~D7A 程序表步骤

使用 python_calamine 读取各 xlsx 中的程序表 sheet，提取 seq/content/ref_index。
输出 JSON 格式供合并到 procedure_table_templates.json。

执行：python backend/scripts/gen/_extract_d_procedure_tables.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from python_calamine import CalamineWorkbook

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "wp_templates" / "D"
OUTPUT_FILE = Path(__file__).parent.parent.parent / "data" / "_d_procedure_tables_extracted.json"

# ─── 模板文件 → sheet 名映射 ────────────────────────────────────────────────
PROCEDURE_SHEETS = {
    "D0A": {
        "file": "D0 收入循环函证.xlsx",
        "sheet_pattern": r"函证程序表D0A|D0A",
    },
    "D1A": {
        "file": "D1 应收票据.xlsx",
        "sheet_pattern": r"程序表D1A|应收票据.*程序表|D1A",
    },
    "D2A": {
        "file": "D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx",
        "sheet_pattern": r"程序表D2A|应收账款.*程序表|D2A",
    },
    "D3A": {
        "file": "D3 预收账款.xlsx",
        "sheet_pattern": r"程序表D3A|预收账款.*程序表|D3A",
    },
    "D4A": {
        "file": "D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx",
        "sheet_pattern": r"程序表D4A|营业收入.*程序表|D4A",
    },
    "D5A": {
        "file": "D5 应收款项融资.xlsx",
        "sheet_pattern": r"程序表D5A|应收款项融资.*程序表|D5A",
    },
    "D6A": {
        "file": "D6 合同资产.xlsx",
        "sheet_pattern": r"程序表D6A|合同资产.*程序表.*D6A|D6A",
    },
    "D7A": {
        "file": "D6 合同资产.xlsx",  # D7A physically in D6.xlsx
        "sheet_pattern": r"程序表D7A|合同负债.*程序表|D7A",
    },
}

NAMES = {
    "D0A": "收入循环函证程序表",
    "D1A": "应收票据实质性程序表",
    "D2A": "应收账款实质性程序表",
    "D3A": "预收账款实质性程序表",
    "D4A": "营业收入实质性程序表",
    "D5A": "应收款项融资实质性程序表",
    "D6A": "合同资产实质性程序表",
    "D7A": "合同负债实质性程序表",
}


def find_sheet(wb: CalamineWorkbook, pattern: str) -> str | None:
    """在工作簿中找到匹配 pattern 的 sheet 名。"""
    for name in wb.sheet_names:
        if re.search(pattern, name, re.IGNORECASE):
            return name
    return None


def extract_procedure_steps(rows: list[list]) -> list[dict]:
    """从程序表 sheet 的行数据中提取步骤。

    通用逻辑：
    - 找到表头行（含"序号"或"编号"或"步骤"）
    - 之后的行：第一列=seq，第二列或含"审计程序"的列=content，最后一列或含"索引"的列=ref_index
    """
    if not rows:
        return []

    # Find header row
    header_idx = -1
    seq_col = -1
    content_col = -1
    ref_col = -1

    for i, row in enumerate(rows):
        row_str = [str(c).strip() if c is not None else "" for c in row]
        # Look for header indicators
        for j, cell in enumerate(row_str):
            if cell in ("序号", "编号", "步骤号", "No.", "序"):
                header_idx = i
                seq_col = j
            elif "审计程序" in cell or "程序内容" in cell or "实质性程序" in cell or "具体审计程序" in cell:
                content_col = j
            elif "索引" in cell or "底稿索引" in cell or "工作底稿索引" in cell or "ref" in cell.lower():
                ref_col = j
        if header_idx >= 0:
            break

    # Fallback: try first row as header
    if header_idx < 0:
        header_idx = 0
        # Try to detect columns from first non-empty row pattern
        for i, row in enumerate(rows[:5]):
            row_str = [str(c).strip() if c is not None else "" for c in row]
            if any("程序" in s for s in row_str):
                header_idx = i
                break

    if seq_col < 0:
        seq_col = 0
    if content_col < 0:
        content_col = min(1, len(rows[0]) - 1) if rows else 1
    if ref_col < 0:
        ref_col = len(rows[0]) - 1 if rows and rows[0] else 2

    # Extract steps from rows after header
    items = []
    seq_counter = 0
    for row in rows[header_idx + 1:]:
        if not row or len(row) <= content_col:
            continue

        # Get seq
        raw_seq = row[seq_col] if seq_col < len(row) else None
        # Get content
        raw_content = row[content_col] if content_col < len(row) else None
        # Get ref_index
        raw_ref = row[ref_col] if ref_col < len(row) else None

        content = str(raw_content).strip() if raw_content else ""
        if not content or content in ("None", "", "nan"):
            continue

        # Skip rows that look like sub-headers or notes
        if content.startswith("注：") or content.startswith("说明") or content.startswith("备注"):
            continue

        # Parse seq number
        seq_str = str(raw_seq).strip() if raw_seq else ""
        try:
            seq_num = int(float(seq_str))
        except (ValueError, TypeError):
            # If it looks like a sub-step marker (1.1, a, etc), use counter
            seq_counter += 1
            seq_num = seq_counter

        # Parse ref_index
        ref_index = str(raw_ref).strip() if raw_ref else None
        if ref_index in ("None", "", "nan", "0", "0.0"):
            ref_index = None

        items.append({
            "seq": seq_num,
            "content": content,
            "ref_index": ref_index,
            "auto_data_source": None,
            "applicable_default": "yes",
        })

    return items


def main():
    results = {}

    for code, config in PROCEDURE_SHEETS.items():
        filepath = TEMPLATE_DIR / config["file"]
        if not filepath.exists():
            print(f"⚠️  文件不存在: {filepath.name}")
            results[code] = {"name": NAMES[code], "items": [], "error": "file_not_found"}
            continue

        try:
            wb = CalamineWorkbook.from_path(str(filepath))
        except Exception as e:
            print(f"⚠️  无法打开: {filepath.name}: {e}")
            results[code] = {"name": NAMES[code], "items": [], "error": str(e)}
            continue

        sheet_name = find_sheet(wb, config["sheet_pattern"])
        if not sheet_name:
            # Try broader search
            print(f"  ⚠️  未找到匹配 sheet for {code} in {filepath.name}")
            print(f"     可用 sheets: {wb.sheet_names}")
            # Try to find any sheet with "程序" in name
            for sn in wb.sheet_names:
                if "程序" in sn:
                    sheet_name = sn
                    print(f"     → 使用 fallback: {sn}")
                    break
            if not sheet_name:
                results[code] = {"name": NAMES[code], "items": [], "error": "sheet_not_found"}
                continue

        try:
            data = wb.get_sheet_by_name(sheet_name).to_python()
        except Exception as e:
            print(f"⚠️  无法读取 sheet {sheet_name}: {e}")
            results[code] = {"name": NAMES[code], "items": [], "error": str(e)}
            continue

        items = extract_procedure_steps(data)
        results[code] = {"name": NAMES[code], "items": items}
        print(f"  ✓ {code}: {sheet_name} → {len(items)} 步骤")

    # Save extracted data
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n输出: {OUTPUT_FILE}")
    print(f"总计: {sum(len(v['items']) for v in results.values())} 步骤 / {len(results)} 程序表")


if __name__ == "__main__":
    main()
