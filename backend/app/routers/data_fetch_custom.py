"""自定义取数 API — 跳行跳列、任选单元格、溯源跳转

提供：
- 执行自定义取数规则（单条/批量）
- 正向溯源（目标→来源）
- 反向溯源（来源→引用目标）
- 取数规则 CRUD（存储在项目 wizard_state 中）
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.data_fetch_custom import CustomFetchService, FetchRule

router = APIRouter(prefix="/api/projects/{project_id}/custom-fetch", tags=["自定义取数"])


class ExecuteRuleRequest(BaseModel):
    """执行取数规则请求"""
    rules: list[dict]
    year: int = 2025


class TraceRequest(BaseModel):
    """溯源查询请求"""
    location: str
    rules: list[dict]


class SaveRulesRequest(BaseModel):
    """保存取数规则"""
    target_type: str  # note / workpaper / report
    target_id: str    # section号 / wp_code / row_code
    rules: list[dict]


@router.post("/execute")
async def execute_fetch_rules(
    project_id: UUID,
    data: ExecuteRuleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行自定义取数规则（支持跳行跳列、任选单元格）

    规则格式示例：
    {
        "target": {"type": "note", "section": "五、1", "row": 0, "col": 1},
        "sources": [
            {"type": "trial_balance", "account_code": "1001", "field": "audited_amount"},
            {"type": "trial_balance", "account_code": "1002", "field": "audited_amount"}
        ],
        "transform": "sum",
        "description": "货币资金=库存现金+银行存款"
    }
    """
    svc = CustomFetchService(db, project_id, data.year)
    result = await svc.execute_rules(data.rules)
    return result


@router.post("/trace-forward")
async def trace_forward(
    project_id: UUID,
    data: TraceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """正向溯源：点击目标单元格 → 显示数据来源 + 跳转链接

    location 格式：note:五、1:0:1 / workpaper:E1-1:Sheet1:B7
    """
    svc = CustomFetchService(db, project_id, 2025)
    traces = await svc.trace_target(data.location, data.rules)
    return {"target": data.location, "sources": traces}


@router.post("/trace-backward")
async def trace_backward(
    project_id: UUID,
    data: TraceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """反向溯源：数据源变更 → 显示哪些目标引用了它

    location 格式：trial_balance:1001:audited_amount
    """
    svc = CustomFetchService(db, project_id, 2025)
    targets = await svc.trace_source(data.location, data.rules)
    return {"source": data.location, "targets": targets}


@router.post("/save-rules")
async def save_custom_rules(
    project_id: UUID,
    data: SaveRulesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存自定义取数规则到项目配置

    规则存储在 Project.wizard_state.custom_fetch_rules 中。
    """
    import sqlalchemy as sa
    from sqlalchemy.orm.attributes import flag_modified
    from app.models.core import Project

    project = (await db.execute(
        sa.select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()
    if not project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="项目不存在")

    ws = project.wizard_state or {}
    fetch_rules = ws.get("custom_fetch_rules", {})

    # 按 target_type:target_id 存储
    key = f"{data.target_type}:{data.target_id}"
    fetch_rules[key] = {
        "rules": data.rules,
        "updated_by": str(current_user.id),
        "updated_at": __import__("datetime").datetime.utcnow().isoformat(),
    }

    ws["custom_fetch_rules"] = fetch_rules
    project.wizard_state = ws
    flag_modified(project, "wizard_state")
    await db.flush()
    await db.commit()

    return {"key": key, "rules_count": len(data.rules), "message": "取数规则已保存"}


@router.get("/rules")
async def get_custom_rules(
    project_id: UUID,
    target_type: str | None = Query(None),
    target_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取项目的自定义取数规则"""
    import sqlalchemy as sa
    from app.models.core import Project

    project = (await db.execute(
        sa.select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()
    if not project:
        return {"rules": {}}

    ws = project.wizard_state or {}
    fetch_rules = ws.get("custom_fetch_rules", {})

    if target_type and target_id:
        key = f"{target_type}:{target_id}"
        return fetch_rules.get(key, {"rules": []})

    return fetch_rules
