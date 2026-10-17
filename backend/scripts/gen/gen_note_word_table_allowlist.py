"""生成附注种子 ↔ 四版 Word 的**表格差异**白名单（并入章节树白名单文件）。

spec: disclosure-note-template-word-realignment Task 6（design §3.3 末条 + 需求 US-2）

用户 2026-10-16 裁定：**表格权威源 = 底稿 working-paper xlsx，不是四版 Word**。国企 51 / 上市
73 节的表格结构与 Word 不一致，其中绝大多数已由逐循环修复脚本（``fix_note_*_structure.py``）、
各循环披露对齐 spec、或 ``note-template-columns-and-legacy-snapshot-closure`` 按底稿 xlsx 对齐，
并被底稿同步注册表 / 公式推送规则消费。按 Word 改这些表会与底稿对不上。

因此表格差异不是「待修」而是「刻意不一致」：本生成器把每一条表格差异登记进
``note_template_word_alignment_allowlist.json``，**每条 reason 写明该节的底稿消费方**（取自种子节
的 ``_aligned_by`` 标记；无标记的少数节按父章或已知类别归因）。守卫
``test_note_template_word_tree_alignment.test_seed_tables_match_four_word_templates`` 读同一白名单，
并另行断言「每条表格差异都能归因到底稿消费方」（防止新出现的未归因表格漂移被静默放过）。

输出确定（无时间戳、按键排序）。用法（仓库根执行）：
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
from app.services.note_word_tree import (  # noqa: E402
    ALLOWLIST_PATH,
    build_report,
)

# 表格差异类别（与 note_word_tree._table_diffs 一致）
_TABLE_KINDS = ("table_count", "table_columns", "table_headers", "table_rows")

# 无 ``_aligned_by`` 标记、但表格仍以底稿为准的节 → 归因说明（Task 6 逐条登记）。
# 这些节的表格结构是底稿 xlsx 派生的现状，四版 Word 与之刻意不一致。
_UNMARKED_REASON: dict[tuple[str, str], str] = {
    # 母公司章子节（父章 ``_aligned_by=fix_note_parent_company_chapter.py``）：
    # 母公司章 37 张表 Word 写「格式参照附注八」(0 张)，由 test_note_parent_company_chapter 守护的既有设计。
    ("soe", "十二、其他应收款"): "fix_note_parent_company_chapter.py（母公司章，Word 格式参照附注八）",
    ("soe", "十二、应收账款"): "fix_note_parent_company_chapter.py（母公司章，Word 格式参照附注八）",
    ("soe", "十二、营业收入与营业成本"): "fix_note_parent_company_chapter.py（母公司章，Word 格式参照附注八）",
    ("listed", "十六、其他应收款"): "fix_note_parent_company_chapter.py（母公司章，Word 格式参照附注八/五）",
    ("listed", "十六、应收票据"): "fix_note_parent_company_chapter.py（母公司章，Word 格式参照附注八/五）",
    ("listed", "十六、应收账款"): "fix_note_parent_company_chapter.py（母公司章，Word 格式参照附注八/五）",
    ("listed", "十六、营业收入与营业成本"): "fix_note_parent_company_chapter.py（母公司章，Word 格式参照附注八/五）",
    # 父章无标记、节本身也无标记：表格为底稿 xlsx 派生的现状表（或空表），非本 spec 范围内按 Word 改。
    ("soe", "八、83"): "底稿 xlsx 派生表（节未经逐循环脚本单独对齐，表结构仍为底稿口径）",
    ("soe", "四、无形资产"): "底稿 xlsx 派生表（节未经逐循环脚本单独对齐，表结构仍为底稿口径）",
    ("listed", "八、采用净额法冲减相关成本费用的政府补助情况"):
        "底稿 xlsx 派生表（政府补助章节，表结构仍为底稿口径）",
    ("listed", "十、1"): "底稿 xlsx 派生表（公允价值章正文叶子，表结构仍为底稿口径）",
    ("listed", "十二、股份支付的修改、终止情况"): "底稿 xlsx 派生表（股份支付章节，表结构仍为底稿口径）",
}


def _aligned_by_map(std: str) -> tuple[dict[str, str], dict[str, str]]:
    """返回 (section_number → _aligned_by, section_id → section_number)；供父章兜底归因。"""
    data = json.loads(template_json_path(std).read_text(encoding="utf-8"))
    by_num: dict[str, str] = {}
    id_to_num: dict[str, str] = {}
    parent_of: dict[str, str] = {}
    sid_aligned: dict[str, str] = {}
    for s in data.get("sections", []):
        num = s.get("section_number") or ""
        sid = s.get("section_id") or ""
        id_to_num[sid] = num
        parent_of[num] = s.get("parent_section_id") or ""
        if s.get("_aligned_by"):
            by_num[num] = s["_aligned_by"]
            sid_aligned[sid] = s["_aligned_by"]
    # 父章兜底：节无标记但父章有标记 ⇒ 用父章标记
    parent_aligned: dict[str, str] = {}
    for num, pid in parent_of.items():
        if num not in by_num and pid in sid_aligned:
            parent_aligned[num] = sid_aligned[pid]
    return by_num, parent_aligned


def _consumer_reason(std: str, section: str, by_num: dict[str, str], parent_aligned: dict[str, str]) -> str | None:
    """该节表格差异的归因 reason；无法归因返回 None（守卫会打红）。"""
    consumer = by_num.get(section)
    if consumer:
        return f"消费方 = {consumer}（种子节 _aligned_by 标记）"
    consumer = parent_aligned.get(section)
    if consumer:
        return f"消费方 = {consumer}（父章 _aligned_by 标记）"
    manual = _UNMARKED_REASON.get((std, section))
    if manual:
        return f"消费方 = {manual}"
    return None


def _table_entries() -> tuple[list[dict[str, str]], list[tuple[str, str, str]]]:
    """返回 (白名单条目, 无法归因的差异)。"""
    diffs = [d for d in build_report(tables=True) if d.kind in _TABLE_KINDS]
    maps = {std: _aligned_by_map(std) for std in ("soe", "listed")}
    entries: list[dict[str, str]] = []
    unattributed: list[tuple[str, str, str]] = []
    for d in diffs:
        std = d.variant.split("_", 1)[0]
        section = d.key.split("#", 1)[0]
        by_num, parent_aligned = maps[std]
        reason = _consumer_reason(std, section, by_num, parent_aligned)
        if reason is None:
            unattributed.append((d.variant, d.kind, d.key))
            continue
        entries.append({
            "variant": d.variant,
            "kind": d.kind,
            "key": d.key,
            "reason": "表格以底稿 xlsx 为准，与四版 Word 刻意不一致（用户 2026-10-16 裁定）；" + reason,
        })
    return entries, unattributed


def render() -> str:
    # 保留现有章节树（非表格）白名单条目，表格条目整体重算。
    existing = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8")) if ALLOWLIST_PATH.exists() else []
    tree_entries = [e for e in existing if e["kind"] not in _TABLE_KINDS]
    table_entries, unattributed = _table_entries()
    if unattributed:
        raise SystemExit(
            "🔴 以下表格差异无法归因到底稿消费方（种子节无 _aligned_by、父章无标记、也不在 "
            "_UNMARKED_REASON 登记表里），请先登记依据：\n"
            + "\n".join(f"  {v} {k} {key}" for v, k, key in sorted(unattributed))
        )
    merged = tree_entries + table_entries
    merged.sort(key=lambda e: (e["variant"], e["kind"], e["key"]))
    return json.dumps(merged, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成附注表格差异白名单（底稿 xlsx 权威）")
    parser.add_argument("--check", action="store_true", help="只比对，不写文件；漂移时 exit 2")
    args = parser.parse_args(argv)
    expected = render()
    current = ALLOWLIST_PATH.read_text(encoding="utf-8") if ALLOWLIST_PATH.exists() else ""
    if args.check:
        if current != expected:
            print(f"[DRIFT] {ALLOWLIST_PATH.name} 与种子 / Word 表格差异不同步，请重跑生成脚本")
            return 2
        print(f"[OK] {ALLOWLIST_PATH.name} 表格白名单与种子 / Word 同步")
        return 0
    if current == expected:
        print(f"(无变化) {ALLOWLIST_PATH.name}")
        return 0
    ALLOWLIST_PATH.write_text(expected, encoding="utf-8")
    print(f"[written] {ALLOWLIST_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
