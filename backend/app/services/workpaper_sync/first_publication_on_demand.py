# -*- coding: utf-8 -*-
"""任意底稿首次进「在线编辑」时**按需**发布首版 representation。

spec: d2-online-edit-platform-closure · R7

═══ 为什么需要它 ═══

materialize 只能在「该 (wp, entry) 已有 current published representation」时打开 OnlyOffice
（AC 2.5）。而生产代码里发首版的 `publish_first_generation` 此前**只有宿主脚本**在调，且宿主
按全序为每个 entry **只选一张**目标底稿（canary）——现算 71 个 entry 有 entry_state、每个
entry 最多 2 张底稿。于是除 canary 外的每家企业点「在线编辑」恒得
`materialize_substrate_not_published`：平台修好了，用户照样进不去。

本模块把「首版」接成运行时能力，**不新增**任何发布路径：

1. :func:`resolve_plan` —— 五条准入原样复用（lane / bundle 已 provision / 尚无首版 / slot /
   契约已复核）。「已发布」由它的判据 B 判，不在这里另写一份；
2. :func:`read_store_payload` —— 与 store-projection **同一份** store 读取口径；
3. :func:`stage_instrumented_substrate` —— 权威模板 → instrumentation → OOXML 安全门，
   CPU 段放工作线程；
4. :func:`publish_first_generation` —— loader → adapter → `ContentMutationService.commit`，
   roundtrip / 未管理区域 / approved bundle 全部判据照旧。

本模块**不 commit**（service 只 flush，router 统一 commit）。

═══ 幂等 ═══

* 已有 current representation ⇒ `already_published`（零写入）。
* 两个请求并发：后到者要么在准入 ③ 被拦（`first_publication_already_done`），要么在
  commit 的 revision CAS 被拦（`RevisionConflictError`）。router 回滚后按 :func:`current_publication`
  复查，指针存在即按 `already_published` 返回 —— 两人同时点「在线编辑」不会有一人看到报错。
"""
from __future__ import annotations

import asyncio
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping

import sqlalchemy as sa

from app.services.workpaper_sync import projection_first_publication as F
from app.services.workpaper_sync.models import RevisionConflictError
from app.services.workpaper_sync.store_projection_response import (
    StoreProjectionNotBackedError,
    StoreProjectionProviderNotAllowedError,
    read_store_payload,
    resolve_store_projection_provider,
)


class StoreEmptyNotPublishableError(F.FirstPublicationError):
    """store 无内容，而该 provider 没有「空载荷」这个合法状态（`EMPTY_STORE_PAYLOAD is None`）。

    与宿主 `fix_projection_first_publication.EmptyStoreNotPublishableError` 同一个业务结论、
    同一个 error_code：「HTML 侧还没录内容，没有可发布的首版」—— 不是故障，是还没到时候。
    """

    error_code = "store_payload_empty_and_not_publishable"


#: 拒绝类型 → HTTP 状态码（router 的唯一映射点）。**按具体类登记**，未登记即 500
#: （与 `MATERIALIZE_REJECTION_STATUS` 同一条纪律：未知失败必须 fail visible）。
#:
#: 422 = 「这张底稿/这个 entry 现在不满足发首版的前提」，前端显示中文原因、不进编辑器。
FIRST_PUBLICATION_REJECTION_STATUS: Final[Mapping[type, int]] = {
    F.ProjectionBundleNotProvisionedError: 422,
    F.ContractNotReviewedError: 422,
    F.OoxmlSecurityRejectedError: 422,
    F.SubstrateStagingError: 422,
    F.ProviderCapabilityError: 422,
    StoreEmptyNotPublishableError: 422,
    StoreProjectionNotBackedError: 422,
    StoreProjectionProviderNotAllowedError: 422,
    RevisionConflictError: 409,
}


def classify_first_publication_rejection(exc: BaseException) -> int:
    """按具体类映射状态码；lane 裁决两类（未裁决 / opaque）同为 422，其余未登记 ⇒ 500。"""
    from app.services.workpaper_sync.projection_lane_registry import (
        LaneIsOpaqueError,
        LaneUndecidedError,
    )

    if type(exc) in (LaneUndecidedError, LaneIsOpaqueError):
        return 422
    return FIRST_PUBLICATION_REJECTION_STATUS.get(type(exc), 500)


@dataclass(frozen=True)
class FirstPublicationOutcome:
    """一次按需首版的结果。`status` ∈ {"published", "already_published"}。"""

    status: str
    representation_id: str
    representation_generation: int
    content_revision: int
    #: 本次 commit 入队的耐久事件（`already_published` 时为 None）。router 在**事务提交之后**
    #: 发布它（Requirement 13.1 / Property 52：事件只在 content commit 之后发出）。不进响应体。
    pending_event: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "representation_id": self.representation_id,
            "representation_generation": self.representation_generation,
            "content_revision": self.content_revision,
        }


async def current_publication(
    session: Any, *, wp_id: uuid.UUID, entry_id: str
) -> FirstPublicationOutcome | None:
    """该 (wp, entry) 的 current published representation；没有则 None。

    判据与 `resolve_plan` 第 ③ 条（供给判据 B）同表同条件：`working_paper_sync_entry_state`
    上有 (wp_id, entry_id) 这一行。
    """
    row = (
        await session.execute(
            sa.text(
                "SELECT s.current_representation_id, s.representation_generation, "
                "w.content_revision "
                "FROM working_paper_sync_entry_state s "
                "JOIN working_paper w ON w.id = s.wp_id "
                "WHERE s.wp_id = :wp AND s.entry_id = :entry"
            ),
            {"wp": wp_id, "entry": entry_id},
        )
    ).first()
    if row is None:
        return None
    return FirstPublicationOutcome(
        status="already_published",
        representation_id=str(row[0]),
        representation_generation=int(row[1]),
        content_revision=int(row[2]),
    )


async def ensure_first_publication(
    *,
    session: Any,
    resolution: Any,
    artifacts: Any,
    repository: Any,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    actor_id: uuid.UUID | None,
) -> FirstPublicationOutcome:
    """已有首版 ⇒ `already_published`；否则发布首版（只 flush，不 commit）。

    Raises:
        准入五条的各自异常、:class:`StoreEmptyNotPublishableError`、
        `publish_first_generation` 链上的判据异常（roundtrip / 未管理区域 / revision CAS）。
    """
    try:
        plan = await F.resolve_plan(
            session=session,
            resolution=resolution,
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            actor_id=actor_id,
        )
    except F.FirstPublicationAlreadyDoneError:
        existing = await current_publication(session, wp_id=wp_id, entry_id=entry_id)
        if existing is None:  # pragma: no cover - 判据 B 刚成立，指针不可能消失
            raise
        return existing

    # provider 由交付登记表 + 白名单解析（contract_id == adapter_id 单一真源），与
    # store-projection 同一入口；`publish_first_generation` 内部按 entry_id 解析的是同一行。
    provider = resolve_store_projection_provider(plan.contract_id)
    store = await read_store_payload(session=session, wp_id=wp_id, provider=provider)
    if store.empty and getattr(provider, "EMPTY_STORE_PAYLOAD", "") is None:
        raise StoreEmptyNotPublishableError(
            f"{entry_id} 在这张底稿上还没有录入任何内容，而该底稿没有「空表」这一可发布状态 —— "
            "请先在结构化视图录入内容后再进入在线编辑"
        )

    with tempfile.TemporaryDirectory(prefix="wp-sync-first-publication-") as tmp:
        # instrumentation + OOXML 安全门是纯 CPU 段：放工作线程，事件循环照常服务其他请求。
        staged = await asyncio.to_thread(
            F.stage_instrumented_substrate,
            entry_id=entry_id,
            staging_dir=Path(tmp),
            contract=plan.contract,
        )
        receipt = await F.publish_first_generation(
            session=session,
            resolution=resolution,
            artifacts=artifacts,
            repository=repository,
            plan=plan,
            staged=staged,
            store_payload=store.payload,
        )
    return FirstPublicationOutcome(
        status="published",
        representation_id=str(receipt.representation_id),
        representation_generation=int(receipt.representation_generation),
        content_revision=int(receipt.revision),
        pending_event=receipt.pending_event,
    )


__all__ = [
    "FIRST_PUBLICATION_REJECTION_STATUS",
    "FirstPublicationOutcome",
    "StoreEmptyNotPublishableError",
    "classify_first_publication_rejection",
    "current_publication",
    "ensure_first_publication",
]
