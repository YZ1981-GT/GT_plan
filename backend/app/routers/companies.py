"""公司管理路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.consolidation_schemas import (
    CompanyCreate,
    CompanyResponse,
    CompanyTreeResponse,
    CompanyUpdate,
    ConsolidationPeriod,
    ConsolScopeCreate,
    ConsolScopeResponse,
    PaginationParams,
    StructureValidationResult,
)
from app.services.group_structure_service import GroupStructureService

router = APIRouter(prefix="/api/projects/{project_id}/companies", tags=["公司管理"])


def get_service(db: Session = Depends(get_db)) -> GroupStructureService:
    return GroupStructureService(db)


@router.get("", response_model=list[CompanyResponse])
def list_companies(
    project_id: UUID,
    service: GroupStructureService = Depends(get_service),
) -> list:
    """列出所有公司"""
    return service.get_companies_by_project(project_id)


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    project_id: UUID,
    data: CompanyCreate,
    service: GroupStructureService = Depends(get_service),
) -> object:
    """创建公司"""
    try:
        return service.create_company(project_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/tree", response_model=CompanyTreeResponse)
def get_company_tree(
    project_id: UUID,
    service: GroupStructureService = Depends(get_service),
) -> CompanyTreeResponse:
    """获取公司层级树"""
    return service.get_group_tree(project_id)


@router.get("/validate")
def validate_structure(
    project_id: UUID,
    service: GroupStructureService = Depends(get_service),
) -> dict:
    """校验集团结构"""
    result = service.validate_structure(project_id)
    return result.model_dump()


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    project_id: UUID,
    company_id: UUID,
    service: GroupStructureService = Depends(get_service),
) -> object:
    """获取单个公司"""
    company = service.get_company(company_id)
    if not company or str(company.project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="公司不存在"
        )
    return company


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(
    project_id: UUID,
    company_id: UUID,
    data: CompanyUpdate,
    service: GroupStructureService = Depends(get_service),
) -> object:
    """更新公司"""
    # 验证公司属于该项目
    existing = service.get_company(company_id)
    if not existing or str(existing.project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="公司不存在"
        )
    try:
        return service.update_company(company_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    project_id: UUID,
    company_id: UUID,
    service: GroupStructureService = Depends(get_service),
) -> None:
    """软删除公司"""
    existing = service.get_company(company_id)
    if not existing or str(existing.project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="公司不存在"
        )
    try:
        service.delete_company(company_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---- 架构树 ----


@router.get("/tree", response_model=CompanyTreeResponse)
def get_group_tree(
    project_id: UUID,
    service: GroupStructureService = Depends(get_service),
) -> CompanyTreeResponse:
    """获取集团结构树"""
    return service.get_group_tree(project_id)


# ---- 结构校验 ----


@router.post("/validate", response_model=StructureValidationResult)
def validate_structure(
    project_id: UUID,
    service: GroupStructureService = Depends(get_service),
) -> StructureValidationResult:
    """校验集团结构（循环引用、孤儿节点、合并范围冲突等）"""
    return service.validate_structure(project_id)


# ---- 合并范围管理 ----


@router.get("/consol-scope", response_model=list[ConsolScopeResponse])
def get_consol_scope(
    project_id: UUID,
    year: int | None = None,
    service: GroupStructureService = Depends(get_service),
) -> list[ConsolScopeResponse]:
    """获取合并范围列表"""
    return service.get_consol_scope(project_id, year)


@router.post(
    "/consol-scope",
    response_model=list[ConsolScopeResponse],
    status_code=status.HTTP_201_CREATED,
)
def manage_consol_scope(
    project_id: UUID,
    scope_items: list[ConsolScopeCreate],
    service: GroupStructureService = Depends(get_service),
) -> list[ConsolScopeResponse]:
    """批量创建/更新合并范围"""
    return service.manage_consol_scope(project_id, scope_items)


@router.get("/consolidation-period/{company_id}/{year}")
def get_consolidation_period(
    project_id: UUID,
    company_id: UUID,
    year: int,
    service: GroupStructureService = Depends(get_service),
) -> ConsolidationPeriod:
    """根据收购/处置日期计算合并期间"""
    company = service.get_company(company_id)
    if not company or str(company.project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="公司不存在"
        )
    return GroupStructureService.get_consolidation_period(company, year)
