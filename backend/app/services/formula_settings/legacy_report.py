"""既有报表配置写路径收口（R9，design §9）：旧端点与旧服务方法一律经同一同步内核与版本。

* ``PUT /api/report-config/{id}``：全局行 = 直接发布（全部应用 + 冲突交项目确认，source=direct_edit）；
  项目行 = 保存本项目适配（CAS 用 ``formula_version``）。结构字段（行名 / 缩进 / 合计行 / 父行）不参与版本，直接写。
* ``POST``：全局 = 新增公式位的发布；项目 = 新增本项目适配（项目独有行带结构）。
* ``DELETE``：全局 = 删除公式位的发布；项目 = 恢复为全局（删本项目适配）。
* 「同步主模板更新」：按当前全局对单项目跑内核；跟随全局的行自动更新，改过且不同的行生成待确认事项。
* 主模板候选审核通过：经全局发布（source=promote）。
只 flush，调用方 commit 后再发变更事件。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReportType, ReportConfig
from app.services.formula_settings.definitions import normalize, same_exec
from app.services.formula_settings.engine import Decisions
from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.project_ops import restore_global, save_overrides
from app.services.formula_settings.projects import ProjectInfo, get_project
from app.services.formula_settings.publish import publish_global
from app.services.formula_settings.stores import REPORT_FIELDS, get_store, report_slot_key
from app.services.formula_settings.sync import Action, Category, ConflictChoice, decide

logger = logging.getLogger(__name__)
STRUCTURE_FIELDS = ("row_name", "indent_level", "is_total_row", "parent_row_code")


def project_id_from_standard(standard: str | None) -> uuid.UUID | None:
    std = (standard or "").strip()
    if not std.startswith("project:"):
        return None
    try:
        return uuid.UUID(std.removeprefix("project:"))
    except ValueError:
        return None


def master_base(src: ReportConfig) -> dict[str, Any]:
    """以准则行（全局）为基线的列值：物化 / 克隆 / 采用全局时写入项目行。"""
    return {"base_definition": {f: getattr(src, f, None) for f in REPORT_FIELDS},
            "base_version": src.formula_version or 1, "base_origin": "global", "pinned": False}


def _formula_part(updates: Mapping[str, Any]) -> dict[str, Any]:
    return {f: updates[f] for f in REPORT_FIELDS if f in updates}


def _current(row: ReportConfig) -> dict[str, Any]:
    return {f: getattr(row, f, None) for f in REPORT_FIELDS}


async def _reload(db: AsyncSession, standard: str, report_type: Any, row_code: str) -> ReportConfig | None:
    return (await db.execute(sa.select(ReportConfig).where(
        ReportConfig.applicable_standard == standard, ReportConfig.report_type == report_type,
        ReportConfig.row_code == row_code, ReportConfig.is_deleted == sa.false(),
    ))).scalars().first()


async def update_row(db: AsyncSession, row: ReportConfig, updates: Mapping[str, Any], *,
                     user_id: uuid.UUID | None) -> dict[str, Any]:
    """旧 PUT 的收口。返回 ``{"row", "events", "publish_id"}``。"""
    slot = report_slot_key(row.report_type, row.row_code)
    std, rt, code = row.applicable_standard, row.report_type, row.row_code
    part = _formula_part(updates)
    ev = updates.get("expected_version")
    ev = int(ev) if ev is not None and str(ev).strip() != "" else None
    result: dict[str, Any] = {"events": []}
    if part and normalize("report", {**_current(row), **part}) != normalize("report", _current(row)):
        pid = project_id_from_standard(std)
        if pid is None:
            result = await publish_global(db, domain="report", scope=std, user_id=user_id, source="direct_edit",
                                          changes=[{"slot_key": slot, "definition": part, "expected_version": ev}])
        else:
            result = await save_overrides(db, domain="report", project_id=pid, user_id=user_id, source="legacy_edit",
                                          items=[{"slot_key": slot, "definition": part, "expected_version": ev}])
    fresh = await _reload(db, std, rt, code) or row
    for f in STRUCTURE_FIELDS:
        if f in updates:
            setattr(fresh, f, updates[f])
    await db.flush()
    return {"row": fresh, "events": result.get("events") or [], "publish_id": result.get("publish_id")}


async def create_row(db: AsyncSession, body: Mapping[str, Any], *, user_id: uuid.UUID | None) -> dict[str, Any]:
    """旧 POST 的收口：全局 = 新公式位发布；项目 = 本项目适配（项目独有行带结构）。"""
    std = str(body.get("applicable_standard") or "enterprise")
    try:
        rt = FinancialReportType(body["report_type"])
    except (KeyError, ValueError):
        raise FormulaSettingError("报表类型不正确") from None
    code = str(body.get("row_code") or "").strip()
    if not code:
        raise FormulaSettingError("行次编码不能为空")
    slot = report_slot_key(rt, code)
    definition = _formula_part(body) or {"formula": None}
    structure = {"row_number": body.get("row_number", 0), "row_name": body.get("row_name") or code,
                 "indent_level": body.get("indent_level", 0), "is_total_row": bool(body.get("is_total_row", False)),
                 "parent_row_code": body.get("parent_row_code")}
    ev = body.get("expected_version")
    item = {"slot_key": slot, "definition": definition, "expected_version": ev,
            "label": structure["row_name"], "structure": structure}
    pid = project_id_from_standard(std)
    if pid is None:
        result = await publish_global(db, domain="report", scope=std, changes=[item], user_id=user_id,
                                      source="direct_edit")
    else:
        result = await save_overrides(db, domain="report", project_id=pid, items=[item], user_id=user_id,
                                      source="legacy_edit")
    row = await _reload(db, std, rt, code)
    if row is None:
        raise FormulaSettingError("新增报表行失败")
    return {"row": row, "events": result.get("events") or [], "publish_id": result.get("publish_id")}


async def delete_row(db: AsyncSession, row: ReportConfig, *, user_id: uuid.UUID | None,
                     expected_version: int | None) -> dict[str, Any]:
    slot = report_slot_key(row.report_type, row.row_code)
    pid = project_id_from_standard(row.applicable_standard)
    if pid is None:
        result = await publish_global(db, domain="report", scope=row.applicable_standard, user_id=user_id,
                                      source="direct_edit",
                                      changes=[{"slot_key": slot, "definition": None,
                                                "expected_version": expected_version}])
    else:
        result = await restore_global(db, domain="report", project_id=pid, slot_keys=[slot], user_id=user_id)
    return {"events": result.get("events") or [], "publish_id": result.get("publish_id")}


async def sync_project_to_global(db: AsyncSession, *, project_id: uuid.UUID, standard: str, keep_local: bool = True,
                                 user_id: uuid.UUID | None = None) -> dict[str, Any]:
    """「同步主模板更新」（R9.2）：只处理全局相对本项目基线变过的公式位。

    跟随全局（本项目 == 基线）→ 改为当前全局；已一致 → 只更新基线；改过且不同 →
    ``keep_local`` 时生成待确认事项（不再清除过期标记了事），否则直接采用全局。
    没有本项目行的公式位本来就读全局（继承），不再复制。
    """
    from app.services.formula_settings.engine import PlanItem, apply_effect

    store = get_store("report")
    project = await get_project(db, "report", project_id) or ProjectInfo(project_id, "", "", standard)
    upstream = await store.list_global(db, standard)
    local = await store.list_project(db, project_id)
    counts = {"updated": 0, "rebased": 0, "pending": 0, "unchanged": 0}
    events: list[str] = []
    choice = ConflictChoice.ASK if keep_local else ConflictChoice.ADOPT
    for slot, lo in sorted(local.items()):
        up = upstream.get(slot)
        if up is None or (lo.base_definition is not None and lo.base_version == up.version
                          and same_exec("report", lo.base_definition, up.definition)):
            counts["unchanged"] += 1
            continue
        item = PlanItem(project=project, slot_key=slot, label=up.label, old_up=lo.base_definition,
                        old_version=lo.base_version, old_origin=lo.base_origin or "global", new_up=up.definition,
                        new_version=up.version, new_origin="global", local=lo, structure=up.structure)
        category = item.classify("report")
        if category is Category.PINNED and not keep_local:
            category = item.category = Category.CONFLICT
        effect = decide("report", category, old_upstream=item.old_up, old_version=item.old_version,
                        new_upstream=up.definition, new_version=up.version, local=lo.local_state(),
                        conflict_choice=choice)
        await apply_effect(db, store, item, effect, publish_id=None, user_id=user_id)
        if effect.action is Action.PENDING:
            counts["pending"] += 1
        elif effect.action is Action.REBASE:
            counts["rebased"] += 1
        elif effect.action is not Action.NONE:
            counts["updated"] += 1
        if effect.effective_changed:
            events.append(slot)
    await db.flush()
    return {**counts, "events": [{"project_id": str(project_id), "slot_keys": events}] if events else []}


async def approve_baseline_candidate(db: AsyncSession, *, standard: str, report_type: str, row_code: str,
                                     formula: str | None, reviewer: uuid.UUID | None,
                                     source_project_id: uuid.UUID | None, candidate_id: uuid.UUID) -> dict[str, Any]:
    """旧主模板候选审核通过 → 全局发布（source=promote）。准则行不存在时不发布（与旧行为一致）。"""
    rt = FinancialReportType(report_type)
    master = await _reload(db, standard, rt, row_code)
    if master is None:
        logger.warning("standard 级未找到 %s/%s/%s，跳过合并", standard, report_type, row_code)
        return {"events": [], "publish_id": None, "old_formula": ""}
    old_formula = master.formula or ""
    result = await publish_global(
        db, domain="report", scope=standard, user_id=reviewer, source="promote", source_project_id=source_project_id,
        decisions=Decisions(), note=f"主模板候选 {candidate_id}",
        changes=[{"slot_key": report_slot_key(rt, row_code), "definition": {"formula": formula},
                  "expected_version": master.formula_version or 1}])
    return {**result, "old_formula": old_formula}
