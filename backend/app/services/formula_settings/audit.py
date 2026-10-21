"""公式设置留痕（R2.3 / R6.3）：全局一条（无项目维度）+ 每个受影响项目带 project_id 的公式变更。

项目条目沿用 ``formula.changed`` / ``formula_changed`` 口径，项目「公式历史」页即可查到。
单项目一次写入超过 :data:`PER_SLOT_LIMIT` 个公式位时合并为一条（明细放 ``changes``），避免哈希链逐条串行写过多。
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_log_helper import append_audit_log
from app.services.formula_settings.definitions import display_formula

PER_SLOT_LIMIT = 30
_CHANGES_CAP = 200
#: 与项目「公式历史」页的模块标签同口径（report / wp / note …）
MODULE_OF_DOMAIN = {
    "report": "report", "tb_detail": "tb_detail", "cross_check": "cross_check",
    "wp": "wp", "note": "note", "consol_note": "consol_note",
}
#: 历史页按 action 显示「修改 / 回滚」并决定能否一键回滚；具体操作记在 operation
_HISTORY_ACTION = {"rollback": "rollback"}


def slot_row_code(domain: str, slot_key: str) -> str:
    """历史页按 row_code 过滤：报表域取行次，其余域用公式位本身。"""
    if domain == "report":
        return slot_key.partition(":")[2] or slot_key
    return slot_key


def change_entry(domain: str, slot_key: str, old: dict | None, new: dict | None, **extra: Any) -> dict[str, Any]:
    return {
        "slot_key": slot_key,
        "old_formula": display_formula(domain, old) if old is not None else "",
        "new_formula": display_formula(domain, new) if new is not None else "",
        **{k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in extra.items() if v is not None},
    }


async def audit_global(db: AsyncSession, *, user_id: uuid.UUID | None, domain: str, scope: str, action: str,
                       resource_id: uuid.UUID | str, details: dict[str, Any]) -> None:
    await append_audit_log(db, {
        "user_id": user_id,
        "project_id": None,
        "action": action,
        "resource_type": "formula_setting",
        "resource_id": str(resource_id),
        "details": {"domain": domain, "scope": scope, **details},
    })


async def audit_project(db: AsyncSession, *, user_id: uuid.UUID | None, project_id: uuid.UUID, domain: str,
                        action: str, source: str, changes: list[dict[str, Any]],
                        publish_id: uuid.UUID | None = None) -> None:
    """``changes`` = :func:`change_entry` 列表；``action`` 是具体操作（sync_global / adapt / restore …）。"""
    if not changes:
        return
    module = MODULE_OF_DOMAIN.get(domain, domain)
    base = {"event_type": "formula_changed", "module": module, "domain": domain,
            "action": _HISTORY_ACTION.get(action, "update"), "operation": action,
            "source": source, "result_value": ""}
    if publish_id is not None:
        base["publish_id"] = str(publish_id)
    if len(changes) <= PER_SLOT_LIMIT:
        for ch in changes:
            await append_audit_log(db, {
                "user_id": user_id,
                "project_id": project_id,
                "action": "formula.changed",
                "resource_type": "formula_setting",
                "resource_id": str(ch.get("config_id") or ch["slot_key"]),
                "details": {**base, **ch, "row_code": slot_row_code(domain, ch["slot_key"])},
            })
        return
    await append_audit_log(db, {
        "user_id": user_id,
        "project_id": project_id,
        "action": "formula.changed",
        "resource_type": "formula_setting",
        "resource_id": str(publish_id) if publish_id else "",
        "details": {
            **base,
            "row_code": f"多处（{len(changes)}）",
            "old_formula": "",
            "new_formula": "",
            "changes": changes[:_CHANGES_CAP],
            "change_count": len(changes),
        },
    })
