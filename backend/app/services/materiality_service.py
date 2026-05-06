"""重要性水平计算服务

覆盖：
- calculate: 三级重要性水平计算
- auto_populate_benchmark: 从试算表自动取基准金额
- override: 手动覆盖 + 记录原因
- get_change_history: 变更历史
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountCategory,
    Materiality,
    TrialBalance,
)
from app.models.audit_platform_schemas import (
    MaterialityChange,
    MaterialityInput,
    MaterialityOverride,
    MaterialityResult,
)


class MaterialityService:
    """重要性水平计算引擎"""

    # 基准类型 → 试算表科目类别/名称映射
    BENCHMARK_MAPPING: dict[str, dict] = {
        "pre_tax_profit": {
            "type": "accounts",
            "names": ["营业利润", "营业外收入", "营业外支出"],
        },
        "revenue": {
            "type": "accounts",
            "names": ["营业收入", "主营业务收入"],
        },
        "total_assets": {
            "type": "category_sum",
            "categories": [AccountCategory.asset],
        },
        "net_assets": {
            "type": "category_diff",
            "plus": [AccountCategory.asset],
            "minus": [AccountCategory.liability],
        },
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 15.1 calculate
    # ------------------------------------------------------------------
    async def calculate(
        self,
        project_id: UUID,
        year: int,
        params: MaterialityInput,
        calculated_by: UUID | None = None,
    ) -> MaterialityResult:
        """
        计算三级重要性水平：
        - 整体重要性 = 基准金额 × 百分比
        - 实际执行重要性 = 整体重要性 × 执行比例
        - 明显微小错报 = 整体重要性 × 微小比例
        """
        benchmark = params.benchmark_amount
        pct = params.overall_percentage / Decimal("100")
        overall = (benchmark * pct).quantize(Decimal("0.01"))

        perf_ratio = params.performance_ratio / Decimal("100")
        performance = (overall * perf_ratio).quantize(Decimal("0.01"))

        trivial_ratio = params.trivial_ratio / Decimal("100")
        trivial = (overall * trivial_ratio).quantize(Decimal("0.01"))

        now = datetime.now(timezone.utc)

        # 查找已有记录
        existing = await self._get_current(project_id, year)

        if existing:
            # 记录变更历史（保存旧值到 notes JSON）
            old_snapshot = self._snapshot(existing)
            existing.benchmark_type = params.benchmark_type
            existing.benchmark_amount = benchmark
            existing.overall_percentage = params.overall_percentage
            existing.overall_materiality = overall
            existing.performance_ratio = params.performance_ratio
            existing.performance_materiality = performance
            existing.trivial_ratio = params.trivial_ratio
            existing.trivial_threshold = trivial
            existing.is_override = False
            existing.override_reason = None
            existing.notes = params.notes
            existing.calculated_by = calculated_by
            existing.calculated_at = now
            # 追加变更历史
            self._append_history(existing, old_snapshot, "recalculate", calculated_by)
            row = existing
        else:
            row = Materiality(
                project_id=project_id,
                year=year,
                benchmark_type=params.benchmark_type,
                benchmark_amount=benchmark,
                overall_percentage=params.overall_percentage,
                overall_materiality=overall,
                performance_ratio=params.performance_ratio,
                performance_materiality=performance,
                trivial_ratio=params.trivial_ratio,
                trivial_threshold=trivial,
                is_override=False,
                notes=params.notes,
                calculated_by=calculated_by,
                calculated_at=now,
            )
            self.db.add(row)

        await self.db.flush()

        return MaterialityResult(
            id=row.id,
            project_id=row.project_id,
            year=row.year,
            benchmark_type=row.benchmark_type,
            benchmark_amount=row.benchmark_amount,
            overall_percentage=row.overall_percentage,
            overall_materiality=row.overall_materiality,
            performance_ratio=row.performance_ratio,
            performance_materiality=row.performance_materiality,
            trivial_ratio=row.trivial_ratio,
            trivial_threshold=row.trivial_threshold,
            is_override=row.is_override,
            override_reason=row.override_reason,
            notes=row.notes,
            calculated_by=row.calculated_by,
            calculated_at=row.calculated_at,
        )

    # ------------------------------------------------------------------
    # 15.2 auto_populate_benchmark
    # ------------------------------------------------------------------
    async def auto_populate_benchmark(
        self,
        project_id: UUID,
        year: int,
        benchmark_type: str,
        company_code: str = "001",
    ) -> Decimal:
        """从试算表自动取基准金额"""
        mapping = self.BENCHMARK_MAPPING.get(benchmark_type)
        if not mapping:
            raise ValueError(f"不支持的基准类型: {benchmark_type}")

        tb = TrialBalance.__table__

        if mapping["type"] == "accounts":
            # 按科目名称匹配
            names = mapping["names"]
            q = (
                sa.select(
                    sa.func.coalesce(
                        sa.func.sum(tb.c.unadjusted_amount), 0
                    ).label("total")
                )
                .where(
                    tb.c.project_id == project_id,
                    tb.c.year == year,
                    tb.c.company_code == company_code,
                    tb.c.is_deleted == sa.false(),
                    tb.c.account_name.in_(names),
                )
            )
            result = await self.db.execute(q)
            total = result.scalar_one()
            return Decimal(str(total))

        elif mapping["type"] == "category_sum":
            categories = [c.value for c in mapping["categories"]]
            q = (
                sa.select(
                    sa.func.coalesce(
                        sa.func.sum(tb.c.unadjusted_amount), 0
                    ).label("total")
                )
                .where(
                    tb.c.project_id == project_id,
                    tb.c.year == year,
                    tb.c.company_code == company_code,
                    tb.c.is_deleted == sa.false(),
                    tb.c.account_category.in_(categories),
                )
            )
            result = await self.db.execute(q)
            total = result.scalar_one()
            return Decimal(str(total))

        elif mapping["type"] == "category_diff":
            plus_cats = [c.value for c in mapping["plus"]]
            minus_cats = [c.value for c in mapping["minus"]]

            # 资产合计
            q_plus = (
                sa.select(
                    sa.func.coalesce(
                        sa.func.sum(tb.c.unadjusted_amount), 0
                    ).label("total")
                )
                .where(
                    tb.c.project_id == project_id,
                    tb.c.year == year,
                    tb.c.company_code == company_code,
                    tb.c.is_deleted == sa.false(),
                    tb.c.account_category.in_(plus_cats),
                )
            )
            r_plus = await self.db.execute(q_plus)
            total_plus = Decimal(str(r_plus.scalar_one()))

            # 负债合计
            q_minus = (
                sa.select(
                    sa.func.coalesce(
                        sa.func.sum(tb.c.unadjusted_amount), 0
                    ).label("total")
                )
                .where(
                    tb.c.project_id == project_id,
                    tb.c.year == year,
                    tb.c.company_code == company_code,
                    tb.c.is_deleted == sa.false(),
                    tb.c.account_category.in_(minus_cats),
                )
            )
            r_minus = await self.db.execute(q_minus)
            total_minus = Decimal(str(r_minus.scalar_one()))

            return total_plus - total_minus

        raise ValueError(f"未知的映射类型: {mapping['type']}")

    # ------------------------------------------------------------------
    # 15.3 override + get_change_history
    # ------------------------------------------------------------------
    async def override(
        self,
        project_id: UUID,
        year: int,
        overrides: MaterialityOverride,
        overridden_by: UUID | None = None,
    ) -> MaterialityResult:
        """手动覆盖任意计算值，记录覆盖原因"""
        existing = await self._get_current(project_id, year)
        if not existing:
            raise ValueError("尚未计算重要性水平，请先执行计算")

        old_snapshot = self._snapshot(existing)

        if overrides.overall_materiality is not None:
            existing.overall_materiality = overrides.overall_materiality
        if overrides.performance_materiality is not None:
            existing.performance_materiality = overrides.performance_materiality
        if overrides.trivial_threshold is not None:
            existing.trivial_threshold = overrides.trivial_threshold

        existing.is_override = True
        existing.override_reason = overrides.override_reason
        existing.calculated_at = datetime.now(timezone.utc)
        existing.calculated_by = overridden_by

        self._append_history(existing, old_snapshot, overrides.override_reason, overridden_by)

        await self.db.flush()

        return MaterialityResult(
            id=existing.id,
            project_id=existing.project_id,
            year=existing.year,
            benchmark_type=existing.benchmark_type,
            benchmark_amount=existing.benchmark_amount,
            overall_percentage=existing.overall_percentage,
            overall_materiality=existing.overall_materiality,
            performance_ratio=existing.performance_ratio,
            performance_materiality=existing.performance_materiality,
            trivial_ratio=existing.trivial_ratio,
            trivial_threshold=existing.trivial_threshold,
            is_override=existing.is_override,
            override_reason=existing.override_reason,
            notes=existing.notes,
            calculated_by=existing.calculated_by,
            calculated_at=existing.calculated_at,
        )

    async def get_change_history(
        self,
        project_id: UUID,
        year: int,
    ) -> list[MaterialityChange]:
        """获取重要性水平变更历史"""
        existing = await self._get_current(project_id, year)
        if not existing:
            return []

        import json
        raw = existing.notes or ""
        # 变更历史存储在 notes 字段的 JSON 数组中，以 __HISTORY__ 标记分隔
        marker = "__HISTORY__"
        if marker not in raw:
            return []

        history_json = raw.split(marker, 1)[1].strip()
        if not history_json:
            return []

        try:
            entries = json.loads(history_json)
        except (json.JSONDecodeError, TypeError):
            return []

        changes = []
        for entry in entries:
            for field_name, values in entry.get("changes", {}).items():
                changes.append(MaterialityChange(
                    changed_at=datetime.fromisoformat(entry["changed_at"]),
                    changed_by=entry.get("changed_by"),
                    field_name=field_name,
                    old_value=str(values.get("old")) if values.get("old") is not None else None,
                    new_value=str(values.get("new")) if values.get("new") is not None else None,
                    reason=entry.get("reason"),
                ))
        return changes

    # ------------------------------------------------------------------
    # 获取当前重要性水平
    # ------------------------------------------------------------------
    async def get_current(
        self,
        project_id: UUID,
        year: int,
    ) -> MaterialityResult | None:
        """获取当前重要性水平"""
        row = await self._get_current(project_id, year)
        if not row:
            return None
        return MaterialityResult(
            id=row.id,
            project_id=row.project_id,
            year=row.year,
            benchmark_type=row.benchmark_type,
            benchmark_amount=row.benchmark_amount,
            overall_percentage=row.overall_percentage,
            overall_materiality=row.overall_materiality,
            performance_ratio=row.performance_ratio,
            performance_materiality=row.performance_materiality,
            trivial_ratio=row.trivial_ratio,
            trivial_threshold=row.trivial_threshold,
            is_override=row.is_override,
            override_reason=row.override_reason,
            notes=row.notes.split("__HISTORY__")[0].strip() if row.notes and "__HISTORY__" in row.notes else row.notes,
            calculated_by=row.calculated_by,
            calculated_at=row.calculated_at,
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    async def _get_current(self, project_id: UUID, year: int) -> Materiality | None:
        result = await self.db.execute(
            sa.select(Materiality).where(
                Materiality.project_id == project_id,
                Materiality.year == year,
                Materiality.is_deleted == sa.false(),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _snapshot(row: Materiality) -> dict:
        return {
            "benchmark_type": row.benchmark_type,
            "benchmark_amount": str(row.benchmark_amount),
            "overall_percentage": str(row.overall_percentage),
            "overall_materiality": str(row.overall_materiality),
            "performance_ratio": str(row.performance_ratio),
            "performance_materiality": str(row.performance_materiality),
            "trivial_ratio": str(row.trivial_ratio),
            "trivial_threshold": str(row.trivial_threshold),
        }

    @staticmethod
    def _append_history(
        row: Materiality,
        old_snapshot: dict,
        reason: str | None,
        changed_by: UUID | None,
    ) -> None:
        """将变更历史追加到 notes 字段"""
        import json

        new_snapshot = MaterialityService._snapshot(row)
        changes = {}
        for key in old_snapshot:
            if old_snapshot[key] != new_snapshot[key]:
                changes[key] = {"old": old_snapshot[key], "new": new_snapshot[key]}

        if not changes:
            return

        entry = {
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "changed_by": str(changed_by) if changed_by else None,
            "reason": reason,
            "changes": changes,
        }

        marker = "__HISTORY__"
        raw = row.notes or ""
        if marker in raw:
            user_notes, history_json = raw.split(marker, 1)
            try:
                entries = json.loads(history_json.strip())
            except (json.JSONDecodeError, TypeError):
                entries = []
        else:
            user_notes = raw
            entries = []

        entries.append(entry)
        row.notes = user_notes.rstrip() + f"\n{marker}\n" + json.dumps(entries, ensure_ascii=False)
