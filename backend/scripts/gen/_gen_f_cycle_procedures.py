"""Generate F-cycle procedure table entries for procedure_table_templates.json.

One-time script: extracts F0A~F5A procedure steps from xlsx templates and adds them
to the procedure_table_templates.json file.
"""
import json
import python_calamine
from python_calamine import CalamineWorkbook
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent


def find_sheet(wb, keyword):
    for s in wb.sheet_names:
        if keyword in s:
            return s
    return None


def extract_procedure_table(filepath, keyword):
    wb = CalamineWorkbook.from_path(str(filepath))
    sheet_name = find_sheet(wb, keyword)
    if not sheet_name:
        raise ValueError(f"No sheet with keyword '{keyword}' in {filepath}")
    sheet = wb.get_sheet_by_name(sheet_name)
    rows = sheet.to_python()

    # Find header row with '底稿索引号'
    header_idx = None
    ref_col = None
    content_col = None
    for i, row in enumerate(rows):
        for j, c in enumerate(row):
            if c and str(c).strip() == "底稿索引号":
                header_idx = i
                ref_col = j
                break
        if header_idx is not None:
            break

    if header_idx is not None:
        for j, c in enumerate(rows[header_idx]):
            if c and "审计程序" in str(c).strip():
                content_col = j
                break

    if content_col is None:
        content_col = 1

    results = []
    for i, row in enumerate(rows[header_idx + 1 :], start=header_idx + 1):
        if not row or row[0] is None:
            continue
        seq = str(row[0]).strip()
        if not seq or not seq[0].isdigit():
            continue
        if seq.endswith(".0"):
            seq = seq[:-2]

        content = (
            str(row[content_col]).strip()
            if len(row) > content_col and row[content_col]
            else ""
        )
        ref_idx = (
            str(row[ref_col]).strip()
            if len(row) > ref_col and row[ref_col]
            else ""
        )
        if ref_idx == "None":
            ref_idx = ""

        # Normalize newlines in ref_index
        ref_idx = ref_idx.replace("\n", "/")
        while "//" in ref_idx:
            ref_idx = ref_idx.replace("//", "/")
        if ref_idx.endswith("/"):
            ref_idx = ref_idx[:-1]
        if ref_idx.startswith("/"):
            ref_idx = ref_idx[1:]

        results.append(
            {"seq": int(seq) if seq.isdigit() else seq, "content": content, "ref_index": ref_idx}
        )
    return results


def build_items(steps, auto_source_fn=None):
    """Convert raw extracted steps into procedure_table_templates items."""
    items = []
    for s in steps:
        ref = s.get("ref_index", "")
        auto = auto_source_fn(s, ref) if auto_source_fn else None
        items.append(
            {
                "seq": s["seq"],
                "content": s["content"],
                "ref_index": ref if ref else None,
                "auto_data_source": auto,
                "applicable_default": "yes",
            }
        )
    return items


def f0a_auto(s, ref):
    """F0A: confirmation-related steps get confirmation_summary_for_cycle."""
    if any(x in ref for x in ["F0-1", "F0-2", "F0-3", "F0-4", "F0-5", "F0-6"]):
        return "confirmation_summary_for_cycle"
    if "F0-8" in ref or (s["seq"] >= 10 and "风险" in s["content"]):
        return "risk_for_cycle"
    return None


def f1a_auto(s, ref):
    """F1A: control test for T1, confirmation for F0."""
    if "T1" in ref:
        return "control_test_result_for_cycle"
    if ref == "F0" or ("F0" in ref and "F0-" not in ref):
        return "confirmation_summary_for_cycle"
    return None


def f2a_auto(s, ref):
    """F2A: control test for T1."""
    if "T1" in ref:
        return "control_test_result_for_cycle"
    return None


def f3a_auto(s, ref):
    """F3A: control test for T1, confirmation for F0."""
    if "T1" in ref:
        return "control_test_result_for_cycle"
    if ref == "F0" or ("F0" in ref and "F0-" not in ref):
        return "confirmation_summary_for_cycle"
    return None


def f4a_auto(s, ref):
    """F4A: control test for T1, confirmation for F0."""
    if "T1" in ref:
        return "control_test_result_for_cycle"
    if ref == "F0" or ("F0" in ref and "F0-" not in ref):
        return "confirmation_summary_for_cycle"
    return None


def f5a_auto(s, ref):
    """F5A: control test for T1."""
    if "T1" in ref:
        return "control_test_result_for_cycle"
    return None


def main():
    templates_dir = BASE / "wp_templates" / "F"

    # Extract from xlsx
    f0a_steps = extract_procedure_table(
        templates_dir / "F0 存货循环函证.xlsx", "F0A"
    )
    f1a_steps = extract_procedure_table(
        templates_dir / "F1 预付账款.xlsx", "F1A"
    )
    f2a_steps = extract_procedure_table(
        templates_dir / "F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx",
        "F2A",
    )
    f3a_steps = extract_procedure_table(
        templates_dir / "F3 应付票据.xlsx", "F3A"
    )
    f4a_steps = extract_procedure_table(
        templates_dir / "F4 应付账款.xlsx", "F4A"
    )
    f5a_steps = extract_procedure_table(
        templates_dir / "F5 营业成本.xlsx", "F5A"
    )

    print(f"Extracted: F0A={len(f0a_steps)}, F1A={len(f1a_steps)}, F2A={len(f2a_steps)}, "
          f"F3A={len(f3a_steps)}, F4A={len(f4a_steps)}, F5A={len(f5a_steps)}")

    # Build items with auto_data_source
    f0a_items = build_items(f0a_steps, f0a_auto)
    f1a_items = build_items(f1a_steps, f1a_auto)
    f2a_items = build_items(f2a_steps, f2a_auto)
    f3a_items = build_items(f3a_steps, f3a_auto)
    f4a_items = build_items(f4a_steps, f4a_auto)
    f5a_items = build_items(f5a_steps, f5a_auto)

    # Load existing file
    json_path = BASE / "data" / "procedure_table_templates.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Add F-cycle tables
    data["tables"]["F0A"] = {
        "name": "采购存货循环函证程序表",
        "items": f0a_items,
    }
    data["tables"]["F1A"] = {
        "name": "预付账款实质性程序表",
        "items": f1a_items,
    }
    data["tables"]["F2A"] = {
        "name": "存货实质性程序表",
        "items": f2a_items,
    }
    data["tables"]["F3A"] = {
        "name": "应付票据实质性程序表",
        "items": f3a_items,
    }
    data["tables"]["F4A"] = {
        "name": "应付账款实质性程序表",
        "items": f4a_items,
    }
    data["tables"]["F5A"] = {
        "name": "营业成本实质性程序表",
        "items": f5a_items,
    }

    # Update description
    data["description"] = "A/B/D/E/F循环程序表模板定义（含程序步骤+自动填充规则+索引引用）"

    # Write back
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total = len(data["tables"])
    print(f"\nSUCCESS: Added F0A~F5A to procedure_table_templates.json")
    print(f"  Total tables in file: {total}")


if __name__ == "__main__":
    main()
