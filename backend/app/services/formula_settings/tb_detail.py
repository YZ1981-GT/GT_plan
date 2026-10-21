"""试算表科目明细公式（tb_detail 域）：旧接口形状 ↔ ``formula_setting`` 公式位（R10，design §12）。

公式位：科目编码（覆盖该科目的默认 ``TB('科目','期末余额')`` 预设）；新增行 ``added:{行编码}``。
全局层作用范围恒为 ``*``（与准则无关）；默认预设由前端按科目生成，不在后端。
旧数据（``projects.wizard_state.tb_detail_formulas``）由 V199 迁入本项目层，代码不再读写 wizard_state。
"""
from __future__ import annotations

import uuid
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.setting_sets import live_slots, replace_set, version_token

DOMAIN = "tb_detail"
ADDED_PREFIX = "added:"
ITEM_FIELDS = ("row_name", "formula", "formula_category", "formula_description")


def _definition(item: Mapping[str, Any]) -> dict[str, Any]:
    d = {f: item.get(f) for f in ITEM_FIELDS}
    d["formula_category"] = d["formula_category"] or "auto_calc"  # 用户要求：分类默认为自动运算
    return d


async def load(db: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    """``{overrides, added, layers, loaded, pending}``；每项带 ``layer`` / ``pending``（R1.4）。"""
    overrides: dict[str, dict[str, Any]] = {}
    added: list[dict[str, Any]] = []
    layers: dict[str, str] = {}
    loaded: dict[str, str] = {}
    pending: list[str] = []
    for slot, e in (await live_slots(db, DOMAIN, project_id)).items():
        d = e.definition or {}
        is_added = slot.startswith(ADDED_PREFIX)
        code = slot[len(ADDED_PREFIX):] if is_added else slot
        token = version_token(e)
        item = {"row_code": code, "row_name": d.get("row_name"), "formula": d.get("formula"),
                "formula_category": d.get("formula_category") or "auto_calc",
                "formula_description": d.get("formula_description"),
                "slot_key": slot, "layer": e.layer, "pending": e.pending, "version_token": token}
        if is_added:
            added.append(item)
        else:
            overrides[code] = item
        layers[slot] = e.layer
        if e.pending:
            pending.append(slot)
        if token:
            loaded[slot] = token
    return {"overrides": overrides, "added": added, "layers": layers, "loaded": loaded, "pending": pending}


async def save(db: AsyncSession, project_id: uuid.UUID, *, overrides: Mapping[str, Mapping[str, Any]],
               added: list[Mapping[str, Any]], loaded: Mapping[str, str] | None,
               user_id: uuid.UUID | None) -> dict[str, Any]:
    desired: dict[str, dict[str, Any]] = {}
    for code, item in overrides.items():
        code = str(code).strip()
        if not code:
            raise FormulaSettingError("科目编码不能为空")
        desired[code] = {"definition": _definition(item), "label": item.get("row_name") or code}
    for item in added:
        code = str(item.get("row_code") or "").strip()
        if not code:
            raise FormulaSettingError("新增公式行缺少行编码")
        slot = ADDED_PREFIX + code
        if slot in desired:
            raise FormulaSettingError(f"新增公式行编码重复：{code}")
        desired[slot] = {"definition": _definition(item), "label": item.get("row_name") or code}
    return await replace_set(db, domain=DOMAIN, project_id=project_id, desired=desired, loaded=loaded,
                             user_id=user_id, source="tb_detail_edit")
