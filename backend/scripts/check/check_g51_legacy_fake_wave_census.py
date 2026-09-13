"""G5-1 分波裁决清册：全量扫描 legacy_fake_bidirectional，按可双向性分类。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Phase 5 / G5-1
用途：四个 Excel pilot 双向 verified 后，量化剩余 legacy_fake_bidirectional entry 的
真实迁移工作面——区分「bidirectional 候选」「Word lane」「single_html 终态」「待逐 entry 核」，
为 Phase 5 分波收口提供分类依据。配套 runbook：
`.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g5-1-canary-feasibility-and-wave-census.md`

只读。从 manifest + 各 cycle slice 现算，不手填。分类维度：
  - workbook_format: xlsx / docx / (empty=无权威册)
  - html_counterpart.store: checklist_responses / field_overrides / unresolved / ...
分波终态建议：
  A. xlsx + 有 store 对端         → bidirectional 候选（需逐字段核映射，参考 A5-1 蓝图：多为 partial）
  B. docx 权威册                  → Word lane（Phase 6，非 xlsx 单元格双向）
  C. 无权威册（前端纯 checklist） → single_html 终态（OO 侧空壳）
  D. xlsx + store=unresolved      → 待逐 entry 解析 store 后再定（多为 single_html）
输出 JSON 供 runbook 引用。
"""
import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_MANIFEST = _REPO / "backend" / "data" / "workpaper_sync_entry_manifest.json"
_SLICES = sorted((_REPO / "backend" / "data").glob("workpaper_sync_*_cycle_manifest_slice.json"))


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    manifest = _load(_MANIFEST)
    entries = manifest["entries"]
    fake = [e for e in entries if e.get("migration_state") == "legacy_fake_bidirectional"]

    # 从 slice 收集逐 entry 的 template_ref.workbook_format + html_counterpart.store
    slice_facts: dict[str, dict] = {}
    for sp in _SLICES:
        s = _load(sp)
        ie = s.get("independent_entries") or s.get("entries") or []
        for e in ie:
            if not isinstance(e, dict):
                continue
            eid = e.get("entry_id")
            if not eid or not isinstance((e.get("template_ref") or {}), dict):
                continue
            slice_facts[eid] = {
                "workbook_format": (e.get("template_ref") or {}).get("workbook_format"),
                "store": (e.get("html_counterpart") or {}).get("store"),
                "html_verdict": e.get("html_counterpart_verdict"),
                "workbook": (e.get("template_ref") or {}).get("workbook"),
                "slice": sp.name,
            }

    def classify(eid: str, e: dict) -> str:
        sf = slice_facts.get(eid, {})
        in_slice = eid in slice_facts
        wbf = sf.get("workbook_format")
        store = sf.get("store")
        doctype = e.get("document_type")
        # 逐 entry slice 已核（in_slice）：用 slice 的 workbook_format/store
        if in_slice:
            if wbf == "docx":
                return "B_word_lane"
            if wbf == "xlsx" and store and store != "unresolved":
                return "A_bidirectional_candidate_xlsx"
            if not wbf:  # slice 里明确无权威册
                return "C_single_html_no_workbook"
            if wbf == "xlsx" and (not store or store == "unresolved"):
                return "D_xlsx_store_unresolved"
            return "E_other"
        # 未在任何 cycle slice 逐 entry 核（not_in_slice）：只能用 manifest document_type 粗分，
        # 不武断归 C。docx → Word lane；xlsx → 待逐 entry 解析（D 循环等，可能有 store 对端）。
        if doctype == "docx":
            return "B_word_lane"
        if doctype == "xlsx":
            return "D_not_in_slice_xlsx_pending"
        return "E_other"

    buckets: dict[str, list] = {}
    for e in fake:
        eid = e["entry_id"]
        cls = classify(eid, e)
        buckets.setdefault(cls, []).append({
            "entry_id": eid,
            "document_type": e.get("document_type"),
            "workbook_format": slice_facts.get(eid, {}).get("workbook_format"),
            "store": slice_facts.get(eid, {}).get("store"),
            "in_slice": eid in slice_facts,
        })

    summary = {k: len(v) for k, v in sorted(buckets.items())}
    report = {
        "generated_from": "backend/data/workpaper_sync_entry_manifest.json + *_cycle_manifest_slice.json",
        "legacy_fake_total": len(fake),
        "in_slice_count": sum(1 for e in fake if e["entry_id"] in slice_facts),
        "bucket_summary": summary,
        "bucket_meaning": {
            "A_bidirectional_candidate_xlsx": "xlsx权威册+有HTML store对端 → bidirectional候选(需逐字段核映射,参A5-1蓝图多为partial)",
            "B_word_lane": "docx权威册 → Word lane(Phase 6),非xlsx单元格双向",
            "C_single_html_no_workbook": "无权威册(前端纯checklist,OO空壳) → single_html终态",
            "D_xlsx_store_unresolved": "in_slice已核: xlsx但store未解析 → 待逐entry解析(多为single_html)",
            "D_not_in_slice_xlsx_pending": "未在cycle slice逐entry核的xlsx(如D循环d1/d3/d4等) → 待补slice或逐entry判store,不武断定终态",
            "E_other": "未落入上述(需人工看)",
        },
        "buckets": buckets,
    }
    out = (
        _REPO / ".kiro" / "specs"
        / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
        / "evidence" / "g5-1-legacy-fake-wave-census.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("legacy_fake_total =", len(fake))
    print("in_slice_count =", report["in_slice_count"])
    print("bucket_summary =", json.dumps(summary, ensure_ascii=False))
    # A 类候选逐个列出（这是真正值得做双向的）
    print("\n=== A 类 bidirectional 候选 ===")
    for e in buckets.get("A_bidirectional_candidate_xlsx", []):
        print(f"  {e['entry_id']:42s} store={e['store']}")
    print("\nwrote", out.name)


if __name__ == "__main__":
    main()
