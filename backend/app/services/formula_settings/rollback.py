"""项目「公式历史」一键回滚（需求 13.1~13.3，ADR-FHIC-10）。

回滚从审计日志条目的 ``old_definition`` 取快照恢复，**不**从请求体取 ``target_formula``。
``expected_version`` 必填（缺则 428），不符 409。

定位顺序：条目自带 ``domain`` + ``slot_key``（本 spec 写的条目）→ 条目对象 id 指向的报表配置行
（旧 ``update_config`` 条目）→ 报表域按行次在本项目有效配置里唯一匹配（旧前端补记的条目）。
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
from app.services.formula_settings.errors import (
    FormulaSettingError, NotFound, VersionConflict, VersionRequired,
)
from app.services.formula_settings.project_ops import save_overrides
from app.services.formula_settings.stores import get_store, report_slot_key

_MODULE_TO_DOMAIN = {"report": "report", "consol": "report", "tb_detail": "tb_detail", "wp": "wp",
                     "workpaper": "wp", "note": "note", "consol_note": "consol_note", "push": "push"}


def _payload(entry: AuditLogEntry) -> dict[str, Any]:
    raw = entry.payload
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = {}
    return dict(raw or {})


async def _locate(db: AsyncSession, project_id: uuid.UUID, object_id: uuid.UUID | None,
                  payload: dict[str, Any], slot_cache: dict[str, Any] | None = None) -> tuple[str, str]:
    domain = payload.get("domain") or _MODULE_TO_DOMAIN.get(str(payload.get("module") or "report"))
    if domain not in DOMAINS:
        raise NotFound("无法定位这条历史对应的公式")
    slot = payload.get("slot_key")
    if slot:
        return domain, str(slot)
    if domain != "report":
        raise NotFound("无法定位这条历史对应的公式")
    if object_id is not None:
        row = await db.get(ReportConfig, object_id)
        if row is not None:
            std = row.applicable_standard or ""
            if std.startswith("project:") and std != f"project:{project_id}":
                raise NotFound("这条历史不属于本项目")
            return domain, report_slot_key(row.report_type, row.row_code)
    code = str(payload.get("row_code") or "")
    if slot_cache is None:
        report_keys = list(await effective_slots(db, "report", project_id))
    else:  # 列表一次请求内多条旧条目共用一次有效公式位查询
        if "report_keys" not in slot_cache:
            slot_cache["report_keys"] = list(await effective_slots(db, "report", project_id))
        report_keys = slot_cache["report_keys"]
    hits = [k for k in report_keys if k.partition(":")[2] == code]
    if len(hits) != 1:
        raise NotFound("无法定位这条历史对应的报表行（行次不存在或不唯一）")
    return domain, hits[0]


def _extract_old_definition(domain: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """从审计条目载荷提取可回滚的旧定义（ADR-FHIC-10）。

    新条目（本 spec 写的）有 ``old_definition`` 完整字典——直接用。
    旧条目只有 ``old_formula`` 显示文本——**仅报表域**可回滚（单字段），其余域判不可回滚。
    """
    full = payload.get("old_definition")
    if isinstance(full, dict):
        return dict(full)
    # 旧条目兼容：只有显示字符串
    old_text = str(payload.get("old_formula") or "").strip()
    if not old_text:
        return None
    if domain == "report":
        return {"formula": old_text}
    # 非报表域旧条目只有显示字符串，无法还原完整定义
    return None


def can_rollback(domain: str, payload: dict[str, Any]) -> tuple[bool, str]:
    """判定条目是否可回滚，返回 ``(rollbackable, blocked_reason)``。"""
    action = payload.get("action", "")
    if action == "manual_note":
        return False, "人工补记不可回滚"
    defn = _extract_old_definition(domain, payload)
    if defn is None:
        old_text = str(payload.get("old_formula") or "").strip()
        if not old_text:
            return False, "该条目没有变更前定义"
        return False, f"该条目为旧格式，{domain} 域无法从显示文本还原完整定义"
    # cross_check 新条目有 old_definition，可回滚
    return True, ""


async def current_version_for_entry(db: AsyncSession, project_id: uuid.UUID, *, object_id: uuid.UUID | None,
                                    payload: dict[str, Any],
                                    local_cache: dict[str, dict[str, Any]]) -> tuple[int | None, str]:
    """历史条目对应公式位在本项目的当前修订号，供界面回滚带 ``expected_version``（需求 13.1）。

    没有本项目适配 ⇒ 0（与 :func:`save_overrides` 的「新建须为 0 或不带」同口径）；
    定位不到公式位 ⇒ ``(None, 原因)``，调用方据此把条目判为不可回滚。
    ``local_cache`` 按域缓存本项目适配，同一次列表请求每个域只查一次。
    """
    try:
        domain, slot = await _locate(db, project_id, object_id, payload,
                                     slot_cache=local_cache.setdefault("_locate", {}))
    except NotFound as exc:
        return None, exc.message
    if domain not in local_cache:
        local_cache[domain] = await get_store(domain).list_project(db, project_id)
    local = local_cache[domain].get(slot)
    return (local.version if local is not None else 0), ""


async def rollback_from_log(db: AsyncSession, *, project_id: uuid.UUID, source_log_id: str,
                            expected_version: int | None,
                            user_id: uuid.UUID | None) -> dict[str, Any]:
    """从审计日志的 old_definition 取快照回滚（ADR-FHIC-10）。

    ``expected_version`` 必填（缺则 428），不符 409。不再从请求体取 ``target_formula``。
    """
    if expected_version is None:
        raise VersionRequired("回滚需要提供当前版本号（expected_version）")
    try:
        log_id = uuid.UUID(str(source_log_id))
    except (TypeError, ValueError):
        raise FormulaSettingError("缺少或无效的历史记录编号") from None
    entry = (await db.execute(sa.select(AuditLogEntry).where(AuditLogEntry.id == log_id))).scalars().first()
    payload = _payload(entry) if entry is not None else {}
    if entry is None or entry.action_type != "formula.changed" or payload.get("project_id") != str(project_id):
        raise NotFound("找不到这条公式历史")
    domain, slot = await _locate(db, project_id, entry.object_id, payload)

    # 从条目读取旧定义（ADR-FHIC-10）
    target_definition = _extract_old_definition(domain, payload)
    if target_definition is None:
        old_text = str(payload.get("old_formula") or "").strip()
        if not old_text:
            raise FormulaSettingError("该条目没有变更前定义，无法回滚")
        raise FormulaSettingError(f"该条目为旧格式，{domain} 域无法从显示文本还原完整定义，无法回滚")

    eff = (await effective_slots(db, domain, project_id)).get(slot)
    local = (await get_store(domain).list_project(db, project_id)).get(slot)
    current_version = local.version if local else None
    # CAS：版本不符 409
    if current_version is not None and expected_version != current_version:
        raise VersionConflict(
            f"版本冲突：期望 {expected_version}，当前 {current_version}，请刷新后重试",
            detail={"expected_version": expected_version, "current_version": current_version},
        )

    result = await save_overrides(
        db, domain=domain, project_id=project_id, user_id=user_id, source="history_rollback", action="rollback",
        items=[{"slot_key": slot, "definition": target_definition,
                "expected_version": expected_version}])
    restored_text = display_formula(domain, target_definition)
    return {"domain": domain, "slot_key": slot,
            "previous_formula": display_formula(domain, eff.definition) if eff is not None else "",
            "restored_formula": restored_text, "events": result.get("events") or []}
