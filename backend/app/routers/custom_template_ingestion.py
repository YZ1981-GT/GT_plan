"""自定义 Excel 模板摄取的独立三入口路由。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 3.6, 3.7

## 为什么是新 router，而不是改 `custom_templates.py`

Requirement 1.5：旧 API 仍接收 `template_file_path`、空 `file_content` 或首 sheet
元数据时，**不得进入正式 ingestion/publication 路径**，并必须有带期限的迁移删除门。

三条新链前缀为 ``/api/custom-template-ingestion/*``，与旧
``/api/custom-templates`` **并列**：

* 旧链保持原样（存量前端仍依赖），但已不再是正式摄取路径；
* 新链是唯一走真实 multipart + private quarantine 的入口；
* 迁移删除门见下方 ``LEGACY_MIGRATION_DEADLINE``，到期后旧链应整体下线。

🔴 本路由**不**生成 HTML / OnlyOffice config / project artifact / runtime entry。
它只做「字节进隔离区 + 返回结构化结果」。preflight 是 Task 5/6 的职责，这里
只返回 ``QUARANTINED`` 状态与 artifact id，供后续任务消费。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.config import settings
from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user
from app.models.core import User
from app.services.custom_template_ingestion.actions import (
    ACTION_IDS,
    INGEST_EXCEL_TEMPLATE,
    success_message,
    spec_for,
)
from app.services.custom_template_ingestion.authorization import (
    CAPABILITY_MATRIX,
    Scope,
    derive_implicit_scope,
    is_permitted,
    role_of,
)
from app.services.custom_template_ingestion.policy import POLICY_V1
from app.services.custom_template_ingestion.quarantine import (
    ArtifactState,
    PrivateQuarantine,
    QuarantineError,
    QuarantineArtifact,
)

router = APIRouter(
    prefix="/api/custom-template-ingestion",
    tags=["custom-template-ingestion"],
)

#: 旧链（/api/custom-templates 的 template_file_path / file_content / 首 sheet）
#: 退出正式路径的期限。到期后旧路由应整体下线（Requirement 1.5 迁移删除门）。
LEGACY_MIGRATION_DEADLINE: str = "2026-12-31"

#: quarantine 根目录。与 ledger_uploads 同级，位于 STORAGE_ROOT 下。
QUARANTINE_ROOT: Path = Path(settings.STORAGE_ROOT) / "custom_template_quarantine"


def get_quarantine() -> PrivateQuarantine:
    """构造 quarantine 内核。

    依赖注入点在 service 层已做（root/policy/clock 全部可注入），这里只做
    生产默认装配。测试直接构造 ``PrivateQuarantine(root=tmp)``，不走本函数。
    """
    return PrivateQuarantine(root=QUARANTINE_ROOT, policy=POLICY_V1)


# ─────────────────────────────────────────────────────────────────────────────
# 1) 入口元数据 —— 让前端能区分三条链，不靠中文文案判断
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/actions")
async def list_actions(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """返回三条 action 的稳定 id 与语义（Requirement 1.4）。

    🔴 权限过滤：只返回当前角色实际具备 capability 的 action，避免 UI 渲染出
    用户无权点击的入口（Requirement 2.6 capability 前置）。
    """
    role = role_of(current_user)
    visible: list[dict[str, Any]] = []
    for action_id in ACTION_IDS:
        spec = spec_for(action_id)
        required = _capability_for_action(action_id)
        # ``None`` = 该 action 无服务端 capability 门槛（前端本地语义动作），
        # 对所有已认证用户可见；有门槛的按角色过滤。
        if required is None or is_permitted(role, required):
            visible.append({
                "actionId": spec.action_id,
                "uiLabel": spec.ui_label,
                "sideEffects": list(spec.side_effects),
                "consumesBinary": spec.consumes_binary,
            })
    return {
        "actions": visible,
        "policyVersion": POLICY_V1.version,
        "legacyMigrationDeadline": LEGACY_MIGRATION_DEADLINE,
    }


def _capability_for_action(action_id: str) -> str | None:
    """action → 所需 capability。

    🔴 返回 ``None`` 表示该 action **无 capability 门槛**（前端/本地动作，如
    批量建空白底稿、维护元数据），而不是"未映射 = 抛错"。

    旧实现只映射 ``INGEST_EXCEL_TEMPLATE`` 并对其余抛 ``ValueError``，导致
    ``GET /actions`` 遍历三条 action 时在第二条上 500 —— **fail-open 变成
    fail-hard**：整个入口发现端点不可用，UI 无法列出任何入口。批量建空白与
    元数据维护是前端本地语义（Requirement 1.1/1.2），不走本服务 capability，
    故显式返回 ``None`` 并在调用方跳过过滤。
    """
    from app.services.custom_template_ingestion.authorization import Capability

    if action_id == INGEST_EXCEL_TEMPLATE:
        return Capability.UPLOAD
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 2) 摄取入口 —— 唯一接收真实字节的链
# ─────────────────────────────────────────────────────────────────────────────


class IngestResponse(BaseModel):
    artifactId: str
    state: str
    displayName: str
    sizeBytes: int
    sha256: str
    policyVersion: str
    actionId: str
    message: str


@router.post("/ingest", response_model=IngestResponse)
async def ingest_excel_template(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """上传 Excel 自定义模板，进入 private quarantine。

    Requirement 1.3：这是**唯一**接收二进制的入口。
    Requirement 3.1：multipart ``UploadFile`` 流式写、流式 SHA-256、
    校验扩展名/MIME/ZIP magic；原文件名只作转义显示值。
    Requirement 3.2：preflight 前不生成 HTML/OO/project/runtime。

    🔴 **不使用** ``TEMP_USER_ID`` 之类硬编码用户：scope 一律由
    ``derive_implicit_scope`` 从认证用户推导（承接 Task 2）。
    """
    role = role_of(current_user)
    from app.services.custom_template_ingestion.authorization import Capability

    if not is_permitted(role, Capability.UPLOAD):
        raise HTTPException(status_code=403, detail=f"角色 {role} 无上传权限")

    quarantine = get_quarantine()
    scope = derive_implicit_scope(user=current_user)
    try:
        artifact = await quarantine.ingest(
            file,
            organization_id=scope.organization_id,
            scope=scope.to_dict(),
        )
    except QuarantineError as exc:
        raise HTTPException(
            status_code=415,
            detail=exc.reason.to_dict(),
        ) from exc

    if artifact.state is not ArtifactState.QUARANTINED:
        raise HTTPException(
            status_code=415,
            detail=artifact.rejection.to_dict() if artifact.rejection else {"code": "REJECTED"},
        )

    return IngestResponse(
        artifactId=artifact.artifact_id,
        state=artifact.state.value,
        displayName=artifact.display_name,
        sizeBytes=artifact.size_bytes,
        sha256=artifact.sha256,
        policyVersion=artifact.policy_version,
        actionId=INGEST_EXCEL_TEMPLATE,
        message=success_message(INGEST_EXCEL_TEMPLATE),
    ).model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# 3) 查询入口 —— 只读回隔离区状态，不暴露 storage 路径
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """查询隔离产物状态。

    🔴 **不返回** storage 绝对路径或枚举列表（Requirement 16.1）。
    需要 raw 字节下载必须走独立 capability 检查（Task 17），此处不提供。
    """
    scope = derive_implicit_scope(user=current_user)
    quarantine = get_quarantine()
    try:
        data = quarantine.load_manifest(scope.organization_id, artifact_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="隔离产物不存在或已过期")
    return {"artifact": data}


@router.get("/quota")
async def get_quota(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """返回组织级隔离区用量与配额，供前端做准入提示。"""
    from app.services.custom_template_ingestion.policy import check_organization_quota

    scope = derive_implicit_scope(user=current_user)
    used = get_quarantine().total_storage_bytes()
    limit = POLICY_V1.organization_storage_bytes
    result = check_organization_quota(
        organization_id=scope.organization_id,
        active_preflights=0,
        storage_used_bytes=used,
        pending_upload_bytes=0,
    )
    return {
        "organizationId": scope.organization_id,
        "usedBytes": used,
        "limitBytes": limit,
        "admitted": result.admitted,
        "policyVersion": POLICY_V1.version,
    }


@router.post("/artifacts/{artifact_id}/preflight")
async def preflight_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """对隔离区 artifact 执行包级 + 语义 preflight，并冻结 preflight digest。

    这是 ingest → preflight 两阶段链的真实 HTTP 接线：

    * 只读取服务端隔离字节，不接受客户端再次上传或传 storage path；
    * `scan_package_bytes` 与 `run_semantic_preflight` 的结果写回 manifest；
    * 结果有效才进入 `PREFLIGHT_READY`，否则进入 `PREFLIGHT_FAILED`；
    * digest 是 canonical JSON 的 SHA-256，后续 authority PUT 必须带同一 digest。

    不生成 HTML / OnlyOffice / WorkingPaper；那是 finalize/instantiate 阶段。
    """
    scope = derive_implicit_scope(user=current_user)
    quarantine = get_quarantine()
    try:
        manifest = quarantine.load_manifest(scope.organization_id, artifact_id)
        if manifest.get("organizationId") != scope.organization_id:
            raise FileNotFoundError(artifact_id)
        if manifest.get("state") != ArtifactState.QUARANTINED.value:
            existing = manifest.get("preflight")
            if existing is not None:
                return {
                    "artifactId": artifact_id,
                    "state": manifest.get("state"),
                    "preflight": existing,
                    "preflightDigest": manifest.get("preflightDigest"),
                }
            raise HTTPException(status_code=409, detail="该隔离产物已完成或正在进行 preflight")
        payload = quarantine.artifact_bytes_path(scope.organization_id, artifact_id).read_bytes()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="隔离产物不存在或不属于当前组织") from exc
    except QuarantineError as exc:
        raise HTTPException(status_code=400, detail=exc.reason.to_dict()) from exc

    from app.services.custom_template_ingestion.package_scanner import scan_package_bytes
    from app.services.custom_template_ingestion.semantic_preflight import run_semantic_preflight

    package = scan_package_bytes(
        payload,
        policy=POLICY_V1,
        filename_hint=manifest.get("displayName"),
    )
    result = run_semantic_preflight(
        payload,
        package=package,
        policy=POLICY_V1,
        filename_hint=manifest.get("displayName"),
    )
    preflight = result.to_dict()
    preflight_digest = hashlib.sha256(
        json.dumps(preflight, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    target_state = (
        ArtifactState.PREFLIGHT_READY if result.is_valid else ArtifactState.PREFLIGHT_FAILED
    )
    updated = quarantine.update_manifest_fields(
        scope.organization_id,
        artifact_id,
        {
            "preflight": preflight,
            "preflightDigest": preflight_digest,
        },
        state=target_state,
    )
    return {
        "artifactId": artifact_id,
        "state": updated["state"],
        "preflight": preflight,
        "preflightDigest": preflight_digest,
    }


class UnitAuthorityRequest(BaseModel):
    """客户端对 preflight 结构做出的 amount-region authority 裁决。"""

    model_config = ConfigDict(extra="forbid")

    workingPaperId: UUID
    workbookSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preflightDigest: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest: dict[str, Any]
    manifestDigest: str = Field(pattern=r"^[0-9a-f]{64}$")


def _canonical_json_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validate_authority_manifest(manifest: dict[str, Any]) -> None:
    """校验 authority manifest 的稳定 amount region 形状，不让自由文本猜单位。"""
    regions = manifest.get("regions")
    if not isinstance(regions, list) or not regions:
        raise HTTPException(status_code=422, detail="manifest.regions 必须是非空数组")
    allowed_kinds = {"amount", "quantity", "count", "ratio", "exchange_rate", "unit_price", "text"}
    allowed_scales = {"fraction", "percent_points"}
    allowed_units = {"yuan", "qian", "wan"}
    seen: set[str] = set()
    for region in regions:
        if not isinstance(region, dict):
            raise HTTPException(status_code=422, detail="manifest.regions 成员必须是对象")
        stable_id = region.get("stable_id") or region.get("stableId")
        kind = region.get("measure_kind") or region.get("measureKind")
        if not isinstance(stable_id, str) or not stable_id or stable_id in seen:
            raise HTTPException(status_code=422, detail="amount region stable_id 必须非空且唯一")
        if kind not in allowed_kinds:
            raise HTTPException(status_code=422, detail=f"未知 measure_kind: {kind}")
        seen.add(stable_id)
        scale = region.get("ratio_scale") or region.get("ratioScale")
        if kind == "ratio" and scale not in allowed_scales:
            raise HTTPException(status_code=422, detail="ratio region 必须声明 fraction 或 percent_points")
        if kind != "ratio" and scale is not None:
            raise HTTPException(status_code=422, detail="非 ratio region 不得声明 ratio_scale")
        if kind == "amount":
            unit = region.get("unit")
            divisor = region.get("divisor")
            if unit not in allowed_units or divisor not in {1, 1000, 10000}:
                raise HTTPException(status_code=422, detail="amount region 的 unit/divisor 无效")


@router.put("/artifacts/{artifact_id}/unit-authority")
async def put_unit_authority(
    artifact_id: str,
    body: UnitAuthorityRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """以 artifact sha + preflight digest 为 CAS，落一份不可变 workbook authority。"""
    from app.models.custom_workbook_unit_authority import CustomWorkbookUnitAuthority
    from app.models.workpaper_models import WorkingPaper

    _validate_authority_manifest(body.manifest)
    scope = derive_implicit_scope(user=current_user)
    quarantine = get_quarantine()
    try:
        artifact = quarantine.load_manifest(scope.organization_id, artifact_id)
    except (FileNotFoundError, QuarantineError) as exc:
        raise HTTPException(status_code=404, detail="隔离产物不存在或不属于当前组织") from exc
    if artifact.get("state") != ArtifactState.PREFLIGHT_READY.value:
        raise HTTPException(status_code=409, detail="artifact 尚未通过 preflight")
    if artifact.get("sha256") != body.workbookSha256:
        raise HTTPException(status_code=409, detail="workbook sha256 与 artifact 不一致")
    if artifact.get("preflightDigest") != body.preflightDigest:
        raise HTTPException(status_code=409, detail="preflight digest 已变化，请重新预检")
    if _canonical_json_digest(body.manifest) != body.manifestDigest:
        raise HTTPException(status_code=409, detail="manifest digest 与请求正文不一致")

    wp = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == body.workingPaperId,
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if wp is None:
        raise HTTPException(status_code=404, detail="目标底稿不存在")
    await assert_project_permission(db, current_user, wp.project_id, "edit")

    existing = (await db.execute(
        sa.select(CustomWorkbookUnitAuthority).where(
            CustomWorkbookUnitAuthority.working_paper_id == body.workingPaperId,
            CustomWorkbookUnitAuthority.workbook_sha256 == body.workbookSha256,
        )
    )).scalar_one_or_none()
    if existing is not None:
        if existing.manifest_digest != body.manifestDigest:
            raise HTTPException(status_code=409, detail="同一 workbook sha256 已有不同 authority")
        return {
            "authorityId": str(existing.id),
            "workingPaperId": str(existing.working_paper_id),
            "workbookSha256": existing.workbook_sha256,
            "manifestDigest": existing.manifest_digest,
            "idempotent": True,
        }

    authority = CustomWorkbookUnitAuthority(
        working_paper_id=body.workingPaperId,
        workbook_sha256=body.workbookSha256,
        manifest=body.manifest,
        manifest_digest=body.manifestDigest,
        created_by=current_user.id,
    )
    db.add(authority)
    await db.flush()
    await db.commit()
    return {
        "authorityId": str(authority.id),
        "workingPaperId": str(authority.working_paper_id),
        "workbookSha256": authority.workbook_sha256,
        "manifestDigest": authority.manifest_digest,
        "idempotent": False,
    }


class FinalizeAuthorityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workingPaperId: UUID
    authorityId: UUID
    manifestDigest: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotencyKey: str = Field(min_length=8, max_length=160)


@router.post("/artifacts/{artifact_id}/finalize")
async def finalize_unit_authority(
    artifact_id: str,
    body: FinalizeAuthorityRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """把已确认 authority 冻结成 finalize handoff；不直接发布或实例化。

    这是 custom 两阶段链的 finalize/publication CAS 边界：
    `PREFLIGHT_READY + authority + manifestDigest` 才能生成 phase=finalized 的
    handoff。该接口**不**把 artifact 标成 ACTIVE，也不创建 WorkingPaper，后续
    publication/instantiate 必须消费此 handoff 并另过状态门。
    """
    from app.models.custom_workbook_unit_authority import CustomWorkbookUnitAuthority
    from app.models.workpaper_models import WorkingPaper

    scope = derive_implicit_scope(user=current_user)
    quarantine = get_quarantine()
    try:
        artifact = quarantine.load_manifest(scope.organization_id, artifact_id)
    except (FileNotFoundError, QuarantineError) as exc:
        raise HTTPException(status_code=404, detail="隔离产物不存在或不属于当前组织") from exc
    if artifact.get("state") != ArtifactState.PREFLIGHT_READY.value:
        raise HTTPException(status_code=409, detail="artifact 尚未通过 preflight")
    if artifact.get("preflightDigest") is None:
        raise HTTPException(status_code=409, detail="artifact 缺少 preflight digest")

    wp = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == body.workingPaperId,
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if wp is None:
        raise HTTPException(status_code=404, detail="目标底稿不存在")
    await assert_project_permission(db, current_user, wp.project_id, "edit")

    authority = (await db.execute(
        sa.select(CustomWorkbookUnitAuthority).where(
            CustomWorkbookUnitAuthority.id == body.authorityId,
            CustomWorkbookUnitAuthority.working_paper_id == body.workingPaperId,
        )
    )).scalar_one_or_none()
    if authority is None:
        raise HTTPException(status_code=404, detail="authority 不存在或不属于目标底稿")
    if authority.workbook_sha256 != artifact.get("sha256"):
        raise HTTPException(status_code=409, detail="authority 与 artifact sha256 不一致")
    if authority.manifest_digest != body.manifestDigest:
        raise HTTPException(status_code=409, detail="authority manifest digest 不一致")

    existing = artifact.get("finalize")
    if existing is not None:
        if (
            existing.get("idempotencyKey") == body.idempotencyKey
            and existing.get("manifestDigest") == body.manifestDigest
        ):
            return {
                "artifactId": artifact_id,
                "phase": "finalized",
                "handoffId": existing["handoffId"],
                "handoffDigest": existing["handoffDigest"],
                "idempotent": True,
                "runtimeDiscoverable": False,
            }
        raise HTTPException(status_code=409, detail="artifact 已有不同 finalize handoff")

    handoff = {
        "phase": "finalized",
        "handoffId": f"handoff-{artifact_id}-{body.authorityId}",
        "artifactId": artifact_id,
        "authorityId": str(body.authorityId),
        "workingPaperId": str(body.workingPaperId),
        "workbookSha256": artifact["sha256"],
        "preflightDigest": artifact["preflightDigest"],
        "manifestDigest": body.manifestDigest,
        "idempotencyKey": body.idempotencyKey,
    }
    handoff_digest = _canonical_json_digest(handoff)
    handoff["handoffDigest"] = handoff_digest
    quarantine.update_manifest_fields(
        scope.organization_id,
        artifact_id,
        {"finalize": handoff},
    )
    return {
        "artifactId": artifact_id,
        "phase": "finalized",
        "handoffId": handoff["handoffId"],
        "handoffDigest": handoff_digest,
        "idempotent": False,
        "runtimeDiscoverable": False,
    }
