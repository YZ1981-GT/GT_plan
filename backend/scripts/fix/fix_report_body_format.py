"""修复审计报告正文模板格式：首行缩进 + 字体统一仿宋_GB2312

问题根因：.doc→.docx 转换或 prepare_report_body_all.py 整理时丢失了：
  1. 正文段落的首行缩进（应为 2 个中文字符 ≈ 0.74cm）
  2. 正文字体（应为仿宋_GB2312，12号=小四字）

修复策略：
  - 标题段落（含"一、""二、"等序号开头 或 Heading 样式）不加缩进不改字体
  - 空段落跳过
  - 抬头/签名/页眉页脚不改（通过段落长度和位置过滤）
  - 其余正文段落：加首行缩进 + 改字体为仿宋_GB2312 + 字号四号(14pt)

用法：
  python scripts/fix/fix_report_body_format.py [--dry-run]
  不加 --dry-run 直接修改模板文件（先自动备份到 _backup_format/）
"""

import re
import shutil
import sys
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm
from docx.oxml.ns import qn

# 配置
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "audit_report_templates" / "report_body"
BACKUP_DIR = TEMPLATES_DIR / "_backup_format"
FIRST_LINE_INDENT = Cm(0.74)  # 2个中文字符宽 ≈ 0.74cm
FONT_NAME_CN = "FangSong"  # OnlyOffice 注册名是 FangSong（非"仿宋_GB2312"，后者在 OO 中找不到会 fallback）
FONT_NAME_EN = "Times New Roman"  # 英文/数字用 Times New Roman
FONT_SIZE = Pt(12)  # 小四字 = 12pt

# 标题段落检测：以 一、二、三… 开头 或 含 OPT/SECTION 标记
HEADING_PATTERN = re.compile(r"^[一二三四五六七八九十]+、|^##(OPT|SECTION|NOTE):")
# 短段落（签名行/日期行等）不改
MIN_BODY_LENGTH = 15


def is_heading_paragraph(para) -> bool:
    """判断是否为标题/非正文段落"""
    # Style 判断
    if para.style and para.style.name:
        sn = para.style.name.lower()
        if "heading" in sn or "title" in sn or "toc" in sn:
            return True
    # 文本模式判断
    text = para.text.strip()
    if HEADING_PATTERN.match(text):
        return True
    return False


def fix_paragraph_format(para) -> bool:
    """修复单个正文段落的格式，返回是否修改了"""
    text = para.text.strip()
    
    # 跳过：空段落/标题/短行
    if not text or len(text) < MIN_BODY_LENGTH:
        return False
    if is_heading_paragraph(para):
        return False
    # 跳过含占位符标记的段落（OPT/SECTION/NOTE）
    if "##" in text and ("OPT" in text or "SECTION" in text or "NOTE" in text):
        return False
    
    modified = False
    
    # 1. 首行缩进
    pf = para.paragraph_format
    if pf.first_line_indent is None or pf.first_line_indent != FIRST_LINE_INDENT:
        pf.first_line_indent = FIRST_LINE_INDENT
        modified = True
    
    # 2. 字体修正：遍历所有 run 设置字体
    for run in para.runs:
        if run.font.name != FONT_NAME_CN:
            run.font.name = FONT_NAME_CN
            # python-docx 中设置中文字体需要同时设 w:rFonts 的 eastAsia 属性
            rpr = run._r.get_or_add_rPr()
            rFonts = rpr.find(qn("w:rFonts"))
            if rFonts is None:
                rFonts = rpr.makeelement(qn("w:rFonts"), {})
                rpr.insert(0, rFonts)
            rFonts.set(qn("w:eastAsia"), FONT_NAME_CN)
            rFonts.set(qn("w:ascii"), FONT_NAME_EN)
            rFonts.set(qn("w:hAnsi"), FONT_NAME_EN)
            modified = True
        if run.font.size != FONT_SIZE:
            run.font.size = FONT_SIZE
            modified = True
    
    return modified


def fix_template(filepath: Path, dry_run: bool = False) -> dict:
    """修复单个模板文件，返回统计信息"""
    doc = Document(str(filepath))
    stats = {"total_paras": 0, "modified_paras": 0, "skipped_paras": 0}
    
    for para in doc.paragraphs:
        stats["total_paras"] += 1
        if fix_paragraph_format(para):
            stats["modified_paras"] += 1
        else:
            stats["skipped_paras"] += 1
    
    if not dry_run and stats["modified_paras"] > 0:
        doc.save(str(filepath))
    
    return stats


def main():
    dry_run = "--dry-run" in sys.argv
    
    # 收集所有 .docx 模板（含 standalone/ 子目录）
    templates = sorted(TEMPLATES_DIR.rglob("*.docx"))
    templates = [t for t in templates if not t.name.startswith("~") and "_backup" not in str(t)]
    
    if not templates:
        print(f"未找到模板文件：{TEMPLATES_DIR}")
        return
    
    print(f"{'[DRY-RUN] ' if dry_run else ''}修复 {len(templates)} 个报告正文模板")
    print(f"  首行缩进: {FIRST_LINE_INDENT.cm:.2f}cm")
    print(f"  中文字体: {FONT_NAME_CN}")
    print(f"  英文字体: {FONT_NAME_EN}")
    print(f"  字号: {FONT_SIZE.pt}pt (小四)")
    print()
    
    # 备份（非 dry-run）
    if not dry_run:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        for t in templates:
            rel = t.relative_to(TEMPLATES_DIR)
            dst = BACKUP_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copy2(t, dst)
        print(f"  备份至: {BACKUP_DIR}")
        print()
    
    total_modified = 0
    for t in templates:
        rel = t.relative_to(TEMPLATES_DIR)
        stats = fix_template(t, dry_run=dry_run)
        if stats["modified_paras"] > 0:
            print(f"  OK {rel}: {stats['modified_paras']}/{stats['total_paras']} 段已修正")
            total_modified += 1
        else:
            print(f"  - {rel}: 无需修改")
    
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}完成：{total_modified}/{len(templates)} 个文件已修正")


if __name__ == "__main__":
    main()
