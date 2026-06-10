#!/usr/bin/env python3
"""从附注 Word 模板中提取表格标题，更新 JSON 模板中的 tables[N].name 字段。

对每个附注 Word 模板变体（soe_standalone, soe_consolidated, listed_standalone, listed_consolidated），
扫描 {{table:SECTION:N}} 占位符，提取其前面的标题段落文本，然后更新对应的 JSON 模板
(note_template_soe.json / note_template_listed.json) 中 section 的 tables[N].name。

Usage:
    python backend/scripts/fix/fix_note_table_names_from_docx.py            # dry-run (default)
    python backend/scripts/fix/fix_note_table_names_from_docx.py --write    # actually write JSON
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

_BACKEND = Path(__file__).resolve().parent.parent.parent
NOTES_DIR = _BACKEND / "data" / "audit_report_templates" / "disclosure_notes"
SOE_JSON = _BACKEND / "data" / "note_template_soe.json"
LISTED_JSON = _BACKEND / "data" / "note_template_listed.json"

# Mapping: docx variant → which JSON file it updates
VARIANT_CONFIG = [
    {
        "docx": "soe_standalone.docx",
        "json_path": SOE_JSON,
        "template_type": "soe",
    },
    {
        "docx": "soe_consolidated.docx",
        "json_path": SOE_JSON,
        "template_type": "soe",
    },
    {
        "docx": "listed_standalone.docx",
        "json_path": LISTED_JSON,
        "template_type": "listed",
    },
    {
        "docx": "listed_consolidated.docx",
        "json_path": LISTED_JSON,
        "template_type": "listed",
    },
]

# Pattern to match ##STYLE_REF:table:CODE:N##
STYLE_REF_RE = re.compile(r"^##STYLE_REF:table:(.+):(\d+)##$")
# Pattern to match {{table:CODE:N}}
TABLE_PH_RE = re.compile(r"^\{\{table:(.+):(\d+)\}\}$")


def _get_para_text(el) -> str:
    """Get full text from a w:p element by iterating w:t nodes."""
    return "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()


def _is_marker_or_empty(text: str) -> bool:
    """Check if a paragraph text is a placeholder/marker/empty (not a title candidate)."""
    if not text:
        return True
    if text.startswith("##") or text.startswith("{{"):
        return True
    if text == "[TABLE]":
        return True
    # Skip guidance notes in brackets (【...】) or containing them
    if text.startswith("【") or text.endswith("】"):
        return True
    if "【" in text and "】" in text:
        return True
    # Skip instructions wrapped in （...）
    if text.startswith("（") and text.endswith("）"):
        return True
    # Skip lines starting with ( or （ that are clearly instructions/notes
    if text.startswith("（") and len(text) > 30:
        return True
    # Skip lines that are purely numeric or just punctuation
    if not any(c.isalpha() or '\u4e00' <= c <= '\u9fff' for c in text):
        return True
    return False


def _is_guidance_continuation(text: str) -> bool:
    """Check if text looks like a continuation of a guidance/instruction block.

    Patterns: numbered items like '1.xxx', '2.xxx', '（1）xxx' etc. that
    follow a 【 block opener.
    """
    # Numbered guidance items
    if re.match(r'^\d+[.、．]', text):
        return True
    if re.match(r'^[（\(]\d+[）\)]', text):
        return True
    # Items starting with ① ② etc.
    if text and text[0] in '①②③④⑤⑥⑦⑧⑨⑩':
        return True
    return False


def extract_table_titles_from_docx(filepath: Path) -> dict[str, dict[int, str]]:
    """Extract table titles from a docx file.

    Returns: {section_code: {table_index: title_text}}
    """
    doc = Document(str(filepath))
    body = doc.element.body

    titles: dict[str, dict[int, str]] = {}

    # Walk through body children, keeping track of preceding paragraphs
    prev_meaningful_text = ""  # Last paragraph text that's not a marker
    in_guidance_block = False  # Track if we're inside a 【...】 block

    for child in body:
        if child.tag == qn("w:p"):
            text = _get_para_text(child)

            # Check if this is a ##STYLE_REF:table:CODE:N## marker
            m = STYLE_REF_RE.match(text)
            if m:
                code = m.group(1)
                idx = int(m.group(2))
                # The title is the last meaningful paragraph before this marker
                if prev_meaningful_text and not _is_marker_or_empty(prev_meaningful_text):
                    titles.setdefault(code, {})[idx] = prev_meaningful_text
                # Reset guidance block tracking after a style_ref
                in_guidance_block = False
                continue

            # Check if it's a {{table:}} marker
            if TABLE_PH_RE.match(text):
                continue

            # Track guidance blocks (【...】 spans)
            if text.startswith("【"):
                in_guidance_block = True
            if text.endswith("】"):
                in_guidance_block = False
                continue  # Don't update prev_meaningful_text

            # Skip markers and empty text
            if _is_marker_or_empty(text):
                continue

            # Skip guidance continuations (numbered items within 【...】 block)
            if in_guidance_block and _is_guidance_continuation(text):
                continue

            # This is a meaningful paragraph - update tracker
            if not in_guidance_block:
                prev_meaningful_text = text

        elif child.tag == qn("w:tbl"):
            # Tables reset the meaningful text tracker (a table is not a title)
            prev_meaningful_text = ""
            in_guidance_block = False

    return titles


def find_section_in_json(sections: list[dict], section_code: str) -> dict | None:
    """Find a section in JSON by section_number matching the docx section code.

    The docx uses codes like '八、5' which maps to section_number '八、5' in JSON.
    Some codes may be like '四、固定资产' which maps by section_number prefix matching.
    """
    # Direct match first
    for sec in sections:
        sn = sec.get("section_number", "")
        if sn == section_code:
            return sec

    # Try matching by section_number == code (handles '五、对期初所有者权益' etc.)
    # Some codes in docx are longer like '四、固定资产' — try prefix match on section title
    for sec in sections:
        sn = sec.get("section_number", "")
        title = sec.get("section_title", "")
        # Build the expected code: section_number prefix + section_title
        # e.g. section_number='四、14' section_title='固定资产' could map to '四、固定资产'
        if "、" in section_code and "、" not in sn:
            continue
        # Try: the code might be "CHAPTER_PREFIX、TITLE"
        if "、" in section_code:
            code_prefix = section_code.split("、")[0]
            code_suffix = "、".join(section_code.split("、")[1:])
            if sn.startswith(code_prefix + "、"):
                # Check if suffix matches title or is numeric
                if title and code_suffix and title.startswith(code_suffix[:4]):
                    return sec

    return None


def update_json_tables(
    json_path: Path,
    all_titles: dict[str, dict[int, str]],
    *,
    dry_run: bool = True,
) -> list[dict]:
    """Update table names in JSON from extracted titles.

    Returns list of changes made.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sections = data.get("sections", [])
    changes = []

    for section_code, table_titles in sorted(all_titles.items()):
        section = find_section_in_json(sections, section_code)
        if section is None:
            # Skip sections not found in JSON
            continue

        tables = section.get("tables", [])
        if not tables:
            continue

        for idx, new_name in sorted(table_titles.items()):
            if idx >= len(tables):
                continue

            old_name = tables[idx].get("name", "")
            if old_name != new_name:
                changes.append({
                    "section": section_code,
                    "section_number": section.get("section_number", ""),
                    "table_index": idx,
                    "old_name": old_name,
                    "new_name": new_name,
                })
                if not dry_run:
                    tables[idx]["name"] = new_name

    if not dry_run and changes:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return changes


def main():
    # Fix Windows console encoding
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Fix note table names from Word templates"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually write changes to JSON files (default is dry-run)",
    )
    args = parser.parse_args()
    dry_run = not args.write

    mode = "DRY-RUN" if dry_run else "WRITE"
    print(f"\n{'=' * 60}")
    print(f"附注表格标题修正（从 Word 模板提取） — {mode}")
    print(f"{'=' * 60}\n")

    # Collect all titles from all variants, grouped by JSON target
    json_titles: dict[Path, dict[str, dict[int, str]]] = {}

    for cfg in VARIANT_CONFIG:
        docx_path = NOTES_DIR / cfg["docx"]
        json_path = cfg["json_path"]

        if not docx_path.exists():
            print(f"  ⚠ MISSING: {cfg['docx']}")
            continue

        print(f"📄 Scanning: {cfg['docx']}")
        titles = extract_table_titles_from_docx(docx_path)
        total_tables = sum(len(v) for v in titles.values())
        print(f"   Found {len(titles)} sections, {total_tables} table titles\n")

        # Merge into json_titles (later variants can override earlier for same code)
        if json_path not in json_titles:
            json_titles[json_path] = {}
        for code, idx_map in titles.items():
            if code not in json_titles[json_path]:
                json_titles[json_path][code] = {}
            json_titles[json_path][code].update(idx_map)

    # Apply changes to each JSON file
    total_changes = 0
    all_changes = []

    for json_path, titles in json_titles.items():
        print(f"\n{'─' * 50}")
        print(f"📝 Updating: {json_path.name}")
        print(f"{'─' * 50}")

        changes = update_json_tables(json_path, titles, dry_run=dry_run)
        total_changes += len(changes)
        all_changes.extend(changes)

        if changes:
            for c in changes[:30]:  # Show first 30
                print(
                    f"  [{c['section_number']}] table[{c['table_index']}]: "
                    f"'{c['old_name'][:30]}' → '{c['new_name'][:50]}'"
                )
            if len(changes) > 30:
                print(f"  ... and {len(changes) - 30} more")
            print(f"\n  Total changes: {len(changes)}")
        else:
            print("  No changes needed (already up-to-date)")

    print(f"\n{'=' * 60}")
    print(f"Total: {total_changes} table name updates across all JSON files")
    if dry_run:
        print("💡 Run with --write to apply changes")
    else:
        print("✅ Changes written to JSON files")
    print(f"{'=' * 60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
