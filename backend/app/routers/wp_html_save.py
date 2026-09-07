"""底稿 HTML 数据保存端点

POST /api/workpapers/{wp_id}/save
按 design §5.1.2 实现：保存 HTML 数据到 parsed_data['html_data']。

Requirements: 2.2 原则 4（决策可追踪）+ 3.11.4（跨底稿引用传播）

═══ Task 18：`_version` / `file_version` 跨域被拆掉，统一到 `content_revision` ═══

spec `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 18；
Requirements 2.1 / 2.2 / 2.12 / 3.1 / 13.4；Property 4 / 54 / 61。

改造前这个端点上有**三个**互不相干的计数器在装同一件事：

1. `parsed_data['_version']` —— 本端点自己 +1，并作为乐观锁比对目标；
2. `working_paper.file_version` —— 由共享的 `orchestrator.after_save` +1；
3. `working_paper.updated_at` / 文件 mtime —— 被 doc_key 与若干下游当版本用。

于是 Task 16 之前的形态是：把 (1) 的值当 `expected_version` 传给按 (2) 比较的
`after_save`，冲突被 `except Exception → logger.warning` 吞掉，四项副作用全部静默
跳过。Task 16 拆了那个 except 与跨域参数；Task 18 给出**替代所有者**：

* 业务内容版本唯一域 = `working_paper.content_revision`，唯一推进者 =
  `ContentMutationService`（Task 15）的单次业务事务。本端点走它的 `single_html`
  lane：`stage_html_projection()`（文件侧）→ `commit_html_projection()`（一次 DB
  事务 + 唯一一次 commit）。
* 真乐观锁 = 那条 lane 里的 `UPDATE ... WHERE content_revision = :expected`（CAS，
  命中 0 行即冲突），不再是「内存里的对象自己跟自己比」。
* `parsed_data['_version']` **不再写、不再读**。它是第二个真源，Requirement 2.1
  明确禁止它「推进或充当跨通道同步版本」。
* `data_version` 请求/响应字段仍在（对外契约不变），但它现在装的是
  `content_revision`。前端未使用该字段（只发 `sheet_name/html_data/schema_version`）。

本端点**不**处理 bidirectional entry：那条路径的 HTML flush 只能形成 pending
mutation，由 Task 25 的 coordinator 调 `ContentMutationService.commit(...)` 在一次
业务事务里同时发布 projection 与兼容 representation。`HtmlOnlyCommitPlan` 对
`capability=bidirectional` 直接抛，`commit_html_projection` 另按数据库事实（该 wp
是否已有 representation pointer）二次拒绝。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user, require_operation
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.cross_ref_service import cross_ref_service
from app.services.project_audit_year import fetch_project_audit_year
from app.services.workpaper_sync.content_mutation import (
    HtmlOnlyCommitPlan,
    HtmlOnlyEntryHasRepresentationError,
    build_html_content_mutation_service,
    html_only_entry_id,
)
from app.services.workpaper_sync.entry_profile import Capability
from app.services.workpaper_sync.models import RevisionConflictError
from app.services.workpaper_sync.outbox import DurableEventOutboxService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["wp-html-save"],
)


# ─── Request / Response schemas ──────────────────────────────────────────────


class SaveHtmlDataRequest(BaseModel):
    """保存 HTML 数据请求体"""
    sheet_name: str = Field(..., description="Sheet 名称")
    html_data: dict = Field(..., description="HTML 渲染数据")
    schema_version: str = Field(..., description="Schema 版本号（如 v2025-R5）")
    changed_cells: list[str] | None = Field(
        None, description="变更的 cell 列表（可选，用于优化跨底稿引用检测）"
    )
    data_version: int | None = Field(
        None,
        description=(
            "乐观锁版本号 = `working_paper.content_revision`（business content revision）。"
            "提交时与服务端比对，不一致返回 409。"
            "🔴 Task 18 起不再是 `parsed_data._version`：那是第二个计数器，"
            "与 `file_version` 跨域比较造出假冲突（Requirement 2.1）"
        ),
    )
    force_overwrite: bool = Field(
        False, description="强制覆盖（忽略版本冲突）"
    )


class StaleImpactItem(BaseModel):
    """受影响的跨底稿引用"""
    ref_id: str
    target_wp_code: str
    target_sheet: str | None = None
    target_cell: str | None = None


class SaveHtmlDataResponse(BaseModel):
    """保存成功响应"""
    saved_at: str
    data_version: int = Field(
        0,
        description=(
            "保存后的新 `content_revision`（唯一 business content revision 域）"
        ),
    )
    content_version_id: str | None = Field(
        None,
        description="本次业务内容的 immutable content version id（opaque 路由键）",
    )
    stale_impact: list[StaleImpactItem] = []


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.post("/{wp_id}/save")
async def save_html_data(
    wp_id: UUID,
    body: SaveHtmlDataRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operation("wp:edit")),
) -> SaveHtmlDataResponse:
    """保存 HTML 数据到 parsed_data['html_data'][sheet_name]。

    EARS:
    - WHEN 保存成功 AND 存在 cross_wp_references 引用此 cell
      THEN 系统 SHALL 发布 SSE cross_ref.updated
    - WHEN schema_version 与服务端 current 不一致 THEN 返回 409
    - IF html_data 校验失败 THEN 返回 422 + 字段级错误
    """
    # ─── Step 1: 查 working_paper ─────────────────────────────────────────
    wp_query = sa.select(WorkingPaper).where(
        WorkingPaper.id == wp_id,
        WorkingPaper.is_deleted == False,  # noqa: E712
    )
    wp_result = await db.execute(wp_query)
    working_paper = wp_result.scalars().first()

    if working_paper is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # ─── Step 2: schema_version 冲突检测 ──────────────────────────────────
    parsed_data = working_paper.parsed_data or {}
    current_schema_version = parsed_data.get("schema_version")

    # 如果服务端已有 schema_version 且与请求不一致，返回 409
    if (
        current_schema_version is not None
        and current_schema_version != body.schema_version
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "schema_version_conflict",
                "message": (
                    f"Schema 版本冲突：服务端当前版本为 {current_schema_version}，"
                    f"请求版本为 {body.schema_version}。请刷新后重试。"
                ),
                "server_version": current_schema_version,
                "client_version": body.schema_version,
            },
        )

    # ─── Step 2b: 乐观锁版本校验（Requirement 2.1 / 6.3）────────────────────
    #
    # 比对目标是 `working_paper.content_revision` —— **唯一** business content revision
    # 域。改造前这里读 `parsed_data['_version']`，那是第二个计数器：它与
    # `working_paper.file_version` 各自递增，谁都不是权威，跨域比较必然造假冲突。
    #
    # 这一处只是「早失败 + 给用户可读信息」；**真正的**并发裁决是
    # `commit_html_projection()` 事务内的 CAS（`UPDATE ... WHERE content_revision =
    # :expected`）。两者缺一不可：只有前者拦不住真并发，只有后者则用户拿不到
    # last_modified_by/at。
    server_version: int = int(getattr(working_paper, "content_revision", 0) or 0)
    if (
        body.data_version is not None
        and not body.force_overwrite
        and body.data_version != server_version
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "data_version_conflict",
                "message": (
                    f"数据版本冲突：您的版本为 {body.data_version}，"
                    f"服务端当前版本为 {server_version}。"
                    "其他用户可能已修改此 sheet，请选择覆盖或合并。"
                ),
                "server_version": server_version,
                "client_version": body.data_version,
                "last_modified_by": parsed_data.get("last_modified_by"),
                "last_modified_at": parsed_data.get("last_modified_at"),
            },
        )

    # ─── Step 3: JSON Schema 基础校验 ─────────────────────────────────────
    # 校验 html_data 必须是 dict 且 sheet_name 非空
    if not isinstance(body.html_data, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": "html_data 必须是 JSON 对象",
                "field": "html_data",
            },
        )

    if not body.sheet_name.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": "sheet_name 不能为空",
                "field": "sheet_name",
            },
        )

    # ─── Step 4: 获取 wp_code（用于跨底稿引用检测）────────────────────────
    wp_code = await cross_ref_service.get_wp_code_for_wp_id(wp_id, db)

    # ─── Step 5: 保存前获取旧数据（用于变更检测）──────────────────────────
    html_data_all = parsed_data.get("html_data", {})
    old_sheet_data = html_data_all.get(body.sheet_name)

    # ─── Step 6: Merge html_data 到 parsed_data['html_data'][sheet_name] ──
    if "html_data" not in parsed_data:
        parsed_data["html_data"] = {}

    parsed_data["html_data"][body.sheet_name] = body.html_data

    # 更新元数据
    now = datetime.now(timezone.utc)
    parsed_data["schema_version"] = body.schema_version
    parsed_data["last_modified_by"] = str(current_user.id)
    parsed_data["last_modified_at"] = now.isoformat()

    # 🔴 `parsed_data['_version']` 不再写（Requirement 2.1：它不得推进也不得充当跨通道
    #    同步版本）。本次业务版本由 `content_revision` 的 CAS 推进，见 Step 7c。
    #    存量 parsed_data 里遗留的 `_version` 键**保持原值不动**：它是历史数据，不是
    #    权威，也没有任何生产读取方（守卫
    #    `test_task18_html_save_unified_revision.py::test_html_save_never_writes_the_parsed_data_version`
    #    锁死"不再写"这半边）。

    # 记录变更的 sheets
    changed_sheets = parsed_data.get("changed_sheets_last_save", [])
    if body.sheet_name not in changed_sheets:
        changed_sheets.append(body.sheet_name)
    parsed_data["changed_sheets_last_save"] = changed_sheets

    # ─── Step 6b: staged artifact（文件先耐久，数据库还没动）───────────────
    # Requirement 2.4 的 staged artifact 协议：artifact 先流式落盘、校验 digest、
    # 内容寻址 publish；**随后**才开那个短数据库事务写 pointer。这里失败时数据库一行
    # 没动；这里成功而事务失败时，文件是不可见 orphan（由 Task 11 的 reconciliation
    # 收），绝不形成「pointer 指向缺失 artifact」的半成功态。
    #
    # `capability=single_html` 是**显式声明**：本端点只服务无 OO representation 的
    # 入口。bidirectional entry 的 HTML flush 必须走 pending mutation +
    # `ContentMutationService.commit(...)`（Task 25），否则就是 design 明确拒绝的
    # 「projection-only commit 后再补 artifact」。`commit_html_projection` 另按数据库
    # 事实（该 wp 是否已有 entry representation pointer）二次拒绝 —— 声明可以写错，
    # 数据库事实不会。
    entry_id = html_only_entry_id(wp_code=wp_code, wp_id=wp_id)
    mutation_service = build_html_content_mutation_service(db)
    commit_plan = HtmlOnlyCommitPlan(
        project_id=working_paper.project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        expected_revision=server_version,
        capability=Capability.single_html,
        sheet_name=body.sheet_name,
        schema_version=body.schema_version,
        actor_id=current_user.id,
        parent_version_id=getattr(working_paper, "current_content_version_id", None),
        trigger="html_save",
    )
    staged_projection = mutation_service.stage_html_projection(
        plan=commit_plan, html_data=body.html_data
    )

    # ─── Step 7: 写入数据库 ───────────────────────────────────────────────
    await db.execute(
        sa.update(WorkingPaper)
        .where(WorkingPaper.id == wp_id)
        .values(
            parsed_data=parsed_data,
            updated_by=current_user.id,
        )
    )

    # ─── Step 7b: 统一后处理（orchestrator）────────────────────────────────
    # prefill_stale, updated_at, audit log, 耐久 outbox 入队（不发布）
    #
    # Task 16 / Requirement 13.4：这里原来是 `try: ... except Exception: logger.warning`。
    # 那个 except 掩盖了一个真实缺陷：`expected_version` 传的是 `body.data_version`
    # （= parsed_data['_version'] 域），而 after_save 拿它和 `wp.file_version` 比 ——
    # 两个独立计数器。第二次带 data_version 的保存起就必然 OptimisticLockError，被吞成
    # warning 后 file_version / prefill_stale / 审计日志 / WORKPAPER_SAVED 事件**四项
    # 全部静默跳过**，下游 cross_ref / stale / SSE 完全不触发。
    #
    # Task 16 / Requirement 2.12：`after_save` 现在**一个版本字段都不写**，只做可重放的
    # 副作用（prefill_stale / updated_at / 审计日志 / 耐久 outbox 行）。它拿到的
    # `content_revision` 是**只读**的 —— 本次业务提交预定推进到的值，写进审计日志与耐久
    # payload 供下游按正确版本刷新。handler 重放不可能递增 revision，因为它根本不碰
    # 版本列。
    #
    # 顺序即语义：`after_save` 只 flush 不 commit，随后 Step 7c 的
    # `commit_html_projection()` 是这笔事务的**唯一**提交出口，因此
    # 「HTML 内容 + 审计日志 + 耐久事件 + content version + content_revision」同生共死
    # （Requirement 13.1）。这里不包 try/except：耐久事件写不进去必须让整笔保存失败，
    # 不得 best-effort warning 后永久丢失（Requirement 13.4）。
    from app.services.workpaper_save_orchestrator import orchestrator as save_orchestrator

    await save_orchestrator.after_save(
        db, working_paper, current_user,
        trigger="html_save",
        extra={
            "sheet_name": body.sheet_name,
            "schema_version": body.schema_version,
            "entry_id": entry_id,
        },
        content_revision=commit_plan.target_revision,
    )

    # ─── Step 7c: 唯一业务 commit（Requirement 2.2 / 3.1 / Property 4 / 61）──────
    # `commit_html_projection()` 在**一个** DB 事务里做：content_revision CAS →
    # immutable content version → wp 级 current pointer → outbox，然后**恰一次** commit。
    # 本端点自己没有 `db.commit()` —— 那才是「所有 writer 进入唯一 revision 域」的落地
    # 形态（绕过统一入口自行 commit 会被 Task 3 的 writer gate 打红）。
    try:
        receipt = await mutation_service.commit_html_projection(
            plan=commit_plan, staged=staged_projection
        )
    except RevisionConflictError as exc:
        # 真并发：CAS 命中 0 行。Step 2b 那道早检查看到的是请求开始时的快照，拦不住
        # 「两个请求同时通过早检查」，所以这里必须把 409 补上，而不是 500。
        raise HTTPException(
            status_code=409,
            detail={
                "error": "data_version_conflict",
                "message": (
                    "数据版本冲突：其他用户在本次保存期间修改了该底稿，请刷新后重试。"
                ),
                "server_version": server_version,
                "client_version": body.data_version,
            },
        ) from exc
    except HtmlOnlyEntryHasRepresentationError as exc:
        # 该底稿已绑定 OO representation（bidirectional entry），不能走 single_html lane。
        # 前端应走 d2-sync / wp_sync_router 的双向保存路径，而非本端点。
        # 返回 409 而非 500：这是业务状态冲突（能力不匹配），不是服务器故障。
        logger.info(
            "wp %s is bidirectional, rejecting html-only save: %s", wp_id, exc
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "bidirectional_entry_requires_sync_path",
                "message": (
                    "该底稿已绑定在线编辑（Excel），HTML 数据不能通过本接口单独保存。"
                    "请使用双向同步接口（d2-sync 或 workpaper-sync）保存数据，"
                    "或先在前端切换到「在线编辑」模式完成保存后再切回。"
                ),
                "wp_id": str(wp_id),
                "entry_id": entry_id,
            },
        ) from exc

    # Requirement 13.1 / Property 52：事件只在 content commit 之后发布。发布失败已经
    # 落成 failed 耐久行，由 outbox_replay_worker 重放、耗尽后进 DLQ，因此这里不需要
    # （也不允许）再把异常降级成 warning。
    await DurableEventOutboxService.publish_pending(db)

    # NOTE: touch_wp_registry 已由 ACNR events.on_workpaper_saved 统一处理（R23.1/R23.2）

    # ─── Step 8: 跨底稿引用变更检测 ──────────────────────────────────────
    stale_impact: list[StaleImpactItem] = []

    if wp_code:
        changes = cross_ref_service.detect_changes(
            wp_code=wp_code,
            sheet_name=body.sheet_name,
            old_html_data=old_sheet_data,
            new_html_data=body.html_data,
            changed_cells=body.changed_cells,
        )

        if changes:
            stale_impact = [
                StaleImpactItem(
                    ref_id=c.ref_id,
                    target_wp_code=c.target_wp_code,
                    target_sheet=c.target_sheet,
                    target_cell=c.target_cell,
                )
                for c in changes
            ]

            # 发布 SSE cross_ref.updated 事件
            _publish_cross_ref_updated(
                project_id=working_paper.project_id,
                source_wp_code=wp_code,
                changed_sheets=[body.sheet_name],
                affected_targets=[c.target_wp_code for c in changes],
            )

    # ─── Step 9: 报表 stale 联动（US-2）────────────────────────────────────
    if wp_code:
        try:
            from app.services.report_stale_service import report_stale_service

            await report_stale_service.mark_if_mapped(
                wp_code=wp_code,
                project_id=working_paper.project_id,
                db=db,
            )
        except Exception as exc:
            # stale 标记失败不阻断保存主流程
            logger.warning("report_stale_service.mark_if_mapped failed: %s", exc)

    # ─── Step 10: 聚合审定表 sheet 保存 → 审定数回写 trial_balance ──────────
    # 多文件聚合：父码底稿（如 D2）保存「审定表D2-1」sheet 时，发布 WORKPAPER_SAVED
    # 携带 sheet 级子码（D2-1）+ 计算后的审定行，触发既有 _on_d_audit_determination_saved
    # 回写 trial_balance.audited_amount（需求 4.4）。非审定表 sheet 不触发。
    await _maybe_publish_determination_writeback(
        db=db,
        project_id=working_paper.project_id,
        sheet_name=body.sheet_name,
        html_data=body.html_data,
    )

    return SaveHtmlDataResponse(
        saved_at=now.isoformat(),
        # 回传 **CAS 实际推进到的** revision，不是请求开始时算的期望值。两者相等由
        # `commit_html_projection` 的 `RevisionTargetError` 保证；这里取 receipt 是为了
        # 让「文件名里的 revision」与「客户端下次提交的 expected」永远来自同一个事实。
        data_version=receipt.revision,
        content_version_id=str(receipt.content_version_id),
        stale_impact=stale_impact,
    )


async def _maybe_publish_determination_writeback(
    *,
    db: AsyncSession,
    project_id: UUID,
    sheet_name: str,
    html_data: dict,
) -> None:
    """聚合审定表 sheet 保存后，计算各行审定数并发布 WORKPAPER_SAVED 触发 TB 回写。

    审定数公式（与前端 useAuditSheetTable.auditedAmount 一致）：
        audited = current_unadjusted + (adj_amount ?? sys_aje ?? 0)
                                     + (reclass_amount ?? sys_rje ?? 0)
    其中 current_unadjusted/sys_aje/sys_rje 实时查 trial_balance（不持久化）。

    仅当 sheet 名含审定表子码（[D-N]\\d+-1）且含 audit_rows 时触发；否则静默跳过。
    任何异常均降级（保存主流程已 commit，不受影响）。
    """
    try:
        from app.services.wp_account_package_resolver import (
            extract_determination_wp_code,
        )

        det_code = extract_determination_wp_code(sheet_name)
        if not det_code:
            return
        audit_rows = html_data.get("audit_rows") if isinstance(html_data, dict) else None
        if not isinstance(audit_rows, list) or not audit_rows:
            return

        from app.services.wp_audit_sheet_tb_service import fetch_audit_sheet_tb_values

        tb_values = await fetch_audit_sheet_tb_values(
            audit_rows, db=db, project_id=project_id
        )

        def _num(v: Any) -> float:
            try:
                return float(v) if v is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        writeback_rows: list[dict] = []
        for row in audit_rows:
            if not isinstance(row, dict):
                continue
            account_code = row.get("account_code")
            if not account_code or row.get("isComputed") or row.get("isSection"):
                continue
            tb = tb_values.get(row.get("id"), {}) if isinstance(tb_values, dict) else {}
            current_unadj = row.get("current_unadjusted")
            if current_unadj is None:
                current_unadj = tb.get("current_unadjusted")
            adj = row.get("adj_amount")
            if adj is None:
                adj = row.get("sys_aje")
            if adj is None:
                adj = tb.get("sys_aje")
            reclass = row.get("reclass_amount")
            if reclass is None:
                reclass = row.get("sys_rje")
            if reclass is None:
                reclass = tb.get("sys_rje")
            audited = _num(current_unadj) + _num(adj) + _num(reclass)
            writeback_rows.append(
                {"account_code": account_code, "audited_amount": audited}
            )

        if not writeback_rows:
            return

        # 推导年度
        year = await fetch_project_audit_year(db, project_id)
        if not year:
            return

        from app.models.audit_platform_schemas import EventPayload, EventType
        from app.services.event_bus import event_bus

        await event_bus.publish(EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=project_id,
            year=year,
            extra={
                "wp_code": det_code,
                "trigger": "aggregated_audit_sheet_save",
                "parsed_data": {"rows": writeback_rows},
            },
        ))
    except Exception as e:  # noqa: BLE001 — 回写联动失败不影响保存
        logger.warning(
            "聚合审定表回写联动失败 sheet=%s pid=%s: %s", sheet_name, project_id, e
        )


# ─── SSE 发布辅助 ────────────────────────────────────────────────────────────


def _publish_cross_ref_updated(
    project_id: UUID,
    source_wp_code: str,
    changed_sheets: list[str],
    affected_targets: list[str],
) -> None:
    """发布 cross_ref.updated SSE 事件。

    使用 EventBus.broadcast_raw 轻量级广播（不走完整 dispatch），
    写入 Redis Stream 供 SSE 端订阅。
    """
    try:
        from app.services.event_bus import event_bus

        event_bus.broadcast_raw(
            event_type="cross_ref.updated",
            extra={
                "project_id": str(project_id),
                "source_wp_code": source_wp_code,
                "changed_sheets": changed_sheets,
                "affected_targets": list(set(affected_targets)),
            },
        )
        logger.info(
            "Published cross_ref.updated: source=%s, targets=%s",
            source_wp_code,
            list(set(affected_targets)),
        )
    except Exception as exc:
        # SSE 发布失败不应阻断保存流程
        logger.warning("Failed to publish cross_ref.updated SSE: %s", exc)
