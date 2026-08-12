"""粗裁/细裁与裁剪方案应用服务（Task 6）

Feature: procedure-delegation-notification
需求：3.3-3.8（两层裁剪 + canonical 方案 key + 真实 applied + legacy UUID 409）、4.2-4.6（一次性 preview 安全模型）
Design：C4（ProcedureTrimService）、D4（ProcedureOperationPreview 一次性凭证）
Properties：P9（裁剪与 workflow 正交）、P10（方案 applied 真实）

职责：
- **粗裁（WorkpaperScopeInstance）**：保留 ProcedureInstance 的 execute/skip/not_applicable 粗裁；
  粗裁为 skip/not_applicable 时级联取消该范围未完成的 ProcedureRowTask（保留历史，需求 3.4）。
- **细裁（applicability）**：ProcedureRowTask.applicability_status ∈ {execute, not_applicable}。
  细裁 not_applicable → 调 TransitionService **cancel**（applicability→not_applicable + workflow→cancelled，
  不伪装 submitted/reviewed，需求 3.3/3.5）。恢复 execute → 调 TransitionService **reopen**
  （applicability→execute + workflow cancelled→unassigned）；恢复后须由 Delegator 重新 assign→ack，
  **不自动完成/不自动恢复原执行人**（Property P9）。
- **方案（canonical key）**：`scope:{cycle}:{wp_index_code}` 与 `row:{template_code}:{sheet_key}:{definition_key}`，
  保存 definition revision 与程序文本快照（需求 3.6）。
- **方案 preview/apply**：与委派/ reconcile 共用一次性 ``ProcedureOperationPreview``（防篡改/越权/过期/
  成员变化/版本变化 409，一次消费 + request_id 幂等）；返回 **真实** applied/unchanged/conflict —
  无真实字段变化时 applied=0（需求 3.7 / Property P10）。
- **legacy UUID key**：row key 的 definition_key 若为非内容寻址（无 ``::``）且无法经别名 **唯一** 转换，
  记 migration_conflict 并 **409**，不按数组顺序或相似文本猜测（需求 3.8）。

**所有** ProcedureRowTask workflow/applicability 写与 ProcedureInstance 粗裁状态写都 **只** 经
``ProcedureTaskTransitionService``（单一状态机入口 / 架构守卫只放行该类）。本服务自身不直接写这些状态字段。

约定：service 只 flush 不 commit；router 显式 commit。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.procedure_trim_engine import TrimReasonCode
from app.models.procedure_models import (
    ProcedureInstance,
    ProcedureRowDefinition,
    ProcedureRowTask,
    ProcedureTrimScheme,
)
from app.models.staff_models import ProjectAssignment
from app.services.procedure_definition_importer import canonical_json, sha256_hex
from app.services.procedure_operation_preview import (
    consume_and_apply,
    create_preview,
)
from app.services.procedure_reconcile_service import is_legacy_uuid_key
from app.services.procedure_task_materialization_service import _base_wp_code
from app.services.procedure_task_transition_service import (
    APPLICABILITY_EXECUTE,
    APPLICABILITY_NOT_APPLICABLE,
    TERMINAL_WORKFLOW_STATES,
    ProcedureTaskTransitionService,
    scope_state_differs,
)

logger = logging.getLogger(__name__)

TRIM_OPERATION = "trim"

KIND_SCOPE = "scope"
KIND_ROW = "row"

_SCOPE_STATUSES = ("execute", "skip", "not_applicable")
_ROW_APPLICABILITIES = (APPLICABILITY_EXECUTE, APPLICABILITY_NOT_APPLICABLE)

# 粗裁结构化理由码的合法取值集合。
#
# 🔴 从 `TrimReasonCode` 枚举**派生**而不是另写一份字面量元组 —— 平台已因手写清单
#    栽过（守卫的表名清单漏一张 ⇒ 断言以 KeyError 形式假失败）。枚举新增取值时
#    本集合自动跟随；前端镜像由 `composables/trimReasonCodes.ts` 的交叉锁死守卫
#    保证同步（一侧新增另一侧未跟进即打红）。
_VALID_TRIM_REASON_CODES = frozenset(c.value for c in TrimReasonCode)

# 完整性敏感清单项目级覆盖的 checklist_responses 键前缀（Task 14）。
#
# 🔴 从读取侧 import 而不是另写一份字面量：`trim_decision_context._load_completeness_override`
#    按该前缀 LIKE 查询，两侧漂移会让「写进去的覆盖读不出来」，而两侧单测各用自己的
#    前缀构造样本 ⇒ 都全绿，只有真实往返才暴露。
#
# 🔴 引公开别名 `COMPLETENESS_SCOPE_ITEM_PREFIX` 而不是私有名 `_CSCOPE_PREFIX`
#    （读取侧模块文档明确要求）。本文件曾同时 import 两个名字（一个未被使用），
#    那种"看着像双真源、实际同一对象"的写法会让守卫难以判断写入侧到底引的是哪个。
from app.services.trim_decision_context import (  # noqa: E402
    COMPLETENESS_SCOPE_ITEM_PREFIX as _CSCOPE_ITEM_PREFIX,
)


# ---------------------------------------------------------------------------
# Canonical trim key（需求 3.6）
# ---------------------------------------------------------------------------


def build_scope_key(cycle: str, wp_index_code: str) -> str:
    """粗裁 canonical key：``scope:{cycle}:{wp_index_code}``。"""
    return f"{KIND_SCOPE}:{cycle}:{wp_index_code}"


def build_row_key(template_code: str, sheet_key: str, definition_key: str) -> str:
    """细裁 canonical key：``row:{template_code}:{sheet_key}:{definition_key}``。"""
    return f"{KIND_ROW}:{template_code}:{sheet_key}:{definition_key}"


class TrimSchemeError(HTTPException):
    """方案应用错误：legacy UUID key 无法唯一转换 → 409 migration_conflict。"""

    def __init__(self, migration_conflicts: list[dict]):
        super().__init__(
            status_code=409,
            detail={
                "error": "migration_conflict",
                "message": "方案含无法唯一转换的 legacy key，拒绝按顺序/文本猜测",
                "migration_conflicts": migration_conflicts,
            },
        )


class ProcedureTrimService:
    """两层裁剪 + 方案 preview/apply（真实 applied）。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.transition = ProcedureTaskTransitionService(db)

    # ======================================================================
    # 细裁：单行 applicability（走 TransitionService cancel / reopen）
    # ======================================================================

    async def _load_task(self, project_id: UUID, task_id: UUID) -> ProcedureRowTask:
        task = (
            await self.db.execute(
                sa.select(ProcedureRowTask)
                .where(
                    ProcedureRowTask.id == task_id,
                    ProcedureRowTask.project_id == project_id,
                    ProcedureRowTask.is_deleted == sa.false(),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return task

    async def set_row_not_applicable(
        self,
        project_id: UUID,
        task_id: UUID,
        *,
        actor_user_id: UUID | None,
        reason: str,
        request_id: str | None = None,
    ) -> dict:
        """细裁 → not_applicable：applicability=not_applicable + workflow→cancelled（TransitionService）。"""
        task = await self._load_task(project_id, task_id)
        changed = await self.transition.cancel(
            task,
            actor_user_id=actor_user_id,
            reason=reason,
            request_id=request_id,
            set_applicability=APPLICABILITY_NOT_APPLICABLE,
            event_type="trim_not_applicable",
        )
        return {
            "task_id": str(task.id),
            "changed": changed,
            "applicability_status": task.applicability_status,
            "workflow_status": task.workflow_status,
        }

    async def restore_row_execute(
        self,
        project_id: UUID,
        task_id: UUID,
        *,
        actor_user_id: UUID | None,
        request_id: str | None = None,
        reason: str | None = None,
    ) -> dict:
        """细裁恢复 → execute：applicability=execute + workflow cancelled→unassigned（TransitionService reopen）。

        恢复后 workflow=unassigned，须由 Delegator 重新 assign→ack（不自动完成，Property P9）。
        """
        task = await self._load_task(project_id, task_id)
        changed = await self.transition.reopen(
            task,
            actor_user_id=actor_user_id,
            request_id=request_id,
            set_applicability=APPLICABILITY_EXECUTE,
            reason=reason,
            event_type="trim_restore",
        )
        return {
            "task_id": str(task.id),
            "changed": changed,
            "applicability_status": task.applicability_status,
            "workflow_status": task.workflow_status,
            "requires_reassign": True,
        }

    # ======================================================================
    # 粗裁读辅助（供委派阻断 / 级联）
    # ======================================================================

    async def is_scope_trimmed(
        self, project_id: UUID, cycle: str, wp_index_code: str
    ) -> bool:
        """粗裁是否为 skip/not_applicable（供 Task 8 委派前置阻断，需求 3.4）。"""
        row = (
            await self.db.execute(
                sa.select(ProcedureInstance.status).where(
                    ProcedureInstance.project_id == project_id,
                    ProcedureInstance.audit_cycle == cycle,
                    ProcedureInstance.wp_code == wp_index_code,
                    ProcedureInstance.is_deleted == sa.false(),
                    ProcedureInstance.status.in_(["skip", "not_applicable"]),
                )
            )
        ).first()
        return row is not None

    # ======================================================================
    # 完整性敏感清单项目级覆盖（Task 14：R5.5 / R5.6 / R5.7）
    # ======================================================================

    async def set_completeness_scope_override(
        self,
        project_id: UUID,
        *,
        cycle: str,
        sensitive: bool,
        actor_user_id: UUID,
        reason: str,
    ) -> dict:
        """写一条完整性敏感清单的项目级覆盖（``B50-T3-cscope-{cycle}``）。

        ## 为什么落 ``checklist_responses`` 而不是新建一张表

        「本项目认为 L 循环的完整性风险不高」本质是一条**风险评估判断**，不是一次
        裁剪操作：它与 B50 同生命周期（B50 审批锁定后应自动只读）、天然有
        ``updated_by`` / ``updated_at`` 留痕、且零迁移成本。放进
        ``procedure_trim_schemes.trim_data`` 反而语义错位 —— 那里是**带日期的历史
        方案快照**，键空间是 procedure_instance UUID，把「当前生效的项目级口径」
        塞进历史快照里，下次存快照就会把它复制一份或覆盖掉。

        ## 三条约束

        1. **`Y`/`N` 都是「已表态」**，只有「该循环没有行」才算未覆盖。故本方法
           **不提供**「写空串取消表态」的语义 —— 取消表态用 :meth:`clear_completeness_scope_override`
           删行，避免出现「有行但 conclusion 为空」这种下游读取端要额外兜底的脏态。
        2. **理由必填**（R5.5）。覆盖平台默认清单是一项需要向质控与项目质量控制
           复核人解释的判断，没有理由的覆盖在复核时无法评价其适当性；故空理由直接
           拒绝而不是存一个空串。
        3. **只写这一个 item_id**，绝不触碰 B50 的矩阵 / cycle / plan 三类键。
           守卫另有一条断言「cscope 行不改变 ``load_b50_accounts()`` 的任何输出」
           （R5.5 的零污染要求）。

        Returns: ``{"cycle": ..., "sensitive": bool, "created": bool, "updated": bool}``
        """
        normalized = str(cycle or "").strip().upper()
        if not normalized:
            raise HTTPException(status_code=400, detail="cycle 不能为空")
        text_reason = str(reason or "").strip()
        if not text_reason:
            raise HTTPException(
                status_code=400,
                detail="覆盖平台默认完整性敏感清单必须填写理由（供质控与复核评价其适当性）",
            )

        b50_wp = await self._require_b50_wp_id(project_id)
        item_id = f"{_CSCOPE_ITEM_PREFIX}{normalized}"
        conclusion = "Y" if sensitive else "N"
        now = datetime.now(timezone.utc)

        # 🔴 UUID 与 timestamptz 两类参数的正确写法**方向相反**，别按一个套路推另一个
        #    （2026-08-12 浏览器实测踩到：PUT 恒 500，而 112 例守卫全绿）：
        #
        #    - **UUID**：`CAST(:x AS uuid)` + 传 `str(uuid)`。不 CAST 则 asyncpg 按 VARCHAR
        #      编码 → `operator does not exist: uuid = character varying`。
        #    - **timestamptz**：`CAST(:ts AS timestamptz)` + 传 **datetime 对象**。
        #      一旦写了 CAST，asyncpg 就把该参数的推断类型定为 timestamptz，于是它要求
        #      Python `datetime`；此时传 `isoformat()` 字符串会 `DataError: expected a
        #      datetime.date or datetime.datetime instance, got 'str'`。
        #      ⇒ 「CAST 了就该传字符串」这个直觉对 UUID 成立、对时间戳恰好相反。
        #
        #    这类错误**只有真实 asyncpg 编码路径才暴露**：替身/sqlite 单测不做参数编码，
        #    源码级守卫只看到「CAST 写了、参数传了」⇒ 全绿。故本处配了一条连库写入守卫
        #    （`test_completeness_scope_override.py::TestRealDbWriteRoundTrip`），它真写真读真删。
        existing = (
            await self.db.execute(
                sa.text(
                    "SELECT id, conclusion FROM checklist_responses "
                    "WHERE wp_id = CAST(:wp AS uuid) AND item_id = :item"
                ),
                {"wp": str(b50_wp), "item": item_id},
            )
        ).first()

        if existing is None:
            await self.db.execute(
                sa.text(
                    "INSERT INTO checklist_responses "
                    "(project_id, wp_id, item_id, conclusion, remark, updated_by, "
                    " created_at, updated_at) "
                    "VALUES (CAST(:pid AS uuid), CAST(:wp AS uuid), :item, :conclusion, "
                    "        :remark, CAST(:actor AS uuid), "
                    "        CAST(:ts AS timestamptz), CAST(:ts AS timestamptz))"
                ),
                {
                    "pid": str(project_id),
                    "wp": str(b50_wp),
                    "item": item_id,
                    "conclusion": conclusion,
                    "remark": text_reason,
                    "actor": str(actor_user_id),
                    # datetime 对象，不是 isoformat() 字符串（见上方注释）
                    "ts": now,
                },
            )
            await self.db.flush()
            return {
                "cycle": normalized, "sensitive": sensitive,
                "created": True, "updated": False,
            }

        await self.db.execute(
            sa.text(
                "UPDATE checklist_responses SET conclusion = :conclusion, "
                "remark = :remark, updated_by = CAST(:actor AS uuid), "
                "updated_at = CAST(:ts AS timestamptz) "
                "WHERE id = CAST(:rid AS uuid)"
            ),
            {
                "conclusion": conclusion,
                "remark": text_reason,
                "actor": str(actor_user_id),
                # datetime 对象，不是 isoformat() 字符串（见上方注释）
                "ts": now,
                "rid": str(existing.id),
            },
        )
        await self.db.flush()
        return {
            "cycle": normalized, "sensitive": sensitive,
            "created": False, "updated": True,
        }

    async def clear_completeness_scope_override(
        self, project_id: UUID, *, cycle: str,
    ) -> dict:
        """撤销某循环的项目级覆盖 → 该循环退回平台默认清单。

        删行而不是写空串：读取侧（``trim_decision_context._load_completeness_override``）
        以「该循环是否出现在 dict 里」区分「已表态」与「未覆盖」，留一行空 conclusion
        会让两态都表现为「未覆盖」但多一条无意义记录，且下次读取端若放宽判据就会
        把它误读成表态。
        """
        normalized = str(cycle or "").strip().upper()
        if not normalized:
            raise HTTPException(status_code=400, detail="cycle 不能为空")
        b50_wp = await self._require_b50_wp_id(project_id)
        res = await self.db.execute(
            sa.text(
                "DELETE FROM checklist_responses "
                "WHERE wp_id = CAST(:wp AS uuid) AND item_id = :item"
            ),
            {"wp": str(b50_wp), "item": f"{_CSCOPE_ITEM_PREFIX}{normalized}"},
        )
        await self.db.flush()
        return {"cycle": normalized, "deleted": int(res.rowcount or 0)}

    async def list_completeness_scope_overrides(self, project_id: UUID) -> dict:
        """读回本项目的全部覆盖（含理由与留痕），供覆盖面板回显。

        与 ``trim_decision_context._load_completeness_override`` 的区别：那个只给
        决策内核用（仅需 ``{cycle: bool}``），这个要给 UI 展示理由与最后修改人。
        两者读同一批行、同一判据（``Y``/``N`` 之外视为未覆盖），故不构成双真源。
        """
        b50_wp = await self._find_b50_wp_id(project_id)
        if not b50_wp:
            return {"overrides": []}
        rows = (
            await self.db.execute(
                sa.text(
                    "SELECT cr.item_id, cr.conclusion, cr.remark, cr.updated_at, "
                    "       u.username AS updated_by_name "
                    "FROM checklist_responses cr "
                    "LEFT JOIN users u ON u.id = cr.updated_by "
                    "WHERE cr.wp_id = CAST(:wp AS uuid) AND cr.item_id LIKE :pattern "
                    "ORDER BY cr.item_id"
                ),
                {"wp": str(b50_wp), "pattern": f"{_CSCOPE_ITEM_PREFIX}%"},
            )
        ).fetchall()

        out: list[dict] = []
        for r in rows:
            cycle = (r.item_id or "").removeprefix(_CSCOPE_ITEM_PREFIX)
            if not cycle or cycle == (r.item_id or ""):
                continue
            val = (r.conclusion or "").strip().upper()
            if val not in ("Y", "N"):
                continue  # 与读取侧同判据：其它取值视为未覆盖
            out.append({
                "cycle": cycle,
                "sensitive": val == "Y",
                "reason": r.remark or "",
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "updated_by_name": r.updated_by_name,
            })
        return {"overrides": out}

    async def _find_b50_wp_id(self, project_id: UUID) -> UUID | None:
        """定位本项目 B50 底稿；复用 ``b50_risk_reader`` 的同一 JOIN，不另写一份。"""
        from app.services.b50_risk_reader import _find_b50_wp_id as _find

        return await _find(self.db, project_id)

    async def _require_b50_wp_id(self, project_id: UUID) -> UUID:
        """写入前定位 B50 底稿；未建则 409 并给出可操作的下一步。"""
        wp = await self._find_b50_wp_id(project_id)
        if not wp:
            raise HTTPException(
                status_code=409,
                detail=(
                    "本项目尚未创建 B50 风险评估底稿，无法保存完整性敏感清单覆盖。"
                    "请先在底稿列表中创建 B50 后重试。"
                ),
            )
        return wp

    # ======================================================================
    # 建议态驳回（Task 13：R6.4 驳回后不再重复建议）
    # ======================================================================

    async def reject_suggestions(
        self,
        project_id: UUID,
        *,
        cycle: str,
        wp_index_codes: list[str],
        actor_user_id: UUID,
        reason: str | None = None,
    ) -> dict:
        """把一批程序的裁剪建议标记为「已驳回」（不改适用性状态）。

        驳回是**纯标记**动作：程序仍保持 execute，只是决策内核下次不再对它出建议
        （`procedureTrimDecision` 档 2 的 `suggestionRejected` 判据）。故它**不走**
        canonical trim preview/apply —— 那条链路是改适用性状态的，用它来驳回会把
        「我不同意裁这个」变成「把这个裁掉」，语义正好相反。

        🔴 JSONB 写入必须**深拷贝构造新 dict 整体赋值**：未声明 `MutableDict` 的
        JSONB 列，就地改嵌套对象不标脏；而「就地改完再整体重赋值」同样不发 UPDATE ——
        因为 `body` 就是 ORM 持有的那个 dict、嵌套已被就地改过 ⇒ 新旧值 `==` 相等 ⇒
        工作单元判「无净变更」。判据必须是 DB 列真值，不是 ORM 对象。

        Returns: ``{"rejected": n, "unchanged": m, "not_found": [...]}``
        """
        codes = [str(c).strip() for c in (wp_index_codes or []) if str(c or "").strip()]
        if not codes:
            return {"rejected": 0, "unchanged": 0, "not_found": []}

        rows = (
            await self.db.execute(
                sa.select(ProcedureInstance).where(
                    ProcedureInstance.project_id == project_id,
                    ProcedureInstance.audit_cycle == str(cycle).strip(),
                    ProcedureInstance.wp_code.in_(codes),
                    ProcedureInstance.is_deleted == sa.false(),
                )
            )
        ).scalars().all()

        found = {inst.wp_code for inst in rows}
        rejected = 0
        unchanged = 0
        now = datetime.now(timezone.utc)
        for inst in rows:
            prev = inst.suggestion_state if isinstance(inst.suggestion_state, dict) else {}
            if prev.get("rejected") is True:
                unchanged += 1
                continue
            # 深拷贝构造新结构（见上方 JSONB 铁律）；保留既有 reason_code / evidence
            # 作为「被驳回的那条建议是什么」的留痕 —— 复核视图要能看出驳回了什么。
            inst.suggestion_state = {
                **{k: v for k, v in prev.items()},
                "rejected": True,
                "rejected_by": str(actor_user_id),
                "rejected_at": now.isoformat(),
                "rejected_reason": (str(reason).strip() or None) if reason else None,
            }
            rejected += 1

        await self.db.flush()
        return {
            "rejected": rejected,
            "unchanged": unchanged,
            "not_found": sorted(c for c in codes if c not in found),
        }

    # ======================================================================
    # 方案解析（纯读；供 preview 与 apply 复用）
    # ======================================================================

    @staticmethod
    def _normalize_entry(entry: dict) -> dict:
        """归一单条方案条目为 canonical 形式（含 canonical key）。"""
        kind = entry.get("kind")
        if kind == KIND_SCOPE:
            cycle = str(entry.get("cycle", "")).strip()
            wp_index_code = str(entry.get("wp_index_code", "")).strip()
            target_status = str(entry.get("target_status", "")).strip()
            if not cycle or not wp_index_code:
                raise HTTPException(status_code=422, detail="scope 条目缺 cycle/wp_index_code")
            if target_status not in _SCOPE_STATUSES:
                raise HTTPException(status_code=422, detail=f"非法 target_status: {target_status}")
            # 裁剪理由是审计轨迹的一部分（旧 PUT /procedures/{cycle}/trim 下线后由本条目承载）。
            # execute 恒为 None，保证 canonical payload 稳定（preview/apply hash 必须一致）。
            raw_reason = entry.get("skip_reason")
            skip_reason = str(raw_reason).strip() if raw_reason is not None else ""
            # 结构化理由码（Task 12，additive）。与 skip_reason 同口径处理：
            # execute 恒 None，保证 canonical payload 稳定（preview/apply hash 必须一致）。
            #
            # 🔴 必须参与本归一函数：preview 与 apply 各自把请求体过一遍 _canonical_entries
            # 后比对 payload hash 防篡改，若 reason_code 只在 apply 侧读取而不进 canonical
            # 形式，两侧 payload 不一致会直接 409。
            #
            # 🔴 未提供时**不写入该键**（不是写 None）—— 写 None 会改变 canonical payload
            # 的字节形态，让存量调用方的 preview/apply 与基线不一致（R8.9 零回归）。
            raw_code = entry.get("reason_code")
            reason_code = str(raw_code).strip() if raw_code is not None else ""
            normalized: dict = {
                "kind": KIND_SCOPE,
                "key": build_scope_key(cycle, wp_index_code),
                "cycle": cycle,
                "wp_index_code": wp_index_code,
                "target_status": target_status,
                "skip_reason": (
                    skip_reason or None
                ) if target_status in ("skip", "not_applicable") else None,
            }
            if reason_code and target_status in ("skip", "not_applicable"):
                if reason_code not in _VALID_TRIM_REASON_CODES:
                    raise HTTPException(
                        status_code=422,
                        detail=f"非法 reason_code: {reason_code}",
                    )
                normalized["reason_code"] = reason_code
            return normalized
        if kind == KIND_ROW:
            template_code = str(entry.get("template_code", "")).strip()
            sheet_key = str(entry.get("sheet_key", "")).strip()
            definition_key = str(entry.get("definition_key", "")).strip()
            target_applicability = str(entry.get("target_applicability", "")).strip()
            if not template_code or not sheet_key or not definition_key:
                raise HTTPException(
                    status_code=422, detail="row 条目缺 template_code/sheet_key/definition_key"
                )
            if target_applicability not in _ROW_APPLICABILITIES:
                raise HTTPException(
                    status_code=422, detail=f"非法 target_applicability: {target_applicability}"
                )
            return {
                "kind": KIND_ROW,
                "key": build_row_key(template_code, sheet_key, definition_key),
                "template_code": template_code,
                "sheet_key": sheet_key,
                "definition_key": definition_key,
                "target_applicability": target_applicability,
            }
        raise HTTPException(status_code=422, detail=f"非法方案条目 kind: {kind}")

    @classmethod
    def _canonical_entries(cls, entries: list[dict]) -> list[dict]:
        """归一 + 稳定排序（preview 与 apply 的 request payload 须一致，防篡改）。"""
        normalized = [cls._normalize_entry(e) for e in entries]
        normalized.sort(key=lambda x: canonical_json(x))
        return normalized

    async def _resolve_legacy_definition_key(
        self, template_code: str, legacy_key: str
    ) -> tuple[str | None, list[str]]:
        """legacy UUID/别名 → 唯一 definition_key。返回 (resolved_or_None, candidates)。

        在同底稿基码范围内查所有定义，Python 侧筛选 legacy_aliases 含该 key 的候选（避免 JSONB 操作符
        方言差异）。唯一 → 返回该 key；0 或 >1 → None（migration_conflict）。
        """
        base = _base_wp_code(template_code)
        rows = (
            (
                await self.db.execute(
                    sa.select(
                        ProcedureRowDefinition.definition_key,
                        ProcedureRowDefinition.legacy_aliases,
                    ).where(ProcedureRowDefinition.template_code.like(f"{base}%"))
                )
            )
            .all()
        )
        candidates = sorted(
            {
                r[0]
                for r in rows
                if _base_wp_code(_split_template(r[0])) == base
                and legacy_key in set(r[1] or [])
            }
        )
        if len(candidates) == 1:
            return candidates[0], candidates
        return None, candidates

    async def _resolve_row_tasks(
        self, project_id: UUID, sheet_key: str, definition_key: str
    ) -> list[ProcedureRowTask]:
        """项目内匹配 (sheet_key, definition_key) 的 active 任务（可跨 wp_index）。"""
        return (
            (
                await self.db.execute(
                    sa.select(ProcedureRowTask)
                    .where(
                        ProcedureRowTask.project_id == project_id,
                        ProcedureRowTask.sheet_key == sheet_key,
                        ProcedureRowTask.definition_key == definition_key,
                        ProcedureRowTask.is_deleted == sa.false(),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    async def _resolve_scope(
        self, project_id: UUID, cycle: str, wp_index_code: str
    ) -> tuple[list[ProcedureInstance], list[ProcedureRowTask]]:
        """粗裁范围：匹配的 ProcedureInstance + 该范围未终态可级联取消的 tasks。"""
        instances = (
            (
                await self.db.execute(
                    sa.select(ProcedureInstance)
                    .where(
                        ProcedureInstance.project_id == project_id,
                        ProcedureInstance.audit_cycle == cycle,
                        ProcedureInstance.wp_code == wp_index_code,
                        ProcedureInstance.is_deleted == sa.false(),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        tasks = (
            (
                await self.db.execute(
                    sa.select(ProcedureRowTask)
                    .where(
                        ProcedureRowTask.project_id == project_id,
                        ProcedureRowTask.wp_code == wp_index_code,
                        ProcedureRowTask.audit_cycle_snapshot == cycle,
                        ProcedureRowTask.is_deleted == sa.false(),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        return instances, tasks

    async def _build_plan(self, project_id: UUID, entries: list[dict]) -> dict:
        """把 canonical 条目解析为可应用计划（纯读）。

        返回：
          - ``row_target_versions``：{task_id: lock_version}（版本守卫用）
          - ``row_plans``：[(entry, tasks, target_applicability)]
          - ``scope_plans``：[(entry, instances, cascade_tasks, target_status)]
          - ``conflicts``：无法解析的条目 key 列表
          - ``migration_conflicts``：legacy 无法唯一转换明细
        """
        row_target_versions: dict[str, int] = {}
        row_plans: list[dict] = []
        scope_plans: list[dict] = []
        conflicts: list[dict] = []
        migration_conflicts: list[dict] = []

        for entry in entries:
            if entry["kind"] == KIND_ROW:
                definition_key = entry["definition_key"]
                resolved_key = definition_key
                if is_legacy_uuid_key(definition_key):
                    resolved_key, candidates = await self._resolve_legacy_definition_key(
                        entry["template_code"], definition_key
                    )
                    if resolved_key is None:
                        migration_conflicts.append(
                            {
                                "key": entry["key"],
                                "legacy_key": definition_key,
                                "reason": "legacy_uuid_unresolvable",
                                "candidates": candidates,
                            }
                        )
                        continue
                tasks = await self._resolve_row_tasks(
                    project_id, entry["sheet_key"], resolved_key
                )
                if not tasks:
                    conflicts.append({"key": entry["key"], "reason": "no_active_task"})
                    continue
                for t in tasks:
                    row_target_versions[str(t.id)] = t.lock_version
                row_plans.append(
                    {
                        "entry": entry,
                        "tasks": tasks,
                        "target_applicability": entry["target_applicability"],
                    }
                )
            else:  # scope
                instances, tasks = await self._resolve_scope(
                    project_id, entry["cycle"], entry["wp_index_code"]
                )
                if not instances and not tasks:
                    conflicts.append({"key": entry["key"], "reason": "no_scope_target"})
                    continue
                for t in tasks:
                    row_target_versions[str(t.id)] = t.lock_version
                scope_plans.append(
                    {
                        "entry": entry,
                        "instances": instances,
                        "cascade_tasks": tasks,
                        "target_status": entry["target_status"],
                    }
                )
        return {
            "row_target_versions": row_target_versions,
            "row_plans": row_plans,
            "scope_plans": scope_plans,
            "conflicts": conflicts,
            "migration_conflicts": migration_conflicts,
        }

    async def _membership_snapshot(self, project_id: UUID) -> list:
        """项目 active ProjectAssignment 快照（staff_id + role），稳定排序供 hash。"""
        rows = (
            await self.db.execute(
                sa.select(ProjectAssignment.staff_id, ProjectAssignment.role).where(
                    ProjectAssignment.project_id == project_id,
                    ProjectAssignment.is_deleted == sa.false(),
                )
            )
        ).all()
        return sorted([[str(r[0]), (r[1] or "").strip().lower()] for r in rows])

    @staticmethod
    def _write_suggestion_reason_code(inst, reason_code: str | None) -> None:
        """把结构化理由码写进 ``suggestion_state.reason_code``（就地修改，调用方负责 flush）。

        与 ``skip_reason`` **同一事务**写入（R8.8）：理由码与适用性状态必须一次落库，
        禁「先 apply 状态再补写理由码」的两次写入 —— 那会产生「状态已改、理由码未写」
        的中间态，且一次性 preview 凭证不覆盖第二次写入。

        🔴 不传 ``reason_code`` 时**完全不碰** ``suggestion_state``（连读都不读）：
        这是本扩展 additive 零回归的结构性保证 —— 存量调用方不传该字段，
        写入行为与扩展前逐字节相同。

        🔴 JSONB 列必须**深拷贝构造新 dict** 再整体赋值。就地改嵌套 dict 不标脏
        （未声明 ``MutableDict``），而「就地改完再整体重赋值」因新旧值 ``==`` 相等
        同样不发 UPDATE（平台已在 `ReportBodyAdapter` 上踩过一次）。

        `rejected` 等既有键原样保留：确认建议时只覆盖 `reason_code` 与 `evidence`，
        不得清掉驳回留痕。
        """
        if reason_code is None:
            return
        existing = inst.suggestion_state if isinstance(inst.suggestion_state, dict) else {}
        inst.suggestion_state = {**existing, "reason_code": reason_code}

    @staticmethod
    def _request_payload(canonical_entries: list[dict]) -> dict:
        """规范化 request payload（preview 与 apply 必须一致，防篡改）。"""
        return {"operation": TRIM_OPERATION, "entries": canonical_entries}

    @staticmethod
    def _scheme_revision(canonical_entries: list[dict]) -> str:
        """方案 revision 摘要（entries 内容寻址），供 preview/apply 比对。"""
        return sha256_hex(canonical_json(canonical_entries))

    # ======================================================================
    # 方案快照保存（revision + 文本快照）
    # ======================================================================

    async def _snapshot_entries(self, entries: list[dict]) -> list[dict]:
        """为每条 row 条目补充 definition revision 与程序文本快照（需求 3.6）。"""
        out: list[dict] = []
        for e in entries:
            item = dict(e)
            if e["kind"] == KIND_ROW:
                d = (
                    await self.db.execute(
                        sa.select(
                            ProcedureRowDefinition.template_revision_hash,
                            ProcedureRowDefinition.procedure_text,
                        ).where(
                            ProcedureRowDefinition.definition_key == e["definition_key"]
                        )
                    )
                ).first()
                item["revision"] = d[0] if d else None
                item["text_snapshot"] = d[1] if d else None
            out.append(item)
        return out

    async def save_scheme(
        self,
        project_id: UUID,
        *,
        scheme_name: str,
        audit_cycle: str,
        entries: list[dict],
        created_by: UUID | None = None,
    ) -> dict:
        """保存裁剪方案（canonical key + revision + 文本快照）。只 flush。"""
        canonical = self._canonical_entries(entries)
        snapshotted = await self._snapshot_entries(canonical)
        scheme = ProcedureTrimScheme(
            project_id=project_id,
            audit_cycle=audit_cycle,
            scheme_name=scheme_name,
            trim_data={
                "version": 2,
                "revision": self._scheme_revision(canonical),
                "entries": snapshotted,
            },
            created_by=created_by,
        )
        self.db.add(scheme)
        await self.db.flush()
        return {"scheme_id": str(scheme.id), "entries": snapshotted}

    async def _load_scheme_entries(self, project_id: UUID, scheme_id: UUID) -> list[dict]:
        scheme = (
            await self.db.execute(
                sa.select(ProcedureTrimScheme).where(
                    ProcedureTrimScheme.id == scheme_id,
                    ProcedureTrimScheme.project_id == project_id,
                    ProcedureTrimScheme.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()
        if scheme is None:
            raise HTTPException(status_code=404, detail="裁剪方案不存在")
        return list((scheme.trim_data or {}).get("entries") or [])

    # ======================================================================
    # 方案 preview / apply（一次性 ProcedureOperationPreview）
    # ======================================================================

    async def preview_scheme(
        self,
        project_id: UUID,
        *,
        actor_user_id: UUID,
        entries: list[dict] | None = None,
        scheme_id: UUID | None = None,
    ) -> dict:
        """方案预览：解析计划 + 创建一次性 preview（只 flush）。

        预览为纯读分析（不 apply）：返回目标数、预计 applied（would_change）/unchanged/conflict
        与 migration_conflict 明细；apply 时再以真实变化计数。
        """
        if entries is None and scheme_id is not None:
            entries = await self._load_scheme_entries(project_id, scheme_id)
        canonical = self._canonical_entries(entries or [])
        plan = await self._build_plan(project_id, canonical)

        would_change = 0
        unchanged = 0
        for rp in plan["row_plans"]:
            for t in rp["tasks"]:
                if t.applicability_status == rp["target_applicability"]:
                    unchanged += 1
                else:
                    would_change += 1
        for sp in plan["scope_plans"]:
            for inst in sp["instances"]:
                if scope_state_differs(
                    inst.status,
                    inst.skip_reason,
                    sp["target_status"],
                    sp["entry"].get("skip_reason"),
                ):
                    would_change += 1
                else:
                    unchanged += 1
            if sp["target_status"] in ("skip", "not_applicable"):
                for t in sp["cascade_tasks"]:
                    if t.workflow_status in TERMINAL_WORKFLOW_STATES:
                        continue
                    would_change += 1

        membership = await self._membership_snapshot(project_id)
        preview = await create_preview(
            self.db,
            actor_user_id=actor_user_id,
            project_id=project_id,
            operation=TRIM_OPERATION,
            request_payload=self._request_payload(canonical),
            target_versions=plan["row_target_versions"],
            membership_snapshot=membership,
            scheme_revision=self._scheme_revision(canonical),
        )
        return {
            "preview_id": str(preview.id),
            "expires_at": preview.expires_at.isoformat(),
            "summary": {
                "targets": len(plan["row_target_versions"]),
                "would_change": would_change,
                "unchanged": unchanged,
                "conflict": len(plan["conflicts"]),
                "migration_conflict": len(plan["migration_conflicts"]),
            },
            "conflicts": plan["conflicts"],
            "migration_conflicts": plan["migration_conflicts"],
        }

    async def apply_scheme(
        self,
        project_id: UUID,
        *,
        actor_user_id: UUID,
        preview_id: UUID,
        request_id: str,
        entries: list[dict] | None = None,
        scheme_id: UUID | None = None,
    ) -> dict:
        """方案应用：消费一次性 preview，经 TransitionService 真实应用（只 flush）。

        - legacy UUID key 无法唯一转换 → 409 migration_conflict（不猜测，需求 3.8）。
        - 目标 task lock_version 自 preview 后变化 → 409（版本冲突）。
        - applied == **真实** 发生变化的 task/scope 数；无变化 applied=0（Property P10）。
        - 相同 request_id 重试 → 幂等返回旧 result。
        """
        if entries is None and scheme_id is not None:
            entries = await self._load_scheme_entries(project_id, scheme_id)
        canonical = self._canonical_entries(entries or [])
        payload = self._request_payload(canonical)
        membership = await self._membership_snapshot(project_id)

        async def _apply_fn(db: AsyncSession, preview) -> dict:
            plan = await self._build_plan(project_id, canonical)

            # legacy UUID 无法唯一转换 → 409（不按顺序/文本猜测）
            if plan["migration_conflicts"]:
                raise TrimSchemeError(plan["migration_conflicts"])

            # 目标 task lock_version 自 preview 后变化 → 409
            current_versions = {
                k: v for k, v in plan["row_target_versions"].items()
            }
            if current_versions != dict(preview.target_versions or {}):
                raise HTTPException(status_code=409, detail="目标任务版本已变化，请重新预览")

            applied = 0
            unchanged = 0
            per_entry: list[dict] = []

            # 细裁行：execute / not_applicable
            for rp in plan["row_plans"]:
                target = rp["target_applicability"]
                entry_applied = 0
                entry_unchanged = 0
                for t in rp["tasks"]:
                    if t.applicability_status == target:
                        entry_unchanged += 1
                        continue
                    if target == APPLICABILITY_NOT_APPLICABLE:
                        changed = await self.transition.cancel(
                            t,
                            actor_user_id=actor_user_id,
                            reason="scheme_trim",
                            request_id=request_id,
                            set_applicability=APPLICABILITY_NOT_APPLICABLE,
                            event_type="scheme_not_applicable",
                        )
                    else:  # 恢复 execute → reopen（cancelled→unassigned；须重新 assign→ack）
                        changed = await self.transition.reopen(
                            t,
                            actor_user_id=actor_user_id,
                            request_id=request_id,
                            set_applicability=APPLICABILITY_EXECUTE,
                            reason="scheme_restore",
                            event_type="scheme_restore",
                        )
                    if changed:
                        entry_applied += 1
                    else:
                        entry_unchanged += 1
                applied += entry_applied
                unchanged += entry_unchanged
                per_entry.append(
                    {"key": rp["entry"]["key"], "applied": entry_applied, "unchanged": entry_unchanged}
                )

            # 粗裁范围：设置 scope 状态 + 级联取消未终态 tasks
            for sp in plan["scope_plans"]:
                target_status = sp["target_status"]
                entry_applied = 0
                entry_unchanged = 0
                # 结构化理由码（Task 12）：与 `skip_reason` **并列写在同一事务**。
                #
                # 🔴 禁「先 apply 状态再补写理由码」的两次写入 —— 那会产生「状态已改、
                #    理由码未写」的中间态，且一次性 preview 凭证不覆盖第二次写入，
                #    第二次请求既无凭证也无幂等键。
                # 🔴 未携带 `reason_code` 时**不触碰** `suggestion_state`（保持 NULL 或
                #    既有值），使存量调用方的写入行为逐字节不变（R8.9 additive 零回归）。
                entry_reason_code = sp["entry"].get("reason_code")
                for inst in sp["instances"]:
                    changed = await self.transition.set_scope_status(
                        inst,
                        status=target_status,
                        actor_user_id=actor_user_id,
                        # 用户填写的裁剪理由（审计轨迹），不写内部动作码
                        reason=sp["entry"].get("skip_reason"),
                    )
                    if entry_reason_code:
                        self._write_suggestion_reason_code(inst, entry_reason_code)
                    if changed:
                        entry_applied += 1
                    else:
                        entry_unchanged += 1
                if target_status in ("skip", "not_applicable"):
                    for t in sp["cascade_tasks"]:
                        if t.workflow_status in TERMINAL_WORKFLOW_STATES:
                            continue
                        changed = await self.transition.cancel(
                            t,
                            actor_user_id=actor_user_id,
                            reason="scheme_scope_cascade",
                            request_id=request_id,
                            set_applicability=APPLICABILITY_NOT_APPLICABLE,
                            event_type="scheme_scope_cascade",
                        )
                        if changed:
                            entry_applied += 1
                        else:
                            entry_unchanged += 1
                applied += entry_applied
                unchanged += entry_unchanged
                per_entry.append(
                    {"key": sp["entry"]["key"], "applied": entry_applied, "unchanged": entry_unchanged}
                )

            await db.flush()
            return {
                "applied": applied,
                "unchanged": unchanged,
                "conflict": len(plan["conflicts"]),
                "conflicts": plan["conflicts"],
                "per_entry": per_entry,
            }

        return await consume_and_apply(
            self.db,
            preview_id=preview_id,
            actor_user_id=actor_user_id,
            project_id=project_id,
            operation=TRIM_OPERATION,
            request_payload=payload,
            request_id=request_id,
            current_membership_snapshot=membership,
            apply_fn=_apply_fn,
        )


def _split_template(definition_key: str) -> str:
    """从内容寻址 definition_key（``{template}::{sheet}::{digest}``）取 template 段。"""
    return (definition_key or "").split("::", 1)[0]
