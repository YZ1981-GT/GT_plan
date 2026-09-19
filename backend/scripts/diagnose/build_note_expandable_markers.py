"""生成可扩行标记词表真源 `backend/data/note_expandable_markers.json`（只读）。

**判据不在本文件** —— 词表与匹配函数的单一真源是
``backend/app/services/note_expandable_markers.py``（纯函数、stdlib-only、
无 IO），本脚本只负责：扫源 xlsx → 统计命中 → 写 JSON → CLI。

为什么判据要放 service 层：``row_type`` 有多个写者（本 spec 的
``fix_note_expandable_rows.py``、共享行构造器 ``_note_structure_kit.data_row()``、
以及若干 per-cycle 幂等脚本会**整表重写 rows**）。判据留在 diagnose 脚本里 ⇒
写者互相翻转（实测 soe `四、生物资产` 4 行被翻回 `data`，2026-08-08）。

扫描真源 = `backend/wp_templates/**` 的**披露 sheet**（运行时权威目录；
`基础数据/` 是已落后的参考副本，见 memory 铁律）。

产出每个词的：
* `source_hits`  该词在披露 sheet 里的命中次数（全量扫）
* `source_ref`   一处可复验的定位（相对路径 + sheet + cell + 原文）
                 —— 守卫据它做 **openpyxl 直读单元格** 的 stale 检测，
                    只开 6 个文件，可进 CI。

spec: note-template-columns-and-legacy-snapshot-closure Requirement 11.1 / Property 34
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
BACKEND_ROOT = _HERE.parents[2]
WP_TEMPLATES = BACKEND_ROOT / "wp_templates"
DEFAULT_OUT = BACKEND_ROOT / "data" / "note_expandable_markers.json"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# 🔴 判据单一真源：词表 + 匹配函数一律从 service 层取，本文件不得再声明一份。
from app.services.note_expandable_markers import (  # noqa: E402
    EXPANDABLE_ROW_TYPE,
    LABEL_MARKER_EXCLUDED,
    LABEL_MARKERS,
    MARKERS,
    label_candidates,
    match_label_marker,
    match_marker,
    normalize_label,
    row_type_for_label,
)

__all__ = [
    "EXPANDABLE_ROW_TYPE",
    "LABEL_MARKERS",
    "LABEL_MARKER_EXCLUDED",
    "MARKERS",
    "build",
    "label_candidates",
    "match_label_marker",
    "match_marker",
    "normalize_label",
    "row_type_for_label",
    "scan_sources",
]

#: 披露 sheet 名判据（源模板 21 种括号/后缀写法，归一后判「附注披露信息」前缀）
_DISCLOSURE_SHEET_RE = re.compile(r"附注披露信息")


def scan_sources() -> dict[str, Any]:
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover
        return {"error": "openpyxl 未安装"}

    hits: Counter = Counter()
    first_ref: dict[str, dict[str, Any]] = {}
    sheets_scanned = 0
    files_scanned = 0

    for xlsx in sorted(WP_TEMPLATES.rglob("*.xlsx")):
        if xlsx.name.startswith("~$"):
            continue
        try:
            wb = load_workbook(xlsx, data_only=True, read_only=True)
        except Exception:  # noqa: BLE001
            continue
        files_scanned += 1
        try:
            for ws in wb.worksheets:
                if not _DISCLOSURE_SHEET_RE.search(str(ws.title or "")):
                    continue
                sheets_scanned += 1
                for row in ws.iter_rows():
                    for cell in row:
                        marker = match_marker(cell.value)
                        if not marker:
                            continue
                        hits[marker] += 1
                        if marker not in first_ref:
                            first_ref[marker] = {
                                "path": str(xlsx.relative_to(BACKEND_ROOT)).replace("\\", "/"),
                                "sheet": str(ws.title),
                                "cell": cell.coordinate,
                                "text": str(cell.value),
                            }
        finally:
            wb.close()

    return {
        "files_scanned": files_scanned,
        "disclosure_sheets_scanned": sheets_scanned,
        "hits": {m: hits.get(m, 0) for m in MARKERS},
        "source_ref": first_ref,
    }


def build(scan: dict[str, Any]) -> dict[str, Any]:
    return {
        "_source": "backend/wp_templates/**/*.xlsx 的「附注披露信息*」sheet（运行时权威目录）",
        "_generator": "backend/scripts/diagnose/build_note_expandable_markers.py",
        "_judge_source": "backend/app/services/note_expandable_markers.py（词表与匹配函数的单一真源）",
        "_note": (
            "六种可扩行标记写法的命中统计与源证据。词表顺序即匹配优先级（长串先于短串）。"
            "判据本体在 app/services/note_expandable_markers.py —— 幂等脚本、行构造器"
            "（_note_structure_kit.data_row）、per-cycle 脚本与守卫共用它，禁止各写一份，"
            "否则多个 row_type 写者会互相翻转。"
        ),
        "_spec": "note-template-columns-and-legacy-snapshot-closure R11.1 / Property 34",
        "markers": list(MARKERS),
        "label_markers": list(LABEL_MARKERS),
        "label_marker_excluded": dict(LABEL_MARKER_EXCLUDED),
        "files_scanned": scan.get("files_scanned"),
        "disclosure_sheets_scanned": scan.get("disclosure_sheets_scanned"),
        "source_hits": scan.get("hits"),
        "source_ref": scan.get("source_ref"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成可扩行标记词表真源（只读）")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--check", action="store_true", help="只比对不写盘；不一致 exit 1")
    args = ap.parse_args(argv)

    scan = scan_sources()
    if "error" in scan:
        print("[ERR] " + scan["error"])
        return 2
    payload = build(scan)

    zero = [m for m, n in payload["source_hits"].items() if not n]
    lines = [
        "[scan] files=%s disclosure_sheets=%s"
        % (payload["files_scanned"], payload["disclosure_sheets_scanned"]),
        "[hits] " + ", ".join("%s=%d" % (m, n) for m, n in payload["source_hits"].items()),
    ]
    if zero:
        lines.append("[ERR] 以下词在源披露 sheet 零命中（词表失效或源模板变更）：%s" % zero)

    out = Path(args.out)
    if args.check:
        if not out.exists():
            lines.append("[ERR] 目标文件不存在：%s" % out)
            print("\n".join(lines))
            return 1
        cur = json.loads(out.read_text(encoding="utf-8"))
        same = cur.get("markers") == payload["markers"] and cur.get("source_hits") == payload["source_hits"]
        lines.append("[OK] 与落盘一致" if same else "[ERR] 与落盘不一致（需重跑 --out）")
        print("\n".join(lines))
        return 0 if (same and not zero) else 1

    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines.append("[OK] wrote %s" % out)
    print("\n".join(lines))
    return 1 if zero else 0


if __name__ == "__main__":
    raise SystemExit(main())
