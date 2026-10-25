from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import xlrd

ROOT = Path(__file__).resolve().parents[3]
MAPPING_PATH = ROOT / "backend/data/wp_account_mapping.json"
S34_CONFIG_PATH = ROOT / "audit-platform/frontend/src/components/workpaper/s34-ipo-bundle/S34_TAB_CONFIG.ts"
S17_PATHS = [
    ROOT / "backend/wp_templates/S/S17 非经常性损益.xls",
    ROOT / "数据/致同通用审计程序及底稿模板（2025年修订）/1.致同审计程序及底稿模板（2025年）/6.特定项目程序（S）/S17 非经常性损益.xls",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cell_value(cell):
    value = cell.value
    if cell.ctype == xlrd.XL_CELL_DATE:
        return {"type": "date", "value": value}
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return {"type": "boolean", "value": bool(value)}
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return {"type": "error", "value": value}
    if cell.ctype == xlrd.XL_CELL_EMPTY:
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def nonempty_row(sheet, row_index):
    values = []
    for col_index in range(sheet.ncols):
        value = cell_value(sheet.cell(row_index, col_index))
        if value not in (None, ""):
            values.append({"col": col_index, "value": value})
    return values


def workbook_summary(path: Path):
    book = xlrd.open_workbook(str(path), formatting_info=False)
    sheets = []
    for sheet in book.sheets():
        rows = []
        for row_index in range(sheet.nrows):
            values = nonempty_row(sheet, row_index)
            if values:
                rows.append({"row": row_index + 1, "values": values})
        sheets.append({
            "name": sheet.name,
            "nrows": sheet.nrows,
            "ncols": sheet.ncols,
            "nonempty_rows": rows,
        })
    return {"path": str(path.relative_to(ROOT)), "size": path.stat().st_size, "sha256": sha256(path), "sheets": sheets}


def extract_s34_clearance():
    text = S34_CONFIG_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        r"wpCode:\s*'(?P<parent>S34-[^']+)'\s*,\s*"
        r"hasSubTable:\s*true\s*,\s*"
        r"subSheets:\s*\[(?P<subs>[^\]]*)\]",
        re.DOTALL,
    )
    parents = []
    for match in pattern.finditer(text):
        sub_sheets = re.findall(r"'([^']+)'", match.group("subs"))
        parents.append({"parent": match.group("parent"), "sub_sheets": sub_sheets})
    return {
        "source": str(S34_CONFIG_PATH.relative_to(ROOT)),
        "sha256": sha256(S34_CONFIG_PATH),
        "parents": parents,
        "parent_count": len(parents),
        "contains_s34_3": any(item["parent"] == "S34-3" for item in parents),
    }


def extract_mapping():
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    mappings = data["mappings"]
    s_entries = [item for item in mappings if item.get("cycle") == "S"]
    return {
        "source": str(MAPPING_PATH.relative_to(ROOT)),
        "sha256": sha256(MAPPING_PATH),
        "version": data.get("version"),
        "mapping_count": len(mappings),
        "s_count": len(s_entries),
        "s17": [item for item in s_entries if item.get("wp_code") == "S17"],
        "s34": [item for item in s_entries if str(item.get("wp_code", "")).startswith("S34")],
        "s_entries": s_entries,
    }


if __name__ == "__main__":
    result = {
        "mapping": extract_mapping(),
        "s34_clearance": extract_s34_clearance(),
        "s17_workbooks": [],
        "missing_s17_paths": [],
    }
    for path in S17_PATHS:
        if path.exists():
            result["s17_workbooks"].append(workbook_summary(path))
        else:
            result["missing_s17_paths"].append(str(path.relative_to(ROOT)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
