"""修复审计报告封面落款「致同会计师事务所（特殊普通合伙）」被挤到第2页的问题。

根因：致同封面模板用巨大行距（w:line="2400" 即 10× 行距）把落款段撑成
~253pt 高的不可分割行框来做"页底锚定"。渲染器（OnlyOffice）CJK 行高略大时，
标题+空行累计高度超过 (可用页高 - 253pt)，整块 253pt 行框无法跨页 → 落款整块
跌到第 2 页。

修复：把封面落款段的超大行距降到 1.5×（360），行框缩到 ~38pt，稳稳留在第1页。
仅改动 firm 段的 w:line 属性，不动其它内容，最小侵入。

用法：
    python scripts/fix_report_cover_firm_spacing.py            # 修所有源模板
    python scripts/fix_report_cover_firm_spacing.py --dry      # 只报告不写入
    python scripts/fix_report_cover_firm_spacing.py --file X   # 修单个 docx
"""
import sys
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

FIRM_MARKERS = ("{{firm_name}}", "致同会计师事务所")
HUGE_LINE_THRESHOLD = 1000   # >=1000 (即 >~4× 行距) 视为异常的页底锚定行框
TARGET_LINE = "360"          # 1.5× 行距
TARGET_RULE = "auto"

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "data" / "audit_report_templates" / "report_body"


def fix_docx(path: Path, dry: bool = False) -> int:
    """返回修复的封面落款段数量（0 表示无需修）。"""
    try:
        doc = Document(str(path))
    except Exception as exc:
        print(f"  [SKIP] 无法打开 {path.name}: {exc}")
        return 0

    fixed = 0
    # 仅扫描前 30 段（封面区），避免误伤正文签章
    for p in doc.paragraphs[:30]:
        txt = p.text.strip()
        if not any(m in txt for m in FIRM_MARKERS):
            continue
        pPr = p._p.find(qn('w:pPr'))
        if pPr is None:
            continue
        sp = pPr.find(qn('w:spacing'))
        if sp is None:
            continue
        line = sp.get(qn('w:line'))
        if line and line.isdigit() and int(line) >= HUGE_LINE_THRESHOLD:
            old = line
            sp.set(qn('w:line'), TARGET_LINE)
            sp.set(qn('w:lineRule'), TARGET_RULE)
            fixed += 1
            print(f"  [FIX] {path.name}: firm 段行距 {old} → {TARGET_LINE}")

    if fixed and not dry:
        doc.save(str(path))
    return fixed


def main():
    args = sys.argv[1:]
    dry = "--dry" in args
    single = None
    if "--file" in args:
        single = Path(args[args.index("--file") + 1])

    targets: list[Path] = []
    if single:
        targets = [single]
    else:
        targets = sorted(TEMPLATE_ROOT.rglob("*.docx"))

    total_files = 0
    total_fixed = 0
    for t in targets:
        n = fix_docx(t, dry=dry)
        if n:
            total_files += 1
            total_fixed += n
    print(f"\n{'[DRY] ' if dry else ''}修复完成：{total_files} 个文件 / {total_fixed} 处封面落款")


if __name__ == "__main__":
    main()
