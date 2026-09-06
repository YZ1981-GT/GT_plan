"""模板覆盖层 HTTP 端点 —— 解析来源 / 版本 / OnlyOffice 编辑会话 / 上传替换 / 回滚。

spec: excel-template-override-layer-and-onlyoffice-template-editor / Wave 4 Task 16
Requirements: 2.2, 3.1, 3.6, 4.1, 4.2, 4.3, 4.5, 5.3, 5.5

## 本 router 只是薄壳

全部业务判断在 `app.services.wp_template_override` 里 —— 两道门（越界 / 扩展名）、
格式门、写入顺序、版本链、可见性还原。这样无损判据可以直接测服务层（更硬），
router 不重复实现任何规则。

## 写入顺序（服务层 §5 的裁决，这里是它的唯一执行处）

    stage / commit_template_edit_session   # 落盘 versions/
    record_override_version                # INSERT + is_current 转移（flush）
    await db.commit()                      # ← DB 先落定
    activate_staged_override               # 再切 current{ext}

反序会造出「已生效、无台账」：审计师看到改过的模板而系统说不出版本与作者。

## 权限

沿用既有 `require_role`（Requirement 7.6：不新造审批状态机）。模板覆盖是**事务所级**
管理操作，不属某个项目，故不用 `require_project_access`。

## OO 机对机端点不带 Bearer

`contents` 与 `callback` 由 DocServer 直接调用，只能靠 OnlyOffice 的 JWT。它们**不**声明
`get_current_user` 依赖 —— 声明了会恒 401，文档下载/保存全失败。
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.models.template_library_models import TemplateLevel
from app.services import wp_template_override as ovr

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wp-template-overrides", tags=["模板覆盖层"])

#: 允许改模板的角色 —— 与既有管理端点同口径（`require_role(["admin", "manager"])`）。
_MANAGE_ROLES = ["admin", "manager", "partner", "signing_partner"]


# ═══════════════════════════════════════════════════════════════════════════
# 请求 / 响应模型
# ═══════════════════════════════════════════════════════════════════════════


class ResolutionOut(BaseModel):
    """当前解析来源 —— 供 UI 展示（Requirement 5.3：来源取自后端，前端不推断）。"""

    wp_code: str
    origin: str = Field(description="authoritative | override:project|group_custom|firm_default")
    origin_label: str = Field(description="中文来源标签，前端直接显示")
    path_name: str
    extension: str
    sha256: str
    version_id: str | None
    #: 是否可在浏览器内编辑（xlsx；其余走上传替换）
    editable_in_browser: bool
    #: 置灰原因（可编辑时为 None）—— Requirement 5.2 要求说明原因而不是只不可点
    not_editable_reason: str | None


class VersionOut(BaseModel):
    version_id: str
    wp_code: str
    authoritative_stem: str
    scope: str
    scope_label: str
    sha256: str
    is_current: bool
    parent_version_id: str | None
    created_by: str | None
    created_at: str | None


class EditSessionOut(BaseModel):
    session_id: str
    wp_code: str
    scope: str
    #: OnlyOffice DocEditor 的完整 config
    onlyoffice_config: dict[str, Any]


class AffectedProjectOut(BaseModel):
    project_id: str
    workpaper_count: int


class PageSetupChangeOut(BaseModel):
    """一处打印设置（`pageSetup`）业务属性的变化。"""

    sheet_part: str
    attribute: str
    before: str
    after: str


class SaveResultOut(BaseModel):
    version_id: str
    wp_code: str
    scope: str
    origin: str
    sha256: str
    #: 受影响面（Requirement 6.1）：该 wp_code 下**已存在**的底稿数，按项目分组。
    affected_workpapers: list[AffectedProjectOut] = Field(default_factory=list)
    #: 打印设置的业务属性变化（浏览器内编辑路径才有值；上传替换恒空）。
    #:
    #: 空 = 与编辑起点等价。**不是告警**：OO 往返实测 0 项真差异，非空通常意味着
    #: 用户自己改了纸张/缩放/方向。设备绑定属性（`horizontalDpi` 等）已排除，
    #: 故这里不会被 OO 显式写默认 dpi 的行为刷屏。
    page_setup_changes: list[PageSetupChangeOut] = Field(default_factory=list)
    #: 🔴 明确声明本次保存**不**回溯改写已生成底稿（Requirement 6.2）。
    #:
    #: 这个字段不是装饰：调用方看到 `affected_workpapers` 有几百份时，第一反应会是
    #: 「系统是不是要把它们都改一遍」。已生成底稿是审计证据，模板变更不得倒灌 ——
    #: 它们继续用自己的文件，需不需要重做由业务合伙人判断。
    retroactive_rewrite: bool = False


_ORIGIN_LABELS = {
    "authoritative": "权威模板",
    "override:firm_default": "事务所覆盖",
    "override:group_custom": "集团覆盖",
    "override:project": "项目覆盖",
}
_SCOPE_LABELS = {
    "firm_default": "事务所",
    "group_custom": "集团",
    "project": "项目",
}

#: 各不可编辑格式的置灰原因（Requirement 5.2：必须说明原因）。
_NOT_EDITABLE_REASONS = {
    ".xlsm": "含 VBA 宏（vbaProject.bin），OnlyOffice 往返是否保留宏未取证，暂不开放在线编辑",
    ".docx": "Word 模板的在线编辑是另一条路（结构化 SDT），本功能只做 Excel",
    ".doc": "Word 97-2003 二进制格式，非 OOXML",
    ".xls": "Excel 97-2003 二进制格式，非 OOXML",
}


def _resolution_out(res: ovr.TemplateResolution) -> ResolutionOut:
    ext = res.path.suffix.lower()
    editable = ext in ovr.EDITABLE_FORMATS
    return ResolutionOut(
        wp_code=res.wp_code,
        origin=res.origin,
        origin_label=_ORIGIN_LABELS.get(res.origin, res.origin),
        path_name=res.path.name,
        extension=ext,
        sha256=res.sha256,
        version_id=res.version_id,
        editable_in_browser=editable,
        not_editable_reason=None if editable else _NOT_EDITABLE_REASONS.get(
            ext, f"{ext} 不在可在线编辑的格式集合内"
        ),
    )


def _scope_of(raw: str) -> TemplateLevel:
    try:
        return TemplateLevel(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"作用域 {raw!r} 非法，可选：{[s.value for s in ovr.SCOPE_PRIORITY]}",
        ) from exc


def _domain_error_to_http(exc: ovr.TemplateOverrideError) -> HTTPException:
    """域异常 → HTTP。

    🔴 逐类型映射而不是一律 500：调用方要能区分「改扩展名」「换格式」「联系运维」。
    error_code 一并下发，前端据它给出可操作的提示。
    """
    status = {
        "template_override_extension_mismatch": 400,
        "template_override_format_not_editable": 400,
        "template_override_scope_unknown": 400,
        "template_override_root_escape": 400,
        "template_override_current_version_ambiguous": 500,
    }.get(getattr(exc, "error_code", ""), 400)
    return HTTPException(
        status_code=status,
        detail={"error_code": getattr(exc, "error_code", "template_override_error"),
                "message": str(exc)},
    )


# ═══════════════════════════════════════════════════════════════════════════
# 只读：解析来源与版本
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/{wp_code}/resolution", response_model=ResolutionOut)
async def get_template_resolution(
    wp_code: str,
    project_id: UUID | None = Query(default=None),
    group_id: UUID | None = Query(default=None),
    _user: User = Depends(get_current_user),
) -> ResolutionOut:
    """当前生效的模板来自哪一层（Requirement 2.2 / 5.3）。"""
    try:
        res = ovr.resolve_template_any(wp_code, project_id=project_id, group_id=group_id)
    except ovr.TemplateOverrideError as exc:
        raise _domain_error_to_http(exc) from exc
    if res is None:
        raise HTTPException(status_code=404, detail=f"{wp_code} 在模板库里没有对应模板")
    return _resolution_out(res)


@router.get("/{wp_code}/versions", response_model=list[VersionOut])
async def list_versions(
    wp_code: str,
    scope: str = Query(default=TemplateLevel.firm_default.value),
    project_id: UUID | None = Query(default=None),
    group_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[VersionOut]:
    """某作用域下的全部版本，新的在前。非当前版本仍可读（Requirement 4.2）。"""
    from app.services.wp_template_finder import find_template_file_any_unresolved

    authoritative = find_template_file_any_unresolved(wp_code)
    if authoritative is None:
        raise HTTPException(status_code=404, detail=f"{wp_code} 在模板库里没有对应模板")

    try:
        rows = await ovr.list_override_versions(
            db, wp_code, authoritative.stem, _scope_of(scope),
            project_id=project_id, group_id=group_id,
        )
    except ovr.TemplateOverrideError as exc:
        raise _domain_error_to_http(exc) from exc

    return [
        VersionOut(
            version_id=str(r["id"]),
            wp_code=r["wp_code"],
            authoritative_stem=r["authoritative_stem"],
            scope=r["scope"],
            scope_label=_SCOPE_LABELS.get(r["scope"], r["scope"]),
            sha256=r["sha256"],
            is_current=bool(r["is_current"]),
            parent_version_id=str(r["parent_version_id"]) if r["parent_version_id"] else None,
            created_by=str(r["created_by"]) if r["created_by"] else None,
            created_at=r["created_at"].isoformat() if r.get("created_at") else None,
        )
        for r in rows
    ]


# ═══════════════════════════════════════════════════════════════════════════
# OnlyOffice 编辑会话
# ═══════════════════════════════════════════════════════════════════════════


def _sign_oo_jwt(payload: dict) -> str:
    """用 OnlyOffice JWT secret 签名（无 secret 时返回空串，dev 直通）。"""
    if not settings.ONLYOFFICE_JWT_SECRET:
        return ""
    from jose import jwt

    return jwt.encode(payload, settings.ONLYOFFICE_JWT_SECRET, algorithm="HS256")


def _sign_session_token(session_id: str, ttl_seconds: int = 900) -> str:
    """机对机端点的短时效令牌。"""
    if not settings.ONLYOFFICE_JWT_SECRET:
        return ""
    from jose import jwt

    return jwt.encode(
        {"sid": session_id, "scope": "template_override_session",
         "exp": int(time.time()) + ttl_seconds},
        settings.ONLYOFFICE_JWT_SECRET,
        algorithm="HS256",
    )


def _verify_session_token(session_id: str, token: str | None) -> bool:
    """校验机对机令牌。无 secret（dev）时直通。"""
    if not settings.ONLYOFFICE_JWT_SECRET:
        return True
    if not token:
        return False
    from jose import JWTError, jwt

    try:
        claims = jwt.decode(token, settings.ONLYOFFICE_JWT_SECRET, algorithms=["HS256"])
    except JWTError as exc:
        logger.warning("模板会话令牌校验失败 sid=%s: %s", session_id, exc)
        return False
    return (
        claims.get("sid") == session_id
        and claims.get("scope") == "template_override_session"
    )


@router.post("/{wp_code}/edit-session", response_model=EditSessionOut)
async def create_edit_session(
    wp_code: str,
    request: Request,
    scope: str = Query(default=TemplateLevel.firm_default.value),
    project_id: UUID | None = Query(default=None),
    group_id: UUID | None = Query(default=None),
    current_user: User = Depends(require_role(_MANAGE_ROLES)),
) -> EditSessionOut:
    """建立 OnlyOffice 模板编辑会话（整本模式）。

    🔴 `whole_workbook` 语义：**不加 `actionLink`**，OO 打开整本并原生显示全部 sheet tab。
    加了 actionLink 会把 OO 定位到某个 sheet 的书签上，审计师就看不到 sheet 间关系了
    （Property 10 断言响应里不含 actionLink）。
    """
    session_id = uuid.uuid4().hex
    try:
        session = ovr.prepare_template_edit_session(
            wp_code, _scope_of(scope), session_id=session_id,
            project_id=project_id, group_id=group_id,
            require_editable_format=True,
        )
        ovr.save_session_manifest(session)
    except ovr.TemplateOverrideError as exc:
        raise _domain_error_to_http(exc) from exc

    base_url = settings.ONLYOFFICE_CALLBACK_BASE or str(request.base_url).rstrip("/")
    token = _sign_session_token(session_id)
    suffix = "" if not token else f"?token={token}"
    download_url = f"{base_url}/api/wp-template-overrides/edit-sessions/{session_id}/contents{suffix}"
    callback_url = f"{base_url}/api/wp-template-overrides/edit-sessions/{session_id}/callback{suffix}"

    document = {
        "fileType": session.working_path.suffix.lstrip("."),
        "key": f"tplovr-{session_id}",
        "title": session.working_path.name,
        "url": download_url,
        "permissions": {"edit": True, "download": True, "print": True},
    }
    editor_config = {
        "callbackUrl": callback_url,
        "lang": "zh-CN",
        "mode": "edit",
        # `User` 只有 username（无 full_name / display_name，实测 core.User 的列集合）
        "user": {"id": str(current_user.id), "name": current_user.username},
        "customization": {"autosave": False, "forcesave": True},
        # 🔴 刻意**不放** actionLink —— 整本模式（Property 10）
    }
    config: dict[str, Any] = {
        "documentType": "cell",
        "document": document,
        "editorConfig": editor_config,
        "height": "100%",
        "width": "100%",
    }
    signed = _sign_oo_jwt(config)
    if signed:
        config["token"] = signed

    return EditSessionOut(
        session_id=session_id, wp_code=wp_code, scope=session.scope.value,
        onlyoffice_config=config,
    )


@router.get("/edit-sessions/{session_id}/contents")
async def get_session_contents(
    session_id: str,
    token: str | None = Query(default=None),
):
    """DocServer 拉取工作副本。**机对机，不带 Bearer。**"""
    if not _verify_session_token(session_id, token):
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        session = ovr.load_session_manifest(session_id)
    except ovr.TemplateOverrideError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not session.working_path.is_file():
        raise HTTPException(status_code=404, detail="工作副本不存在")
    return FileResponse(
        path=str(session.working_path),
        filename=session.working_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/edit-sessions/{session_id}/callback")
async def session_callback(
    session_id: str,
    request: Request,
    token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """OnlyOffice 保存回调 —— 把编辑结果落成新的覆盖版本。

    OO 的 `status`：2 = 编辑结束需保存，6 = forcesave。其余状态不落盘。
    """
    if not _verify_session_token(session_id, token):
        raise HTTPException(status_code=404, detail="Not Found")

    body = await request.json()
    status = int(body.get("status", 0))
    if status not in (2, 6):
        return {"error": 0}

    download_url = body.get("url")
    if not download_url:
        logger.error("模板会话 callback 缺 url sid=%s status=%s", session_id, status)
        return {"error": 1}

    try:
        session = ovr.load_session_manifest(session_id)
    except ovr.TemplateOverrideError as exc:
        logger.error("模板会话 callback 找不到会话 sid=%s: %s", session_id, exc)
        return {"error": 1}

    # 从 DocServer 取回编辑后的字节，写进工作副本（逐字节，不经任何 xlsx 库）
    import httpx

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(download_url)
            resp.raise_for_status()
            edited = resp.content
    except Exception as exc:  # noqa: BLE001 —— 网络失败必须记 ERROR 并让 OO 重试
        logger.error("模板会话拉取编辑结果失败 sid=%s: %s", session_id, exc)
        return {"error": 1}

    session.working_path.write_bytes(edited)

    version_id = str(uuid.uuid4())
    try:
        staged = ovr.commit_template_edit_session(session, version_id=version_id)
        await ovr.record_override_version(
            db, staged, project_id=session.project_id, group_id=session.group_id,
        )
        await db.commit()                       # ← DB 先落定
        ovr.activate_staged_override(staged)    # 再切 current
    except ovr.TemplateOverrideError as exc:
        await db.rollback()
        logger.error("模板覆盖落盘失败 sid=%s: %s", session_id, exc)
        return {"error": 1}

    ovr.discard_template_edit_session(session_id)
    # OO 的 callback 响应格式是固定的 `{"error": N}`，塞不进受影响面 ⇒ 记 log。
    # 前端在编辑器关闭后重新拉 `/resolution`，需要受影响面时走 upload 那条响应或单独查询。
    try:
        affected = await ovr.count_affected_workpapers(db, staged.wp_code)
    except Exception as exc:  # noqa: BLE001 —— 统计失败不该让已成功的保存变成 error
        logger.warning("受影响面统计失败 wp_code=%s: %s", staged.wp_code, exc)
        affected = []
    logger.info(
        "模板覆盖已保存 wp_code=%s scope=%s version=%s sha256=%s 受影响底稿=%s"
        "（不回溯改写）打印设置变化=%s",
        staged.wp_code, staged.scope.value, version_id, staged.sha256[:12],
        sum(a["workpaper_count"] for a in affected),
        len(staged.page_setup_changes),
    )
    # 打印设置的业务属性差异逐条记 WARNING —— callback 响应体是 OO 固定的 `{"error": N}`，
    # 塞不进结构化结果。**实测 OO 往返为 0 条**，故这里一旦有输出就值得看一眼：
    # 要么用户真改了纸张/方向（正常），要么 OO 换版本后行为变了（需复核）。
    for change in staged.page_setup_changes:
        logger.warning(
            "打印设置变化 wp_code=%s %s %s: %r → %r",
            staged.wp_code, change.sheet_part, change.attribute,
            change.before, change.after,
        )
    return {"error": 0}


# ═══════════════════════════════════════════════════════════════════════════
# 上传替换 / 回滚 / 删除
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/{wp_code}/upload", response_model=SaveResultOut)
async def upload_replacement(
    wp_code: str,
    file: UploadFile = File(...),
    scope: str = Query(default=TemplateLevel.firm_default.value),
    project_id: UUID | None = Query(default=None),
    group_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(_MANAGE_ROLES)),
) -> SaveResultOut:
    """上传替换 —— 给 127 份不可在线编辑的模板同样的覆盖能力（AC 5.5）。

    🔴 走与在线编辑**同一条** `stage_override` + 版本表路径，只是
    `require_editable_format=False`（覆盖层格式无关，476/476 都可覆盖）。
    **不得**另开一条绕过越界门与扩展名门的通道。
    """
    from app.services.wp_template_finder import find_template_file_any_unresolved

    authoritative = find_template_file_any_unresolved(wp_code)
    if authoritative is None:
        raise HTTPException(status_code=404, detail=f"{wp_code} 在模板库里没有对应模板")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="上传内容为空")

    # 比对基线 = **被替换的那份**（当前解析结果，可能是上一层覆盖也可能是权威文件）。
    # 🔴 在 stage_override 之前取：落盘后 current 已被换掉，再读就是拿新的比新的。
    baseline_before_replace: bytes | None = None
    if Path(authoritative.name).suffix.lower() in {".xlsx", ".xlsm"}:
        existing = ovr.resolve_template_any(
            wp_code, project_id=project_id, group_id=group_id
        )
        if existing is not None and existing.path.is_file():
            baseline_before_replace = existing.path.read_bytes()

    version_id = str(uuid.uuid4())
    try:
        staged = ovr.stage_override(
            wp_code, authoritative, _scope_of(scope), payload,
            version_id=version_id,
            source_extension=Path(file.filename or "").suffix,
            project_id=project_id, group_id=group_id,
            require_editable_format=False,
        )
        if baseline_before_replace is not None:
            staged = ovr.attach_page_setup_changes(
                staged, baseline_before_replace, payload, label=wp_code
            )
        await ovr.record_override_version(
            db, staged, project_id=project_id, group_id=group_id,
            created_by=current_user.id,
        )
        # 受影响面在 commit **之前**算 —— 它统计的是「用旧模板生成的底稿」，
        # 与本次覆盖是否落定无关；放到 commit 之后算会多一次往返且数字相同。
        affected = await ovr.count_affected_workpapers(db, wp_code)
        await db.commit()
        ovr.activate_staged_override(staged)
    except ovr.TemplateOverrideError as exc:
        await db.rollback()
        raise _domain_error_to_http(exc) from exc

    return SaveResultOut(
        version_id=version_id, wp_code=wp_code, scope=staged.scope.value,
        origin=f"override:{staged.scope.value}", sha256=staged.sha256,
        affected_workpapers=[AffectedProjectOut(**a) for a in affected],
        retroactive_rewrite=False,
        page_setup_changes=[
            PageSetupChangeOut(**c.as_dict()) for c in staged.page_setup_changes
        ],
    )


@router.post("/{wp_code}/versions/{version_id}/promote", response_model=SaveResultOut)
async def promote_version(
    wp_code: str,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(_MANAGE_ROLES)),
) -> SaveResultOut:
    """回滚 —— 把某个历史版本置为当前，不删任何版本记录（Requirement 4.3）。"""
    try:
        row = await ovr.promote_override_version(db, version_id)
        if row["wp_code"] != wp_code:
            raise HTTPException(
                status_code=400,
                detail=f"版本 {version_id} 属于 {row['wp_code']}，与路径上的 {wp_code} 不符",
            )
        await db.commit()

        # DB 落定后切 current 投影（写入顺序裁决）
        current = ovr.OVERRIDE_ROOT / row["file_relpath"]
        target_dir = current.parent.parent  # versions/ 的上一级
        marker_name = f"{ovr.CURRENT_STEM}{row['extension']}"
        ovr.assert_target_within_override_root(target_dir / marker_name)
        staged = ovr.StagedOverride(
            version_id=str(version_id),
            wp_code=row["wp_code"],
            authoritative_stem=row["authoritative_stem"],
            scope=TemplateLevel(row["scope"]),
            extension=row["extension"],
            staged_path=current,
            relpath=row["file_relpath"],
            sha256=row["sha256"],
            current_path=target_dir / marker_name,
        )
        ovr.activate_staged_override(staged)
    except ovr.TemplateOverrideError as exc:
        await db.rollback()
        raise _domain_error_to_http(exc) from exc

    return SaveResultOut(
        version_id=str(version_id), wp_code=wp_code, scope=row["scope"],
        origin=f"override:{row['scope']}", sha256=row["sha256"],
    )


@router.delete("/{wp_code}/current")
async def delete_current_override(
    wp_code: str,
    scope: str = Query(default=TemplateLevel.firm_default.value),
    project_id: UUID | None = Query(default=None),
    group_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(_MANAGE_ROLES)),
) -> dict[str, Any]:
    """删除覆盖 —— 该作用域下不再有当前版本，解析回落下一层（Requirement 4.5）。

    **不删版本记录**（V154 有 BEFORE DELETE 触发器兜底），历史仍可回滚。
    """
    from app.services.wp_template_finder import find_template_file_any_unresolved

    authoritative = find_template_file_any_unresolved(wp_code)
    if authoritative is None:
        raise HTTPException(status_code=404, detail=f"{wp_code} 在模板库里没有对应模板")

    level = _scope_of(scope)
    try:
        cleared = await ovr.clear_current_override(
            db, wp_code, authoritative.stem, level,
            project_id=project_id, group_id=group_id,
        )
        await db.commit()
        removed = ovr.deactivate_override(
            wp_code, authoritative, level, project_id=project_id, group_id=group_id,
        )
    except ovr.TemplateOverrideError as exc:
        await db.rollback()
        raise _domain_error_to_http(exc) from exc

    res = ovr.resolve_template_any(wp_code, project_id=project_id, group_id=group_id)
    return {
        "cleared_versions": cleared,
        "removed_projection": removed,
        "now_resolving_to": res.origin if res else None,
    }
