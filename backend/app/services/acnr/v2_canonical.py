"""V2 依赖图节点的规范身份（acnr-foundation-defect-closure T21，需求 9.1~9.3，design §10.2）。

V2 静态依赖图（L2 语义锚点、resolved refs、L3 依赖、统一依赖图 ``WP:{底稿}:{表}:{末段}`` 键）里的节点
用「底稿编码 + 表显示名 + 末段」描述。本模块把它们换成平台规范身份，只调用 ``exact_identity``，
不用正则从显示名里猜 sheet_code。

``canonical_node`` 的结果里 ``addr_id`` 与 ``unresolved_reason`` 恰有其一；``addr_id`` 有值时另带目录的统一显示名
``display_label``（T29，与 ``/api/acnr/resolve``、acnr_targets 同一字段）：

| 情形 | addr_id | identity_key | unresolved_code |
|---|---|---|---|
| 末段是 A1，且为目录登记 cell | ``{sheet_addr_id}/{A1}`` | 同 addr_id | — |
| 末段是 A1，表已识别、格未登记 | — | ``{sheet_addr_id}/{A1}`` | ``cell_not_in_catalog`` |
| 末段是语义标签（审定数等） | — | ``{sheet_addr_id}#{原样标签}`` | ``label_not_a1`` |
| 表在该底稿下多义 / 命中禁止别名 | — | — | ``ambiguous_sheet_name`` / ``alias_forbidden`` |
| 表不在目录 | — | — | ``sheet_not_in_catalog`` |
| 底稿不在目录 | — | — | ``wp_not_in_catalog`` |
| 不是 ``WP:{底稿}:{表}:{末段}`` 形态（含 ``WP:{码}::docx:…`` 自定义占位） | — | 自定义占位为 ``custom:{wp}:{suffix}`` | ``not_wellformed`` |

``identity_key`` 是 stale 引擎的内部身份（不对外宣称为 addr_id）：同一物理格、或同一张表的同一标签的
多种写法（表名 / 别名 / 编码）落到同一个键。stale 图的键与写入口都经本模块算身份（需求 9.3）。

V2 读端点另有非底稿节点（附注 / 报表目标），用 ``non_workpaper_node`` 给出 ``not_workpaper_node`` 原因。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import exact_identity, reasons
from .catalog_contract import A1_PATTERN

if TYPE_CHECKING:  # pragma: no cover
    from .catalog import CatalogIndex

_A1_RE = re.compile(A1_PATTERN)

#: sheet_of 非 ok 状态 → 节点 unresolved_code
_SHEET_STATE_CODE = {
    "ambiguous": "ambiguous_sheet_name",
    "alias_forbidden": "alias_forbidden",
    "not_found": "sheet_not_in_catalog",
    "wp_not_in_catalog": "wp_not_in_catalog",
}

#: 响应里追加的字段（只增，旧字段不变）；display_label 只在 addr_id 为目录登记格时有值，取目录字段（T29）
RESPONSE_FIELDS = ("addr_id", "sheet_addr_id", "unresolved_code", "unresolved_reason", "display_label")


@dataclass(frozen=True)
class CanonicalNode:
    addr_id: str | None = None
    sheet_addr_id: str | None = None
    identity_key: str | None = None
    unresolved_code: str | None = None
    unresolved_reason: str | None = None
    display_label: str | None = None

    def response_fields(self) -> dict:
        """V2 响应里追加的字段。"""
        return {name: getattr(self, name) for name in RESPONSE_FIELDS}


def _catalog_display_label(addr_id: str, index: "CatalogIndex | None") -> str | None:
    """目录登记格的统一显示名（与 `/api/acnr/resolve`、acnr_targets 同一字段）。"""
    if index is None:
        from .catalog import get_catalog

        index = get_catalog()
    return (index.cells_by_addr_id.get(addr_id) or {}).get("display_label")


def _unresolved(code: str, *, sheet_addr_id: str | None = None, identity_key: str | None = None,
                detail: str = "") -> CanonicalNode:
    reason = reasons.NODE_UNRESOLVED_REASONS[code]
    if detail:
        reason = f"{reason}：{detail}"
    return CanonicalNode(sheet_addr_id=sheet_addr_id, identity_key=identity_key,
                         unresolved_code=code, unresolved_reason=reason)


def canonical_node(wp_code: str | None, sheet: str | None, last: str | None, *,
                   index: "CatalogIndex | None" = None) -> CanonicalNode:
    """底稿编码 + 表文字 + 末段（A1 或语义标签）→ 规范身份。表文字逐字交 ``exact_identity.sheet_of``。"""
    wp_code = (wp_code or "").strip()
    sheet = sheet or ""
    last = last or ""
    if not wp_code or not sheet or not last:
        return _unresolved("not_wellformed")
    sm = exact_identity.sheet_of(wp_code, sheet, index=index)
    if not sm.ok or sm.entry is None:
        return _unresolved(_SHEET_STATE_CODE.get(sm.state, "sheet_not_in_catalog"), detail=sm.reason)
    sheet_addr_id = sm.entry["addr_id"]
    if _A1_RE.match(last):
        cm = exact_identity.cell_of(wp_code, sheet, last, index=index)
        if cm.ok and cm.addr_id:
            if cm.in_catalog:
                return CanonicalNode(addr_id=cm.addr_id, sheet_addr_id=sheet_addr_id, identity_key=cm.addr_id,
                                     display_label=_catalog_display_label(cm.addr_id, index))
            return _unresolved("cell_not_in_catalog", sheet_addr_id=sheet_addr_id, identity_key=cm.addr_id)
    return _unresolved("label_not_a1", sheet_addr_id=sheet_addr_id, identity_key=f"{sheet_addr_id}#{last}")


def canonical_uri(uri: str, *, index: "CatalogIndex | None" = None) -> CanonicalNode:
    """``WP:{底稿}:{表}:{末段}`` 写法 → 规范身份。末段可含冒号（只按前三个冒号切分）。"""
    if not uri.startswith("WP:"):
        return _unresolved("not_wellformed")
    parts = uri.split(":", 3)
    if len(parts) == 4 and parts[1] and parts[2] and parts[3]:
        return canonical_node(parts[1], parts[2], parts[3], index=index)
    if len(parts) == 4 and parts[1] and not parts[2] and parts[3]:
        # 自定义占位 WP:{码}::{suffix}（docx 段落、total 等）：只并入同写法，不给地址
        return _unresolved("not_wellformed", identity_key=f"custom:{parts[1]}:{parts[3]}")
    return _unresolved("not_wellformed")


def canonical_addr(addr: str, *, index: "CatalogIndex | None" = None) -> CanonicalNode:
    """addr_id 形态 ``{wp_code}/{sheet_code}/{末段}`` 的输入 → 规范身份（第二段按 sheet_code 精确判定）。"""
    parts = addr.split("/", 2)
    if len(parts) != 3 or not all(parts):
        return _unresolved("not_wellformed")
    wp_code, sheet_code, last = parts
    if wp_code == sheet_code and not _A1_RE.match(last):
        # custom_flat 形态 {wp}/{wp}/{suffix} 与自定义占位同一身份
        custom = canonical_uri(f"WP:{wp_code}::{last}", index=index)
        if custom.identity_key:
            return custom
    return canonical_node(wp_code, sheet_code, last, index=index)


def non_workpaper_node(module: str | None) -> CanonicalNode:
    """附注 / 报表等非底稿节点：不分配底稿地址，给出原因。"""
    return _unresolved("not_workpaper_node", detail=str(module or "未知模块"))


def annotate(node: dict, wp_code: str | None, sheet: str | None, last: str | None, *,
             index: "CatalogIndex | None" = None) -> dict:
    """在 V2 响应节点 dict 上追加规范字段（不改旧字段），返回同一个 dict。"""
    node.update(canonical_node(wp_code, sheet, last, index=index).response_fields())
    return node


__all__ = [
    "CanonicalNode",
    "RESPONSE_FIELDS",
    "canonical_node",
    "canonical_uri",
    "canonical_addr",
    "non_workpaper_node",
    "annotate",
]
