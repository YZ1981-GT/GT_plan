"""附注主表格的权威源交接：公式推送写过的格，披露同步写入后保持推送值（spec note-pull-followup-closure R3 / ADR-3）。

披露同步（底稿披露 Tab → ``sync-from-workpaper`` / HTML 入口）按表整表替换行，公式推送按格写，原先后写的赢：先推送、
再保存底稿披露 Tab，试算表审定数就被披露 Tab 里发布前的底稿数覆盖，下一次推送又改回来（来回翻）。交接规则：

- 推送最近一次写入 / 核对一致（推送状态 ``auto``、有推送值）的格归推送：同步写入后恢复推送值，逐格回报 ``push_kept``
  （前端提示「以试算表审定数为准」）；
- 合计格分两种（与引擎同口径）：表里还有推送写的数据格 ⇒ 合计是推送按本表重算的，只在本次恢复了数据格时按本表重算
  （``note_writer.total_formula``，与 ``_push_note_total`` 同一函数）；表里只有合计格是推送写的 ⇒ 合计行兜底写入的科目
  合计（数据行一行都没对上），与数据格一样恢复推送值；
- 整节人工覆盖（``_manual_override``）不动；规则已删除 / 本项目停用的推送状态不认（2026-10-27 删除的子表规则在真库留有
  状态）；同一期间对应多个字段的规则（D1 主表六字段）无法从地址还原字段，不恢复；同名行有两行以上、找不到行的不恢复。

只改调用方传入的 ``table_data``，不提交。
"""
from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_push import note_writer
from app.services.formula_push.policy import values_equal

__all__ = ["parse_note_addr", "reapply_pushed_cells"]


def parse_note_addr(addr: str) -> tuple[str, str, str, str] | None:
    """``note://五、1/货币资金/库存现金.end`` → (章节, 表名, 行名, 期间)；不是附注地址返回 None。"""
    if not isinstance(addr, str) or not addr.startswith("note://"):
        return None
    body, _, period = addr[len("note://"):].rpartition(".")
    section, _, rest = body.partition("/")
    table, _, label = rest.rpartition("/")
    if not (section and table and period in ("end", "prior")):
        return None
    return section, table, label, period


def _value_keys(table_data: dict, table: str) -> list[str]:
    """与 ``note_writer.locate_table`` 子表路径同口径：``_sub_table_columns`` 里去掉标签列的键。"""
    cols = table_data.get("_sub_table_columns")
    defs = [d for d in ((cols or {}).get(table) or []) if isinstance(d, dict) and d.get("key")] if isinstance(
        cols, dict) else []
    label_def = next((d for d in defs if d.get("is_label")), defs[0] if defs else None)
    return [d["key"] for d in defs if d is not label_def]


def _is_total(row: Any) -> bool:
    return isinstance(row, dict) and bool(row.get("is_total") or row.get("row_type") == "total")


def _norm(text: Any) -> str:
    return "".join(str(text or "").split())


def _locate(rows: list, label: str) -> int | None:
    """推送地址里的行名 → 行号。合计行按去空白的行名唯一对上（「合  计」与「合计」）；数据行与引擎找行同一函数。"""
    totals = [i for i, r in enumerate(rows) if _is_total(r) and _norm(note_writer.row_label(r)) == _norm(label)]
    if len(totals) == 1:
        return totals[0]
    return note_writer.find_row(rows, [label]) if label else None


async def _owned_states(db: AsyncSession, project_id: UUID, year: int, section: str) -> list[Any]:
    from app.models.formula_push_models import FormulaPushState

    return list((await db.execute(sa.select(FormulaPushState).where(
        FormulaPushState.project_id == project_id,
        FormulaPushState.year == year,
        FormulaPushState.domain == "note",
        FormulaPushState.note_section == section,
        FormulaPushState.state == "auto",
        FormulaPushState.last_pushed_value.is_not(None),
    ))).scalars().all())


async def reapply_pushed_cells(
    db: AsyncSession, *, project_id: UUID, year: int, section: str, table_data: dict, touched: Iterable[str],
) -> list[dict[str, Any]]:
    """把本次同步写过的表里、推送拥有的格恢复为推送值；返回逐格差异（``kind``：cell / fallback_total / total）。"""
    sub = table_data.get("sub_table_data")
    touched = {str(t) for t in touched}
    if not (isinstance(sub, dict) and touched) or note_writer.detect_manual_override(table_data):
        return []
    states = [s for s in await _owned_states(db, project_id, year, section)
              if (parsed := parse_note_addr(s.addr_id)) and parsed[1] in touched]
    if not states:
        return []
    from app.services.formula_settings.push_settings import effective_push_rules

    rules, _issues = await effective_push_rules(db, project_id)
    rule_of = {r.rule_id: r for r in rules}

    # (表, 行号, 字段, 期间, 行名, 推送值)；合计格单列
    cells: list[tuple[str, int, str, str, str, Any]] = []
    totals: list[tuple[str, int, str, str, str, Any]] = []
    for state in states:
        _sec, table, label, period = parse_note_addr(state.addr_id)
        rule = rule_of.get(state.rule_id)
        rows = sub.get(table)
        # 有效规则清单逐条保留停用（status=disabled）/ 失效（invalid）的规则，只认 active（与引擎「本次会推」同口径）
        if rule is None or rule.status != "active" or not isinstance(rows, list):
            continue
        fields = [f for f in rule.target.fields if note_writer.NOTE_FIELDS.get(f, ("", ""))[1] == period]
        index = _locate(rows, label)
        if len(fields) != 1 or index is None:
            continue
        (totals if _is_total(rows[index]) else cells).append(
            (table, index, fields[0], period, label, state.last_pushed_value))
    data_tables = {c[0] for c in cells}

    kept: list[dict[str, Any]] = []
    restored: set[str] = set()

    def restore(table: str, index: int, field: str, period: str, label: str, pushed: Any, kind: str) -> None:
        rows, keys = sub[table], _value_keys(table_data, table)
        ok, incoming, _mode = note_writer.read_cell(rows[index], field, keys)
        if not ok or values_equal(incoming, pushed):
            return
        note_writer.write_cell(rows[index], field, pushed, keys)
        restored.add(table)
        kept.append({"table": table, "row": label, "period": period, "field": field, "kind": kind,
                     "pushed": pushed, "incoming": incoming})

    for cell in cells:
        restore(*cell, kind="cell")
    for table, index, field, period, label, pushed in totals:
        if table not in data_tables:  # 合计行兜底写入的科目合计
            restore(table, index, field, period, label, pushed, kind="fallback_total")
    for table, index, field, period, label, _pushed in totals:
        if table in data_tables and table in restored:  # 推送按本表重算的合计：恢复了数据格才重算
            rows, keys = sub[table], _value_keys(table_data, table)
            ok, incoming, _mode = note_writer.read_cell(rows[index], field, keys)
            total = note_writer.total_formula(rows, index, field, keys)
            # 上方各行这一列都没有数 ⇒ 不重算（与 ``_push_note_total`` 同口径，不写 0）
            if ok and total is not None and not values_equal(incoming, total):
                note_writer.write_cell(rows[index], field, total, keys)
                kept.append({"table": table, "row": label, "period": period, "field": field, "kind": "total",
                             "pushed": total, "incoming": incoming})
    return kept
