#!/usr/bin/env python3
"""批量将 report_body/*.doc 转为 .docx（LibreOffice headless）.

Task 0.1

Usage:
    python backend/scripts/convert_template_doc_to_docx.py --dry-run
    python backend/scripts/convert_template_doc_to_docx.py --write
    python backend/scripts/convert_template_doc_to_docx.py --write --update-manifest
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
REPORT_BODY = _BACKEND / "data" / "audit_report_templates" / "report_body"
MANIFEST = _BACKEND / "data" / "audit_report_templates" / "template_manifest.json"
ARCHIVE = REPORT_BODY / "_archive_doc"

SOFFICE_CANDIDATES = [
    "soffice",
    "libreoffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]


def find_soffice() -> str | None:
    for c in SOFFICE_CANDIDATES:
        p = shutil.which(c) if not c.endswith(".exe") else (c if Path(c).is_file() else None)
        if p:
            return p
        if Path(c).is_file():
            return c
    return None


def convert_one(soffice: str, src: Path, out_dir: Path) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        str(out_dir),
        str(src),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"FAIL {src.name}: {result.stderr or result.stdout}", file=sys.stderr)
        return None
    dest = out_dir / (src.stem + ".docx")
    return dest if dest.is_file() else None


def update_manifest_paths() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def walk(node):
        if isinstance(node, str):
            return node.replace(".doc", ".docx") if node.endswith(".doc") else node
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        return node

    new_data = walk(data)
    MANIFEST.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return json.dumps(data).count(".doc")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert .doc report templates to .docx")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--update-manifest", action="store_true", help="Rewrite manifest .doc→.docx")
    args = parser.parse_args()
    if not args.write:
        args.dry_run = True

    docs = sorted(REPORT_BODY.glob("*.doc"))
    print(f"Found {len(docs)} .doc files under {REPORT_BODY}")
    if not docs:
        raise SystemExit(0)

    soffice = find_soffice()
    if not soffice and args.write:
        print("LibreOffice (soffice) not found; install or add to PATH", file=sys.stderr)
        raise SystemExit(1)
    if not soffice:
        print("dry-run: soffice not checked")

    converted = 0
    for src in docs:
        dest = src.with_suffix(".docx")
        if dest.exists():
            print(f"SKIP {src.name} → {dest.name} exists")
            continue
        if args.dry_run:
            print(f"PLAN convert {src.name} → {dest.name}")
            converted += 1
            continue
        out = convert_one(soffice, src, REPORT_BODY)
        if out:
            ARCHIVE.mkdir(exist_ok=True)
            shutil.move(str(src), str(ARCHIVE / src.name))
            print(f"OK {src.name} → {out.name} (archived .doc)")
            converted += 1

    if args.update_manifest and args.write:
        n = update_manifest_paths()
        print(f"Updated manifest ({n} .doc refs in old file)")

    print(f"done: {converted} files")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
