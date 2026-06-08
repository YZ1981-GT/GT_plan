#!/usr/bin/env python3
"""从 note_template JSON + docx ##SECTION: 标记生成 section_code_index.json.

POC 阶段：仅扫描已打标的章节；未打标节输出到 stdout 供人工补录。

Usage:
    python backend/scripts/build_section_code_index.py --variant soe_standalone
    python backend/scripts/build_section_code_index.py --all-poc
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from docx import Document

_BACKEND = Path(__file__).resolve().parent.parent
DATA = _BACKEND / "data"
TPL_ROOT = DATA / "audit_report_templates"
NOTES_DIR = TPL_ROOT / "disclosure_notes"
OUT_PATH = TPL_ROOT / "section_code_index.json"

SECTION_OPEN = re.compile(r"^##SECTION:([^#]+)##\s*$")
SECTION_CLOSE = re.compile(r"^##/SECTION:([^#]+)##\s*$")

VARIANT_SEED = {
    "soe_standalone": ("note_template_soe.json", "soe"),
    "soe_consolidated": ("note_template_soe.json", "soe"),
    "listed_standalone": ("note_template_listed.json", "listed"),
    "listed_consolidated": ("note_template_listed.json", "listed"),
}

# 国企五、N → 八、N legacy 映射（POC 人工补录位）
SOE_LEGACY_ALIASES: dict[str, list[str]] = {
    "八、1": ["五、1"],
    "八、2": ["五、2"],
    "八、3": ["五、3"],
}


def load_json_sections(seed_file: str) -> dict[str, dict[str, Any]]:
    path = DATA / seed_file
    data = json.loads(path.read_text(encoding="utf-8"))
    sections = data.get("sections", [])
    return {s["section_number"]: s for s in sections if s.get("section_number")}


def scan_section_markers(docx_path: Path) -> list[str]:
    """按文档顺序返回已打标的 section_code 列表."""
    doc = Document(docx_path)
    codes: list[str] = []
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        m = SECTION_OPEN.match(text)
        if m:
            codes.append(m.group(1).strip())
    return codes


def build_entry(
    section_code: str,
    seed: dict[str, Any],
    *,
    template_type: str,
) -> dict[str, Any]:
    title = seed.get("section_title", "")
    content_type = seed.get("content_type", "text")
    prefix = section_code.split("、")[0] if "、" in section_code else section_code
    entry: dict[str, Any] = {
        "section_code": section_code,
        "section_id": seed.get("section_id") or seed.get("id"),
        "section_title": title,
        "level": 2 if "、" in section_code else 1,
        "content_type": content_type,
        "placeholders": [f"{{{{seq:{prefix}}}}}", f"{{{{section:{section_code}}}}}"],
        "binding_wp_code": None,
        "legacy_aliases": [],
    }
    if content_type in ("table", "mixed"):
        entry["placeholders"].append(f"{{{{table:{section_code}}}}}")
    if template_type == "soe" and section_code in SOE_LEGACY_ALIASES:
        entry["legacy_aliases"] = SOE_LEGACY_ALIASES[section_code]
    return entry


def build_variant_index(variant_key: str) -> dict[str, Any]:
    seed_file, template_type = VARIANT_SEED[variant_key]
    docx_name = f"{variant_key}.docx"
    docx_path = NOTES_DIR / docx_name
    if not docx_path.is_file():
        raise FileNotFoundError(docx_path)

    by_code = load_json_sections(seed_file)
    marked = scan_section_markers(docx_path)
    sections: list[dict[str, Any]] = []
    missing_seed: list[str] = []

    for code in marked:
        seed = by_code.get(code)
        if not seed:
            missing_seed.append(code)
            continue
        sections.append(build_entry(code, seed, template_type=template_type))

    return {
        "template_key": variant_key,
        "seed_file": seed_file,
        "docx_file": f"disclosure_notes/{docx_name}",
        "sections": sections,
        "_meta": {
            "marked_in_docx": len(marked),
            "indexed": len(sections),
            "missing_seed": missing_seed,
        },
    }


def merge_into_index(variant_payload: dict[str, Any]) -> dict[str, Any]:
    if OUT_PATH.exists():
        root = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    else:
        root = {"version": "poc-v1", "variants": {}}
    root.setdefault("variants", {})[variant_payload["template_key"]] = variant_payload
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description="Build section_code_index.json from docx markers")
    parser.add_argument("--variant", help="Variant key e.g. soe_standalone")
    parser.add_argument("--all-poc", action="store_true", help="Build all variants that have SECTION markers")
    parser.add_argument("--write", action="store_true", help="Write to section_code_index.json")
    args = parser.parse_args()

    variants: list[str]
    if args.all_poc:
        variants = list(VARIANT_SEED.keys())
    elif args.variant:
        variants = [args.variant]
    else:
        variants = ["soe_standalone"]

    if OUT_PATH.exists():
        root: dict[str, Any] = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    else:
        root = {"version": "poc-v1", "variants": {}}
    root.setdefault("variants", {})

    for vk in variants:
        try:
            payload = build_variant_index(vk)
        except FileNotFoundError as e:
            print(f"SKIP {vk}: {e}", file=sys.stderr)
            continue
        meta = payload.pop("_meta", {})
        print(f"{vk}: marked={meta.get('marked_in_docx')} indexed={meta.get('indexed')}")
        if meta.get("missing_seed"):
            print(f"  missing_seed: {meta['missing_seed']}")
        store = {k: v for k, v in payload.items() if not k.startswith("_")}
        if args.write:
            root["variants"][vk] = store

    if args.write:
        OUT_PATH.write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {OUT_PATH}")
    else:
        print("(dry-run; pass --write to save)")


if __name__ == "__main__":
    main()
