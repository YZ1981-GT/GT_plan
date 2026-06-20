"""科目工作包 API 路由

提供工作包列表、详情、摘要和程序状态端点。
Requirements: 1.2, 1.3, 1.4, 2.3, 5.1
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.account_package_registry_service import AccountPackageRegistryService
from app.services.account_package_summary_service import (
    AccountPackageSummaryDTO,
    AccountPackageSummaryService,
)
from app.services.account_package_program_status_service import (
    AccountPackageProgramStatusService,
    ProgramStatusValidationError,
)

router = APIRouter(
    prefix="/projects/{project_id}/account-packages",
    tags=["科目工作包"],
)


# ─── Response schemas ──────────────────────────────────────────────────────


class PackageListItem(BaseModel):
    account_package_id: str
    cycle: str
    account_code: str
    account_name: str
    mapping_status: str
    primary_wp_code: str
    sheet_count: int


class PackageDetail(BaseModel):
    account_package_id: str
    cycle: str
    account_code: str
    account_name: str
    mapping_status: str
    primary_wp_code: str
    control_panel_sheet: str | None = None
    source_wp_codes: list[str] = Field(default_factory=list)
    sheets: list[dict] = Field(default_factory=list)
    external_cards: list[str] = Field(default_factory=list)
    downstream: list[str] = Field(default_factory=list)


class SummaryResponse(BaseModel):
    registry_status: str
    mapping_status: str
    program_status_summary: dict
    external_cards: list[dict]
    stale_summary: dict
    missing_sources: list[dict]


# ─── Program Status schemas ───────────────────────────────────────────────


class ProgramStatusUpdateRequest(BaseModel):
    """程序状态更新请求"""
    applicable: bool | None = None
    status: str | None = None
    evidence: str | None = None
    review_result: str | None = None
    conclusion: str | None = None
    not_applicable_reason: str | None = None


class ProgramStatusResponse(BaseModel):
    """程序状态响应"""
    id: uuid.UUID
    project_id: uuid.UUID
    account_package_id: str
    program_code: str
    applicable: bool
    status: str
    evidence: str | None = None
    review_result: str | None = None
    conclusion: str | None = None
    not_applicable_reason: str | None = None
    reviewer: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    updated_by: uuid.UUID | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ─── Endpoints ─────────────────────────────────────────────────────────────


@router.get("")
async def list_account_packages(
    project_id: uuid.UUID,
    cycle: str | None = Query(None, description="按循环筛选，如 D"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[PackageListItem]:
    """获取工作包列表"""
    registry = AccountPackageRegistryService()
    service = AccountPackageSummaryService(db, registry)
    packages = service.get_package_list(cycle=cycle)
    return [
        PackageListItem(
            account_package_id=pkg["account_package_id"],
            cycle=pkg["cycle"],
            account_code=pkg["account_code"],
            account_name=pkg["account_name"],
            mapping_status=registry.get_effective_mapping_status(pkg),
            primary_wp_code=pkg["primary_wp_code"],
            sheet_count=len(pkg.get("sheets", [])),
        )
        for pkg in packages
    ]


@router.get("/{package_id}")
async def get_account_package(
    project_id: uuid.UUID,
    package_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> PackageDetail:
    """获取工作包详情"""
    registry = AccountPackageRegistryService()
    pkg = registry.get_package(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Account package not found")
    return PackageDetail(
        account_package_id=pkg["account_package_id"],
        cycle=pkg["cycle"],
        account_code=pkg["account_code"],
        account_name=pkg["account_name"],
        mapping_status=registry.get_effective_mapping_status(pkg),
        primary_wp_code=pkg["primary_wp_code"],
        control_panel_sheet=pkg.get("control_panel_sheet"),
        source_wp_codes=pkg.get("source_wp_codes", []),
        sheets=pkg.get("sheets", []),
        external_cards=pkg.get("external_cards", []),
        downstream=pkg.get("downstream", []),
    )


@router.get("/{package_id}/summary")
async def get_account_package_summary(
    project_id: uuid.UUID,
    package_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> SummaryResponse:
    """获取工作包摘要

    即使部分 sheet/schema 缺失也能返回摘要（missing_sources 列出缺失项），
    工作包仍可打开。
    """
    registry = AccountPackageRegistryService()
    service = AccountPackageSummaryService(db, registry)
    dto = await service.get_summary(project_id, package_id)

    return SummaryResponse(
        registry_status=dto.registry_status,
        mapping_status=dto.mapping_status,
        program_status_summary=dto.program_status_summary,
        external_cards=dto.external_cards,
        stale_summary=dto.stale_summary,
        missing_sources=dto.missing_sources,
    )


# ─── Program Status Endpoints ─────────────────────────────────────────────


@router.get("/{package_id}/confirmation-summary")
async def get_confirmation_summary(
    project_id: uuid.UUID,
    package_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> dict:
    """获取函证摘要（只读消费 confirmation_service）

    Task 6.2: D2 摘要读取函证事实真源。
    本端点只从 confirmation 表聚合统计，不写入任何函证数据。
    当无函证数据时返回 {status: "missing", coverage_rate: null}。
    """
    registry = AccountPackageRegistryService()
    service = AccountPackageSummaryService(db, registry)
    return await service.get_confirmation_summary(project_id, package_id)


@router.get("/{package_id}/program-status")
async def list_program_statuses(
    project_id: uuid.UUID,
    package_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[ProgramStatusResponse]:
    """获取工作包下所有程序状态"""
    service = AccountPackageProgramStatusService(db)
    statuses = await service.get_all_statuses(project_id, package_id)
    return [ProgramStatusResponse.model_validate(s) for s in statuses]


@router.get("/{package_id}/program-status/{program_code}")
async def get_program_status(
    project_id: uuid.UUID,
    package_id: str,
    program_code: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> ProgramStatusResponse | None:
    """获取单个程序状态"""
    service = AccountPackageProgramStatusService(db)
    status = await service.get_status(project_id, package_id, program_code)
    if status is None:
        return None
    return ProgramStatusResponse.model_validate(status)


@router.patch("/{package_id}/program-status/{program_code}")
async def update_program_status(
    project_id: uuid.UUID,
    package_id: str,
    program_code: str,
    body: ProgramStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> ProgramStatusResponse:
    """更新程序状态（upsert）

    验证规则：
    - applicable=False 时 not_applicable_reason 必须非空
    - 设置 review_result 时自动记录 reviewer 和 reviewed_at
    - 始终记录 updated_by 和 updated_at
    """
    service = AccountPackageProgramStatusService(db)

    # 构建更新数据（只包含显式传入的字段）
    update_data = body.model_dump(exclude_unset=True)

    try:
        result = await service.upsert_status(
            project_id=project_id,
            account_package_id=package_id,
            program_code=program_code,
            data=update_data,
            user_id=user.id,
        )
        await db.commit()
        return ProgramStatusResponse.model_validate(result)
    except ProgramStatusValidationError as e:
        raise HTTPException(status_code=422, detail=e.message)


# ─── 自定义模板导出/导入（spec workpaper-account-multifile-aggregation 需求 6）──


class ImportTemplateRequest(BaseModel):
    """导入自定义科目模板请求体。"""
    content: str = Field(..., description="YAML/JSON 模板文本（export-template 导出后编辑）")
    scope: str = Field("project", description="作用域: project | firm")


class ImportTemplateResponse(BaseModel):
    success: bool
    wp_code: str | None = None
    scope: str | None = None
    errors: list[str] = Field(default_factory=list)


@router.get("/{wp_code}/export-template")
async def export_account_package_template(
    project_id: uuid.UUID,
    wp_code: str,
    _user=Depends(get_current_user),
):
    """导出科目工作包结构为可编辑 YAML（含 sheet_type + 字段定义）。

    用户编辑后通过 import-template 端点导入形成自定义工作包。
    """
    from fastapi.responses import PlainTextResponse

    from app.services.custom_account_package_service import export_package_template

    yaml_text = export_package_template(wp_code)
    if yaml_text is None:
        raise HTTPException(status_code=404, detail=f"科目工作包不存在: {wp_code}")
    filename = f"account_package_{wp_code}_template.yaml"
    return PlainTextResponse(
        content=yaml_text,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import-template", response_model=ImportTemplateResponse)
async def import_account_package_template(
    project_id: uuid.UUID,
    body: ImportTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ImportTemplateResponse:
    """导入自定义科目模板：解析 + 校验 + 登记为项目级/事务所级工作包。

    校验失败返回明确错误清单（不静默失败，需求 6.6）。
    """
    from app.services.custom_account_package_service import (
        CustomPackageValidationError,
        import_custom_package,
        parse_and_validate,
    )

    try:
        package_json = parse_and_validate(body.content)
    except CustomPackageValidationError as e:
        return ImportTemplateResponse(success=False, errors=e.errors)

    try:
        result = await import_custom_package(
            db,
            scope=body.scope,
            scope_id=project_id,
            package_json=package_json,
            created_by=getattr(current_user, "id", None),
        )
    except CustomPackageValidationError as e:
        return ImportTemplateResponse(success=False, errors=e.errors)

    return ImportTemplateResponse(
        success=True, wp_code=result["wp_code"], scope=result["scope"]
    )
