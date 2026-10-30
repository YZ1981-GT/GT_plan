"""附注单元格最终来源诊断（只读；spec note-chain-followup-optimizations R2 / ADR-3）。

回答「这一格现在的数是谁写的、还有谁会写、谁和谁对不上」。只 select：不写库、不物化公式设置、不执行公式，章节数据深拷贝后
在副本上判。坐标两种：投影表（底稿来源）传 ``sub_table_key`` + 来源行号 + 业务列键；存储表传表序号 + 行 + 列（列不含标签列）。

判定与写入方的实际行为一一对应（刷新顺序：离屏同步 → 公式推送 → 模板取数重算 → 附注公式，后写的为准）：

1. 人工 / 锁定格：推送、公式、刷新都不写（投影表只有来源行还按位置存时才有标记，``view_cell_mode`` 与推送同口径）；
2. 附注公式（``auto_calc``）：用户公式（本项目 / 全局…）照常写；预设公式在存储表上写，在投影表上只补空格；
3. 模板取数（``_cell_meta.binding_id``，存储表）：刷新按绑定重算；
4. 公式推送：推送状态 ``note://章节/表/行.期间`` 反解到这一格（与 ``note_push_ownership`` 同一套找表 / 找行），当前值等于
   上次推送值才算推送写的；同一期间对应多个字段的规则无法逐格还原，只列出不判定；
5. 底稿披露表同步：投影表（``sub_table_data``）；
6. 其余：模板生成 / 编辑器录入。

整节人工覆盖（``_manual_override``）挡推送与同步，不挡附注公式（与执行器一致）。表内公式按当前各格的值在副本上求值核实；
含跨表取数的标「未核实」（诊断不预载试算表 / 报表）。
"""
from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["diagnose_cell"]

FINAL_LABELS: dict[str, str] = {
    "manual": "人工填写",
    "locked": "已锁定",
    "section_override": "整节人工覆盖",
    "user_formula": "用户公式",
    "preset_formula": "预设公式",
    "stored_formula": "章节存的旧公式",
    "binding": "模板取数",
    "push": "公式推送",
    "workpaper_sync": "底稿披露表同步",
    "entry": "模板生成 / 编辑器录入",
}


def _num(value: Any) -> str:
    from app.services.consol_note_table_totals import to_decimal

    d = to_decimal(value)
    return "空" if d is None else f"{d:,.2f}"


def _resolve(tables: dict[int, dict], catalog: dict[int, dict], *, table_index: int, row: int, col: int,
             sub_table_key: str | None, value_key: str | None) -> tuple[int, int, int] | str:
    """请求坐标 → 显示视图坐标 ``(表, 行, 列)``；定位不到返回中文原因。"""
    from app.services.note_sub_table_projector import projected_value_keys

    t, r, c = table_index, row, col
    if sub_table_key:
        t = next((i for i, tb in tables.items() if tb.get("_source_sub_table_key") == sub_table_key), -1)
        if t < 0:
            return f"章节显示的表里没有底稿子表「{sub_table_key}」"
        indexes = tables[t].get("_source_row_indexes") or []
        if row not in indexes:
            return f"底稿子表「{sub_table_key}」第 {row + 1} 行不在显示的表里（空的可扩位行不显示）"
        r = indexes.index(row)
        if value_key:
            keys = projected_value_keys(tables[t])
            if value_key not in keys:
                return f"底稿子表「{sub_table_key}」没有「{value_key}」列"
            c = keys.index(value_key)
    if t not in tables:
        return f"章节没有第 {t + 1} 张表"
    rows = tables[t].get("rows") if isinstance(tables[t].get("rows"), list) else []
    if not (0 <= r < len(rows) and isinstance(rows[r], dict)):
        return f"「{catalog[t]['name']}」没有第 {r + 1} 行"
    if not 0 <= c < len(catalog[t]["columns"]):
        return f"「{catalog[t]['name']}」没有第 {c + 1} 个数据列"
    return t, r, c


def _formula_fact(td: dict, view: Any, t: int, r: int, c: int, rows: list, value: Any) -> dict[str, Any] | None:
    """这一格的附注公式（与执行器同一套合并：模板层 ∪ ``_user_formulas``，同目标用户集优先）+ 按当前值核算。"""
    from app.services.formula_settings.effective import LAYER_LABELS
    from app.services.note_formula_generator import _merge_formula_sets, _same_amount, _user_formula_to_def
    from app.services.note_formula_tables import CROSS_REF_RE, evaluate, formula_key, section_preset_formulas

    stored = td.get("_formulas")
    use_stored = isinstance(stored, dict) and bool(stored) and view is td
    template = stored if use_stored else section_preset_formulas(view)[0]
    user_list = td.get("_user_formulas") if isinstance(td.get("_user_formulas"), list) else []
    user = {conv[0]: rec for rec in user_list if (conv := _user_formula_to_def(rec))}
    key = formula_key(t, r, c)
    fdef = _merge_formula_sets(template, user_list).get(key)
    if fdef is None:
        return None
    kind = "user_formula" if key in user else ("stored_formula" if use_stored else "preset_formula")
    layer = str(user[key].get("layer") or "project") if key in user else "preset"
    expression = str(fdef.get("expression") or "")
    category = str(fdef.get("category") or "auto_calc")
    fact: dict[str, Any] = {"kind": kind, "label": FINAL_LABELS[kind], "target": key, "layer": layer,
                            "layer_label": LAYER_LABELS.get(layer, layer), "expression": expression,
                            "description": fdef.get("description") or "", "category": category}
    if category != "auto_calc":
        fact["check"] = {"status": "audit", "message": "审核类公式，不回填单元格"}
    elif CROSS_REF_RE.search(expression):
        fact["check"] = {"status": "unverified", "message": "含跨表取数，诊断不代入试算表 / 报表数据，未核实"}
    else:
        result, reason = evaluate(expression, rows)
        if result is None:
            fact["check"] = {"status": "no_value", "message": f"按当前各格取不到值，执行时不写：{reason}"}
        else:
            new = float(result)
            same = _same_amount(value, new)
            fact["check"] = {"status": "match" if same else "differs", "value": new,
                             "message": f"按当前各格算得 {_num(new)}，{'与当前值一致' if same else f'当前值 {_num(value)}'}"}
    return fact


async def _push_facts(db: AsyncSession, project_id: UUID, year: int, section: str, td: dict,
                      cell_rows: list | None, cell_row: int, col: int, value: Any) -> list[dict[str, Any]]:
    """推送状态里写这一格的条目：``note://`` 地址按推送同一套找表 / 找行反解，再按规则字段对列。"""
    from app.models.formula_push_models import FormulaPushState
    from app.services.formula_push import note_writer
    from app.services.formula_push.policy import values_equal
    from app.services.formula_settings.push_settings import effective_push_rules
    from app.services.note_push_ownership import _locate, parse_note_addr

    if cell_rows is None:
        return []
    states = list((await db.execute(sa.select(FormulaPushState).where(
        FormulaPushState.project_id == project_id, FormulaPushState.year == year,
        FormulaPushState.domain == "note", FormulaPushState.note_section == section,
    ))).scalars().all())
    if not states:
        return []
    rules, _issues = await effective_push_rules(db, project_id)
    rule_of = {rule.rule_id: rule for rule in rules}
    out: list[dict[str, Any]] = []
    for state in states:
        parsed = parse_note_addr(state.addr_id)
        if parsed is None:
            continue
        _sec, table_name, label, period = parsed
        located, _why = note_writer.locate_table(td, table_name, exact=".note.subtable_" in state.rule_id)
        if located is None or located.rows is not cell_rows or _locate(located.rows, label) != cell_row:
            continue
        cell_key = located.value_keys[col] if col < len(located.value_keys) else None
        rule = rule_of.get(state.rule_id)
        if rule is not None:
            fields = [f for f in rule.target.fields if note_writer.NOTE_FIELDS.get(f, ("", ""))[1] == period]
            if cell_key not in fields:
                continue  # 这条规则写的是这一行的别的列
            ambiguous = len(fields) != 1
        elif note_writer.NOTE_FIELDS.get(str(cell_key), ("", ""))[1] != period:
            continue
        else:
            ambiguous = True
        try:
            wp_code = rule.wp_code if rule is not None else None
        except IndexError:
            wp_code = None
        pushed = state.last_pushed_value
        out.append({
            "rule_id": state.rule_id, "wp_code": wp_code, "rule_status": rule.status if rule is not None else "deleted",
            "description": rule.description if rule is not None else "", "addr_id": state.addr_id,
            "source_formula": rule.source.display_formula if rule is not None else "",
            "state": state.state, "last_pushed_value": pushed, "last_formula_value": state.last_formula_value,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None, "ambiguous": ambiguous,
            "matches_current": None if pushed is None else bool(values_equal(value, pushed)),
        })
    return out


async def _sync_fact(db: AsyncSession, td: dict, note: Any) -> dict[str, Any]:
    from app.models.workpaper_models import WorkingPaper, WpIndex

    wp_id = td.get("_last_sync_wp_id")
    wp_code = None
    if wp_id:
        try:
            wp_code = (await db.execute(
                sa.select(WpIndex.wp_code).join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
                .where(WorkingPaper.id == UUID(str(wp_id)))
            )).scalar_one_or_none()
        except ValueError:
            wp_code = None
    return {"source": td.get("_source"), "wp_id": str(wp_id) if wp_id else None, "wp_code": wp_code,
            "sheet": td.get("_last_sync_sheet"), "synced_at": td.get("_last_sync_at"),
            "note_last_writer": getattr(note, "last_sync_source", None)}


def _decide(*, mode: str, projected: bool, value: Any, formula: dict | None, binding: dict | None,
            pushes: list[dict], section_locked: bool, sync: dict) -> tuple[dict, list[dict], list[dict]]:
    """``(最终来源, 逐层说明, 冲突)``：层级顺序与写入方的实际行为一致（见模块说明）。"""
    steps: list[dict[str, Any]] = []
    conflicts: list[dict[str, str]] = []
    final: dict[str, Any] | None = None

    def take(kind: str, detail: str) -> None:
        nonlocal final
        final = {"kind": kind, "label": FINAL_LABELS[kind], "detail": detail}

    def step(kind: str, label: str, status: str, detail: str) -> None:
        steps.append({"kind": kind, "label": label, "status": status, "detail": detail})

    if mode in ("manual", "locked"):
        take(mode, "推送、公式、刷新都不改写这一格")
        step("cell_mode", "单元格模式", "final", FINAL_LABELS[mode])
    else:
        step("cell_mode", "单元格模式", "inactive", "自动：推送 / 公式 / 刷新可以写")

    blank = value is None or value == ""
    if formula is None:
        step("formula", "附注公式", "inactive", "这一格没有附注公式")
    else:
        check, status = formula.get("check") or {}, "inactive"
        result = check.get("status")
        detail = f"{formula['expression']}；{check.get('message', '')}"
        # 用户公式照常写；预设公式在存储表上写、在投影表上只补空格（执行器 ADR-2）
        writes = formula["category"] == "auto_calc" and (formula["kind"] == "user_formula" or not projected)
        if final is not None:
            status = "overridden"
        elif result == "audit":
            pass
        elif writes and result in ("match", "differs", "unverified"):
            status = "final"
            take(formula["kind"], detail)
            if result == "differs":
                conflicts.append({"kind": "formula_differs", "message": (
                    f"公式结果 {_num(check.get('value'))} 与当前值 {_num(value)} 不一致：刷新或「应用公式」后会改为公式结果")})
        elif not writes and blank and result in ("differs", "unverified"):
            status = "pending"
            detail += "；当前为空，执行公式会补上"
        elif not writes and result == "differs":
            status = "kept"
            conflicts.append({"kind": "workpaper_differs", "message": (
                f"底稿披露表的值 {_num(value)} 与预设公式结果 {_num(check.get('value'))} 不一致，保留底稿值（请核对底稿披露表）")})
        elif not writes and result == "match":
            status = "consistent"
        step("formula", f"{formula['label']}（{formula['layer_label']}）", status, detail)

    if binding and binding.get("binding_id") and not projected:
        detail = f"按模板绑定 {binding['binding_id']} 取数（刷新时重算）"
        step("binding", "模板取数", "overridden" if final is not None else "final", detail)
        if final is None:
            take("binding", detail)

    if section_locked:
        step("section_override", "整节人工覆盖", "final" if final is None else "overridden",
             "推送与底稿同步不再写本章节（附注公式照常写自动格）")
        if final is None:
            take("section_override", "推送与底稿同步不再写本章节")

    for push in pushes:
        pushed = push.get("last_pushed_value")
        detail = (f"规则 {push['rule_id']}（底稿 {push.get('wp_code') or '—'}）上次推送 {_num(pushed)}，状态 {push['state']}"
                  f"{'；规则已删除' if push['rule_status'] == 'deleted' else ''}")
        if section_locked:
            status = "blocked"
        elif push["ambiguous"] or pushed is None or push["state"] != "auto":
            status = "info"
            if push["ambiguous"]:
                detail += "；同一期间对应多个字段，推送值无法逐格还原"
        elif push["matches_current"]:
            status = "overridden" if final is not None else "final"
            if final is None:
                take("push", detail)
        else:
            status = "conflict"
            conflicts.append({"kind": "push_overwritten", "message": (
                f"公式推送写过 {_num(pushed)}，当前是 {_num(value)}（之后被同步、公式或人工改写）")})
        step("push", "公式推送", status, detail)

    if projected:
        where = f"底稿 {sync.get('wp_code') or '—'}「{sync.get('sheet') or '附注披露'}」" if sync.get("wp_id") else "底稿披露表"
        synced_at = str(sync.get("synced_at") or "")[:19].replace("T", " ")
        detail = f"{where}{'，' + synced_at + ' 同步' if synced_at else ''}"
        step("sync", "底稿披露表同步", "blocked" if section_locked else ("overridden" if final else "final"), detail)
        if final is None:
            take("workpaper_sync", detail)
    if final is None:
        take("entry", "没有取数、推送或公式记录")
    return final, steps, conflicts


async def diagnose_cell(db: AsyncSession, project_id: UUID, year: int, section: str, *, table_index: int = 0,
                        row: int = 0, col: int = 0, sub_table_key: str | None = None,
                        value_key: str | None = None) -> dict[str, Any]:
    """一格的最终来源 + 逐层说明 + 冲突；章节不存在抛 ``LookupError``，坐标定位不到回 ``{"error": ..., "message"}``。"""
    from app.models.report_models import DisclosureNote
    from app.services.formula_push.note_writer import detect_manual_override
    from app.services.note_formula_tables import (
        _source_rows, describe_target, formula_targets, formula_view, is_projected_table, iter_note_tables,
        view_cell_mode, view_cell_source,
    )

    note = (await db.execute(sa.select(DisclosureNote).where(
        DisclosureNote.project_id == project_id, DisclosureNote.year == year,
        DisclosureNote.note_section == section, DisclosureNote.is_deleted == sa.false(),
    ))).scalar_one_or_none()
    if note is None:
        raise LookupError("附注章节不存在")
    td = copy.deepcopy(note.table_data) if isinstance(note.table_data, dict) else {}
    view = formula_view(td)
    tables = dict(iter_note_tables(view))
    catalog = {entry["index"]: entry for entry in formula_targets(view)}
    loc = _resolve(tables, catalog, table_index=table_index, row=row, col=col,
                   sub_table_key=sub_table_key, value_key=value_key)
    if isinstance(loc, str):
        return {"error": "cell_not_found", "message": loc}
    t, r, c = loc
    table = tables[t]
    rows = table["rows"]
    values = rows[r].get("values") if isinstance(rows[r].get("values"), list) else []
    value = values[c] if c < len(values) else None
    projected = is_projected_table(table)
    raw, key = view_cell_source(td, table, r, c)
    if projected:
        source_key = str(table["_source_sub_table_key"])
        source_row = table["_source_row_indexes"][r]
        storage = {"kind": "sub_table", "sub_table_key": source_key, "source_row": source_row, "value_key": key,
                   "text": f"底稿子表「{source_key}」第 {source_row + 1} 行 · {key}"}
        cell_rows, cell_row = _source_rows(td, source_key), source_row
    else:
        storage = {"kind": "table", "table_index": t, "row": r, "col": c,
                   "text": f"附注表格「{catalog[t]['name']}」第 {r + 1} 行第 {c + 1} 列"}
        cell_rows, cell_row = rows, r
    meta_row = raw if projected else rows[r]
    meta = (meta_row or {}).get("_cell_meta") if isinstance((meta_row or {}).get("_cell_meta"), dict) else {}
    binding = meta.get(str(c)) if isinstance(meta.get(str(c)), dict) else None
    mode = view_cell_mode(td, table, r, c)
    formula = _formula_fact(td, view, t, r, c, rows, value)
    pushes = await _push_facts(db, project_id, year, section, td, cell_rows, cell_row, c, value)
    sync = await _sync_fact(db, td, note)
    section_locked = detect_manual_override(td)
    final, steps, conflicts = _decide(mode=mode, projected=projected, value=value, formula=formula, binding=binding,
                                      pushes=pushes, section_locked=section_locked, sync=sync)
    target = (formula or {}).get("target") or (f"{r}:{c}" if t == 0 else f"t{t}:{r}:{c}")
    return {
        "section": section, "target": target, "table_index": t, "row": r, "col": c,
        "table_name": catalog[t]["name"], "row_label": catalog[t]["rows"][r], "column_label": catalog[t]["columns"][c],
        "target_label": describe_target(view, target, list(catalog.values())), "value": value,
        "projected": projected, "storage": storage, "mode": mode,
        "binding": {k: binding.get(k) for k in ("binding_id", "semantic", "unbound", "computed_at") if k in binding}
        if binding else None,
        "formula": formula, "pushes": pushes, "sync": sync if projected else None,
        "section_manual_override": section_locked, "final": final, "steps": steps, "conflicts": conflicts,
    }
