"""可恢复/可重复 backfill runner（Task 15）

Feature: procedure-delegation-notification
需求：7.6-7.9（保守状态映射、投影重建/校验报告）、13.5（backfill 可恢复/可重复 +
      coverage/conflict/orphan 报告 + 原始快照保留）
Design：C1/C2/C8（复用 importer / materialize / projection）、Legacy State Mapping
Properties：P24（旧状态保守映射）、P34（部署阶段 backfill 阶段能力）

职责（编排层，**复用** Task 3/4/9，绝不重造）：

1. **definition import**：复用 ``ProcedureDefinitionImporter``（JSON 模板 insert-if-absent）。
2. **task materialize**：复用 ``ProcedureTaskMaterializationService.materialize``（active partial
   unique upsert，已存在 task 不重置委派/工作流）。
3. **保守状态映射**：复用 ``ProcedureProjectionService.map_legacy_status``；把 legacy
   ``parsed_data.procedure_status`` 保守映射到 task 的 applicability/workflow，写入
   ``migration_confidence`` / ``migration_detail``（保留原始来源/值/规则/conflict 快照，
   不猜测更高状态）。
4. **legacy alias 匹配**：legacy row_id（``row-{program_no}`` / 数组序号）经 definition
   ``legacy_aliases`` / program_no 匹配到 task；无匹配 → orphaned（不臆造）。
5. **legacy ProcedureInstance.assigned_to → 底稿主编候选（report only）**：粗裁实例上的
   assignment **不复制到每条程序**，仅作为底稿主编候选写入报告；矛盾记 conflict。
6. **canonical trim key**：coverage 报告用 ``scope:``/``row:`` canonical key（复用 trim service）。
7. **projection 重建 + 校验报告**：复用 ``ProcedureProjectionService.rebuild`` + ``diff_report``。

**可恢复/可重复（Req 13.5）**：
- 每步幂等：definition insert-if-absent；materialize active upsert；状态映射只作用于
  ``migration_confidence IS NULL`` 且仍处默认 ``unassigned/execute`` 的 task（已 backfill 或
  已被人工推进的 task 跳过）。中断后重跑从未完成处继续，重复运行结果一致。
- **runner 显式 commit**（service 只 flush；backfill runner 是提交边界）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance, ProcedureRowTask
from app.services.procedure_definition_importer import ProcedureDefinitionImporter
from app.services.procedure_projection_service import (
    ProcedureProjectionService,
    map_legacy_status,
)
from app.services.procedure_task_materialization_service import (
    ProcedureTaskMaterializationService,
    _base_wp_code,
)
from app.services.procedure_trim_service import build_row_key, build_scope_key

logger = logging.getLogger(__name__)

# 仍处“默认未迁移”状态的 task 才允许 backfill 状态映射（可恢复/可重复护栏）。
_DEFAULT_WORKFLOW = "unassigned"
_DEFAULT_APPLICABILITY = "execute"

# legacy value 中可能承载 assignee 的字段名（保守探测）。
_LEGACY_ASSIGNEE_KEYS = ("assignee_staff_id", "assigned_to", "assignee", "assignee_id")
# legacy value 中可能承载状态的字段名。
_LEGACY_STATUS_KEYS = ("workflow_status", "execution_status", "status", "state")


# ---------------------------------------------------------------------------
# 报告模型
# ---------------------------------------------------------------------------


@dataclass
class BackfillReport:
    """一次 backfill 的完整报告（coverage / conflict / orphan / primary-editor）。"""

    project_id: str
    wp_index_count: int = 0
    definitions_imported: int = 0
    definitions_preserved: int = 0
    tasks_created: int = 0
    tasks_existing: int = 0
    # 状态映射
    status_mapped: int = 0
    status_skipped_non_default: int = 0
    conflicts: list[dict] = field(default_factory=list)
    orphans: list[dict] = field(default_factory=list)
    # canonical trim key 覆盖（scope/row）
    coverage_keys: list[str] = field(default_factory=list)
    # 底稿主编候选（来自 legacy ProcedureInstance.assigned_to，report only）
    primary_editor_candidates: list[dict] = field(default_factory=list)
    # 投影核对
    projection_rebuilt_wps: int = 0
    projection_mismatches: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "wp_index_count": self.wp_index_count,
            "definitions_imported": self.definitions_imported,
            "definitions_preserved": self.definitions_preserved,
            "tasks_created": self.tasks_created,
            "tasks_existing": self.tasks_existing,
            "status_mapped": self.status_mapped,
            "status_skipped_non_default": self.status_skipped_non_default,
            "conflict_count": len(self.conflicts),
            "conflicts": self.conflicts,
            "orphan_count": len(self.orphans),
            "orphans": self.orphans,
            "coverage_key_count": len(self.coverage_keys),
            "coverage_keys": self.coverage_keys,
            "primary_editor_candidates": self.primary_editor_candidates,
            "projection_rebuilt_wps": self.projection_rebuilt_wps,
            "projection_mismatch_count": len(self.projection_mismatches),
            "projection_mismatches": self.projection_mismatches,
        }


# ---------------------------------------------------------------------------
# 纯函数：legacy value 探测
# ---------------------------------------------------------------------------


def extract_legacy_status(value: object) -> str | None:
    """从 legacy procedure_status 值提取状态字符串（兼容裸字符串或 dict）。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for k in _LEGACY_STATUS_KEYS:
            v = value.get(k)
            if isinstance(v, str) and v.strip():
                return v
    return None


def extract_legacy_has_assignee(value: object) -> bool:
    """从 legacy value 探测是否有 assignee（保守：任一 assignee 字段非空即视为有）。"""
    if isinstance(value, dict):
        for k in _LEGACY_ASSIGNEE_KEYS:
            v = value.get(k)
            if v not in (None, "", []):
                return True
    return False


def legacy_row_program_no(row_id: str) -> str:
    """legacy row_id → 候选 program_no（剥离 ``row-`` / ``index-`` 前缀）。"""
    s = str(row_id or "").strip()
    for prefix in ("row-", "index-"):
        if s.startswith(prefix):
            return s[len(prefix):]
    return s


class ProcedureBackfillRunner:
    """可恢复/可重复 backfill 编排器（复用 importer / materialize / projection / trim）。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.importer = ProcedureDefinitionImporter(db)
        self.materializer = ProcedureTaskMaterializationService(db)
        self.projection = ProcedureProjectionService(db)

    # -- wp_index 装载 -------------------------------------------------------

    async def _load_wp_indexes(
        self, project_id: UUID, wp_index_ids: list[UUID] | None
    ) -> list[dict]:
        """加载项目下 wp_index（可选子集）；返回 [{id, wp_code, audit_cycle, wp_name}]。"""
        from app.models.workpaper_models import WpIndex

        conds = [
            WpIndex.project_id == project_id,
            WpIndex.is_deleted == sa.false(),
        ]
        if wp_index_ids:
            conds.append(WpIndex.id.in_(wp_index_ids))
        rows = (
            await self.db.execute(
                sa.select(
                    WpIndex.id, WpIndex.wp_code, WpIndex.audit_cycle, WpIndex.wp_name
                ).where(*conds)
            )
        ).all()
        return [
            {
                "id": r[0],
                "wp_code": r[1],
                "audit_cycle": r[2] or "A",
                "wp_name": r[3],
            }
            for r in rows
        ]

    # -- Step 1：definition import（复用 importer，insert-if-absent） ---------

    async def import_definitions(self, wp_codes: set[str]) -> tuple[int, int]:
        """为给定 wp_codes 从 JSON 模板导入定义（insert-if-absent，保留旧 revision）。

        复用 ``ProcedureDefinitionImporter``；template_code=table_code、sheet_key=table_code，
        与 materialize 的 base-code 匹配一致。返回 (inserted, preserved)。
        """
        from app.services.procedure_table_auto_service import _load_templates

        tables = (_load_templates() or {}).get("tables", {}) or {}
        inserted = 0
        preserved = 0
        for table_code, template in tables.items():
            if not isinstance(template, dict):
                continue
            base = _base_wp_code(table_code)
            if base not in wp_codes:
                continue
            result = ProcedureDefinitionImporter.build_from_json_template(
                table_code, table_code, template
            )
            if not result.definitions:
                continue
            res = await self.importer.import_definitions(result)
            inserted += res["inserted"]
            preserved += res["preserved"]
        return inserted, preserved

    # -- Step 3：保守状态映射（复用 map_legacy_status；幂等护栏） --------------

    async def _legacy_projection(self, wp_id: UUID) -> dict:
        """读单底稿 legacy parsed_data.procedure_status（纯读）。"""
        from app.models.workpaper_models import WorkingPaper

        parsed = (
            await self.db.execute(
                sa.select(WorkingPaper.parsed_data).where(WorkingPaper.id == wp_id)
            )
        ).scalar_one_or_none()
        if not isinstance(parsed, dict):
            return {}
        ps = parsed.get("procedure_status")
        return ps if isinstance(ps, dict) else {}

    async def _map_status_for_wp(
        self, task_by_key: dict[tuple[str, str], ProcedureRowTask], wp_id: UUID
    ) -> tuple[int, int, list[dict], list[dict]]:
        """把某底稿的 legacy procedure_status 保守映射到已物化 task。

        - 仅作用于 ``migration_confidence IS NULL`` 且仍 default(unassigned/execute) 的 task
          （可恢复/可重复护栏：已 backfill 或人工推进的不动）。
        - 无匹配 legacy row → orphaned（不臆造）。
        返回 (mapped, skipped_non_default, conflicts, orphans)。
        """
        legacy = await self._legacy_projection(wp_id)
        mapped = 0
        skipped = 0
        conflicts: list[dict] = []
        orphans: list[dict] = []

        # 建两套索引：
        #  - def_index：(sheet_key, definition_key) → task（canonical 身份；rebuilt 投影 row_id
        #    即 definition_key，见 projection.rebuild，可重复运行必须先按此直配）。
        #  - prog_index：(sheet_key, program_no) → task（legacy alias：row-{program_no}/数组序号）。
        prog_index: dict[tuple[str, str], ProcedureRowTask] = {}
        def_index: dict[tuple[str, str], ProcedureRowTask] = {}
        for (sheet_key, dk), t in task_by_key.items():
            def_index[(sheet_key, dk)] = t
            if t.program_no:
                prog_index[(sheet_key, str(t.program_no))] = t

        for sheet_key, rows in legacy.items():
            if not isinstance(rows, dict):
                continue
            for row_id, value in rows.items():
                # 先按 canonical definition_key 直配（rebuilt 投影），再退回 legacy alias。
                task = def_index.get((sheet_key, row_id))
                if task is None:
                    cand_no = legacy_row_program_no(row_id)
                    task = prog_index.get((sheet_key, cand_no))
                if task is None:
                    orphans.append(
                        {
                            "wp_id": str(wp_id),
                            "sheet_key": sheet_key,
                            "legacy_row_id": row_id,
                            "reason": "no_matching_definition_task",
                        }
                    )
                    continue
                # 幂等护栏：只映射尚未 backfill 且仍默认态的 task。
                if task.migration_confidence is not None or (
                    task.workflow_status != _DEFAULT_WORKFLOW
                    or task.applicability_status != _DEFAULT_APPLICABILITY
                ):
                    skipped += 1
                    continue
                legacy_status = extract_legacy_status(value)
                has_assignee = extract_legacy_has_assignee(value)
                m = map_legacy_status(legacy_status, has_assignee=has_assignee)
                await self.db.execute(
                    sa.update(ProcedureRowTask)
                    .where(ProcedureRowTask.id == task.id)
                    .values(
                        applicability_status=m["applicability"],
                        workflow_status=m["workflow"],
                        migration_confidence=m["confidence"],
                        migration_detail={
                            "source": "backfill",
                            "legacy_row_id": row_id,
                            **m["detail"],
                        },
                        updated_at=sa.func.now(),
                    )
                )
                # 就地更新内存对象，避免同批重复处理。
                task.migration_confidence = m["confidence"]
                task.workflow_status = m["workflow"]
                task.applicability_status = m["applicability"]
                mapped += 1
                if m["confidence"] == "conflict":
                    conflicts.append(
                        {
                            "wp_id": str(wp_id),
                            "sheet_key": sheet_key,
                            "legacy_row_id": row_id,
                            "task_id": str(task.id),
                            "detail": m["detail"],
                        }
                    )
        return mapped, skipped, conflicts, orphans

    # -- Step 5：底稿主编候选（report only，绝不复制到每条程序） ---------------

    async def _primary_editor_candidates(
        self, project_id: UUID, wp_codes: set[str]
    ) -> list[dict]:
        """从 legacy ProcedureInstance.assigned_to 汇总底稿主编候选（不复制到 task）。

        同一 wp_code 若粗裁实例上出现多个不同 assigned_to → 记 conflict，不猜测唯一主编。
        """
        rows = (
            await self.db.execute(
                sa.select(
                    ProcedureInstance.wp_code,
                    ProcedureInstance.assigned_to,
                ).where(
                    ProcedureInstance.project_id == project_id,
                    ProcedureInstance.assigned_to.is_not(None),
                    ProcedureInstance.is_deleted == sa.false(),
                )
            )
        ).all()
        by_code: dict[str, set[str]] = {}
        for wp_code, assigned_to in rows:
            if not wp_code:
                continue
            base = str(wp_code)
            if wp_codes and base not in wp_codes:
                # 也接受 sheet 级编码归一到 base
                base = _base_wp_code(str(wp_code))
                if base not in wp_codes:
                    continue
            by_code.setdefault(base, set()).add(str(assigned_to))
        candidates: list[dict] = []
        for wp_code, staff_ids in sorted(by_code.items()):
            ids = sorted(staff_ids)
            candidates.append(
                {
                    "wp_code": wp_code,
                    "candidate_staff_ids": ids,
                    "conflict": len(ids) > 1,
                    "note": "底稿主编候选（不复制到每条程序）",
                }
            )
        return candidates

    # -- 主入口：显式 commit（可恢复/可重复） --------------------------------

    async def run(
        self,
        project_id: UUID,
        *,
        wp_index_ids: list[UUID] | None = None,
        commit: bool = True,
    ) -> BackfillReport:
        """执行一次完整 backfill；返回 coverage/conflict/orphan/主编候选报告。

        步骤：definition import → materialize → 保守状态映射 → 投影重建/核对 →
        主编候选 → canonical coverage key。**runner 显式 commit**（可关闭用于测试/演练）。
        """
        report = BackfillReport(project_id=str(project_id))
        wp_indexes = await self._load_wp_indexes(project_id, wp_index_ids)
        report.wp_index_count = len(wp_indexes)
        if not wp_indexes:
            if commit:
                await self.db.commit()
            return report

        wp_codes = {wi["wp_code"] for wi in wp_indexes if wi["wp_code"]}
        id_list = [wi["id"] for wi in wp_indexes]

        # Step 1：definition import（insert-if-absent）。
        inserted, preserved = await self.import_definitions(wp_codes)
        report.definitions_imported = inserted
        report.definitions_preserved = preserved

        # Step 2：materialize（active partial unique upsert，已存在不重置）。
        mat = await self.materializer.materialize(
            project_id, id_list, request_id="backfill"
        )
        report.tasks_created = mat["created"]
        report.tasks_existing = mat["existing"]

        # Step 3-4：保守状态映射 + orphan（按 wp_index active tasks）。
        for wi in wp_indexes:
            task_index = await self.materializer._active_tasks_by_key(
                project_id, wi["id"]
            )
            # coverage：canonical trim key（scope + 每行 row）。
            report.coverage_keys.append(
                build_scope_key(wi["audit_cycle"], wi["wp_code"] or "")
            )
            wp_ids_seen: set[UUID] = set()
            for (sheet_key, dk), t in task_index.items():
                report.coverage_keys.append(
                    build_row_key(t.wp_code or wi["wp_code"] or "", sheet_key, dk)
                )
                if t.wp_id is not None:
                    wp_ids_seen.add(t.wp_id)
            # 仅对已绑定底稿的 task 做 legacy 状态映射（未绑定 wp 无 legacy projection）。
            for wp_id in wp_ids_seen:
                m, s, c, o = await self._map_status_for_wp(task_index, wp_id)
                report.status_mapped += m
                report.status_skipped_non_default += s
                report.conflicts.extend(c)
                report.orphans.extend(o)

        # Step 5：底稿主编候选（report only）。
        report.primary_editor_candidates = await self._primary_editor_candidates(
            project_id, wp_codes
        )

        # Step 6：投影重建 + 核对报告（复用 projection）。
        all_wp_ids: set[UUID] = set()
        for wi in wp_indexes:
            task_index = await self.materializer._active_tasks_by_key(
                project_id, wi["id"]
            )
            for (_sk, _dk), t in task_index.items():
                if t.wp_id is not None:
                    all_wp_ids.add(t.wp_id)
        for wp_id in sorted(all_wp_ids, key=str):
            await self.projection.rebuild(wp_id)
            report.projection_rebuilt_wps += 1
            diff = await self.projection.diff_report(wp_id)
            if diff["mismatches"]:
                report.projection_mismatches.extend(diff["mismatches"])

        if commit:
            await self.db.commit()

        logger.info(
            "backfill project=%s wp_index=%d defs(+%d/=%d) tasks(+%d/=%d) "
            "mapped=%d skipped=%d conflicts=%d orphans=%d rebuilt=%d",
            project_id,
            report.wp_index_count,
            report.definitions_imported,
            report.definitions_preserved,
            report.tasks_created,
            report.tasks_existing,
            report.status_mapped,
            report.status_skipped_non_default,
            len(report.conflicts),
            len(report.orphans),
            report.projection_rebuilt_wps,
        )
        return report
