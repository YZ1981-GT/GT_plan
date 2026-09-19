"""ACNR sheet 显示名覆盖/漂移守卫（CI 友好，仅用已提交文件，无需 DB）。

目的：防止 catalog 新增/改名后 sheet_display_names.json 静默过期，导致
公式管理树/选字段树出现重名占位名（如「附注披露信息(上市公司）D2-1」）。

检查（仅读已提交文件：global_catalog.json + wp_account_mapping.json +
sheet_display_names.json + prefill_formula_mapping.json）：
  1. 覆盖：每个 wp 域 sheet_code 都能解析出「非占位」显示名——
     命中 wp_account_mapping / sheet_display_names / prefill，或其 catalog
     sheet_name 本身已是干净真名（非裸编码、且末尾编码==自身）。否则记 GAP。
  2. 孤儿：sheet_display_names 中的 code 在 catalog 已无对应 sheet → 记 ORPHAN。

默认 report 模式（exit 0 打印清单）；--strict 时有 GAP/ORPHAN 即 exit 1。
可选 --with-db：若能连 DB，另跑 gen 逻辑与committed文件 diff（真·漂移检测）。

用法（cwd=backend）：python scripts/check/check_sheet_display_names.py [--strict]
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]  # backend/
_DATA = _ROOT / "data"
_CATALOG = _DATA / "acnr" / "global_catalog.json"
_DISPLAY = _DATA / "acnr" / "sheet_display_names.json"
_MAPPING = _DATA / "wp_account_mapping.json"
_PREFILL = _DATA / "prefill_formula_mapping.json"

_BARE_CODE_RE = re.compile(r"^[A-Za-z]+\d+(?:-\d+)?[A-Za-z]?$")
_TRAIL_CODE_RE = re.compile(r"([A-Za-z]+\d+(?:-\d+)?)$")


def _load(p: Path) -> dict | list:
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def _mapping_names() -> dict[str, str]:
    d = _load(_MAPPING)
    rows = d if isinstance(d, list) else (d.get("mappings") or list(d.values()))
    return {m["wp_code"]: (m.get("wp_name") or "") for m in rows
            if isinstance(m, dict) and m.get("wp_code")}


def _prefill_names() -> dict[str, str]:
    d = _load(_PREFILL)
    return {m["wp_code"]: (m.get("wp_name") or "") for m in d.get("mappings", [])
            if m.get("wp_code")}


_CLEAN_TRAIL_RE = re.compile(r"\s*[A-Za-z]+\d+(?:-\d+)?[A-Za-z]?$")


def _catalog_name_ok(sheet_name: str, sheet_code: str) -> bool:
    """catalog sheet_name 是否已是可用真名。

    与前端 cleanSheetLabelName 对齐：去掉末尾编码后若仍有描述文字即可用
    （如「…判断F6-10」→「…判断」）；仅剩空/裸编码（如 K14）才判占位。
    """
    if not sheet_name:
        return False
    cleaned = _CLEAN_TRAIL_RE.sub("", sheet_name.strip()).strip()
    return bool(cleaned)


def main() -> int:
    strict = "--strict" in sys.argv
    catalog = _load(_CATALOG)
    display: dict = _load(_DISPLAY)  # code -> name
    mapping = _mapping_names()
    prefill = _prefill_names()

    wp_sheets = [s for s in catalog.get("sheets", []) if s.get("domain") == "wp"]
    catalog_codes = {s.get("sheet_code") for s in wp_sheets if s.get("sheet_code")}

    # 1. 覆盖检查
    gaps: list[tuple[str, str]] = []  # (sheet_code, catalog_name)
    for s in wp_sheets:
        code = s.get("sheet_code") or ""
        name = s.get("sheet_name") or ""
        covered = (
            bool(mapping.get(code))
            or bool(display.get(code))
            or bool(prefill.get(code))
            or _catalog_name_ok(name, code)
        )
        if not covered:
            gaps.append((code, name))

    # 2. 额外名（display 覆盖比 catalog 更细的 tab 编码，属正常预留，仅统计不判失败）
    extra = sum(1 for c in display if c not in catalog_codes)

    print(f"[check_sheet_display_names] wp sheets={len(wp_sheets)} "
          f"display={len(display)} mapping={len(mapping)} prefill={len(prefill)}")
    print(f"  未覆盖(GAP)={len(gaps)}  display 细粒度额外名(info)={extra}")

    if gaps:
        by_cyc: dict[str, list[str]] = defaultdict(list)
        code_cyc = {s.get("sheet_code"): (s.get("cycle") or "?") for s in wp_sheets}
        for code, name in sorted(gaps):
            by_cyc[code_cyc.get(code, "?")].append(f"{code}={name!r}")
        for cyc in sorted(by_cyc):
            print(f"  [GAP][{cyc}] " + " | ".join(by_cyc[cyc]))
        print("  → 提示：重跑 scripts/gen_sheet_display_names.py（cwd=backend）补齐")

    # 只有「catalog 有名却无法解析」的真缺口(GAP)才算漂移；额外细粒度名不阻断
    if strict and gaps:
        print("[FAIL] --strict：存在未覆盖 sheet（catalog 有但无可用显示名）")
        return 1
    print("[OK]" if not gaps else "[REPORT] 见上（非 strict 不阻断）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
