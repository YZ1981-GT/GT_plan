"""custom template publication registry 端点（从 custom_template_ingestion 抽出）。

Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 16 / 20

抽出原因：`custom_template_ingestion.py` 加完 publications 三段后 947 行，超
800 行门禁。按「超限优先抽模块不抬白名单」拆出本文件；原文件保留
ingest / preflight / unit-authority / finalize，publication 相关（list /
instantiate / commit-visibility）在此。

路由前缀与主文件一致（`/api/custom-template-ingestion`），前端路径不变。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.config import settings
from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user
from app.models.core import User
from app.services.custom_template_ingestion.authorization import (
    Capability,
    derive_implicit_scope,
    is_permitted,
    role_of,
)
from app.services.custom_template_ingestion.policy import POLICY_V1
from app.services.custom_template_ingestion.quarantine import (
    PrivateQuarantine,
    QuarantineError,
)

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/custom-template-ingestion",
    tags=["custom-template-ingestion"],
)

QUARANTINE_ROOT: Path = Path(settings.STORAGE_ROOT) / "custom_template_quarantine"


def get_quarantine() -> PrivateQuarantine:
    """构造 quarantine 内核（与 custom_template_ingestion 同装配）。

    本模块由 `custom_template_ingestion.py` 抽出（守 800 行门禁），故独立持有
    这份装配而不是跨 router import —— 跨 router 依赖会让两个模块互相拖住。
    测试用 monkeypatch 替换本模块命名空间里的 `get_quarantine`。
    """
    return PrivateQuarantine(root=QUARANTINE_ROOT, policy=POLICY_V1)


@router.get("/publications")
async def list_template_publications(
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """列出本组织的 custom template publication。

    `runtimeDiscoverable` 只对 ACTIVE 为 true —— 前端据此决定能否实例化。
    """
    from app.services.custom_template_ingestion.lifecycles import PublicationState
    from app.services.custom_template_ingestion.publication_registry_store import (
        list_publications,
    )

    scope = derive_implicit_scope(user=current_user)
    states: tuple[PublicationState, ...] | None = None
    if state:
        try:
            states = (PublicationState(state),)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"未知 publication 状态: {state}") from exc
    rows = await db.run_sync(
        lambda s: list_publications(
            s, organization_id=scope.organization_id, states=states
        )
    )
    return {
        "publications": [
            {
                "publicationKey": r.publication_key,
                "candidateId": r.candidate_id,
                "state": r.state.value,
                "artifactDigest": r.artifact_digest,
                "authorityRef": r.authority_ref,
                "reason": r.reason,
                "runtimeDiscoverable": r.state == PublicationState.ACTIVE,
                "createdAt": r.created_at.isoformat(),
                "updatedAt": r.updated_at.isoformat(),
            }
            for r in rows
        ]
    }


class InstantiateSheetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheetUid: str = Field(min_length=1, max_length=200)
    wpCode: str = Field(min_length=1, max_length=64)
    componentType: str = Field(min_length=1, max_length=64)
    projectionMode: str = Field(min_length=1, max_length=32)
    sheetCode: str | None = Field(default=None, max_length=64)
    manifestVersion: str | None = Field(default=None, max_length=64)


class InstantiateFromPublicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publicationKey: str = Field(min_length=1, max_length=160)
    workingPaperId: UUID
    sheets: list[InstantiateSheetInput] = Field(min_length=1)
    onlyOfficeRoomId: str | None = Field(default=None, max_length=256)


@router.post("/publications/instantiate")
async def instantiate_from_publication(
    body: InstantiateFromPublicationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """把 ACTIVE publication 实例化成整册 workbook 并落库。

    sheet 映射（wpCode / componentType / projectionMode）是**业务裁决**，由调用方
    提交；服务端只做白名单校验 —— 每个 sheetUid 必须真实出现在该 artifact 的
    preflight 报告里，拒绝凭空造的 sheet。
    """
    from app.models.workpaper_models import WorkingPaper
    from app.services.custom_template_ingestion.instantiate_from_publication import (
        InstantiateError,
        SheetSeedInput,
        instantiate_publication,
    )
    from app.services.custom_template_ingestion.publication_registry_store import (
        PublicationStoreError,
        get_publication,
        pin_project,
    )
    from app.services.custom_template_ingestion.workbook_instance import (
        WorkbookInstanceError,
    )

    scope = derive_implicit_scope(user=current_user)
    wp = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == body.workingPaperId,
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if wp is None:
        raise HTTPException(status_code=404, detail="目标底稿不存在")
    await assert_project_permission(db, current_user, wp.project_id, "edit")

    pub = await db.run_sync(
        lambda s: get_publication(
            s,
            organization_id=scope.organization_id,
            publication_key=body.publicationKey,
        )
    )
    if pub is None:
        raise HTTPException(status_code=404, detail="publication 不存在")
    if not pub.runtime_discoverable:
        raise HTTPException(
            status_code=409,
            detail=f"publication 当前状态 {pub.state.value} 不可实例化（需 ACTIVE）",
        )

    # preflight 报告是 sheet 白名单的唯一来源。它落在隔离区 manifest 里，
    # 读取是同步文件 IO ⇒ 放线程池，不阻塞事件循环。
    quarantine = get_quarantine()
    artifact_id = pub.candidate_id
    try:
        manifest = await asyncio.to_thread(
            quarantine.load_manifest, scope.organization_id, artifact_id
        )
    except (FileNotFoundError, QuarantineError) as exc:
        raise HTTPException(
            status_code=409,
            detail="publication 对应的隔离产物已不在，无法校验 sheet 白名单",
        ) from exc
    preflight = manifest.get("preflight")
    if not isinstance(preflight, dict):
        raise HTTPException(status_code=409, detail="隔离产物缺少 preflight 报告")
    workbook = preflight.get("workbook")
    preflight_sheets = (workbook or {}).get("sheets") if isinstance(workbook, dict) else None
    if not isinstance(preflight_sheets, list) or not preflight_sheets:
        raise HTTPException(status_code=409, detail="preflight 报告缺少 sheet 列表")

    sheet_inputs = [
        SheetSeedInput(
            sheet_uid=s.sheetUid,
            wp_code=s.wpCode,
            component_type=s.componentType,
            projection_mode=s.projectionMode,
            sheet_code=s.sheetCode,
            manifest_version=s.manifestVersion,
        )
        for s in body.sheets
    ]

    def _run(session):
        result = instantiate_publication(
            session,
            publication=pub,
            organization_id=scope.organization_id,
            project_id=str(wp.project_id),
            wp_id=str(wp.id),
            sheet_inputs=sheet_inputs,
            preflight_sheets=preflight_sheets,
            onlyoffice_room_id=body.onlyOfficeRoomId,
        )
        pin_project(
            session,
            organization_id=scope.organization_id,
            project_id=wp.project_id,
            publication_key=body.publicationKey,
        )
        return result

    try:
        result = await db.run_sync(_run)
    except PublicationStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InstantiateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WorkbookInstanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return {
        "publicationKey": result.publication_key,
        "workbookInstanceId": result.instance.workbook_instance_id,
        "projectId": str(wp.project_id),
        "pinned": True,
        "instantiated": True,
        "sheetCount": result.sheet_count,
        "entries": [
            {
                "entryId": c.entry_id,
                "sheetUid": c.sheet_uid,
                "wpCode": c.wp_code,
                "componentType": c.component_type,
                "projectionMode": c.projection_mode.value,
            }
            for c in result.instance.children
        ],
        "contextFingerprint": result.instance.context_fingerprint,
        "workbookGeneration": result.instance.workbook_generation,
    }


class AckSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consumer: str = Field(min_length=1, max_length=64)
    consumerVersion: str = Field(min_length=1, max_length=64)
    verdict: str = Field(pattern=r"^(ACCEPTED|REJECTED)$")
    reasonCodes: list[str] = Field(default_factory=list)


class CommitVisibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publicationKey: str = Field(min_length=1, max_length=160)
    acks: list[AckSubmission] = Field(default_factory=list)


@router.post("/publications/commit-visibility")
async def commit_publication_visibility(
    body: CommitVisibilityRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """收集 consumer ACK 并把 PENDING_VISIBILITY publication 推进到 ACTIVE。

    ACK 落真实 `guidance_consumer_ack` 表、visibility 落
    `guidance_handoff_visibility` 表（复用 `guidance_handoff_consumer_service`）。
    **只有四个必需 consumer 全部 ACCEPTED 才 ACTIVE** —— 任一缺 ACK 保持
    PENDING_VISIBILITY，任一 REJECTED 落 FAILED。
    """
    from app.services.custom_template_ingestion.durable_ack_ledger import (
        DurableAckLedger,
    )
    from app.services.custom_template_ingestion.finalize_saga import (
        FinalizeSagaError,
        REQUIRED_FINALIZE_CONSUMERS,
    )
    from app.services.custom_template_ingestion.lifecycles import (
        InvalidLifecycleTransition,
        PublicationState,
    )
    from app.services.custom_template_ingestion.publication_registry_store import (
        PublicationStoreError,
        get_publication,
        transition_publication,
    )

    scope = derive_implicit_scope(user=current_user)

    pub = await db.run_sync(
        lambda s: get_publication(
            s,
            organization_id=scope.organization_id,
            publication_key=body.publicationKey,
        )
    )
    if pub is None:
        raise HTTPException(status_code=404, detail="publication 不存在")
    # 权限：收集 ACK 并推进可见性是 finalize 之后的技术推进，属
    # `FINALIZE_PROJECT`（manager / admin 持有），与 instantiate 同级。
    # 🔴 不是 `APPROVE_PUBLISH_ORGANIZATION` —— 后者是**组织级发布的批准权**
    # （partner / qc 持有、走 ApprovalIntent 双人复核），语义不同。
    # 曾误用 approve 权限，导致 admin 点「推进可见性」直接 403（浏览器实测抓到），
    # 而库里 partner/qc 用户数为 0 ⇒ 该端点实际无人可用。
    role = role_of(current_user)
    if not is_permitted(role, Capability.FINALIZE_PROJECT):
        raise HTTPException(
            status_code=403, detail="推进 publication 可见性需要 finalize 权限"
        )

    if pub.state == PublicationState.ACTIVE:
        return {
            "publicationKey": pub.publication_key,
            "state": PublicationState.ACTIVE.value,
            "runtimeDiscoverable": True,
            "idempotent": True,
        }
    if pub.state != PublicationState.PENDING_VISIBILITY:
        raise HTTPException(
            status_code=409,
            detail=f"publication 当前状态 {pub.state.value} 不可推进可见性",
        )

    handoff = pub.handoff or {}
    handoff_id = str(handoff.get("handoffId") or "")
    handoff_digest = str(handoff.get("handoffDigest") or "")
    if not handoff_id or not handoff_digest:
        raise HTTPException(status_code=409, detail="publication 缺少 handoff 身份，无法推进可见性")

    unknown = [a.consumer for a in body.acks if a.consumer not in REQUIRED_FINALIZE_CONSUMERS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"未知 consumer: {', '.join(sorted(set(unknown)))}",
        )

    def _run(session):
        ledger = DurableAckLedger(session)
        for ack in body.acks:
            ledger.upsert(
                handoff_id=handoff_id,
                handoff_digest=handoff_digest,
                consumer=ack.consumer,
                consumer_version=ack.consumerVersion,
                verdict=ack.verdict,
                reason_codes=tuple(ack.reasonCodes),
            )
        state = ledger.resolve(handoff_id=handoff_id, handoff_digest=handoff_digest)
        if state == "ACTIVE":
            transition_publication(
                session,
                organization_id=scope.organization_id,
                publication_key=body.publicationKey,
                to_state=PublicationState.ACTIVE,
                reason="all_acks_accepted",
            )
        elif state == "REJECTED":
            transition_publication(
                session,
                organization_id=scope.organization_id,
                publication_key=body.publicationKey,
                to_state=PublicationState.FAILED,
                reason="ack_rejected",
            )
        return state

    try:
        visibility_state = await db.run_sync(_run)
    except FinalizeSagaError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidLifecycleTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PublicationStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return {
        "publicationKey": body.publicationKey,
        "visibilityState": visibility_state,
        "state": (
            PublicationState.ACTIVE.value
            if visibility_state == "ACTIVE"
            else PublicationState.FAILED.value
            if visibility_state == "REJECTED"
            else PublicationState.PENDING_VISIBILITY.value
        ),
        "runtimeDiscoverable": visibility_state == "ACTIVE",
        "requiredConsumers": list(REQUIRED_FINALIZE_CONSUMERS),
        "idempotent": False,
    }
