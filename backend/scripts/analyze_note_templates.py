"""Compare disclosure note Word templates vs JSON seeds."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

DATA = Path(__file__).resolve().parent.parent / "data"
TEMPLATES = DATA / "audit_report_templates" / "disclosure_notes"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def extract_docx_text_blocks(path: Path) -> tuple[list[str], int]:
    headings: list[str] = []
    all_paras: list[str] = []
    tables = 0
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    for p in root.iter(f"{{{W_NS}}}p"):
        texts: list[str] = []
        for t in p.iter(f"{{{W_NS}}}t"):
            if t.text:
                texts.append(t.text)
            if t.tail:
                texts.append(t.tail)
        text = "".join(texts).strip()
        if not text:
            continue
        all_paras.append(text)
        if re.match(r"^[一二三四五六七八九十百]+[、．.]", text) or re.match(
            r"^（[一二三四五六七八九十]+）", text
        ):
            headings.append(text)
    for _ in root.iter(f"{{{W_NS}}}tbl"):
        tables += 1
    return headings, tables, all_paras


def load_json_sections(name: str) -> list[dict]:
    p = DATA / name
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("sections", data if isinstance(data, list) else [])


def norm_title(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[【】（）()、．.]", "", s)
    return s[:40]


def compare_word_json(word_headings: list[str], json_secs: list[dict], label: str) -> None:
    json_by_title = {norm_title(s.get("section_title", "")): s for s in json_secs if s.get("section_title")}
    json_nums = {s.get("section_number", ""): s for s in json_secs}

    print(f"\n--- {label}: Word vs JSON alignment ---")
    matched = 0
    word_only: list[str] = []
    for h in word_headings:
        # strip leading number
        title_part = re.sub(r"^[一二三四五六七八九十百]+[、．.]?\s*", "", h)
        title_part = re.sub(r"^[0-9]+[、．.]?\s*", "", title_part)
        key = norm_title(title_part)
        if key in json_by_title:
            js = json_by_title[key]
            # check number prefix
            w_num = re.match(r"^([一二三四五六七八九十百]+(?:[、．.][0-9]+)?)", h)
            w_num_s = w_num.group(1).replace("．", "、").replace(".", "、") if w_num else ""
            j_num = js.get("section_number", "")
            if w_num_s and j_num and w_num_s != j_num and not j_num.startswith(w_num_s.split("、")[0]):
                print(f"  NUM MISMATCH: Word[{w_num_s}] JSON[{j_num}] {title_part[:30]}")
            matched += 1
        else:
            if len(title_part) > 2 and "使用说明" not in h and "目录" not in h:
                word_only.append(h[:80])

    json_only_titles = []
    word_title_keys = set()
    for h in word_headings:
        tp = re.sub(r"^[一二三四五六七八九十百]+[、．.]?\s*", "", h)
        word_title_keys.add(norm_title(tp))
    for s in json_secs:
        t = norm_title(s.get("section_title", ""))
        if t and t not in word_title_keys and s.get("section_number"):
            json_only_titles.append((s.get("section_number"), s.get("section_title", "")[:40]))

    print(f"  Word headings: {len(word_headings)}, JSON sections: {len(json_secs)}")
    print(f"  Title matched: {matched}, Word-only headings: {len(word_only)}, JSON-only: {len(json_only_titles)}")
    if word_only[:15]:
        print("  Word-only (sample):")
        for x in word_only[:15]:
            print(f"    - {x}")
    if json_only_titles[:15]:
        print("  JSON-only (sample):")
        for n, t in json_only_titles[:15]:
            print(f"    - {n} {t}")


def main() -> None:
    soe = load_json_sections("note_template_soe.json")
    listed = load_json_sections("note_template_listed.json")

    mapping = {
        "soe_standalone.docx": ("note_template_soe.json", soe),
        "soe_consolidated.docx": ("note_template_soe.json", soe),
        "listed_standalone.docx": ("note_template_listed.json", listed),
        "listed_consolidated.docx": ("note_template_listed.json", listed),
    }

    for docx_name, (json_name, secs) in mapping.items():
        path = TEMPLATES / docx_name
        headings, tables, paras = extract_docx_text_blocks(path)
        print("=" * 80)
        print(f"FILE: {docx_name}")
        print(f"  tables={tables}, headings={len(headings)}, paras={len(paras)}")
        print("  First 30 headings:")
        for i, h in enumerate(headings[:30], 1):
            print(f"    {i:3d}. {h[:90]}")
        compare_word_json(headings, secs, docx_name)

    # Chapter structure comparison SOE vs Listed
    print("\n" + "=" * 80)
    print("CHAPTER STRUCTURE (level-1 synthesized)")
    for name, secs in [("SOE", soe), ("Listed", listed)]:
        ch = [s for s in secs if s.get("section_number") and re.match(r"^[一二三四五六七八九十]+$", s["section_number"])]
        print(f"\n{name} chapters ({len(ch)}):")
        for s in ch:
            print(f"  {s['section_number']} {s.get('section_title','')[:50]}")

    # Bindings keys sample
    bindings = json.loads((DATA / "note_template_bindings.json").read_text(encoding="utf-8"))
    if isinstance(bindings, dict) and "bindings" in bindings:
        keys = list(bindings["bindings"].keys())
    else:
        keys = list(bindings.keys())
    soe_nums = {s["section_number"] for s in soe}
    listed_nums = {s["section_number"] for s in listed}
    bind_soe = keys & soe_nums if isinstance(keys, set) else set(k for k in keys if k in soe_nums)
    bind_listed = set(k for k in keys if k in listed_nums)
    bind_orphan = set(k for k in keys if k not in soe_nums and k not in listed_nums)
    print(f"\nBindings: total keys={len(keys)}, in SOE={len(bind_soe)}, in Listed={len(bind_listed)}, orphan={len(bind_orphan)}")
    print("  Orphan sample:", sorted(bind_orphan)[:20])

    # scope filter check
    for variant, secs in [("soe_standalone", soe), ("listed_standalone", listed)]:
        standalone = [s for s in secs if s.get("scope") in ("standalone", "both")]
        consolidated_only = [s for s in secs if s.get("scope") == "consolidated"]
        print(f"\n{variant}: total={len(secs)}, standalone+both={len(standalone)}, consolidated_only={len(consolidated_only)}")


def extract_main_chapters(headings: list[str]) -> list[str]:
    """Top-level 一、二、 chapters only."""
    out = []
    for h in headings:
        if re.match(r"^[一二三四五六七八九十百]+、[^一二三四五六七八九十]", h):
            if len(h) < 80:
                out.append(h)
    return out


def diff_standalone_consolidated() -> None:
    pairs = [
        ("soe_standalone.docx", "soe_consolidated.docx"),
        ("listed_standalone.docx", "listed_consolidated.docx"),
    ]
    for a, b in pairs:
        ha, _, _ = extract_docx_text_blocks(TEMPLATES / a)
        hb, _, _ = extract_docx_text_blocks(TEMPLATES / b)
        sa = set(ha)
        sb = set(hb)
        print(f"\n--- {a} vs {b} ---")
        print(f"  only in standalone: {len(sa - sb)}")
        for x in sorted(sa - sb)[:10]:
            print(f"    + {x}")
        print(f"  only in consolidated: {len(sb - sa)}")
        for x in sorted(sb - sa)[:10]:
            print(f"    + {x}")


if __name__ == "__main__":
    import sys
    out_path = Path(__file__).resolve().parent / "_note_template_analysis.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        sys.stdout = f
        main()
        diff_standalone_consolidated()
        # main chapters
        for docx in sorted(TEMPLATES.glob("*.docx")):
            h, _, _ = extract_docx_text_blocks(docx)
            mc = extract_main_chapters(h)
            print(f"\n=== MAIN CHAPTERS {docx.name} ({len(mc)}) ===")
            for x in mc:
                print(f"  {x}")
    print(f"Wrote {out_path}")
