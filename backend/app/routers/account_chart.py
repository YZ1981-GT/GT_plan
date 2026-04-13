"""科目表管理 API 路由

Validates: Requirements 2.2, 2.5, 2.6
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
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
    # Try to get existing standard chart
    accounts = await account_chart_service.get_standard_chart(project_id, db)
    if accounts:
        return accounts

    # Auto-load standard template based on project's accounting standard
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
    skip_rows: int = 2,
    current_user: User = Depends(get_current_user),
):
    """Preview uploaded file: return first 20 rows per sheet + auto-matched column mapping.
    
    skip_rows: 跳过前N行（默认2行，第3行作为表头）
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
