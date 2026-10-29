"""ACNR sheet 显示名报告（薄壳，acnr-foundation-defect-closure T29，design §13.2）。

显示名由目录生成器经 `app.services.acnr.display` 写进 `global_catalog.json` 的 `display_label`；
`sheet_display_names.json` 改为手工维护的生成器输入（原生成脚本 `gen_sheet_display_names.py` 已删除，
重跑会回退手工修正过的条目）。本脚本只读已提交目录，用 `display.py` 同一规则重算名称部分，列出名称为空
（纯编码，只显示编码）的未停用 sheet，并核对目录里的显示名与重算一致。

默认报告模式（exit 0 打印清单）；`--strict` 时有纯编码 sheet 或显示名与重算不一致即 exit 1。

用法（cwd=仓库根）：python backend/scripts/check/check_sheet_display_names.py [--strict]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.acnr import display  # noqa: E402

_CATALOG = _BACKEND / "data" / "acnr" / "global_catalog.json"


def run() -> dict:
    """返回 {sheets, code_only: [addr_id…], mismatched: [addr_id…]}（code_only 只数未停用 sheet）。"""
    catalog = json.loads(_CATALOG.read_text(encoding="utf-8"))
    sources = display.load_name_sources(_BACKEND)
    labels: dict[str, str] = {}
    for group in display.group_by_parent(catalog.get("sheets", [])).values():
        labels.update(display.compose_sheet_labels(group, sources))
    sheets = catalog.get("sheets", [])
    code_only = sorted(s["addr_id"] for s in sheets
                       if not s.get("deprecated") and labels[s["addr_id"]] == (s.get("sheet_code") or ""))
    mismatched = sorted(s["addr_id"] for s in sheets if s.get("display_label") != labels[s["addr_id"]])
    return {"sheets": len(sheets), "code_only": code_only, "mismatched": mismatched}


def main(argv: list[str] | None = None) -> int:
    strict = "--strict" in (sys.argv[1:] if argv is None else argv)
    res = run()
    print(f"[check_sheet_display_names] sheets={res['sheets']} 纯编码（只显示编码）={len(res['code_only'])} "
          f"显示名与重算不一致={len(res['mismatched'])}")
    for aid in res["code_only"]:
        print(f"  [纯编码] {aid}")
    for aid in res["mismatched"][:50]:
        print(f"  [不一致] {aid}（目录未经生成器重新发布）")
    bad = bool(res["code_only"] or res["mismatched"])
    if strict and bad:
        print("[FAIL] --strict：存在纯编码 sheet 或显示名与重算不一致")
        return 1
    print("[OK]" if not bad else "[REPORT] 见上（非 strict 不阻断；补名称改 sheet_display_names.json 后重新发布目录）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
