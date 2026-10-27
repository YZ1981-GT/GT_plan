"""ACNR 唯一精确身份判定（design §6.2）。

纯函数模块：输入一个 `CatalogIndex`（缺省 `get_catalog()`，门禁/测试可传任意索引），
提供 sheet / cell / 名称归属的唯一判定。文本逐字比较，不做空白或全半角归一。

目标（design §6.2）：全平台「名称/编码 → sheet 身份」只留这一处实现。
现状：生产代码里调用它的是目录写法解析 `catalog._formula_ref_to_sheet_match` / `_uri_to_sheet_match`
（`full_resolve` 首步经 `resolve_identity.step1_identity` 调它，T10）、发布门禁 `catalog_release` 与生成器名称规则
`catalog_names`（T06），以及单元格取值接线 `acnr.wp_cell_target`（T12；它的生产调用方是底稿公式三参 WP 的
A1 第三参 `WPExecutor.read_sheet_cell`（T13），高级查询接线随 T14）。
计划接入：V2 规范化与 stale 引擎（T21）、`check_ccr_resolve`（T22）。

只依赖标准库与本包的 `catalog` / `reasons` / `catalog_contract`（CI 无需新增依赖）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import reasons
from .catalog_contract import A1_PATTERN

if TYPE_CHECKING:  # 避免运行期强依赖（纯函数可独立测试）
    from .catalog import CatalogIndex

# A1 地址：1~3 个大写字母 + 1~7 位数字（口径唯一来源 catalog_contract.A1_PATTERN）
_A1_RE = re.compile(A1_PATTERN)
# 编码词元边界字符
_TOKEN_CH = re.compile(r"[A-Za-z0-9-]")


# ─── 结果对象 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SheetMatch:
    """sheet_of 的结果。state ∈ ok / ambiguous / alias_forbidden / not_found / wp_not_in_catalog。"""

    state: str
    entry: dict | None = None
    match_kind: str = ""  # sheet_code / sheet_name / alias / code_token
    reason: str = ""
    candidates: list[str] = field(default_factory=list)
    required_context: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.state == "ok"


@dataclass(frozen=True)
class CellMatch:
    """cell_of 的结果。state ∈ ok / bad_a1 / <sheet_of 的非 ok 状态>。"""

    state: str
    addr_id: str | None = None
    in_catalog: bool = False
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.state == "ok"


# ─── 内部：从 CatalogIndex 取三类索引（兼容 T08 之前/之后） ──────────────────


def _resolve_index(index: "CatalogIndex | None") -> "CatalogIndex":
    if index is not None:
        return index
    from .catalog import get_catalog

    return get_catalog()


def _sheets_by_parent(index: "CatalogIndex") -> dict[str, list[dict]]:
    """父级 wp_code → 该父级下的 sheet 条目列表。

    优先用 index 预建的 `sheets_by_parent`（T08 加），否则现场构建（只读）。
    """
    pre = getattr(index, "sheets_by_parent", None)
    if isinstance(pre, dict):
        return pre
    by_parent: dict[str, list[dict]] = {}
    for s in index.sheets_by_addr_id.values():
        by_parent.setdefault(s.get("parent_wp_code", ""), []).append(s)
    return by_parent


def _forbidden_aliases(index: "CatalogIndex") -> dict[tuple[str, str], list[str]]:
    """(parent_wp_code, alias) → 冲突 sheet_code 列表（禁止别名）。

    优先用 index 预建的 `forbidden_aliases`（T08/T06 加），否则现场由
    「同父级内一名多码」推导（只读）。
    """
    pre = getattr(index, "forbidden_aliases", None)
    if isinstance(pre, dict):
        return pre
    # 现场推导：同一父级下，某平台索引名/别名对应 >= 2 个 sheet。
    # 当前目录 sheet 无 aliases 字段时该集合为空（禁止别名由 T06 的 loader 产出）。
    buckets: dict[tuple[str, str], list[str]] = {}
    for s in index.sheets_by_addr_id.values():
        parent = s.get("parent_wp_code", "")
        code = s.get("sheet_code", "")
        for alias in s.get("sheet_name_aliases", []) or []:
            buckets.setdefault((parent, alias), []).append(code)
    return {k: sorted(v) for k, v in buckets.items() if len(v) >= 2}


# ─── 编码词元裁决 ─────────────────────────────────────────────────────────


def _code_token_in(code: str, text: str) -> bool:
    """code 以完整词元出现在 text 中（左右相邻字符都不是 [A-Za-z0-9-]）。"""
    if not code:
        return False
    start = 0
    while True:
        idx = text.find(code, start)
        if idx < 0:
            return False
        left_ok = idx == 0 or not _TOKEN_CH.match(text[idx - 1])
        right = idx + len(code)
        right_ok = right >= len(text) or not _TOKEN_CH.match(text[right])
        if left_ok and right_ok:
            return True
        start = idx + 1


# ─── sheet_of ─────────────────────────────────────────────────────────────


def sheet_of(wp_code: str, text: str, *, index: "CatalogIndex | None" = None) -> SheetMatch:
    """按 design §6.2 的 6 步规则精确判定 sheet 身份。

    参数：
      wp_code —— WP() 第一参（父级或 sheet 编码）
      text    —— sheet 名 / 编码 / 别名（逐字比较，不归一）
    """
    idx = _resolve_index(index)
    by_parent = _sheets_by_parent(idx)

    # 第 1 步：确定父级 P
    parent: str | None = None
    if wp_code in by_parent:
        parent = wp_code
    else:
        # wp_code 可能是某 sheet 的 sheet_code → 取其父级
        code_hits = idx.sheets_by_code.get(wp_code, [])
        if len(code_hits) == 1:
            if not text:
                # text 为空 → 直接取该 sheet
                return SheetMatch(state="ok", entry=code_hits[0], match_kind="sheet_code")
            parent = code_hits[0].get("parent_wp_code", "")
        elif len(code_hits) >= 2:
            # 同编码多条（理论上目录内唯一，保险处理）
            return SheetMatch(
                state="ambiguous",
                reason=reasons.sheet_reason(
                    "ambiguous", wp_code=wp_code, text=text,
                    candidates=[h.get("sheet_code", "") for h in code_hits],
                ),
                candidates=[h.get("addr_id", "") for h in code_hits],
                required_context=["sheet_code"],
            )
    if parent is None or parent not in by_parent:
        return SheetMatch(
            state="wp_not_in_catalog",
            reason=reasons.sheet_reason("wp_not_in_catalog", wp_code=wp_code, text=text),
        )

    pool = by_parent[parent]

    # 第 2 步：text 等于 P 内某 sheet 的 sheet_code
    code_exact = [s for s in pool if s.get("sheet_code") == text]
    if len(code_exact) == 1:
        return SheetMatch(state="ok", entry=code_exact[0], match_kind="sheet_code")

    # 第 3 步：text 属于 P 的禁止集合
    forbidden = _forbidden_aliases(idx)
    if (parent, text) in forbidden:
        codes = forbidden[(parent, text)]
        return SheetMatch(
            state="alias_forbidden",
            reason=reasons.sheet_reason("alias_forbidden", wp_code=wp_code, text=text, codes=codes),
            candidates=[f"{parent}/{c}" for c in codes],
            required_context=["sheet_code"],
        )

    # 第 4 步：P 内恰一个 sheet 的 sheet_name == text
    name_hits = [s for s in pool if s.get("sheet_name") == text]
    if len(name_hits) == 1:
        return SheetMatch(state="ok", entry=name_hits[0], match_kind="sheet_name")

    # 第 5 步：无 sheet_name 命中、P 内恰一个 sheet 的别名 == text
    alias_hits: list[dict] = []
    if not name_hits:
        for s in pool:
            if text in (s.get("sheet_name_aliases") or []):
                alias_hits.append(s)
        if len(alias_hits) == 1:
            return SheetMatch(state="ok", entry=alias_hits[0], match_kind="alias")

    # 第 6 步：编码词元裁决
    multi_hits = name_hits if len(name_hits) >= 2 else alias_hits
    pool_for_token = multi_hits if len(multi_hits) >= 2 else pool
    best: dict | None = None
    best_len = -1
    tie = False
    for s in pool_for_token:
        code = s.get("sheet_code", "")
        if _code_token_in(code, text):
            if len(code) > best_len:
                best, best_len, tie = s, len(code), False
            elif len(code) == best_len:
                tie = True
    if best is not None and not tie:
        return SheetMatch(state="ok", entry=best, match_kind="code_token")

    # 第 7 步：第 4/5 步命中 >= 2 而第 6 步无结果 → ambiguous；否则 not_found
    if len(multi_hits) >= 2:
        return SheetMatch(
            state="ambiguous",
            reason=reasons.sheet_reason(
                "ambiguous", wp_code=wp_code, text=text,
                candidates=[s.get("sheet_code", "") for s in multi_hits],
            ),
            candidates=[s.get("addr_id", "") for s in multi_hits[:5]],
            required_context=["sheet_code"],
        )
    return SheetMatch(
        state="not_found",
        reason=reasons.sheet_reason("not_found", wp_code=wp_code, text=text),
    )


# ─── cell_of ──────────────────────────────────────────────────────────────


def cell_of(wp_code: str, sheet_text: str, a1: str,
            *, index: "CatalogIndex | None" = None) -> CellMatch:
    """精确定位单元格：sheet 用 sheet_of、A1 须匹配 ^[A-Z]{1,3}[0-9]{1,7}$。"""
    idx = _resolve_index(index)
    a1_norm = (a1 or "").upper()
    if not _A1_RE.match(a1_norm):
        return CellMatch(state="bad_a1", reason=reasons.CELL_REASONS["bad_a1"].format(a1=a1))
    sm = sheet_of(wp_code, sheet_text, index=idx)
    if not sm.ok or sm.entry is None:
        return CellMatch(state=sm.state, reason=sm.reason)
    addr_id = f"{sm.entry['addr_id']}/{a1_norm}"
    in_catalog = addr_id in idx.cells_by_addr_id
    return CellMatch(state="ok", addr_id=addr_id, in_catalog=in_catalog)


# ─── name_owner ───────────────────────────────────────────────────────────


def name_owner(parent: str, name: str, *, index: "CatalogIndex | None" = None) -> dict | None:
    """该名在父级内按第 4~7 步裁出的唯一 sheet；无唯一归属返回 None。

    生成器 cell formula_ref / uri 的归属选择用它（`catalog_names.apply_cell_names`，T06）。
    `wp_cell_target.sheet_key_for` 不用它而直接用 `sheet_of`：本函数不认编码命中，名称恰等于自身编码的
    sheet（如 S17/S17）会被当成无归属。
    """
    sm = sheet_of(parent, name, index=index)
    if sm.ok and sm.match_kind in ("sheet_name", "alias", "code_token"):
        return sm.entry
    return None


# ─── 不变量：父级禁止集合与 sheet_name / sheet_code 不相交 ────────────────────


def forbidden_disjoint_violations(index: "CatalogIndex | None" = None) -> list[str]:
    """门禁 alias 检查用：返回「禁止别名同时又是本父级内某 sheet 的 sheet_name/sheet_code」的冲突描述。"""
    idx = _resolve_index(index)
    by_parent = _sheets_by_parent(idx)
    forbidden = _forbidden_aliases(idx)
    violations: list[str] = []
    for (parent, alias), codes in forbidden.items():
        pool = by_parent.get(parent, [])
        names = {s.get("sheet_name") for s in pool}
        scodes = {s.get("sheet_code") for s in pool}
        if alias in names or alias in scodes:
            violations.append(f"{parent}:{alias} 既是禁止别名又是 sheet_name/sheet_code")
    return violations


__all__ = [
    "SheetMatch",
    "CellMatch",
    "sheet_of",
    "cell_of",
    "name_owner",
    "forbidden_disjoint_violations",
]
