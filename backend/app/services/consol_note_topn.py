"""合并附注「前 N 名」类表：按单位跨企业合并后重排取前 N（spec note-pull-followup-closure R10 / ADR-7）。

「按欠款方归集的期末余额前五名」这类表的行随数据变化（每行是一个欠款单位），不经映射骨架：原先按行名跨企业相加，
比例列被加总、不重排、不截 N。现在：

* 识别：合并模板表名里有「前 N 名」（``topn_limit``）；
* 列：第 0 列单位名称；表头含「比例」「%」的是比例列；含「性质」「账龄」或标题行库判为说明的是文字列；其余是金额列，
  第一个不含「准备」的金额列是排名用的期末账面余额（``topn_columns``）；
* 重排（``rerank``）：同名单位合并（金额相加、文字去重并列），集团内单位（企业树里的企业）不进排名，按期末余额从大到小
  取前 N；合计 = 前 N 行之和；比例 = 期末余额 ÷ 分母 × 100，分母取不到留空并回报原因；
* 分母（``topn_denominator``）：同章「按账龄披露 / 列示」表本节点已保存的期末账面余额合计（有「小计 / 减：… / 合计」时取小计，
  即扣准备前的毛额）；
* 写入（``write_topn``）：手工 / 锁定格按单位名称对到新行（不按位置：行是单位，换了单位位置就不是同一行），对不上的回报。

数据叶子按该企业单体附注的前 N 名重排（去掉集团内单位）；汇总节点只能基于下级已保存的前 N 名重排 —— 下级第 N 名之后的单位
看不到，结果是近似（``_topn.approximate``，界面写明）。Service 只 flush 不 commit。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.consol_note_table_totals import fmt_amount, to_decimal

__all__ = [
    "TopNColumns", "TopNEntry", "TopNResult", "apply_topn_refresh", "group_unit_names", "rerank",
    "section_topn_limit", "topn_columns", "topn_denominator", "topn_denominator_table", "topn_entries", "topn_limit",
    "topn_table", "write_topn",
]

_TOPN_RE = re.compile(r"前\s*([一二三四五六七八九十]+|\d+)\s*名")
_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_RATIO_RE = re.compile(r"比例|比率|%|％")
_TEXT_WORDS = ("性质", "账龄", "原因", "说明", "备注")
_AGING_TABLE_RE = re.compile(r"按账龄(?:披露|列示)|账龄(?:披露|列示)")
TOTAL_LABEL = "合  计"


def topn_limit(title: Any) -> int | None:
    """表名里的「前 N 名」→ N；不是前 N 名表 → None。"""
    m = _TOPN_RE.search(str(title or ""))
    if not m:
        return None
    text = m.group(1)
    if text.isdigit():
        return int(text) or None
    if text == "十":
        return 10
    if len(text) == 2 and text[0] == "十":
        return 10 + _CN_DIGITS.get(text[1], 0)
    return _CN_DIGITS.get(text[0]) if len(text) == 1 else None


def section_topn_limit(template_type: str, section_id: str) -> int | None:
    from app.services.consol_note_formula_service import find_table

    table = find_table(template_type, section_id) or {}
    return topn_limit(table.get("title") or table.get("name"))


def _norm(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _unit_key(name: Any) -> str:
    from app.services.consol_elimination_sheet_service import name_key

    return name_key(name)


@dataclass(frozen=True)
class TopNColumns:
    balance: int
    amounts: tuple[int, ...]
    ratio: tuple[int, ...]
    text: tuple[int, ...]


def topn_columns(headers: Sequence[Any]) -> TopNColumns | None:
    """列角色（列号含第 0 列）；没有能排名的期末余额列 → None。"""
    from app.services.note_table_header_library import load_vocabulary, norm

    vocab = load_vocabulary()
    amounts: list[int] = []
    ratio: list[int] = []
    text: list[int] = []
    for col, raw in enumerate(headers[1:], start=1):
        header = _norm(raw)
        if _RATIO_RE.search(header) or vocab.ratio_re.search(norm(raw)):
            ratio.append(col)
        elif any(w in header for w in _TEXT_WORDS) or vocab.text_re.search(norm(raw)):
            text.append(col)
        else:
            amounts.append(col)
    balance = next((c for c in amounts if "准备" not in _norm(headers[c])), None)
    if balance is None:
        return None
    return TopNColumns(balance, tuple(amounts), tuple(ratio), tuple(text))


@dataclass
class TopNEntry:
    """一家企业（或一个下级）表里的一行：单位名称 + 列号 → 原始值。"""
    name: str
    cells: dict[int, Any]
    source: str = ""


@dataclass
class TopNResult:
    rows: list[list[str]]
    names: list[str]
    excluded: list[str] = field(default_factory=list)   # 集团内单位（不进排名）
    beyond: int = 0                                     # 排在第 N 名之后的单位数
    reasons: list[str] = field(default_factory=list)
    columns: TopNColumns | None = None
    denominator: Decimal | None = None


def finish_rows(rows: list[list[str]], columns: TopNColumns, denominator: Decimal | None,
                guard: set[tuple[int, int]] = frozenset()) -> None:
    """最后一行是合计：金额列 = 上面各行之和（都没有数留空）；比例 = 期末余额 ÷ 分母 × 100（分母取不到留空）。
    ``guard`` 里的格（手工 / 锁定，新行号）不动 —— 合计用已组装好的行（含手工值）重算，与其他表同口径。"""
    ratio_ok = denominator is not None and denominator != 0

    def ratio_of(balance: Decimal | None) -> str:
        if not ratio_ok or balance is None:
            return ""
        return str((balance / denominator * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    *body, total = rows
    t = len(rows) - 1
    for col in columns.amounts:
        if (t, col) in guard or col >= len(total):
            continue
        values = [v for row in body if (v := to_decimal(row[col])) is not None]
        total[col] = fmt_amount(sum(values, Decimal(0))) if values else ""
    for i, row in enumerate(rows):
        for col in columns.ratio:
            if (i, col) not in guard and col < len(row):
                row[col] = ratio_of(to_decimal(row[columns.balance]))


def rerank(entries: Iterable[TopNEntry], *, columns: TopNColumns, limit: int, width: int,
           exclude: Iterable[str] = (), denominator: Decimal | None = None,
           denominator_reason: str | None = None) -> TopNResult:
    """同名合并 → 去集团内单位 → 按期末余额取前 N → 合计 / 比例。"""
    blocked = {_unit_key(n) for n in exclude if _unit_key(n)}
    merged: dict[str, dict[str, Any]] = {}
    excluded: list[str] = []
    for entry in entries:
        name = str(entry.name or "").strip()
        key = _unit_key(name)
        if not key:
            continue
        if key in blocked:
            if name not in excluded:
                excluded.append(name)
            continue
        item = merged.setdefault(key, {"name": name, "amounts": {}, "text": {}})
        for col in columns.amounts:
            value = to_decimal(entry.cells.get(col))
            if value is not None:
                item["amounts"][col] = item["amounts"].get(col, Decimal(0)) + value
        for col in columns.text:
            value = str(entry.cells.get(col) or "").strip()
            if value and value not in item["text"].setdefault(col, []):
                item["text"][col].append(value)
    ranked = sorted((m for m in merged.values() if m["amounts"]),
                    key=lambda m: (-m["amounts"].get(columns.balance, Decimal(0)), _unit_key(m["name"])))
    top = ranked[:limit]
    reasons: list[str] = []
    if columns.ratio and (denominator is None or denominator == 0):
        reasons.append(denominator_reason or "比例列分母取不到，比例留空")
    rows: list[list[str]] = []
    for item in top:
        row = [""] * width
        row[0] = item["name"]
        for col, value in item["amounts"].items():
            if col < width:
                row[col] = fmt_amount(value)
        for col, values in item["text"].items():
            if col < width:
                row[col] = "、".join(values)
        rows.append(row)
    rows.append([TOTAL_LABEL] + [""] * (width - 1))
    finish_rows(rows, columns, denominator)
    return TopNResult(rows, [item["name"] for item in top], excluded, max(0, len(ranked) - limit), reasons,
                      columns, denominator)


def group_unit_names(tree: Any) -> list[str]:
    """企业树里全部企业的名称（集团内单位不进前 N 名排名）。"""
    if tree is None:
        return []
    from app.services.consol_tree_service import iter_nodes

    return [n.company_name for n in iter_nodes(tree) if getattr(n, "company_name", "")]


def topn_denominator_table(template_type: str, section_id: str) -> tuple[dict | None, int | None, str]:
    """比例列分母取自哪张表的哪一列：同章第一张「按账龄披露 / 列示」表的期末账面余额列 → (表, 列号, 说明 / 原因)。"""
    from app.services.consol_note_formula_service import consol_note_tables, find_table, value_column

    chapter = (find_table(template_type, section_id) or {}).get("parent_section")
    aging = next((t for t in consol_note_tables(template_type)
                  if t.get("parent_section") == chapter and t.get("section_id") != section_id
                  and _AGING_TABLE_RE.search(_norm(t.get("title")))), None)
    if aging is None:
        return None, None, f"同章（{chapter or '未知章节'}）没有按账龄披露的表，比例列分母取不到，比例留空"
    col, why = value_column(aging, "balance_sheet", net=False)
    title = str(aging.get("title") or aging.get("section_id"))
    if col is None:
        return aging, None, f"「{title}」认不出期末账面余额列（{why}），比例留空"
    return aging, col, f"「{title}」期末账面余额"


async def topn_denominator(db: AsyncSession, *, project_id: UUID, year: int, template_type: str, section_id: str,
                           node_key: str | None) -> tuple[Decimal | None, str]:
    """比例列分母：同章按账龄披露表本节点已保存的期末账面余额合计 → (值, 说明)；取不到值为 None、说明写原因。"""
    from app.models.consol_note_data_models import ConsolNoteData
    from app.services.note_total_terms import label_row_type

    aging, col, why = topn_denominator_table(template_type, section_id)
    if aging is None or col is None:
        return None, why
    title = str(aging.get("title") or aging.get("section_id"))
    q = sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == project_id, ConsolNoteData.year == year,
        ConsolNoteData.section_id == aging["section_id"],
        ConsolNoteData.node_key == node_key if node_key is not None else ConsolNoteData.node_key.is_(None),
    )
    record = (await db.execute(q)).scalar_one_or_none()
    rows = (record.data or {}).get("rows") if record is not None and isinstance(record.data, dict) else None
    if not isinstance(rows, list) or not rows:
        return None, f"「{title}」本节点还没有数（先拉数 / 汇总该表），比例留空"
    kinds = [label_row_type(r[0] if isinstance(r, (list, tuple)) and r else "") for r in rows]
    pick = next((i for i, k in enumerate(kinds) if k == "subtotal" and _norm(rows[i][0]) in ("小计", "小计:", "小计：")),
                None)
    if pick is None:
        pick = next((i for i, k in enumerate(kinds) if k == "total"), None)
    value = to_decimal(rows[pick][col]) if pick is not None and col < len(rows[pick]) else None
    if value is None:
        return None, f"「{title}」本节点的期末账面余额合计没有数，比例留空"
    return value, f"「{title}」期末账面余额{'小计' if kinds[pick] == 'subtotal' else '合计'}"


def write_topn(record: Any, *, headers: Sequence[Any], result: TopNResult, limit: int, approximate: bool,
               denominator: Decimal | None, denominator_note: str, data_updates: dict[str, Any] | None = None,
               ) -> dict[str, Any]:
    """把重排结果写进合并附注记录；手工 / 锁定格按单位名称对到新行（对不上的回报）。返回写入摘要。"""
    from app.services.consol_note_detail_apply_service import (
        _parse_locked_cells,
        _parse_manual_cells,
        remap_protected,
    )

    data = dict(record.data) if isinstance(record.data, dict) else {}
    manual, locked = _parse_manual_cells(data), _parse_locked_cells(record)
    old_rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    old_index = {}
    for i, row in enumerate(old_rows):
        label = row[0] if isinstance(row, (list, tuple)) and row else (row.get("label") if isinstance(row, dict) else "")
        old_index.setdefault(_unit_key(label), i)
    new_index = {_unit_key(row[0]): i for i, row in enumerate(result.rows)}
    old_to_new = {old: new_index[key] for key, old in old_index.items() if key in new_index}
    kept: list[dict[str, Any]] = []
    guard: set[tuple[int, int]] = set()
    for r, c in sorted(manual | locked):
        new = old_to_new.get(r)
        if new is None or r >= len(old_rows) or not isinstance(old_rows[r], (list, tuple)) or c >= len(old_rows[r]):
            continue
        result.rows[new][c] = str(old_rows[r][c] if old_rows[r][c] is not None else "")
        guard.add((new, c))
        kept.append({"row": new, "col": c, "kept_value": result.rows[new][c]})
    if guard and result.columns is not None:
        finish_rows(result.rows, result.columns, result.denominator, guard)  # 合计 / 比例按含手工值的行重算
    lost = remap_protected(data, record, manual, locked, old_to_new)
    data["rows"] = result.rows
    data["headers"] = data.get("headers") or list(headers)
    data["_topn"] = {
        "limit": limit, "approximate": approximate, "units": result.names, "excluded_group_units": result.excluded,
        "beyond_count": result.beyond, "denominator": None if denominator is None else str(denominator),
        "denominator_source": denominator_note, "reasons": result.reasons,
    }
    data.update(data_updates or {})
    record.data = data
    record.is_stale = False
    record.updated_at = datetime.now(timezone.utc)
    return {"kept": kept, "lost_protected": lost, "units": result.names, "excluded": result.excluded,
            "beyond_count": result.beyond, "reasons": result.reasons, "approximate": approximate}


def _raw_cells(row: Any) -> dict[int, Any]:
    """来源行 / 已保存行 → {列号: 原始值}（含文字列；行名在第 0 列，不在结果里）。"""
    if isinstance(row, dict):
        vals = row.get("values")
        if isinstance(vals, dict):
            return {int(k): v for k, v in vals.items() if str(k).isdigit() and int(k) >= 1}
        if isinstance(vals, (list, tuple)):
            return {k + 1: v for k, v in enumerate(vals)}
        return {}
    if isinstance(row, (list, tuple)):
        return {j: v for j, v in enumerate(row) if j >= 1}
    return {}


def topn_entries(rows: Iterable[Any], source: str) -> list[TopNEntry]:
    """表里的单位行（去掉合计 / 小计、空行名、「……」占位行）。"""
    from app.services.consol_note_detail_source_service import _first_cell
    from app.services.consol_note_detail_suggest import is_placeholder_label
    from app.services.note_total_terms import label_row_type

    out = []
    for row in rows:
        if isinstance(row, dict) and (row.get("is_total") or row.get("row_type") in ("total", "subtotal")):
            continue
        name = _first_cell(row).strip()
        if not name or label_row_type(name) != "data" or is_placeholder_label(name):
            continue
        out.append(TopNEntry(name, _raw_cells(row), source))
    return out


def topn_table(template_type: str, section_id: str) -> tuple[list[Any], TopNColumns | None]:
    from app.services.consol_note_formula_service import find_table

    headers = list((find_table(template_type, section_id) or {}).get("headers") or [])
    return headers, topn_columns(headers)


async def apply_topn_refresh(db: AsyncSession, *, project_id: UUID, section_id: str, year: int, limit: int,
                             template_type: str, node_key: str | None = None,
                             scope_leaves: list[Any] | None = None) -> dict[str, Any]:
    """数据叶子 / 指定节点：本节点范围内各企业单体附注的前 N 名表按单位合并重排后写入（不需明细映射）。

    映射里被排除的企业不计入；集团内单位不进排名；回报形状与 ``apply_detail_refresh`` 相同（另带 ``topn``）。
    """
    from app.models.consol_note_mapping_models import ConsolNoteMappingBinding
    from app.services.consol_calc_basis import data_leaves
    from app.services.consol_note_detail_apply_service import (
        WRITE_SOURCE,
        ApplyError,
        _load_or_create_note_data,
        _scope_data_leaves,
    )
    from app.services.consol_note_detail_source_service import load_source_tables
    from app.services.consol_tree_service import build_tree

    headers, columns = topn_table(template_type, section_id)
    if columns is None:
        raise ApplyError(400, "TOPN_NO_BALANCE_COLUMN", f"前 {limit} 名表认不出期末余额列（表头：{'、'.join(map(str, headers[1:]))}）")
    tree = await build_tree(db, project_id)
    leaves = scope_leaves if scope_leaves is not None else await _scope_data_leaves(db, project_id, node_key)
    if leaves is None:
        leaves = data_leaves(tree) if tree is not None else []
    excluded_keys = set((await db.execute(sa.select(ConsolNoteMappingBinding.entity_node_key).where(
        ConsolNoteMappingBinding.project_id == project_id, ConsolNoteMappingBinding.section_id == section_id,
        ConsolNoteMappingBinding.status == "excluded"))).scalars().all())
    leaves = [leaf for leaf in leaves if leaf.project_id is not None and leaf.node_key not in excluded_keys]
    if not leaves:
        raise ApplyError(400, "NO_BINDINGS", "本节点范围内没有可拉数的子企业")
    sources = await load_source_tables(db, [leaf.project_id for leaf in leaves], section_id, year,
                                       template_type=template_type)
    entries: list[TopNEntry] = []
    applied: list[str] = []
    skipped: list[dict[str, Any]] = []
    for leaf in leaves:
        src = sources.get(leaf.project_id)
        rows = src.rows if src is not None else []
        if not rows:
            skipped.append({"node_key": leaf.node_key,
                            "reason": (src.reason if src is not None else None) or "未读到来源"})
            continue
        applied.append(leaf.node_key)
        entries.extend(topn_entries(rows, leaf.node_key))

    record = await _load_or_create_note_data(db, project_id, year, section_id, node_key)
    if getattr(record, "cell_state", "auto") == "locked":
        return {"status": "skipped_locked", "reason": "整节被锁定（cell_state=locked），不覆盖", "section_id": section_id}
    denominator, note = await topn_denominator(db, project_id=project_id, year=year, template_type=template_type,
                                               section_id=section_id, node_key=node_key)
    result = rerank(entries, columns=columns, limit=limit, width=max(len(headers), 2),
                    exclude=group_unit_names(tree), denominator=denominator, denominator_reason=note)
    summary = write_topn(record, headers=headers, result=result, limit=limit, approximate=False,
                         denominator=denominator, denominator_note=note, data_updates={
                             "_last_write_source": WRITE_SOURCE, "_detail_entity_count": len(applied),
                             "_detail_applied_at": datetime.now(timezone.utc).isoformat()})
    for stale_key in ("_detail_provenance",):
        record.data.pop(stale_key, None)
    await db.flush()
    return {
        "status": "applied", "section_id": section_id, "node_key": node_key,
        "applied_entity_count": len(applied), "skipped_stale": [], "skipped_entities": skipped,
        "unbound_entities": [], "out_of_scope_count": 0,
        "filled_count": sum(1 for row in result.rows for cell in row[1:] if str(cell).strip()),
        "kept_manual_count": len(summary["kept"]), "filled": [], "kept_manual": summary["kept"][:50],
        "template_row_count": 0, "output_row_count": len(result.rows), "dropped_placeholders": [],
        "lost_protected": summary["lost_protected"][:50], "inactive_optional_count": 0, "topn": summary,
    }
