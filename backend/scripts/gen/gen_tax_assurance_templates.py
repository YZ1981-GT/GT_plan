"""鉴证报告导出模板：样表 / 案例文件 → ``backend/data/tax_assurance/``（spec citar-assurance-report-menus）。

- ``tax_return_template.xlsx``：样表只留汇算申报表 37 张（封面、表单、A 类表），计算格 / 取数格 / 可填格清空（导出时填值），
  去外部链接与定义名。
- ``report_body.docx``：案例「1企业所得税年度纳税申报审核报告.docx」，单位名称、年度、报告号、日期、摘录表 25 个金额换成占位。
- ``review_notes.docx``：案例「2审核说明2025.docx」清空正文（保留样式、页眉页脚、页面设置），页眉换成占位。

先跑 gen_tax_workpaper_sheets.py（本脚本读它生成的计算模型判断哪些格要清空）。

用法：
  python backend/scripts/gen/gen_tax_assurance_templates.py --src <样表.xlsx> --case-dir <案例1/六部案例-税审报告>
  ... --check   # 只比对，有差异 exit 2
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import openpyxl
from docx import Document
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.tax_assurance.common import replace_in_document, replace_in_paragraph  # noqa: E402

OUT_DIR = ROOT / "backend" / "data" / "tax_assurance"
MODEL_PATH = ROOT / "backend" / "data" / "tax_workpaper_model.json"
REPORT_DOCX = "1企业所得税年度纳税申报审核报告.docx"
NOTES_DOCX = "2审核说明2025.docx"
FIXED_TIME = dt.datetime(2026, 1, 1)

#: 案例报告里的匿名单位名、年度、报告号、日期 → 占位（顺序替换，长的在前）
REPORT_REPLACEMENTS = [
    ("北京XXXX餐饮有限公司", "{{client}}"),
    ("致同税务审字(2026)第110ZC 号", "{{report_no}}"),
    ("日期：2026年4月30日", "{{report_date}}"),
    ("2025年度", "{{year}}年度"),
]
NOTES_HEADER_REPLACEMENTS = [
    ("北京XXXX餐饮有限公司", "{{client}}"),
    ("2025年度企业所得税年度纳税申报审核报告说明", "{{header_title}}"),
]
EXTRACT_ROWS = 25


# ── 汇算申报表 ──
def build_tax_return_template(src: Path) -> bytes:
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    codes = model["groups"]["tax_return"]
    keep = [s for c in codes for s in model["codes"][c]]
    rule_cells = {(r["sheet"], r["ref"]) for r in model["rules"]}
    book = openpyxl.load_workbook(src)
    for name in list(book.sheetnames):
        if name not in keep:
            del book[name]
    missing = [s for s in keep if s not in book.sheetnames]
    if missing:
        raise SystemExit(f"样表缺少申报表 sheet：{missing}")
    for name in keep:
        ws = book[name]
        cells = model["sheets"].get(name, {}).get("cells", {})
        for row in ws.iter_rows():
            for c in row:
                if type(c).__name__ == "MergedCell":
                    continue
                raw = cells.get(c.coordinate)
                # 公式格、取数格、模型外的公式（打印区外的辅助格）：清空，导出时填计算值
                if (isinstance(raw, dict) and "f" in raw) or (name, c.coordinate) in rule_cells or c.data_type == "f":
                    c.value = None
        ws.sheet_state = "visible"
    for name in list(book.defined_names):
        del book.defined_names[name]
    book._external_links = []
    book.properties.created = FIXED_TIME
    book.properties.modified = FIXED_TIME
    book.properties.lastModifiedBy = None
    book.active = 0
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()


# ── 报告正文 ──
def build_report_template(case_dir: Path) -> bytes:
    doc = Document(str(case_dir / REPORT_DOCX))
    changed = replace_in_document(doc, dict(REPORT_REPLACEMENTS))
    if not changed:
        raise SystemExit("报告正文：没有找到可替换的单位名称 / 年度")
    tables = doc.tables
    if len(tables) != 1 or len(tables[0].rows) != EXTRACT_ROWS + 1:
        raise SystemExit(f"报告正文：摘录表应为 1 张 {EXTRACT_ROWS + 1} 行，实际 {len(tables)} 张")
    for i, row in enumerate(tables[0].rows[1:], start=1):
        cell = row.cells[-1]
        paras = cell.paragraphs
        if paras[0].runs:
            paras[0].runs[0].text = f"{{{{amt_{i}}}}}"
            for r in paras[0].runs[1:]:
                r.text = ""
        else:
            paras[0].add_run(f"{{{{amt_{i}}}}}")
        for p in paras[1:]:
            for r in p.runs:
                r.text = ""
    text = "\n".join(p.text for p in doc.paragraphs) + "\n".join(c.text for r in tables[0].rows for c in r.cells)
    for token in ("{{client}}", "{{year}}", "{{report_no}}", "{{report_date}}", f"{{{{amt_{EXTRACT_ROWS}}}}}"):
        if token not in text:
            raise SystemExit(f"报告正文：模板缺少占位 {token}")
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── 审核说明 ──
def build_notes_template(case_dir: Path) -> bytes:
    doc = Document(str(case_dir / NOTES_DOCX))
    body = doc.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)
    header_changed = 0
    for section in doc.sections:
        if not section.header.is_linked_to_previous:
            for p in section.header.paragraphs:
                header_changed += replace_in_paragraph(p, dict(NOTES_HEADER_REPLACEMENTS))
    if header_changed == 0:
        raise SystemExit("审核说明：页眉里没有找到单位名称 / 标题")
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist() if n != "docProps/core.xml"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--src", default=os.environ.get("GT_TAX_WORKPAPER_XLSX"), help="税审底稿样表 xlsx")
    parser.add_argument("--case-dir", default=os.environ.get("GT_TAX_ASSURANCE_CASE_DIR"), help="案例报告目录（含 1~2 号 docx）")
    parser.add_argument("--check", action="store_true", help="只比对，不写文件；有差异 exit 2")
    args = parser.parse_args()
    if not args.src or not args.case_dir:
        parser.error("需要 --src 与 --case-dir")
    src, case_dir = Path(args.src), Path(args.case_dir)
    outputs = {
        "tax_return_template.xlsx": build_tax_return_template(src),
        "report_body.docx": build_report_template(case_dir),
        "review_notes.docx": build_notes_template(case_dir),
    }
    changed = []
    for name, data in outputs.items():
        path = OUT_DIR / name
        if not path.is_file() or _members(path.read_bytes()) != _members(data):
            changed.append(name)
    if args.check:
        if changed:
            print(f"[DRIFT] 模板差异：{changed}")
            return 2
        print(f"[OK] {len(outputs)} 个模板与来源一致")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in changed:
        (OUT_DIR / name).write_bytes(outputs[name])
    print(f"[WRITE] 模板 {len(outputs)} 个，写入 {len(changed)}：{changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
