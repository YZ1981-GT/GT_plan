"""显式 materialize 与底稿原子绑定服务（Task 4）

Feature: procedure-delegation-notification / 需求 2.1-2.8, 12.2 / Design C2、D2-D3、Properties P4-P7

职责（命令 + 纯读，严格分离）：

- ``materialize(project_id, wp_index_ids, ...)``：把模板级 ProcedureRowDefinition 显式
  实例化为项目级 ProcedureRowTask。项目初始化、backfill、delegation preview 前置 job
  **复用同一服务**。按 active partial unique **批量 upsert**（禁止逐行 N+1）：
  ``ON CONFLICT (project_id, wp_index_id, sheet_key, definition_key) WHERE is_deleted=false``
  —— 谓词与 V105 ``uq_procedure_row_tasks_active`` 索引完全一致（Req 12.2）。已存在 task
  **只补充安全展示快照**（wp_code/sheet_name），**绝不重置** assignee/reviewer/workflow/
  applicability/assignment_version/lock_version/wp_id（Req 2.3 语义护栏）。

- ``bind_working_paper(project_id, wp_index_id, wp_id, ...)``：底稿生成事务内，锁定同锚点
  active 且 ``wp_id IS NULL`` 的 task，校验 wp 属于同 project/wp_index 后**一次**更新
  nullable ``wp_id``；task_id/assignee/reviewer/workflow/assignment_version/历史保持不变。
  幂等：重试返回相同绑定结果，不换 task_id（Req 2.3-2.4 / P5）。

- ``build_row_overlay(...)`` / ``overlay_program_rows(...)``：**纯读** overlay，缺 task 的
  definition 行返回 ``task_id=null, materialization_required=true``，**绝不写库**
  （Req 2.5-2.8 / P6-P7）。render-config 只调用此纯读接口，不触发任何 upsert/materialize。

约定：service 只 flush 不 commit；router/dispatcher 显式 commit。
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureRowDefinition, ProcedureRowTask

logger = logging.getLogger(__name__)

# 从程序表 sheet 级编码（如 D2A / D4A / G1A / D2-7A）提取底稿基码（D2 / D4 / G1 / D2-7）。
# definition.template_code 是 sheet 级编码；wp_index.wp_code 是底稿编码，故物化时按 base 归一匹配。
_BASE_WP_CODE_RE = re.compile(r"^([A-Za-z]+\d+(?:-\d+)?)")


def _base_wp_code(template_code: str) -> str:
    """程序表 sheet 编码 → 底稿基码（D2A→D2 / D2-7A→D2-7）；无法解析时原样返回。"""
    if not template_code:
        return template_code or ""
    m = _BASE_WP_CODE_RE.match(template_code)
    return m.group(1) if m else template_code


class ProcedureTaskMaterializationService:
    """程序行任务显式物化 + 底稿原子绑定 + 纯读 overlay。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -- 内部：wp_index 解析 -------------------------------------------------

    async def _load_wp_indexes(
        self, project_id: UUID, wp_index_ids: list[UUID]
    ) -> dict[UUID, dict]:
        """加载并校验 wp_index 属于本项目；返回 {wp_index_id: {wp_code, audit_cycle, wp_name}}。"""
        from app.models.workpaper_models import WpIndex

        if not wp_index_ids:
            return {}
        rows = (
            await self.db.execute(
                sa.select(
                    WpIndex.id, WpIndex.wp_code, WpIndex.audit_cycle, WpIndex.wp_name
                ).where(
                    WpIndex.id.in_(wp_index_ids),
                    WpIndex.project_id == project_id,
                    WpIndex.is_deleted == sa.false(),
                )
            )
        ).all()
        return {
            r[0]: {"wp_code": r[1], "audit_cycle": r[2] or "A", "wp_name": r[3]}
            for r in rows
        }

    async def _definitions_for_wp_code(
        self, wp_code: str, definition_revision: str | None = None
    ) -> list[ProcedureRowDefinition]:
        """按底稿基码匹配模板定义（template_code base == wp_code）。

        用 ``LIKE wp_code%`` 收窄后在 Python 按精确 base 过滤，规避 D2 与 D20 前缀误匹配。
        可选按 ``definition_revision`` 进一步过滤某一版本。
        """
        if not wp_code:
            return []
        conds = [ProcedureRowDefinition.template_code.like(f"{wp_code}%")]
        if definition_revision:
            conds.append(
                ProcedureRowDefinition.template_revision_hash == definition_revision
            )
        rows = (
            await self.db.execute(
                sa.select(ProcedureRowDefinition).where(*conds)
            )
        ).scalars().all()
        return [d for d in rows if _base_wp_code(d.template_code) == wp_code]

    # -- 命令：显式物化（批量 upsert） --------------------------------------

    async def materialize(
        self,
        project_id: UUID,
        wp_index_ids: list[UUID],
        *,
        definition_revision: str | None = None,
        actor_user_id: UUID | None = None,
        request_id: str | None = None,
    ) -> dict:
        """把匹配 definitions 显式物化为 ProcedureRowTask（批量 active partial unique upsert）。

        - 新 (project, wp_index, sheet, definition) → 插入 task（默认 unassigned/execute）。
        - 已存在 active task → 只更新展示快照（wp_code/sheet_name），不动委派/工作流/版本/wp_id。
        - 只 flush 不 commit。

        返回 ``{created, existing, targets, wp_index_results:[...], missing_wp_index:[...]}``。
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        wp_index_map = await self._load_wp_indexes(project_id, wp_index_ids)
        missing = [str(i) for i in wp_index_ids if i not in wp_index_map]

        # 收集全部待 upsert 行（跨 wp_index 一次批量，禁止逐行 N+1）。
        value_rows: list[dict] = []
        per_index: dict[UUID, int] = {}
        for wp_index_id, meta in wp_index_map.items():
            wp_code = meta["wp_code"]
            defs = await self._definitions_for_wp_code(wp_code, definition_revision)
            per_index[wp_index_id] = len(defs)
            for d in defs:
                value_rows.append(
                    {
                        "project_id": project_id,
                        "wp_index_id": wp_index_id,
                        "wp_id": None,
                        "definition_key": d.definition_key,
                        "sheet_key": d.sheet_key,
                        "wp_code": wp_code,
                        "sheet_name": meta.get("wp_name") or d.sheet_key,
                        "program_no": d.program_no,
                        "procedure_text": d.procedure_text,
                        "ref_snapshot": list(d.ref_snapshot or []),
                        "definition_revision_hash": d.template_revision_hash,
                        "audit_cycle_snapshot": meta["audit_cycle"],
                        "applicability_status": "execute",
                        "workflow_status": "unassigned",
                    }
                )

        created = 0
        existing = 0
        if value_rows:
            stmt = pg_insert(ProcedureRowTask).values(value_rows)
            # ON CONFLICT 谓词必须与 uq_procedure_row_tasks_active 完全一致。
            # 已存在 active task 仅补充安全展示快照，绝不重置委派/工作流/版本/wp_id。
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    ProcedureRowTask.project_id,
                    ProcedureRowTask.wp_index_id,
                    ProcedureRowTask.sheet_key,
                    ProcedureRowTask.definition_key,
                ],
                index_where=ProcedureRowTask.is_deleted == sa.false(),
                set_={
                    "wp_code": stmt.excluded.wp_code,
                    "sheet_name": stmt.excluded.sheet_name,
                    "updated_at": sa.func.now(),
                },
            ).returning(
                ProcedureRowTask.id, sa.literal_column("(xmax = 0)")
            )
            result = (await self.db.execute(stmt)).all()
            for _id, inserted in result:
                if inserted:
                    created += 1
                else:
                    existing += 1
            await self.db.flush()

        logger.info(
            "materialize project=%s wp_index=%d targets=%d created=%d existing=%d request_id=%s",
            project_id,
            len(wp_index_map),
            len(value_rows),
            created,
            existing,
            request_id,
        )
        return {
            "created": created,
            "existing": existing,
            "targets": len(value_rows),
            "wp_index_results": [
                {"wp_index_id": str(i), "definitions": n} for i, n in per_index.items()
            ],
            "missing_wp_index": missing,
        }

    # -- 命令：底稿原子绑定 -------------------------------------------------

    async def bind_working_paper(
        self,
        project_id: UUID,
        wp_index_id: UUID,
        wp_id: UUID,
        *,
        request_id: str | None = None,
    ) -> dict:
        """底稿生成事务内，把同锚点 active 且未绑定 task 原子设置 wp_id。

        - 校验 wp 属于同 project/wp_index（否则 ValueError，不写）。
        - 只更新 ``wp_id IS NULL`` 的 active task；已绑定到本 wp 的幂等跳过。
        - task_id/assignee/reviewer/workflow/assignment_version/历史均不变。
        - 只 flush 不 commit。
        """
        from app.models.workpaper_models import WorkingPaper

        wp = (
            await self.db.execute(
                sa.select(WorkingPaper.id, WorkingPaper.wp_index_id, WorkingPaper.project_id)
                .where(
                    WorkingPaper.id == wp_id,
                    WorkingPaper.is_deleted == sa.false(),
                )
            )
        ).first()
        if wp is None:
            raise ValueError("底稿不存在")
        if wp[2] != project_id or wp[1] != wp_index_id:
            raise ValueError("底稿不属于该 project/wp_index，禁止绑定")

        # 锁定同锚点 active 任务（行锁，避免并发绑定竞态）。
        locked = (
            await self.db.execute(
                sa.select(ProcedureRowTask.id, ProcedureRowTask.wp_id)
                .where(
                    ProcedureRowTask.project_id == project_id,
                    ProcedureRowTask.wp_index_id == wp_index_id,
                    ProcedureRowTask.is_deleted == sa.false(),
                )
                .with_for_update()
            )
        ).all()

        pending_ids = [r[0] for r in locked if r[1] is None]
        already = [r[0] for r in locked if r[1] == wp_id]
        conflict = [r[0] for r in locked if r[1] is not None and r[1] != wp_id]

        bound = 0
        if pending_ids:
            await self.db.execute(
                sa.update(ProcedureRowTask)
                .where(ProcedureRowTask.id.in_(pending_ids))
                .values(wp_id=wp_id, updated_at=sa.func.now())
            )
            bound = len(pending_ids)
            await self.db.flush()

        logger.info(
            "bind_working_paper project=%s wp_index=%s wp=%s bound=%d already=%d conflict=%d request_id=%s",
            project_id,
            wp_index_id,
            wp_id,
            bound,
            len(already),
            len(conflict),
            request_id,
        )
        return {
            "wp_id": str(wp_id),
            "wp_index_id": str(wp_index_id),
            "bound": bound,
            "already_bound": len(already),
            "conflict": len(conflict),
            "total_active": len(locked),
        }

    # -- 纯读：overlay（严禁写库） ------------------------------------------

    async def _active_tasks_by_key(
        self, project_id: UUID, wp_index_id: UUID
    ) -> dict[tuple[str, str], ProcedureRowTask]:
        """加载同锚点 active tasks，按 (sheet_key, definition_key) 索引（纯读）。"""
        rows = (
            await self.db.execute(
                sa.select(ProcedureRowTask).where(
                    ProcedureRowTask.project_id == project_id,
                    ProcedureRowTask.wp_index_id == wp_index_id,
                    ProcedureRowTask.is_deleted == sa.false(),
                )
            )
        ).scalars().all()
        return {(t.sheet_key, t.definition_key): t for t in rows}

    @staticmethod
    def _task_overlay(task: ProcedureRowTask | None) -> dict:
        """把 task（或缺失）投影为 overlay 字段；未物化 → task_id=null/materialization_required=true。"""
        if task is None:
            return {"task_id": None, "materialization_required": True}
        return {
            "task_id": str(task.id),
            "materialization_required": False,
            "wp_id": str(task.wp_id) if task.wp_id else None,
            "workflow_status": task.workflow_status,
            "applicability_status": task.applicability_status,
            "assignee_staff_id": str(task.assignee_staff_id) if task.assignee_staff_id else None,
            "reviewer_staff_id": str(task.reviewer_staff_id) if task.reviewer_staff_id else None,
            "assignment_version": task.assignment_version,
            "lock_version": task.lock_version,
            "due_at": task.due_at.isoformat() if task.due_at else None,
        }

    async def build_row_overlay(
        self,
        project_id: UUID,
        wp_index_id: UUID,
        *,
        definition_revision: str | None = None,
    ) -> list[dict]:
        """纯读：对本 wp_index 的全部 definition 行构造 overlay（缺 task 标 materialization_required）。

        绝不创建/更新 definition/task/preview/projection/outbox，也不改 WorkingPaper。
        """
        wp_index_map = await self._load_wp_indexes(project_id, [wp_index_id])
        meta = wp_index_map.get(wp_index_id)
        if meta is None:
            return []
        defs = await self._definitions_for_wp_code(meta["wp_code"], definition_revision)
        task_index = await self._active_tasks_by_key(project_id, wp_index_id)

        overlay: list[dict] = []
        for d in defs:
            task = task_index.get((d.sheet_key, d.definition_key))
            row = {
                "definition_key": d.definition_key,
                "sheet_key": d.sheet_key,
                "program_no": d.program_no,
                "procedure_text": d.procedure_text,
                "ref_snapshot": list(d.ref_snapshot or []),
                **self._task_overlay(task),
            }
            overlay.append(row)
        return overlay

    async def overlay_program_rows(
        self,
        project_id: UUID,
        wp_index_id: UUID,
        programs: list[dict],
        *,
        definition_revision: str | None = None,
    ) -> list[dict]:
        """纯读：把 task overlay 合并到 render-config 的 program 行（按 sheet_key+program_no 匹配）。

        - 命中 active task → 附加 task_id + workflow/applicability 等；
        - definition 存在但无 task → task_id=null, materialization_required=true；
        - 无匹配 definition → 保持原样（不臆造 materialization_required）。
        绝不写库；供 render-config 只读调用（Design D3）。
        """
        wp_index_map = await self._load_wp_indexes(project_id, [wp_index_id])
        meta = wp_index_map.get(wp_index_id)
        if meta is None:
            return programs
        defs = await self._definitions_for_wp_code(meta["wp_code"], definition_revision)
        task_index = await self._active_tasks_by_key(project_id, wp_index_id)

        # 按 program_no 归一索引 definition（同一 sheet 内 program_no 语义唯一）。
        def_by_program: dict[str, ProcedureRowDefinition] = {}
        for d in defs:
            if d.program_no:
                def_by_program.setdefault(str(d.program_no), d)

        for prog in programs:
            prog_no = str(prog.get("program_no", "")).strip()
            d = def_by_program.get(prog_no)
            if d is None:
                continue
            task = task_index.get((d.sheet_key, d.definition_key))
            prog.update(self._task_overlay(task))
            prog["definition_key"] = d.definition_key
        return programs
