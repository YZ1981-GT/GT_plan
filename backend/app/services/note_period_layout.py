"""附注表格期间层：只在显示 / 导出还原，不改存储（spec note-pull-header-formula-closure R4 / ADR-3）。

单体模板为了让编辑器 / Word 只认两层表头，把底稿里「期间 / 账面余额·坏账准备 / 金额·比例」三层的表按期间拆开
（国企 八、5「按坏账准备计提方法分类」拆成期末 / 期初两张）、或去掉最上层统一期间（组合计提项目表每期一张）。
存储保持两层（推送规则、前端载荷、合并拉数、标题行库都按两层读，零改动）；显示与导出按底稿还原：

* ``side_by_side``：一张底稿表被拆成几张模板表 ⇒ 几张表横向合成一张，各自数据列外面包一层期间；
  **逐行行名一致才合成**（不一致保持原样，不猜）。
* ``top``：一对一配上、底稿最上层是统一期间、模板没有这一层 ⇒ 数据列外面包一层期间。

依据 = 底稿模板 xlsx 与单体模板逐表配对（``note_template_workpaper_alignment.compare_all``），由生成器
``scripts/gen/gen_note_table_period_layout.py`` 产出 ``backend/data/note_table_period_layout.json``（请求期只读这个文件、
不读 xlsx）。读时增强 ``attach_display_layout`` 把 ``_display_layout`` 挂到表上，编辑器（``noteTablePeriodLayout.ts`` 同规则）
与 Word 两种导出（``apply_period_layout`` + ``header_defs``）共用。
"""
from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAYOUT_PATH = DATA_DIR / "note_table_period_layout.json"
_SPACES = re.compile(r"\s+")

__all__ = [
    "LAYOUT_PATH", "apply_period_layout", "apply_period_layout_indexed", "attach_display_layout",
    "build_layout_document", "export_header_defs", "header_defs", "header_paths", "load_layouts",
    "render_layout_document",
]


def _norm(text: Any) -> str:
    return _SPACES.sub("", str(text or ""))


# ─── 生成（离线，读底稿 xlsx） ────────────────────────────────────────────────


def build_layout_document(results: Iterable[Any] | None = None, templates: dict | None = None) -> dict[str, Any]:
    """按底稿与模板逐表配对结果生成期间层布局：``{version, layouts: {口径: {章节: [条目]}}}``。

    条目：``{"mode": "side_by_side", "tables": [表名…], "periods": [期间…], "workpaper": "D2 sheet 第 r 行"}`` /
    ``{"mode": "top", "tables": [表名], "periods": [期间], "workpaper": …}``。按章节、表序排序，输出确定。
    """
    from app.services.note_template_workpaper_alignment import (
        _top_period,
        compare_all,
        load_templates,
        split_by_period,
        template_paths,
    )

    templates = templates or load_templates()
    if results is None:
        _mismatches, results = compare_all(templates)
    by_sec = {std: {s.get("section_number"): s for s in doc["sections"]} for std, doc in templates.items()}
    layouts: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for res in results:
        tables = (by_sec.get(res.std, {}).get(res.section) or {}).get("tables") or []
        entries: list[tuple[int, dict[str, Any]]] = []
        for pair in res.pairs:
            names = [str(tables[j].get("name") or "") for j in pair.tpl_idx]
            where = f"{pair.wp[0].wp_code} {pair.wp[0].sheet} 第 {pair.wp[0].header_rows[0]} 行" if pair.wp else ""
            if len(pair.tpl_idx) > 1 and len(pair.wp) == 1:
                parts = split_by_period(pair.wp[0])
                if parts and len(parts) == len(pair.tpl_idx) and all(names):
                    periods = [p.columns[1].raw[0] for p in parts]
                    entries.append((pair.tpl_idx[0], {"mode": "side_by_side", "tables": names, "periods": periods,
                                                       "workpaper": where}))
                continue
            if len(pair.tpl_idx) != len(pair.wp):
                continue
            for j, wp in zip(pair.tpl_idx, pair.wp):
                period = _top_period(wp.paths)
                tp = template_paths(tables[j], "headers") or []
                name = str(tables[j].get("name") or "")
                if period and name and _top_period(tp) is None:
                    entries.append((j, {"mode": "top", "tables": [name], "periods": [period],
                                        "workpaper": f"{wp.wp_code} {wp.sheet} 第 {wp.header_rows[0]} 行"}))
        if entries:
            layouts.setdefault(res.std, {})[res.section] = [e for _j, e in sorted(entries, key=lambda x: x[0])]
    return {
        "version": 1,
        "_doc": [
            "附注表格期间层布局（生成文件，勿手改）：scripts/gen/gen_note_table_period_layout.py 由底稿模板 xlsx 与单体模板"
            "逐表配对生成，--check 比对漂移。只影响编辑器显示与 Word 导出，不改存储。",
            "side_by_side：几张模板表是同一张底稿表按期间拆开的 ⇒ 横向合成，各自数据列外包一层期间（逐行行名一致才合成）；"
            "top：底稿最上层是统一期间、模板没有这一层 ⇒ 数据列外包一层期间。",
        ],
        "layouts": {std: dict(sorted(secs.items())) for std, secs in sorted(layouts.items())},
    }


def render_layout_document(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


# ─── 读取 / 读时增强 ──────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def load_layouts() -> dict[str, dict[str, list[dict[str, Any]]]]:
    try:
        return json.loads(LAYOUT_PATH.read_text(encoding="utf-8")).get("layouts") or {}
    except (OSError, ValueError):
        return {}


def attach_display_layout(table_data: Any, std: str | None, section: str | None) -> int:
    """按表名把 ``_display_layout`` 挂到 ``_tables`` 各表（就地；读时增强、不落库）。返回挂上的表数。

    ``top`` ⇒ ``{mode, period}``；``side_by_side`` ⇒ ``{mode, period, group, order}``（``group`` = 首张表名）。
    同一组的表必须都在（缺一张就整组不挂）。
    """
    if not isinstance(table_data, dict):
        return 0
    tables = table_data.get("_tables")
    if isinstance(tables, list):  # 先清掉存进库里的旧标记（前端保存会把读时增强的键带回去）：以布局文件为准
        for t in tables:
            if isinstance(t, dict):
                t.pop("_display_layout", None)
    entries = load_layouts().get(std, {}).get(section) or [] if std and section else []
    if not isinstance(tables, list) or not entries:
        return 0
    by_name: dict[str, dict] = {}
    for t in tables:
        if isinstance(t, dict) and _norm(t.get("name")) and _norm(t.get("name")) not in by_name:
            by_name[_norm(t.get("name"))] = t
    attached = 0
    for e in entries:
        found = [by_name.get(_norm(n)) for n in e.get("tables") or []]
        if not found or any(t is None for t in found):
            continue
        periods = list(e.get("periods") or [])
        for k, t in enumerate(found):
            layout = {"mode": e["mode"], "period": periods[k] if k < len(periods) else ""}
            if e["mode"] == "side_by_side":
                layout.update(group=str(e["tables"][0]), order=k)
            t["_display_layout"] = layout
            attached += 1
    return attached


# ─── 表头路径 / Word 表头行 ───────────────────────────────────────────────────


def header_paths(table: dict) -> list[tuple[str, ...]]:
    """展示用逐列表头路径（第 0 列为标签列）：合成表带 ``_header_paths``；否则标题行库 ``column_paths``，
    ``top`` 布局在数据列前加期间。"""
    explicit = table.get("_header_paths")
    if isinstance(explicit, list) and explicit:
        return [tuple(p) for p in explicit]
    from app.services.note_table_header_library import column_paths, norm

    headers = table.get("headers") if isinstance(table.get("headers"), list) else []
    paths = []
    for c, p in enumerate(column_paths(table)):
        raw = str(headers[c]).strip() if c < len(headers) and headers[c] is not None else ""
        # 结构按标题行库（规范化后比的），文字保留原样（「类 别」「账 龄」这类排版空格）
        paths.append((*p[:-1], raw) if p and raw and norm(raw) == p[-1] else tuple(p))
    layout = table.get("_display_layout") if isinstance(table.get("_display_layout"), dict) else {}
    period = str(layout.get("period") or "").strip()
    if layout.get("mode") == "top" and period and len(paths) > 1:
        paths = [paths[0], *[(period, *p) for p in paths[1:]]]
    return paths


def header_defs(paths: list[tuple[str, ...]]) -> list[list[dict[str, Any]]]:
    """逐列路径 → ``fill_multi_header`` 的表头行定义（N 行：分组跨列、比最深浅的列跨到底）。"""
    if not paths:
        return []
    depth = max(len(p) for p in paths) or 1
    rows: list[list[dict[str, Any]]] = [[] for _ in range(depth)]

    def walk(cols: list[int], level: int) -> None:
        i = 0
        while i < len(cols):
            p = paths[cols[i]]
            if len(p) - 1 <= level:
                rows[level].append({"text": p[-1] if p else "", "colspan": 1, "rowspan": depth - level})
                i += 1
                continue
            name = p[level]
            j = i
            while j < len(cols) and len(paths[cols[j]]) - 1 > level and paths[cols[j]][level] == name:
                j += 1
            rows[level].append({"text": name, "colspan": j - i, "rowspan": 1})
            walk(cols[i:j], level + 1)
            i = j

    walk(list(range(len(paths))), 0)
    return rows


# ─── Word 导出：合成 / 加层 ───────────────────────────────────────────────────


def _rows_match(a: dict, b: dict) -> bool:
    ra = [r for r in (a.get("rows") or []) if isinstance(r, dict)]
    rb = [r for r in (b.get("rows") or []) if isinstance(r, dict)]
    return bool(ra) and len(ra) == len(rb) and all(_norm(x.get("label")) == _norm(y.get("label")) for x, y in zip(ra, rb))


def _merge_side_by_side(group: list[dict]) -> dict:
    """同组几张表横向合成：标签列取首张；各张数据列依次排开、表头外包各自期间；单元格模式按列偏移带过来。"""
    first = group[0]
    parts_rows = [[r for r in (t.get("rows") or []) if isinstance(r, dict)] for t in group]
    widths = [max(0, len(t.get("headers") or []) - 1) for t in group]
    first_paths = header_paths({k: v for k, v in first.items() if k != "_display_layout"})
    paths: list[tuple[str, ...]] = [first_paths[0] if first_paths else ("",)]
    headers = [(first.get("headers") or [""])[0]]
    for t, width in zip(group, widths):
        period = str((t.get("_display_layout") or {}).get("period") or "").strip()
        t_paths = header_paths({k: v for k, v in t.items() if k != "_display_layout"})
        paths.extend(((period, *p) if period else p) for p in (t_paths[1:] + [("",)] * width)[:width])
        headers.extend(((t.get("headers") or [])[1:] + [""] * width)[:width])
    rows: list[dict] = []
    for i, base in enumerate(parts_rows[0]):
        values: list[Any] = []
        modes: dict[str, Any] = {}
        offset = 0
        for t_rows, width in zip(parts_rows, widths):
            row = t_rows[i]
            values.extend((list(row.get("values") or []) + [None] * width)[:width])
            for col, mode in (row.get("_cell_modes") or {}).items():
                if str(col).isdigit() and int(col) < width:
                    modes[str(int(col) + offset)] = mode
            offset += width
        merged_row = {**copy.deepcopy(base), "values": values}
        if modes:
            merged_row["_cell_modes"] = modes
        rows.append(merged_row)
    merged = {k: copy.deepcopy(v) for k, v in first.items()
              if k not in ("_column_groups", "multi_header", "_display_layout", "columns", "header_rows")}
    merged.update(headers=headers, rows=rows, _header_paths=[list(p) for p in paths],
                  _merged_from=[t.get("name") for t in group])
    return merged


def apply_period_layout_indexed(items: list[tuple[int, dict, bool]], std: Any, section: str | None
                                ) -> list[tuple[int, dict, bool]]:
    """Word 导出前（``[(原表序, 表, 是否空表)]``）：按布局挂 ``_display_layout``（表的浅拷贝，不改入参）后，
    ``side_by_side`` 同组合成一张（逐行行名一致才合；合成表取首张的表序，全组都空才算空表）；``top`` 写出
    ``_header_paths``（Word 表头多一层期间）。没有布局的章节原样返回。"""
    std = getattr(std, "value", std)
    copies = [(i, dict(t), e) for i, t, e in items]
    if not attach_display_layout({"_tables": [t for _i, t, _e in copies]}, str(std) if std else None, section):
        return items
    groups: dict[str, list[tuple[int, dict, bool]]] = {}
    for item in copies:
        layout = item[1].get("_display_layout")
        if isinstance(layout, dict) and layout.get("mode") == "side_by_side":
            groups.setdefault(str(layout.get("group")), []).append(item)
    out: list[tuple[int, dict, bool]] = []
    done: set[str] = set()
    for idx, t, empty in copies:
        layout = t.get("_display_layout")
        if not isinstance(layout, dict):
            out.append((idx, t, empty))
        elif layout.get("mode") == "top":
            out.append((idx, {**t, "_header_paths": [list(p) for p in header_paths(t)]}, empty))
        else:
            group = sorted(groups.get(str(layout.get("group")), []),
                           key=lambda x: int((x[1].get("_display_layout") or {}).get("order") or 0))
            tables = [g[1] for g in group]
            if len(tables) < 2 or not all(_rows_match(tables[0], g) for g in tables[1:]):
                t = {k: v for k, v in t.items() if k != "_display_layout"}  # 行名不一致 / 缺表：保持原样
                out.append((idx, t, empty))
            elif str(layout.get("group")) not in done:
                done.add(str(layout.get("group")))
                out.append((group[0][0], _merge_side_by_side(tables), all(g[2] for g in group)))
    return out


def apply_period_layout(tables: list[dict], std: Any, section: str | None) -> list[dict]:
    """``apply_period_layout_indexed`` 的表列表版本（程序化导出用）。"""
    return [t for _i, t, _e in apply_period_layout_indexed([(i, t, False) for i, t in enumerate(tables)], std, section)]


def export_header_defs(table: dict) -> list[list[dict[str, Any]]] | None:
    """Word 导出的多级表头行：合成 / 加了期间层（``_header_paths``）或表头 ≥ 3 层时给出 N 行定义；
    两层分组表头照旧由导出器按 ``_column_groups`` 画两行（返回 None），单行表头也返回 None。"""
    if not isinstance(table, dict):
        return None
    explicit = isinstance(table.get("_header_paths"), list) and table.get("_header_paths")
    try:
        paths = header_paths(table)
    except Exception:  # noqa: BLE001 —— 表头跨度坏了：退回导出器原来的两行 / 一行
        return None
    if not paths or (not explicit and max(len(p) for p in paths) < 3):
        return None
    defs = header_defs(paths)
    return defs if len(defs) >= 2 else None
