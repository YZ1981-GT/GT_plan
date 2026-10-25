#!/usr/bin/env python
"""生成公式推送独占键前端文件。

范围 = policy ∈ {system, derived} 的底稿目标 item_id；
行集目标（four_table_leaves）不进独占集合（用户可编辑同一行的其他字段）。
editable 目标不进（用户可改，后端三态保留）。

输出幂等（无时间戳），内容不变则文件字节不变。
``--check`` 模式比对文件内容，漂移时 exit 2 并点名。

spec: formula-push-all-subjects-rollout · design §五 · 需求 4.1, 4.2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "data" / "formula_push_rules.json"
OUTPUT_PATH = ROOT.parent / "audit-platform" / "frontend" / "src" / "generated" / "formulaPushOwnedKeys.ts"

OWNED_POLICIES = frozenset({"system", "derived"})
EXCLUDED_KINDS = frozenset({"four_table_leaves"})


def compute_owned(rules_path: Path = RULES_PATH) -> dict[str, list[str]]:
    """按主编码分组，返回 {wp_code: sorted([item_id, ...])}。"""
    document = json.loads(rules_path.read_text("utf-8"))
    result: dict[str, set[str]] = {}
    for rule in document.get("rules") or []:
        target = rule.get("target") or {}
        if target.get("domain") != "workpaper":
            continue
        if rule.get("policy") not in OWNED_POLICIES:
            continue
        source = rule.get("source") or {}
        if source.get("kind") in EXCLUDED_KINDS:
            continue
        item_id = target.get("item_id")
        if not item_id:
            continue
        wp_code = (rule.get("page_key") or "").split(":", 1)[-1]
        result.setdefault(wp_code, set()).add(item_id)
    return {code: sorted(items) for code, items in sorted(result.items())}


def render_ts(owned: dict[str, list[str]]) -> str:
    """生成 TypeScript 源码。"""
    lines = [
        "// @generated DO NOT EDIT — 由 gen_formula_push_owned_keys.py 生成",
        "// spec: formula-push-all-subjects-rollout · 需求 4.1",
        "",
        "export const FORMULA_PUSH_OWNED: Record<string, { exact: readonly string[]; patterns: readonly string[] }> = {",
    ]
    for code, items in owned.items():
        exact_str = ", ".join(f"'{item}'" for item in items)
        lines.append(f"  {code}: {{ exact: [{exact_str}], patterns: [] }},")
    lines.append("} as const")
    lines.append("")
    lines.append("/** 判断 item_id 是否是指定主编码的后端独占键。 */")
    lines.append("export function isOwnedKey(wpCode: string, itemId: string): boolean {")
    lines.append("  const entry = FORMULA_PUSH_OWNED[wpCode]")
    lines.append("  if (!entry) return false")
    lines.append("  if (entry.exact.includes(itemId)) return true")
    lines.append("  return entry.patterns.some((p) => new RegExp(p).test(itemId))")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成公式推送独占键前端文件")
    parser.add_argument("--check", action="store_true", help="检查模式：文件内容不一致则 exit 2")
    parser.add_argument("--write", action="store_true", help="写入模式（默认）")
    parser.add_argument("--rules", type=Path, default=RULES_PATH, help="规则 JSON 路径")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="输出文件路径")
    args = parser.parse_args()

    owned = compute_owned(args.rules)
    content = render_ts(owned)

    if args.check:
        if not args.output.exists():
            print(f"生成文件不存在：{args.output}", file=sys.stderr)
            sys.exit(2)
        existing = args.output.read_text("utf-8")
        if existing == content:
            print(f"独占键文件与规则一致（{sum(len(v) for v in owned.values())} 个键）")
            sys.exit(0)
        else:
            # 找出差异
            existing_keys: set[str] = set()
            new_keys: set[str] = set()
            for items in owned.values():
                new_keys.update(items)
            for line in existing.splitlines():
                line = line.strip()
                if line.startswith("'") and line.endswith("',"):
                    existing_keys.add(line.strip("', "))
            added = sorted(new_keys - existing_keys)
            removed = sorted(existing_keys - new_keys)
            msg = "独占键文件与规则不一致"
            if added:
                msg += f"，新增：{added[:5]}"
            if removed:
                msg += f"，删除：{removed[:5]}"
            print(msg, file=sys.stderr)
            sys.exit(2)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"已生成 {args.output}（{sum(len(v) for v in owned.values())} 个键）")


if __name__ == "__main__":
    main()
