#!/usr/bin/env python3
"""修复单体报告正文目录页(TOC 域缓存)残留的"合并及公司XX表"。

paragraph.text 读不全 TOC 域内缓存 run，故直接在 <w:t> 文本节点层替换。
覆盖所有 run（含域缓存），不动域指令 <w:instrText>。

Usage:
    python backend/scripts/fix_standalone_toc_consolidated.py            # dry-run
    python backend/scripts/fix_standalone_toc_consolidated.py --write
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

_BACKEND = Path(__file__).resolve().parent.parent
STANDALONE_DIR = (
    _BACKEND / "data" / "audit_report_templates" / "report_body" / "standalone"
)

# 目录页（及正文）合并口径 → 单体口径（长优先）
REPLACEMENTS: list[tuple[str, str]] = [
    ("合并及公司资产负债表", "资产负债表"),
    ("合并及公司利润表", "利润表"),
    ("合并及公司现金流量表", "现金流量表"),
    ("合并及公司股东权益变动表", "股东权益变动表"),
    ("合并及公司所有者权益变动表", "所有者权益变动表"),
    ("合并及公司财务状况", "财务状况"),
    ("合并及公司经营成果和现金流量", "经营成果和现金流量"),
    ("合并及公司财务报表", "财务报表"),
    ("合并及公司", ""),
]


def _replace_in_text(s: str) -> str:
    out = s
    for old, new in REPLACEMENTS:
        out = out.replace(old, new)
    return out


def process(path: Path, *, write: bool) -> int:
    doc = Document(path)
    body = doc.element.body
    changed = 0
    # 遍历所有 <w:t> 文本节点（含 TOC 域缓存 run）
    for t in body.iter(qn("w:t")):
        if t.text and "合并及公司" in t.text:
            new = _replace_in_text(t.text)
            if new != t.text:
                changed += 1
                if write:
                    t.text = new
    if write and changed:
        doc.save(path)
    return changed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    files = sorted(p for p in STANDALONE_DIR.glob("*.docx") if not p.name.startswith("~"))
    if not files:
        print("无单体文件", file=sys.stderr)
        raise SystemExit(1)

    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"目录页合并口径修复 — {mode}  共 {len(files)} 份\n")
    total = 0
    for f in files:
        n = process(f, write=args.write)
        total += n
        flag = f"  改 {n} 个文本节点" if n else "  (无残留)"
        print(f"  {f.name[:46]:48s}{flag}")
    print(f"\n合计修复 {total} 个 <w:t> 节点")
    if not args.write:
        print("加 --write 执行")


if __name__ == "__main__":
    main()
