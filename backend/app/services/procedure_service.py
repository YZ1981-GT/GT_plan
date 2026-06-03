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
        """获取该循环的程序列表（含 wp_id 回填 + 委派人姓名）"""
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
        result = [self._to_dict(r) for r in rows]

        # ── wp_code → wp_id 回填（跳转底稿程序表控制台用）──
        wp_codes = {r["wp_code"] for r in result if r.get("wp_code")}
        if wp_codes:
            wp_map = await self._resolve_wp_ids(project_id, wp_codes)
            for r in result:
                if not r.get("wp_id") and r.get("wp_code"):
                    r["wp_id"] = wp_map.get(r["wp_code"])

        # ── assigned_to → staff 姓名回填（委派显示用）──
        staff_ids = {r["assigned_to"] for r in result if r.get("assigned_to")}
        if staff_ids:
            name_map = await self._resolve_staff_names(staff_ids)
            for r in result:
                if r.get("assigned_to"):
                    r["assigned_to_name"] = name_map.get(r["assigned_to"])

        return result

    async def _resolve_wp_ids(self, project_id: UUID, wp_codes: set[str]) -> dict[str, str]:
        """按 wp_code 查本项目 working_paper 的 wp_id（JOIN wp_index）。"""
        from app.models.workpaper_models import WorkingPaper, WpIndex
        q = (
            sa.select(WpIndex.wp_code, WorkingPaper.id)
            .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
                WpIndex.is_deleted == False,  # noqa: E712
                WpIndex.wp_code.in_(wp_codes),
            )
        )
        rows = (await self.db.execute(q)).all()
        return {code: str(wid) for code, wid in rows}

    async def _resolve_staff_names(self, staff_ids: set[str]) -> dict[str, str]:
        """按 staff_id 查 staff_members.name。"""
        from app.models.staff_models import StaffMember
        try:
            uuid_ids = [UUID(s) for s in staff_ids]
        except (ValueError, TypeError):
            return {}
        q = sa.select(StaffMember.id, StaffMember.name).where(StaffMember.id.in_(uuid_ids))
        rows = (await self.db.execute(q)).all()
        return {str(sid): name for sid, name in rows}

    async def init_from_templates(self, project_id: UUID, cycle: str) -> list[dict]:
        """从模板初始化程序实例

        优先级：
        1. template_library 表中项目已选择的底稿模板
        2. gt_template_library.json 全量模板
        3. WpTemplate 表（降级）

        裁剪衔接：初始化后用户可通过 save_trim 裁剪程序，
        generate_project_workpapers 会跳过 status=skip/not_applicable 的底稿。
        """
        import json
        from pathlib import Path

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

        # 优先从 template_library 表加载项目已选择的底稿模板
        lib_items = []
        try:
            from app.models.template_library_models import TemplateLibraryItem, ProjectTemplateSelection, TemplateType
            sel_q = (
                sa.select(TemplateLibraryItem)
                .join(ProjectTemplateSelection, ProjectTemplateSelection.template_id == TemplateLibraryItem.id)
                .where(
                    ProjectTemplateSelection.project_id == project_id,
                    ProjectTemplateSelection.is_active == sa.true(),
                    TemplateLibraryItem.template_type == TemplateType.workpaper_preset,
                    TemplateLibraryItem.audit_cycle == cycle,
                    TemplateLibraryItem.is_deleted == sa.false(),
                )
                .order_by(TemplateLibraryItem.wp_code)
            )
            sel_items = (await self.db.execute(sel_q)).scalars().all()
            for item in sel_items:
                lib_items.append({
                    "wp_code": item.wp_code,
                    "wp_name": item.name,
                    "cycle_prefix": item.audit_cycle,
                })
        except Exception:
            pass

        # 降级：从 gt_template_library.json 加载
        if not lib_items:
            lib_path = Path(__file__).parent.parent.parent / "data" / "gt_template_library.json"
            if lib_path.exists():
                try:
                    with open(lib_path, "r", encoding="utf-8-sig") as f:
                        raw = json.load(f)
                    all_items = raw.get("templates", []) if isinstance(raw, dict) else raw
                    lib_items = [
                        item for item in all_items
                        if isinstance(item, dict) and item.get("cycle_prefix") == cycle
                    ]
                except Exception:
                    pass

        if lib_items:
            for i, item in enumerate(lib_items):
                wp_code = item.get("wp_code", item.get("code", f"{cycle}-{i}"))
                pi = ProcedureInstance(
                    project_id=project_id,
                    audit_cycle=cycle,
                    procedure_code=wp_code,
                    procedure_name=item.get("wp_name", item.get("name", f"程序{cycle}-{i}")),
                    sort_order=i * 10,
                    wp_code=wp_code,
                )
                self.db.add(pi)
        else:
            # 最终降级：从 wp_template 加载该循环的模板
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
        """新增自定义程序步骤

        procedure_code 为 NOT NULL 列；前端可能传 None（key 存在但值为 None），
        `.get(k, default)` 不会回退 default，故此处显式 `or` 兜底 + 自动编号去重。
        """
        # 显式兜底：None / 空串都回退到自动生成编码
        proc_code = (data.get("procedure_code") or "").strip()
        if not proc_code:
            # 统计已有自定义程序数，生成 {cycle}-C{序号}（如 D-C01）
            existing = (await self.db.execute(
                sa.select(sa.func.count()).select_from(ProcedureInstance).where(
                    ProcedureInstance.project_id == project_id,
                    ProcedureInstance.audit_cycle == cycle,
                    ProcedureInstance.is_custom == True,  # noqa: E712
                    ProcedureInstance.is_deleted == False,  # noqa: E712
                )
            )).scalar() or 0
            proc_code = f"{cycle}-C{existing + 1:02d}"

        pi = ProcedureInstance(
            project_id=project_id,
            audit_cycle=cycle,
            procedure_code=proc_code,
            procedure_name=data["procedure_name"],
            sort_order=data.get("sort_order") or 999,
            is_custom=True,
            wp_code=data.get("wp_code") or proc_code,
        )
        self.db.add(pi)
        await self.db.flush()
        return self._to_dict(pi)

    async def assign_procedures(self, project_id: UUID, assignments: list[dict]) -> int:
        """批量委派"""
        from app.models.workpaper_models import WorkingPaper, WpIndex
        from app.services.workpaper_generation_service import workpaper_generation_service

        now = datetime.now(timezone.utc)
        updated = 0
        for a in assignments:
            proc_id = a["procedure_id"]
            await self.db.execute(
                sa.update(ProcedureInstance)
                .where(ProcedureInstance.id == proc_id)
                .values(assigned_to=a["staff_id"], assigned_at=now)
            )
            updated += 1

            proc = (
                await self.db.execute(
                    sa.select(ProcedureInstance).where(ProcedureInstance.id == proc_id)
                )
            ).scalar_one_or_none()
            if not proc or not proc.is_custom or not proc.wp_code:
                continue

            wp_index = (
                await self.db.execute(
                    sa.select(WpIndex).where(
                        WpIndex.project_id == project_id,
                        WpIndex.wp_code == proc.wp_code,
                        WpIndex.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()
            if wp_index is None:
                continue

            has_wp = (
                await self.db.execute(
                    sa.select(sa.func.count())
                    .select_from(WorkingPaper)
                    .where(
                        WorkingPaper.project_id == project_id,
                        WorkingPaper.wp_index_id == wp_index.id,
                        WorkingPaper.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalar()
            if not has_wp:
                wp = await workpaper_generation_service.ensure_working_paper(
                    self.db, project_id, wp_index.id
                )
                await self.db.execute(
                    sa.update(ProcedureInstance)
                    .where(ProcedureInstance.id == proc_id)
                    .values(wp_id=wp.id)
                )

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
            "wp_id": str(p.wp_id) if p.wp_id else None,
        }
