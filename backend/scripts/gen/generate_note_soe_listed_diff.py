"""Generate note_soe_listed_diff.json from SOE/Listed template JSONs.

Compares sections by section_title to produce:
- common_sections: sections present in both templates (matched by title)
- soe_only_sections: sections only in SOE template
- listed_only_sections: sections only in Listed template
- format_diff_sections: common sections with different table counts/content_type

Usage:
    python backend/scripts/generate_note_soe_listed_diff.py

Output:
    backend/data/note_soe_listed_diff.json
"""
from __future__ import annotations

import json
import pathlib

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
SOE_PATH = DATA_DIR / "note_template_soe.json"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
OUTPUT_PATH = DATA_DIR / "note_soe_listed_diff.json"


def _load_sections(path: pathlib.Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("sections", [])


def _build_title_index(sections: list[dict]) -> dict[str, dict]:
    """Build section_title -> first section dict (dedup by title)."""
    index: dict[str, dict] = {}
    for s in sections:
        title = s.get("section_title", "")
        if title and title not in index:
            index[title] = s
    return index


def generate_diff() -> dict:
    soe_sections = _load_sections(SOE_PATH)
    listed_sections = _load_sections(LISTED_PATH)

    soe_by_title = _build_title_index(soe_sections)
    listed_by_title = _build_title_index(listed_sections)

    soe_titles = set(soe_by_title.keys())
    listed_titles = set(listed_by_title.keys())

    common_titles = sorted(soe_titles & listed_titles)
    soe_only_titles = sorted(soe_titles - listed_titles)
    listed_only_titles = sorted(listed_titles - soe_titles)

    # Common sections
    common_sections = []
    format_diff_sections = []

    for title in common_titles:
        soe_s = soe_by_title[title]
        listed_s = listed_by_title[title]
        entry = {
            "section_title": title,
            "soe_section_id": soe_s.get("section_id", ""),
            "listed_section_id": listed_s.get("section_id", ""),
        }
        common_sections.append(entry)

        # Check format differences
        soe_ct = soe_s.get("content_type", "text")
        listed_ct = listed_s.get("content_type", "text")
        soe_tables = len(soe_s.get("tables", []))
        listed_tables = len(listed_s.get("tables", []))

        if soe_ct != listed_ct or (soe_tables > 0 and listed_tables > 0 and soe_tables != listed_tables):
            format_diff_sections.append({
                "section_title": title,
                "soe_section_id": soe_s.get("section_id", ""),
                "listed_section_id": listed_s.get("section_id", ""),
                "soe_format": {"content_type": soe_ct, "table_count": soe_tables},
                "listed_format": {"content_type": listed_ct, "table_count": listed_tables},
                "field_mapping": None,  # To be filled by auditor (P-7)
            })

    # SOE only
    soe_only_sections = [
        {
            "section_id": soe_by_title[t].get("section_id", ""),
            "title": t,
        }
        for t in soe_only_titles
    ]

    # Listed only
    listed_only_sections = [
        {
            "section_id": listed_by_title[t].get("section_id", ""),
            "title": t,
        }
        for t in listed_only_titles
    ]

    return {
        "version": "1.0.0",
        "is_mock": True,
        "description": "SOE vs Listed template section diff (auto-generated from template JSONs)",
        "common_sections": common_sections,
        "soe_only_sections": soe_only_sections,
        "listed_only_sections": listed_only_sections,
        "format_diff_sections": format_diff_sections,
    }


def main():
    diff = generate_diff()
    OUTPUT_PATH.write_text(
        json.dumps(diff, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Generated {OUTPUT_PATH}")
    print(f"  Common sections: {len(diff['common_sections'])}")
    print(f"  SOE only: {len(diff['soe_only_sections'])}")
    print(f"  Listed only: {len(diff['listed_only_sections'])}")
    print(f"  Format diffs: {len(diff['format_diff_sections'])}")


if __name__ == "__main__":
    main()
