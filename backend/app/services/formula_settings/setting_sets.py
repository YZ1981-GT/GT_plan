"""整表替换型旧接口 → 本项目适配的差量写入（试算表科目明细 / 表间审核规则，R6 / R10）。

旧接口一次 PUT 整个集合。改存 ``formula_setting`` 后按「客户端载入时的版本令牌」求差量：

* 载入过、本次仍在且定义变了 → 保存本项目适配；
* 载入过、本次不在 → 本项目独有的删除，来自全局的写「本项目停用」；
* 本次新出现 → 新增本项目适配；
* 没载入过、本次也不在（别人在你载入之后加的）→ 不动。

版本令牌 ``L{n}`` = 本项目适配修订号，``G{n}`` = 全局版本；与当前不一致 → 409，整批不写。
已有生效条目却没带令牌 → 428（不能凭空整表覆盖别人的修改）。
"""
from __future__ import annotations

import uuid
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_settings.definitions import DISABLED_KEY, is_effectively_disabled, normalize
from app.services.formula_settings.effective import EffectiveSlot, effective_slots
from app.services.formula_settings.errors import FormulaSettingError, VersionConflict, VersionRequired
from app.services.formula_settings.project_ops import restore_global, save_overrides


def version_token(slot: EffectiveSlot | None) -> str | None:
    if slot is None:
        return None
    if slot.local is not None:
        return f"L{slot.local.version}"
    if slot.upstream is not None and slot.upstream.layer != "preset":
        return f"G{slot.upstream.version}"
    return None


def is_live(domain: str, slot: EffectiveSlot) -> bool:
    """在本项目实际生效（有定义且未停用）。"""
    return slot.definition is not None and not is_effectively_disabled(domain, slot.definition)


async def live_slots(db: AsyncSession, domain: str, project_id: uuid.UUID) -> dict[str, EffectiveSlot]:
    eff = await effective_slots(db, domain, project_id)
    return {k: e for k, e in eff.items() if is_live(domain, e)}


async def replace_set(db: AsyncSession, *, domain: str, project_id: uuid.UUID,
                      desired: Mapping[str, Mapping[str, Any]], loaded: Mapping[str, str] | None,
                      user_id: uuid.UUID | None, source: str, prefix: str = "") -> dict[str, Any]:
    """``desired`` = ``{slot_key: {"definition": {...}, "label": str}}``；只 flush。

    ``prefix``：只替换这一组公式位（如附注某章节 ``"五、1|"``）；组外的公式位不看、不动。
    """
    eff = {k: e for k, e in (await effective_slots(db, domain, project_id)).items() if k.startswith(prefix)}
    if prefix and any(not k.startswith(prefix) for k in [*desired, *(loaded or {})]):
        raise FormulaSettingError("公式位不属于本次保存的范围")
    live = {k for k, e in eff.items() if is_live(domain, e)}
    if loaded is None:
        if live:
            raise VersionRequired("请刷新后再保存：缺少载入时的版本信息")
        loaded = {}
    problems = [{"slot_key": k, "loaded": v, "current": version_token(eff.get(k))}
                for k, v in loaded.items() if v != version_token(eff.get(k))]
    if problems:
        raise VersionConflict("这些公式已被他人修改，请刷新后再保存", detail={"problems": problems})

    items: list[dict[str, Any]] = []
    removes: list[str] = []
    for slot, want in desired.items():
        e = eff.get(slot)
        definition = dict(want["definition"])
        if e is not None and slot in live and normalize(domain, e.definition) == normalize(domain, definition):
            continue
        items.append({"slot_key": slot, "definition": definition, "label": str(want.get("label") or ""),
                      "expected_version": e.local.version if e is not None and e.local is not None else None})
    for slot in loaded:
        if slot in desired or slot not in live:
            continue
        e = eff[slot]
        if e.upstream is None:
            removes.append(slot)  # 本项目独有 ⇒ 直接删
        else:  # 来自全局 ⇒ 本项目停用（全局仍在，其他项目照用）
            items.append({"slot_key": slot, "definition": {DISABLED_KEY: True},
                          "expected_version": e.local.version if e.local is not None else None})
    events: list[dict[str, Any]] = []
    if items:
        events += (await save_overrides(db, domain=domain, project_id=project_id, items=items, user_id=user_id,
                                        source=source))["events"]
    if removes:
        events += (await restore_global(db, domain=domain, project_id=project_id, slot_keys=removes,
                                        user_id=user_id,
                                        expected_versions=None))["events"]  # replace_set 已在同一事务内做过 CAS
    merged: dict[str, list[str]] = {}
    for ev in events:
        merged.setdefault(ev["project_id"], []).extend(ev["slot_keys"])
    return {"saved": len(items), "removed": len(removes),
            "events": [{"project_id": pid, "slot_keys": slots} for pid, slots in merged.items()]}
