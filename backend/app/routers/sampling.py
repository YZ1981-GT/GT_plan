"""抽样管理 API 路由

- GET    /api/projects/{id}/sampling-configs              — 抽样配置列表
- POST   /api/projects/{id}/sampling-configs              — 创建抽样配置
- PUT    /api/projects/{id}/sampling-configs/{config_id}  — 更新抽样配置
- POST   /api/projects/{id}/sampling-configs/calculate    — 计算样本量
- GET    /api/projects/{id}/sampling-records              — 抽样记录列表
- POST   /api/projects/{id}/sampling-records              — 创建抽样记录
- PUT    /api/projects/{id}/sampling-records/{record_id}  — 更新抽样记录
- POST   /api/projects/{id}/sampling-records/{record_id}/mus-evaluate — MUS评价

Validates: Requirements 11.1-11.6
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.sampling_service import SamplingService

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["sampling"],
)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class SamplingConfigCreateRequest(BaseModel):
    config_name: str
    sampling_type: str = "statistical"
    sampling_method: str = "random"
    applicable_scenario: str = "substantive_test"
    confidence_level: float | None = None
    expected_deviation_rate: float | None = None
    tolerable_deviation_rate: float | None = None
    tolerable_misstatement: float | None = None
    population_amount: float | None = None
    population_count: int | None = None


class SamplingConfigUpdateRequest(BaseModel):
    config_name: str | None = None
    sampling_type: str | None = None
    sampling_method: str | None = None
    applicable_scenario: str | None = None
    confidence_level: float | None = None
    expected_deviation_rate: float | None = None
    tolerable_deviation_rate: float | None = None
    tolerable_misstatement: float | None = None
    population_amount: float | None = None
    population_count: int | None = None


class CalculateSampleSizeRequest(BaseModel):
    method: str
    confidence_level: float | None = None
    expected_deviation_rate: float | None = None
    tolerable_deviation_rate: float | None = None
    tolerable_misstatement: float | None = None
    population_amount: float | None = None
    population_count: int | None = None
    sample_size: int | None = None


class SamplingRecordCreateRequest(BaseModel):
    working_paper_id: UUID | None = None
    sampling_config_id: UUID | None = None
    sampling_purpose: str
    population_description: str
    population_total_amount: float | None = None
    population_total_count: int | None = None
    sample_size: int
    sampling_method_description: str | None = None
    deviations_found: int | None = None
    misstatements_found: float | None = None
    projected_misstatement: float | None = None
    upper_misstatement_limit: float | None = None
    conclusion: str | None = None


class SamplingRecordUpdateRequest(BaseModel):
    working_paper_id: UUID | None = None
    sampling_config_id: UUID | None = None
    sampling_purpose: str | None = None
    population_description: str | None = None
    population_total_amount: float | None = None
    population_total_count: int | None = None
    sample_size: int | None = None
    sampling_method_description: str | None = None
    deviations_found: int | None = None
    misstatements_found: float | None = None
    projected_misstatement: float | None = None
    upper_misstatement_limit: float | None = None
    conclusion: str | None = None


class MUSEvaluateRequest(BaseModel):
    misstatement_details: list[dict]


# ---------------------------------------------------------------------------
# Sampling Config endpoints
# ---------------------------------------------------------------------------

@router.get("/sampling-configs")
async def list_sampling_configs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """抽样配置列表"""
    svc = SamplingService()
    return await svc.list_configs(db=db, project_id=project_id)


@router.post("/sampling-configs")
async def create_sampling_config(
    project_id: UUID,
    data: SamplingConfigCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建抽样配置"""
    svc = SamplingService()
    try:
        result = await svc.create_config(
            db=db,
            project_id=project_id,
            data=data.model_dump(exclude_none=True),
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/sampling-configs/{config_id}")
async def update_sampling_config(
    project_id: UUID,
    config_id: UUID,
    data: SamplingConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """更新抽样配置"""
    svc = SamplingService()
    try:
        result = await svc.update_config(
            db=db,
            config_id=config_id,
            data=data.model_dump(exclude_none=True),
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sampling-configs/calculate")
async def calculate_sample_size(
    project_id: UUID,
    data: CalculateSampleSizeRequest,
    db: AsyncSession = Depends(get_db),
):
    """计算样本量"""
    svc = SamplingService()
    try:
        params = data.model_dump(exclude_none=True)
        method = params.pop("method")
        size = await svc.calculate_sample_size(method=method, params=params)
        return {"method": method, "params": params, "calculated_size": size}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Sampling Record endpoints
# ---------------------------------------------------------------------------

@router.get("/sampling-records")
async def list_sampling_records(
    project_id: UUID,
    working_paper_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """抽样记录列表"""
    svc = SamplingService()
    return await svc.list_records(
        db=db,
        project_id=project_id,
        working_paper_id=working_paper_id,
    )


@router.post("/sampling-records")
async def create_sampling_record(
    project_id: UUID,
    data: SamplingRecordCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建抽样记录"""
    svc = SamplingService()
    try:
        result = await svc.create_record(
            db=db,
            project_id=project_id,
            data=data.model_dump(exclude_none=True),
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/sampling-records/{record_id}")
async def update_sampling_record(
    project_id: UUID,
    record_id: UUID,
    data: SamplingRecordUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """更新抽样记录"""
    svc = SamplingService()
    try:
        result = await svc.update_record(
            db=db,
            record_id=record_id,
            data=data.model_dump(exclude_none=True),
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sampling-records/{record_id}/mus-evaluate")
async def mus_evaluate(
    project_id: UUID,
    record_id: UUID,
    data: MUSEvaluateRequest,
    db: AsyncSession = Depends(get_db),
):
    """MUS评价计算"""
    svc = SamplingService()
    try:
        result = await svc.calculate_mus_evaluation(
            db=db,
            record_id=record_id,
            misstatement_details=data.misstatement_details,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
