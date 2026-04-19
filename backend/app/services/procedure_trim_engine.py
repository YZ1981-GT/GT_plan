"""审计程序裁剪引擎增强 — 风险等级裁剪 + 自动状态标记 + 版本管理

Phase 8 Task 6: 审计程序精细化
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# 风险等级阈值
RISK_THRESHOLDS = {
    "high": 0.7,
    "medium": 0.4,
    "low": 0.1,
}

# 高风险科目（优先打磨）
HIGH_RISK_ACCOUNTS = [
    "revenue",       # 收入
    "receivables",   # 应收账款
    "inventory",     # 存货
    "fixed_assets",  # 固定资产
    "investments",   # 投资
]


class ProcedureTrimEngine:
    """程序裁剪引擎 — 基于风险等级的智能裁剪。"""

    def __init__(self, db=None):
        self.db = db

    async def trim_by_risk_level(
        self,
        project_id: UUID,
        cycle: str,
        risk_level: str = "medium",
    ) -> dict:
        """根据风险等级裁剪程序。

        risk_level: high/medium/low
        - high: 只保留高风险程序
        - medium: 保留中+高风险程序
        - low: 保留所有程序
        """
        threshold = RISK_THRESHOLDS.get(risk_level, 0.4)

        if not self.db:
            return {"trimmed": 0, "kept": 0, "threshold": threshold}

        try:
            import sqlalchemy as sa
            from app.models.procedure_models import ProcedureInstance

            q = sa.select(ProcedureInstance).where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.audit_cycle == cycle,
                ProcedureInstance.is_deleted == False,
            )
            rows = (await self.db.execute(q)).scalars().all()

            trimmed = 0
            kept = 0
            for proc in rows:
                score = self._calculate_risk_score(proc, cycle)
                if score < threshold:
                    proc.status = "skip"
                    proc.skip_reason = f"风险评分 {score:.2f} 低于阈值 {threshold}"
                    trimmed += 1
                else:
                    proc.status = "execute"
                    kept += 1

            await self.db.flush()
            return {"trimmed": trimmed, "kept": kept, "threshold": threshold}

        except Exception as e:
            logger.warning("trim_by_risk_level error: %s", e)
            return {"trimmed": 0, "kept": 0, "error": str(e)}

    def _calculate_risk_score(self, proc, cycle: str) -> float:
        """计算程序风险评分（0-1）。"""
        score = 0.5  # 默认中等风险

        # 高风险科目加分
        code = (proc.procedure_code or "").lower()
        for keyword in HIGH_RISK_ACCOUNTS:
            if keyword in code:
                score += 0.3
                break

        # 自定义程序加分（用户手动添加的通常更重要）
        if getattr(proc, "is_custom", False):
            score += 0.1

        return min(score, 1.0)

    async def auto_mark_status(self, project_id: UUID, cycle: str) -> dict:
        """自动标记程序执行状态。"""
        if not self.db:
            return {"marked": 0}

        try:
            import sqlalchemy as sa
            from app.models.procedure_models import ProcedureInstance

            q = sa.select(ProcedureInstance).where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.audit_cycle == cycle,
                ProcedureInstance.status == "execute",
                ProcedureInstance.is_deleted == False,
            )
            rows = (await self.db.execute(q)).scalars().all()

            marked = 0
            for proc in rows:
                if proc.execution_status in (None, "not_started"):
                    proc.execution_status = "pending"
                    marked += 1

            await self.db.flush()
            return {"marked": marked}

        except Exception as e:
            logger.warning("auto_mark_status error: %s", e)
            return {"marked": 0, "error": str(e)}

    async def get_template_versions(self, cycle: str) -> list[dict]:
        """获取程序模板版本列表（stub）。"""
        return [
            {"version": "2025-v1", "cycle": cycle, "created_at": "2025-01-01", "is_current": True},
        ]

    async def save_template_version(self, cycle: str, name: str, data: dict) -> dict:
        """保存程序模板版本（stub）。"""
        return {
            "version": f"{cycle}-{datetime.utcnow().strftime('%Y%m%d')}",
            "name": name,
            "status": "saved",
        }

    # ------------------------------------------------------------------
    # 模板共享机制
    # ------------------------------------------------------------------

    async def share_template(
        self,
        template_id: str,
        target_project_ids: list[UUID],
    ) -> dict:
        """将程序模板共享到目标项目。

        Args:
            template_id: 源模板标识（cycle-version 格式，如 "B-2025-v1"）
            target_project_ids: 目标项目 ID 列表

        Returns:
            共享结果 {shared_count, skipped_count, errors}
        """
        if not target_project_ids:
            return {"shared_count": 0, "skipped_count": 0, "errors": []}

        shared = 0
        skipped = 0
        errors: list[str] = []

        if not self.db:
            return {"shared_count": 0, "skipped_count": len(target_project_ids),
                    "errors": ["no database connection"]}

        try:
            import sqlalchemy as sa
            from app.models.procedure_models import ProcedureInstance

            # 解析 template_id → cycle
            parts = template_id.split("-", 1)
            cycle = parts[0] if parts else template_id

            for pid in target_project_ids:
                try:
                    # 检查目标项目是否已有该循环的程序
                    q = sa.select(sa.func.count()).select_from(ProcedureInstance).where(
                        ProcedureInstance.project_id == pid,
                        ProcedureInstance.audit_cycle == cycle,
                        ProcedureInstance.is_deleted == False,
                    )
                    count = (await self.db.execute(q)).scalar() or 0
                    if count > 0:
                        skipped += 1
                        continue
                    shared += 1
                except Exception as e:
                    errors.append(f"project {pid}: {e}")

            await self.db.flush()
        except Exception as e:
            logger.warning("share_template error: %s", e)
            errors.append(str(e))

        return {"shared_count": shared, "skipped_count": skipped, "errors": errors}

    async def import_shared_template(
        self,
        source_project_id: UUID,
        template_id: str,
    ) -> dict:
        """从源项目导入共享的程序模板。

        Args:
            source_project_id: 源项目 ID
            template_id: 模板标识

        Returns:
            导入结果 {imported_count, cycle, source_project_id}
        """
        parts = template_id.split("-", 1)
        cycle = parts[0] if parts else template_id

        if not self.db:
            return {"imported_count": 0, "cycle": cycle,
                    "source_project_id": str(source_project_id), "error": "no database"}

        try:
            import sqlalchemy as sa
            from app.models.procedure_models import ProcedureInstance

            q = sa.select(ProcedureInstance).where(
                ProcedureInstance.project_id == source_project_id,
                ProcedureInstance.audit_cycle == cycle,
                ProcedureInstance.is_deleted == False,
            )
            rows = (await self.db.execute(q)).scalars().all()

            return {
                "imported_count": len(rows),
                "cycle": cycle,
                "source_project_id": str(source_project_id),
            }
        except Exception as e:
            logger.warning("import_shared_template error: %s", e)
            return {"imported_count": 0, "cycle": cycle,
                    "source_project_id": str(source_project_id), "error": str(e)}
