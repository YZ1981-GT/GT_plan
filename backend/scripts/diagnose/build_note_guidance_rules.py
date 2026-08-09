"""生成附注模板 `guidance` 规则表 ``backend/data/note_guidance_rules.json``（只读）。

spec: note-template-columns-and-legacy-snapshot-closure（Task 12）

判据真源
--------
``backend/data/note_table_headers_source_facts.json`` 的 ``guidance_candidates``
（由 Task 7 抽取器从 ``docs/模版/`` 两份源 docx 逐表抽出：括注型指引 / 条款引用 /
提示型三类，见 ``extract_note_table_headers._pick_guidance``）。

🔴 R3.2 只许三种来源，故本脚本**只搬运**不生成
--------------------------------------------------------------
① 源模板红字/括注原文 ② 准则或财会文号条款 ③ 「勾稽：」前缀的工具提示。
源 docx 里找不到候选的表 → 进 ``deficits``（R3.3 由 apply 脚本写最小提示），
**绝不按表名/列名编造口径**。

🔴 复用 Task 8 的章归属闸门
--------------------------
`guidance` 与 `columns` 共用同一套「JSON 章 ↔ docx root」映射，故直接 import
``build_note_columns_rules`` 的 ``chapter_verdict`` / ``norm_section`` /
``_chapter_no`` / ``_docx_root``。**不另写一份**（两份判据会漂移）。

用法
----
    python backend/scripts/diagnose/build_note_guidance_rules.py
    python backend/scripts/diagnose/build_note_guidance_rules.py --out <path>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
BACKEND_ROOT = _HERE.parents[2]
REPO_ROOT = _HERE.parents[3]
DATA_DIR = BACKEND_ROOT / "data"
HEADERS_FACTS = DATA_DIR / "note_table_headers_source_facts.json"
DEFAULT_OUT = DATA_DIR / "note_guidance_rules.json"

VARIANTS = ("listed", "soe")

# guidance 长度上限：源 docx 有 275 字的长括注（应收账款迁徙率说明），
# 全文搬运会让 TAB 提示条撑爆；截断会破坏「逐字取自源模板」这一判据 ⇒
# 超长的照样全文收录（TAB 侧折叠展示是 UI 职责），只在报告里标出来。
_LONG_THRESHOLD = 120


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


RULES_GEN = _load(
    BACKEND_ROOT / "scripts" / "diagnose" / "build_note_columns_rules.py",
    "columns_rules_gen_for_guidance",
)
PROBE = RULES_GEN.PROBE
norm_section = RULES_GEN.norm_section
chapter_verdict = RULES_GEN.chapter_verdict
_chapter_no = RULES_GEN._chapter_no
_docx_root = RULES_GEN._docx_root


def _clean(text: str) -> str:
    """guidance 必须是纯文本：剥 HTML + 去 markdown 粗体（R3.4/R3.5）。

    🔴 不做别的归一 —— 源模板的内部空格与全角标点是有意字面。
    """
    out = re.sub(r"<[^>]+>", "", str(text or ""))
    return out.replace("**", "").strip()


def build(scanned: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "_source": (
            "生成自 backend/scripts/diagnose/build_note_guidance_rules.py；"
            "真源 = docs/模版 两份附注模板 docx 的逐表指引段"
            "（note_table_headers_source_facts.json 的 guidance_candidates）"
        ),
        "_key": "rules 以 section_id 为键（section_number 不唯一）",
        "_policy": (
            "只搬运源 docx 指引段，不生成内容；无候选的表进 deficits，"
            "由 fix 脚本按 R3.3 写「本表编制口径待补充，参见…」最小提示"
        ),
        "rules": {v: {} for v in VARIANTS},
        "deficits": {v: [] for v in VARIANTS},
        "summary": {},
    }
    stat: Counter = Counter()

    for variant in VARIANTS:
        dsec = facts[variant]["sections"]
        by_leaf: dict[str, list[str]] = {}
        for key, meta in dsec.items():
            leaf = norm_section(str(meta.get("heading_text") or ""))
            if leaf:
                by_leaf.setdefault(leaf, []).append(key)

        raw = json.loads(
            (DATA_DIR / f"note_template_{variant}.json").read_text(encoding="utf-8")
        )
        raw_by_id = {
            str(s.get("section_id") or ""): s
            for s in (raw.get("sections") or [])
            if isinstance(s, dict)
        }
        chapters = {
            _chapter_no(str(s.get("section_number") or "")): norm_section(
                str(s.get("section_title") or "")
            )
            for s in (raw.get("sections") or [])
            if isinstance(s, dict) and s.get("level") == 1
        }

        for sec in scanned[variant]["sections"]:
            if sec["scope"] != PROBE.SCOPE_UNREGISTERED:
                continue
            gaps = [t for t in sec["tables"] if not t.get("has_guidance")]
            if not gaps:
                continue
            sid = sec["section_id"]
            rawsec = raw_by_id.get(sid) or {}
            raw_tables = rawsec.get("tables") or []

            title = norm_section(sec["section_title"])
            keys = by_leaf.get(title) or [
                k
                for leaf, ks in by_leaf.items()
                if title and (title in leaf or leaf in title)
                for k in ks
            ]
            chapter_title = chapters.get(_chapter_no(sec["section_number"]), "")
            docx_key = None
            rejected: list[str] = []
            for k in keys:
                ok, _kind = chapter_verdict(variant, chapter_title, _docx_root(k))
                if ok:
                    docx_key = k
                    break
                rejected.append(_docx_root(k))
            dtbls = dsec[docx_key]["tables"] if docx_key else []
            count_ok = bool(docx_key) and len(dtbls) == sec["table_count"]

            planned: list[dict[str, Any]] = []
            for t in gaps:
                idx = t["index"]
                tname = (
                    str(raw_tables[idx].get("name") or "")
                    if idx < len(raw_tables)
                    else ""
                )
                reason = ""
                cands: list[str] = []
                if not docx_key:
                    reason = (
                        f"CROSS_CHAPTER（章归属不符，拒绝 {rejected[:2]}）"
                        if rejected
                        else "NO_SECTION（源 docx 未映射到该章节）"
                    )
                elif not count_ok:
                    reason = (
                        f"COUNT_MISMATCH（docx {len(dtbls)} 表 vs "
                        f"JSON {sec['table_count']} 表）"
                    )
                else:
                    cands = [
                        _clean(x)
                        for x in (dtbls[idx].get("guidance_candidates") or [])
                    ]
                    cands = [c for c in cands if c]
                    if not cands:
                        reason = "NO_GUIDANCE_IN_SOURCE（源 docx 该表前无指引段）"

                if reason:
                    out["deficits"][variant].append(
                        {
                            "section_id": sid,
                            "section_number": sec["section_number"],
                            "section_title": sec["section_title"],
                            "index": idx,
                            "table_name": tname or t["name"],
                            "reason": reason,
                        }
                    )
                    stat[f"{variant}_deficit"] += 1
                    stat[f"{variant}_" + reason.split("（")[0]] += 1
                    continue

                text = "\n".join(cands)
                planned.append(
                    {
                        "index": idx,
                        "table_name": tname or t["name"],
                        "guidance": text,
                        "source_ref": f"docx:{docx_key}#{idx}guidance",
                        "candidate_count": len(cands),
                    }
                )
                stat[f"{variant}_rule"] += 1
                if len(text) > _LONG_THRESHOLD:
                    stat[f"{variant}_rule_long"] += 1

            if planned:
                out["rules"][variant][sid] = {
                    "section_number": sec["section_number"],
                    "section_title": sec["section_title"],
                    "docx_key": docx_key,
                    "tables": planned,
                }
                stat[f"{variant}_rule_sections"] += 1

    out["summary"] = dict(sorted(stat.items()))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__ or "")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if not HEADERS_FACTS.exists():
        print(f"[ERR] 缺少 {HEADERS_FACTS}；先跑 extract_note_table_headers.py")
        return 2

    payload = build(
        PROBE.scan_templates(), json.loads(HEADERS_FACTS.read_text(encoding="utf-8"))
    )
    for k, v in payload["summary"].items():
        print(f"[OK] {k}={v}")
    out = Path(args.out) if args.out else DEFAULT_OUT
    if not out.is_absolute():
        out = REPO_ROOT / out
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[OK] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
