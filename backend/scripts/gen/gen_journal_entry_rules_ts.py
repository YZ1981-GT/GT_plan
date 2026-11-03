#!/usr/bin/env python
"""从 ``custom_query_presets.json`` 生成 C24 分录规则词表。

输出无时间戳且顺序跟随权威 JSON；``--check`` 发现缺失或漂移时返回 2。

用法（cwd 任意）::

    python backend/scripts/gen/gen_journal_entry_rules_ts.py --write
    python backend/scripts/gen/gen_journal_entry_rules_ts.py --check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE_PATH = ROOT / "backend" / "data" / "custom_query_presets.json"
OUTPUT_PATH = ROOT / "audit-platform" / "frontend" / "src" / "generated" / "journalEntryRules.ts"


def _keyword_values(document: dict[str, object], key: str) -> list[str]:
    keyword_sets = document.get("keyword_sets")
    if not isinstance(keyword_sets, dict):
        raise ValueError("custom_query_presets.json 缺少 keyword_sets 对象")

    values = keyword_sets.get(key)
    if not isinstance(values, list) or not values:
        raise ValueError(f"keyword_sets.{key} 必须是非空数组")

    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"keyword_sets.{key} 只能包含非空字符串")
        result.append(value)
    if len(result) != len(set(result)):
        raise ValueError(f"keyword_sets.{key} 不能包含重复词")
    return result


def _ts_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    escaped = escaped.replace("\r", "\\r").replace("\n", "\\n")
    return f"'{escaped}'"


def _render_array(name: str, values: list[str]) -> str:
    body = "\n".join(f"  {_ts_string(value)}," for value in values)
    return f"export const {name} = [\n{body}\n] as const"


def render(document: dict[str, object]) -> str:
    """把权威 JSON 文档渲染成确定性的 TypeScript 常量。"""
    special_event = _keyword_values(document, "special_event")
    vague = _keyword_values(document, "vague")
    header = (
        "// @generated DO NOT EDIT — 由 gen_journal_entry_rules_ts.py 生成\n"
        "// source: backend/data/custom_query_presets.json\n"
        "// spec: advanced-query-linkage-closure · Task 42\n\n"
    )
    return (
        header
        + _render_array("SPECIAL_EVENT_KEYWORDS", special_event)
        + "\n\n"
        + _render_array("VAGUE_KEYWORDS_DEFAULT", vague)
        + "\n"
    )


def _load() -> dict[str, object]:
    document = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("custom_query_presets.json 根节点必须是对象")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="写入生成文件")
    mode.add_argument("--check", action="store_true", help="校验生成文件，漂移时返回 2")
    args = parser.parse_args(argv)

    content = render(_load())
    existing = OUTPUT_PATH.read_bytes() if OUTPUT_PATH.exists() else b""
    if args.check:
        if existing.decode("utf-8").replace("\r\n", "\n") == content:
            print("journalEntryRules.ts 与 custom_query_presets.json 一致")
            return 0
        print("journalEntryRules.ts 缺失或已漂移：运行 --write 重新生成", file=sys.stderr)
        return 2

    newline = "\r\n" if b"\r\n" in existing else "\n"
    generated = content.replace("\n", newline).encode("utf-8")
    if generated != existing:
        OUTPUT_PATH.write_bytes(generated)
    print(f"已生成 {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
