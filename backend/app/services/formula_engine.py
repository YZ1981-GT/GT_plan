"""取数公式引擎 — 底稿公式驱动取数 + Redis缓存 + 错误处理

支持5种公式类型：
- TB(account_code, column_name) — 从 trial_balance 取数
- WP(wp_code, cell_ref) — 跨底稿引用（MVP stub）
- AUX(account_code, aux_type, aux_name, column_name) — 从辅助余额表取数
- PREV(inner_formula) — 上年数据（year-1 递归）
- SUM_TB(account_range, column_name) — 科目范围汇总

Validates: Requirements 2.1-2.10
"""

from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbAuxBalance, TrialBalance

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FormulaError
# ---------------------------------------------------------------------------

class FormulaError:
    """公式执行错误对象"""

    def __init__(self, code: str = "FORMULA_ERROR", message: str = ""):
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


# ---------------------------------------------------------------------------
# Column name mapping (Chinese → TrialBalance field)
# ---------------------------------------------------------------------------

TB_COLUMN_MAP: dict[str, str] = {
    "期末余额": "audited_amount",
    "未审数": "unadjusted_amount",
    "AJE调整": "aje_adjustment",
    "RJE调整": "rje_adjustment",
    "年初余额": "opening_balance",
}

AUX_COLUMN_MAP: dict[str, str] = {
    "期初余额": "opening_balance",
    "借方发生额": "debit_amount",
    "贷方发生额": "credit_amount",
    "期末余额": "closing_balance",
}


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

class TBExecutor:
    """TB(account_code, column_name) → 从 trial_balance 取数

    Validates: Requirements 2.1, 2.2
    """

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        params: dict,
    ) -> Decimal | FormulaError:
        account_code = params.get("account_code", "")
        column_name = params.get("column_name", "")

        field = TB_COLUMN_MAP.get(column_name)
        if not field:
            return FormulaError(
                message=f"未知列名'{column_name}'，支持: {', '.join(TB_COLUMN_MAP.keys())}"
            )

        result = await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return FormulaError(message=f"科目{account_code}不存在")

        val = getattr(row, field, None)
        return val if val is not None else Decimal("0")


class WPExecutor:
    """WP(wp_code, cell_ref) → 跨底稿引用（MVP stub）

    Validates: Requirements 2.1, 2.3
    """

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        params: dict,
    ) -> Any | FormulaError:
        wp_code = params.get("wp_code", "")
        cell_ref = params.get("cell_ref", "")

        if not wp_code or not cell_ref:
            return FormulaError(message="WP函数需要wp_code和cell_ref参数")

        # MVP stub: return placeholder
        # Full implementation would query working_paper table for file_path,
        # then use openpyxl to read the cell value
        return FormulaError(
            message=f"WP({wp_code},{cell_ref})暂不支持，MVP阶段请使用离线编辑"
        )


class AUXExecutor:
    """AUX(account_code, aux_type, aux_name, column_name) → 从辅助余额表取数

    Validates: Requirements 2.1, 2.4
    """

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        params: dict,
    ) -> Decimal | FormulaError:
        account_code = params.get("account_code", "")
        aux_type = params.get("aux_type", "")
        aux_name = params.get("aux_name", "")
        column_name = params.get("column_name", "")

        field = AUX_COLUMN_MAP.get(column_name)
        if not field:
            return FormulaError(
                message=f"未知辅助列名'{column_name}'，支持: {', '.join(AUX_COLUMN_MAP.keys())}"
            )

        result = await db.execute(
            sa.select(TbAuxBalance).where(
                TbAuxBalance.project_id == project_id,
                TbAuxBalance.year == year,
                TbAuxBalance.account_code == account_code,
                TbAuxBalance.aux_type == aux_type,
                TbAuxBalance.aux_name == aux_name,
                TbAuxBalance.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return FormulaError(
                message=f"辅助余额不存在: 科目{account_code}, {aux_type}={aux_name}"
            )

        val = getattr(row, field, None)
        return val if val is not None else Decimal("0")


class PREVExecutor:
    """PREV(inner_formula) → 递归调用 year-1

    Validates: Requirements 2.1, 2.5
    """

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        params: dict,
        engine: "FormulaEngine",
    ) -> Any | FormulaError:
        inner_type = params.get("inner_type", "")
        inner_params = params.get("inner_params", {})

        if not inner_type:
            return FormulaError(message="PREV函数需要inner_type参数")

        return await engine.execute(
            db=db,
            project_id=project_id,
            year=year - 1,
            formula_type=inner_type,
            params=inner_params,
        )


class SumTBExecutor:
    """SUM_TB(account_range, column_name) → 科目范围汇总

    Validates: Requirements 2.1, 2.6
    """

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        params: dict,
    ) -> Decimal | FormulaError:
        account_range = params.get("account_range", "")
        column_name = params.get("column_name", "")

        field = TB_COLUMN_MAP.get(column_name)
        if not field:
            return FormulaError(
                message=f"未知列名'{column_name}'，支持: {', '.join(TB_COLUMN_MAP.keys())}"
            )

        parts = account_range.split("~")
        if len(parts) != 2:
            return FormulaError(
                message=f"无效科目范围'{account_range}'，格式应为'start~end'"
            )

        start_code, end_code = parts[0].strip(), parts[1].strip()

        result = await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code >= start_code,
                TrialBalance.standard_account_code <= end_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        rows = result.scalars().all()

        total = Decimal("0")
        for row in rows:
            val = getattr(row, field, None)
            total += val if val is not None else Decimal("0")

        return total


# ---------------------------------------------------------------------------
# FormulaEngine
# ---------------------------------------------------------------------------

class FormulaEngine:
    """取数公式引擎 — 公式类型注册 + Redis缓存 + 批量执行

    Validates: Requirements 2.8, 2.9, 2.10
    """

    FORMULA_TYPES: dict[str, Any] = {
        "TB": TBExecutor,
        "WP": WPExecutor,
        "AUX": AUXExecutor,
        "PREV": PREVExecutor,
        "SUM_TB": SumTBExecutor,
    }

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._executors: dict[str, Any] = {
            k: v() for k, v in self.FORMULA_TYPES.items()
        }

    @staticmethod
    def _cache_key(project_id: UUID, year: int, formula_type: str, params: dict) -> str:
        """Generate Redis cache key"""
        params_hash = hashlib.md5(
            json.dumps(params, sort_keys=True, default=str).encode()
        ).hexdigest()
        return f"formula:{project_id}:{year}:{formula_type}:{params_hash}"

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        formula_type: str,
        params: dict,
    ) -> dict:
        """Execute a single formula. Returns FormulaResult dict.

        Validates: Requirements 2.8, 2.9, 2.10
        """
        # Validate formula type
        if formula_type not in self._executors:
            return {
                "value": None,
                "cached": False,
                "error": f"未知公式类型'{formula_type}'，支持: {', '.join(self.FORMULA_TYPES.keys())}",
            }

        cache_key = self._cache_key(project_id, year, formula_type, params)

        # Check Redis cache
        if self._redis:
            try:
                cached = await self._redis.get(cache_key)
                if cached is not None:
                    return {"value": json.loads(cached), "cached": True, "error": None}
            except Exception:
                logger.warning("Redis cache read failed, proceeding without cache")

        # Execute formula
        executor = self._executors[formula_type]
        if formula_type == "PREV":
            result = await executor.execute(db, project_id, year, params, self)
            # PREV returns a dict from recursive call
            if isinstance(result, dict):
                # Cache the result
                if self._redis and result.get("error") is None:
                    try:
                        await self._redis.set(
                            cache_key,
                            json.dumps(result["value"], default=str),
                            ex=300,  # TTL 5 min
                        )
                    except Exception:
                        logger.warning("Redis cache write failed")
                return result
        else:
            result = await executor.execute(db, project_id, year, params)

        # Handle FormulaError
        if isinstance(result, FormulaError):
            return {"value": None, "cached": False, "error": result.message}

        # Convert Decimal to float for JSON serialization
        value = float(result) if isinstance(result, Decimal) else result

        # Write to cache
        if self._redis:
            try:
                await self._redis.set(
                    cache_key,
                    json.dumps(value, default=str),
                    ex=300,  # TTL 5 min
                )
            except Exception:
                logger.warning("Redis cache write failed")

        return {"value": value, "cached": False, "error": None}

    async def batch_execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        formulas: list[dict],
    ) -> list[dict]:
        """Batch execute formulas. Each item: {formula_type, params}

        Validates: Requirements 2.9
        """
        results = []
        for f in formulas:
            r = await self.execute(
                db=db,
                project_id=project_id,
                year=year,
                formula_type=f.get("formula_type", ""),
                params=f.get("params", {}),
            )
            results.append(r)
        return results

    async def invalidate_cache(
        self,
        project_id: UUID,
        year: int,
        affected_accounts: list[str] | None = None,
    ) -> int:
        """Invalidate formula cache entries.

        affected_accounts=None → invalidate all for project/year
        affected_accounts=[...] → invalidate all (simple approach for MVP)

        Returns count of deleted keys.
        """
        if not self._redis:
            return 0

        try:
            pattern = f"formula:{project_id}:{year}:*"
            deleted = 0
            async for key in self._redis.scan_iter(match=pattern):
                await self._redis.delete(key)
                deleted += 1
            return deleted
        except Exception:
            logger.warning("Redis cache invalidation failed")
            return 0
