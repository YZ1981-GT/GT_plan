"""ACNR 生成器名称规则（design §6.3 / §6.4，T06）。

在合并完全部 sheet（含 sheet_verdicts 补登 / 停用条目）之后统一处理名称，纯函数、只改传入的目录 dict：

1. 平台底稿索引名（`wp_account_mapping.wp_name`）经 `loaders.from_wp_account_mapping` 分类：
   - 可并入的（含只跨父级重名、每父唯一的 6 组）并入 sheet 的 `sheet_name_aliases`；并入后逐条断言
     `exact_identity.sheet_of(父级, 平台名)` 回到本 sheet，不回即 `NameSystemError`（fail-closed）；
   - 同父一名多码（现算 9 组）写进目录顶层 `alias_policy.forbidden`，`exact_identity` 第 3 步据此拒绝。
2. cell 的 `formula_ref` / `uri` 第二参：父 sheet 的模板名（`sheet_name`）在父级内归属本 sheet
   （`exact_identity.name_owner` 是它）时用模板名，否则用 `sheet_code`。种子名不作别名、不进写法。
3. `cell_verdicts` 判 keep_semantic_unverified 的格保留地址、`semantic_label=null`、
   `cell_label="{A1}（语义待核对）"`（§6.4 的 33 格原用此判定，wp-deeplink-locate-residual-closure 起改由坐标复核判定，
   现 0 格）；判 deprecate 的格标 `deprecated` + `replaced_by`，`cell_label="{A1}（坐标待核对）"`。
4. 标签源别名的冲突与未登记键按 `sources/alias_policy.json` 处置（`apply_alias_policy`，design §7.2 / §7.3，T09）。

只依赖标准库与本包（catalog / exact_identity / loaders.from_wp_account_mapping）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import exact_identity
from .catalog import CatalogIndex
from .loaders.from_wp_account_mapping import load_wp_account_mapping_aliases

KEEP_SEMANTIC_UNVERIFIED = "keep_semantic_unverified"


class NameSystemError(ValueError):
    """名称规则无法满足（并入别名后不能回到本 sheet 等），生成器据此失败、不写文件。"""


@dataclass
class NameSystemOutcome:
    merged_aliases: dict[str, list[str]] = field(default_factory=dict)
    forbidden: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    parent_qualified: dict[str, dict[str, str]] = field(default_factory=dict)
    by_template_name: int = 0
    by_sheet_code: int = 0


def _index(catalog: dict[str, Any]) -> CatalogIndex:
    return CatalogIndex(catalog)


def merge_platform_names(catalog: dict[str, Any], *, mapping_path: Path | None = None) -> NameSystemOutcome:
    """规则 1：平台索引名并入别名 + 同父一名多码写 alias_policy.forbidden。"""
    sheets = catalog.get("sheets", [])
    res = load_wp_account_mapping_aliases(sheets, mapping_path=mapping_path)
    by_code = {s.get("sheet_code", ""): s for s in sheets}
    out = NameSystemOutcome(parent_qualified=res.parent_qualified)
    for code in sorted(res.aliases):
        entry = by_code[code]
        cur = list(entry.get("sheet_name_aliases") or [])
        added = [n for n in res.aliases[code] if n not in cur]
        if added:
            entry["sheet_name_aliases"] = cur + added
            out.merged_aliases[code] = added
    for (parent, name), codes in sorted(res.forbidden.items()):
        out.forbidden.setdefault(parent, {})[name] = list(codes)
    if out.forbidden:
        policy = dict(catalog.get("alias_policy") or {})
        merged = {p: dict(v) for p, v in (policy.get("forbidden") or {}).items()}
        for parent, by_alias in out.forbidden.items():
            merged.setdefault(parent, {}).update(by_alias)
        policy["forbidden"] = {p: dict(sorted(v.items())) for p, v in sorted(merged.items())}
        catalog["alias_policy"] = policy

    index = _index(catalog)
    bad: list[str] = []
    for code, names in sorted(out.merged_aliases.items()):
        entry = by_code[code]
        for name in names:
            sm = exact_identity.sheet_of(entry.get("parent_wp_code", ""), name, index=index)
            got = (sm.entry or {}).get("addr_id") if sm.ok else sm.state
            if got != entry.get("addr_id"):
                bad.append(f"{entry.get('addr_id')} 平台名「{name}」并入后解析为 {got}")
    if bad:
        raise NameSystemError("平台底稿名并入别名后不能回到本 sheet（design §6.3）：" + "；".join(bad[:10]))
    return out


def apply_alias_policy(catalog: dict[str, Any], entries: list[dict[str, Any]],
                       label_aliases: dict[str, list[str]]) -> dict[str, list[str]]:
    """规则 4（design §7.2 / §7.3）：按 `sources/alias_policy.json` 处置标签源别名，返回 {目标 addr_id: 新并入别名}。

    - merge_into：把标签源里该键（未登记的 sheet_code）的全部别名并入 `target` sheet（条目带 `writings`
      写法证据时别名键本身也并入，T10）；并入后逐条断言
      `sheet_of(父级, 别名)` 回到 target，否则 `NameSystemError`；
    - forbidden：别名在所列 sheet 的父级内写进目录顶层 `alias_policy.forbidden`（第 3 步据此拒绝并给理由）；
    - parent_qualified：别名加回所列 sheet（每个父级内唯一，缺父级时由 exact_identity 判歧义）；
    - non_address_label / project_context：不写目录（只进报告 info）。
    所指 sheet / 目标不在目录的条目不在这里处理，由发布门禁 alias 报失效条目。
    """
    sheets = catalog.get("sheets", [])
    by_code = {s.get("sheet_code", ""): s for s in sheets}
    by_id = {s.get("addr_id", ""): s for s in sheets}
    merged: dict[str, list[str]] = {}
    forbidden: dict[str, dict[str, list[str]]] = {}

    def _add(entry: dict[str, Any], names: list[str]) -> list[str]:
        cur = list(entry.get("sheet_name_aliases") or [])
        added = [n for n in names if n not in cur and n != entry.get("sheet_name")]
        if added:
            entry["sheet_name_aliases"] = cur + added
        return added

    for e in entries:
        disp, alias = e.get("disposition"), e.get("alias", "")
        if disp == "merge_into" and e.get("target") in by_id:
            # 带 writings 的条目：别名键本身也并入（HEAD 能解析的静态写法改用父级限定别名，design §6.5）
            names = list(label_aliases.get(alias, [])) + ([alias] if e.get("writings") else [])
            added = _add(by_id[e["target"]], names)
            if added:
                merged.setdefault(e["target"], []).extend(added)
        elif disp in ("forbidden", "parent_qualified"):
            for code in e.get("sheet_codes", []) or []:
                sheet = by_code.get(code)
                if sheet is None:
                    continue
                if disp == "forbidden":
                    forbidden.setdefault(sheet.get("parent_wp_code", ""), {}).setdefault(alias, []).append(code)
                elif _add(sheet, [alias]):
                    merged.setdefault(sheet["addr_id"], []).append(alias)
    if forbidden:
        policy = dict(catalog.get("alias_policy") or {})
        cur = {p: dict(v) for p, v in (policy.get("forbidden") or {}).items()}
        for parent, by_alias in forbidden.items():
            for name, codes in by_alias.items():
                cur.setdefault(parent, {})[name] = sorted(set(cur.get(parent, {}).get(name, [])) | set(codes))
        policy["forbidden"] = {p: dict(sorted(v.items())) for p, v in sorted(cur.items())}
        catalog["alias_policy"] = policy

    index = _index(catalog)
    bad = []
    for aid, names in sorted(merged.items()):
        for name in names:
            sm = exact_identity.sheet_of(by_id[aid].get("parent_wp_code", ""), name, index=index)
            got = (sm.entry or {}).get("addr_id") if sm.ok else sm.state
            if got != aid:
                bad.append(f"{aid} 别名「{name}」并入后解析为 {got}")
    if bad:
        raise NameSystemError("alias_policy 并入的别名不能回到目标 sheet（design §7.2）：" + "；".join(bad[:10]))
    return merged


def apply_cell_verdicts(catalog: dict[str, Any], cell_verdicts: list[dict[str, Any]]) -> None:
    """规则 3：按 cell_verdicts 停用 / 标语义待核对（只改目录里已有的 cell，不新增、不删除）。"""
    by_id = {c.get("addr_id", ""): c for c in catalog.get("cells", [])}
    for v in cell_verdicts:
        cell = by_id.get(v.get("addr_id", ""))
        if cell is None:
            continue  # 判定所指 cell 不在目录：由发布门禁 verdict 检查报告
        a1 = cell.get("cell_address") or ""
        if v.get("verdict") == "deprecate":
            cell["deprecated"] = True
            cell["replaced_by"] = v.get("replaced_by")
            cell["cell_label"] = f"{a1}（坐标待核对）"
        elif v.get("verdict") == KEEP_SEMANTIC_UNVERIFIED:
            cell["semantic_label"] = None
            cell["cell_label"] = f"{a1}（语义待核对）"


def apply_cell_names(catalog: dict[str, Any]) -> NameSystemOutcome:
    """规则 2：按名称归属重写 cell 的 formula_ref / uri（父 sheet 不在目录的 cell 不动，由门禁 orphan 报）。"""
    index = _index(catalog)
    out = NameSystemOutcome()
    for c in catalog.get("cells", []):
        parent_entry = index.sheets_by_addr_id.get(c.get("parent_addr_id", ""))
        if parent_entry is None:
            continue
        parent = parent_entry.get("parent_wp_code", "")
        code, name = parent_entry.get("sheet_code", ""), parent_entry.get("sheet_name", "")
        owner = exact_identity.name_owner(parent, name, index=index) if name else None
        if owner is not None and owner.get("addr_id") == parent_entry.get("addr_id"):
            second, out.by_template_name = name, out.by_template_name + 1
        else:
            second, out.by_sheet_code = code, out.by_sheet_code + 1
        a1 = c.get("cell_address")
        third = a1 if a1 else (c.get("semantic_label") or "")
        c["formula_ref"] = f"WP('{parent}','{second}','{third}')"
        c["uri"] = f"wp://{parent}/{second}#{a1}" if a1 else f"wp://{parent}/{second}"
    return out


__all__ = [
    "KEEP_SEMANTIC_UNVERIFIED",
    "NameSystemError",
    "NameSystemOutcome",
    "apply_alias_policy",
    "apply_cell_names",
    "apply_cell_verdicts",
    "merge_platform_names",
]
