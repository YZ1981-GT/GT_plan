"""附注种子 JSON 与四版 Word 的章节树 / 表格比对（只读）。

spec: disclosure-note-template-word-realignment Task 1（design §2）

用法（仓库根执行）：
    python backend/scripts/check/check_note_template_word_tree.py                 # 计数 + 逐条差异
    python backend/scripts/check/check_note_template_word_tree.py --summary       # 只看计数
    python backend/scripts/check/check_note_template_word_tree.py --kind misplaced --variant listed_consolidated
    python backend/scripts/check/check_note_template_word_tree.py --json out.json # 完整报告（审阅用，不入库）
    python backend/scripts/check/check_note_template_word_tree.py --check         # 白名单外差异 / 失效条目 ⇒ exit 2

输出确定（无时间戳、按键排序）。白名单 ``backend/data/note_template_word_alignment_allowlist.json``。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.note_section_catalog import VARIANT_KEYS  # noqa: E402
from app.services.note_word_tree import (  # noqa: E402
    ALLOWLIST_PATH,
    build_report,
    check_against_allowlist,
)


def _load_allowlist() -> list[dict]:
    if not ALLOWLIST_PATH.exists():
        return []
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="附注种子与四版 Word 比对")
    parser.add_argument("--variant", action="append", choices=VARIANT_KEYS, help="只比对指定口径（可重复）")
    parser.add_argument("--kind", action="append", help="只打印指定差异类别（可重复）")
    parser.add_argument("--no-tables", action="store_true", help="不比表格")
    parser.add_argument("--summary", action="store_true", help="只打印计数")
    parser.add_argument("--json", type=Path, help="完整报告写入该路径")
    parser.add_argument("--check", action="store_true", help="白名单外差异或失效白名单条目 ⇒ exit 2")
    args = parser.parse_args(argv)

    variants = tuple(args.variant or VARIANT_KEYS)
    diffs = build_report(variants=variants, tables=not args.no_tables)
    counts: dict[str, Counter] = {}
    for d in diffs:
        counts.setdefault(d.variant, Counter())[d.kind] += 1
    for variant in sorted(counts):
        print(f"[{variant}] " + "  ".join(f"{k}={n}" for k, n in sorted(counts[variant].items())))
    if not args.summary:
        for d in diffs:
            if args.kind and d.kind not in args.kind:
                continue
            print(f"  {d.variant}\t{d.kind}\t{d.key}\t{d.detail}")
    if args.json:
        args.json.write_text(
            json.dumps([d.as_dict() for d in diffs], ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
        )
        print(f"[written] {args.json}")
    if args.check:
        unexpected, stale = check_against_allowlist(diffs, _load_allowlist())
        for d in unexpected:
            print(f"[DIFF] {d.variant} {d.kind} {d.key} {d.detail}")
        for e in stale:
            print(f"[STALE] 白名单条目已不再出现：{e}")
        if unexpected or stale:
            print(f"🔴 --check 失败：白名单外差异 {len(unexpected)} 条，失效白名单 {len(stale)} 条")
            return 2
        print("✅ --check 通过：种子与四版 Word 一致（白名单除外）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
