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
        return bool(settings.ONLYOFFICE_JWT_SECRET)

    def verify_callback_jwt(self, token: str | None, body: dict) -> bool:
        """校验 OnlyOffice callback JWT；失败写安全日志"""
        if not self.enabled:
            logger.warning("OnlyOffice JWT 未配置，回调鉴权已禁用")
            return False

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
        """生成 OnlyOffice 编辑配置 + JWT"""
        if not self.enabled:
            raise ValueError("OnlyOffice JWT 未配置")

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

        token = jwt.encode(config, settings.ONLYOFFICE_JWT_SECRET, algorithm="HS256")
        return {"config": config, "token": token, "mode": mode, "documentType": doc_type}
