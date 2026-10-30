"""Loader: sheet_verdicts.json → 孤儿/历史移除判定（生成器权威输入）。

承接 acnr-foundation-defect-closure T05 / design §3.2：
- `sheet_verdicts`：三种结论 `add_platform_sheet` / `fix_parent` / `deprecate`。
  * add_platform_sheet：补登 5 张父 sheet（I6-7/J2-5/J3-4/J3-5/M6-5），仅为导航，
    让 R2-F1 停用的孤儿 cell 有可解析 replaced_by 父级。
  * deprecate：K14~K18 停用并指向同科目替代审定表（H10-1/K10-1/G11-1/G13-1/K7-1）。
- `cell_verdicts`：孤儿 cell（kind=orphan，R2-F1，25 格）判 deprecate，replaced_by 指父 sheet；
  T06 追加 §6.4 种子名不一致的 47 格（kind=seed_name_mismatch）：超出模板已用范围 14 格 deprecate，
  范围内 33 格 keep_semantic_unverified（不带 replaced_by）。
  spec wp-deeplink-locate-coverage-closure 追加 kind=seed_coordinate_mismatch：其余旧种子坐标逐格对模板复核后停用，
  replaced_by 指模板核对后的新坐标（`t_address_registry_seed.json`）或父 sheet。

本模块只做加载 + 结构校验（纯函数、只读、仅标准库），不改目录。生成器（T07）据此
在 classification 骨架之后补 sheet、从种子 loader 输入清除孤儿 cell、产出 deprecated 条目。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# sheet verdict 三种结论（design §3.2 / 需求 2.1）
SHEET_VERDICTS = frozenset({"add_platform_sheet", "fix_parent", "deprecate"})
# cell verdict：deprecate（R2-F1 孤儿 25 格 + §6.4 超范围 14 格）与 keep_semantic_unverified
# （§6.4 范围内 33 格：地址保留，semantic_label=null、cell_label「{A1}（语义待核对）」）
CELL_VERDICTS = frozenset({"deprecate", "keep_semantic_unverified"})
# cell 记录的来源分类：orphan（父 sheet 不在 classification 骨架）/ seed_name_mismatch（§6.4）/
# seed_coordinate_mismatch（spec wp-deeplink-locate-coverage-closure：逐格对模板复核，种子坐标与模板不符，
# 由 backend/scripts/acnr/review_cell_coordinates.py 生成）
CELL_KINDS = frozenset({"orphan", "seed_name_mismatch", "seed_coordinate_mismatch"})

_DEFAULT_PATH = (
    Path(__file__).resolve().parents[4]  # backend/  (loaders → acnr → services → app → backend)
    / "data" / "acnr" / "sources" / "sheet_verdicts.json"
)


class SheetVerdictError(ValueError):
    """sheet_verdicts.json 结构/取值非法。"""


@dataclass
class SheetVerdict:
    sheet_code: str
    parent_wp_code: str
    addr_id: str
    verdict: str
    sheet_name: str
    replaced_by: str | None
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class CellVerdict:
    addr_id: str
    parent_sheet_code: str
    verdict: str
    replaced_by: str | None
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    kind: str = "orphan"


@dataclass
class SheetVerdicts:
    """加载后的结构化判定集合。"""

    sheet_verdicts: list[SheetVerdict]
    cell_verdicts: list[CellVerdict]
    owner: str = ""
    decided_on: str = ""

    def add_platform_sheets(self) -> list[SheetVerdict]:
        return [v for v in self.sheet_verdicts if v.verdict == "add_platform_sheet"]

    def deprecated_sheets(self) -> list[SheetVerdict]:
        return [v for v in self.sheet_verdicts if v.verdict == "deprecate"]

    def deprecated_cell_addr_ids(self) -> set[str]:
        return {c.addr_id for c in self.cell_verdicts if c.verdict == "deprecate"}

    def cells_of_kind(self, kind: str) -> list[CellVerdict]:
        return [c for c in self.cell_verdicts if c.kind == kind]


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise SheetVerdictError(msg)


def load_sheet_verdicts(path: str | Path | None = None) -> SheetVerdicts:
    """加载并校验 sheet_verdicts.json。

    校验：两段存在；sheet verdict ∈ SHEET_VERDICTS、cell verdict ∈ CELL_VERDICTS；
    必填字段齐全；deprecate 的 sheet / cell 必须有 replaced_by；addr_id 唯一。
    """
    p = Path(path) if path is not None else _DEFAULT_PATH
    _require(p.exists(), f"缺少 sheet_verdicts.json：{p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    _require(isinstance(data, dict), "sheet_verdicts.json 顶层必须是对象")
    _require("sheet_verdicts" in data, "缺少 sheet_verdicts 段")
    _require("cell_verdicts" in data, "缺少 cell_verdicts 段")

    sheet_rows = data["sheet_verdicts"]
    cell_rows = data["cell_verdicts"]
    _require(isinstance(sheet_rows, list), "sheet_verdicts 必须是数组")
    _require(isinstance(cell_rows, list), "cell_verdicts 必须是数组")

    sheets: list[SheetVerdict] = []
    seen_sheet_addr: set[str] = set()
    for i, row in enumerate(sheet_rows):
        _require(isinstance(row, dict), f"sheet_verdicts[{i}] 必须是对象")
        verdict = row.get("verdict", "")
        _require(verdict in SHEET_VERDICTS, f"sheet_verdicts[{i}] verdict 非法：{verdict!r}")
        addr_id = row.get("addr_id", "")
        _require(bool(addr_id), f"sheet_verdicts[{i}] 缺 addr_id")
        _require(addr_id not in seen_sheet_addr, f"sheet_verdicts addr_id 重复：{addr_id}")
        seen_sheet_addr.add(addr_id)
        replaced_by = row.get("replaced_by")
        if verdict == "deprecate":
            _require(bool(replaced_by), f"sheet_verdicts[{i}] deprecate 必须有 replaced_by")
        for fld in ("sheet_code", "parent_wp_code", "sheet_name", "reason"):
            _require(fld in row, f"sheet_verdicts[{i}] 缺字段 {fld}")
        sheets.append(
            SheetVerdict(
                sheet_code=row["sheet_code"],
                parent_wp_code=row["parent_wp_code"],
                addr_id=addr_id,
                verdict=verdict,
                sheet_name=row["sheet_name"],
                replaced_by=replaced_by,
                reason=row["reason"],
                evidence=row.get("evidence", {}) or {},
            )
        )

    cells: list[CellVerdict] = []
    seen_cell_addr: set[str] = set()
    for i, row in enumerate(cell_rows):
        _require(isinstance(row, dict), f"cell_verdicts[{i}] 必须是对象")
        verdict = row.get("verdict", "")
        _require(verdict in CELL_VERDICTS, f"cell_verdicts[{i}] verdict 非法：{verdict!r}")
        addr_id = row.get("addr_id", "")
        _require(bool(addr_id), f"cell_verdicts[{i}] 缺 addr_id")
        _require(addr_id not in seen_cell_addr, f"cell_verdicts addr_id 重复：{addr_id}")
        seen_cell_addr.add(addr_id)
        replaced_by = row.get("replaced_by") or None
        if verdict == "deprecate":
            _require(bool(replaced_by), f"cell_verdicts[{i}] deprecate 必须有 replaced_by")
        else:
            _require(replaced_by is None, f"cell_verdicts[{i}] {verdict} 不得带 replaced_by")
        kind = row.get("kind", "")
        _require(kind in CELL_KINDS, f"cell_verdicts[{i}] kind 非法：{kind!r}")
        for fld in ("parent_sheet_code", "reason"):
            _require(fld in row, f"cell_verdicts[{i}] 缺字段 {fld}")
        cells.append(
            CellVerdict(
                addr_id=addr_id,
                parent_sheet_code=row["parent_sheet_code"],
                verdict=verdict,
                replaced_by=replaced_by,
                reason=row["reason"],
                evidence=row.get("evidence", {}) or {},
                kind=kind,
            )
        )

    return SheetVerdicts(
        sheet_verdicts=sheets,
        cell_verdicts=cells,
        owner=data.get("owner", ""),
        decided_on=data.get("decided_on", ""),
    )
