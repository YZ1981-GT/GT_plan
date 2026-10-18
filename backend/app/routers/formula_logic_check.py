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

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import Project, User
from app.services.formula_management.cross_check_run import (
    STATUS_NO_RESULT,
    execute_cross_check_run,
)
from app.services.formula_management.logic_check import CrossCheckResult

router = APIRouter(tags=["formula-logic-check"])

#: ``project.wizard_state`` 下存放用户表间审核规则的键。
#: 复用既有 ``wizard_state`` JSONB（与 aging_config / column_mappings /
#: custom_fetch_rules 同款项目级配置存储，不新建大表——design §5 步骤 6）。
_CROSS_CHECK_RULES_KEY = "cross_check_user_rules"


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
    user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """执行报表勾稽（7 条 logic_check 公式）→ 返回 Issue_List + run_id。

    Phase 6 Task 6.4：一次执行贯穿同一 ``run_id`` 写 run / issue / hint / outbox /
    audit 五表（可按 run_id 查询）；**去掉"执行 0 条仍成功"**——没有任何可执行勾稽
    时返回 ``status=no_result``（无结果），而非 ``executed``。

    logic_check 只读、绝不改被勾稽的数据值；本端点写的是"勾稽结论 + 运行留痕"
    这一新事实。service 只 flush，router 层统一 commit（工程铁律）。
    """
    run = await execute_cross_check_run(
        db,
        project_id=project_id,
        year=year,
        operator_id=user.id,
        operator_role=getattr(user.role, "value", str(user.role)),
    )
    # router 层 commit（工程铁律）：五表写入在同一事务内，commit 保原子。
    await db.commit()

    payload = _serialize(run.result)
    payload["run_id"] = str(run.run_id)
    payload["status"] = run.status
    payload["executed_count"] = run.executed_count
    payload["hint_count"] = run.hint_count
    payload["hints"] = run.hints
    # 0 条显式"无结果"（去掉"执行 0 条仍成功"）：前端据此呈现"无结果"而非"成功"。
    payload["no_result"] = run.status == STATUS_NO_RESULT
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# 表间审核用户规则持久化（Phase 6 Task 6.2 / 需求 7.3）
# ─────────────────────────────────────────────────────────────────────────────
# 用户在公式管理中央弹窗「表间审核」里新增/编辑的规则，必须落库，关闭再打开仍
# 可见。规则按树节点 key（如 ``cross_report_note``）分组存放于项目 ``wizard_state``
# 下的 ``cross_check_user_rules``——复用既有项目级 JSONB 配置存储（不新建大表）。
#
# 存储结构::
#
#     project.wizard_state["cross_check_user_rules"] = {
#         "<nodeKey>": [ {label, left_ref, operator, right_ref, description}, ... ],
#         ...
#     }
#
# 前端树节点 key 与规则 map key 由同一键生成函数产出（MEDIUM-2），后端只按
# 字符串 key 存取、不解析其语义——避免前后端双真源偏移。


class CrossCheckRule(BaseModel):
    """单条表间审核规则（用户可编辑字段）。

    与前端 ``crossRuleForm`` 契约字段一致；``_editing`` 等 UI 瞬态字段不落库。
    """

    label: str = ""
    left_ref: str = ""
    operator: str = "="
    right_ref: str = ""
    description: str = ""


class CrossCheckRulesPayload(BaseModel):
    """PUT 请求体：按节点 key 分组的规则集合（整体替换该项目的用户规则）。"""

    rules: dict[str, list[CrossCheckRule]]


async def _get_project_or_404(db: AsyncSession, project_id: UUID) -> Project:
    project = (
        await db.execute(
            sa.select(Project).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.get("/api/projects/{project_id}/formula/cross-check-rules")
async def get_cross_check_rules(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """读取项目的用户表间审核规则（按树节点 key 分组）。

    从未保存过 → 返回空集 ``{"rules": {}}``（前端据此呈现「无规则」，不冒充静态示例）。
    """
    project = await _get_project_or_404(db, project_id)
    ws = project.wizard_state if isinstance(project.wizard_state, dict) else {}
    rules = ws.get(_CROSS_CHECK_RULES_KEY) or {}
    return {"rules": rules}


@router.put("/api/projects/{project_id}/formula/cross-check-rules")
async def save_cross_check_rules(
    project_id: UUID,
    payload: CrossCheckRulesPayload,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("edit")),
) -> dict[str, Any]:
    """整体替换项目的用户表间审核规则（落库到 ``wizard_state``），返回已保存集合。

    整体替换语义：前端在新增/编辑/删除后把该节点（或全部节点）的完整规则集 PUT 上来，
    后端按 key 覆盖。``flag_modified`` 就地改 JSONB 使 SQLAlchemy 感知变更。
    """
    project = await _get_project_or_404(db, project_id)
    ws = dict(project.wizard_state) if isinstance(project.wizard_state, dict) else {}
    # 序列化为纯 dict（剔除 pydantic 模型 / UI 瞬态字段），仅落库契约字段。
    serialized: dict[str, list[dict[str, str]]] = {
        node_key: [rule.model_dump() for rule in node_rules]
        for node_key, node_rules in payload.rules.items()
    }
    ws[_CROSS_CHECK_RULES_KEY] = serialized
    project.wizard_state = ws
    flag_modified(project, "wizard_state")
    # service 层只 flush、router 统一 commit（工程铁律）。此端点无跨 service 编排，
    # 直接在 router 内 flush + commit。
    await db.flush()
    await db.commit()
    return {"rules": serialized}
