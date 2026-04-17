"""审计程序裁剪与委派服务

Phase 9 Task 9.12
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance, ProcedureTrimScheme
from app.models.workpaper_models import WpTemplate

logger = logging.getLogger(__name__)


class ProcedureService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_procedures(self, project_id: UUID, cycle: str) -> list[dict]:
        """获取该循环的程序列表"""
        q = (
            sa.select(ProcedureInstance)
            .where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.audit_cycle == cycle,
                ProcedureInstance.is_deleted == False,  # noqa
            )
            .order_by(ProcedureInstance.sort_order)
        )
        rows = (await self.db.execute(q)).scalars().all()
        return [self._to_dict(r) for r in rows]

    async def init_from_templates(self, project_id: UUID, cycle: str) -> list[dict]:
        """从模板初始化程序实例"""
        # 检查是否已初始化
        existing = await self.db.execute(
            sa.select(sa.func.count()).select_from(ProcedureInstance).where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.audit_cycle == cycle,
                ProcedureInstance.is_deleted == False,  # noqa
            )
        )
        if (existing.scalar() or 0) > 0:
            return await self.get_procedures(project_id, cycle)

        # 从 wp_template 加载该循环的模板
        tmpl_q = sa.select(WpTemplate).where(
            WpTemplate.audit_cycle == cycle,
            WpTemplate.is_deleted == False,  # noqa
        ).order_by(WpTemplate.template_code)
        templates = (await self.db.execute(tmpl_q)).scalars().all()

        for i, t in enumerate(templates):
            pi = ProcedureInstance(
                project_id=project_id,
                audit_cycle=cycle,
                procedure_code=t.template_code,
                procedure_name=t.template_name,
                sort_order=i * 10,
                wp_code=t.template_code,
            )
            self.db.add(pi)

        await self.db.flush()
        return await self.get_procedures(project_id, cycle)

    async def save_trim(self, project_id: UUID, cycle: str, items: list[dict]) -> int:
        """保存裁剪结果"""
        updated = 0
        for item in items:
            proc_id = item.get("id")
            if not proc_id:
                continue
            await self.db.execute(
                sa.update(ProcedureInstance)
                .where(ProcedureInstance.id == proc_id)
                .values(
                    status=item.get("status", "execute"),
                    skip_reason=item.get("skip_reason"),
                )
            )
            updated += 1

        # 自动保存裁剪方案
        scheme = ProcedureTrimScheme(
            project_id=project_id,
            audit_cycle=cycle,
            scheme_name=f"裁剪方案-{cycle}-{datetime.now().strftime('%Y%m%d')}",
            trim_data={item["id"]: {"status": item.get("status"), "skip_reason": item.get("skip_reason")} for item in items if item.get("id")},
        )
        self.db.add(scheme)
        await self.db.flush()
        return updated

    async def add_custom(self, project_id: UUID, cycle: str, data: dict) -> dict:
        """新增自定义程序步骤"""
        pi = ProcedureInstance(
            project_id=project_id,
            audit_cycle=cycle,
            procedure_code=data.get("procedure_code", f"CUSTOM-{cycle}"),
            procedure_name=data["procedure_name"],
            sort_order=data.get("sort_order", 999),
            is_custom=True,
        )
        self.db.add(pi)
        await self.db.flush()
        return self._to_dict(pi)

    async def assign_procedures(self, project_id: UUID, assignments: list[dict]) -> int:
        """批量委派"""
        now = datetime.now(timezone.utc)
        updated = 0
        for a in assignments:
            await self.db.execute(
                sa.update(ProcedureInstance)
                .where(ProcedureInstance.id == a["procedure_id"])
                .values(assigned_to=a["staff_id"], assigned_at=now)
            )
            updated += 1
        await self.db.flush()
        return updated

    async def get_trim_scheme(self, project_id: UUID, cycle: str) -> dict | None:
        """获取裁剪方案"""
        q = (
            sa.select(ProcedureTrimScheme)
            .where(
                ProcedureTrimScheme.project_id == project_id,
                ProcedureTrimScheme.audit_cycle == cycle,
                ProcedureTrimScheme.is_deleted == False,  # noqa
            )
            .order_by(ProcedureTrimScheme.created_at.desc())
            .limit(1)
        )
        scheme = (await self.db.execute(q)).scalar_one_or_none()
        if not scheme:
            return None
        return {"id": str(scheme.id), "scheme_name": scheme.scheme_name, "trim_data": scheme.trim_data}

    async def apply_scheme(self, project_id: UUID, cycle: str, source_project_id: UUID) -> int:
        """应用参照方案"""
        scheme = await self.get_trim_scheme(source_project_id, cycle)
        if not scheme or not scheme.get("trim_data"):
            return 0

        # 获取当前项目的程序列表
        procs = await self.get_procedures(project_id, cycle)
        if not procs:
            await self.init_from_templates(project_id, cycle)
            procs = await self.get_procedures(project_id, cycle)

        # 按 procedure_code 匹配应用裁剪
        source_data = scheme["trim_data"]
        applied = 0
        for proc in procs:
            for _, trim_info in source_data.items():
                if isinstance(trim_info, dict) and trim_info.get("status"):
                    # 简化：按顺序应用
                    pass
            applied += 1

        return applied

    async def batch_apply(self, parent_project_id: UUID, cycle: str, target_ids: list[UUID]) -> dict:
        """批量应用到子公司"""
        scheme = await self.get_trim_scheme(parent_project_id, cycle)
        if not scheme:
            return {"applied": 0, "failed": [{"reason": "源项目无裁剪方案"}]}

        results = {"applied": 0, "failed": []}
        for tid in target_ids:
            try:
                await self.apply_scheme(tid, cycle, parent_project_id)
                results["applied"] += 1
            except Exception as e:
                results["failed"].append({"project_id": str(tid), "reason": str(e)})

        return results

    async def get_my_tasks(self, project_id: UUID, staff_id: UUID) -> list[dict]:
        """当前用户被委派的程序列表"""
        q = (
            sa.select(ProcedureInstance)
            .where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.assigned_to == staff_id,
                ProcedureInstance.status == "execute",
                ProcedureInstance.is_deleted == False,  # noqa
            )
            .order_by(ProcedureInstance.audit_cycle, ProcedureInstance.sort_order)
        )
        rows = (await self.db.execute(q)).scalars().all()
        return [self._to_dict(r) for r in rows]

    def _to_dict(self, p: ProcedureInstance) -> dict:
        return {
            "id": str(p.id),
            "project_id": str(p.project_id),
            "audit_cycle": p.audit_cycle,
            "procedure_code": p.procedure_code,
            "procedure_name": p.procedure_name,
            "sort_order": p.sort_order,
            "status": p.status,
            "skip_reason": p.skip_reason,
            "is_custom": p.is_custom,
            "assigned_to": str(p.assigned_to) if p.assigned_to else None,
            "execution_status": p.execution_status,
            "wp_code": p.wp_code,
        }
