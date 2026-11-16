"""publication registry 的持久化仓储（V272）。

Spec: custom-workpaper-template-ingestion-and-sync-closure

## 为什么需要这一层

`publication_ops.PublicationRegistry` 是纯内存 dataclass：进程重启后
publication 与项目 pin 全部消失，而 `finalize_saga.begin_pending_visibility`
也只**返回** record、不落库。于是「finalize → publication → instantiate」这条
链在真实运行里根本接不上 —— service 写了、测试绿了、生产零调用方。

本模块把内存版语义逐一映射到 `custom_template_publications` /
`custom_template_publication_pins` 两张表，并与既有
`guidance_handoff_consumer_service.record_ack / resolve_visibility` 的
durable ACK ledger 配套使用（那部分持久化本来就有，只是没人调）。

## 不变量

* **publication 不可覆盖**：`(organization_id, publication_key)` 唯一；
  重复登记抛 `PublicationStoreError`，绝不 UPDATE 已有行的
  `artifact_digest` / `authority_ref` / `candidate_digest`。
* **只有 ACTIVE 能 pin**：与内存版 `pin_project` 同判据。
* **一个项目一个 pin**：DB 唯一约束 `uq_custom_publication_pin_project` 兜底，
  upgrade 即改写本行（历史 publication 行保留）。
* **instantiate 必须 ACTIVE**：`assert_instantiate_allowed` 同判据。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

import sqlalchemy as sa

from app.models.custom_template_publication import (
    CustomTemplatePublication,
    CustomTemplatePublicationPin,
)
from app.services.custom_template_ingestion.lifecycles import (
    PublicationState,
    TemplatePublicationRecord,
)

__all__ = [
    "PublicationStoreError",
    "StoredPublication",
    "register_publication",
    "get_publication",
    "list_publications",
    "transition_publication",
    "pin_project",
    "get_project_pin",
    "assert_instantiate_allowed_persisted",
]


class PublicationStoreError(ValueError):
    """publication 登记 / pin 的不合法操作（与内存版 ValueError 同语义）。"""


@dataclass(frozen=True, slots=True)
class StoredPublication:
    """DB 行的只读视图 —— 与 `TemplatePublicationRecord` 字段一一对应。"""

    id: uuid.UUID
    publication_key: str
    organization_id: str
    candidate_id: str
    candidate_digest: str
    authority_ref: str
    artifact_digest: str
    state: PublicationState
    reason: str | None
    handoff: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    def to_record(self) -> TemplatePublicationRecord:
        return TemplatePublicationRecord(
            publication_id=self.publication_key,
            organization_id=self.organization_id,
            candidate_id=self.candidate_id,
            candidate_digest=self.candidate_digest,
            authority_ref=self.authority_ref,
            state=self.state,
            created_at=self.created_at,
            updated_at=self.updated_at,
            reason=self.reason,
        )

    @property
    def runtime_discoverable(self) -> bool:
        """只有 ACTIVE 才对运行时可见（与 finalize_saga 同判据）。"""
        return self.state == PublicationState.ACTIVE


def _to_stored(row: CustomTemplatePublication) -> StoredPublication:
    return StoredPublication(
        id=row.id,
        publication_key=row.publication_key,
        organization_id=row.organization_id,
        candidate_id=row.candidate_id,
        candidate_digest=row.candidate_digest,
        authority_ref=row.authority_ref,
        artifact_digest=row.artifact_digest,
        state=PublicationState(row.state),
        reason=row.reason,
        handoff=dict(row.handoff or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def register_publication(
    session: Any,
    *,
    record: TemplatePublicationRecord,
    artifact_digest: str,
    handoff: Mapping[str, Any],
) -> StoredPublication:
    """登记一条 publication。只允许 ACTIVE / PENDING_VISIBILITY，且不可覆盖。

    与内存版 `PublicationRegistry.register_active` 的差异：内存版只收 ACTIVE，
    这里额外允许 PENDING_VISIBILITY —— finalize saga 的中间态需要落库，否则
    「saga 跑到一半崩溃」就没有可恢复的锚点。
    """
    if record.state not in (
        PublicationState.ACTIVE,
        PublicationState.PENDING_VISIBILITY,
    ):
        raise PublicationStoreError(
            f"只能登记 ACTIVE / PENDING_VISIBILITY publication，收到 {record.state.value}"
        )
    existing = session.execute(
        sa.select(CustomTemplatePublication).where(
            CustomTemplatePublication.organization_id == record.organization_id,
            CustomTemplatePublication.publication_key == record.publication_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise PublicationStoreError(
            f"publication 不可覆盖：{record.publication_id} 已存在"
        )
    row = CustomTemplatePublication(
        organization_id=record.organization_id,
        publication_key=record.publication_id,
        candidate_id=record.candidate_id,
        candidate_digest=record.candidate_digest,
        authority_ref=record.authority_ref,
        artifact_digest=artifact_digest,
        state=record.state.value,
        reason=record.reason,
        handoff=dict(handoff),
    )
    session.add(row)
    session.flush()
    return _to_stored(row)


def get_publication(
    session: Any,
    *,
    organization_id: str,
    publication_key: str,
) -> StoredPublication | None:
    row = session.execute(
        sa.select(CustomTemplatePublication).where(
            CustomTemplatePublication.organization_id == organization_id,
            CustomTemplatePublication.publication_key == publication_key,
        )
    ).scalar_one_or_none()
    return _to_stored(row) if row is not None else None


def list_publications(
    session: Any,
    *,
    organization_id: str,
    states: tuple[PublicationState, ...] | None = None,
) -> list[StoredPublication]:
    stmt = sa.select(CustomTemplatePublication).where(
        CustomTemplatePublication.organization_id == organization_id
    )
    if states:
        stmt = stmt.where(
            CustomTemplatePublication.state.in_([s.value for s in states])
        )
    stmt = stmt.order_by(CustomTemplatePublication.created_at.desc())
    return [_to_stored(r) for r in session.execute(stmt).scalars().all()]


def transition_publication(
    session: Any,
    *,
    organization_id: str,
    publication_key: str,
    to_state: PublicationState,
    reason: str,
    clock: datetime | None = None,
) -> StoredPublication:
    """状态推进。合法转换集合与 `TemplatePublicationRecord.transition` 共用
    `lifecycles._PUBLICATION_TRANSITIONS`，不另立一套判据。
    """
    from app.services.custom_template_ingestion.lifecycles import (
        InvalidLifecycleTransition,
        _PUBLICATION_TRANSITIONS,  # noqa: PLC2701 —— 单源，刻意为避免两套判据
    )

    row = session.execute(
        sa.select(CustomTemplatePublication)
        .where(
            CustomTemplatePublication.organization_id == organization_id,
            CustomTemplatePublication.publication_key == publication_key,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise PublicationStoreError(f"publication 不存在：{publication_key}")

    current = PublicationState(row.state)
    allowed = _PUBLICATION_TRANSITIONS.get(current, frozenset())
    if to_state not in allowed:
        raise InvalidLifecycleTransition(
            f"Publication {current.value} -> {to_state.value} 非法"
        )
    row.state = to_state.value
    row.reason = reason
    row.updated_at = clock or datetime.now(timezone.utc)
    session.flush()
    return _to_stored(row)


def pin_project(
    session: Any,
    *,
    organization_id: str,
    project_id: uuid.UUID,
    publication_key: str,
) -> uuid.UUID:
    """pin 项目到 ACTIVE publication。一个项目一个 pin，upgrade 即改写本行。"""
    pub = session.execute(
        sa.select(CustomTemplatePublication).where(
            CustomTemplatePublication.organization_id == organization_id,
            CustomTemplatePublication.publication_key == publication_key,
        )
    ).scalar_one_or_none()
    if pub is None:
        raise PublicationStoreError(f"未知 publication：{publication_key}")
    if pub.state != PublicationState.ACTIVE.value:
        raise PublicationStoreError("只能 pin ACTIVE publication")

    pin = session.execute(
        sa.select(CustomTemplatePublicationPin)
        .where(CustomTemplatePublicationPin.project_id == project_id)
        .with_for_update()
    ).scalar_one_or_none()
    if pin is None:
        pin = CustomTemplatePublicationPin(
            organization_id=organization_id,
            project_id=project_id,
            publication_id=pub.id,
        )
        session.add(pin)
    else:
        pin.publication_id = pub.id
        pin.organization_id = organization_id
        pin.pinned_at = datetime.now(timezone.utc)
    session.flush()
    return pin.id


def get_project_pin(
    session: Any,
    *,
    project_id: uuid.UUID,
) -> StoredPublication | None:
    row = session.execute(
        sa.select(CustomTemplatePublication)
        .join(
            CustomTemplatePublicationPin,
            CustomTemplatePublicationPin.publication_id == CustomTemplatePublication.id,
        )
        .where(CustomTemplatePublicationPin.project_id == project_id)
    ).scalar_one_or_none()
    return _to_stored(row) if row is not None else None


def assert_instantiate_allowed_persisted(pub: StoredPublication) -> None:
    """instantiate 门禁 —— 与内存版 `assert_instantiate_allowed` 同判据。"""
    if pub.state != PublicationState.ACTIVE:
        raise PublicationStoreError(
            f"instantiate 仅允许 ACTIVE publication，当前={pub.state.value}"
        )
