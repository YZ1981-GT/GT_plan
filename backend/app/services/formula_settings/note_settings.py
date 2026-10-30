"""附注域（design §12 note，tasks 6.2）：全局层与本项目层都在 ``formula_setting``（全局按模板类型 soe / listed）。

* 公式位 ``{note_section}|{target}``；target 与附注公式弹窗一致（单元格 ``行:列``，或合计行等标识）。
* 每张附注表自带的模板公式（``table_data._formulas``，按表结构生成）仍是最底层，由执行器合并；
  全局 / 本项目两层的有效集合物化到 ``table_data._user_formulas``（执行器按目标单元格「用户集优先」），
  执行器不改。物化时机：保存本章节、变更传播（全局发布 / 处理待确认 / 应用到项目…）、执行附注公式前。
* 停用只对全局层的公式位有意义：模板公式按表结构生成，在这里停用后执行器仍按模板公式算（与原弹窗一致），
  列表也如实显示模板公式。
* 项目层按项目，不分年度：同一项目各年度的同一章节共用一套适配。
* 旧数据：未物化过的附注若已有 ``_user_formulas``（旧弹窗保存的用户集），首次物化前导入本项目层
  （与该表模板公式相同的不算适配）。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.report_models import DisclosureNote
from app.services.formula_settings.definitions import is_effectively_disabled, same_exec
from app.services.formula_settings.effective import LAYER_LABELS, EffectiveSlot, effective_slots
from app.services.formula_settings.setting_sets import replace_set, version_token
from app.services.formula_settings.stores import get_store

logger = logging.getLogger(__name__)
DOMAIN = "note"
USER_KEY = "_user_formulas"
#: 物化标记：有它说明 ``_user_formulas`` 由本模块按有效集合写入（不是旧弹窗保存的用户集）
MARK = "_user_formulas_origin"
MARK_VALUE = "formula_settings"
_CATEGORIES = ("auto_calc", "logic_check", "reasonability")


def note_slot(section: str, target: str) -> str:
    return f"{section}|{target}"


def _target(rec: Mapping[str, Any]) -> str:
    """目标单元格统一成 ``formula_key`` 写法（``t0:1:2`` ≡ ``1:2``），同一格不会因写法不同成两个公式位。"""
    from app.services.note_formula_tables import formula_key, parse_formula_key

    raw = str(rec.get("target") or rec.get("target_cell") or "").strip()
    parsed = parse_formula_key(raw)
    return formula_key(*parsed) if parsed else raw


def definition_of(rec: Mapping[str, Any]) -> dict[str, Any]:
    expr = rec.get("formula") if rec.get("formula") is not None else rec.get("expression")
    category = rec.get("category") or "auto_calc"
    return {"formula": str(expr or "").strip(), "category": category if category in _CATEGORIES else "auto_calc",
            "description": rec.get("description") or "", "source": rec.get("source") or "",
            "type": rec.get("type") or ""}


def _record(target: str, definition: Mapping[str, Any], layer: str) -> dict[str, Any]:
    d = definition_of(definition)
    return {"target": target, **d, "layer": layer}


def _presets(note: DisclosureNote | None) -> dict[str, dict]:
    from app.services.note_formula_service import preview_records

    if note is None:
        return {}
    return {r["target"]: r for r in preview_records(note.table_data, note.note_section) if r.get("target")}


async def _notes(db: AsyncSession, project_id: uuid.UUID, sections: Iterable[str] | None = None,
                 year: int | None = None) -> list[DisclosureNote]:
    q = sa.select(DisclosureNote).where(DisclosureNote.project_id == project_id,
                                        DisclosureNote.is_deleted == sa.false())
    if sections is not None:
        q = q.where(DisclosureNote.note_section.in_(sorted(set(sections))))
    if year is not None:
        q = q.where(DisclosureNote.year == year)
    return list((await db.execute(q)).scalars().all())


async def _section_slots(db: AsyncSession, project_id: uuid.UUID, section: str) -> dict[str, EffectiveSlot]:
    prefix = f"{section}|"
    return {k: e for k, e in (await effective_slots(db, DOMAIN, project_id)).items() if k.startswith(prefix)}


async def _import_legacy(db: AsyncSession, project_id: uuid.UUID, notes: list[DisclosureNote],
                         user_id: uuid.UUID | None) -> int:
    """旧弹窗保存的 ``_user_formulas``（未物化过）→ 本项目层。已有本项目行的公式位不覆盖。"""
    legacy = [n for n in notes if isinstance(n.table_data, dict) and n.table_data.get(MARK) != MARK_VALUE
              and isinstance(n.table_data.get(USER_KEY), list) and n.table_data.get(USER_KEY)]
    if not legacy:
        return 0
    store = get_store(DOMAIN)
    existing = set(await store.list_project(db, project_id))
    imported = 0
    for note in legacy:
        presets = _presets(note)
        for rec in note.table_data.get(USER_KEY) or []:
            if not isinstance(rec, dict):
                continue
            target, d = _target(rec), definition_of(rec)
            key = note_slot(note.note_section, target)
            if not target or not d["formula"] or key in existing:
                continue
            if target in presets and same_exec(DOMAIN, d, definition_of(presets[target])):
                continue
            await store.write_project(db, project_id, key, definition=d, base_definition=None, base_version=None,
                                      pinned=False, base_origin=None, base_template_id=None, user_id=user_id,
                                      label=f"{note.note_section} {target}")
            existing.add(key)
            imported += 1
    return imported


async def materialize(db: AsyncSession, project_id: uuid.UUID, sections: Iterable[str] | None = None) -> int:
    """把有效集合（全局 + 本项目适配，剔除停用）写进这些章节各年度附注的 ``_user_formulas``。返回改动的附注数。

    系统路径：不写编辑人（不是人工编辑附注内容）。只 flush。
    """
    notes = await _notes(db, project_id, sections)
    if not notes:
        return 0
    await _import_legacy(db, project_id, notes, None)
    wanted: dict[str, list[dict]] = {}
    for key, e in (await effective_slots(db, DOMAIN, project_id)).items():
        section, _, target = key.partition("|")
        if e.definition is not None and not is_effectively_disabled(DOMAIN, e.definition):
            wanted.setdefault(section, []).append(_record(target, e.definition, e.layer))
    changed = 0
    for note in notes:
        if not isinstance(note.table_data, dict):
            continue
        td = dict(note.table_data)
        records = sorted(wanted.get(note.note_section, []), key=lambda r: r["target"])
        if td.get(MARK) == MARK_VALUE and td.get(USER_KEY) == records:
            continue
        if not records and not td.get(USER_KEY) and td.get(MARK) is None:
            continue  # 从没有过公式设置：不动
        td[USER_KEY], td[MARK] = records, MARK_VALUE
        note.table_data = td
        flag_modified(note, "table_data")
        changed += 1
    if changed:
        await db.flush()
    return changed


async def materialize_quietly(db: AsyncSession, project_id: uuid.UUID, sections: Iterable[str]) -> None:
    """执行附注公式前补物化（新建的附注还没写过）；失败不阻断执行（保存点隔离）。"""
    try:
        async with db.begin_nested():
            await materialize(db, project_id, list(sections))
    except Exception as exc:  # noqa: BLE001
        logger.warning("附注有效公式物化失败，按已存公式执行 project=%s: %s", project_id, exc)


async def list_section(db: AsyncSession, project_id: uuid.UUID, year: int, section: str) -> dict[str, Any]:
    """章节有效公式集（本项目 > 全局 > 该表模板公式）+ 载入版本令牌 + 目标清单（逐表行 / 列名，弹窗选目标用）。

    每条带 ``target_label``「表名 · 行名 · 列名」；按（表, 行, 列）排序。
    """
    from app.services.note_formula_service import target_sort_key
    from app.services.note_formula_tables import describe_target, formula_targets, formula_view

    note = next(iter(await _notes(db, project_id, [section], year)), None)
    presets = _presets(note)
    out = {t: {**_record(t, r, "preset"), "slot_key": note_slot(section, t), "pending": False}
           for t, r in presets.items()}
    eff = await _section_slots(db, project_id, section)
    for key, e in eff.items():
        target = key.partition("|")[2]
        if e.definition is None or is_effectively_disabled(DOMAIN, e.definition):
            continue  # 停用 ⇒ 执行器按模板公式算（若有），列表如实显示模板公式
        out[target] = {**_record(target, e.definition, e.layer), "slot_key": key, "pending": e.pending}
    catalog = formula_targets(formula_view(note.table_data)) if note is not None else []
    for rec in out.values():
        rec["layer_label"] = LAYER_LABELS.get(rec["layer"], rec["layer"])
        rec["target_label"] = describe_target(None, rec["target"], catalog)
    loaded = {note_slot(section, t): None for t in presets}
    loaded.update({k: version_token(e) for k, e in eff.items()})
    return {"formulas": sorted(out.values(), key=target_sort_key), "loaded": loaded, "targets": catalog}


async def target_problems(db: AsyncSession, project_id: uuid.UUID, year: int, section: str,
                          formulas: list[dict]) -> list[dict[str, str]]:
    """保存前校验目标单元格（有公式却没选目标 / 不是单元格 / 超出表格）→ ``[{target, message}]``。

    原先没有目标的公式被当空行静默丢掉、弹窗照样提示「已保存」（spec note-pull-header-formula-closure F7）。
    章节不存在时不在这里报（保存时 404）。
    """
    from app.services.note_formula_tables import formula_view, target_issues

    note = next(iter(await _notes(db, project_id, [section], year)), None)
    return target_issues(formula_view(note.table_data), formulas) if note is not None else []


async def save_section(db: AsyncSession, project_id: uuid.UUID, year: int, section: str, formulas: list[dict], *,
                       loaded: Mapping[str, str | None] | None, user_id: uuid.UUID | None) -> dict[str, Any]:
    """保存章节公式集（整表）：差量写本项目适配 → 物化。返回 ``{formulas, loaded, events}``。只 flush。"""
    note = next(iter(await _notes(db, project_id, [section], year)), None)
    if note is None:
        raise ValueError(f"附注章节不存在: {section}")
    await _import_legacy(db, project_id, [note], user_id)
    presets = _presets(note)
    eff = await _section_slots(db, project_id, section)
    desired: dict[str, dict] = {}
    for rec in formulas:
        if not isinstance(rec, dict):
            continue
        target, d = _target(rec), definition_of(rec)
        if not target or not d["formula"]:
            continue  # 空行过滤（同旧行为）
        key = note_slot(section, target)
        if key not in eff and target in presets and same_exec(DOMAIN, d, definition_of(presets[target])):
            continue  # 与该表模板公式相同、且没有全局 / 本项目定义：不是适配
        desired[key] = {"definition": d, "label": f"{section} {target}"}
    result = await replace_set(db, domain=DOMAIN, project_id=project_id, desired=desired,
                               loaded=dict(loaded) if loaded is not None else None, user_id=user_id,
                               source="project_edit", prefix=f"{section}|")
    await materialize(db, project_id, [section])
    listing = await list_section(db, project_id, year, section)
    return {**listing, "events": result["events"]}
