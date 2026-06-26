"""底稿 Sheet 级 OnlyOffice WOPI 路由

提供非白名单 sheet（函证检查表/替代程序表等）的 OnlyOffice 编辑集成：
- GET  /api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-config  — 编辑器配置（doc_key + JWT）
- GET  /api/workpapers/{wp_id}/sheets/{sheet_name}/wopi/contents      — WOPI GetFile（xlsx 文件内容）

设计参考：.kiro/specs/d0-onlyoffice-migration/design.md §1.2
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.config import settings
from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.workpaper_models import WpIndex, WorkingPaper

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["working-papers"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _onlyoffice_storage_dir(project_id: UUID) -> Path:
    """项目级 OnlyOffice 编辑文件存储目录"""
    root = Path(settings.STORAGE_ROOT)
    return root / "projects" / str(project_id) / "workpapers" / "onlyoffice"


async def _load_wp_or_404(db: AsyncSession, wp_id: UUID) -> tuple[WorkingPaper, str]:
    """查询底稿 + wp_code，并执行项目软删守卫。三端点统一入口。

    - 校验 WorkingPaper.is_deleted == False
    - 校验 projects.is_deleted == False（复用 render-config Step1.5 同款裸 SQL）
    - 返回 (wp, wp_code)
    """
    result = await db.execute(
        sa.select(WorkingPaper, WpIndex.wp_code)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(
            WorkingPaper.id == wp_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    wp, wp_code = row[0], row[1]

    # 项目软删守卫（复用 render-config Step1.5 同款裸 SQL）
    proj_deleted = (
        await db.execute(
            sa.text("SELECT is_deleted FROM projects WHERE id = :pid"),
            {"pid": str(wp.project_id)},
        )
    ).scalar()
    if proj_deleted:
        raise HTTPException(status_code=404, detail="项目已删除")

    return wp, wp_code


def _resolve_wp_file(
    project_id: UUID,
    wp_code: str,
    template_path: Path | None,
) -> Path:
    """解析 wp_code 对应的单一共享文件（不再 per-sheet 复制）。

    按 {wp_code}.{ext} 命名单一文件，扩展名取自模板实际类型。
    同一 wp_code 的多个 sheet 共享此文件。
    首次从模板整本复制一次，后续复用。
    """
    storage_dir = _onlyoffice_storage_dir(project_id)

    # 确定文件扩展名：优先从模板取实际后缀，回退 xlsx
    ext = template_path.suffix.lower() if template_path else ".xlsx"
    if not ext:
        ext = ".xlsx"
    file_name = f"{wp_code}{ext}"           # single file per wp_code, 保留原始扩展名
    target = storage_dir / file_name

    if target.exists():
        return target

    # 兼容旧格式：检查是否存在旧的 .xlsx 命名（从 .xlsx 硬编码时代遗留）
    legacy_target = storage_dir / f"{wp_code}.xlsx"
    if legacy_target.exists() and ext != ".xlsx":
        # 旧文件存在但扩展名不对 → 重命名为正确扩展名
        legacy_target.rename(target)
        return target

    if template_path and template_path.exists():
        storage_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_path, target)
        return target
    raise FileNotFoundError(f"OnlyOffice 文件不存在且无模板可复制: {file_name}")


def _generate_doc_key(file_path: Path, wp_code: str) -> str:
    """doc_key = hash(wp_code + mtime_ns)。同 wp_code 所有 sheet 共享同一 key。"""
    stat = file_path.stat()
    raw = f"{wp_code}:{stat.st_mtime_ns}"
    return hashlib.md5(raw.encode()).hexdigest()


def _rewrite_onlyoffice_download_url(url: str) -> str:
    """重写 OnlyOffice callback 下载 URL 的 scheme+host 为后端可达的 ONLYOFFICE_URL。

    OnlyOffice 容器在 status=2/6 callback 里返回的 ``url`` 使用其自身视角地址
    （容器内 ``http://localhost/cache/...`` 指向容器 80 端口，或用容器 hostname），
    宿主机后端无法访问 → 下载失败 → 前端弹"无法保存文档"。

    将 url 的 scheme+netloc 替换为 ``settings.ONLYOFFICE_URL`` 的 scheme+netloc
    （如 ``http://localhost:8080``，宿主机可达），保留 path/query 不变。
    ONLYOFFICE_URL 未配置时原样返回（不破坏 Docker 内部署场景）。
    """
    from urllib.parse import urlsplit, urlunsplit

    base = settings.ONLYOFFICE_URL
    if not base:
        return url
    try:
        base_parts = urlsplit(base)
        url_parts = urlsplit(url)
        if not base_parts.netloc:
            return url
        # 已经是同一 host:port 则无需重写
        if url_parts.netloc == base_parts.netloc:
            return url
        return urlunsplit((
            base_parts.scheme or url_parts.scheme,
            base_parts.netloc,
            url_parts.path,
            url_parts.query,
            url_parts.fragment,
        ))
    except Exception:
        return url


def _sign_jwt(payload: dict) -> str:
    """使用 OnlyOffice JWT secret 签名"""
    if not settings.ONLYOFFICE_JWT_SECRET:
        return ""
    return jwt.encode(payload, settings.ONLYOFFICE_JWT_SECRET, algorithm="HS256")


def _sign_wopi_token(wp_id: UUID, wp_code: str, ttl_seconds: int = 300) -> str:
    """为 WOPI download_url 生成短时效签名 token。

    嵌入 download_url 的 ?token= 参数，确保即使容器不附带 outbox JWT，
    WOPI 端点也能校验请求合法性。TTL 默认 5 分钟（编辑器打开后立即下载）。
    """
    import time

    if not settings.ONLYOFFICE_JWT_SECRET:
        return ""
    payload = {
        "sub": "wopi",
        "wp_id": str(wp_id),
        "wp_code": wp_code,
        "exp": int(time.time()) + ttl_seconds,
    }
    return jwt.encode(payload, settings.ONLYOFFICE_JWT_SECRET, algorithm="HS256")


# ---------------------------------------------------------------------------
# GET /api/workpapers/onlyoffice/health
# (静态路径，必须注册在 /{wp_id} 动态通配之前)
# ---------------------------------------------------------------------------


@router.get("/onlyoffice/health")
async def get_onlyoffice_health(db: AsyncSession = Depends(get_db)):
    """底稿模块 OnlyOffice 健康预检。

    复用交付模块已有 health_check（不重复实现），返回健康状态 + 活跃席位 + 席位上限。
    前端 GtOnlyOfficeSheet mounted 时主动调用，不健康直接降级（不加载 api.js）。
    无需用户鉴权（状态端点）。
    """
    from app.services.onlyoffice_callback_service import OnlyOfficeCallbackService
    from app.services.onlyoffice_session_limiter import get_active_count, MAX_SESSIONS

    try:
        svc = OnlyOfficeCallbackService(db)
        healthy = await svc.health_check()
    except Exception:
        healthy = False

    try:
        active = await get_active_count()
    except Exception:
        active = 0

    return {
        "healthy": healthy,
        "active_sessions": active,
        "max_sessions": MAX_SESSIONS,
    }


# ---------------------------------------------------------------------------
# GET /api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-config
# ---------------------------------------------------------------------------


@router.get("/{wp_id}/sheets/{sheet_name}/onlyoffice-config")
async def get_sheet_onlyoffice_config(
    wp_id: UUID,
    sheet_name: str,
    request: Request,
    whole_workbook: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """返回 OnlyOffice 编辑器配置（doc_key / download_url / callback_url / JWT token）

    前端 GtOnlyOfficeSheet 组件调用此端点获取配置后创建 DocEditor iframe。

    whole_workbook=True（完整Excel 页签）：不加 actionLink，OnlyOffice 打开整本 xlsx
    原生显示全部 sheet tab，供组员直接编辑。
    """
    # 1. 查询底稿 + wp_code + 项目软删守卫
    wp, wp_code = await _load_wp_or_404(db, wp_id)
    project_id = wp.project_id

    # 2. OnlyOffice 可用性检查
    if not settings.ONLYOFFICE_URL:
        raise HTTPException(status_code=503, detail="OnlyOffice 未配置")

    # 3. 解析文件路径（项目存储优先 → 回退模板）
    from app.services.wp_template_finder import find_template_file_any

    template_path = find_template_file_any(wp_code)
    try:
        file_path = _resolve_wp_file(project_id, wp_code, template_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # 4. 生成 doc_key
    doc_key = _generate_doc_key(file_path, wp_code)

    # 5. 构建 URL（download_url 嵌短时效签名 token，确保 WOPI 鉴权不依赖容器 outbox JWT）
    base_url = settings.ONLYOFFICE_CALLBACK_BASE or str(request.base_url).rstrip("/")
    wopi_token = _sign_wopi_token(wp_id, wp_code)
    download_url = (
        f"{base_url}/api/workpapers/{wp_id}/sheets/{sheet_name}/wopi/contents"
    )
    if wopi_token:
        download_url += f"?token={wopi_token}"
    callback_url = (
        f"{base_url}/api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-callback"
    )

    # 6. 判断编辑模式
    from app.models.workpaper_models import WpFileStatus

    mode = "edit"
    if wp.status in (
        WpFileStatus.review_passed,
        WpFileStatus.archived,
    ):
        mode = "view"

    # 6.5 席位接入：仅 edit 模式占席位；view（只读）不占
    if mode == "edit":
        from app.services.onlyoffice_session_limiter import acquire_session

        ok = await acquire_session(current_user.id, doc_key)
        if not ok:
            raise HTTPException(
                status_code=429,
                detail="当前编辑人数已满，请稍后再试",
            )

    # 7. 根据实际文件扩展名确定 fileType / documentType
    from pathlib import Path as _Path

    _ext = _Path(file_path).suffix.lower().lstrip(".")
    if _ext in ("doc", "docx", "odt", "rtf"):
        file_type = _ext if _ext == "docx" else "docx"
        document_type = "word"
    elif _ext in ("ppt", "pptx", "odp"):
        file_type = _ext if _ext == "pptx" else "pptx"
        document_type = "slide"
    else:
        file_type = "xlsx"
        document_type = "cell"

    # 8. 构建 OnlyOffice config
    config = {
        "document": {
            "fileType": file_type,
            "key": doc_key,
            "title": f"{wp_code}_{sheet_name}.{file_type}",
            "url": download_url,
            "permissions": {
                "edit": mode == "edit",
                "download": True,
                "print": True,
            },
        },
        "documentType": document_type,
        "editorConfig": {
            "mode": mode,
            "lang": "zh-CN",
            "callbackUrl": callback_url,
            **(
                {}
                if whole_workbook or document_type != "cell"
                else {"actionLink": {"action": {"type": "bookmark", "data": sheet_name}}}
            ),
            "user": {
                "id": str(current_user.id),
                "name": current_user.username,
            },
            "customization": {
                "forcesave": True,
                "compactHeader": True,
                # 紧凑工具栏：ribbon 默认折叠为单行，给单元格区腾空间。
                # 用户仍可双击选项卡展开。toolbar:true 保留选项卡可用。
                "compactToolbar": True,
                "toolbar": True,
            },
        },
        "type": "desktop",
    }

    # 9. JWT 签名
    token = _sign_jwt(config)

    return {
        "config": config,
        "token": token,
        "mode": mode,
        "documentType": document_type,
        "onlyoffice_url": settings.ONLYOFFICE_URL,
    }


# ---------------------------------------------------------------------------
# GET /api/workpapers/{wp_id}/sheets/{sheet_name}/wopi/contents
# ---------------------------------------------------------------------------


@router.get("/{wp_id}/sheets/{sheet_name}/wopi/contents")
async def get_sheet_wopi_contents(
    wp_id: UUID,
    sheet_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """WOPI GetFile — JWT 鉴权后返回 xlsx 内容。

    安全模型修正：不再依赖"doc_key 不可预测性"（端点从不校验它）。
    改为校验 OnlyOffice 下载请求所带 JWT（Authorization header 或 ?token= 查询参数）。
    """
    # 1. JWT 鉴权
    if not _verify_wopi_jwt(request):
        raise HTTPException(status_code=403, detail="WOPI 请求未授权")

    # 2. 查询底稿 + 项目软删守卫
    wp, wp_code = await _load_wp_or_404(db, wp_id)
    project_id = wp.project_id

    # 解析文件路径
    from app.services.wp_template_finder import find_template_file_any

    template_path = find_template_file_any(wp_code)
    try:
        file_path = _resolve_wp_file(project_id, wp_code, template_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(
        path=str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=file_path.name,
    )


# ---------------------------------------------------------------------------
# POST /api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-callback
# ---------------------------------------------------------------------------

# OnlyOffice callback status codes that require file download
_SAVE_STATUSES = {2, 6}  # 2=ready to save, 6=force save
# OnlyOffice callback status codes that indicate session close (release seat)
_RELEASE_STATUSES = {3, 4, 7}  # 3=save error close, 4=close no change, 7=force save error


def _extract_user_id_from_callback(body: dict) -> str | None:
    """从 OO callback body 提取 userid。

    actions[].userid 优先（含 type=0 断开/type=1 连接），回退 users[0]。
    返回 None 时跳过席位释放，依赖 TTL 兜底。
    """
    actions = body.get("actions") or []
    for a in actions:
        uid = a.get("userid")
        if uid:
            return str(uid)
    users = body.get("users") or []
    if users:
        return str(users[0])
    return None


def _verify_wopi_jwt(request: Request) -> bool:
    """校验 WOPI GetFile 请求 JWT。

    OnlyOffice 对 document.url 的下载请求带 JWT（header 或 token 查询参数）。
    无 JWT_SECRET 配置（测试环境）→ 直通。
    """
    if not settings.ONLYOFFICE_JWT_SECRET:
        return True
    token = request.headers.get("Authorization") or request.query_params.get("token")
    if not token:
        logger.warning("WOPI GetFile 缺少 JWT, wp_id 越权下载风险")
        return False
    try:
        if token.lower().startswith("bearer "):
            token = token[7:]
        jwt.decode(token, settings.ONLYOFFICE_JWT_SECRET, algorithms=["HS256"])
        return True
    except JWTError as exc:
        logger.warning("WOPI GetFile JWT 校验失败: %s", exc)
        return False


def _verify_callback_jwt(request: Request) -> bool:
    """校验 OnlyOffice callback 请求的 JWT 签名。

    无 JWT_SECRET 配置时跳过验证（测试环境直通）。
    """
    if not settings.ONLYOFFICE_JWT_SECRET:
        return True

    token = request.headers.get("Authorization")
    if not token:
        logger.warning("OnlyOffice callback 缺少 Authorization header")
        return False

    try:
        if token.lower().startswith("bearer "):
            token = token[7:]
        jwt.decode(
            token,
            settings.ONLYOFFICE_JWT_SECRET,
            algorithms=["HS256"],
        )
        return True
    except JWTError as exc:
        logger.warning("OnlyOffice callback JWT 校验失败: %s", exc)
        return False


@router.post("/{wp_id}/sheets/{sheet_name}/onlyoffice-callback")
async def post_sheet_onlyoffice_callback(
    wp_id: UUID,
    sheet_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """OnlyOffice 编辑回调端点。

    OnlyOffice 容器在文档保存/关闭时 POST 此端点：
    - status=1: 用户正在编辑（无操作）
    - status=2: 文档准备保存（下载编辑后文件并覆盖存储）
    - status=3: 保存出错（无操作）
    - status=4: 关闭无修改（无操作）
    - status=6: 强制保存（同 status=2）
    - status=7: 强制保存出错（无操作）

    注意：此端点不做用户鉴权（由 OnlyOffice 容器内部调用），
    安全性由 JWT 签名验证 + 内网隔离保障。
    必须始终返回 {"error": 0} 确认收到（OnlyOffice 协议要求）。
    """
    # 1. JWT 验证（若配置了 secret）
    if not _verify_callback_jwt(request):
        logger.warning(
            "OnlyOffice callback JWT 校验失败 wp_id=%s sheet=%s",
            wp_id,
            sheet_name,
        )
        # OnlyOffice 协议要求返回 error 非 0 表示拒绝
        return {"error": 1}

    # 2. 解析 body
    body = await request.json()
    status = body.get("status")
    doc_key = body.get("key")
    user_id = _extract_user_id_from_callback(body)

    # 3. status=2/6: 保存 — 下载写回后释放席位
    if status in _SAVE_STATUSES:
        url = body.get("url")
        if not url:
            logger.warning(
                "OnlyOffice callback status=%s 但缺少 url, wp_id=%s sheet=%s",
                status,
                wp_id,
                sheet_name,
            )
            return {"error": 1}

        # 重写下载 URL 的 host:port 为后端可达的 ONLYOFFICE_URL。
        # OnlyOffice 容器在 callback 里给出的 url 用其自身视角的地址
        # （容器内 http://localhost/cache/... = 容器 80 端口 / 或容器 hostname），
        # host 上的后端访问不到 → 下载失败 → "无法保存文档"。
        # 将其 scheme+netloc 替换为 ONLYOFFICE_URL（host 可达，如 localhost:8080）。
        url = _rewrite_onlyoffice_download_url(url)

        # 查询底稿 + 项目软删守卫
        wp, wp_code = await _load_wp_or_404(db, wp_id)
        project_id = wp.project_id

        # 下载编辑后文件
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                file_bytes = resp.content
        except Exception as exc:
            logger.error(
                "OnlyOffice callback: 下载编辑后文件失败 url=%s error=%s",
                url,
                exc,
            )
            return {"error": 1}

        # 覆盖写入项目存储
        # 判断是否为 word-template（docx）底稿
        from app.services.wp_classification_service import _WP_CODE_OVERRIDE

        component_type = _WP_CODE_OVERRIDE.get(wp_code)
        is_word_template = component_type == "word-template"

        if is_word_template:
            # word-template: 保存到 storage/{project_id}/workpapers/{wp_code}.docx
            target = Path(f"storage/{project_id}/workpapers/{wp_code}.docx")
        else:
            # xlsx: 保存到原有 OnlyOffice 存储目录
            storage_dir = _onlyoffice_storage_dir(project_id)
            target = storage_dir / f"{wp_code}.xlsx"

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(file_bytes)
            logger.info(
                "OnlyOffice callback: 文件已保存 wp_id=%s sheet=%s path=%s size=%d",
                wp_id,
                sheet_name,
                target,
                len(file_bytes),
            )
        except Exception as exc:
            logger.error(
                "OnlyOffice callback: 文件写入失败 path=%s error=%s",
                target,
                exc,
            )
            return {"error": 1}

        # 更新 workpaper.updated_at（last_modified）
        from datetime import datetime, timezone

        try:
            wp.updated_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception as exc:
            logger.warning(
                "OnlyOffice callback: 更新 updated_at 失败 wp_id=%s error=%s",
                wp_id,
                exc,
            )
            # 文件已写入成功，updated_at 更新失败不阻塞

        # 写回成功后释放席位
        if user_id and doc_key:
            from app.services.onlyoffice_session_limiter import release_session

            await release_session(user_id, doc_key)

        # 统一后处理 — orchestrator 负责 file_version++, prefill_stale, audit log, event_bus
        try:
            from app.services.workpaper_save_orchestrator import orchestrator as save_orchestrator

            # 创建虚拟 user 对象（callback 来自 OO 容器，非真实用户请求）
            class _CallbackUser:
                id = UUID(user_id) if user_id else None

            await save_orchestrator.after_save(
                db, wp, _CallbackUser(),
                trigger="onlyoffice_callback",
                extra={
                    "sheet_name": sheet_name,
                    "doc_key": doc_key or "",
                    "file_size": len(file_bytes),
                },
            )
            await db.commit()
        except Exception as exc:
            logger.warning(
                "orchestrator.after_save failed in onlyoffice_callback wp=%s: %s",
                wp_id, exc,
            )

        return {"error": 0}

    # 4. status=3/4/7: 关闭（无修改/保存出错/强制保存出错）— 释放席位
    if status in _RELEASE_STATUSES:
        if user_id and doc_key:
            from app.services.onlyoffice_session_limiter import release_session

            await release_session(user_id, doc_key)
        return {"error": 0}

    # 5. status=1 等：编辑中，无操作
    return {"error": 0}
