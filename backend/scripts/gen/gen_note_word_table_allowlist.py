"""生成附注种子 ↔ 四版 Word 的**表格差异**白名单（并入章节树白名单文件）。

spec: disclosure-note-template-word-realignment Task 6（design §3.3 末条 + 需求 US-2）；
类别与证据：note-disclosure-pull-regression-and-headless-backend 任务 6 / R3.3（design §4.3）

用户 2026-10-17（US-8）：有底稿披露表的节，种子表格以底稿为准，与 Word 的表格差异只登记、不作待修。本生成器把每条
表格差异登记进 ``note_template_word_alignment_allowlist.json``，**类别与证据现算**（``note_word_allowlist.derive``）：
配上底稿披露表的记 ``workpaper_authority``（证据 = 配上的底稿编码 / 节内配上张数）、Word 只写「参照」不列表的记
``word_placeholder``、其余记 ``todo``（未经底稿核实，守卫钉住条数、只许减少）。章节树（非表格）条目手工维护，
渲染前逐条核对证据（``note_word_allowlist.evidence_problems``）。

守卫 ``test_note_template_word_tree_alignment`` 读同一白名单并断言磁盘内容 == 本生成器渲染：底稿配对、种子标记、Word
任何一侧变了，证据就对不上。输出确定（无时间戳、按键排序）。用法（仓库根执行）：
    python backend/scripts/gen/gen_note_word_table_allowlist.py          # 写入（内容未变则不改文件）
    python backend/scripts/gen/gen_note_word_table_allowlist.py --check  # 漂移 exit 2 并点名
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.note_section_catalog import template_json_path  # noqa: E402
from app.services.note_word_allowlist import derive, evidence_problems, pairing_index, split_key, word_side  # noqa: E402
from app.services.note_word_tree import ALLOWLIST_PATH, build_report, match_all  # noqa: E402

# 表格差异类别（与 note_word_tree._table_diffs 一致）
_TABLE_KINDS = ("table_count", "table_columns", "table_headers", "table_rows")


def _seeds() -> dict[str, tuple[dict[str, dict], dict[str, dict]]]:
    """口径 → （章节号 → 种子节, section_id → 种子节）。"""
    out = {}
    for std in ("soe", "listed"):
        secs = json.loads(template_json_path(std).read_text(encoding="utf-8")).get("sections", [])
        out[std] = ({s.get("section_number") or "": s for s in secs}, {s.get("section_id") or "": s for s in secs})
    return out


def _table_entries() -> list[dict]:
    from app.services.note_template_workpaper_alignment import compare_all, load_allowlist, load_templates

    diffs = [d for d in build_report(tables=True) if d.kind in _TABLE_KINDS]
    _mm, results = compare_all(load_templates(), corrections=load_allowlist()["corrections"])
    paired, registered = pairing_index(results)
    matches = match_all()
    seeds = _seeds()
    table_keys: dict[str, set[str]] = {}
    for d in diffs:
        if d.kind != "table_count":
            table_keys.setdefault(d.variant, set()).add(d.key)
    entries = []
    for d in diffs:
        std = d.variant.split("_", 1)[0]
        section, _t = split_key(d.key)
        by_num, by_id = seeds[std]
        got = derive(d, seed=by_num.get(section), by_id=by_id, paired=paired.get((std, section), {}),
                     registered=(std, section) in registered, word=word_side(matches[d.variant], section),
                     table_diff_keys=table_keys.get(d.variant, set()))
        entries.append({"variant": d.variant, "kind": d.kind, "key": d.key, **got})
    return entries


def render() -> str:
    # 保留现有章节树（非表格）白名单条目，表格条目整体重算。
    existing = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8")) if ALLOWLIST_PATH.exists() else []
    tree_entries = [e for e in existing if e["kind"] not in _TABLE_KINDS]
    problems = [f"  {e['variant']} {e['kind']} {e['key']}: {p}" for e in tree_entries for p in evidence_problems(e)]
    if problems:
        raise SystemExit("🔴 章节树白名单条目证据不成立：\n" + "\n".join(problems))
    merged = tree_entries + _table_entries()
    merged.sort(key=lambda e: (e["variant"], e["kind"], e["key"]))
    return json.dumps(merged, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成附注表格差异白名单（类别与证据现算）")
    parser.add_argument("--check", action="store_true", help="只比对，不写文件；漂移时 exit 2")
    args = parser.parse_args(argv)
    expected = render()
    current = ALLOWLIST_PATH.read_text(encoding="utf-8") if ALLOWLIST_PATH.exists() else ""
    if args.check:
        if current != expected:
            print(f"[DRIFT] {ALLOWLIST_PATH.name} 与种子 / Word / 底稿配对不同步，请重跑生成脚本")
            return 2
        print(f"[OK] {ALLOWLIST_PATH.name} 表格白名单与种子 / Word / 底稿配对同步")
        return 0
    if current == expected:
        print(f"(无变化) {ALLOWLIST_PATH.name}")
        return 0
    ALLOWLIST_PATH.write_bytes(expected.encode("utf-8"))
    print(f"[written] {ALLOWLIST_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
