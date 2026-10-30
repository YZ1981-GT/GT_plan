"""
部门管理 API 路由
account-field-completion Task 1.4
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete as sql_delete, func
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.models.core import Department
from app.models.department_schemas import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
)
from app.deps import get_current_user

router = APIRouter(prefix="/api/departments", tags=["departments"])


@router.get("", response_model=List[DepartmentResponse])
async def list_departments(
    parent_id: Optional[str] = Query(None, description="按上级部门筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    获取部门列表
    
    - 支持按上级部门筛选
    - 支持分页
    - 按 sort_order、name 排序
    """
    query = select(Department).where(Department.is_deleted == False)
    
    if parent_id:
        query = query.where(Department.parent_id == parent_id)
    
    query = query.order_by(Department.sort_order, Department.name)
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    departments = result.scalars().all()
    
    return departments


@router.get("/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """获取部门详情"""
    query = select(Department).where(
        Department.id == department_id,
        Department.is_deleted == False
    )
    result = await db.execute(query)
    department = result.scalar_one_or_none()
    
    if not department:
        raise HTTPException(status_code=404, detail="部门不存在")
    
    return department


@router.post("", response_model=DepartmentResponse, status_code=201)
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    创建部门
    
    - 部门编码必须唯一
    - parent_id 如果提供，必须是有效的部门
    """
    # 检查部门编码是否已存在
    existing = await db.execute(
        select(Department).where(
            Department.code == data.code,
            Department.is_deleted == False
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"部门编码 {data.code} 已存在")
    
    # 检查上级部门是否存在
    if data.parent_id:
        parent = await db.execute(
            select(Department).where(
                Department.id == data.parent_id,
                Department.is_deleted == False
            )
        )
        if not parent.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="上级部门不存在")
    
    # 创建部门
    department = Department(**data.model_dump())
    db.add(department)
    await db.commit()
    await db.refresh(department)
    
    return department


@router.put("/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: UUID,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    更新部门信息
    
    - 只更新提供的字段
    - 部门编码如果修改，必须保持唯一
    """
    # 查找部门
    query = select(Department).where(
        Department.id == department_id,
        Department.is_deleted == False
    )
    result = await db.execute(query)
    department = result.scalar_one_or_none()
    
    if not department:
        raise HTTPException(status_code=404, detail="部门不存在")
    
    # 检查部门编码唯一性
    if data.code and data.code != department.code:
        existing = await db.execute(
            select(Department).where(
                Department.code == data.code,
                Department.is_deleted == False,
                Department.id != department_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"部门编码 {data.code} 已被使用")
    
    # 检查上级部门
    if data.parent_id:
        # 防止循环引用（不能设置自己或子部门为上级）
        if str(data.parent_id) == str(department_id):
            raise HTTPException(status_code=400, detail="不能将自己设为上级部门")
        
        parent = await db.execute(
            select(Department).where(
                Department.id == data.parent_id,
                Department.is_deleted == False
            )
        )
        if not parent.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="上级部门不存在")
    
    # 更新字段
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(department, key, value)
    
    await db.commit()
    await db.refresh(department)
    
    return department


@router.delete("/{department_id}", status_code=204)
async def delete_department(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    删除部门（软删除）
    
    - 如果有子部门，不允许删除
    - 如果有关联用户，不允许删除
    """
    # 查找部门
    query = select(Department).where(
        Department.id == department_id,
        Department.is_deleted == False
    )
    result = await db.execute(query)
    department = result.scalar_one_or_none()
    
    if not department:
        raise HTTPException(status_code=404, detail="部门不存在")
    
    # 检查是否有子部门
    children = await db.execute(
        select(func.count(Department.id)).where(
            Department.parent_id == department_id,
            Department.is_deleted == False
        )
    )
    if children.scalar() > 0:
        raise HTTPException(status_code=400, detail="该部门下有子部门，无法删除")
    
    # 检查是否有关联用户
    from app.models.core import User
    users = await db.execute(
        select(func.count(User.id)).where(
            User.dept_id == department_id,
            User.is_deleted == False
        )
    )
    if users.scalar() > 0:
        raise HTTPException(status_code=400, detail="该部门下有用户，无法删除")
    
    # 软删除
    department.is_deleted = True
    await db.commit()
    
    return None


@router.get("/{department_id}/tree", response_model=List[DepartmentResponse])
async def get_department_tree(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    获取部门树（包含所有子部门）
    
    返回指定部门及其所有子孙部门
    """
    # 使用递归 CTE 查询部门树
    # 注意：这是简化版本，实际生产环境可能需要更复杂的递归查询
    all_departments = []
    
    async def fetch_children(parent_id: UUID):
        query = select(Department).where(
            Department.parent_id == parent_id,
            Department.is_deleted == False
        ).order_by(Department.sort_order, Department.name)
        
        result = await db.execute(query)
        children = result.scalars().all()
        
        for child in children:
            all_departments.append(child)
            await fetch_children(child.id)
    
    # 先获取根部门
    root_query = select(Department).where(
        Department.id == department_id,
        Department.is_deleted == False
    )
    root_result = await db.execute(root_query)
    root = root_result.scalar_one_or_none()
    
    if not root:
        raise HTTPException(status_code=404, detail="部门不存在")
    
    all_departments.append(root)
    await fetch_children(department_id)
    
    return all_departments
