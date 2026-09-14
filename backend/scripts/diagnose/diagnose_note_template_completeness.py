#!/usr/bin/env python3
"""全局诊断：哪些附注章节 _tables 为空 / 哪些表缺 columns / guidance.

用法：
  python backend/scripts/diagnose/diagnose_note_template_completeness.py
  python backend/scripts/diagnose/diagnose_note_template_completeness.py --summary
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DATA = Path(__file__).resolve().parent.parent.parent / "data"


def _load(variant: str) -> list[dict]:
    path = BACKEND_DATA / f"note_template_{variant}.json"
    root = json.loads(path.read_text("utf-8"))
    return root.get("sections", root) if isinstance(root, dict) else root


def diagnose():
    summary_mode = "--summary" in sys.argv

    results = {"listed": [], "soe": []}

    for variant in ("listed", "soe"):
        sections = _load(variant)
        for sec in sections:
            sn = sec.get("section_number", "?")
            st = sec.get("section_title", "?")
            tables = sec.get("_tables", [])
            aligned = sec.get("_aligned_by")

            if not tables:
                results[variant].append({
                    "section": sn,
                    "title": st,
                    "issue": "无表格（_tables 为空）",
                    "aligned_by": aligned,
                })
                continue

            for t in tables:
                name = t.get("name", "?")
                cols = t.get("columns")
                guidance = t.get("guidance", "")

                issues = []
                if not cols:
                    issues.append("缺 columns")
                if not guidance or len(guidance) < 10:
                    issues.append("缺 guidance")

                if issues:
                    results[variant].append({
                        "section": sn,
                        "title": st,
                        "table": name,
                        "issue": " + ".join(issues),
                        "aligned_by": aligned,
                    })

    # 输出
    total_issues = sum(len(v) for v in results.values())

    if summary_mode:
        listed_no_tables = sum(1 for r in results["listed"] if "无表格" in r["issue"])
        soe_no_tables = sum(1 for r in results["soe"] if "无表格" in r["issue"])
        listed_no_cols = sum(1 for r in results["listed"] if "缺 columns" in r["issue"])
        soe_no_cols = sum(1 for r in results["soe"] if "缺 columns" in r["issue"])
        print(f"附注模板完整性诊断摘要")
        print(f"  listed: {listed_no_tables} 章节无表 / {listed_no_cols} 张表缺 columns")
        print(f"  soe:    {soe_no_tables} 章节无表 / {soe_no_cols} 张表缺 columns")
        print(f"  总问题数: {total_issues}")
    else:
        for variant, issues in results.items():
            if not issues:
                continue
            print(f"\n{'='*60}")
            print(f"  {variant} — {len(issues)} 处问题")
            print(f"{'='*60}")
            for r in issues[:50]:
                table_info = f" / 表={r['table']}" if "table" in r else ""
                aligned = f" [aligned_by={r['aligned_by']}]" if r.get("aligned_by") else ""
                print(f"  {r['section']} {r['title']}{table_info}: {r['issue']}{aligned}")
            if len(issues) > 50:
                print(f"  ... 还有 {len(issues) - 50} 处")

    return total_issues


if __name__ == "__main__":
    total = diagnose()
    # 诊断脚本不 exit(1)，只报告
    sys.exit(0)
