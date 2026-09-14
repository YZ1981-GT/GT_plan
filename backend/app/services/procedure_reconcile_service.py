"""模板 reconcile 与显式继承服务（Task 5）

Feature: procedure-delegation-notification
需求：1.6（模板升级显式继承）、3.1-3.2（reconcile 分类 + 不确定项零继承）、3.8（legacy UUID 冲突 409）、
      4.2-4.6（一次性 preview 安全模型）
Design：C3（ProcedureReconcileService）、D4（ProcedureOperationPreview 一次性凭证）
Properties：P8（reconcile 不确定项零继承）

职责：
- **分类（纯函数 ``classify``）**：按 ``definition_key → legacy_alias → 唯一规范化内容匹配`` 顺序，
  把项目现有任务（source，引用旧 definition）映射到目标 revision 的定义（target），输出
  matched / unmatched / ambiguous / orphaned / conflict。歧义/孤儿/冲突 **绝不** 进入 matched。
- **preview**：跑分类 + 创建一次性 ProcedureOperationPreview（operation='reconcile'），
  绑定 actor/project/规范 request hash/target lock_versions/membership 快照/目标 revision/TTL。
- **apply**：消费 preview（防篡改/越权/过期/成员变化 409）；仅对 matched 与 Delegator 显式
  resolution 的项迁移 task 的 definition 关联（definition_key / revision / 展示快照），**保留**
  assignee/reviewer/workflow/assignment_version/历史不变；ambiguous/orphaned/conflict **零继承**
  （P8）。目标 task lock_version 自 preview 后变化 → 409（版本冲突）。migrate 记 reconcile
  history 并保留旧 definition 快照供审计。legacy UUID key 无法唯一转换 → conflict（不猜测，3.8）。

约定：service 只 flush 不 commit；router 显式 commit。分类为纯逻辑（无 DB），便于 PBT。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import (
    ProcedureRowDefinition,
    ProcedureRowTask,
    ProcedureRowTaskHistory,
)
from app.models.staff_models import ProjectAssignment
from app.services.procedure_definition_importer import canonical_json, sha256_hex
from app.services.procedure_operation_preview import (
    consume_and_apply,
    create_preview,
)
from app.services.procedure_task_materialization_service import _base_wp_code

logger = logging.getLogger(__name__)

RECONCILE_OPERATION = "reconcile"

# 匹配方法
METHOD_EXACT_KEY = "exact_key"
METHOD_LEGACY_ALIAS = "legacy_alias"
METHOD_NORMALIZED_CONTENT = "normalized_content"


# ---------------------------------------------------------------------------
# 纯分类逻辑（无 DB，可直接 PBT）
# ---------------------------------------------------------------------------


@dataclass
class ReconcileDefn:
    """分类输入的定义描述（source 或 target 通用）。"""

    definition_key: str
    normalized_content: dict = field(default_factory=dict)
    legacy_aliases: list = field(default_factory=list)
    program_no: str | None = None
    sheet_key: str = ""
    # source 专用：对应任务身份/版本
    task_id: str | None = None
    lock_version: int | None = None


def _content_hash(normalized_content: dict | None) -> str:
    return sha256_hex(canonical_json(normalized_content or {}))


def is_legacy_uuid_key(key: str | None) -> bool:
    """判断是否为“legacy UUID / 数组序号”类 key（非内容寻址）。

    内容寻址 definition_key 形如 ``{template}::{sheet}::{digest}``，必含 ``::``。
    不含 ``::`` 的（裸 UUID / row-N / index-N / 旧历史 key）视为 legacy，需唯一转换（3.8）。
    """
    return "::" not in (key or "")


def classify(
    sources: list[ReconcileDefn], targets: list[ReconcileDefn]
) -> dict:
    """把 source 定义（现有任务引用）映射到 target 定义（目标 revision）。

    匹配顺序（每个 source 独立）：exact_key → legacy_alias（唯一）→ normalized_content（唯一）。
    - alias 与 content 各自唯一但指向不同 target → conflict（矛盾，不猜测）。
    - alias 或 content 有多个候选 → ambiguous。
    - 无任何候选：legacy UUID key → conflict（3.8）；内容寻址 key → orphaned（模板删行）。

    返回 dict：matched / ambiguous / orphaned / conflict / unmatched（详见各条 source_key/candidates）。
    保证：ambiguous/orphaned/conflict 的 source_key **绝不** 出现在 matched（P8 分类不变量）。
    """
    target_by_key: dict[str, ReconcileDefn] = {t.definition_key: t for t in targets}
    content_index: dict[str, set[str]] = {}
    alias_index: dict[str, set[str]] = {}
    for t in targets:
        content_index.setdefault(_content_hash(t.normalized_content), set()).add(
            t.definition_key
        )
        for tok in set(t.legacy_aliases or []) | {t.definition_key}:
            alias_index.setdefault(tok, set()).add(t.definition_key)

    matched: list[dict] = []
    ambiguous: list[dict] = []
    orphaned: list[dict] = []
    conflict: list[dict] = []
    consumed_targets: set[str] = set()

    for s in sources:
        skey = s.definition_key
        base = {"source_id": s.task_id, "source_key": skey}

        # 1) exact key
        if skey in target_by_key:
            matched.append({**base, "target_key": skey, "method": METHOD_EXACT_KEY})
            consumed_targets.add(skey)
            continue

        source_tokens = set(s.legacy_aliases or []) | {skey}
        alias_targets: set[str] = set()
        for tok in source_tokens:
            alias_targets |= alias_index.get(tok, set())
        content_targets: set[str] = set(content_index.get(_content_hash(s.normalized_content), set()))
        is_legacy = is_legacy_uuid_key(skey)

        # 矛盾：alias 唯一指向 A，content 唯一指向不同 B
        if (
            len(alias_targets) == 1
            and len(content_targets) == 1
            and alias_targets != content_targets
        ):
            conflict.append(
                {
                    **base,
                    "reason": "alias_content_contradiction",
                    "candidates": sorted(alias_targets | content_targets),
                }
            )
            continue

        # 2) legacy alias 唯一
        if len(alias_targets) == 1:
            tk = next(iter(alias_targets))
            matched.append({**base, "target_key": tk, "method": METHOD_LEGACY_ALIAS})
            consumed_targets.add(tk)
            continue
        if len(alias_targets) > 1:
            ambiguous.append({**base, "candidates": sorted(alias_targets)})
            continue

        # 3) 唯一规范化内容
        if len(content_targets) == 1:
            tk = next(iter(content_targets))
            matched.append({**base, "target_key": tk, "method": METHOD_NORMALIZED_CONTENT})
            consumed_targets.add(tk)
            continue
        if len(content_targets) > 1:
            ambiguous.append({**base, "candidates": sorted(content_targets)})
            continue

        # 无候选
        if is_legacy:
            conflict.append({**base, "reason": "legacy_uuid_unresolvable", "candidates": []})
        else:
            orphaned.append(base)

    unmatched = [
        {"target_key": t.definition_key}
        for t in targets
        if t.definition_key not in consumed_targets
    ]
    return {
        "matched": matched,
        "ambiguous": ambiguous,
        "orphaned": orphaned,
        "conflict": conflict,
        "unmatched": unmatched,
    }


# ---------------------------------------------------------------------------
# reconcile 服务（DB）
# ---------------------------------------------------------------------------


class ProcedureReconcileService:
    """模板 reconcile：分类 + 一次性 preview/apply 显式继承。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -- 加载 ----------------------------------------------------------------

    async def _load_project_tasks(
        self, project_id: UUID, template_code: str, wp_index_ids: list[UUID] | None
    ) -> list[ProcedureRowTask]:
        """本项目、匹配模板底稿基码的 active 任务。"""
        conds = [
            ProcedureRowTask.project_id == project_id,
            ProcedureRowTask.wp_code == template_code,
            ProcedureRowTask.is_deleted == sa.false(),
        ]
        if wp_index_ids:
            conds.append(ProcedureRowTask.wp_index_id.in_(wp_index_ids))
        return (
            (await self.db.execute(sa.select(ProcedureRowTask).where(*conds)))
            .scalars()
            .all()
        )

    async def _load_target_definitions(
        self, template_code: str, target_revision: str
    ) -> list[ProcedureRowDefinition]:
        """目标 revision 的定义（按底稿基码 + revision 精确过滤）。"""
        rows = (
            (
                await self.db.execute(
                    sa.select(ProcedureRowDefinition).where(
                        ProcedureRowDefinition.template_code.like(f"{template_code}%"),
                        ProcedureRowDefinition.template_revision_hash == target_revision,
                    )
                )
            )
            .scalars()
            .all()
        )
        return [d for d in rows if _base_wp_code(d.template_code) == template_code]

    async def _load_source_definitions(
        self, keys: list[str]
    ) -> dict[str, ProcedureRowDefinition]:
        """按 definition_key 加载现有任务引用的旧定义（导入器保留旧 revision）。"""
        if not keys:
            return {}
        rows = (
            (
                await self.db.execute(
                    sa.select(ProcedureRowDefinition).where(
                        ProcedureRowDefinition.definition_key.in_(keys)
                    )
                )
            )
            .scalars()
            .all()
        )
        return {d.definition_key: d for d in rows}

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

    # -- 构造分类输入 --------------------------------------------------------

    async def _build_classification(
        self,
        project_id: UUID,
        template_code: str,
        target_revision: str,
        wp_index_ids: list[UUID] | None,
    ) -> tuple[dict, list[ProcedureRowTask]]:
        """加载 source 任务 + target 定义并跑纯分类；返回 (classification, tasks)。"""
        tasks = await self._load_project_tasks(project_id, template_code, wp_index_ids)
        src_defs = await self._load_source_definitions(
            list({t.definition_key for t in tasks})
        )
        targets_orm = await self._load_target_definitions(template_code, target_revision)

        sources: list[ReconcileDefn] = []
        for t in tasks:
            d = src_defs.get(t.definition_key)
            sources.append(
                ReconcileDefn(
                    definition_key=t.definition_key,
                    normalized_content=(d.normalized_content if d else {}) or {},
                    legacy_aliases=(d.legacy_aliases if d else []) or [],
                    program_no=t.program_no,
                    sheet_key=t.sheet_key,
                    task_id=str(t.id),
                    lock_version=t.lock_version,
                )
            )
        targets = [
            ReconcileDefn(
                definition_key=d.definition_key,
                normalized_content=d.normalized_content or {},
                legacy_aliases=d.legacy_aliases or [],
                program_no=d.program_no,
                sheet_key=d.sheet_key,
            )
            for d in targets_orm
        ]
        return classify(sources, targets), tasks

    @staticmethod
    def _summary(classification: dict) -> dict:
        return {k: len(v) for k, v in classification.items()}

    @staticmethod
    def _request_payload(
        template_code: str,
        target_revision: str,
        wp_index_ids: list[UUID] | None,
        resolutions: list[dict] | None,
    ) -> dict:
        """规范化 request payload（preview 与 apply 必须一致，防篡改）。"""
        return {
            "operation": RECONCILE_OPERATION,
            "template_code": template_code,
            "target_revision": target_revision,
            "wp_index_ids": sorted(str(i) for i in (wp_index_ids or [])),
            "resolutions": sorted(
                (
                    canonical_json(
                        {
                            "source_key": r.get("source_key"),
                            "target_key": r.get("target_key"),
                        }
                    )
                    for r in (resolutions or [])
                )
            ),
        }

    # -- preview -------------------------------------------------------------

    async def preview(
        self,
        project_id: UUID,
        *,
        actor_user_id: UUID,
        template_code: str,
        target_revision: str,
        wp_index_ids: list[UUID] | None = None,
        resolutions: list[dict] | None = None,
    ) -> dict:
        """跑分类并创建一次性 preview（只 flush）。返回 preview_id + 分类明细 + 汇总。"""
        classification, tasks = await self._build_classification(
            project_id, template_code, target_revision, wp_index_ids
        )
        target_versions = {str(t.id): t.lock_version for t in tasks}
        membership = await self._membership_snapshot(project_id)
        payload = self._request_payload(
            template_code, target_revision, wp_index_ids, resolutions
        )
        preview = await create_preview(
            self.db,
            actor_user_id=actor_user_id,
            project_id=project_id,
            operation=RECONCILE_OPERATION,
            request_payload=payload,
            target_versions=target_versions,
            membership_snapshot=membership,
            scheme_revision=target_revision,
        )
        return {
            "preview_id": str(preview.id),
            "expires_at": preview.expires_at.isoformat(),
            "target_revision": target_revision,
            "summary": self._summary(classification),
            "classification": classification,
        }

    # -- apply ---------------------------------------------------------------

    async def apply(
        self,
        project_id: UUID,
        *,
        actor_user_id: UUID,
        preview_id: UUID,
        request_id: str,
        template_code: str,
        target_revision: str,
        wp_index_ids: list[UUID] | None = None,
        resolutions: list[dict] | None = None,
    ) -> dict:
        """消费 preview 并显式迁移 matched + resolved 的 task 关联（只 flush）。

        ambiguous/orphaned/conflict 无 Delegator 显式 resolution 时零继承（P8）。
        目标 task lock_version 自 preview 后变化 → 409。相同 request_id 重试幂等返回旧 result。
        """
        payload = self._request_payload(
            template_code, target_revision, wp_index_ids, resolutions
        )
        membership = await self._membership_snapshot(project_id)

        async def _apply_fn(db: AsyncSession, preview) -> dict:
            # 复核：重跑分类（也会锁定当前 task 版本），版本自 preview 后变化 → 409
            classification, tasks = await self._build_classification(
                project_id, template_code, target_revision, wp_index_ids
            )
            current_versions = {str(t.id): t.lock_version for t in tasks}
            if current_versions != dict(preview.target_versions or {}):
                raise HTTPException(
                    status_code=409, detail="目标任务版本已变化，请重新预览"
                )

            tasks_by_id = {str(t.id): t for t in tasks}
            # target 定义查表（迁移时刷新快照）
            targets_orm = await self._load_target_definitions(template_code, target_revision)
            target_by_key = {d.definition_key: d for d in targets_orm}

            # 显式 resolution 映射：source_key → target_key（仅用于 ambiguous/orphaned/conflict）
            resolution_map: dict[str, str] = {}
            for r in resolutions or []:
                sk = r.get("source_key")
                tk = r.get("target_key")
                if sk and tk:
                    resolution_map[str(sk)] = str(tk)

            applied = 0
            unchanged = 0
            skipped: list[dict] = []

            # matched：迁移（含 exact_key 的 revision 刷新）
            migrations: list[tuple[ProcedureRowTask, str]] = []
            for m in classification["matched"]:
                task = tasks_by_id.get(str(m["source_id"]))
                if task is not None:
                    migrations.append((task, m["target_key"]))

            # 显式 resolution：仅对不确定项（ambiguous/orphaned/conflict）迁移到 Delegator 选定 target
            uncertain = (
                classification["ambiguous"]
                + classification["orphaned"]
                + classification["conflict"]
            )
            for item in uncertain:
                sk = item.get("source_key")
                tk = resolution_map.get(str(sk))
                task = tasks_by_id.get(str(item.get("source_id")))
                if tk and task is not None and tk in target_by_key:
                    migrations.append((task, tk))

            for task, target_key in migrations:
                target_def = target_by_key.get(target_key)
                if target_def is None:
                    skipped.append({"task_id": str(task.id), "reason": "target_missing"})
                    continue
                # 目标锚点 (project, wp_index, sheet, definition) 已被别的 active task 占用 → 冲突跳过
                if target_key != task.definition_key or target_def.sheet_key != task.sheet_key:
                    exists = (
                        await db.execute(
                            sa.select(ProcedureRowTask.id).where(
                                ProcedureRowTask.project_id == project_id,
                                ProcedureRowTask.wp_index_id == task.wp_index_id,
                                ProcedureRowTask.sheet_key == target_def.sheet_key,
                                ProcedureRowTask.definition_key == target_key,
                                ProcedureRowTask.is_deleted == sa.false(),
                                ProcedureRowTask.id != task.id,
                            )
                        )
                    ).first()
                    if exists is not None:
                        skipped.append(
                            {"task_id": str(task.id), "reason": "active_conflict"}
                        )
                        continue

                changed = (
                    task.definition_key != target_key
                    or task.definition_revision_hash != target_revision
                    or task.sheet_key != target_def.sheet_key
                )
                if not changed:
                    unchanged += 1
                    continue

                old_key = task.definition_key
                old_revision = task.definition_revision_hash
                # 只迁移 definition 关联与展示快照；assignee/reviewer/workflow/assignment_version 不变
                task.definition_key = target_key
                task.definition_revision_hash = target_revision
                task.sheet_key = target_def.sheet_key
                task.program_no = target_def.program_no
                task.procedure_text = target_def.procedure_text
                task.ref_snapshot = list(target_def.ref_snapshot or [])
                task.lock_version = (task.lock_version or 0) + 1
                task.updated_at = sa.func.now()
                # reconcile history：保留旧 definition 快照供审计
                db.add(
                    ProcedureRowTaskHistory(
                        task_id=task.id,
                        project_id=project_id,
                        event_type="reconcile_migrate",
                        actor_user_id=actor_user_id,
                        request_id=request_id,
                        assignment_version=task.assignment_version,
                        lock_version=task.lock_version,
                        definition_revision_hash=target_revision,
                        audit_cycle_snapshot=task.audit_cycle_snapshot,
                        detail={
                            "old_definition_key": old_key,
                            "old_revision_hash": old_revision,
                            "new_definition_key": target_key,
                            "target_revision": target_revision,
                        },
                    )
                )
                applied += 1

            await db.flush()
            return {
                "applied": applied,
                "unchanged": unchanged,
                "skipped": skipped,
                "summary": self._summary(classification),
                "target_revision": target_revision,
            }

        return await consume_and_apply(
            self.db,
            preview_id=preview_id,
            actor_user_id=actor_user_id,
            project_id=project_id,
            operation=RECONCILE_OPERATION,
            request_payload=payload,
            request_id=request_id,
            current_membership_snapshot=membership,
            apply_fn=_apply_fn,
        )
