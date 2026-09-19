#!/usr/bin/env python
"""附注模板表头去 HTML 标记（平台级幂等修订）。

**问题**：`note_template_{listed,soe}.json` 的 `tables[].headers` 里残留
`附注模版/*.md` 表格的排版换行 `<br/>`（`rebuild_note_from_md.py` 的搬运产物）。

- 前端附注编辑器用 `el-table-column :label` 渲染表头，**不解析 HTML**
- `note_word_exporter._build_two_level_header_rows` 同样按纯文本写 docx

→ 两处都会把 `<br/>` 当字面量显示（如「预付款项<br/>期末余额」）。

同步链路侧的 `columns[].label` 各循环本来就是纯文本，因此该缺陷只在
**seed 路径**（新建项目 / 重新生成附注）暴露，久未被发现；守卫
`_disclosureSubtableContract.helper.ts` 的 P4 只校验 `columns`，模板 `headers`
原是盲区（现已补 P6）。

**修订内容**：剥离 `headers` / `columns[].label` / `columns[].group` 中的 HTML 标记，
不改变文字内容（`预付款项<br/>期末余额` → `预付款项期末余额`）。

Usage::

    python backend/scripts/fix/fix_note_headers_plaintext.py --dry-run
    python backend/scripts/fix/fix_note_headers_plaintext.py
    python backend/scripts/fix/fix_note_headers_plaintext.py --check

spec: .kiro/specs/f-cycle-disclosure-parity/ R7 / R8
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

_HTML_RE = re.compile(r"<[^>]+>")


def strip_html(text: Any) -> Any:
    """剥离 HTML 标记；非字符串原样返回。"""
    if not isinstance(text, str):
        return text
    if "<" not in text or ">" not in text:
        return text
    return _HTML_RE.sub("", text).strip()


def scan_section(section: dict[str, Any], *, apply: bool) -> list[str]:
    """返回命中项描述；``apply=True`` 时就地剥离。"""
    hits: list[str] = []
    num = section.get("section_number")
    for tbl in section.get("tables") or []:
        name = str(tbl.get("name", ""))

        headers = tbl.get("headers")
        if isinstance(headers, list):
            for i, h in enumerate(headers):
                cleaned = strip_html(h)
                if cleaned != h:
                    hits.append(f"§{num} {name}.headers[{i}]：{h!r} → {cleaned!r}")
                    if apply:
                        headers[i] = cleaned

        for c in tbl.get("columns") or []:
            if not isinstance(c, dict):
                continue
            for key in ("label", "group"):
                cleaned = strip_html(c.get(key))
                if key in c and cleaned != c.get(key):
                    hits.append(
                        f"§{num} {name}.columns[{c.get('key')}].{key}："
                        f"{c.get(key)!r} → {cleaned!r}"
                    )
                    if apply:
                        c[key] = cleaned
    return hits


def process(path: Path, *, dry_run: bool, check_only: bool) -> tuple[bool, list[str]]:
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    log = [f"=== {path.name} ==="]

    all_hits: list[str] = []
    for section in doc.get("sections", []):
        all_hits += scan_section(section, apply=not check_only)

    if check_only:
        if all_hits:
            log.append(f"[FAIL] {len(all_hits)} 处表头含 HTML 标记：")
            log.extend("  " + h for h in all_hits)
            return False, log
        log.append("表头均为纯文本")
        return True, log

    if not all_hits:
        log.append("无需修改（表头均为纯文本）")
        return True, log

    log.append(f"剥离 {len(all_hits)} 处 HTML 标记：")
    log.extend("  " + h for h in all_hits)

    if dry_run:
        log.append("[dry-run] 未写文件")
        return True, log

    trailing = "\n" if raw.endswith("\n") else ""
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + trailing,
        encoding="utf-8",
    )
    log.append(f"已写入 {path}")
    return True, log


def main() -> int:
    ap = argparse.ArgumentParser(description="附注模板表头去 HTML 标记（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只打印命中项，不写文件")
    ap.add_argument("--check", action="store_true", help="仅校验（供 CI）")
    args = ap.parse_args()

    ok_all = True
    for path in PATHS:
        ok, log = process(path, dry_run=args.dry_run, check_only=args.check)
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
