#!/usr/bin/env python
"""生成附注写入归属矩阵 ``backend/data/note_write_ownership_matrix.json``（spec formula-writer-ownership-and-stale design §13）。

输入：``note_workpaper_sync_registry.json`` 按准则登记的章节（治理域）+ ``formula_push.engine.load_push_rules()`` 的附注规则。
每个域内章节两条基础条目（底稿披露容器 → workpaper_sync、模板容器 → binding_refill），推送规则目标逐（表, 字段）一条
推送条目（→ formula_push，scope = pushed_cells）。推送规则目标不在治理域内 ⇒ 拒绝生成（与 D1 矛盾，须先拍板）。

输出幂等（无时间戳，内容不变则字节不变）。``--check``：文件与现算不一致 ⇒ exit 2 并点名差异。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_PATH = ROOT / "data" / "note_write_ownership_matrix.json"
DECISION = ("D1（2026-11-04 用户拍板）：已接「从底稿拉取 / 离屏同步」的章节由后端取数链路唯一写入，"
            "其余章节暂留前端同步，加前后端对拍守卫")
MANUAL_POLICY_INPUTS = ((False, 0), (False, 1), (False, 3), (True, 0), (True, 2))


def _section_key(section: str) -> tuple[str, int, str]:
    match = re.match(r"^(.*?)(\d+)$", section)
    return (match.group(1), int(match.group(2)), "") if match else (section, -1, section)


def compute_matrix() -> dict:
    from app.services.formula_push.engine import load_push_rules
    from app.services.note_readiness_service import _load_registry_entries, registry_sections
    from app.services.note_write_ownership import (
        ANY_TABLE, BINDING_WRITER, CELL_PREFIX, FIELD_ROWS, FIELD_SUB_TABLE, IDENTITY, PUSH_WRITER,
        SCOPE_CELLS, SCOPE_PUSHED, SYNC_WRITER, TEMPLATE_TYPES, never_synced_manual_block,
    )

    codes: dict[tuple[str, str], set[str]] = {}
    for entry in _load_registry_entries():
        code = str(entry.get("wp_code") or "").strip()
        for tt in TEMPLATE_TYPES:
            for sec in registry_sections(entry, tt):
                codes.setdefault((tt, sec), set()).update({code} if code else set())

    push: dict[tuple[str, str], dict[tuple[str, str], set[str]]] = {}
    outside: list[str] = []
    for rule in load_push_rules():
        if rule.stage != "note":
            continue
        for tt, sec in rule.target.sections.items():
            if (tt, sec) not in codes:
                outside.append(f"{rule.rule_id}（{tt} {sec}）")
                continue
            table = rule.target.resolve_table(tt) or rule.target.table
            for field in rule.target.fields:
                push.setdefault((tt, sec), {}).setdefault((table, CELL_PREFIX + field), set()).add(rule.rule_id)
    if outside:
        raise SystemExit(f"推送规则目标章节不在交接域（登记表）内，先登记或拍板：{'、'.join(sorted(outside))}")

    chapters = []
    for tt, sec in sorted(codes, key=lambda k: (TEMPLATE_TYPES.index(k[0]), _section_key(k[1]))):
        entries = [
            {"table_key": ANY_TABLE, "field_key": FIELD_SUB_TABLE, "owner": SYNC_WRITER, "scope": SCOPE_CELLS},
            {"table_key": ANY_TABLE, "field_key": FIELD_ROWS, "owner": BINDING_WRITER, "scope": SCOPE_CELLS},
        ]
        for (table, field), rules in sorted((push.get((tt, sec)) or {}).items()):
            entries.append({"table_key": table, "field_key": field, "owner": PUSH_WRITER, "scope": SCOPE_PUSHED,
                            "rules": sorted(rules)})
        chapters.append({"template_type": tt, "note_section": sec, "wp_codes": sorted(codes[(tt, sec)]),
                         "entries": entries})
    return {
        "_source": "backend/scripts/gen/gen_note_write_ownership_matrix.py",
        "_doc": ".kiro/specs/formula-writer-ownership-and-stale/design.md §13",
        "decision": DECISION,
        "identity": dict(sorted(IDENTITY.items())),
        "manual_policy": {
            "writer": SYNC_WRITER,
            "rule": "never_synced_with_manual_values",
            "cases": [{"synced_before": s, "manual_values": n, "blocked": never_synced_manual_block(s, n)}
                      for s, n in MANUAL_POLICY_INPUTS],
        },
        "chapters": chapters,
    }


def render(matrix: dict) -> str:
    """一章一行表头、一条一行（diff 按条目读）。"""
    def dump(value: object) -> str:
        return json.dumps(value, ensure_ascii=False)

    head = {k: v for k, v in matrix.items() if k != "chapters"}
    lines = ["{"] + [f" {dump(k)}: {dump(v)}," for k, v in head.items()] + [' "chapters": [']
    for ci, chapter in enumerate(matrix["chapters"]):
        meta = {k: v for k, v in chapter.items() if k != "entries"}
        lines.append("  " + dump(meta)[:-1] + ', "entries": [')
        entries = chapter["entries"]
        lines += [f"   {dump(e)}{',' if ei < len(entries) - 1 else ''}" for ei, e in enumerate(entries)]
        lines.append("  ]}" + ("," if ci < len(matrix["chapters"]) - 1 else ""))
    lines += [" ]", "}"]
    return "\n".join(lines) + "\n"


def _entry_keys(matrix: dict) -> set[tuple]:
    return {(c["template_type"], c["note_section"], e["table_key"], e["field_key"], e["owner"])
            for c in matrix.get("chapters") or [] for e in c.get("entries") or []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成附注写入归属矩阵")
    parser.add_argument("--check", action="store_true", help="检查模式：与现算不一致 exit 2")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)

    matrix = compute_matrix()
    content = render(matrix)
    summary = (f"{len(matrix['chapters'])} 章 / "
               f"{sum(len(c['entries']) for c in matrix['chapters'])} 条（推送条目 "
               f"{sum(1 for c in matrix['chapters'] for e in c['entries'] if e['owner'] == 'formula_push')}）")
    if args.check:
        if not args.output.exists():
            print(f"矩阵文件不存在：{args.output}", file=sys.stderr)
            return 2
        existing = args.output.read_text(encoding="utf-8")
        if existing == content:
            print(f"附注写入归属矩阵与登记表 / 推送规则一致：{summary}")
            return 0
        try:
            old = _entry_keys(json.loads(existing))
        except ValueError:
            old = set()
        new = _entry_keys(matrix)
        print(f"附注写入归属矩阵已漂移：新增 {sorted(new - old)[:5]}，删除 {sorted(old - new)[:5]}；"
              f"运行 python backend/scripts/gen/gen_note_write_ownership_matrix.py 重新生成", file=sys.stderr)
        return 2
    args.output.write_text(content, encoding="utf-8")
    print(f"已生成 {args.output}：{summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
