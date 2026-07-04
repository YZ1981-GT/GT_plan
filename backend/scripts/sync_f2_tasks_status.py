#!/usr/bin/env python3
"""Sync f2-inventory-* tasks.md checkboxes with implemented code (2026-07-04)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPECS = ROOT / ".kiro" / "specs"

BANNER = """
> **代码同步（2026-07-04）**：下列 `[x]` 已与仓库实现对齐；`[ ]*` 为可选 PBT；Checkpoint/最终验收/性能打磨仍待人工确认。

"""

# Subtask IDs to mark done (never touch [ ]*)
MAIN_DONE = {
    "3.1", "4.1", "7.1", "8.1", "10.1", "11.1", "12.1",
    "15.2", "15.3", "15.4", "15.5", "15.6",
    "16.1", "16.2", "17.1", "17.2", "17.3", "17.4",
    "18.1", "19.1", "19.2", "20.1", "20.2", "21.1", "23.1",
    "27.1", "28.1", "29.1", "29.2", "29.3",
}
MAIN_PARENTS = {3, 4, 7, 8, 10, 11, 12, 15, 16, 17, 18, 19, 20, 21, 23, 27, 28, 29}

SPECIAL_DONE = {
    "3.1", "4.1", "4.2", "4.3", "5.1", "5.2", "5.3",
    "7.2", "7.3", "7.4",
    "8.2", "8.3", "8.4", "8.5",
    "10.1", "10.2", "10.3", "10.4", "10.5", "10.6", "10.7", "10.8",
    "11.1", "11.2", "12.1", "12.2", "13.1", "14.1",
    "15.1", "16.1", "17.3", "18.1",
}
SPECIAL_PARENTS = {3, 4, 5, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17, 18}

VAL_DONE = {
    "3.1", "4.1", "5.1", "6.1", "6.2", "6.3", "11.3",
    "8.2", "8.3", "8.4",
    "9.1", "9.2", "9.3", "9.4",
    "10.1", "10.2", "11.1", "11.2",
    "13.1", "14.1", "14.2", "17.1", "18.1", "19.1",
}
VAL_PARENTS = {3, 4, 5, 6, 8, 9, 10, 11, 13, 14, 17, 18, 19}

CONFIG = {
    "f2-inventory-main": (MAIN_DONE, MAIN_PARENTS),
    "f2-inventory-special": (SPECIAL_DONE, SPECIAL_PARENTS),
    "f2-inventory-valuation-impairment": (VAL_DONE, VAL_PARENTS),
}


def _mark_subtasks(content: str, done_ids: set[str]) -> str:
    def repl(m: re.Match) -> str:
        tid = m.group(1)
        if tid in done_ids:
            return f"  - [x] {tid}"
        return m.group(0)

    return re.sub(r"  - \[ \] (\d+\.\d+)", repl, content)


def _mark_parents(content: str, parents: set[int]) -> str:
    def repl(m: re.Match) -> str:
        num = int(m.group(1))
        if num in parents:
            return f"- [x] {num}."
        return m.group(0)

    return re.sub(r"^- \[ \] (\d+)\.", repl, content, flags=re.MULTILINE)


def sync_file(spec: str, done_ids: set[str], parents: set[int]) -> None:
    path = SPECS / spec / "tasks.md"
    text = path.read_text(encoding="utf-8")
    if "代码同步（2026-07-04）" not in text:
        # insert after first ## Overview block line
        idx = text.find("\n## Notes")
        if idx == -1:
            idx = text.find("\n## Tasks")
        if idx != -1:
            text = text[:idx] + BANNER + text[idx:]
    text = _mark_subtasks(text, done_ids)
    text = _mark_parents(text, parents)
    path.write_text(text, encoding="utf-8")
    print(f"Updated {path.relative_to(ROOT)}")


def main() -> None:
    for spec, (done, parents) in CONFIG.items():
        sync_file(spec, done, parents)


if __name__ == "__main__":
    main()
