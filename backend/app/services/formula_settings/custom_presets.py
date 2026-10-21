"""自定义公式预设改存数据库（R14.3，design §16.5）。

* 存储：事务所级公式模板「自定义公式预设」（share_scope=firm，域 ``preset``，公式位 ``{page_key}|{target_cell}``），
  模板行定义 = 预设条目。不再写代码仓库里的 ``formula_custom_presets.json``（该文件只读兼容，空则无）。
  这个模板只是存储：状态 archived（不能订阅），不出现在模板列表里。
* admin 直接写；其他可写角色（合伙人 / 签字合伙人）提交全局候选（``formula_publish`` status=pending、
  域 ``preset``），admin 在全局设置页审核通过后写入。
* 读取：``preset_library`` 进程内缓存（数据库 > 旧文件 > 基线 seed > 收敛源，去重首个赢 ⇒ 自定义优先的
  口径不变）。写入后本进程立即刷新；各工作进程启动时加载，之后读预设库时缓存超过
  :data:`REFRESH_SECONDS` 秒就后台补刷（多进程最迟约一分钟一致；不常驻后台循环）。
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formula_setting_models import FormulaPublish, FormulaSetting, FormulaTemplate
from app.services.formula_management.preset_library import (
    PresetEntry,
    set_db_custom_entries,
    set_db_custom_refresher,
)
from app.services.formula_settings.audit import audit_global

logger = logging.getLogger(__name__)
DOMAIN = "preset"
TEMPLATE_NAME = "自定义公式预设"
REFRESH_SECONDS = 60
_FIELDS = ("page_key", "target_cell", "expression", "formula_type", "refs", "description", "variant")
_state: dict[str, Any] = {"loaded_at": float("-inf"), "inflight": False}


def slot_of(entry: PresetEntry) -> str:
    return f"{entry.page_key}|{entry.target_cell}"


def _payload(entry: PresetEntry) -> dict[str, Any]:
    d = entry.to_dict()
    d["source"] = "custom"  # 隔离来源标注
    return d


def entry_of(d: Mapping[str, Any]) -> PresetEntry:
    return PresetEntry(**{k: d.get(k) for k in _FIELDS if k in d} | {"source": "custom",
                                                                    "refs": list(d.get("refs") or []),
                                                                    "description": d.get("description") or ""})


def is_store(tpl: FormulaTemplate) -> bool:
    return DOMAIN in (tpl.domains or [])


async def preset_template(db: AsyncSession, *, create: bool = False,
                          user_id: uuid.UUID | None = None) -> FormulaTemplate | None:
    rows = (await db.execute(sa.select(FormulaTemplate).where(
        FormulaTemplate.name == TEMPLATE_NAME, FormulaTemplate.share_scope == "firm",
        FormulaTemplate.is_deleted == sa.false()).order_by(FormulaTemplate.created_at))).scalars().all()
    tpl = next((t for t in rows if is_store(t)), None)
    if tpl is None and create:
        now = datetime.now(timezone.utc)
        tpl = FormulaTemplate(id=uuid.uuid4(), name=TEMPLATE_NAME, description="公式预设库的自定义预设（数据库存储）",
                              share_scope="firm", owner_user_id=user_id, applicable_scope="", domains=[DOMAIN],
                              version=1, status="archived", created_by=user_id, updated_by=user_id,
                              created_at=now, updated_at=now)
        db.add(tpl)
        await db.flush()
    return tpl


async def _rows(db: AsyncSession, tpl: FormulaTemplate) -> dict[str, FormulaSetting]:
    rows = (await db.execute(sa.select(FormulaSetting).where(
        FormulaSetting.layer == "template", FormulaSetting.template_id == tpl.id, FormulaSetting.domain == DOMAIN,
        FormulaSetting.is_deleted == sa.false()))).scalars().all()
    return {r.slot_key: r for r in rows}


async def load_entries(db: AsyncSession) -> list[PresetEntry]:
    tpl = await preset_template(db)
    if tpl is None:
        return []
    return [entry_of(r.definition or {}) for _, r in sorted((await _rows(db, tpl)).items())]


async def refresh_cache(db: AsyncSession) -> int:
    entries = await load_entries(db)
    set_db_custom_entries(entries)
    _state["loaded_at"] = time.monotonic()
    return len(entries)


async def upsert(db: AsyncSession, entries: list[PresetEntry], *, user_id: uuid.UUID | None,
                 note: str | None = None) -> dict[str, int]:
    """幂等写入（同 ``page_key + target_cell`` 覆盖）；只 flush，调用方 commit 后 :func:`refresh_cache`。"""
    tpl = await preset_template(db, create=True, user_id=user_id)
    existing = await _rows(db, tpl)
    stats = {"inserted": 0, "updated": 0}
    now = datetime.now(timezone.utc)
    for entry in entries:
        slot, payload = slot_of(entry), _payload(entry)
        row = existing.get(slot)
        if row is None:
            row = FormulaSetting(id=uuid.uuid4(), domain=DOMAIN, layer="template", scope="", template_id=tpl.id,
                                 slot_key=slot, slot_label=f"{entry.page_key} {entry.target_cell}", definition=payload,
                                 version=1, created_by=user_id, updated_by=user_id, created_at=now, updated_at=now)
            db.add(row)
            existing[slot] = row
            stats["inserted"] += 1
        elif row.definition != payload:
            row.definition, row.version, row.updated_by, row.updated_at = payload, row.version + 1, user_id, now
            stats["updated"] += 1
    if stats["inserted"] or stats["updated"]:
        tpl.version, tpl.updated_by, tpl.updated_at = tpl.version + 1, user_id, now
        await db.flush()
        await audit_global(db, user_id=user_id, domain=DOMAIN, scope="", action="formula.custom_preset_saved",
                           resource_id=tpl.id, details={"template_id": str(tpl.id), "note": note or "",
                                                        "slots": [slot_of(e) for e in entries], **stats})
    return {**stats, "total": len(existing)}


async def submit_candidate(db: AsyncSession, entries: list[PresetEntry], *, user_id: uuid.UUID | None,
                           note: str | None = None) -> FormulaPublish:
    tpl = await preset_template(db)
    current = await _rows(db, tpl) if tpl is not None else {}
    row = FormulaPublish(id=uuid.uuid4(), domain=DOMAIN, scope="", target="global", source="candidate",
                         status="pending", published_by=user_id, note=note or "自定义公式预设候选", summary={},
                         change_set=[{"slot_key": slot_of(e), "label": f"{e.page_key} {e.target_cell}",
                                      "old": dict(current[slot_of(e)].definition) if slot_of(e) in current else None,
                                      "new": _payload(e)} for e in entries])
    db.add(row)
    await db.flush()
    await audit_global(db, user_id=user_id, domain=DOMAIN, scope="", action="formula.custom_preset_candidate",
                       resource_id=row.id, details={"publish_id": str(row.id), "slots": [slot_of(e) for e in entries]})
    return row


async def approve_candidate(db: AsyncSession, row: FormulaPublish, *, user_id: uuid.UUID | None) -> dict[str, int]:
    return await upsert(db, [entry_of(c.get("new") or {}) for c in (row.change_set or [])], user_id=user_id,
                        note=f"审核通过候选 {row.id}")


# ── 多进程缓存（读时按时效补刷，不常驻后台循环） ─────────────────────────────


async def _refresh_once() -> None:
    from app.core.database import async_session

    try:
        async with async_session() as db:
            await refresh_cache(db)
    except Exception as exc:  # noqa: BLE001 —— 表未就绪等：沿用上次缓存，过时效再试
        logger.warning("自定义公式预设缓存刷新失败（沿用上次）：%s", exc)
    finally:
        _state["inflight"] = False
        _state["loaded_at"] = time.monotonic()


def schedule_refresh(*, force: bool = False) -> bool:
    """缓存过时效（或 ``force``）且当前有运行中的事件循环时，后台补刷一次；不阻塞调用方。"""
    if _state["inflight"] or (not force and time.monotonic() - _state["loaded_at"] < REFRESH_SECONDS):
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    _state["inflight"] = True
    loop.create_task(_refresh_once(), name="formula-custom-presets-refresh")
    return True


def start_refresher() -> bool:
    """启动时调用：登记读时补刷钩子并立即加载一次。"""
    set_db_custom_refresher(schedule_refresh)
    return schedule_refresh(force=True)
