"""合并附注明细模板建议：来源独有的明细行放在哪（spec note-table-structure-formula-pull-closure R6.4）。

原先来源独有的行一律替换第一个「……」占位行、没有占位行就插在第一个合计行之前，且同名行只留一行 ⇒ 上市「按坏账计提
方法分类」里「按单项计提坏账准备 / 其中：」下的欠款单位与「按组合计提坏账准备 / 其中：」下的组合全挤到组合那一组末尾；
无形资产「一、原价合计 / 二、累计摊销合计 / …」各组都有的「住房使用权」只建一行，其余三组只能按位置配（须人工确认）。
现在按来源里的位置放：来源独有行的第 k 次出现跟在来源里它前面最近的一行模板也有的行（或已放好的来源独有行）之后；
紧跟着的「……」占位行由它们替换。来源里前面没有模板行的，照旧替换第一个「……」/ 插在第一个合计行之前。纯函数，无 DB。
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["place_source_rows", "suggest_detail_rows"]

_Anchor = tuple[str, Any]  # ("t", 骨架行号) / ("x", (来源独有行的键, 第几次出现))


def suggest_detail_rows(table: dict[str, Any], entity_rows: Sequence[Sequence[Any]]) -> list[dict[str, Any]]:
    """合并模板表 + 各企业来源行 → 建议的明细模板行（``suggest_template_for_section`` 的纯计算部分）。

    - 骨架 = 合并模板该表的行（顺序 / 行类型；「……」= 可扩位占位 ``dynamic_zone``）；
    - 通用别名库认得的写法（「现金」→「库存现金」、「其中：软件」↔「软件」）并进模板行别名（同名行都加），不单列一行；
    - 单体账龄档整段落在模板某一档里（「3至4年」→「3年以上」）不另起一行，明细映射按 ``aging_bucket`` 相加；
    - 其余来源独有的明细行按来源位置放（``place_source_rows``）；合并模板缺该表时按来源出现顺序，合计行放最后。
    每行带来源出现次数与金额合计（``frequency`` / ``total_amount`` / ``entity_total``）。
    """
    from app.services.consol_note_detail_source_service import _first_cell, _row_numbers, _row_type
    from app.services.consol_note_detail_suggest import _label_key, _load_global_aliases, is_placeholder_label
    from app.services.note_aging_buckets import containing_bucket

    stats_of: dict[str, dict[str, Any]] = {}  # 行名比较键 → 首次出现的写法 / 次数 / 金额
    for rows in entity_rows:
        for row in rows:
            label = _first_cell(row).strip()
            key = _label_key(label)
            if key:
                stats = stats_of.setdefault(key, {"label": label, "count": 0, "row_type": _row_type(row),
                                                  "total_amount": 0.0})
                stats["count"] += 1
                stats["total_amount"] += sum(abs(float(v)) for v in _row_numbers(row))

    skeleton: list[dict[str, Any]] = []
    row_types = table.get("_row_types") or []
    for i, trow in enumerate(table.get("rows") or []):
        label = _first_cell(trow).strip()
        key = _label_key(label)
        if not key:
            continue
        declared = row_types[i] if i < len(row_types) else ""
        stats = stats_of.get(key)
        canonical = key if key in ("合计", "小计") else label
        skeleton.append({
            "canonical_name": canonical,
            "aliases": [stats["label"]] if stats and stats["label"] != canonical else [],
            "row_type": declared if declared in ("total", "subtotal") else _row_type([label]),
            "origin": "template",
            "_key": key,
            # 「……」可扩位占位：动态行区（下推不写进子企业附注；有来源独有行时由它们替换）
            **({"category": "dynamic_zone"} if is_placeholder_label(label) else {}),
        })

    template_keys = {r["_key"] for r in skeleton}
    variants = _load_global_aliases()
    canonical_of: dict[str, list[str]] = {}  # 标准名 → 变体（来源用标准名、模板用变体：「软件」↔「其中：软件」）
    for variant, canonical in variants.items():
        canonical_of.setdefault(canonical, []).append(variant)
    merged: dict[str, str] = {}  # 并进模板行的来源行名键 → 骨架行名键
    names = [r["canonical_name"] for r in skeleton]
    for key, stats in stats_of.items():
        if key in template_keys:
            continue
        same = variants.get(key) if variants.get(key) in template_keys else next(
            (v for v in canonical_of.get(key, ()) if v in template_keys), None)
        if same is not None:  # 同名行（各分组的「土地使用权」）都加别名，分组配对才对得上
            for r in skeleton:
                if r["_key"] == same and stats["label"] not in r["aliases"]:
                    r["aliases"].append(stats["label"])
            merged[key] = same
        elif stats["row_type"] == "data" and (bucket := containing_bucket(stats["label"], names)) is not None:
            merged[key] = skeleton[bucket]["_key"]
    extras = [{"canonical_name": s["label"], "aliases": [], "row_type": s["row_type"], "origin": "source", "_key": k}
              for k, s in stats_of.items()  # 来源出现顺序（企业树先序、表内行序）
              if k not in template_keys and k not in merged and s["row_type"] == "data"]
    if skeleton:
        ordered = place_source_rows(skeleton, extras, [[_label_key(_first_cell(r).strip()) for r in rows]
                                                       for rows in entity_rows], merged)
    else:  # 合并模板缺该表：按来源出现顺序，合计行放最后
        ordered = extras + [{"canonical_name": s["label"], "aliases": [], "row_type": s["row_type"],
                             "origin": "source", "_key": k} for k, s in stats_of.items() if s["row_type"] != "data"]
    out: list[dict[str, Any]] = []
    for i, r in enumerate(ordered):
        stats = stats_of.get(r["_key"])
        out.append({**{k: v for k, v in r.items() if k != "_key"}, "sort_order": i * 10,
                    "frequency": stats["count"] if stats else 0,
                    "total_amount": round(stats["total_amount"], 2) if stats else 0.0,
                    "entity_total": len(entity_rows)})
    return out


def place_source_rows(
    skeleton: Sequence[dict[str, Any]],
    extras: Sequence[dict[str, Any]],
    sequences: Sequence[Sequence[str]],
    merged: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """骨架行 + 来源独有行 → 建议模板行序。

    ``skeleton``：合并模板骨架行（``_key`` 行名比较键、``row_type``、可扩位占位行 ``category="dynamic_zone"``）；
    ``extras``：来源独有的行（``_key``，来源出现顺序，每个键一行）；``sequences``：每家企业来源行的行名比较键（企业树先序、
    表内行序）；``merged``：并进了模板行的来源行名键 → 骨架行名键（别名 / 账龄档包含），来源里第 k 次出现对骨架第 k 个
    同名行，也当位置锚点。同一来源独有行出现几次（各分组各一行）就放几行。
    """
    if not extras:
        return list(skeleton)
    merged = merged or {}
    slot: dict[tuple[str, int], int] = {}
    seen: Counter[str] = Counter()
    for i, row in enumerate(skeleton):
        slot[(row["_key"], seen[row["_key"]])] = i
        seen[row["_key"]] += 1
    by_key = {row["_key"]: row for row in extras}
    after: dict[_Anchor, list[tuple[str, int]]] = {}
    placed: set[tuple[str, int]] = set()
    for keys in sequences:
        occ: Counter[str] = Counter()
        anchor: _Anchor | None = None
        for key in keys:
            k = occ[key]
            occ[key] += 1
            if key in by_key:
                if (key, k) not in placed and anchor is not None:
                    after.setdefault(anchor, []).append((key, k))
                    placed.add((key, k))
                if (key, k) in placed:
                    anchor = ("x", (key, k))
                continue
            pos = slot.get((merged.get(key, key), k))
            if pos is not None:
                anchor = ("t", pos)

    out: list[dict[str, Any]] = []

    def emit(anchor: _Anchor) -> None:
        for key, k in after.get(anchor, []):
            out.append(by_key[key] if k == 0 else dict(by_key[key]))
            emit(("x", (key, k)))

    for i, row in enumerate(skeleton):
        if row.get("category") == "dynamic_zone" and i and after.get(("t", i - 1)):
            continue  # 「……」由紧挨着它前面那行之后的来源独有行替换
        out.append(row)
        emit(("t", i))
    loose = [row for row in extras if (row["_key"], 0) not in placed]
    if not loose:
        return out
    holder = next((i for i, row in enumerate(out) if row.get("category") == "dynamic_zone"), None)
    if holder is not None:
        return out[:holder] + loose + out[holder + 1:]
    cut = next((i for i, row in enumerate(out) if row.get("row_type") == "total"), len(out))
    return out[:cut] + loose + out[cut:]
