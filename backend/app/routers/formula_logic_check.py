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

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import Project, User
from app.services.formula_management.cross_check_run import (
    STATUS_NO_RESULT,
    execute_cross_check_run,
)
from app.services.formula_management.logic_check import CrossCheckResult
from app.services.formula_settings import cross_check_rules

router = APIRouter(tags=["formula-logic-check"])

#: 旧存储键：``project.wizard_state["cross_check_user_rules"]``。2026-10-20 起规则存 ``formula_setting``
#: （cross_check 域，全局 + 本项目两层），V199 迁移把旧数据迁入；代码不再读写 wizard_state。
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
# 可见。规则按树节点 key（如 ``cross_report_note``）分组；存储见
# ``services/formula_settings/cross_check_rules.py``（公式位 ``{nodeKey}#{rule_id}``）。
# 前端树节点 key 与规则 map key 由同一键生成函数产出（MEDIUM-2），后端只按
# 字符串 key 存取、不解析其语义——避免前后端双真源偏移。


class CrossCheckRule(BaseModel):
    """单条表间审核规则（用户可编辑字段）。

    与前端 ``crossRuleForm`` 契约字段一致；``_editing`` 等 UI 瞬态字段不落库。
    ``rule_id``：读接口下发的规则编号（新增规则不带，后端生成）；``tolerance`` 缺省 0.01。
    """

    rule_id: str | None = None
    label: str = ""
    left_ref: str = ""
    operator: str = "="
    right_ref: str = ""
    description: str = ""
    tolerance: float | None = None


class CrossCheckRulesPayload(BaseModel):
    """PUT 请求体：按节点 key 分组的规则集合（整体替换该项目的用户规则）。

    ``loaded``：读接口下发的版本令牌原样带回（差量写入与并发冲突判定，见 setting_sets）。
    """

    rules: dict[str, list[CrossCheckRule]]
    loaded: dict[str, str] | None = None


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
    """读取项目生效的表间审核规则（全局 + 本项目，按树节点 key 分组，带层级与版本令牌）。

    从未保存过 → 返回空集 ``{"rules": {}}``（前端据此呈现「无规则」，不冒充静态示例）。
    spec formula-global-settings-sync：存储改为 ``formula_setting``（V199 已迁入旧 wizard_state 数据）。
    """
    await _get_project_or_404(db, project_id)
    return await cross_check_rules.load(db, project_id)


@router.put("/api/projects/{project_id}/formula/cross-check-rules")
async def save_cross_check_rules(
    project_id: UUID,
    payload: CrossCheckRulesPayload,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("edit")),
) -> dict[str, Any]:
    """整体替换项目的用户表间审核规则，返回保存后的生效集合。

    整体替换语义保持：前端把完整规则集 PUT 上来；后端按载入时的版本令牌求差量写本项目适配
    （来自全局的规则被删 = 本项目停用，全局不受影响）。缺令牌 428、令牌过期 409，整批不写。
    service 只 flush，这里 commit 后发变更事件。
    """
    from app.services.formula_settings.errors import FormulaSettingError
    from app.services.formula_settings.outbox import record_changes, publish_pending

    await _get_project_or_404(db, project_id)
    try:
        result = await cross_check_rules.save(
            db, project_id,
            rules={k: [r.model_dump() for r in v] for k, v in payload.rules.items()},
            loaded=payload.loaded, user_id=_user.id,
        )
    except FormulaSettingError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from None
    await record_changes(db, events=result["events"], domain="cross_check", source="cross_check_edit")
    await db.commit()
    await publish_pending(db)
    # 本次真正改动的公式位（供前端保存后问「应用范围」，R7.1）
    changed = sorted({s for ev in result["events"] for s in ev.get("slot_keys", [])})
    return {**await cross_check_rules.load(db, project_id), "changed_slot_keys": changed}


# ── E 批：表间审核执行历史 ────────────────────────────────────────────────
# spec: formula-management-ux-improvements · E 批；按真实列读取见 formula-settings-wiring-closure R3.1


@router.get("/api/projects/{project_id}/formula/cross-check-history")
async def cross_check_history(
    project_id: UUID,
    year: int,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """本项目本年度最近 N 次表间审核：每次的计数 + 仍保留的逐条结论（只读）。"""
    from app.services.formula_management.cross_check_history import list_history

    await _get_project_or_404(db, project_id)
    runs = await list_history(db, project_id, year, limit)
    return {"project_id": str(project_id), "year": year, "total": len(runs), "runs": runs}
