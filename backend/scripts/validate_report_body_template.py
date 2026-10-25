#!/usr/bin/env python3
"""校验报告正文模板 POC：无 ABC/XXXX、无裸【、含核心占位符.

Usage:
    python backend/scripts/validate_report_body_template.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document

_BACKEND = Path(__file__).resolve().parent.parent
POC = (
    _BACKEND / "data/audit_report_templates/report_body/"
    "1.1 模板A-无保留意见审计报告模板（上市公司、三板创新层及公开发债）-简版.docx"
)

FORBIDDEN = [
    (re.compile(r"\bABC\b"), "ABC"),
    (re.compile(r"XXXX"), "XXXX"),
    (re.compile(r"^【"), "【行首说明"),
]

#: 畸形占位符：`{{x}`（缺右括号）或 `{x}}`（缺左括号）。
#:
#: 🔴 2026-09-28 加：POC 模板 para[21] 实为 `{{firm_name}`（少一个 `}`），
#: 原校验只查"必需 token 是否在全文里"，于是只报了一句含糊的
#: `missing required token: {{firm_name}}`，定位不到是"写错了"还是"压根没写"。
#: 现算分母：`report_body/**.docx` 34 本，畸形占位符 **2** 本（主目录 + standalone
#: 同名副本，同一处 run）—— 已修，本规则用于防复发。
MALFORMED_TOKEN_RE = re.compile(r"\{\{[^{}]*\}(?!\})|(?<!\{)\{[^{}]*\}\}")
REQUIRED_TOKENS = [
    "{{company_full_name}}",
    "{{audit_year}}",
    "{{firm_name}}",
    "{{report_number}}",
    "##OPT:key_audit_matters:",
]


def iter_text_locations(doc: Document) -> list[tuple[str, str]]:
    """段落 + 表格单元格的 `(位置标签, 文本)`。

    🔴 `doc.paragraphs` **不含表格内段落**（python-docx 行为）。占位符若落在表格里，
    只拼 `paragraphs` 会读成"缺失"——这是"读出为空先排除解析失败"的典型触发点。
    本 POC 实测表格内 0 个占位符，但扫描口径必须覆盖，否则以后挪进表格就静默漏。
    """
    out: list[tuple[str, str]] = [
        (f"para[{i}]", p.text or "") for i, p in enumerate(doc.paragraphs)
    ]
    for ti, table in enumerate(doc.tables):
        for ri, row in enumerate(table.rows):
            for ci, cell in enumerate(row.cells):
                out.append((f"table[{ti}]r{ri}c{ci}", cell.text or ""))
    return out


def validate(path: Path) -> list[str]:
    issues: list[str] = []
    if not path.is_file():
        return [f"missing file: {path}"]
    doc = Document(path)
    locations = iter_text_locations(doc)
    full_text = "\n".join(text for _, text in locations)
    for pattern, label in FORBIDDEN:
        for i, p in enumerate(doc.paragraphs):
            t = p.text or ""
            if pattern.search(t):
                issues.append(f"para[{i}] forbidden {label}: {t[:80]}")
    for loc, text in locations:
        for match in MALFORMED_TOKEN_RE.finditer(text):
            issues.append(
                f"{loc} malformed placeholder {match.group(0)!r}: {text.strip()[:80]}"
            )
    for token in REQUIRED_TOKENS:
        if token not in full_text:
            issues.append(f"missing required token: {token}")
    return issues


def main() -> None:
    issues = validate(POC)
    if issues:
        print(f"FAIL ({len(issues)}):")
        for x in issues:
            print(f"  - {x}")
        raise SystemExit(1)
    print(f"OK {POC.name}")


if __name__ == "__main__":
    main()
