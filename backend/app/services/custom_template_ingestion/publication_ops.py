"""immutable publication、pin、升级/回滚、withdraw/revocation（Task 16）。"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Mapping, Sequence

from app.services.custom_template_ingestion.lifecycles import (
    Clock,
    InvalidLifecycleTransition,
    PublicationState,
    SystemClock,
    TemplatePublicationRecord,
)
from app.services.custom_template_ingestion.workbook_instance import (
    ProjectWorkbookInstance,
    SheetSeed,
    WorkbookInstanceError,
    create_workbook_instance,
)

__all__ = [
    "PublicationRegistry",
    "UpgradeOffer",
    "instantiate_from_active",
    "offer_upgrade",
    "apply_upgrade_via_staging",
    "withdraw_publication",
    "security_revoke",
]


@dataclass
class PublicationRegistry:
    """不可变 publication 登记：新 version 不覆盖旧 artifact。"""

    publications: dict[str, TemplatePublicationRecord] = field(default_factory=dict)
    #: publication_id → artifact digests（不可变）
    artifacts: dict[str, str] = field(default_factory=dict)
    pins: dict[str, str] = field(default_factory=dict)  # project_id → publication_id

    def register_active(self, pub: TemplatePublicationRecord, artifact_digest: str) -> None:
        if pub.state != PublicationState.ACTIVE:
            raise ValueError("只能登记 ACTIVE publication")
        if pub.publication_id in self.publications:
            raise ValueError("publication_id 不可覆盖")
        self.publications[pub.publication_id] = pub
        self.artifacts[pub.publication_id] = artifact_digest

    def pin_project(self, project_id: str, publication_id: str) -> None:
        if publication_id not in self.publications:
            raise ValueError("未知 publication")
        pub = self.publications[publication_id]
        if pub.state != PublicationState.ACTIVE:
            raise ValueError("只能 pin ACTIVE")
        self.pins[project_id] = publication_id


@dataclass(frozen=True, slots=True)
class UpgradeOffer:
    from_publication_id: str
    to_publication_id: str
    diff_digest: str
    requires_approval: bool = True


def instantiate_from_active(
    registry: PublicationRegistry,
    *,
    publication_id: str,
    organization_id: str,
    project_id: str,
    wp_id: str,
    sheets: Sequence[SheetSeed],
    current_artifact_id: str,
) -> ProjectWorkbookInstance:
    pub = registry.publications.get(publication_id)
    if pub is None or pub.state != PublicationState.ACTIVE:
        raise WorkbookInstanceError("instantiate 只允许 ACTIVE publication")
    inst = create_workbook_instance(
        organization_id=organization_id,
        project_id=project_id,
        wp_id=wp_id,
        workbook_lineage_id=pub.authority_ref,
        pinned_template_version_id=publication_id,
        current_artifact_id=current_artifact_id,
        content_revision="c0",
        representation_revision="r0",
        sheets=sheets,
    )
    registry.pin_project(project_id, publication_id)
    return inst


def offer_upgrade(
    registry: PublicationRegistry,
    *,
    project_id: str,
    to_publication_id: str,
) -> UpgradeOffer:
    from_id = registry.pins.get(project_id)
    if not from_id:
        raise ValueError("项目未 pin，无 upgrade")
    if to_publication_id not in registry.publications:
        raise ValueError("目标 publication 不存在")
    if registry.publications[to_publication_id].state != PublicationState.ACTIVE:
        raise ValueError("只能升级到 ACTIVE")
    raw = f"{from_id}|{to_publication_id}|{registry.artifacts[from_id]}|{registry.artifacts[to_publication_id]}"
    return UpgradeOffer(
        from_publication_id=from_id,
        to_publication_id=to_publication_id,
        diff_digest=hashlib.sha256(raw.encode()).hexdigest(),
        requires_approval=True,
    )


def apply_upgrade_via_staging(
    registry: PublicationRegistry,
    *,
    project_id: str,
    offer: UpgradeOffer,
    approval_intent_id: str | None,
    staging_ok: bool,
) -> str:
    """升级必须有 ApprovalIntent；staging 失败不动 pin。"""
    if offer.requires_approval and not approval_intent_id:
        raise ValueError("升级需要有效 ApprovalIntent")
    if not staging_ok:
        # pin 不变
        return registry.pins[project_id]
    registry.pins[project_id] = offer.to_publication_id
    return offer.to_publication_id


def withdraw_publication(
    registry: PublicationRegistry,
    publication_id: str,
    *,
    clock: Clock | None = None,
) -> None:
    clk = clock or SystemClock()
    pub = registry.publications[publication_id]
    pub.transition(PublicationState.WITHDRAWN, clock=clk, reason="withdrawn")
    # pinned 项目继续使用 —— pin 不自动清除


def security_revoke(
    registry: PublicationRegistry,
    publication_id: str,
    *,
    clock: Clock | None = None,
    clear_pins: bool = True,
) -> list[str]:
    """SECURITY_REVOKED：可阻断 pinned instance；返回受影响 project_id。"""
    clk = clock or SystemClock()
    pub = registry.publications[publication_id]
    pub.transition(PublicationState.SECURITY_REVOKED, clock=clk, reason="security_revoked")
    affected = [pid for pid, pub_id in registry.pins.items() if pub_id == publication_id]
    if clear_pins:
        for pid in affected:
            del registry.pins[pid]
    return affected
