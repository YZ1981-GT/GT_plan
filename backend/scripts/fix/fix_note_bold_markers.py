#!/usr/bin/env python
"""附注模板剥离 markdown 粗体标记 `**`（平台级幂等修订）。

**问题**：`note_template_{listed,soe}.json` 的 `text_sections` / `tables[].guidance`
里残留 `附注模版/*.md` 的 markdown 粗体标记（`rebuild_note_from_md.py` 的搬运产物）。

- 附注正文 `text_content` 由 `disclosure_engine` 按纯文本拼接
- `note_word_exporter` 同样按纯文本写 docx

→ 两处都把 `**` 当字面量显示给用户（如「**重要提示**：本公司…」）。

**🔴 关键约束：只做成对剥离。**

实测有 2 段的 `**` 是**不成对**的脱敏占位（会计师事务所模板惯例，`XXX` 的同类）::

    本公司之控股子公司北京公司因有关债务纠纷事宜被他人起诉，诉讼金额为**元，…

无脑 `replace('**', '')` 会把 `诉讼金额为**元` 变成 `诉讼金额为元`，语义被破坏。
故用非贪婪成对正则 `\\*\\*(.+?)\\*\\*`：孤立的 `**` 天然匹配不上，原样保留；
并由 :func:`odd_marker_paragraphs` 单独列示这些段落供人工确认。

**修订内容**：`**xxx**` → `xxx`，非 `*` 字符逐字不变。

Usage::

    python backend/scripts/fix/fix_note_bold_markers.py --dry-run
    python backend/scripts/fix/fix_note_bold_markers.py --apply
    python backend/scripts/fix/fix_note_bold_markers.py --check

spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

PATHS = [
    DATA_DIR / "note_template_listed.json",
    DATA_DIR / "note_template_soe.json",
]

#: 成对粗体：非贪婪，跨行（`re.S`），内容至少 1 字符。
#: 用非贪婪保证 `**a** 与 **b**` 被拆成两对而非一对（否则中间的文字也被当标记内容）。
BOLD_PAIR = re.compile(r"\*\*(.+?)\*\*", re.S)

#: 幂等循环上限（嵌套 `****xxx****` 需多轮；正常数据 1 轮即收敛）
_MAX_ROUNDS = 3


def strip_pairs(text: Any) -> tuple[Any, int]:
    """成对剥离 `**`，返回 ``(新文本, 剥离对数)``。

    - 非字符串原样返回，计数 0
    - 不成对的 `**`（出现次数为奇数）原样保留
    - 幂等：对已剥离的文本再调用返回计数 0
    """
    if not isinstance(text, str) or "**" not in text:
        return text, 0
    total = 0
    cur = text
    for _ in range(_MAX_ROUNDS):
        cur, n = BOLD_PAIR.subn(r"\1", cur)
        total += n
        if n == 0:
            break
    return cur, total


def count_markers(text: str) -> int:
    """`**` 出现次数（不重叠计数，与 `str.count` 同口径）。"""
    return text.count("**")


def _walk_rows(rows: Any):
    """递归遍历行（含 `children` 嵌套），产出 ``(row_dict,)``。"""
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        yield row
        yield from _walk_rows(row.get("children"))


class Finding:
    __slots__ = ("variant", "section", "where", "before", "after", "pairs")

    def __init__(self, variant: str, section: str, where: str, before: str, after: str, pairs: int):
        self.variant = variant
        self.section = section
        self.where = where
        self.before = before
        self.after = after
        self.pairs = pairs

    def __str__(self) -> str:
        head = self.before.strip().replace("\n", " ")[:70]
        return f"{self.variant} §{self.section} {self.where}（{self.pairs} 对）：{head}…"


def scan_doc(doc: dict[str, Any], variant: str, *, apply: bool) -> tuple[list[Finding], list[Finding]]:
    """扫全文档。返回 ``(成对命中, 不成对段落)``；``apply=True`` 时就地剥离成对标记。"""
    pairs: list[Finding] = []
    odd: list[Finding] = []

    def handle(container: Any, key: Any, section_no: str, where: str) -> None:
        value = container[key]
        if not isinstance(value, str) or "**" not in value:
            return
        new, n = strip_pairs(value)
        if n:
            pairs.append(Finding(variant, section_no, where, value, new, n))
            if apply:
                container[key] = new
        # 剥离后仍残留 `**` = 不成对（脱敏占位），单独列示，不改
        if count_markers(new) > 0:
            odd.append(Finding(variant, section_no, where, value, new, 0))

    for section in doc.get("sections", []) or []:
        section_no = str(section.get("section_number") or "?")

        ts = section.get("text_sections")
        if isinstance(ts, list):
            for i in range(len(ts)):
                handle(ts, i, section_no, f"text_sections[{i}]")

        for row in _walk_rows(section.get("rows")):
            for key in ("label", "guidance"):
                if key in row:
                    handle(row, key, section_no, f"rows.{key}")

        for ti, tbl in enumerate(section.get("tables") or []):
            if not isinstance(tbl, dict):
                continue
            tname = str(tbl.get("name", ""))
            for key in ("guidance", "name"):
                if key in tbl:
                    handle(tbl, key, section_no, f"tables[{ti}]{tname}.{key}")
            headers = tbl.get("headers")
            if isinstance(headers, list):
                for i in range(len(headers)):
                    handle(headers, i, section_no, f"tables[{ti}]{tname}.headers[{i}]")
            for col in tbl.get("columns") or []:
                if isinstance(col, dict):
                    for key in ("label", "group"):
                        if key in col:
                            handle(col, key, section_no, f"tables[{ti}]{tname}.columns[{col.get('key')}].{key}")
            for row in _walk_rows(tbl.get("rows")):
                for key in ("label", "guidance"):
                    if key in row:
                        handle(row, key, section_no, f"tables[{ti}]{tname}.rows.{key}")

    return pairs, odd


def process(path: Path, *, apply: bool, check_only: bool) -> tuple[bool, list[str]]:
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    variant = "listed" if "listed" in path.name else "soe"
    log = [f"=== {path.name} ==="]

    pairs, odd = scan_doc(doc, variant, apply=apply and not check_only)

    if odd:
        log.append(f"[INFO] {len(odd)} 处不成对 `**`（脱敏占位，脚本不改）：")
        log.extend("  ~ " + str(f) for f in odd)

    if check_only:
        if pairs:
            log.append(f"[FAIL] {len(pairs)} 处成对 `**` 未剥离：")
            log.extend("  x " + str(f) for f in pairs)
            return False, log
        log.append("无成对 `**` 残迹")
        return True, log

    if not pairs:
        log.append("无需修改（无成对 `**`）")
        return True, log

    log.append(f"剥离 {len(pairs)} 处成对 `**`（共 {sum(f.pairs for f in pairs)} 对）：")
    log.extend("  " + str(f) for f in pairs)

    if not apply:
        log.append("[dry-run] 未写文件（加 --apply 才写）")
        return True, log

    trailing = "\n" if raw.endswith("\n") else ""
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + trailing, encoding="utf-8")
    log.append(f"已写入 {path}")
    return True, log


def main() -> int:
    ap = argparse.ArgumentParser(description="附注模板剥离 markdown 粗体标记（成对，幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只打印命中项，不写文件（默认行为）")
    ap.add_argument("--apply", action="store_true", help="写入文件")
    ap.add_argument("--check", action="store_true", help="仅校验（供 CI）")
    args = ap.parse_args()

    ok_all = True
    for path in PATHS:
        ok, log = process(path, apply=args.apply, check_only=args.check)
        print("\n".join(log))
        print()
        ok_all = ok_all and ok

    if not ok_all:
        print("[FAIL] 存在未通过项")
        return 1
    print("[OK] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
