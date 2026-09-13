"""D4-1 审定表权威模板核定（spec: d4-1-adjudication-bidirectional-writeback-and-formula-io Task 1.1）。

只读 openpyxl 直读 `backend/wp_templates/D/D4-1至D4-4 …xlsx`，钉死 D4-1 审定表的：
- 真实 workbook 内所有 tab 名（确认 D4-1/D4-2/D4-3/D4-4 是否同册）
- D4-1 sheet 的表头行、列坐标、合并单元格
- 行身份（固定行 / 空白可扩行区段）
- 公式格（cell 里以 `=` 开头的）

产出 JSON 到 stdout（供 Task 1.2 契约测试锁定 + 人工核定）。

用法::

    python backend/scripts/diagnose/diagnose_d4_1_template.py
    python backend/scripts/diagnose/diagnose_d4_1_template.py --out evidence/d4_1_template_facts.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("需要 openpyxl: pip install openpyxl", file=sys.stderr)
    sys.exit(2)


def _repo_root() -> Path:
    # backend/scripts/diagnose/xxx.py -> repo root
    return Path(__file__).resolve().parents[3]


def _find_template() -> Path:
    root = _repo_root()
    d_dir = root / "backend" / "wp_templates" / "D"
    # 🔴 D4-1 审定表册文件名是「D4-1至D4-4 …审定表明细表…」，
    #    不能用 glob("D4-1*")——会误命中「D4-12 营业收入-合同检查…」（同以 D4-1 开头）。
    #    用「D4-1至」精确定位审定表明细册。
    for p in sorted(d_dir.glob("D4-1至*.xlsx")):
        if p.name.startswith("~$"):  # 跳过 WPS/Excel 锁文件
            continue
        return p
    raise FileNotFoundError(f"未找到 D4-1 审定表册（D4-1至*.xlsx）于 {d_dir}")


def _cell_facts(ws, max_rows: int = 60, max_cols: int = 26) -> dict:
    """扫描前 max_rows 行 max_cols 列，收集非空单元格、公式格、合并区。"""
    non_empty: list[dict] = []
    formulas: list[dict] = []
    rows = min(ws.max_row or 0, max_rows)
    cols = min(ws.max_column or 0, max_cols)
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            cell = ws.cell(row=r, column=c)
            v = cell.value
            if v is None:
                continue
            coord = cell.coordinate
            # openpyxl: data_only=False 时公式格 value 是 "=..." 字符串
            is_formula = isinstance(v, str) and v.startswith("=")
            entry = {"coord": coord, "row": r, "col": c, "value": v}
            if is_formula:
                formulas.append(entry)
            non_empty.append(entry)
    merged = [str(mc) for mc in (ws.merged_cells.ranges or [])]
    return {
        "max_row": ws.max_row,
        "max_column": ws.max_column,
        "scanned_rows": rows,
        "scanned_cols": cols,
        "non_empty_count": len(non_empty),
        "non_empty": non_empty,
        "formula_count": len(formulas),
        "formulas": formulas,
        "merged_ranges": merged,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="输出 JSON 文件路径（相对 spec 目录）")
    ap.add_argument("--sheet", default=None, help="只看某个 sheet（默认全册摘要 + D4-1 详情）")
    args = ap.parse_args()

    tpl = _find_template()
    wb = openpyxl.load_workbook(tpl, data_only=False, read_only=False)

    facts: dict = {
        "template_path": str(tpl.relative_to(_repo_root())).replace("\\", "/"),
        "template_name": tpl.name,
        "sheet_names": list(wb.sheetnames),
    }

    target_sheets = [args.sheet] if args.sheet else [
        s for s in wb.sheetnames if s
    ]
    detail: dict = {}
    for name in target_sheets:
        ws = wb[name]
        detail[name] = _cell_facts(ws)
    facts["sheets"] = detail

    out_json = json.dumps(facts, ensure_ascii=False, indent=2)
    if args.out:
        out_path = _repo_root() / ".kiro" / "specs" / \
            "d4-1-adjudication-bidirectional-writeback-and-formula-io" / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_json, encoding="utf-8")
        print(f"written: {out_path}")
    else:
        print(out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
