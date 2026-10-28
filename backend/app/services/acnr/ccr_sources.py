"""跨底稿引用（CCR，`cross_wp_references.json`）端点的规范身份（acnr-foundation-defect-closure T22，design §10.3）。

CCR 的源端点是「源底稿 + 源表文字 + 源格」，目标端点是「目标底稿 + 目标表文字 + 目标格」。本模块只用
`exact_identity.sheet_of` / `cell_of` 判表身份，不另写匹配（原 CCR 检查器的「编码 → 名称首个命中 → 子串」
私有判定已删除，见 design §6.1：它把 94 个源配到别的表）。

- 表已识别：源格是 A1 时 addr_id 为 `{表 addr_id}/{A1}`（`in_catalog` 标明是否目录登记格）；源格不是 A1
  （语义标签，如「审定数」）时 addr_id 取表本身。
- 表未识别（底稿不在目录、表名不在目录、多义、命中禁止别名）：不给 addr_id，带 `exact_identity` 的中文原因。
- 目标端点没有底稿编码（附注 / 报表等模块目标）的不参与身份判定。

生成器（`catalog_build.build_release`，把不可解析源写进报告 `open_problems.ccr_unresolved` 供豁免门禁核实）
与 CI 检查器 `backend/scripts/acnr/check_ccr_resolve.py` 共用本模块，保证两边对「哪些源不可解析」口径一致。

只依赖标准库与本包。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable

from . import exact_identity
from .catalog_contract import A1_PATTERN

if TYPE_CHECKING:  # pragma: no cover
    from .catalog import CatalogIndex

_A1_RE = re.compile(A1_PATTERN)

#: 源字段缺失时的原因（其余原因都来自 exact_identity）
NO_SOURCE_REASON = "CCR 条目缺源底稿编码或源表名，无法判定身份"


@dataclass(frozen=True)
class CcrEnd:
    """CCR 一个端点的规范身份。state 为 exact_identity.sheet_of 的状态，或 no_source_fields。"""

    ref_id: str
    role: str  # source / target
    state: str
    addr_id: str | None = None
    sheet_addr_id: str | None = None
    in_catalog: bool = False
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.state == "ok"


def _end(ref_id: str, role: str, wp_code: str, sheet: str, cell: str, index: "CatalogIndex") -> CcrEnd:
    if not wp_code or not sheet:
        return CcrEnd(ref_id, role, "no_source_fields", reason=NO_SOURCE_REASON)
    sm = exact_identity.sheet_of(wp_code, sheet, index=index)
    if not sm.ok or sm.entry is None:
        return CcrEnd(ref_id, role, sm.state, reason=sm.reason)
    sheet_addr_id = sm.entry["addr_id"]
    if cell and _A1_RE.match(cell.upper()):
        cm = exact_identity.cell_of(wp_code, sheet, cell, index=index)
        if cm.ok and cm.addr_id:
            return CcrEnd(ref_id, role, "ok", addr_id=cm.addr_id, sheet_addr_id=sheet_addr_id, in_catalog=cm.in_catalog)
    return CcrEnd(ref_id, role, "ok", addr_id=sheet_addr_id, sheet_addr_id=sheet_addr_id,
                  in_catalog=sheet_addr_id in index.sheets_by_addr_id)


def source_end(ref: dict[str, Any], index: "CatalogIndex") -> CcrEnd:
    """CCR 源端点：source_wp + source_sheet + source_cell。"""
    return _end(str(ref.get("ref_id", "?")), "source", str(ref.get("source_wp") or ""),
                str(ref.get("source_sheet") or ""), str(ref.get("source_cell") or ""), index)


def target_ends(ref: dict[str, Any], index: "CatalogIndex") -> list[CcrEnd]:
    """CCR 目标端点（只取带 wp_code 的底稿目标）：wp_code + sheet + cell。

    不再拿目标的 `formula` 判身份：那个公式写的是目标格引用源的写法（如 `=WP('H1','折旧分配分析表H1-13',…)`），
    指向源而不是目标本身。"""
    rid = str(ref.get("ref_id", "?"))
    return [_end(rid, "target", str(t.get("wp_code") or ""), str(t.get("sheet") or ""), str(t.get("cell") or ""), index)
            for t in ref.get("targets") or [] if isinstance(t, dict) and t.get("wp_code")]


def unresolved_source_ids(references: Iterable[dict[str, Any]], index: "CatalogIndex") -> list[str]:
    """不可解析的 CCR 源（semantic_only 的不计），按 ref_id 排序——生成器写进 open_problems.ccr_unresolved。"""
    return sorted(str(r.get("ref_id", "?")) for r in references
                  if not r.get("semantic_only") and not source_end(r, index).ok)


def is_deprecated(addr_id: str | None, index: "CatalogIndex") -> bool:
    """addr_id 所指 cell 或其所在表为停用条目（design §3.3：CCR 解析到停用条目计入 deprecated 组、不阻断）。"""
    if not addr_id:
        return False
    cell = index.cells_by_addr_id.get(addr_id)
    if cell is not None and cell.get("deprecated"):
        return True
    sheet = index.sheets_by_addr_id.get(addr_id) or index.sheets_by_addr_id.get("/".join(addr_id.split("/")[:2]))
    return bool(sheet and sheet.get("deprecated"))


__all__ = ["CcrEnd", "NO_SOURCE_REASON", "is_deprecated", "source_end", "target_ends", "unresolved_source_ids"]
