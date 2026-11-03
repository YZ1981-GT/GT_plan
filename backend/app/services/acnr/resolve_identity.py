"""full_resolve 第 1 步的身份推导与停用字段（T10，design §6.2 / §3.3）。

`resolver.py` 已超行数门禁，第 1 步「写法 → addr_id」与命中结果的停用字段放在这里：

- `step1_identity`：uri / formula_ref / index_ref 经 `catalog` 的结构化判定（内部只用
  `exact_identity.sheet_of`）推导 addr_id；多义或命中禁止别名时返回可直接作为结果的字段
  （`found=False` + `error` + 中文 `reason` + `required_context` + 候选），调用方不得再按别的规则猜。
  判定用调用方传入的目录（版本锁定时即锁定快照），不读当前目录。
- `deprecation_fields`：命中停用条目时返回 `deprecated` / `replaced_by` / 中文 `reason`
  （「该地址已停用，建议改用 …」），非停用条目返回空字典。
- `cell_candidate` / `computed_display_label`：候选与命中的显示名（T29）——目录条目取目录的 `display_label`，
  L3 运行时条目与非底稿域委托结果用 `display.cell_labels` 现算。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.acnr import display, reasons
from app.services.acnr.catalog import (
    _formula_ref_to_sheet_match,
    _index_ref_to_addr_id,
    _uri_to_sheet_match,
)

if TYPE_CHECKING:
    from app.services.acnr.catalog import CatalogIndex

#: 候选最多返回几条（与 miss 候选同口径）
_MAX_CANDIDATES = 5


def _label(cat: "CatalogIndex", addr_id: str) -> str:
    entry = cat.sheets_by_addr_id.get(addr_id) or cat.cells_by_addr_id.get(addr_id) or {}
    return (entry.get("display_label") or entry.get("sheet_name")
            or entry.get("semantic_label") or addr_id)


def step1_identity(
    cat: "CatalogIndex",
    *,
    uri: str | None,
    formula_ref: str | None,
    addr_id: str | None,
    index_ref: str | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """返回 (推导出的 addr_id, 拒绝结果字段)；拒绝结果非 None 时 addr_id 为 None。"""
    if addr_id:
        return addr_id, None
    if index_ref and not uri and not formula_ref:
        return _index_ref_to_addr_id(index_ref, index=cat), None
    if uri:
        ident = _uri_to_sheet_match(uri, index=cat)
    elif formula_ref:
        ident = _formula_ref_to_sheet_match(formula_ref, index=cat)
    else:
        return None, None
    if not ident.blocked:
        return ident.addr_id, None
    sm = ident.match
    return None, {
        "found": False,
        "error": sm.state,
        "reason": sm.reason,
        "required_context": list(sm.required_context),
        "candidates": [
            {"addr_id": a, "display_label": _label(cat, a), "score": 1.0}
            for a in sm.candidates[:_MAX_CANDIDATES]
        ],
        "source_layer": "L1_sheet",
    }


def cell_candidate(cell: dict) -> dict[str, Any]:
    """目录 cell 候选：显示名取目录的 `display_label`（T29 由生成器写入）。"""
    return {"addr_id": cell.get("addr_id"),
            "display_label": cell.get("display_label") or cell.get("semantic_label") or cell.get("addr_id"),
            "score": 1.0}


def computed_display_label(head: str | None, cell_address: str | None, semantic_label: str | None) -> str:
    """不在目录里的命中（L3 运行时条目、非底稿域委托 V1）用目录同一函数 `display.cell_labels` 现算显示名。"""
    return display.cell_labels(head or "", {"cell_address": cell_address, "semantic_label": semantic_label})[1]


def deprecation_fields(entry: dict, cat: "CatalogIndex") -> dict[str, Any]:
    """停用条目的 `deprecated` / `replaced_by` / `reason`；非停用条目返回 {}。"""
    if not entry.get("deprecated"):
        return {}
    replaced_by = entry.get("replaced_by")
    target = _label(cat, replaced_by) if replaced_by else "（未登记替代地址）"
    return {
        "deprecated": True,
        "replaced_by": replaced_by,
        "reason": reasons.DEPRECATED_REASON.format(replaced_by=target),
    }


__all__ = ["step1_identity", "deprecation_fields", "cell_candidate", "computed_display_label"]
