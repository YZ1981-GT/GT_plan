"""Evidence Governance Attachments Router — 安全上传 + 安全读取 HTTP 装配。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R2, R12, R15
Design: §5.1 流式上传与异步 finalize / read path, §6.2 主要端点 (Attachment row),
        §7.2 稳定失败类别
Properties: P1 (项目隔离), P2 (存储边界封闭), P3 (创建主体完备), P29 (降级安全)

本模块只做 **缺失的 HTTP 接线**，复用已实现的 ``SecureAttachmentGateway`` +
``UploadAttempt`` 模型 + ``StorageBoundaryResolver``，不复制存储/OCR/边界引擎。

端点（前缀 /api/projects/{project_id}/years/{year}/evidence/attachments）：
  - POST /                                 — 治理安全上传（multipart，先建 UploadAttempt 再验证）
  - GET  /{attachment_id}/content          — 安全读取（边界/权限先于字节 I/O）
  - GET  /versions/{version_id}/content    — 按版本安全读取

所有端点：
  - scope + capability 校验由 facade 在任何字节 I/O / 业务写之前执行（scope-first）。
  - 失败返回脱敏 error_code（SCOPE_NOT_FOUND_OR_FORBIDDEN 等），不泄露路径/目标项目。
  - 读取只返回 opaque locator / 受控下载 URL，绝不返回绝对路径（design §6.1 C3）。
  - 写命令支持 Idempotency-Key。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.attachment_service import AttachmentService
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.attachment_security_gates import (
    resolve_attachment_security_gates,
)
from app.services.evidence_governance.secure_attachment_gateway import (
    DEFAULT_CHUNK_SIZE,
    DurableQuarantineStore,
    InMemoryQuarantineStore,
    SecureAttachmentGateway,
    StorageBoundaryResolver,
)
from app.services.evidence_governance.scope_guard import ProjectYearScopeGuard
from app.services.evidence_governance.version_manager import (
    AttachmentVersionManager,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/years/{year}/evidence/attachments",
    tags=["evidence-governance"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_uuid(value: str, field_name: str = "id") -> uuid.UUID:
    """解析 UUID，无效则抛脱敏错误（不泄露目标存在性）。"""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            f"invalid {field_name}",
        )


async def _get_user_role(db: AsyncSession, user: Any, project_id: uuid.UUID) -> str:
    """获取用户在项目中的角色（DB 为权威真源；对齐 ocr/evidence_ref router）。"""
    import sqlalchemy as sa

    if hasattr(user, "role"):
        role = user.role
        role_val = role.value if hasattr(role, "value") else role
        if role_val in ("admin", "partner"):
            return role_val

    row = (
        await db.execute(
            sa.text(
                "SELECT role FROM project_users "
                "WHERE project_id = :pid AND user_id = :uid "
                "AND is_deleted = false LIMIT 1"
            ),
            {"pid": str(project_id), "uid": str(user.id)},
        )
    ).mappings().first()
    if row:
        return row["role"]

    if hasattr(user, "role"):
        role = user.role
        return role.value if hasattr(role, "value") else role
    return "readonly"


def _build_gateway(db: AsyncSession) -> SecureAttachmentGateway:
    """构造网关：委托 ``AttachmentService`` 做实际存储/finalize（禁止分叉存储）。

    读取用默认 spy-friendly ``LocalByteReader`` + 从 settings 派生的
    ``StorageBoundaryResolver``；本地存储读取即经边界解析器。paperless 远程字节由
    ``AttachmentService`` 服务凭据解析（未注入远程读取器时安全降级为 DEPENDENCY_DEGRADED）。

    **三道内容门从配置真实接线**（R1.2/R1.3/R2/R15）：声明媒体类型允许清单 / 恶意内容
    扫描（最小签名式 + 可选 ClamAV）/ 可读性检查。不再让门保持 None 默认（None 会以
    ``default=True`` 静默放行）。门仍可注入覆盖（测试构造 gateway 时显式传参即可）。
    """
    gates = resolve_attachment_security_gates()
    return SecureAttachmentGateway(
        db,
        attachment_service=AttachmentService(db),
        quarantine_store=_build_quarantine_store(),
        allowed_media_types=gates.allowed_media_types,
        malware_scanner=gates.malware_scanner,
        readability_checker=gates.readability_checker,
    )


def _build_quarantine_store():
    """从配置构造隔离区实现（生产默认 **durable 磁盘 store**）。

    ``ATTACHMENT_QUARANTINE_DURABLE=True``（默认）时用 :class:`DurableQuarantineStore`——
    202 异步 finalize / API 重启 / 独立 worker 进程后 staged 内容仍在，可 finalize；且崩溃时
    reaper 仍能加密擦除。根目录为 ``settings.ATTACHMENT_QUARANTINE_ROOT``（非 servable，位于任何
    Storage_Boundary root 之外，隔离内容对任何读取/边界链不可达）。可通过配置切回进程内实现；
    测试仍可直接给 gateway 注入 ``InMemoryQuarantineStore``（本函数不影响测试构造的 gateway）。
    """
    from app.core.config import settings

    if getattr(settings, "ATTACHMENT_QUARANTINE_DURABLE", True):
        return DurableQuarantineStore(settings.ATTACHMENT_QUARANTINE_ROOT)
    return InMemoryQuarantineStore()


# ─────────────────────────────────────────────────────────────────────────────
# POST / — 治理安全上传（R1/R2/R12）
# ─────────────────────────────────────────────────────────────────────────────


@router.post("")
async def upload_attachment(
    project_id: str,
    year: int,
    response: Response,
    file: UploadFile = File(...),
    declared_media_type: str | None = Form(None),
    source_type: str | None = Form(None),
    provider: str | None = Form(None),
    is_key_evidence: bool = Form(False),
    synchronous_finalize: bool = Form(True),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """治理安全上传（design §5.1）。

    流程（``SecureAttachmentGateway.receive_upload``）：
      1. **先建最小 UploadAttempt(pending)**（内容验证之前，R1.1）。
      2. 固定块流式接收 + SHA-256 / magic MIME / 大小 / 背压检查；任何失败都
         **不创建可用 Attachment/AttachmentVersion**，删除/加密擦除隔离内容，并把
         **同一** attempt 收敛为 rejected/quarantined/failed（R1.2）。
      3. staged → finalize（委托 AttachmentService）→ available（仅合法内容）。

    返回 attempt id + outcome + response_mode（201 同步 available / 202 staged 异步 /
    413/415/422/429 失败）。scope/capability 由 facade 在任何字节 I/O 前执行；跨项目/越权
    在此阶段即以脱敏 SCOPE_NOT_FOUND_OR_FORBIDDEN 拒绝。
    """
    pid = _parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    idem_key = idempotency_key or f"upload:{pid}:{year}:{uuid.uuid4().hex}"

    async def _chunks():
        # 固定块流式读取 multipart，避免把整个文件读入内存（design §5.1）。
        while True:
            data = await file.read(DEFAULT_CHUNK_SIZE)
            if not data:
                break
            yield data

    gateway = _build_gateway(db)
    receipt = await gateway.receive_upload(
        project_id=pid,
        audit_year=year,
        raw_file_name=file.filename,
        declared_media_type=declared_media_type or file.content_type,
        chunks=_chunks(),
        actor=actor,
        actor_role=role,
        idempotency_key=idem_key,
        source_type=source_type,
        provider=provider,
        is_key_evidence=is_key_evidence,
        synchronous_finalize=synchronous_finalize,
    )

    # response_mode 映射为 HTTP 状态（201 available / 202 staged / 413/415/422/429 失败）。
    response.status_code = receipt.response_mode
    body: dict[str, Any] = {
        "attempt_id": str(receipt.attempt_id),
        "outcome": receipt.outcome,
        "content_hash": receipt.content_hash,
        "detected_media_type": receipt.detected_media_type,
        "received_byte_size": receipt.received_byte_size,
        "availability": receipt.availability,
    }
    # 只有合法内容才暴露可用 Attachment/Version id；失败不返回可用记录（R1.2）。
    if receipt.is_available or receipt.availability is not None:
        body["attachment_id"] = (
            str(receipt.attachment_id) if receipt.attachment_id else None
        )
        body["attachment_version_id"] = (
            str(receipt.attachment_version_id)
            if receipt.attachment_version_id
            else None
        )
        body["is_available"] = receipt.is_available
    if receipt.error_code is not None:
        body["error_code"] = receipt.error_code.value
        body["failure_category"] = receipt.failure_category
    return body


# ─────────────────────────────────────────────────────────────────────────────
# GET /{attachment_id}/content — 安全读取（R1/R12/R15）
# ─────────────────────────────────────────────────────────────────────────────


def _read_result_body(result: Any) -> dict[str, Any]:
    """把安全读取结果投影为脱敏响应：opaque locator / 受控下载 URL，绝不含绝对路径。"""
    return {
        "attachment_id": str(result.attachment_id),
        "attachment_version_id": str(result.attachment_version_id),
        "version_no": result.version_no,
        "media_type": result.media_type,
        "byte_size": result.byte_size,
        "content_hash": result.content_hash,
        # C3：只返回受控下载 URL（opaque locator），不返回 storage_key/绝对路径。
        "locator": f"/api/attachments/{result.attachment_id}/download",
    }


@router.get("/{attachment_id}/content")
async def read_attachment_content(
    project_id: str,
    year: int,
    attachment_id: str,
    version_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """安全读取附件内容（design §5.1 read path）。

    严格拒绝链（scope/权限/边界失败时字节读取器 open/stat/read 计数恒为 0）：
      (a) legacy/new ID 解析为确定根 + 确定版本（纯 DB 读）；
      (b) scope + 成员权限（facade 在业务回调 **之前** 执行）；
      (c) StorageBoundaryResolver 规范化 opaque storage_key 并确认仍在 Storage_Boundary 内。

    越界/外项目/不存在统一返回脱敏 SCOPE_NOT_FOUND_OR_FORBIDDEN，不泄露路径/目标项目。
    成功只返回 opaque locator / 受控下载 URL（绝不返回绝对路径）。
    """
    pid = _parse_uuid(project_id, "project_id")
    aid = _parse_uuid(attachment_id, "attachment_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    vid = _parse_uuid(version_id, "version_id") if version_id else None

    gateway = _build_gateway(db)
    result = await gateway.read_attachment_content(
        attachment_id=aid,
        actor=actor,
        actor_role=role,
        requested_project_id=pid,
        requested_year=year,
        version_id=vid,
    )
    return _read_result_body(result)


@router.get("/versions/{version_id}/content")
async def read_attachment_version_content(
    project_id: str,
    year: int,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """按 AttachmentVersion id 安全读取（R1/R12/R15）。

    先经纯 DB 读解析该版本所属的 attachment 根（scope 归属再由 facade 权威校验），再走与
    ``/{attachment_id}/content`` 相同的边界先于字节 I/O 拒绝链。版本不存在/不可读统一
    脱敏 SCOPE_NOT_FOUND_OR_FORBIDDEN。
    """
    import sqlalchemy as sa

    pid = _parse_uuid(project_id, "project_id")
    vid = _parse_uuid(version_id, "version_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    # 解析版本 → attachment 根（纯 DB 读；不泄露存在性）。
    row = (
        await db.execute(
            sa.text(
                "SELECT attachment_id FROM attachment_versions "
                "WHERE id = :vid LIMIT 1"
            ),
            {"vid": str(vid)},
        )
    ).mappings().first()
    if row is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "attachment version not found or forbidden",
        )

    gateway = _build_gateway(db)
    result = await gateway.read_attachment_content(
        attachment_id=uuid.UUID(str(row["attachment_id"])),
        actor=actor,
        actor_role=role,
        requested_project_id=pid,
        requested_year=year,
        version_id=vid,
    )
    return _read_result_body(result)


# ─────────────────────────────────────────────────────────────────────────────
# Version replace + impact (Task 3.5 / R2 / R9 — design §4.3 step 8, §5.1)
#   ``AttachmentVersionManager`` was implemented (replace_version / assess_impact) but
#   never routed. Wire the two missing surfaces so §6.2 Attachment row
#   ("GET/POST /attachments/{id}/versions, GET content/impact") is reachable.
# ─────────────────────────────────────────────────────────────────────────────


class ReplaceVersionRequest(BaseModel):
    """请求体：替换附件内容 → 生成新版本 vN+1（旧版本不可变，下游 stale）。"""

    new_content_hash: str = Field(..., min_length=1, max_length=200)
    new_storage_key: str | None = None
    new_storage_type: str = Field(default="local", max_length=50)
    new_media_type: str | None = Field(default=None, max_length=200)
    new_byte_size: int | None = Field(default=None, ge=0)
    config_snapshot: dict | None = None
    expected_current_version: int | None = Field(default=None, ge=0)
    impact_confirmed: bool = False


def _impact_report_body(report: Any) -> dict[str, Any]:
    """把 ``ImpactReport`` 投影为响应（直接 + 传递影响 + hold/formal 标志 + 阻断状态）。"""
    return {
        "attachment_id": str(report.attachment_id),
        "version_no": report.version_no,
        "has_legal_hold": report.has_legal_hold,
        "has_formal_output": report.has_formal_output,
        "total_count": report.total_count,
        "blocked": report.blocked,
        "direct_impacts": [
            {
                "ref_id": e.ref_id,
                "ref_type": e.ref_type,
                "source_type": e.source_type,
                "source_id": e.source_id,
                "label": e.label,
                "is_transitive": e.is_transitive,
            }
            for e in report.direct_impacts
        ],
        "transitive_impacts": [
            {
                "ref_id": e.ref_id,
                "ref_type": e.ref_type,
                "source_type": e.source_type,
                "source_id": e.source_id,
                "label": e.label,
                "is_transitive": e.is_transitive,
            }
            for e in report.transitive_impacts
        ],
    }


@router.post("/{attachment_id}/versions", status_code=201)
async def replace_attachment_version(
    project_id: str,
    year: int,
    attachment_id: str,
    body: ReplaceVersionRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """替换附件内容 → 生成新版本 vN+1（R2/R9；capability attachment.replace）。

    委托 ``AttachmentVersionManager.replace_version``（经 facade：scope + capability +
    object 归属重解析 + 短事务 + command-root + outbox stale 传播）：

      1. ``SELECT attachments ... FOR UPDATE`` 锁父行，读当前 max version_no；
      2. active Legal Hold → ``LEGAL_HOLD_ACTIVE``（零效果，只允许新增版本不覆盖历史）；
      3. 当前版本被引用且未确认影响 → ``EVIDENCE_GATE_BLOCKED``（先看 impact）；
      4. 生成 ``version_no = max + 1``，INSERT 新 AttachmentVersion（旧版本不可变，P4）；
      5. 更新父 current_version_id，outbox ``attachment.version_replaced`` 使下游 stale。

    跨项目/越权/不存在统一脱敏 ``SCOPE_NOT_FOUND_OR_FORBIDDEN``。
    """
    pid = _parse_uuid(project_id, "project_id")
    aid = _parse_uuid(attachment_id, "attachment_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    idem_key = idempotency_key or f"attachment:replace:{aid}:{body.new_content_hash}"

    mgr = AttachmentVersionManager(db)
    result = await mgr.replace_version(
        attachment_id=aid,
        new_content_hash=body.new_content_hash,
        new_storage_key=body.new_storage_key,
        new_storage_type=body.new_storage_type,
        new_media_type=body.new_media_type,
        new_byte_size=body.new_byte_size,
        config_snapshot=body.config_snapshot,
        actor=actor,
        actor_role=role,
        idempotency_key=idem_key,
        project_id=pid,
        audit_year=year,
        expected_current_version=body.expected_current_version,
        impact_confirmed=body.impact_confirmed,
    )

    return {
        "attachment_id": str(result.attachment_id),
        "new_version_id": str(result.new_version_id),
        "new_version_no": result.new_version_no,
        "previous_version_id": (
            str(result.previous_version_id) if result.previous_version_id else None
        ),
        "content_hash": result.content_hash,
        "command_root_id": str(result.command_root_id),
    }


@router.get("/{attachment_id}/impact")
async def assess_attachment_impact(
    project_id: str,
    year: int,
    attachment_id: str,
    version_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """评估替换/删除某版本的直接与传递影响（R2.3 / R9.1；只读）。

    scope 先于业务：``ProjectYearScopeGuard.authorize_object`` 从 DB 重新解析该附件的权威
    归属并与 path scope 比对（不存在/越权同一脱敏 ``SCOPE_NOT_FOUND_OR_FORBIDDEN``），再委托
    ``AttachmentVersionManager.assess_impact`` 返回引用/正式产出/Legal Hold 依赖清单，供有
    权限用户在破坏性操作前确认。
    """
    pid = _parse_uuid(project_id, "project_id")
    aid = _parse_uuid(attachment_id, "attachment_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    vid = _parse_uuid(version_id, "version_id") if version_id else None

    # scope 先于业务：重解析附件归属并授权（脱敏拒绝）。
    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_object(
        actor_role=role,
        actor=actor,
        object_type="attachment",
        object_id=aid,
        requested_project_id=pid,
        requested_year=year,
    )

    mgr = AttachmentVersionManager(db)
    report = await mgr.assess_impact(aid, version_id=vid, project_id=pid)
    return _impact_report_body(report)
