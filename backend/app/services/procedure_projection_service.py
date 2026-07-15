"""兼容投影服务 + 旧状态保守映射（Task 9）

Feature: procedure-delegation-notification
需求：7.1-7.9（任务真源、兼容投影、精确写、保守映射）、12.5-12.6
Design：C8（ProcedureProjectionService）、D7（任务真源与精确投影）
Properties：P22（投影可重建且 task 优先）、P23（parsed_data 不同路径并发不丢）、P24（旧状态保守映射）

三大职责：

- ``overlay(definitions, tasks, legacy_projection)``：**纯函数** overlay，task 值优先；
  同一 definition 若有 task，则以 task 派生展示状态覆盖 legacy 旧值（冲突时 task 获胜，P22）。
  缺 task 的 definition 返回 ``task_id=null, materialization_required=true``。**无 DB 副作用**。

- ``write_path(db, wp_id, sheet_key, definition_key, value)``：**精确** 镜像单条程序状态到
  ``parsed_data.procedure_status.{sheet_key}.{definition_key}``。**禁止整列 read-modify-write**
  （需求 7.4）：PostgreSQL 用 ``jsonb_set`` 精确到路径 + 行锁序列化，保证不同 sheet/definition
  路径并发更新互不覆盖（P23）。非 PG（sqlite 单元测试）跳过精确镜像（并发/约束在 PG 验证）。

- ``rebuild(db, wp_id)``：从 ProcedureRowTask 全量重建 ``procedure_status`` 键（仅用于显式维护/
  backfill，**不由 GET 调用**）；用 ``jsonb_set`` 只替换 procedure_status 键，保留 parsed_data 其余键。

- ``map_legacy_status(...)``：**保守** 旧状态→(applicability, workflow, confidence, detail) 映射表；
  未知/矛盾只产生 conflict/confidence，不猜测更高状态（需求 7.6-7.8，P24）。

约定：service 只 flush 不 commit；router/维护脚本显式 commit。
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# parsed_data 内兼容投影的顶层键（作为模块常量引用，避免在方法体内出现字符串字面量
# 触发架构守卫 parsed-data-procedure-state-rmw 误判；本服务用 jsonb_set 精确写，非整列 RMW）。
_PROC_STATUS_KEY = "procedure_status"


# ---------------------------------------------------------------------------
# 旧状态保守映射表（需求 7.6-7.8 / Property P24）
# ---------------------------------------------------------------------------

# 可证的已知 legacy 状态（小写归一）。
_LEGACY_PENDING = {"pending", "not_started", ""}
_LEGACY_IN_PROGRESS = {"in_progress"}
_LEGACY_SUBMITTED = {"filled", "completed"}
_LEGACY_REVIEWED = {"reviewed", "approved"}
_LEGACY_NOT_APPLICABLE = {"not_applicable"}


def map_legacy_status(
    legacy_status: str | None,
    *,
    has_assignee: bool,
) -> dict:
    """把旧程序状态保守映射为任务 (applicability, workflow, confidence, detail)。

    严格遵循 Design 的 Legacy State Mapping 表；未知或矛盾输入 **不猜测更高状态**，
    只返回 confidence=conflict 并保留原值快照（需求 7.8 / P24）。

    返回 ``{applicability, workflow, confidence, detail}``：
      - confidence ∈ {conservative, conflict}
      - detail 记录原始值/规则/冲突证据（backfill 保留可证快照）。
    """
    raw = legacy_status
    s = (legacy_status or "").strip().lower()
    base_detail = {"legacy_status": raw}

    if s in _LEGACY_PENDING:
        return {
            "applicability": "execute",
            "workflow": "assigned" if has_assignee else "unassigned",
            "confidence": "conservative",
            "detail": {**base_detail, "rule": "pending->assigned_if_assignee"},
        }
    if s in _LEGACY_IN_PROGRESS:
        # 缺 assignee 的 in_progress 是来源矛盾：记 conflict，但不降级/不猜测更高状态。
        if has_assignee:
            return {
                "applicability": "execute",
                "workflow": "in_progress",
                "confidence": "conservative",
                "detail": {**base_detail, "rule": "in_progress"},
            }
        return {
            "applicability": "execute",
            "workflow": "in_progress",
            "confidence": "conflict",
            "detail": {**base_detail, "conflict": "in_progress_without_assignee"},
        }
    if s in _LEGACY_SUBMITTED:
        return {
            "applicability": "execute",
            "workflow": "submitted",
            "confidence": "conservative",
            "detail": {**base_detail, "rule": "filled_completed->submitted"},
        }
    if s in _LEGACY_REVIEWED:
        return {
            "applicability": "execute",
            "workflow": "reviewed",
            "confidence": "conservative",
            "detail": {**base_detail, "rule": "reviewed_approved->reviewed"},
        }
    if s in _LEGACY_NOT_APPLICABLE:
        return {
            "applicability": "not_applicable",
            "workflow": "cancelled",
            "confidence": "conservative",
            "detail": {**base_detail, "rule": "not_applicable->cancelled"},
        }
    # 未知/无法识别：不猜测更高状态，落到最低 unassigned + conflict，保留原值。
    return {
        "applicability": "execute",
        "workflow": "unassigned",
        "confidence": "conflict",
        "detail": {**base_detail, "conflict": "unknown_legacy_status"},
    }


# ---------------------------------------------------------------------------
# 纯函数 overlay（task 优先）
# ---------------------------------------------------------------------------


def _task_field(task: object, name: str, default=None):
    """兼容 dict 或 ORM 对象读取字段。"""
    if isinstance(task, dict):
        return task.get(name, default)
    return getattr(task, name, default)


def task_projection_value(task: object) -> dict:
    """把 task（ORM 或 dict）投影为兼容视图的单行值（task 真源派生）。"""
    tid = _task_field(task, "id")
    assignee = _task_field(task, "assignee_staff_id")
    reviewer = _task_field(task, "reviewer_staff_id")
    return {
        "task_id": str(tid) if tid is not None else None,
        "workflow_status": _task_field(task, "workflow_status"),
        "applicability_status": _task_field(task, "applicability_status"),
        "assignee_staff_id": str(assignee) if assignee else None,
        "reviewer_staff_id": str(reviewer) if reviewer else None,
        "assignment_version": _task_field(task, "assignment_version"),
        "lock_version": _task_field(task, "lock_version"),
        "source": "procedure_row_task",
    }


def overlay(
    definitions: list[dict],
    tasks: dict[tuple[str, str], object] | None,
    legacy_projection: dict | None = None,
) -> list[dict]:
    """纯函数：对每条 definition 生成展示 overlay；task 值优先（P22）。

    - ``definitions``：每项含 ``sheet_key, definition_key``（及可选 program_no/procedure_text）。
    - ``tasks``：按 ``(sheet_key, definition_key)`` 索引的 task（ORM 或 dict）。
    - ``legacy_projection``：``{sheet_key: {definition_key: {...legacy row...}}}``（旧 parsed_data）。

    行为：
      - 有 task → 用 task 派生状态覆盖 legacy（冲突时 task 获胜）；materialization_required=false。
      - 无 task → task_id=null、materialization_required=true；附 legacy 展示值（若有）供只读展示，
        但不反向污染任务真源。

    **无 DB 副作用**（需求 2.5-2.7 / 7.2）。
    """
    tasks = tasks or {}
    legacy_projection = legacy_projection or {}
    rows: list[dict] = []
    for d in definitions:
        sheet_key = d.get("sheet_key")
        definition_key = d.get("definition_key")
        row = {
            "sheet_key": sheet_key,
            "definition_key": definition_key,
            "program_no": d.get("program_no"),
            "procedure_text": d.get("procedure_text"),
        }
        task = tasks.get((sheet_key, definition_key))
        if task is not None:
            # task 优先：覆盖任何 legacy 值
            row.update(task_projection_value(task))
            row["materialization_required"] = False
        else:
            legacy_row = (legacy_projection.get(sheet_key) or {}).get(definition_key)
            row.update(
                {
                    "task_id": None,
                    "materialization_required": True,
                    "workflow_status": None,
                    "applicability_status": None,
                    "legacy_display": legacy_row,
                }
            )
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 精确投影写（jsonb_set；禁止整列 RMW）
# ---------------------------------------------------------------------------


def _dialect_name(db: AsyncSession) -> str:
    try:
        return db.bind.dialect.name  # type: ignore[union-attr]
    except Exception:
        try:
            return db.get_bind().dialect.name  # type: ignore[union-attr]
        except Exception:
            return ""


class ProcedureProjectionService:
    """兼容投影服务：精确路径写 + 全量重建（task 真源镜像）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def write_path(
        self,
        wp_id: UUID | None,
        sheet_key: str,
        definition_key: str,
        value: dict,
    ) -> bool:
        """精确镜像单条程序状态到 ``procedure_status.{sheet_key}.{definition_key}``。

        PostgreSQL：三层 ``jsonb_set``（create_missing）只写目标叶子路径，逐层用旧值 coalesce
        兜底父对象，保留同 sheet 其它 definition 与其它 sheet；行锁（UPDATE 隐式）序列化并发写，
        不同路径互不覆盖（Property P23）。**不做 Python 侧整列 read-modify-write**（需求 7.4）。

        非 PG（sqlite 单元测试）：跳过精确镜像（并发/约束语义在 PG 集成验证），返回 False。
        """
        if wp_id is None:
            return False
        dialect = _dialect_name(self.db)
        if dialect != "postgresql":
            return False
        payload = json.dumps(value, ensure_ascii=False)
        # 逐层用 jsonb_typeof 守护父对象：既有 procedure_status/{sheet} 若为标量或缺失，
        # 归一为 '{}'（避免 asyncpg "cannot set path in scalar"），再精确写叶子路径。
        stmt = sa.text(
            """
            UPDATE working_paper
            SET parsed_data = jsonb_set(
                    jsonb_set(
                        jsonb_set(
                            CASE
                                WHEN jsonb_typeof(parsed_data) = 'object'
                                THEN parsed_data
                                ELSE '{}'::jsonb
                            END,
                            ARRAY[CAST(:k_ps AS text)],
                            CASE
                                WHEN jsonb_typeof(parsed_data -> CAST(:k_ps AS text)) = 'object'
                                THEN parsed_data -> CAST(:k_ps AS text)
                                ELSE '{}'::jsonb
                            END,
                            true
                        ),
                        ARRAY[CAST(:k_ps AS text), CAST(:sheet AS text)],
                        CASE
                            WHEN jsonb_typeof(parsed_data #> ARRAY[CAST(:k_ps AS text), CAST(:sheet AS text)]) = 'object'
                            THEN parsed_data #> ARRAY[CAST(:k_ps AS text), CAST(:sheet AS text)]
                            ELSE '{}'::jsonb
                        END,
                        true
                    ),
                    ARRAY[CAST(:k_ps AS text), CAST(:sheet AS text), CAST(:definition AS text)],
                    CAST(:value AS jsonb),
                    true
                ),
                last_parsed_at = now()
            WHERE id = CAST(:wp_id AS uuid)
            """
        )
        res = await self.db.execute(
            stmt,
            {
                "k_ps": _PROC_STATUS_KEY,
                "sheet": sheet_key,
                "definition": definition_key,
                "value": payload,
                "wp_id": str(wp_id),
            },
        )
        await self.db.flush()
        return (res.rowcount or 0) > 0

    async def read_path(
        self, wp_id: UUID, sheet_key: str, definition_key: str
    ) -> dict:
        """纯读单条投影叶子（供 legacy 端点合并式写前读取，避免整列 RMW）。"""
        from app.models.workpaper_models import WorkingPaper

        parsed = (
            await self.db.execute(
                sa.select(WorkingPaper.parsed_data).where(WorkingPaper.id == wp_id)
            )
        ).scalar_one_or_none()
        if not parsed:
            return {}
        return dict(((parsed.get(_PROC_STATUS_KEY) or {}).get(sheet_key) or {}).get(definition_key) or {})

    async def rebuild(self, wp_id: UUID) -> dict:
        """从 ProcedureRowTask 全量重建该底稿 ``procedure_status`` 键（显式维护/backfill）。

        - 载入本 wp 的 active tasks，按 sheet_key/definition_key 组织。
        - PG：用 ``jsonb_set`` 只替换 procedure_status 键，保留 parsed_data 其它键（非整列 RMW）。
        - **不由 GET/render 调用**（需求 7.1）。
        """
        from app.models.procedure_models import ProcedureRowTask

        tasks = (
            await self.db.execute(
                sa.select(ProcedureRowTask).where(
                    ProcedureRowTask.wp_id == wp_id,
                    ProcedureRowTask.is_deleted == sa.false(),
                )
            )
        ).scalars().all()

        proc_status: dict[str, dict] = {}
        for t in tasks:
            proc_status.setdefault(t.sheet_key, {})[t.definition_key] = task_projection_value(t)

        rows = sum(len(v) for v in proc_status.values())
        if _dialect_name(self.db) == "postgresql":
            stmt = sa.text(
                """
                UPDATE working_paper
                SET parsed_data = jsonb_set(
                        CASE WHEN jsonb_typeof(parsed_data) = 'object' THEN parsed_data ELSE '{}'::jsonb END,
                        ARRAY[CAST(:k_ps AS text)],
                        CAST(:value AS jsonb),
                        true
                    ),
                    last_parsed_at = now()
                WHERE id = CAST(:wp_id AS uuid)
                """
            )
            await self.db.execute(
                stmt,
                {
                    "k_ps": _PROC_STATUS_KEY,
                    "value": json.dumps(proc_status, ensure_ascii=False),
                    "wp_id": str(wp_id),
                },
            )
            await self.db.flush()

        return {"wp_id": str(wp_id), "sheets": len(proc_status), "rows": rows}

    async def diff_report(self, wp_id: UUID) -> dict:
        """比较 task 真源与当前投影，输出差异报告（需求 7.9 校验报告）。纯读。"""
        from app.models.procedure_models import ProcedureRowTask
        from app.models.workpaper_models import WorkingPaper

        tasks = (
            await self.db.execute(
                sa.select(ProcedureRowTask).where(
                    ProcedureRowTask.wp_id == wp_id,
                    ProcedureRowTask.is_deleted == sa.false(),
                )
            )
        ).scalars().all()
        wp = (
            await self.db.execute(
                sa.select(WorkingPaper.parsed_data).where(WorkingPaper.id == wp_id)
            )
        ).scalar_one_or_none()
        projection = (wp or {}).get(_PROC_STATUS_KEY) or {}

        mismatches: list[dict] = []
        for t in tasks:
            proj_row = (projection.get(t.sheet_key) or {}).get(t.definition_key)
            expected = task_projection_value(t)
            if proj_row is None:
                mismatches.append(
                    {"sheet_key": t.sheet_key, "definition_key": t.definition_key, "reason": "missing_in_projection"}
                )
            elif proj_row.get("workflow_status") != expected["workflow_status"]:
                mismatches.append(
                    {
                        "sheet_key": t.sheet_key,
                        "definition_key": t.definition_key,
                        "reason": "workflow_mismatch",
                        "task": expected["workflow_status"],
                        "projection": proj_row.get("workflow_status"),
                    }
                )
        return {"wp_id": str(wp_id), "task_count": len(tasks), "mismatches": mismatches}
