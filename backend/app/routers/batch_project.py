"""批量建项 API 路由

Feature: project-creation-enhancement, Task 8.2
Endpoints:
  - GET  /api/projects/batch-template  → 下载建项模板
  - POST /api/projects/batch-import    → 批量导入建项
  - POST /api/projects/batch-export    → 导出选中项目数据
"""

from uuid import UUID
from urllib.parse import quote

from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.batch_project_service import (
    BatchImportResult,
    BatchValidateResponse,
    export_projects,
    generate_template,
    parse_and_import,
    validate_batch,
)
from app.services import consol_tree_service

router = APIRouter(prefix="/api/projects", tags=["批量建项"])


def _make_content_disposition(filename: str) -> str:
    """RFC5987 编码 Content-Disposition（支持中文文件名）。"""
    encoded = quote(filename, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


@router.get("/batch-template")
async def download_batch_template(
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """下载建项模板 Excel。"""
    output = await generate_template()
    filename = "建项模板.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _make_content_disposition(filename)},
    )


@router.get("/tree")
async def get_group_tree(
    year: int | None = None,
    scope: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """集团架构全局森林树形。

    与 consol_worksheet 的 GET /tree?project_id=X（单合并项目内部树）不同：
    本端点是全局森林——所有项目按 ultimate_company_code 分组成多棵树，无单一 root。

    静态路径 /tree 必须在通配 /{project_id}（project_wizard.py）之前解析。
    注册顺序由 router_registry/system.py §2 保证（batch_project_router 先于
    project_wizard_router 注册）。

    Args:
        year: 年度过滤（按 audit_period_end 年份），不传则不过滤
        scope: report_scope 过滤（如 'consolidated'），不传或 'all' 则全部项目

    Returns:
        {"trees": [...], "independents": [...]}
    """
    effective_scope = None if scope in (None, "", "all") else scope
    return await consol_tree_service.build_tree_by_codes(
        db, year=year, scope=effective_scope
    )


@router.post("/batch-validate", response_model=BatchValidateResponse)
async def batch_validate_projects(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchValidateResponse:
    """批量建项预校验（dry-run，不入库）。

    解析上传 Excel → 行级格式/必填/USCC 校验 + 同批次重复检测 +
    集团树形预览（含循环引用检测）。绝不写库，用于导入前确认层级正确。

    静态路径 /batch-validate 由 batch_project_router 在通配 /{project_id} 之前注册。
    """
    file_bytes = await file.read()
    return await validate_batch(file_bytes, db)


@router.post("/batch-import", response_model=BatchImportResult)
async def batch_import_projects(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchImportResult:
    """批量导入建项（上传 Excel 文件）。"""
    file_bytes = await file.read()
    return await parse_and_import(file_bytes, db)


class BatchExportRequest(BaseModel):
    project_ids: list[UUID]


@router.post("/batch-export")
async def batch_export_projects(
    body: BatchExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出选中项目数据为 Excel。"""
    from datetime import date as date_type

    output = await export_projects(body.project_ids, db)
    today = date_type.today().strftime("%Y%m%d")
    filename = f"项目数据导出_{today}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _make_content_disposition(filename)},
    )
