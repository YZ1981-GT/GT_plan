#!/usr/bin/env python
"""Report which guidance wp_codes have an attachable template authority (T7 input).

This does NOT write source_refs. It only records machine-verifiable facts a human
reviewer needs before authoring a real locator:

* does a canonical ``backend/wp_templates`` workbook exist for the wp_code
* its repo-relative path and current SHA-256 (the ``digest`` a ref must carry)
* its sheet names (the ``sheet`` a ref must name)
* how many canonical sections currently carry zero source_refs

Ambiguous or missing template matches are reported as-is; nothing is guessed.

Usage:
  python backend/scripts/diagnose/diagnose_guidance_source_ref_feasibility.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.guidance_inventory import (  # noqa: E402
    CANONICAL_SECTION_KEYS,
    GUIDANCE_DIR,
    SHEET_CODE_RE,
)
from app.services.guidance_source_refs import file_sha256  # noqa: E402
from app.services.workpaper_sync.canonical_paths import TEMPLATE_ROOT  # noqa: E402

REPORT = (
    ROOT
    / ".kiro"
    / "specs"
    / "workpaper-guidance-content-closure"
    / "basis"
    / "T07-source-ref-feasibility.json"
)

_LEADING_CODE = re.compile(r"^([A-Za-z]+\d+(?:-\d+[a-z]?)*)\s")
_SHEET_NAME_RE = re.compile(r'<sheet [^>]*name="([^"]+)"')


def _template_code(path: Path) -> str | None:
    match = _LEADING_CODE.match(path.stem)
    return match.group(1).upper() if match else None


def _sheet_names(path: Path) -> list[str]:
    try:
        with ZipFile(path) as archive:
            xml = archive.read("xl/workbook.xml").decode("utf-8", errors="replace")
    except (OSError, KeyError, BadZipFile):
        return []
    return [
        name.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        for name in _SHEET_NAME_RE.findall(xml)
    ]


def _template_files() -> list[Path]:
    return [
        path
        for path in sorted(TEMPLATE_ROOT.rglob("*.xls[xm]"))
        if "_reference" not in path.parts
    ]


def _index_templates(paths: list[Path]) -> dict[str, list[Path]]:
    by_code: dict[str, list[Path]] = {}
    for path in paths:
        code = _template_code(path)
        if code:
            by_code.setdefault(code, []).append(path)
    return by_code


def _index_sheet_codes(
    paths: list[Path], sheet_names: dict[Path, list[str]]
) -> dict[str, list[tuple[Path, str]]]:
    """code → [(workbook, sheet_name)] derived from real sheet names only."""
    by_code: dict[str, list[tuple[Path, str]]] = {}
    for path in paths:
        for name in sheet_names.get(path, ()):
            for code in SHEET_CODE_RE.findall(name.upper()):
                by_code.setdefault(code, []).append((path, name))
    return by_code


def build_report(*, with_sheets: bool) -> dict[str, Any]:
    paths = _template_files()
    templates = _index_templates(paths)
    sheet_names = {path: _sheet_names(path) for path in paths} if with_sheets else {}
    sheet_index = _index_sheet_codes(paths, sheet_names) if with_sheets else {}
    digest_cache: dict[Path, str] = {}

    def _digest(path: Path) -> str:
        if path not in digest_cache:
            try:
                digest_cache[path] = file_sha256(path)
            except OSError:
                digest_cache[path] = ""
        return digest_cache[path]

    rows: list[dict[str, Any]] = []

    for doc_path in sorted(GUIDANCE_DIR.glob("*.json")):
        if doc_path.stem.startswith("_"):
            continue
        try:
            document = json.loads(doc_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        wp_code = str(document.get("wp_code") or doc_path.stem).strip().upper()

        sections = [s for s in (document.get("sections") or []) if isinstance(s, dict)]
        canonical = [s for s in sections if str(s.get("key") or "") in CANONICAL_SECTION_KEYS]
        without_refs = [
            str(s.get("key"))
            for s in canonical
            if not (s.get("source_refs") or [])
        ]

        matches = templates.get(wp_code, [])
        sheet_hits = sheet_index.get(wp_code, [])
        if len(matches) == 1:
            template = matches[0]
            row_template: dict[str, Any] = {
                "path": template.relative_to(ROOT).as_posix(),
                "digest": _digest(template),
            }
            if with_sheets:
                row_template["sheetNames"] = sheet_names.get(template, [])
                own = [name for path, name in sheet_hits if path == template]
                if own:
                    row_template["matchingSheetNames"] = own
            authority = "single_template"
        elif len(matches) > 1:
            row_template = {
                "candidates": [p.relative_to(ROOT).as_posix() for p in matches]
            }
            authority = "ambiguous_template"
        elif len({path for path, _ in sheet_hits}) == 1:
            template = sheet_hits[0][0]
            row_template = {
                "path": template.relative_to(ROOT).as_posix(),
                "digest": _digest(template),
                "matchingSheetNames": sorted({name for _, name in sheet_hits}),
            }
            authority = "parent_workbook_sheet"
        elif sheet_hits:
            row_template = {
                "candidates": sorted(
                    {path.relative_to(ROOT).as_posix() for path, _ in sheet_hits}
                ),
                "matchingSheetNames": sorted({name for _, name in sheet_hits}),
            }
            authority = "ambiguous_template"
        else:
            row_template = {}
            authority = "no_template"

        rows.append(
            {
                "wp_code": wp_code,
                "authority": authority,
                "canonicalSectionCount": len(canonical),
                "sectionsWithoutSourceRefs": without_refs,
                "template": row_template,
            }
        )

    counts = {
        "single_template": sum(1 for r in rows if r["authority"] == "single_template"),
        "parent_workbook_sheet": sum(
            1 for r in rows if r["authority"] == "parent_workbook_sheet"
        ),
        "ambiguous_template": sum(1 for r in rows if r["authority"] == "ambiguous_template"),
        "no_template": sum(1 for r in rows if r["authority"] == "no_template"),
    }
    return {
        "task": 7,
        "purpose": "source_ref_attachability_facts",
        "recordedAt": datetime.now(UTC).isoformat(),
        "templateRoot": TEMPLATE_ROOT.relative_to(ROOT).as_posix(),
        "guidanceDocCount": len(rows),
        "authorityCounts": counts,
        "sectionsWithoutSourceRefsTotal": sum(
            len(r["sectionsWithoutSourceRefs"]) for r in rows
        ),
        "policy": "facts_only_no_generated_refs",
        "notes": [
            "A valid xlsx ref still needs sheet + cell_range + digest authored per section",
            "Static inventory cannot validate refs without a runtime template authority snapshot",
            "This report does not make any entry exact",
        ],
        "entries": rows,
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-sheets", action="store_true", help="skip workbook sheet-name probe")
    args = ap.parse_args()

    report = build_report(with_sheets=not args.no_sheets)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    counts = report["authorityCounts"]
    print(
        f"docs={report['guidanceDocCount']} single={counts['single_template']} "
        f"parentSheet={counts.get('parent_workbook_sheet', 0)} "
        f"ambiguous={counts['ambiguous_template']} none={counts['no_template']} "
        f"sectionsWithoutRefs={report['sectionsWithoutSourceRefsTotal']}"
    )
    print(f"report={REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
