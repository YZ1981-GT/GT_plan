"""ACNR 统一显示名（acnr-foundation-defect-closure T29，需求 12.1 / D10，design §13.2）——纯函数，只依赖标准库。

规则以前端 `sheetDisplayName.ts::composeSheetLabelsForGroup`（T29 时的口径）为基线移植，T30 拍板修订第 4 条（规则 B）：

1. 同一父级（`parent_wp_code`）一组，按编码自然排序（`wp_code_compare`，与前端 `wpCodeNaturalCompare` 同序）；
2. 名称 = 平台底稿名（`wp_account_mapping.json` 的 `wp_name`）→ 兜底 `sheet_display_names.json`（手工维护）→
   去尾编码的模板名（`clean_sheet_label_name`）；名称等于编码（纯编码占位）则置空、只显示编码；
3. 科目简称（父级的 `account_name`，缺则组内首个有简称的 sheet）不在名称里时加「简称·」前缀；
4. 同组内仍重名的按编码序追加（1）（2）；编码等于所属底稿编码的那张 sheet 不参与序号（标签以编码开头已能区分），
   同组其余重名的 sheet 仍不少于 2 张时照常从（1）编号（T30 拍板，design §13.2）；
5. 标签 = `{sheet_code} {名称}`，名称为空时只有 `{sheet_code}`。

只多一条：停用条目加「（已停用）」。分组与序号只数未停用的 sheet（前端树从 `/api/acnr/entries` 建树，
该端点默认不列停用条目），停用 sheet 不参与序号、不改变未停用 sheet 的显示名。

cell：`cell_label` =「{A1} {语义标签}」（无语义时「{A1}」；判定记录已写的「（语义待核对）」「（坐标待核对）」照用），
`display_label` =「{所属 sheet 的 display_label} › {cell_label}」。L3 运行时条目与非底稿域委托结果由 resolver 用
`cell_labels` 现算（不在目录里）。
"""
from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

#: 停用条目显示名后缀
DEPRECATED_SUFFIX = "（已停用）"
#: sheet 显示名与 cell 标签之间的分隔
CELL_SEPARATOR = " › "

_CODE_PARSE_RE = re.compile(r"^([A-Za-z]+)([0-9]+)?(?:-([0-9]+))?(.*)\Z", re.S)
_TRAIL_CODE_RE = re.compile(r"\s*[A-Za-z]+[0-9]+(?:-[0-9]+)?[A-Za-z]?\Z")
_MAX_SAFE_INTEGER = 2 ** 53 - 1


@dataclass(frozen=True)
class NameSources:
    """显示名的两个名称来源（生成器输入，进 inputs_fingerprint）。"""

    #: wp_code → {"account_name": 科目简称（缺则 wp_name）, "wp_name": 平台底稿名}；同码多条时后者覆盖（与 list_sheets 同）
    mapping: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    #: sheet_code → 名称（手工维护的 `sheet_display_names.json`）
    sheet_names: Mapping[str, str] = field(default_factory=dict)

    def account_name(self, parent_wp_code: str, sheet_code: str) -> str:
        """与 `catalog.list_sheets` 注入的 `account_name` 同口径：父级优先，其次本 sheet。"""
        return ((self.mapping.get(parent_wp_code) or {}).get("account_name")
                or (self.mapping.get(sheet_code) or {}).get("account_name") or "")

    def mapped_sheet_name(self, sheet_code: str) -> str:
        """与 `catalog.list_sheets` 注入的 `mapped_sheet_name` 同口径：平台底稿名优先，兜底手工名。"""
        return (self.mapping.get(sheet_code) or {}).get("wp_name") or self.sheet_names.get(sheet_code) or ""


def load_name_sources(backend_root: Path) -> NameSources:
    """读 `data/wp_account_mapping.json` 与 `data/acnr/sheet_display_names.json`（缺文件按空处理）。"""
    mapping: dict[str, dict[str, str]] = {}
    mp = backend_root / "data" / "wp_account_mapping.json"
    if mp.exists():
        data = json.loads(mp.read_text(encoding="utf-8-sig"))
        for m in (data.get("mappings") or []) if isinstance(data, dict) else []:
            code = m.get("wp_code")
            if code:
                mapping[code] = {"account_name": m.get("account_name") or m.get("wp_name") or "",
                                 "wp_name": m.get("wp_name") or ""}
    names: dict[str, str] = {}
    sp = backend_root / "data" / "acnr" / "sheet_display_names.json"
    if sp.exists():
        raw = json.loads(sp.read_text(encoding="utf-8"))
        names = {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
    return NameSources(mapping=mapping, sheet_names=names)


def _locale_cmp(a: str, b: str) -> int:
    """近似 JS `localeCompare`（ICU 根序）在编码片段上的行为：先不分大小写比，再小写在前。"""
    ka, kb = a.casefold(), b.casefold()
    if ka != kb:
        return -1 if ka < kb else 1
    sa, sb = a.swapcase(), b.swapcase()
    return (sa > sb) - (sa < sb)


def _parse_code(code: str) -> tuple[str, int, int, str]:
    m = _CODE_PARSE_RE.match((code or "").strip())
    if not m:
        return (code or "", _MAX_SAFE_INTEGER, -1, "")
    return (m.group(1) or "", int(m.group(2)) if m.group(2) else -1,
            int(m.group(3)) if m.group(3) else -1, m.group(4) or "")


def wp_code_compare(a: str, b: str) -> int:
    """底稿编码自然排序（字母段 / 数字段 / -数字段 / 其余），与前端 `wpCodeNaturalCompare` 同序。"""
    pa, pb = _parse_code(a), _parse_code(b)
    if pa[0] != pb[0]:
        return _locale_cmp(pa[0], pb[0])
    if pa[1] != pb[1]:
        return pa[1] - pb[1]
    if pa[2] != pb[2]:
        return pa[2] - pb[2]
    return _locale_cmp(pa[3], pb[3])


def clean_sheet_label_name(name: str) -> str:
    """去掉名称末尾冗余的底稿编码（「审定表D1-1」→「审定表」）；去完为空则保留原名。"""
    if not name:
        return ""
    cleaned = _TRAIL_CODE_RE.sub("", name, count=1).strip()
    return cleaned or name


def _base_name(sheet: Mapping[str, Any], sources: NameSources, subject: str) -> str:
    code = sheet.get("sheet_code") or ""
    name = sources.mapped_sheet_name(code).strip() or clean_sheet_label_name(sheet.get("sheet_name") or "")
    if name == code:
        name = ""
    if subject and name and subject not in name:
        name = f"{subject}·{name}"
    return name


def _numbered(sheet: Mapping[str, Any]) -> bool:
    """是否参与同名序号：编码等于所属底稿编码的那张 sheet 不参与（标签以编码开头已能区分，T30 拍板规则 B）。"""
    return (sheet.get("sheet_code") or "") != (sheet.get("parent_wp_code") or "")


def compose_sheet_labels(group: list[Mapping[str, Any]], sources: NameSources) -> dict[str, str]:
    """一个父级内全部 sheet 的显示名：返回 {addr_id: display_label}（规则见模块文档）。

    `group` 按目录顺序给出（科目简称取「组内首个有简称」与前端同序）；停用条目不参与序号并加「（已停用）」。"""
    active = [s for s in group if not s.get("deprecated")]
    subject = next((a for a in (sources.account_name(s.get("parent_wp_code") or "", s.get("sheet_code") or "")
                                for s in (active or group)) if a), "")
    ordered = sorted(active, key=functools.cmp_to_key(lambda x, y: wp_code_compare(x.get("sheet_code") or "",
                                                                                   y.get("sheet_code") or "")))
    named = [(s, _base_name(s, sources, subject), _numbered(s)) for s in ordered]
    counts: dict[str, int] = {}
    for _s, name, numbered in named:
        if name and numbered:
            counts[name] = counts.get(name, 0) + 1
    seen: dict[str, int] = {}
    out: dict[str, str] = {}
    for s, name, numbered in named:
        if name and numbered and counts[name] > 1:
            seen[name] = seen.get(name, 0) + 1
            name = f"{name}（{seen[name]}）"
        code = s.get("sheet_code") or ""
        out[s["addr_id"]] = f"{code} {name}" if name else code
    for s in group:
        if s.get("deprecated"):
            code = s.get("sheet_code") or ""
            name = _base_name(s, sources, subject)
            out[s["addr_id"]] = (f"{code} {name}" if name else code) + DEPRECATED_SUFFIX
    return out


def cell_labels(sheet_label: str, cell: Mapping[str, Any]) -> tuple[str, str]:
    """返回 (cell_label, display_label)。判定记录已写入的 cell_label（语义待核对 / 坐标待核对）照用。

    两段都有才加分隔符：目录里的 cell 一定有 A1 坐标（发布门禁卡着），所以 label 不会空；
    但非底稿域委托 V1 时「列」可能为空（如 ``note://五、3``），此时只显示源，不要留一个
    后面空无一物的「五、3 › 」（T31 现算发现）。
    """
    label = cell.get("cell_label")
    if not label:
        a1 = cell.get("cell_address") or ""
        semantic = (cell.get("semantic_label") or "").strip()
        label = " ".join(x for x in (a1, semantic) if x) or str(cell.get("addr_id") or "")
    if not sheet_label:
        return label, label
    if not label:
        return label, sheet_label
    return label, f"{sheet_label}{CELL_SEPARATOR}{label}"


def group_by_parent(sheets: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for s in sheets:
        groups.setdefault(s.get("parent_wp_code") or "", []).append(s)
    return groups


def apply_display_labels(catalog: dict[str, Any], sources: NameSources) -> None:
    """生成器用：按目录顺序分组，写每个 sheet 的 display_label、每个 cell 的 cell_label 与 display_label。"""
    labels: dict[str, str] = {}
    for group in group_by_parent(catalog.get("sheets", [])).values():
        labels.update(compose_sheet_labels(group, sources))
    for s in catalog.get("sheets", []):
        s["display_label"] = labels[s["addr_id"]]
    for c in catalog.get("cells", []):
        head = labels.get(c.get("parent_addr_id") or "") or str(c.get("parent_addr_id") or "")
        c["cell_label"], c["display_label"] = cell_labels(head, c)


__all__ = [
    "CELL_SEPARATOR", "DEPRECATED_SUFFIX", "NameSources", "apply_display_labels", "cell_labels",
    "clean_sheet_label_name", "compose_sheet_labels", "group_by_parent", "load_name_sources", "wp_code_compare",
]
