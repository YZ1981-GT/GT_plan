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

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.deps import get_current_user
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
