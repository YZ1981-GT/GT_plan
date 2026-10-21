"""项目「公式历史」一键回滚（R9.3）：按历史条目定位公式位，经本项目适配写回；定位不到 404。

定位顺序：条目自带 ``domain`` + ``slot_key``（本 spec 写的条目）→ 条目对象 id 指向的报表配置行
（旧 ``update_config`` 条目）→ 报表域按行次在本项目有效配置里唯一匹配（旧前端补记的条目）。
不再按行次 ``LIMIT 1`` 去改任意一个准则的全局行。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log_models import AuditLogEntry
from app.models.report_models import ReportConfig
from app.services.formula_settings.definitions import DOMAINS, display_formula
from app.services.formula_settings.effective import effective_slots
from app.services.formula_settings.errors import FormulaSettingError, NotFound
from app.services.formula_settings.project_ops import save_overrides
from app.services.formula_settings.stores import get_store, report_slot_key

_MODULE_TO_DOMAIN = {"report": "report", "consol": "report", "tb_detail": "tb_detail", "wp": "wp",
                     "workpaper": "wp", "note": "note", "consol_note": "consol_note"}


def _payload(entry: AuditLogEntry) -> dict[str, Any]:
    raw = entry.payload
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = {}
    return dict(raw or {})


async def _locate(db: AsyncSession, project_id: uuid.UUID, entry: AuditLogEntry,
                  payload: dict[str, Any]) -> tuple[str, str]:
    domain = payload.get("domain") or _MODULE_TO_DOMAIN.get(str(payload.get("module") or "report"))
    if domain not in DOMAINS:
        raise NotFound("无法定位这条历史对应的公式")
    slot = payload.get("slot_key")
    if slot:
        return domain, str(slot)
    if domain != "report":
        raise NotFound("无法定位这条历史对应的公式")
    if entry.object_id is not None:
        row = await db.get(ReportConfig, entry.object_id)
        if row is not None:
            std = row.applicable_standard or ""
            if std.startswith("project:") and std != f"project:{project_id}":
                raise NotFound("这条历史不属于本项目")
            return domain, report_slot_key(row.report_type, row.row_code)
    code = str(payload.get("row_code") or "")
    hits = [k for k in await effective_slots(db, "report", project_id) if k.partition(":")[2] == code]
    if len(hits) != 1:
        raise NotFound("无法定位这条历史对应的报表行（行次不存在或不唯一）")
    return domain, hits[0]


async def rollback_from_log(db: AsyncSession, *, project_id: uuid.UUID, source_log_id: str,
                            target_formula: str | None, expected_version: int | None,
                            user_id: uuid.UUID | None) -> dict[str, Any]:
    try:
        log_id = uuid.UUID(str(source_log_id))
    except (TypeError, ValueError):
        raise FormulaSettingError("缺少或无效的历史记录编号") from None
    entry = (await db.execute(sa.select(AuditLogEntry).where(AuditLogEntry.id == log_id))).scalars().first()
    payload = _payload(entry) if entry is not None else {}
    if entry is None or entry.action_type != "formula.changed" or payload.get("project_id") != str(project_id):
        raise NotFound("找不到这条公式历史")
    domain, slot = await _locate(db, project_id, entry, payload)
    if domain == "cross_check":
        raise FormulaSettingError("表间审核规则请在规则列表中修改")
    field = "expression" if domain == "wp" else "formula"
    eff = (await effective_slots(db, domain, project_id)).get(slot)
    local = (await get_store(domain).list_project(db, project_id)).get(slot)
    version = expected_version if expected_version is not None else (local.version if local else None)
    result = await save_overrides(
        db, domain=domain, project_id=project_id, user_id=user_id, source="history_rollback", action="rollback",
        items=[{"slot_key": slot, "definition": {field: (target_formula or "").strip() or None},
                "expected_version": version}])
    return {"domain": domain, "slot_key": slot,
            "previous_formula": display_formula(domain, eff.definition) if eff is not None else "",
            "restored_formula": target_formula or "", "events": result.get("events") or []}
