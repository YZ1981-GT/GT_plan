"""报表格式配置服务

功能：
- 加载种子数据到 report_config 表
- 克隆标准配置为项目级配置
- 查询/修改报表配置
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReportType, ReportConfig

logger = logging.getLogger(__name__)

SEED_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "report_config_seed.json"


class ReportConfigService:
    """报表格式配置服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 加载种子数据
    # ------------------------------------------------------------------
    async def load_seed_data(self) -> int:
        """将种子 JSON 加载到 report_config 表，返回插入行数。
        跳过已存在的行（按 report_type + row_code + applicable_standard 判重）。
        """
        with open(SEED_DATA_PATH, encoding="utf-8-sig") as f:
            seed = json.load(f)

        count = 0
        for report_block in seed:
            report_type = report_block["report_type"]
            standard = report_block["applicable_standard"]
            for row in report_block["rows"]:
                # 检查是否已存在
                existing = await self.db.execute(
                    sa.select(ReportConfig.id).where(
                        ReportConfig.report_type == FinancialReportType(report_type),
                        ReportConfig.row_code == row["row_code"],
                        ReportConfig.applicable_standard == standard,
                        ReportConfig.is_deleted == sa.false(),
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    continue

                rc = ReportConfig(
                    report_type=FinancialReportType(report_type),
                    row_number=row["row_number"],
                    row_code=row["row_code"],
                    row_name=row["row_name"],
                    indent_level=row.get("indent_level", 0),
                    formula=row.get("formula"),
                    formula_category=row.get("formula_category"),
                    formula_description=row.get("formula_description"),
                    formula_source=row.get("formula_source"),
                    applicable_standard=standard,
                    is_total_row=row.get("is_total_row", False),
                    parent_row_code=row.get("parent_row_code"),
                )
                self.db.add(rc)
                count += 1

        await self.db.flush()
        return count

    # ------------------------------------------------------------------
    # 查询配置列表
    # ------------------------------------------------------------------
    async def list_configs(
        self,
        report_type: FinancialReportType | None = None,
        applicable_standard: str = "enterprise",
    ) -> list[ReportConfig]:
        """查询报表配置行列表"""
        q = (
            sa.select(ReportConfig)
            .where(
                ReportConfig.applicable_standard == applicable_standard,
                ReportConfig.is_deleted == sa.false(),
            )
            .order_by(ReportConfig.report_type, ReportConfig.row_number)
        )
        if report_type is not None:
            q = q.where(ReportConfig.report_type == report_type)

        result = await self.db.execute(q)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # 查询单行详情
    # ------------------------------------------------------------------
    async def get_config(self, config_id: UUID) -> ReportConfig | None:
        """按 ID 查询单行配置"""
        result = await self.db.execute(
            sa.select(ReportConfig).where(
                ReportConfig.id == config_id,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # 克隆配置
    # ------------------------------------------------------------------
    async def clone_report_config(
        self,
        project_id: UUID,
        applicable_standard: str = "enterprise",
    ) -> int:
        """将标准配置复制为项目级配置。

        项目级配置的 applicable_standard 格式为 "project:{project_id}"，
        支持后续自定义修改而不影响标准模板。
        返回克隆的行数。
        """
        project_standard = f"project:{project_id}"

        # 检查是否已克隆
        existing = await self.db.execute(
            sa.select(sa.func.count()).select_from(ReportConfig).where(
                ReportConfig.applicable_standard == project_standard,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        if (existing.scalar() or 0) > 0:
            raise ValueError("该项目已存在克隆配置，请勿重复克隆")

        # 加载标准配置
        source_rows = await self.list_configs(applicable_standard=applicable_standard)
        if not source_rows:
            raise ValueError(f"未找到标准 '{applicable_standard}' 的配置数据")

        count = 0
        for src in source_rows:
            clone = ReportConfig(
                report_type=src.report_type,
                row_number=src.row_number,
                row_code=src.row_code,
                row_name=src.row_name,
                indent_level=src.indent_level,
                formula=src.formula,
                applicable_standard=project_standard,
                is_total_row=src.is_total_row,
                parent_row_code=src.parent_row_code,
            )
            self.db.add(clone)
            count += 1

        await self.db.flush()
        return count

    # ------------------------------------------------------------------
    # 修改配置行
    # ------------------------------------------------------------------
    async def update_config(
        self,
        config_id: UUID,
        updates: dict,
    ) -> ReportConfig:
        """修改报表配置行（仅允许修改项目级配置）"""
        row = await self.get_config(config_id)
        if row is None:
            raise ValueError("配置行不存在")

        allowed_fields = {"row_name", "indent_level", "formula", "is_total_row", "parent_row_code", "formula_category", "formula_description", "formula_source"}
        for key, value in updates.items():
            if key in allowed_fields:
                setattr(row, key, value)

        await self.db.flush()
        return row
