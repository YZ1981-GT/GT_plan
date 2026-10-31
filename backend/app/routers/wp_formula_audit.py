"""底稿公式 CRUD 审计日志写入（从 wp_formula.py 拆出，任务 26 行数门处理）。"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User

logger = logging.getLogger(__name__)


async def write_wp_formula_audit(
    db: AsyncSession,
    *,
    user: User,
    project_id: UUID,
    wp_code: str | None,
    target_cell: str,
    action: str,
    old_formula: str,
    new_formula: str,
    result_value: str = "",
    year: int | None = None,
) -> None:
    """直接 wp_formula CRUD（save/delete）写 V007 审计哈希链（Task 5.4 / 需求 13.4）。

    统一走 ``audit_log_helper.append_audit_log``（event_type='formula_changed'，与
    report/consol 同源留痕），``user_id`` 必须是**真实操作人**（``user.id``，禁写死全零）。
    ``resource_id`` 用 ``target_cell`` 作行标识。由 router 统一 commit（service 只 flush，审计 append 也只 flush）。

    🔴 mandatory（ADR-ALC-07，spec audit-log-chain-integrity 批 B 的调用点裁决，登记在
    ``services/audit_chain/call_sites.py``）：审计失败即业务失败。在 begin_nested 内
    保证 SAVEPOINT 隔离，但不捕获异常——失败向上传播。

    ``year`` 写入载荷供历史页按年度查询（需求 11.1）；调用方不传时按项目审计年度补齐
    （三处 CRUD 调用方都不传；不补则这些条目在按年度过滤的历史页里一条都看不到）。
    """
    from app.services.audit_log_helper import append_audit_log

    async with db.begin_nested():
        if year is None:
            from app.services.project_audit_year import resolve_project_audit_year_for_request

            year = await resolve_project_audit_year_for_request(db, project_id)
        details: dict = {
                "event_type": "formula_changed",
                "module": "workpaper",
                "row_code": wp_code or "",
                "action": action,
                "old_formula": old_formula,
                "new_formula": new_formula,
                "result_value": result_value,
        }
        if year is not None:
            details["year"] = str(year)
        await append_audit_log(db, {
            "user_id": user.id,
            "project_id": project_id,
            "action": "formula.changed",
            "resource_type": "wp_formula",
            "resource_id": target_cell,
            "details": details,
        })
