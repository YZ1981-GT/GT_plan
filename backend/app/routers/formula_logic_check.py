"""公式管理库 · logic_check 执行端点（Task 4.1 / Req 6.4）。

收编前端 ``useReportCrossCheck`` 的 7 条硬编码报表勾稽为**可编辑的
logic_check 公式**后，本路由提供其后端执行入口：从 ``financial_report`` 取
资产负债表 / 利润表数据，经统一公式引擎（logic_check 分派）执行 7 条勾稽，
返回 **Issue_List**（勾稽不通过项）+ 逐条 passed 结果。

logic_check 语义：**绝不修改任何数据单元值**（Req 6.3）——本端点为只读计算。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.formula_management.logic_check import (
    CrossCheckResult,
    execute_report_cross_checks,
)

router = APIRouter(tags=["formula-logic-check"])


def _serialize(result: CrossCheckResult) -> dict[str, Any]:
    """把执行结果序列化为可 JSON 化的响应（Issue_List + 逐条结果）。"""
    return {
        "issue_list": [
            {
                "formula_id": issue.formula_id,
                "addr_id": issue.addr_id,
                "description": issue.description,
                "left_value": (
                    str(issue.left_value) if issue.left_value is not None else None
                ),
                "right_value": (
                    str(issue.right_value) if issue.right_value is not None else None
                ),
            }
            for issue in result.issues
        ],
        "results": [
            {
                "formula_id": o.formula_id,
                "description": o.description,
                "expression": o.expression,
                "passed": o.passed,
            }
            for o in result.outcomes
        ],
        "last_computed_at": (
            result.last_computed_at.isoformat()
            if result.last_computed_at is not None
            else None
        ),
    }


@router.get("/api/projects/{project_id}/formula/report-cross-check")
async def run_report_cross_check(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """执行报表勾稽（7 条 logic_check 公式）→ 返回 Issue_List。

    logic_check 只读、绝不改值；router 层负责事务收尾（commit）。
    """
    result = await execute_report_cross_checks(db, project_id=project_id, year=year)
    # router 层 commit（工程铁律）：logic_check 无写入，此处为事务收尾一致性。
    await db.commit()
    return _serialize(result)
