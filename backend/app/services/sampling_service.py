"""抽样管理服务 — 抽样配置 + 抽样记录 + 样本量计算 + MUS评价

Validates: Requirements 11.1-11.6, 12.1-12.2
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import (
    SamplingConfig,
    SamplingMethod,
    SamplingRecord,
)


def _to_uuid(val: Any) -> UUID | None:
    """Convert string or UUID to UUID, return None if empty."""
    if val is None:
        return None
    if isinstance(val, UUID):
        return val
    try:
        return UUID(str(val))
    except (ValueError, AttributeError):
        return None


# Confidence factor lookup table
CONFIDENCE_FACTORS: dict[str, float] = {
    "0.90": 2.3,
    "0.9": 2.3,
    "0.95": 3.0,
    "0.99": 4.6,
}


def _get_confidence_factor(confidence_level: Decimal | float | None) -> float:
    """Get confidence factor from confidence level."""
    if confidence_level is None:
        return 3.0  # default 95%
    key = str(float(confidence_level))
    # Try exact match first
    if key in CONFIDENCE_FACTORS:
        return CONFIDENCE_FACTORS[key]
    # Try rounding
    rounded = str(round(float(confidence_level), 2))
    if rounded in CONFIDENCE_FACTORS:
        return CONFIDENCE_FACTORS[rounded]
    # Default to 95%
    return 3.0


class SamplingService:
    """抽样管理服务

    Validates: Requirements 11.1-11.6
    """

    # ------------------------------------------------------------------
    # Sample size calculation
    # ------------------------------------------------------------------

    async def calculate_sample_size(
        self,
        method: str,
        params: dict[str, Any],
    ) -> int:
        """根据抽样方法计算样本量。

        Attribute: sample_size = confidence_factor / tolerable_deviation_rate
          (adjusted for expected_deviation_rate and population_count)
        MUS: sample_size = ceil(population_amount * confidence_factor / tolerable_misstatement)
        Random/Systematic: user-specified or basic formula
        """
        if method == "attribute":
            return self._calc_attribute_sample_size(params)
        elif method == "mus":
            return self._calc_mus_sample_size(params)
        elif method in ("random", "systematic", "stratified"):
            return self._calc_basic_sample_size(params)
        else:
            raise ValueError(f"不支持的抽样方法: {method}")

    def _calc_attribute_sample_size(self, params: dict) -> int:
        """Attribute sampling: confidence_factor / tolerable_deviation_rate"""
        confidence_level = params.get("confidence_level")
        tolerable_deviation_rate = params.get("tolerable_deviation_rate")
        expected_deviation_rate = params.get("expected_deviation_rate", 0)
        population_count = params.get("population_count")

        if not tolerable_deviation_rate or float(tolerable_deviation_rate) <= 0:
            raise ValueError("可容忍偏差率必须大于0")

        cf = _get_confidence_factor(confidence_level)
        tdr = float(tolerable_deviation_rate)
        edr = float(expected_deviation_rate) if expected_deviation_rate else 0.0

        # Basic formula: cf / (tdr - edr)
        denominator = tdr - edr
        if denominator <= 0:
            raise ValueError("可容忍偏差率必须大于预期偏差率")

        sample_size = math.ceil(cf / denominator)

        # Finite population correction if population_count provided
        if population_count and int(population_count) > 0:
            n = int(population_count)
            if sample_size > n:
                sample_size = n
            elif sample_size < n:
                # Finite correction: n_adj = n0 / (1 + n0/N)
                sample_size = math.ceil(sample_size / (1 + sample_size / n))

        return max(sample_size, 1)

    def _calc_mus_sample_size(self, params: dict) -> int:
        """MUS: ceil(population_amount * confidence_factor / tolerable_misstatement)"""
        confidence_level = params.get("confidence_level")
        population_amount = params.get("population_amount")
        tolerable_misstatement = params.get("tolerable_misstatement")

        if not population_amount or float(population_amount) <= 0:
            raise ValueError("总体金额必须大于0")
        if not tolerable_misstatement or float(tolerable_misstatement) <= 0:
            raise ValueError("可容忍错报必须大于0")

        cf = _get_confidence_factor(confidence_level)
        pa = float(population_amount)
        tm = float(tolerable_misstatement)

        sample_size = math.ceil(pa * cf / tm)
        return max(sample_size, 1)

    def _calc_basic_sample_size(self, params: dict) -> int:
        """Random/Systematic/Stratified: user-specified or basic formula."""
        # If user specified a size, use it
        specified = params.get("sample_size") or params.get("calculated_sample_size")
        if specified:
            return max(int(specified), 1)

        # Basic formula using confidence factor and population
        confidence_level = params.get("confidence_level")
        population_count = params.get("population_count")

        if population_count and int(population_count) > 0:
            cf = _get_confidence_factor(confidence_level)
            n = int(population_count)
            # Simple heuristic: cf * sqrt(N)
            sample_size = math.ceil(cf * math.sqrt(n))
            return min(sample_size, n)

        # Fallback
        return 30  # minimum reasonable sample size

    # ------------------------------------------------------------------
    # Config CRUD
    # ------------------------------------------------------------------

    async def create_config(
        self,
        db: AsyncSession,
        project_id: UUID,
        data: dict[str, Any],
        created_by: UUID | None = None,
    ) -> dict:
        """Create sampling config + auto-calculate sample_size."""
        method = data.get("sampling_method", "random")

        # Auto-calculate sample size
        calc_params = {
            "confidence_level": data.get("confidence_level"),
            "expected_deviation_rate": data.get("expected_deviation_rate"),
            "tolerable_deviation_rate": data.get("tolerable_deviation_rate"),
            "tolerable_misstatement": data.get("tolerable_misstatement"),
            "population_amount": data.get("population_amount"),
            "population_count": data.get("population_count"),
        }
        try:
            calculated_size = await self.calculate_sample_size(method, calc_params)
        except (ValueError, ZeroDivisionError):
            calculated_size = None

        config = SamplingConfig(
            project_id=project_id,
            config_name=data.get("config_name", ""),
            sampling_type=data.get("sampling_type", "statistical"),
            sampling_method=method,
            applicable_scenario=data.get("applicable_scenario", "substantive_test"),
            confidence_level=data.get("confidence_level"),
            expected_deviation_rate=data.get("expected_deviation_rate"),
            tolerable_deviation_rate=data.get("tolerable_deviation_rate"),
            tolerable_misstatement=data.get("tolerable_misstatement"),
            population_amount=data.get("population_amount"),
            population_count=data.get("population_count"),
            calculated_sample_size=calculated_size,
            created_by=created_by,
        )
        db.add(config)
        await db.flush()

        return self._config_to_dict(config)

    async def list_configs(
        self,
        db: AsyncSession,
        project_id: UUID,
    ) -> list[dict]:
        """List sampling configs for a project."""
        result = await db.execute(
            sa.select(SamplingConfig)
            .where(
                SamplingConfig.project_id == project_id,
                SamplingConfig.is_deleted == sa.false(),
            )
            .order_by(SamplingConfig.created_at)
        )
        items = result.scalars().all()
        return [self._config_to_dict(c) for c in items]

    async def update_config(
        self,
        db: AsyncSession,
        config_id: UUID,
        data: dict[str, Any],
    ) -> dict:
        """Update sampling config."""
        result = await db.execute(
            sa.select(SamplingConfig).where(SamplingConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise ValueError("抽样配置不存在")

        for key, value in data.items():
            if hasattr(config, key) and key not in ("id", "project_id", "created_by", "created_at"):
                setattr(config, key, value)

        # Recalculate sample size if relevant params changed
        method = config.sampling_method
        if isinstance(method, SamplingMethod):
            method = method.value
        calc_params = {
            "confidence_level": config.confidence_level,
            "expected_deviation_rate": config.expected_deviation_rate,
            "tolerable_deviation_rate": config.tolerable_deviation_rate,
            "tolerable_misstatement": config.tolerable_misstatement,
            "population_amount": config.population_amount,
            "population_count": config.population_count,
        }
        try:
            config.calculated_sample_size = await self.calculate_sample_size(method, calc_params)
        except (ValueError, ZeroDivisionError):
            pass

        await db.flush()
        return self._config_to_dict(config)

    # ------------------------------------------------------------------
    # Record CRUD
    # ------------------------------------------------------------------

    async def create_record(
        self,
        db: AsyncSession,
        project_id: UUID,
        data: dict[str, Any],
        created_by: UUID | None = None,
    ) -> dict:
        """Create sampling record linked to workpaper."""
        record = SamplingRecord(
            project_id=project_id,
            working_paper_id=_to_uuid(data.get("working_paper_id")),
            sampling_config_id=_to_uuid(data.get("sampling_config_id")),
            sampling_purpose=data.get("sampling_purpose", ""),
            population_description=data.get("population_description", ""),
            population_total_amount=data.get("population_total_amount"),
            population_total_count=data.get("population_total_count"),
            sample_size=data.get("sample_size", 0),
            sampling_method_description=data.get("sampling_method_description"),
            deviations_found=data.get("deviations_found"),
            misstatements_found=data.get("misstatements_found"),
            projected_misstatement=data.get("projected_misstatement"),
            upper_misstatement_limit=data.get("upper_misstatement_limit"),
            conclusion=data.get("conclusion"),
            created_by=created_by,
        )
        db.add(record)
        await db.flush()

        return self._record_to_dict(record)

    async def list_records(
        self,
        db: AsyncSession,
        project_id: UUID,
        working_paper_id: UUID | None = None,
    ) -> list[dict]:
        """List sampling records for a project, optionally filtered by working_paper_id."""
        stmt = (
            sa.select(SamplingRecord)
            .where(
                SamplingRecord.project_id == project_id,
                SamplingRecord.is_deleted == sa.false(),
            )
        )
        if working_paper_id is not None:
            stmt = stmt.where(SamplingRecord.working_paper_id == working_paper_id)
        stmt = stmt.order_by(SamplingRecord.created_at)

        result = await db.execute(stmt)
        items = result.scalars().all()
        return [self._record_to_dict(r) for r in items]

    async def update_record(
        self,
        db: AsyncSession,
        record_id: UUID,
        data: dict[str, Any],
    ) -> dict:
        """Update sampling record."""
        result = await db.execute(
            sa.select(SamplingRecord).where(SamplingRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise ValueError("抽样记录不存在")

        for key, value in data.items():
            if hasattr(record, key) and key not in ("id", "project_id", "created_by", "created_at"):
                setattr(record, key, value)

        await db.flush()
        return self._record_to_dict(record)

    # ------------------------------------------------------------------
    # MUS Evaluation
    # ------------------------------------------------------------------

    async def calculate_mus_evaluation(
        self,
        db: AsyncSession,
        record_id: UUID,
        misstatement_details: list[dict],
    ) -> dict:
        """MUS evaluation:
        - For each misstatement: tainting_factor = misstatement_amount / book_value
        - projected_misstatement = sum(tainting_factor * sampling_interval) for each
        - upper_misstatement_limit = projected_misstatement + basic_precision
        - basic_precision = sampling_interval * confidence_factor
        - sampling_interval = population_amount / sample_size
        """
        result = await db.execute(
            sa.select(SamplingRecord).where(SamplingRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise ValueError("抽样记录不存在")

        population_amount = float(record.population_total_amount or 0)
        sample_size = record.sample_size or 1

        if population_amount <= 0 or sample_size <= 0:
            raise ValueError("总体金额和样本量必须大于0")

        sampling_interval = population_amount / sample_size

        # Get confidence factor from linked config
        confidence_factor = 3.0  # default 95%
        if record.sampling_config_id:
            cfg_result = await db.execute(
                sa.select(SamplingConfig).where(
                    SamplingConfig.id == record.sampling_config_id
                )
            )
            cfg = cfg_result.scalar_one_or_none()
            if cfg and cfg.confidence_level:
                confidence_factor = _get_confidence_factor(cfg.confidence_level)

        # Calculate projected misstatement
        detail_results = []
        total_projected = Decimal("0")

        for item in misstatement_details:
            book_value = float(item.get("book_value", 0))
            misstatement_amount = float(item.get("misstatement_amount", 0))

            if book_value == 0:
                tainting_factor = 1.0 if misstatement_amount != 0 else 0.0
            else:
                tainting_factor = abs(misstatement_amount / book_value)

            projected = Decimal(str(tainting_factor * sampling_interval))
            total_projected += projected

            detail_results.append({
                "book_value": book_value,
                "misstatement_amount": misstatement_amount,
                "tainting_factor": round(tainting_factor, 6),
                "projected_misstatement": float(round(projected, 2)),
            })

        basic_precision = Decimal(str(sampling_interval * confidence_factor))
        upper_limit = total_projected + basic_precision

        # Update record
        record.projected_misstatement = round(total_projected, 2)
        record.upper_misstatement_limit = round(upper_limit, 2)
        await db.flush()

        return {
            "projected_misstatement": float(round(total_projected, 2)),
            "upper_misstatement_limit": float(round(upper_limit, 2)),
            "details": detail_results,
        }

    # ------------------------------------------------------------------
    # Completeness check (for QC Rule 10)
    # ------------------------------------------------------------------

    async def check_completeness(
        self,
        db: AsyncSession,
        working_paper_id: UUID,
    ) -> bool:
        """Check if sampling records for this WP have all required fields filled."""
        result = await db.execute(
            sa.select(SamplingRecord)
            .where(
                SamplingRecord.working_paper_id == working_paper_id,
                SamplingRecord.is_deleted == sa.false(),
            )
        )
        records = result.scalars().all()

        if not records:
            # No sampling records — considered complete (no sampling needed)
            return True

        for r in records:
            if not r.sampling_purpose or not r.sampling_purpose.strip():
                return False
            if not r.population_description or not r.population_description.strip():
                return False
            if not r.sample_size or r.sample_size <= 0:
                return False
            if not r.conclusion or not r.conclusion.strip():
                return False

        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _config_to_dict(self, config: SamplingConfig) -> dict:
        return {
            "id": str(config.id),
            "project_id": str(config.project_id),
            "config_name": config.config_name,
            "sampling_type": config.sampling_type.value if hasattr(config.sampling_type, "value") else str(config.sampling_type),
            "sampling_method": config.sampling_method.value if hasattr(config.sampling_method, "value") else str(config.sampling_method),
            "applicable_scenario": config.applicable_scenario.value if hasattr(config.applicable_scenario, "value") else str(config.applicable_scenario),
            "confidence_level": float(config.confidence_level) if config.confidence_level is not None else None,
            "expected_deviation_rate": float(config.expected_deviation_rate) if config.expected_deviation_rate is not None else None,
            "tolerable_deviation_rate": float(config.tolerable_deviation_rate) if config.tolerable_deviation_rate is not None else None,
            "tolerable_misstatement": float(config.tolerable_misstatement) if config.tolerable_misstatement is not None else None,
            "population_amount": float(config.population_amount) if config.population_amount is not None else None,
            "population_count": config.population_count,
            "calculated_sample_size": config.calculated_sample_size,
            "is_deleted": config.is_deleted,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    def _record_to_dict(self, record: SamplingRecord) -> dict:
        return {
            "id": str(record.id),
            "project_id": str(record.project_id),
            "working_paper_id": str(record.working_paper_id) if record.working_paper_id else None,
            "sampling_config_id": str(record.sampling_config_id) if record.sampling_config_id else None,
            "sampling_purpose": record.sampling_purpose,
            "population_description": record.population_description,
            "population_total_amount": float(record.population_total_amount) if record.population_total_amount is not None else None,
            "population_total_count": record.population_total_count,
            "sample_size": record.sample_size,
            "sampling_method_description": record.sampling_method_description,
            "deviations_found": record.deviations_found,
            "misstatements_found": float(record.misstatements_found) if record.misstatements_found is not None else None,
            "projected_misstatement": float(record.projected_misstatement) if record.projected_misstatement is not None else None,
            "upper_misstatement_limit": float(record.upper_misstatement_limit) if record.upper_misstatement_limit is not None else None,
            "conclusion": record.conclusion,
            "is_deleted": record.is_deleted,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }
