"""科目表管理 API 路由

Validates: Requirements 2.2, 2.5, 2.6
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import (
    AccountChartResponse,
    AccountImportResult,
    AccountTreeNode,
)
from app.models.core import User
from app.services import account_chart_service

router = APIRouter(prefix="/api/projects", tags=["account-chart"])


@router.get(
    "/{project_id}/account-chart/standard",
    response_model=list[AccountChartResponse],
)
async def get_standard_chart(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AccountChartResponse]:
    """获取项目的标准科目表。

    如果尚未加载，则根据项目会计准则自动加载标准科目模板。

    Validates: Requirements 2.2
    """
    # Always try incremental load (adds missing standard accounts)
    from app.services.project_wizard_service import get_wizard_state
    state = await get_wizard_state(project_id, db)
    accounting_standard = "enterprise"  # default
    basic_info = state.steps.get("basic_info")
    if basic_info and basic_info.data:
        accounting_standard = basic_info.data.get("accounting_standard", "enterprise")

    return await account_chart_service.load_standard_template(
        project_id, accounting_standard, db
    )


@router.post("/{project_id}/account-chart/preview")
async def preview_file(
    project_id: UUID,
    file: UploadFile = File(...),
    skip_rows: int | None = Query(default=None, description="跳过前N行，None=自动检测表头"),
    current_user: User = Depends(get_current_user),
):
    """Preview uploaded file: return first 20 rows per sheet + auto-matched column mapping.

    skip_rows: None=自动检测表头行位置（推荐），传数字则固定跳过。
    """
    return await account_chart_service.preview_file(file, skip_rows=skip_rows)


@router.post(
    "/{project_id}/account-chart/import",
    response_model=AccountImportResult,
)
async def import_client_chart(
    project_id: UUID,
    file: UploadFile = File(...),
    column_mapping: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AccountImportResult:
    """导入客户科目表（Excel/CSV 文件上传）。

    可选传入 column_mapping JSON 字符串，格式: {"原列名": "标准字段名", ...}
    如果不传，使用默认的列名映射逻辑。

    Validates: Requirements 2.3, 2.4, 2.5
    """
    import json

    parsed_mapping = None
    if column_mapping:
        try:
            parsed_mapping = json.loads(column_mapping)
        except (json.JSONDecodeError, TypeError):
            pass  # Fall back to default mapping

    return await account_chart_service.import_client_chart(
        project_id, file, db, column_mapping=parsed_mapping
    )


@router.get(
    "/{project_id}/account-chart/client",
    response_model=dict[str, list[AccountTreeNode]],
)
async def get_client_chart(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, list[AccountTreeNode]]:
    """获取客户科目表（树形结构按类别分组）。

    Validates: Requirements 2.6
    """
    return await account_chart_service.get_client_chart_tree(project_id, db)


# ── 列映射保存/加载（持久化到 wizard_state） ──

from pydantic import BaseModel as _BaseModel


class SaveColumnMappingRequest(_BaseModel):
    """保存列映射"""
    file_type: str  # account_chart / ledger / balance / aux_balance
    sheet_name: str | None = None
    mapping: dict[str, str]  # {原列名: 标准字段名}


class ReferenceMatchRequest(_BaseModel):
    """参照匹配请求"""
    source_project_id: str
    source_year: int | None = None


@router.post("/{project_id}/column-mappings")
async def save_column_mapping(
    project_id: UUID,
    body: SaveColumnMappingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存用户确认的列映射（持久化到项目 wizard_state）"""
    from sqlalchemy import select
    from app.models.core import Project

    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    project = result.scalar_one_or_none()
    if not project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="项目不存在")

    # 保存到 wizard_state.column_mappings
    state = project.wizard_state or {}
    if "column_mappings" not in state:
        state["column_mappings"] = {}

    key = f"{body.file_type}"
    if body.sheet_name:
        key = f"{body.file_type}:{body.sheet_name}"
    state["column_mappings"][key] = body.mapping
    project.wizard_state = state

    await db.commit()
    return {"saved": True, "key": key, "field_count": len(body.mapping)}


@router.get("/{project_id}/column-mappings")
async def get_column_mappings(
    project_id: UUID,
    file_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取已保存的列映射"""
    from sqlalchemy import select
    from app.models.core import Project

    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    project = result.scalar_one_or_none()
    if not project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="项目不存在")

    state = project.wizard_state or {}
    mappings = state.get("column_mappings", {})

    if file_type:
        # 过滤指定文件类型
        filtered = {k: v for k, v in mappings.items() if k.startswith(file_type)}
        return filtered
    return mappings


@router.get("/{project_id}/column-mappings/reference-projects")
async def get_reference_projects(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取可参照的项目列表（有已保存列映射的其他项目）"""
    from sqlalchemy import select, func, cast, String
    from app.models.core import Project

    # 查找所有有 column_mappings 的项目（排除当前项目）
    result = await db.execute(
        select(Project.id, Project.name, Project.client_name, Project.wizard_state)
        .where(
            Project.id != project_id,
            Project.is_deleted == False,  # noqa: E712
            Project.wizard_state.isnot(None),
        )
        .order_by(Project.created_at.desc())
        .limit(20)
    )
    projects = []
    for row in result.all():
        ws = row.wizard_state or {}
        mappings = ws.get("column_mappings", {})
        if mappings:
            projects.append({
                "id": str(row.id),
                "name": row.name,
                "client_name": row.client_name,
                "mapping_count": len(mappings),
                "file_types": list(set(k.split(":")[0] for k in mappings.keys())),
            })
    return projects


@router.post("/{project_id}/column-mappings/reference-copy")
async def reference_copy_mappings(
    project_id: UUID,
    body: ReferenceMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从其他项目参照复制列映射"""
    from sqlalchemy import select
    from app.models.core import Project

    # 获取源项目的映射
    source = await db.execute(
        select(Project).where(Project.id == UUID(body.source_project_id))
    )
    source_project = source.scalar_one_or_none()
    if not source_project or not source_project.wizard_state:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="源项目不存在或无映射数据")

    source_mappings = (source_project.wizard_state or {}).get("column_mappings", {})
    if not source_mappings:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="源项目无已保存的列映射")

    # 复制到目标项目
    target = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    target_project = target.scalar_one_or_none()
    if not target_project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="目标项目不存在")

    state = target_project.wizard_state or {}
    if "column_mappings" not in state:
        state["column_mappings"] = {}
    state["column_mappings"].update(source_mappings)
    target_project.wizard_state = state

    await db.commit()
    return {
        "copied": True,
        "source_project": body.source_project_id,
        "mapping_count": len(source_mappings),
    }


class AccountUpdateItem(_BaseModel):
    """单个科目更新"""
    account_code: str
    account_name: str | None = None
    direction: str | None = None


class BatchUpdateRequest(_BaseModel):
    """批量更新科目"""
    updates: list[AccountUpdateItem]


@router.put("/{project_id}/account-chart/batch-update")
async def batch_update_accounts(
    project_id: UUID,
    body: BatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """批量更新客户科目（名称、借贷方向）"""
    from app.models.audit_platform_models import AccountChart, AccountSource, AccountDirection

    updated = 0
    for item in body.updates:
        result = await db.execute(
            select(AccountChart).where(
                AccountChart.project_id == project_id,
                AccountChart.account_code == item.account_code,
                AccountChart.source == AccountSource.client,
                AccountChart.is_deleted == False,  # noqa: E712
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            continue

        if item.account_name is not None:
            row.account_name = item.account_name
        if item.direction is not None:
            try:
                row.direction = AccountDirection(item.direction)
            except ValueError:
                pass
        updated += 1

    await db.commit()
    return {"updated": updated, "total": len(body.updates)}
