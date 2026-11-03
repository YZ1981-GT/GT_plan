"""鉴证报告案例验收（spec citar-assurance-report-menus 任务 11）：用案例底稿的填写值跑计算模型，比对案例成品。

做法：案例底稿（CITRv1.0，缓存值）里每个「模型非公式格」（常量、取数格、参数格）的值作为输入，
本平台计算模型重新求全部公式，再与案例目录里的成品逐项比对：
- 汇算申报表：36 张 A 类表的数值格 vs ``3汇算申报表2025.xlsx``（同地址，容差 0.01）
- 报告正文：摘录表 25 个金额 vs ``1企业所得税年度纳税申报审核报告.docx``
- 审核说明：段落 vs ``2审核说明2025.docx``（去编号后逐段比，差异逐条列出）

单体财务报表的数据源是项目试算表（需导入账套），不在本脚本内；案例底稿与样表版本不同处如实列出，不改判据。

用法：python backend/scripts/check/check_tax_assurance_case.py --case-dir <案例1目录> [--out 报告.txt]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import zipfile
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

import openpyxl  # noqa: E402
from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

from app.services.tax_assurance import report_body, review_notes  # noqa: E402
from app.services.tax_workbook import json_to_value, load_workbook, parse_a1  # noqa: E402

CASE_WP = "CITRv1.0工作底稿-六部提供案例（解密）.xlsx"
SUB = "六部案例-税审报告"
TOL = Decimal("0.01")
_NUM_PREFIX = re.compile(r"^(（?[一二三四五六七八九十]+[、）]|（?\d+[、）]|[①-⑳]|[IVX]+\.|[ivx]+\.)")


def _value(v):
    """案例缓存值 → 输入值。金额在分位以下的浮点尾差（3997297.90999999）按两位小数取：
    平台账套金额是 Numeric(20,2)，不会有这种尾差；不收掉会让应纳税额成 -0.00、IF(x=0) 分支翻转。"""
    if isinstance(v, float):
        if v.is_integer():
            v = int(v)
        elif abs(v - round(v, 2)) < 1e-6:
            v = round(v, 2)
    return json_to_value(v) if not isinstance(v, str) else v


_DECIMALS_RE = re.compile(r"0\.(0+)")


def displayed_decimals(number_format: str | None) -> int | None:
    """数字格式显示的小数位（``#,##0.00`` → 2，``0`` → 0）；常规 / 文本 None。"""
    fmt = (number_format or "").split(";")[0]
    if not fmt or fmt in ("General", "@"):
        return None
    m = _DECIMALS_RE.search(fmt)
    if m:
        return len(m.group(1))
    return 0 if "0" in fmt and "%" not in fmt else None


def full_precision(case_wp: Path) -> bool:
    """工作簿是否按完整精度计算（Excel「将精度设为所显示的精度」关闭）。"""
    with zipfile.ZipFile(case_wp) as z:
        m = re.search(r"<calcPr[^>]*>", z.read("xl/workbook.xml").decode("utf-8"))
    return not (m and 'fullPrecision="0"' in m.group(0))


def evaluate_case(case_wp: Path):
    """案例值作输入跑模型。案例工作簿开了「将精度设为所显示的精度」时（CITRv1.0 即是），
    输入按单元格显示的小数位取舍 —— Excel 在该模式下存的就是显示值，平台账套金额本身也是两位小数。"""
    wb = load_workbook()
    case = openpyxl.load_workbook(str(case_wp), data_only=True)
    as_displayed = not full_precision(case_wp)

    def take(c):
        v = _value(c.value)
        if as_displayed and isinstance(v, Decimal):
            places = displayed_decimals(c.number_format)
            if places is not None:
                v = v.quantize(Decimal(1).scaleb(-places))
        return v

    inputs = {}
    # 模型里全部非公式格（常量、取数格）+ 案例里手工填写、样表上是空白的格：一律按案例值作为输入
    for (sheet, row, col) in list(wb.consts) + list(wb.rules):
        if sheet in case.sheetnames:
            inputs[(sheet, row, col)] = take(case[sheet].cell(row, col))
    for sheet in wb.model["sheets"]:
        if sheet not in case.sheetnames:
            continue
        for row in case[sheet].iter_rows():
            for c in row:
                key = (sheet, c.row, c.column)
                if c.value is not None and key not in wb.formulas and key not in inputs:
                    inputs[key] = take(c)
    computed = wb.evaluate(set(wb.formulas), inputs, {})
    return wb, inputs, computed, case


def value_of(wb, inputs, computed, calc: bool = False):
    """显示值；``calc=True`` 取计算值（引用空格的公式得 0，审核说明占位用，同 Evaluation.calc_value）。"""
    def get(sheet: str, ref: str):
        key = (sheet, *parse_a1(ref))
        if calc and key in wb.formulas:
            return computed.get(key)
        return wb.cell_value(key, inputs, {}, computed)
    get.blank = getattr(computed, "blank", set())
    return get


def check_tax_return(wb, get, decl_path: Path) -> list[str]:
    decl = openpyxl.load_workbook(str(decl_path), data_only=True)
    out, total, bad = [], 0, 0
    for code in wb.model["groups"]["tax_return"]:
        if not re.fullmatch(r"A\d{6}", code) or code not in decl.sheetnames:
            continue
        ws = decl[code]
        for row in ws.iter_rows():
            for c in row:
                if not isinstance(c.value, (int, float)) or isinstance(c.value, bool) or c.value == 0:
                    continue
                total += 1
                got = get(code, c.coordinate)
                if not isinstance(got, Decimal) or abs(got - Decimal(str(c.value))) > TOL:
                    bad += 1
                    if bad <= 40:
                        out.append(f"  {code}!{c.coordinate} 案例 {c.value} / 平台 {got}")
    return [f"汇算申报表：非零数值格 {total}，一致 {total - bad}，不一致 {bad}"] + out


def check_report_body(get, docx_path: Path) -> list[str]:
    doc = Document(str(docx_path))
    table = doc.tables[0]
    out, bad = [], 0
    for i, row in enumerate(table.rows[1:], start=17):
        want = row.cells[-1].text.strip()
        v = get(report_body.BODY_SHEET, f"F{i}")
        got = report_body._amount_text(i, v)
        if got != want:
            bad += 1
            out.append(f"  第 {i - 16} 行 {row.cells[1].text.strip()}：案例「{want}」/ 平台「{got}」")
    return [f"报告正文摘录表：25 行，不一致 {bad}"] + out


def check_review_notes(wb, get, docx_path: Path) -> list[str]:
    rules = review_notes.read_rules(wb, lambda ref: get(review_notes.RULES_SHEET, ref))
    review_notes.blank_text_slots(rules, getattr(get, "blank", set()))
    got = [p["text"] for p in review_notes.layout(rules)]
    doc = Document(str(docx_path))
    want = ["".join(t.text or "" for t in p.iter(qn("w:t"))).strip() for p in doc.element.body.iter(qn("w:p"))]
    want = [w for w in want if w]
    # 编号：平台写在段首文字里，案例多数用 Word 自动编号（不在文字里）、少数手打 ⇒ 两边都去掉再比
    got_cmp = [_NUM_PREFIX.sub("", g) for g in got]
    want = [_NUM_PREFIX.sub("", w) for w in want]
    sm = SequenceMatcher(a=got_cmp, b=want, autojunk=False)
    same = sum(b - a for tag, a, b, _, _ in sm.get_opcodes() if tag == "equal")
    out = [f"审核说明：平台 {len(got)} 段 / 案例 {len(want)} 段，逐段一致 {same}"]
    for tag, a1, a2, b1, b2 in sm.get_opcodes():
        if tag == "equal":
            continue
        for k in range(a1, a2):
            out.append(f"  - 平台：{got[k][:90]}")
        for k in range(b1, b2):
            out.append(f"  + 案例：{want[k][:90]}")
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--case-dir", default=os.environ.get("GT_TAX_CASE_DIR"), help="案例目录（含 CITRv1.0 底稿与「六部案例-税审报告」）")
    parser.add_argument("--out", help="报告写到文件（默认打印）")
    args = parser.parse_args()
    if not args.case_dir:
        parser.error("需要 --case-dir 或环境变量 GT_TAX_CASE_DIR")
    case_dir = Path(args.case_dir)
    wb, inputs, computed, _ = evaluate_case(case_dir / CASE_WP)
    get = value_of(wb, inputs, computed)
    lines = []
    lines += check_tax_return(wb, get, case_dir / SUB / "3汇算申报表2025.xlsx")
    lines += check_report_body(get, case_dir / SUB / "1企业所得税年度纳税申报审核报告.docx")
    lines += check_review_notes(wb, value_of(wb, inputs, computed, calc=True), case_dir / SUB / "2审核说明2025.docx")
    text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
