"""design §6.4：13 张种子名不一致 sheet 的 47 格三路判定证据（守卫与一次性写入脚本共用同一实现）。

识别口径（以输入为准，不读目录 cell 的 formula_ref，目录重生成后结论不变）：
地址种子 `backend/data/*_address_registry_seed.json` 的条目，其 sheet 在目录中、不是 sheet_verdicts 补登的
sheet，且种子 sheet 名与模板名（目录 sheet_name）、sheet_code、平台底稿索引名（wp_account_mapping.wp_name）
都不同。逐格用 openpyxl 读父级模板册里模板名对应的 tab：

- 坐标超出该 tab 已用范围（max_row / max_column）→ out_of_range → deprecate（replaced_by 父 sheet）；
- 在范围内、该行有文字 → in_range_row_text；行空 → in_range_row_empty；二者都保留地址，语义待核对。
"""
from __future__ import annotations

import collections
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
_DATA = _BACKEND / "data"
_TEMPLATES = _BACKEND / "wp_templates"
_SEED_RE = re.compile(r"^[a-z]\d*_address_registry_seed\.json$")
_PARENT_RE = re.compile(r"^([A-S]\d+)")

OUT_OF_RANGE = "out_of_range"
CLASSES = ("in_range_row_text", "in_range_row_empty", OUT_OF_RANGE)
KEEP_VERDICT = "keep_semantic_unverified"
KIND = "seed_name_mismatch"


def _rel(p: Path) -> str:
    return p.relative_to(_REPO).as_posix()


def _parent_of(code: str) -> str:
    m = _PARENT_RE.match(code)
    return m.group(1) if m else code


@lru_cache(maxsize=1)
def _platform_names() -> dict[str, frozenset[str]]:
    mp = json.loads((_DATA / "wp_account_mapping.json").read_text(encoding="utf-8"))
    out: dict[str, set[str]] = collections.defaultdict(set)
    for m in mp.get("mappings", []):
        if m.get("wp_code") and m.get("wp_name"):
            out[m["wp_code"]].add(m["wp_name"])
    return {k: frozenset(v) for k, v in out.items()}


def seed_name_mismatch_cells(catalog_sheets: list[dict], added_sheet_codes: set[str]) -> list[dict[str, Any]]:
    """按输入识别三名都不同的种子坐标（不含 openpyxl 证据）。"""
    from app.services.acnr.catalog import CatalogIndex
    from app.services.acnr.exact_identity import sheet_of

    by_code = {s["sheet_code"]: s for s in catalog_sheets}
    index = CatalogIndex({"version": "1", "registry_version": "x", "sheets": list(catalog_sheets), "cells": []})
    plat = _platform_names()
    rows: list[dict[str, Any]] = []
    for seed in sorted(p for p in _DATA.iterdir() if p.is_file() and _SEED_RE.match(p.name)):
        data = json.loads(seed.read_text(encoding="utf-8"))
        for entry in data.get("entries", []):
            code, seed_name = entry.get("wp_code", ""), entry.get("sheet_name", "")
            s = by_code.get(code)
            if s is None or code in added_sheet_codes:
                continue
            if seed_name in (s.get("sheet_name"), code) or seed_name in plat.get(code, frozenset()):
                continue
            parent = _parent_of(code)
            # 种子名以完整词元带出本 sheet 编码（exact_identity 第 6 步可回本 sheet）的不算「三名都不同」
            hit = sheet_of(parent, seed_name, index=index)
            if hit.ok and (hit.entry or {}).get("sheet_code") == code:
                continue
            for coord in entry.get("coordinates", []):
                a1 = coord.get("cell_address") or coord.get("cell_ref")
                if not a1:
                    continue
                rows.append({
                    "addr_id": f"{parent}/{code}/{a1}", "parent_sheet_code": f"{parent}/{code}",
                    "parent_wp_code": parent, "sheet_code": code, "template_name": s.get("sheet_name"),
                    "a1": a1, "seed_file": _rel(seed), "seed_name": seed_name,
                    "seed_semantic": coord.get("description", "") or coord.get("label", "") or None,
                })
    return sorted(rows, key=lambda r: r["addr_id"])


def with_template_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """逐格补 openpyxl 证据与三路分类。"""
    import openpyxl
    from openpyxl.utils.cell import column_index_from_string, coordinate_from_string

    books: dict[Path, Any] = {}
    out: list[dict[str, Any]] = []
    try:
        for r in rows:
            r = dict(r)
            parent = r["parent_wp_code"]
            files = sorted(p for p in (_TEMPLATES / parent[:1]).glob("*.xlsx") if re.match(rf"^{re.escape(parent)} ", p.name))
            if not files:
                raise AssertionError(f"{r['addr_id']}：父级 {parent} 没有模板册")
            if files[0] not in books:
                books[files[0]] = openpyxl.load_workbook(files[0], data_only=False)
            wb = books[files[0]]
            tab = r["template_name"]
            if tab not in wb.sheetnames:
                raise AssertionError(f"{r['addr_id']}：模板册 {files[0].name} 没有模板名 tab「{tab}」")
            ws = wb[tab]
            col_letter, row_no = coordinate_from_string(r["a1"])
            col = column_index_from_string(col_letter)
            r.update({"template_file": _rel(files[0]), "template_tab": tab, "seed_tab_exists": r["seed_name"] in wb.sheetnames,
                      "max_row": ws.max_row, "max_col": ws.max_column})
            if row_no > ws.max_row or col > ws.max_column:
                r.update({"class": OUT_OF_RANGE, "row_text": None, "cell_value": None})
            else:
                texts = [str(ws.cell(row=row_no, column=j).value).strip() for j in range(1, ws.max_column + 1)
                         if isinstance(ws.cell(row=row_no, column=j).value, str) and str(ws.cell(row=row_no, column=j).value).strip()]
                v = ws.cell(row=row_no, column=col).value
                r.update({"class": "in_range_row_text" if texts else "in_range_row_empty",
                          "row_text": " | ".join(texts)[:200] or None, "cell_value": None if v is None else str(v)[:120]})
            out.append(r)
    finally:
        for wb in books.values():
            wb.close()
    return out


def verdict_record(r: dict[str, Any]) -> dict[str, Any]:
    """三路证据 → cell_verdicts 记录（生成器只读 verdict / replaced_by，其余为证据）。"""
    ev = {k: r[k] for k in ("template_file", "template_tab", "max_row", "max_col", "seed_file", "seed_name",
                            "seed_semantic", "seed_tab_exists", "row_text", "cell_value", "class")}
    if r["class"] == OUT_OF_RANGE:
        return {"addr_id": r["addr_id"], "parent_sheet_code": r["parent_sheet_code"], "kind": KIND, "verdict": "deprecate",
                "replaced_by": r["parent_sheet_code"],
                "reason": f"种子坐标超出模板已用范围（{r['template_tab']} 共 {r['max_row']} 行 {r['max_col']} 列）",
                "evidence": ev}
    return {"addr_id": r["addr_id"], "parent_sheet_code": r["parent_sheet_code"], "kind": KIND, "verdict": KEEP_VERDICT,
            "replaced_by": None, "reason": "种子名与模板名、平台名都不同，坐标在模板已用范围内但种子语义与模板行文字不符：地址保留，语义待核对",
            "evidence": ev}
