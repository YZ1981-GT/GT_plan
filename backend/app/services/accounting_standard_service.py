"""多准则适配服务

功能：
- 加载会计准则种子数据（幂等）
- 查询准则列表/详情
- 切换项目会计准则
- 获取准则对应的标准科目表
- 获取准则对应的报表格式配置
- 获取准则对应的附注模版配置

Validates: Requirements 3.1-3.4
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.extension_models import AccountingStandard, ACCOUNTING_STANDARD_SEEDS

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class AccountingStandardService:
    """会计准则服务"""

    async def load_seed_data(self, db: AsyncSession) -> dict:
        """加载会计准则种子数据（幂等：已存在则跳过）"""
        result = await db.execute(
            sa.select(sa.func.count()).select_from(AccountingStandard)
        )
        existing_count = result.scalar() or 0
        if existing_count > 0:
            return {"loaded": 0, "existing": existing_count, "message": "种子数据已存在"}

        loaded = 0
        for item in ACCOUNTING_STANDARD_SEEDS:
            std = AccountingStandard(
                standard_code=item["standard_code"],
                standard_name=item["standard_name"],
                standard_description=item.get("standard_description"),
            )
            db.add(std)
            loaded += 1
        await db.flush()
        return {"loaded": loaded, "existing": 0, "message": f"已加载 {loaded} 条准则数据"}

    async def list_standards(self, db: AsyncSession) -> list[dict]:
        """列出所有活跃准则"""
        stmt = (
            sa.select(AccountingStandard)
            .where(AccountingStandard.is_active == sa.true())
            .order_by(AccountingStandard.standard_code)
        )
        result = await db.execute(stmt)
        return [self._to_dict(s) for s in result.scalars().all()]

    async def get_standard(self, db: AsyncSession, standard_id: UUID) -> dict | None:
        """获取准则详情"""
        result = await db.execute(
            sa.select(AccountingStandard).where(AccountingStandard.id == standard_id)
        )
        std = result.scalar_one_or_none()
        return self._to_dict(std) if std else None

    async def switch_project_standard(
        self, db: AsyncSession, project_id: UUID, standard_id: UUID
    ) -> dict:
        """切换项目会计准则"""
        # 验证准则存在
        std_result = await db.execute(
            sa.select(AccountingStandard).where(AccountingStandard.id == standard_id)
        )
        std = std_result.scalar_one_or_none()
        if not std:
            raise ValueError("会计准则不存在")

        # 获取项目
        proj_result = await db.execute(
            sa.select(Project).where(Project.id == project_id)
        )
        project = proj_result.scalar_one_or_none()
        if not project:
            raise ValueError("项目不存在")

        warning = None
        if project.accounting_standard_id is not None:
            warning = "项目已有会计准则设置，切换可能影响已有数据"

        project.accounting_standard_id = standard_id
        await db.flush()

        return {
            "project_id": str(project_id),
            "standard_id": str(standard_id),
            "standard_name": std.standard_name,
            "warning": warning,
        }

    # ------------------------------------------------------------------
    # 准则科目表 / 报表格式 / 附注模版
    # ------------------------------------------------------------------

    def get_standard_chart(self, standard_code: str) -> dict:
        """获取准则对应的标准科目表"""
        if standard_code == "CAS":
            chart_path = DATA_DIR / "standard_account_chart.json"
            if chart_path.exists():
                with open(chart_path, encoding="utf-8-sig") as f:
                    return json.load(f)
            return {"standard": "CAS", "accounts": []}

        multi_path = DATA_DIR / "multi_standard_charts.json"
        if not multi_path.exists():
            return {"standard_code": standard_code, "accounts": []}
        with open(multi_path, encoding="utf-8-sig") as f:
            data = json.load(f)

        # Map SME -> CAS_SMALL for backward compat
        lookup = standard_code
        if standard_code == "SME":
            lookup = "CAS_SMALL"

        std_data = data.get("standards", {}).get(lookup)
        if not std_data:
            return {"standard_code": standard_code, "accounts": []}
        if "reference" in std_data:
            return self.get_standard_chart("CAS")
        return std_data

    def get_standard_report_formats(self, standard_code: str) -> dict:
        """获取准则对应的报表格式配置"""
        fmt_path = DATA_DIR / "multi_standard_report_formats.json"
        if not fmt_path.exists():
            return {"standard_code": standard_code, "reports": {}}
        with open(fmt_path, encoding="utf-8-sig") as f:
            data = json.load(f)
        lookup = "CAS_SMALL" if standard_code == "SME" else standard_code
        std_data = data.get("standards", {}).get(lookup)
        if not std_data:
            return {"standard_code": standard_code, "reports": {}}
        return {"standard_code": standard_code, "reports": std_data}

    def get_standard_note_templates(self, standard_code: str) -> dict:
        """获取准则对应的附注模版配置"""
        note_path = DATA_DIR / "multi_standard_note_templates.json"
        if not note_path.exists():
            return {"standard_code": standard_code, "sections": []}
        with open(note_path, encoding="utf-8-sig") as f:
            data = json.load(f)
        lookup = "CAS_SMALL" if standard_code == "SME" else standard_code
        std_data = data.get("standards", {}).get(lookup)
        if not std_data:
            return {"standard_code": standard_code, "sections": []}
        return {"standard_code": standard_code, **std_data}

    def _to_dict(self, std: AccountingStandard) -> dict:
        return {
            "id": str(std.id),
            "standard_code": std.standard_code,
            "standard_name": std.standard_name,
            "standard_description": std.standard_description,
            "effective_date": str(std.effective_date) if std.effective_date else None,
            "is_active": std.is_active,
        }
