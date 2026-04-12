"""公司信息服务"""

from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from app.models.consolidation_models import Company
from app.models.consolidation_schemas import (
    CompanyCreate,
    CompanyResponse,
    CompanyTreeNode,
    CompanyUpdate,
    StructureValidationResult,
)
from app.services.utils import build_company_tree


def get_companies(db: Session, project_id: UUID) -> list[Company]:
    return (
        db.query(Company)
        .filter(Company.project_id == project_id, Company.is_deleted.is_(False))
        .order_by(Company.consol_level, Company.company_code)
        .all()
    )


def get_company(db: Session, company_id: UUID, project_id: UUID) -> Company | None:
    return (
        db.query(Company)
        .filter(Company.id == company_id, Company.project_id == project_id)
        .first()
    )


def create_company(db: Session, project_id: UUID, data: CompanyCreate) -> Company:
    company = Company(project_id=project_id, **data.model_dump())
    db.add(company)
    db.flush()
    _recalc_levels(db, project_id)
    db.commit()
    db.refresh(company)
    return company


def update_company(db: Session, company_id: UUID, project_id: UUID, data: CompanyUpdate) -> Company | None:
    company = get_company(db, company_id, project_id)
    if not company:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(company, key, value)
    db.flush()
    _recalc_levels(db, project_id)
    db.commit()
    db.refresh(company)
    return company


def delete_company(db: Session, company_id: UUID, project_id: UUID) -> bool:
    company = get_company(db, company_id, project_id)
    if not company:
        return False
    company.is_deleted = True
    db.commit()
    return True


def get_company_tree(db: Session, project_id: UUID) -> list[CompanyTreeNode]:
    companies = get_companies(db, project_id)
    return build_company_tree(companies)


def validate_structure(db: Session, project_id: UUID) -> StructureValidationResult:
    """校验集团结构"""
    companies = get_companies(db, project_id)
    errors: list[str] = []
    warnings: list[str] = []

    code_map = {c.company_code: c for c in companies}

    # 检查根公司
    roots = [c for c in companies if not c.parent_code]
    if not roots:
        errors.append("缺少根公司（无父公司的公司）")
    elif len(roots) > 1:
        warnings.append(f"存在 {len(roots)} 个根公司，可能需要统一母公司")

    # 检查循环引用
    for c in companies:
        visited = set()
        cur = c
        while cur and cur.parent_code:
            if cur.parent_code in visited:
                errors.append(f"公司 {c.company_code} 存在循环引用")
                break
            visited.add(cur.parent_code)
            cur = code_map.get(cur.parent_code)

    # 检查 parent_code 引用有效性
    for c in companies:
        if c.parent_code and c.parent_code not in code_map:
            errors.append(f"公司 {c.company_code} 的父公司代码 {c.parent_code} 不存在")

    # 检查终极公司标记
    ultimate_codes = set(c.ultimate_code for c in companies)
    if not ultimate_codes:
        errors.append("缺少终极公司标记")

    return StructureValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def _recalc_levels(db: Session, project_id: UUID) -> None:
    """重新计算所有公司的合并层级和终极公司代码"""
    companies = (
        db.query(Company)
        .filter(Company.project_id == project_id, Company.is_deleted.is_(False))
        .order_by(Company.company_code)
        .all()
    )
    if not companies:
        return

    code_map = {c.company_code: c for c in companies}

    def find_root(c: Company) -> str:
        """找到根公司代码"""
        visited = set()
        while c and c.parent_code:
            if c.company_code in visited:
                return c.company_code  # 防止循环
            visited.add(c.company_code)
            c = code_map.get(c.parent_code)
        return c.company_code if c else ""

    def get_level(c: Company) -> int:
        level = 0
        visited = set()
        cur = c
        while cur and cur.parent_code:
            if cur.company_code in visited:
                break
            visited.add(cur.parent_code)
            cur = code_map.get(cur.parent_code)
            level += 1
        return level

    for company in companies:
        company.ultimate_code = find_root(company)
        company.consol_level = get_level(company)
