"""publication registry 的持久化仓储（V275）。

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
    "withdraw_publication_persisted",
    "security_revoke_publication_persisted",
    "offer_upgrade_persisted",
    "apply_upgrade_persisted",
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


# ---------------------------------------------------------------------------
# 撤回 / 安全撤销 / 升级（2026-11-24 补齐持久层接线）
#
# 为什么补这一层：`publication_ops.py` 早有 `withdraw_publication` /
# `security_revoke` / `offer_upgrade` / `apply_upgrade_via_staging` 四个纯内存实现，
# 但**只有测试调用**（零生产调用方）：进程重启后撤销状态与 pin 全丢，路由层也没有
# 对应端点 ⇒ 「撤回已发布的模板」这个业务能力在生产上根本不存在。
#
# 本段把它们逐一映射到 `custom_template_publications` /
# `custom_template_publication_pins`，语义与内存版逐条对齐：
# * withdraw：publication → WITHDRAWN，**pin 不自动清除**（已实例化的项目继续用）
# * security_revoke：publication → SECURITY_REVOKED，**清除相关 pin**（阻断新实例化）
# * offer_upgrade：只产 UpgradeOffer（含 from/to artifact digest 的 diff 指纹），
#   不改任何状态 —— 真正生效要 apply_upgrade
# * apply_upgrade：改写 pin 行（一个项目一个 pin，DB 唯一约束兜底）
# ---------------------------------------------------------------------------


def withdraw_publication_persisted(
    session: Any,
    *,
    organization_id: str,
    publication_key: str,
    reason: str = "withdrawn",
    clock: datetime | None = None,
) -> StoredPublication:
    """撤回 publication（→ WITHDRAWN）。pin 不清 —— 已实例化项目继续使用。

    与内存版 `publication_ops.withdraw_publication` 同语义：撤回是「下架，不再
    供新项目 pin」，不是「让在用的项目失效」。需要后者请用 security_revoke。
    """
    return transition_publication(
        session,
        organization_id=organization_id,
        publication_key=publication_key,
        to_state=PublicationState.WITHDRAWN,
        reason=reason,
        clock=clock,
    )


def security_revoke_publication_persisted(
    session: Any,
    *,
    organization_id: str,
    publication_key: str,
    reason: str = "security_revoked",
    clear_pins: bool = True,
    clock: datetime | None = None,
) -> list[uuid.UUID]:
    """安全撤销（→ SECURITY_REVOKED），默认清除相关 pin 以阻断后续实例化。

    返回受影响的 project_id 列表（与内存版返回值同型）。
    """
    pub = session.execute(
        sa.select(CustomTemplatePublication).where(
            CustomTemplatePublication.organization_id == organization_id,
            CustomTemplatePublication.publication_key == publication_key,
        )
    ).scalar_one_or_none()
    if pub is None:
        raise PublicationStoreError(f"publication 不存在：{publication_key}")

    # 先收集受影响项目，再推进状态（顺序与内存版一致：先 transition 再清 pin。
    # 这里先读是为了在同一事务里拿到准确列表，语义等价）。
    affected = list(
        session.execute(
            sa.select(CustomTemplatePublicationPin.project_id).where(
                CustomTemplatePublicationPin.publication_id == pub.id
            )
        ).scalars().all()
    )

    transition_publication(
        session,
        organization_id=organization_id,
        publication_key=publication_key,
        to_state=PublicationState.SECURITY_REVOKED,
        reason=reason,
        clock=clock,
    )

    if clear_pins and affected:
        session.execute(
            sa.delete(CustomTemplatePublicationPin).where(
                CustomTemplatePublicationPin.publication_id == pub.id
            )
        )
        session.flush()
    return affected


def offer_upgrade_persisted(
    session: Any,
    *,
    project_id: uuid.UUID,
    to_publication_key: str,
    organization_id: str,
) -> dict[str, Any]:
    """产出一份升级提议（不改状态）。

    与内存版 `offer_upgrade` 同判据：项目必须已 pin、目标必须存在且 ACTIVE。
    diff 指纹 = sha256(from|to|from_digest|to_digest)，与内存版逐字相同。
    """
    import hashlib as _hashlib

    from_pub = get_project_pin(session, project_id=project_id)
    if from_pub is None:
        raise PublicationStoreError("项目未 pin，无 upgrade")
    to_pub = get_publication(
        session, organization_id=organization_id, publication_key=to_publication_key
    )
    if to_pub is None:
        raise PublicationStoreError(f"目标 publication 不存在：{to_publication_key}")
    if to_pub.state != PublicationState.ACTIVE:
        raise PublicationStoreError(
            f"只能升级到 ACTIVE publication，目标当前 {to_pub.state.value}"
        )
    raw = (
        f"{from_pub.publication_key}|{to_pub.publication_key}|"
        f"{from_pub.artifact_digest}|{to_pub.artifact_digest}"
    )
    return {
        "fromPublicationKey": from_pub.publication_key,
        "toPublicationKey": to_pub.publication_key,
        "diffDigest": _hashlib.sha256(raw.encode()).hexdigest(),
        "requiresApproval": True,
    }


def apply_upgrade_persisted(
    session: Any,
    *,
    organization_id: str,
    project_id: uuid.UUID,
    to_publication_key: str,
    approval_intent_id: str | None,
    staging_ok: bool,
) -> str:
    """执行升级：改写项目 pin 到目标 publication。

    与内存版 `apply_upgrade_via_staging` 同判据：
    * 必须有 ApprovalIntent（升级是审批动作，不信任前端）；
    * `staging_ok=False` 时 **pin 不变**（失败不留半截状态）。
    """
    if not approval_intent_id:
        raise PublicationStoreError("升级需要有效 ApprovalIntent")
    to_pub = get_publication(
        session, organization_id=organization_id, publication_key=to_publication_key
    )
    if to_pub is None:
        raise PublicationStoreError(f"目标 publication 不存在：{to_publication_key}")
    if to_pub.state != PublicationState.ACTIVE:
        raise PublicationStoreError("只能升级到 ACTIVE publication")

    current = get_project_pin(session, project_id=project_id)
    if not staging_ok:
        # pin 不变 —— 与内存版一致
        if current is None:
            raise PublicationStoreError("项目未 pin，且 staging 未就绪")
        return current.publication_key

    pin_project(
        session,
        organization_id=organization_id,
        project_id=project_id,
        publication_key=to_publication_key,
    )
    return to_publication_key
