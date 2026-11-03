"""生成计划与粗裁状态（spec trim-generation-plan-linkage R1，只读）。

生成底稿弹窗原先按业务分类勾选模板清单，和程序裁剪页只有「已裁的变灰」一条单向联系。现在弹窗只读本模块
给出的计划：按循环列出每个模板编码这次会不会生成、为什么，用户只能按循环勾选；逐个底稿的排除走裁剪页。

判定与生成接口同一来源（PG 一致性测试逐码对拍）：
- 已裁剪：``procedure_scope_retention.TrimmedScope``（与 ``load_trimmed_scope`` 同一行集合，含母码跟随下级）；
- 在回收站 / 已生成：``wp_index_states``；
- 业务分类不生成：只用于没人保存过粗裁的循环（默认方案）。保存过的循环以程序行为准：业务分类不适用但
  程序行执行的编码照常生成，标 ``category_conflict``。

「保存过粗裁」= 本项目有已消费的粗裁应用凭证（``procedure_operation_previews``，operation = trim），且其中
有该循环的粗裁条目；取最近一次的时间与操作人。follow-up R3 起由确认投影
``procedure_trim_cycle_confirmations``（``procedure_trim_confirmation``）在消费凭证的同一事务里维护，
这里只读投影；凭证仍是不可变历史真源。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance
from app.services.business_category_service import template_mappings
from app.services.procedure_catalog import (
    catalog_codes_by_cycle,
    category_lookup,
    cycle_template_items,
    project_category,
    row_origin,
)
from app.services.procedure_scope_retention import (
    TrimmedScope,
    TrimScopeUnavailable,
    normalize_code,
    wp_index_states,
)
from app.services.procedure_trim_confirmation import load_projection

#: 循环展示顺序（与程序裁剪页页签一致），其余循环按字母排在后面。
CYCLE_ORDER = "BCDEFGHIJKLMNAS"
OTHER_CYCLE = "其他"

STATE_TRIMMED = "trimmed"
STATE_IN_RECYCLE = "in_recycle"
STATE_EXISTING = "existing"
STATE_CATEGORY_EXCLUDED = "category_excluded"
STATE_TO_CREATE = "to_create"
#: 计数键（与 totals / 每个循环的 counts 同一组）。
COUNT_KEYS = ("total", STATE_TO_CREATE, STATE_EXISTING, STATE_IN_RECYCLE, STATE_TRIMMED, STATE_CATEGORY_EXCLUDED)

TRIM_NOT_INITIALIZED = "not_initialized"
TRIM_UNCONFIRMED = "unconfirmed"
TRIM_CONFIRMED = "confirmed"


class TemplateSetNotFound(LookupError):
    """所选模板集不存在（路由回 404）。"""


def cycle_sort_key(cycle: str) -> tuple[int, str]:
    pos = CYCLE_ORDER.find(cycle) if len(cycle) == 1 else -1
    return (pos if pos >= 0 else len(CYCLE_ORDER), cycle)


def code_cycle(code: str, mapping_cycle: str | None) -> str:
    if mapping_cycle:
        return mapping_cycle
    head = normalize_code(code)[:1]
    return head if head.isalpha() else OTHER_CYCLE


def _iso(at: datetime) -> str:
    """带时区的 ISO 8601（库里是 timestamptz；SQLite 测试库读出来不带时区，按 UTC）。"""
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).isoformat()


async def load_cycle_confirmations(db: AsyncSession, project_id: UUID) -> dict[str, dict[str, Any]]:
    """各循环最近一次保存粗裁：``{循环: {confirmed_at, confirmed_by}}``（没保存过的循环不在里面）。

    只读确认投影 ``procedure_trim_cycle_confirmations``（R3），不再扫描预览凭证 JSON 历史。
    读不到抛 :class:`TrimScopeUnavailable`：粗裁状态决定业务分类默认方案用不用，读不到就不能当成「没保存过」。
    """
    try:
        async with db.begin_nested():
            projection = await load_projection(db, project_id)
    except SQLAlchemyError as exc:
        raise TrimScopeUnavailable(f"读取粗裁保存记录失败：{exc}") from exc
    return {
        cycle: {"confirmed_at": _iso(row["confirmed_at"]), "confirmed_by": row["confirmed_by"]}
        for cycle, row in projection.items()
    }


async def _program_rows(db: AsyncSession, project_id: UUID) -> list[dict[str, Any]]:
    """本项目全部未删除程序行（与 ``load_trimmed_scope`` 同一行集合）；读不到抛 :class:`TrimScopeUnavailable`。"""
    stmt = sa.select(
        sa.func.coalesce(ProcedureInstance.wp_code, ProcedureInstance.procedure_code),
        ProcedureInstance.status,
        ProcedureInstance.audit_cycle,
        ProcedureInstance.procedure_name,
        ProcedureInstance.skip_reason,
        ProcedureInstance.is_custom,
        ProcedureInstance.sort_order,
    ).where(ProcedureInstance.project_id == project_id, ProcedureInstance.is_deleted == sa.false())
    try:
        async with db.begin_nested():
            rows = (await db.execute(stmt)).all()
    except SQLAlchemyError as exc:
        raise TrimScopeUnavailable(f"读取程序裁剪结果失败：{exc}") from exc
    return [
        {"code": r[0] or "", "status": r[1] or "", "cycle": r[2] or "", "name": r[3] or "",
         "skip_reason": r[4], "is_custom": bool(r[5]), "sort_order": int(r[6] or 0)}
        for r in rows
    ]


def _trim_states(rows: list[dict[str, Any]], confirmations: dict[str, dict]) -> dict[str, str]:
    cycles = {r["cycle"] for r in rows}
    return {c: (TRIM_CONFIRMED if c in confirmations else TRIM_UNCONFIRMED) for c in cycles}


async def build_scope_confirmations(db: AsyncSession, project_id: UUID) -> dict[str, Any]:
    """各循环粗裁状态（裁剪页用）：标准循环全列出，其他循环有程序行才列。"""
    rows = await _program_rows(db, project_id)
    confirmations = await load_cycle_confirmations(db, project_id)
    states = _trim_states(rows, confirmations)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["cycle"]] = counts.get(r["cycle"], 0) + 1
    cycles = sorted(set(CYCLE_ORDER) | set(states), key=cycle_sort_key)
    return {"cycles": [
        {
            "cycle": c,
            "trim_state": states.get(c, TRIM_NOT_INITIALIZED),
            "program_count": counts.get(c, 0),
            "confirmed_at": (confirmations.get(c) or {}).get("confirmed_at"),
            "confirmed_by": (confirmations.get(c) or {}).get("confirmed_by"),
        }
        for c in cycles
    ]}


async def _template_set(db: AsyncSession, template_set_id: UUID | None) -> tuple[dict | None, list[str]]:
    if template_set_id is None:
        return None, list(dict.fromkeys(str(m["wp_code"]) for m in template_mappings() if m.get("wp_code")))
    from app.models.workpaper_models import WpTemplateSet

    ts = (await db.execute(sa.select(WpTemplateSet).where(
        WpTemplateSet.id == template_set_id,
        WpTemplateSet.is_deleted == sa.false(),
    ))).scalar_one_or_none()
    if ts is None:
        raise TemplateSetNotFound(str(template_set_id))
    # 与生成接口 select_generation_codes 同一口径：按模板集顺序去重、去掉空值
    codes = list(dict.fromkeys(str(c) for c in (ts.template_codes or []) if c))
    return {"id": str(ts.id), "set_name": ts.set_name, "code_count": len(codes)}, codes


async def build_generation_plan(db: AsyncSession, project_id: UUID, template_set_id: UUID | None) -> dict[str, Any]:
    """生成计划（契约 docs/contracts/procedure-chain/generation-plan-view.schema.json ``$defs/plan``）。"""
    template_set, codes = await _template_set(db, template_set_id)
    category, defaulted = await project_category(db, project_id)
    lookup = category_lookup(category)
    rows = await _program_rows(db, project_id)
    scope = TrimmedScope.from_rows((r["code"], r["status"]) for r in rows)
    confirmations = await load_cycle_confirmations(db, project_id)
    trim_states = _trim_states(rows, confirmations)
    index_states = await wp_index_states(db, project_id, codes)
    catalog = await catalog_codes_by_cycle(db, project_id)
    mapping = {normalize_code(m.get("wp_code")): m for m in template_mappings()}

    groups: dict[str, list[dict[str, Any]]] = {}
    for code in codes:
        item = mapping.get(normalize_code(code)) or {}
        cycle = code_cycle(code, item.get("cycle"))
        verdict = scope.decided_by(code)
        applicable, reason = lookup.get(normalize_code(code), (True, ""))
        trim_state = trim_states.get(cycle, TRIM_NOT_INITIALIZED)
        in_index = index_states.get(code)
        if verdict is not None and verdict[1]:
            state = STATE_TRIMMED
        elif in_index is True:
            state = STATE_IN_RECYCLE
        elif in_index is False:
            state = STATE_EXISTING
        elif not applicable and trim_state != TRIM_CONFIRMED:
            state = STATE_CATEGORY_EXCLUDED
        else:
            state = STATE_TO_CREATE
        groups.setdefault(cycle, []).append({
            "wp_code": code,
            "wp_name": str(item.get("wp_name") or code),
            "state": state,
            "decided_by": verdict[0] if verdict else None,
            "follows_children": scope.follows_children(code),
            "category_applicable": applicable,
            "category_reason": None if applicable else (reason or None),
            "category_conflict": (not applicable) and state == STATE_TO_CREATE,
        })

    rows_by_cycle: dict[str, list[dict[str, Any]]] = {}
    for r in sorted(rows, key=lambda r: r["sort_order"]):
        rows_by_cycle.setdefault(r["cycle"], []).append(r)
    totals = dict.fromkeys(COUNT_KEYS, 0)
    cycles_out = []
    for cycle in sorted(groups, key=cycle_sort_key):
        items = groups[cycle]
        counts = dict.fromkeys(COUNT_KEYS, 0)
        counts["total"] = len(items)
        for it in items:
            counts[it["state"]] += 1
        for key in COUNT_KEYS:
            totals[key] += counts[key]
        template_codes = {normalize_code(t.get("wp_code")) for t in cycle_template_items(cycle)}
        cycles_out.append({
            "cycle": cycle,
            "trim_state": trim_states.get(cycle, TRIM_NOT_INITIALIZED),
            "confirmed_at": (confirmations.get(cycle) or {}).get("confirmed_at"),
            "confirmed_by": (confirmations.get(cycle) or {}).get("confirmed_by"),
            "counts": counts,
            "programs": [
                {
                    "code": r["code"],
                    "name": r["name"],
                    "status": r["status"],
                    "skip_reason": r["skip_reason"],
                    "origin": row_origin(r["code"], is_custom=r["is_custom"], catalog_codes=catalog.get(cycle, set()),
                                         template_codes=template_codes),
                }
                for r in rows_by_cycle.get(cycle, [])
            ],
            "items": items,
        })
    return {
        "template_set": template_set,
        "business_category": {"code": category, "defaulted": defaulted},
        "totals": totals,
        "cycles": cycles_out,
    }
