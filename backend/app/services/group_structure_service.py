"""集团结构服务

提供公司层级结构管理、合并范围管理等功能。
"""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, text
from sqlalchemy.orm import Session

from app.models.consolidation_models import (
    Company,
    ConsolScope,
    ConsolMethod,
    ScopeCompanyType,
    ScopeChangeType,
)
from app.models.consolidation_schemas import (
    CompanyCreate,
    CompanyResponse,
    CompanyTreeNode,
    CompanyUpdate,
    ConsolScopeCreate,
    ConsolScopeResponse,
    ConsolScopeUpdate,
    StructureValidationResult,
)
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 本地补充 Schema（consolidation_schemas 中未定义）
# ---------------------------------------------------------------------------

class CompanyTreeResponse(BaseModel):
    """集团结构树响应"""
    nodes: list[CompanyTreeNode] = Field(default_factory=list)


class ConsolidationPeriod(BaseModel):
    """合并期间"""
    include_pl: bool = True
    include_bs: bool = True
    start_date: date | None = None
    end_date: date | None = None


# ===================================================================
# 辅助函数
# ===================================================================


def _find_ultimate_ancestor(
    db: Session, project_id: UUID, company_code: str
) -> str | None:
    """递归查找顶级最终控股公司代码"""
    company = (
        db.query(Company)
        .filter(
            Company.project_id == project_id,
            Company.company_code == company_code,
            Company.is_deleted.is_(False),
        )
        .first()
    )
    if not company:
        return None
    if company.parent_code is None:
        return company.company_code
    return _find_ultimate_ancestor(db, project_id, company.parent_code)


def _calculate_consol_level(
    db: Session, project_id: UUID, parent_code: str | None
) -> int:
    """计算合并层级"""
    if parent_code is None:
        return 0
    parent = (
        db.query(Company)
        .filter(
            Company.project_id == project_id,
            Company.company_code == parent_code,
            Company.is_deleted.is_(False),
        )
        .first()
    )
    if parent:
        return parent.consol_level + 1
    return 0


def _update_descendants_ultimate(
    db: Session, project_id: UUID, old_ultimate_code: str, new_ultimate_code: str
) -> None:
    """更新所有后代公司的最终控股代码"""
    # 递归更新所有后代
    def update_subtree(code: str) -> None:
        children = (
            db.query(Company)
            .filter(
                Company.project_id == project_id,
                Company.parent_code == code,
                Company.is_deleted.is_(False),
            )
            .all()
        )
        for child in children:
            if child.ultimate_code == old_ultimate_code:
                child.ultimate_code = new_ultimate_code
            update_subtree(child.company_code)

    update_subtree(old_ultimate_code)


def _update_descendants_levels(
    db: Session, project_id: UUID, company_code: str, level_delta: int
) -> None:
    """更新所有后代公司的合并层级"""
    children = (
        db.query(Company)
        .filter(
            Company.project_id == project_id,
            Company.parent_code == company_code,
            Company.is_deleted.is_(False),
        )
        .all()
    )
    for child in children:
        child.consol_level = child.consol_level + level_delta
        _update_descendants_levels(db, project_id, child.company_code, level_delta)


def _build_tree(
    companies: list[Company],
) -> list[CompanyTreeNode]:
    """从扁平列表构建树结构"""
    # 建立 code -> node 映射
    node_map: dict[str, CompanyTreeNode] = {}
    for c in companies:
        node_map[c.company_code] = CompanyTreeNode(
            company_code=c.company_code,
            company_name=c.company_name,
            consol_level=c.consol_level,
            ownership_type=c.ownership_type,
            ownership_percentage=c.ownership_percentage,
            consolidation_method=c.consolidation_method,
            ultimate_code=c.ultimate_code,
            parent_code=c.parent_code,
            children=[],
        )

    # 构建父子关系
    roots: list[CompanyTreeNode] = []
    for c in companies:
        node = node_map[c.company_code]
        if c.parent_code and c.parent_code in node_map:
            node_map[c.parent_code].children.append(node)
        else:
            roots.append(node)

    return roots


def _detect_circular_reference(
    db: Session, project_id: UUID
) -> list[str]:
    """使用 DFS 检测循环引用"""
    errors: list[str] = []

    # 获取所有公司
    companies = (
        db.query(Company)
        .filter(
            Company.project_id == project_id,
            Company.is_deleted.is_(False),
        )
        .all()
    )

    # 建立邻接表
    adj: dict[str, str | None] = {}
    code_set: set[str] = set()
    for c in companies:
        adj[c.company_code] = c.parent_code
        code_set.add(c.company_code)

    # DFS 检测
    visited: set[str] = set()
    rec_stack: set[str] = set()
    path: list[str] = []

    def dfs(code: str) -> bool:
        visited.add(code)
        rec_stack.add(code)
        path.append(code)

        parent = adj.get(code)
        if parent and parent in code_set:
            if parent not in visited:
                if dfs(parent):
                    return True
            elif parent in rec_stack:
                cycle = " -> ".join(path[path.index(parent) :] + [parent])
                errors.append(f"检测到循环引用: {cycle}")
                return True

        path.pop()
        rec_stack.remove(code)
        return False

    for code in code_set:
        if code not in visited:
            if dfs(code):
                break

    return errors


# ===================================================================
# GroupStructureService
# ===================================================================


class GroupStructureService:
    """集团结构服务类"""

    def __init__(self, db: Session):
        self.db = db

    # -----------------------------------------------------------------
    # 4.1 公司 CRUD
    # -----------------------------------------------------------------

    def create_company(
        self, project_id: UUID, data: CompanyCreate
    ) -> Company:
        """创建公司"""
        # 验证父公司代码
        if data.parent_code:
            parent = (
                self.db.query(Company)
                .filter(
                    Company.project_id == project_id,
                    Company.company_code == data.parent_code,
                    Company.is_deleted.is_(False),
                )
                .first()
            )
            if not parent:
                raise ValueError(f"父公司代码 '{data.parent_code}' 不存在")

        # 自动计算合并层级
        consol_level = _calculate_consol_level(
            self.db, project_id, data.parent_code
        )

        # 自动计算最终控股代码
        if data.parent_code:
            ultimate_code = _find_ultimate_ancestor(
                self.db, project_id, data.parent_code
            ) or data.parent_code
        else:
            ultimate_code = data.company_code

        # 构建记录
        company = Company(
            project_id=project_id,
            company_code=data.company_code,
            company_name=data.company_name,
            parent_code=data.parent_code,
            consol_level=consol_level,
            ultimate_code=ultimate_code,
            ownership_type=data.ownership_type,
            ownership_percentage=data.ownership_percentage,
            consolidation_method=data.consolidation_method,
            acquisition_date=data.acquisition_date,
            disposal_date=data.disposal_date,
            is_deleted=False,
        )

        self.db.add(company)
        self.db.commit()
        self.db.refresh(company)
        return company

    def get_company(self, company_id: UUID) -> Company | None:
        """获取单个公司"""
        return (
            self.db.query(Company)
            .filter(Company.id == company_id, Company.is_deleted.is_(False))
            .first()
        )

    def get_companies_by_project(
        self, project_id: UUID
    ) -> list[Company]:
        """列出项目中所有公司"""
        return (
            self.db.query(Company)
            .filter(
                Company.project_id == project_id,
                Company.is_deleted.is_(False),
            )
            .order_by(Company.consol_level, Company.company_code)
            .all()
        )

    def update_company(
        self, company_id: UUID, data: CompanyUpdate
    ) -> Company:
        """更新公司"""
        company = self.get_company(company_id)
        if not company:
            raise ValueError("公司不存在")

        old_parent_code = company.parent_code
        old_consol_level = company.consol_level

        # 处理 parent_code 变更
        if data.parent_code is not None and data.parent_code != old_parent_code:
            # 验证新父公司存在
            if data.parent_code:
                parent = (
                    self.db.query(Company)
                    .filter(
                        Company.project_id == company.project_id,
                        Company.company_code == data.parent_code,
                        Company.is_deleted.is_(False),
                    )
                    .first()
                )
                if not parent:
                    raise ValueError(f"父公司代码 '{data.parent_code}' 不存在")
                # 检查不能是自己的后代
                if self._is_descendant(
                    company.project_id, data.parent_code, company.company_code
                ):
                    raise ValueError("不能将公司设置为自己的后代")

            new_level = _calculate_consol_level(
                self.db, company.project_id, data.parent_code
            )
            level_delta = new_level - old_consol_level

            # 更新当前公司
            company.parent_code = data.parent_code
            company.consol_level = new_level

            # 计算新的 ultimate_code
            if data.parent_code:
                company.ultimate_code = (
                    _find_ultimate_ancestor(
                        self.db, company.project_id, data.parent_code
                    )
                    or data.parent_code
                )
            else:
                company.ultimate_code = company.company_code

            # 更新后代公司
            if level_delta != 0:
                _update_descendants_levels(
                    self.db, company.project_id, company.company_code, level_delta
                )

        # 更新其他字段
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key not in ("parent_code",):  # parent_code 已单独处理
                setattr(company, key, value)

        self.db.commit()
        self.db.refresh(company)
        return company

    def _is_descendant(
        self, project_id: UUID, potential_child: str, potential_ancestor: str
    ) -> bool:
        """检查 potential_child 是否是 potential_ancestor 的后代"""
        visited: set[str] = set()

        def dfs(code: str) -> bool:
            if code in visited:
                return False
            visited.add(code)
            children = (
                self.db.query(Company.company_code)
                .filter(
                    Company.project_id == project_id,
                    Company.parent_code == code,
                    Company.is_deleted.is_(False),
                )
                .all()
            )
            for (child_code,) in children:
                if child_code == potential_ancestor:
                    return True
                if dfs(child_code):
                    return True
            return False

        return dfs(potential_child)

    def delete_company(self, company_id: UUID) -> None:
        """软删除公司"""
        company = self.get_company(company_id)
        if not company:
            raise ValueError("公司不存在")

        # 检查是否有子级
        has_children = (
            self.db.query(Company.id)
            .filter(
                Company.project_id == company.project_id,
                Company.parent_code == company.company_code,
                Company.is_deleted.is_(False),
            )
            .first()
        )

        if has_children:
            # 递归软删除所有后代
            self._soft_delete_descendants(company.project_id, company.company_code)

        company.soft_delete()
        self.db.commit()

    def _soft_delete_descendants(self, project_id: UUID, parent_code: str) -> None:
        """递归软删除所有后代"""
        children = (
            self.db.query(Company)
            .filter(
                Company.project_id == project_id,
                Company.parent_code == parent_code,
                Company.is_deleted.is_(False),
            )
            .all()
        )
        for child in children:
            self._soft_delete_descendants(project_id, child.company_code)
            child.soft_delete()

    # -----------------------------------------------------------------
    # 4.2 树结构 & 校验
    # -----------------------------------------------------------------

    def get_group_tree(self, project_id: UUID) -> CompanyTreeResponse:
        """获取集团结构树"""
        companies = self.get_companies_by_project(project_id)
        nodes = _build_tree(companies)
        return CompanyTreeResponse(nodes=nodes)

    def validate_structure(
        self, project_id: UUID
    ) -> StructureValidationResult:
        """校验集团结构"""
        errors: list[str] = []
        warnings: list[str] = []

        companies = self.get_companies_by_project(project_id)
        if not companies:
            warnings.append("项目中没有任何公司")

        # 建立 code -> company 映射
        code_map: dict[str, Company] = {c.company_code: c for c in companies}
        code_set = set(code_map.keys())

        # Check 1: 循环引用检测
        circular_errors = _detect_circular_reference(self.db, project_id)
        errors.extend(circular_errors)

        # Check 2 & 3: 孤儿节点和父代码有效性
        for c in companies:
            if c.parent_code:
                if c.parent_code not in code_set:
                    errors.append(
                        f"公司 '{c.company_code}' ({c.company_name}): "
                        f"父代码 '{c.parent_code}' 不存在"
                    )
                else:
                    parent = code_map[c.parent_code]
                    # Check 4: ultimate_code 正确性
                    expected_ultimate = _find_ultimate_ancestor(
                        self.db, project_id, c.parent_code
                    )
                    if expected_ultimate is None:
                        expected_ultimate = c.parent_code
                    if c.ultimate_code != expected_ultimate:
                        errors.append(
                            f"公司 '{c.company_code}': ultimate_code 错误，"
                            f"应为 '{expected_ultimate}'，当前为 '{c.ultimate_code}'"
                        )

        # 检查是否缺少顶级母公司
        roots = [c for c in companies if c.parent_code is None]
        if len(roots) > 1:
            errors.append(
                f"存在多个顶级母公司: {', '.join(r.company_code for r in roots)}"
            )
        if not roots and companies:
            warnings.append("没有找到顶级母公司")

        # 检查重复的公司代码
        codes = [c.company_code for c in companies]
        if len(codes) != len(set(codes)):
            seen: set[str] = set()
            for code in codes:
                if code in seen:
                    errors.append(f"发现重复的公司代码: '{code}'")
                seen.add(code)

        return StructureValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # -----------------------------------------------------------------
    # 4.3 合并范围管理
    # -----------------------------------------------------------------

    def get_consol_scope(
        self, project_id: UUID, year: int
    ) -> list[ConsolScopeResponse]:
        """获取指定年度合并范围"""
        items = (
            self.db.query(ConsolScope)
            .filter(
                ConsolScope.project_id == project_id,
                ConsolScope.year == year,
                ConsolScope.is_deleted.is_(False),
            )
            .all()
        )
        return [ConsolScopeResponse.model_validate(i) for i in items]

    def manage_consol_scope(
        self,
        project_id: UUID,
        year: int,
        scope_items: list[ConsolScopeCreate],
    ) -> list[ConsolScope]:
        """批量管理合并范围"""
        # 获取上年度范围
        prior_year = year - 1
        prior_scope: dict[str, ConsolScope] = {}
        prior_items = (
            self.db.query(ConsolScope)
            .filter(
                ConsolScope.project_id == project_id,
                ConsolScope.year == prior_year,
                ConsolScope.is_deleted.is_(False),
            )
            .all()
        )
        for item in prior_items:
            prior_scope[item.company_code] = item

        results: list[ConsolScope] = []

        for item in scope_items:
            # 验证排除原因
            if not item.is_included and not item.exclusion_reason:
                raise ValueError(
                    f"公司 '{item.company_code}' 被排除但未提供排除原因"
                )

            # 检查是否已存在
            existing = (
                self.db.query(ConsolScope)
                .filter(
                    ConsolScope.project_id == project_id,
                    ConsolScope.year == year,
                    ConsolScope.company_code == item.company_code,
                )
                .first()
            )

            # 确定变更类型
            prior = prior_scope.get(item.company_code)
            if prior is None:
                change_type = ScopeChangeType.ADDED
            elif prior.is_included and not item.is_included:
                change_type = ScopeChangeType.EXCLUDED
            elif not prior.is_included and item.is_included:
                change_type = ScopeChangeType.INCLUDED
            elif (
                prior.ownership_percentage != item.ownership_percentage
                or prior.consolidation_method != item.consolidation_method
            ):
                change_type = ScopeChangeType.CHANGED
            else:
                change_type = ScopeChangeType.NONE

            if existing:
                for key, value in item.model_dump().items():
                    setattr(existing, key, value)
                existing.scope_change_type = change_type
                results.append(existing)
            else:
                scope = ConsolScope(
                    project_id=project_id,
                    year=year,
                    scope_change_type=change_type,
                    **item.model_dump(),
                )
                self.db.add(scope)
                results.append(scope)

        self.db.commit()
        for r in results:
            self.db.refresh(r)
        return results

    # -----------------------------------------------------------------
    # 4.4 合并期间计算
    # -----------------------------------------------------------------

    @staticmethod
    def get_consolidation_period(
        company: Company, year: int
    ) -> ConsolidationPeriod:
        """根据收购/处置日期确定合并期间"""
        # 假设财政年度为自然年，期末为 12-31
        year_end = date(year, 12, 31)
        year_start = date(year, 1, 1)

        include_pl = True
        include_bs = True
        period_months = 12
        note = "全年合并"

        if company.acquisition_date:
            if company.acquisition_date > year_end:
                include_pl = False
                include_bs = False
                period_months = 0
                note = f"收购日期 ({company.acquisition_date}) 在期末之后，本年度不纳入"
            elif company.acquisition_date > year_start:
                # 部分年度合并
                acq = company.acquisition_date
                if acq.month <= 12:
                    period_months = 12 - acq.month + 1
                    note = f"从 {company.acquisition_date} 开始合并 ({period_months} 个月)"
                    include_pl = True
                    include_bs = True

        if company.disposal_date:
            disp = company.disposal_date
            if disp < year_start:
                include_pl = False
                include_bs = False
                period_months = 0
                note = f"处置日期 ({disp}) 在期初之前，本年度不纳入"
            elif disp <= year_end:
                # 部分年度合并
                if disp.month >= 1:
                    if include_pl or include_bs:
                        # 只在处置月份前合并
                        if company.acquisition_date and company.acquisition_date > year_start:
                            # 部分年度，已有期间
                            new_months = disp.month - company.acquisition_date.month
                            if new_months < period_months:
                                period_months = new_months
                        else:
                            period_months = disp.month
                        note = f"至 {disp} 处置 ({period_months} 个月)"
                        include_pl = True
                        include_bs = True
                    else:
                        note = f"在 {disp} 处置，本年度不纳入"
                        period_months = 0
                        include_pl = False
                        include_bs = False

        return ConsolidationPeriod(
            include_pl=include_pl,
            include_bs=include_bs,
            period_months=period_months,
            note=note,
        )
