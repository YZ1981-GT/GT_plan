"""审计程序裁剪与委派服务

Phase 9 Task 9.12
"""

from __future__ import annotations

import logging
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

    @staticmethod
    def _expand_range_wp_code(code: str) -> list[str]:
        """将区间型 wp_code（如 ``D2-1至D2-4``）展开为构成底稿编码 ``[D2-1, D2-2, D2-3, D2-4]``。

        LEAP 合并程序把多张连号底稿并成一行（编码用 ``起至终`` 表示），该区间串在
        ``wp_index`` 中无对应单一底稿 → wp_id 回填失败 → 前端显示"未生成"。展开后可回退到
        首张已生成底稿（控制台实际入口位置）。非区间码返回 ``[]``。
        """
        import re
        if "至" not in code:
            return []
        left, _, right = code.partition("至")
        m1 = re.match(r"^(.*-)(\d+)$", left.strip())
        m2 = re.match(r"^(.*-)(\d+)$", right.strip())
        if not m1 or not m2:
            return []
        prefix, start = m1.group(1), int(m1.group(2))
        prefix2, end = m2.group(1), int(m2.group(2))
        if prefix != prefix2 or end < start:
            return []
        return [f"{prefix}{n}" for n in range(start, end + 1)]

    @staticmethod
    def _parent_subject_code(code: str) -> str | None:
        """取科目级母编码：``D2-5``/``D2-6至D2-13`` → ``D2``；``D4-1至D4-4`` → ``D4``。

        LEAP 合并/子程序（``D2-6至D2-13`` 等）若无对应构成底稿，回退到科目级母底稿
        （``D2``/``D4``，与 ``D0``/``D1``/``D3`` 同级），进入该循环真实程序表控制台。
        """
        import re
        left = code.partition("至")[0].strip()
        m = re.match(r"^([A-Za-z]+\d+)-", left)
        return m.group(1) if m else None

    async def _resolve_wp_ids(self, project_id: UUID, wp_codes: set[str]) -> dict[str, str]:
        """按 wp_code 查本项目 working_paper 的 wp_id（JOIN wp_index）。

        解析优先级（控制台实际入口位置）：
        1. 精确匹配 wp_code；
        2. 区间码（``D2-1至D2-4``）→ 首张已生成的构成底稿（``D2-1``）；
        3. 子/区间码无构成底稿 → 科目级母底稿（``D2``/``D4``）。
        任一级命中即用，全部落空才保留 None（真正"未生成"）。
        """
        from app.models.workpaper_models import WorkingPaper, WpIndex

        # 展开区间码 + 收集母编码，一并查询（精确码 + 构成码 + 母码）
        expanded: dict[str, list[str]] = {}
        parents: dict[str, str] = {}
        query_codes: set[str] = set()
        for code in wp_codes:
            query_codes.add(code)
            parts = self._expand_range_wp_code(code)
            if parts:
                expanded[code] = parts
                query_codes.update(parts)
            parent = self._parent_subject_code(code)
            if parent:
                parents[code] = parent
                query_codes.add(parent)

        q = (
            sa.select(WpIndex.wp_code, WorkingPaper.id)
            .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
                WpIndex.is_deleted == False,  # noqa: E712
                WpIndex.wp_code.in_(query_codes),
            )
        )
        rows = (await self.db.execute(q)).all()
        code_to_id = {code: str(wid) for code, wid in rows}

        result: dict[str, str] = {}
        for code in wp_codes:
            if code in code_to_id:
                result[code] = code_to_id[code]
                continue
            # 区间码：取首张已生成底稿（构成码顺序）
            matched = False
            for part in expanded.get(code, []):
                if part in code_to_id:
                    result[code] = code_to_id[part]
                    matched = True
                    break
            if matched:
                continue
            # 回退科目级母底稿（进入该循环程序表控制台）
            parent = parents.get(code)
            if parent and parent in code_to_id:
                result[code] = code_to_id[parent]
        return result

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

    # save_trim 已删除（procedure-mainline-convergence 需求 1/3）：
    # 粗裁写入口收敛到 ProcedureTrimService.preview_scheme/apply_scheme（canonical scope key
    # + 一次性 preview + 真实 applied），且状态写只经 ProcedureTaskTransitionService。
    # 旧实现直接 UPDATE ProcedureInstance.status 绕过状态机，且以 UUID 为 key 写
    # trim_data（参照项目无法转换），已连同 PUT /procedures/{cycle}/trim 一起下线。

    async def _existing_custom_codes(
        self, project_id: UUID, cycle: str
    ) -> set[str]:
        """收集该项目下已占用的编码（用于查重 / 生成唯一编号）。

        合并两个来源，避免 WpIndex 唯一约束 (project_id, wp_code) 冲突：
        - ProcedureInstance.procedure_code / wp_code（**含已软删**，编号永不复用）
        - WpIndex.wp_code（自定义程序会创建 WpIndex 占位）
        """
        from app.models.workpaper_models import WpIndex

        codes: set[str] = set()
        # ProcedureInstance：含已删（防止软删后复用编号造成撞库）
        pi_rows = (await self.db.execute(
            sa.select(
                ProcedureInstance.procedure_code, ProcedureInstance.wp_code
            ).where(ProcedureInstance.project_id == project_id)
        )).all()
        for pc, wc in pi_rows:
            if pc:
                codes.add(pc)
            if wc:
                codes.add(wc)
        # WpIndex：全部（唯一约束按 project_id+wp_code，无软删列区分）
        wi_rows = (await self.db.execute(
            sa.select(WpIndex.wp_code).where(WpIndex.project_id == project_id)
        )).scalars().all()
        for wc in wi_rows:
            if wc:
                codes.add(wc)
        return codes

    @staticmethod
    def _next_custom_code(cycle: str, existing: set[str]) -> str:
        """基于现有编码的最大序号生成 {cycle}-C{n:02d}，序号永不复用。

        扫描形如 ``{cycle}-C<digits>`` 的现有编码取最大数字后 +1，避免
        「软删后 COUNT 回退 → 复用编号 → 撞库」的碰撞。
        """
        import re

        prefix = f"{cycle}-C"
        max_seq = 0
        pat = re.compile(rf"^{re.escape(prefix)}(\d+)$")
        for code in existing:
            m = pat.match(code or "")
            if m:
                max_seq = max(max_seq, int(m.group(1)))
        seq = max_seq + 1
        # 唯一性兜底循环（防边缘：非标准命名占用了目标编码）
        candidate = f"{prefix}{seq:02d}"
        while candidate in existing:
            seq += 1
            candidate = f"{prefix}{seq:02d}"
        return candidate

    async def add_custom(self, project_id: UUID, cycle: str, data: dict) -> dict:
        """新增自定义程序步骤

        - 用户手填编码 → 先查重（含 WpIndex + 已软删），冲突抛 ValueError（路由映射 409）。
        - 未填 → 基于现有最大序号生成 {cycle}-C{n}（序号永不复用，避免软删/并发撞库）。
        procedure_code 为 NOT NULL 列。
        """
        existing = await self._existing_custom_codes(project_id, cycle)

        proc_code = (data.get("procedure_code") or "").strip()
        if proc_code:
            # 用户手填 → 查重，冲突返回友好错误（避免 WpIndex 唯一约束原始 500）
            if proc_code in existing:
                raise ValueError(f"程序编码 {proc_code} 已存在，请换一个编码")
        else:
            proc_code = self._next_custom_code(cycle, existing)

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

    async def delete_custom(self, project_id: UUID, proc_id: UUID) -> bool:
        """软删自定义程序 + 一并清理 WpIndex 占位（保持前后端一致）。

        仅允许删除 is_custom=True 的程序（模板程序不可删，只能裁剪）。
        返回 True 表示删除成功，False 表示未找到 / 非自定义。
        """
        from app.models.workpaper_models import WpIndex

        pi = (await self.db.execute(
            sa.select(ProcedureInstance).where(
                ProcedureInstance.id == proc_id,
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.is_deleted == False,  # noqa: E712
            )
        )).scalar_one_or_none()
        if pi is None or not pi.is_custom:
            return False

        pi.is_deleted = True
        # 软删 WpIndex 占位（不硬删：WorkingPaper.wp_index_id 是 NOT NULL FK，
        # 已上传文件时硬删会违反外键）。wp_code 保留 → 唯一约束(无is_deleted过滤)
        # 仍占位 + _existing_custom_codes 仍计入 → 编号不复用，零撞库。
        wp_code = pi.wp_code or pi.procedure_code
        if wp_code:
            await self.db.execute(
                sa.update(WpIndex)
                .where(
                    WpIndex.project_id == project_id,
                    WpIndex.wp_code == wp_code,
                    WpIndex.is_deleted == False,  # noqa: E712
                )
                .values(is_deleted=True)
            )
        await self.db.flush()
        return True

    async def assign_procedures(
        self,
        project_id: UUID,
        assignments: list[dict],
        actor_user_id: UUID | None = None,
    ) -> int:
        """批量委派（走底稿主编两层原子事务 · procedure-delegation-visibility-isolation Task 7）。

        每个 assignment 经 ``DelegationTransactionService.delegate_lead`` 落地：
          - 唯一解析 wp_index（由 procedure_instance_id / wp_code 联合解析，fail-closed）；
          - 严格 staff→user 映射后同事务写 ``working_paper.assigned_to=user_id`` 权威、
            ``procedure_instances.assigned_to=staff_id`` 投影、统一 delegation history、
            policy epoch 与 invalidation outbox；
          - 两层互不覆盖、无 last-write-wins；任一 assignment 校验失败 raise
            ``DelegationError`` → router 回滚整批（原子）。

        为保持既有行为：自定义程序在委派前先幂等确保 working_paper 存在（standard 程序若
        底稿尚未生成则由 delegate_lead 只写投影 + history，WP 生成后再回填 assigned_to）。
        """
        from app.models.workpaper_models import WorkingPaper, WpIndex
        from app.services.workpaper_generation_service import workpaper_generation_service
        from app.services.wp_visibility.delegation_transaction import (
            DelegationTransactionService,
            LeadDelegationRequest,
        )

        deleg = DelegationTransactionService(self.db)
        updated = 0
        for a in assignments:
            proc_id = a["procedure_id"]
            staff_raw = a.get("staff_id")
            request_id = a.get("request_id")

            proc = (
                await self.db.execute(
                    sa.select(ProcedureInstance).where(
                        ProcedureInstance.id == proc_id,
                        ProcedureInstance.project_id == project_id,
                        ProcedureInstance.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()
            if proc is None:
                continue

            # 自定义程序：委派前幂等确保 working_paper 存在（保持既有行为）。
            if proc.is_custom and proc.wp_code:
                wp_index = (
                    await self.db.execute(
                        sa.select(WpIndex).where(
                            WpIndex.project_id == project_id,
                            WpIndex.wp_code == proc.wp_code,
                            WpIndex.is_deleted == False,  # noqa: E712
                        )
                    )
                ).scalar_one_or_none()
                if wp_index is not None:
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

            staff_uuid = self._coerce_uuid(staff_raw)
            req = LeadDelegationRequest(
                project_id=project_id,
                actor_user_id=actor_user_id or project_id,  # actor 缺省兜底（审计用）
                staff_id=staff_uuid,
                clear=(staff_uuid is None),
                procedure_instance_id=proc.id,
                wp_code=proc.wp_code,
                request_id=str(request_id) if request_id else None,
            )
            await deleg.delegate_lead(req)
            updated += 1

        await self.db.flush()
        return updated

    @staticmethod
    def _coerce_uuid(value) -> UUID | None:
        if value is None or value == "":
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (ValueError, TypeError):
            return None

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

    # apply_scheme / batch_apply 已删除（需求 2/3）：旧实现读 UUID-key trim_data，
    # 内层循环什么都不做却把 applied 累加成程序总数 = 假成功。参照项目改为前端读源项目
    # 当前 wp_code+status 构造 canonical entries，再走 procedure-trim/preview|apply。
    #
    # get_my_tasks 已删除（需求 3/12）：程序任务真源是 ProcedureRowTask
    # （/api/my/procedure-row-tasks），把 ProcedureInstance.id 当 task_id 暴露会串线。

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
