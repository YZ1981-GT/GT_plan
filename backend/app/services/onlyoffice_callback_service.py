"""OnlyOffice 回调鉴权与健康检查 — P1 安全刚需"""

from __future__ import annotations

import logging
import time
import urllib.request
from pathlib import Path
from uuid import UUID

import httpx
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.core import User
from app.models.phase13_models import WordExportStatus, WordExportTaskVersion
from app.services.deliverable_service import DeliverableService

logger = logging.getLogger(__name__)

# OnlyOffice callback status codes
STATUS_READY_FOR_SAVE = 2


class OnlyOfficeCallbackService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._deliverable_svc = DeliverableService(db)

    @property
    def enabled(self) -> bool:
        """OnlyOffice 集成是否启用：只要配置了 URL 即启用（JWT 为可选鉴权）"""
        return bool(settings.ONLYOFFICE_URL)

    def verify_callback_jwt(self, token: str | None, body: dict) -> bool:
        """校验 OnlyOffice callback JWT 签名（需求 29.1）。

        仅做签名校验（纯函数，无副作用）。失败时由调用方
        （路由）调用 ``write_security_log`` 写入安全日志并拒绝（需求 29.2）。
        无 JWT_SECRET 配置时跳过验证（测试环境直通）。
        """
        if not settings.ONLYOFFICE_JWT_SECRET:
            # 测试环境：无密钥配置时跳过 JWT 校验，直接放行
            return True

        if not token:
            logger.warning("OnlyOffice callback 缺少 JWT token")
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

    async def write_security_log(
        self,
        task_id: UUID,
        *,
        project_id: UUID | None,
        reason: str,
    ) -> None:
        """JWT 校验失败时写入安全日志（需求 29.2）。

        伪造回调企图属高风险安全事件，复用哈希链 ``append_audit_log``，
        ``event_type='onlyoffice_callback_rejected'``，便于事后审计追溯。
        """
        from app.services.audit_log_helper import append_audit_log

        try:
            await append_audit_log(
                self.db,
                {
                    "user_id": None,
                    "project_id": project_id,
                    "action": "onlyoffice_callback_rejected",
                    "resource_type": "word_export_task",
                    "resource_id": str(task_id),
                    "details": {
                        "event_type": "onlyoffice_callback_rejected",
                        "reason": reason,
                    },
                },
            )
        except Exception as exc:  # 安全日志写入不应阻断拒绝流程
            logger.error("OnlyOffice callback 安全日志写入失败: %s", exc)

    async def health_check(self) -> bool:
        """探测 OnlyOffice /healthcheck"""
        base = settings.ONLYOFFICE_URL.rstrip("/")
        try:
            req = urllib.request.Request(f"{base}/healthcheck", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception as exc:
            logger.debug("OnlyOffice healthcheck 不可用: %s", exc)
            return False

    async def handle_callback(
        self,
        task_id: UUID,
        body: dict,
        *,
        user_id: UUID,
        year: int,
    ) -> dict:
        """status==2 时下载编辑后文件并创建新版本"""
        status = body.get("status")
        if status != STATUS_READY_FOR_SAVE:
            return {"error": 0}

        url = body.get("url")
        if not url:
            logger.warning("OnlyOffice callback status=2 但缺少 url task=%s", task_id)
            return {"error": 1}

        task = await self._deliverable_svc.get_task(task_id)
        if task is None:
            return {"error": 1}

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            docx_bytes = resp.content

        from app.services.deliverable_snapshot_service import DeliverableSnapshotService

        snap_svc = DeliverableSnapshotService(self.db)
        snapshot_refs = await snap_svc.capture_snapshot_refs(
            task.project_id, year, task.doc_type
        )

        latest = await self._deliverable_svc._latest_version(task_id)
        next_no = (latest.version_no + 1) if latest else 1
        ext = Path(url).suffix or ".docx"
        file_name = f"{task.doc_type}_v{next_no}{ext}"

        await self._deliverable_svc.render_and_store(
            task_id,
            docx_bytes=docx_bytes,
            user_id=user_id,
            source_snapshot_refs=snapshot_refs,
            file_name=file_name,
            created_via="onlyoffice_edit",
        )
        return {"error": 0}

    def _editor_mode(self, task_status: str) -> str:
        if task_status in (
            WordExportStatus.confirmed.value,
            WordExportStatus.signed.value,
            WordExportStatus.archived.value,
        ):
            return "view"
        return "edit"

    def _document_type(self, file_path: str | None) -> str:
        if file_path and Path(file_path).suffix.lower() == ".xlsx":
            return "cell"
        return "word"

    def build_editor_config(
        self,
        task,
        version: WordExportTaskVersion,
        user: User,
        *,
        download_url: str,
        callback_url: str,
    ) -> dict:
        """生成 OnlyOffice 编辑配置 + JWT（无密钥时不签 JWT）"""
        if not self.enabled:
            raise ValueError("OnlyOffice 未配置（ONLYOFFICE_URL 为空）")

        doc_key = f"{task.id}_{version.version_no}_{int(time.time())}"
        mode = self._editor_mode(task.status)
        doc_type = self._document_type(version.file_path)

        config = {
            "document": {
                "fileType": Path(version.file_path or "").suffix.lstrip(".") or "docx",
                "key": doc_key,
                "title": Path(version.file_path or "deliverable").name,
                "url": download_url,
                "permissions": {
                    "edit": mode == "edit",
                    "download": True,
                    "print": True,
                },
            },
            "documentType": doc_type,
            "editorConfig": {
                "mode": mode,
                "lang": "zh-CN",
                "callbackUrl": callback_url,
                "user": {"id": str(user.id), "name": user.username},
                "customization": {
                    "forcesave": True,
                    "compactHeader": True,
                },
            },
            "type": "desktop",
        }

        token = ""
        if settings.ONLYOFFICE_JWT_SECRET:
            token = jwt.encode(config, settings.ONLYOFFICE_JWT_SECRET, algorithm="HS256")

        return {"config": config, "token": token, "mode": mode, "documentType": doc_type}
