"""OnlyOffice 回调鉴权与健康检查 — P1 安全刚需"""

from __future__ import annotations

import logging
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.core import User
from app.models.phase13_models import WordExportStatus, WordExportTaskVersion
from app.services.deliverable_doc_key import deliverable_doc_key
from app.services.deliverable_service import DeliverableService
from app.services.onlyoffice_editor_identity import resolve_editor_id

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
        """status==2 时下载编辑后文件并创建新版本。

        Args:
            user_id: 版本记录的 ``created_by`` 占位（NOT NULL 列，回调无鉴权用户上下文，
                由路由传交付物创建人）。**实际编辑人**另由 ``resolve_editor_id`` 从回调体
                解析并落 ``edited_by``；解析不出记 None（需求 7.2/7.3）。

        快照绑定（需求 7.1）：OO 编辑**不重新捕获** ``tb_hash``，改为继承上一版
        —— 人工润色不等于按新试算表重算，重捕会把「本该 stale」洗白成绿。
        """
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

        latest = await self._deliverable_svc._latest_version(task_id)
        next_no = (latest.version_no + 1) if latest else 1
        ext = Path(url).suffix or ".docx"
        file_name = f"{task.doc_type}_v{next_no}{ext}"

        editor_id = await self._resolve_verified_editor(body, task=task, task_id=task_id)

        stored = await self._deliverable_svc.render_and_store(
            task_id,
            docx_bytes=docx_bytes,
            user_id=user_id,
            file_name=file_name,
            created_via="onlyoffice_edit",
            inherit_snapshot_refs=True,
            edited_by=editor_id,
            edited_at=datetime.now(timezone.utc),
        )
        await self.detect_and_store_report_drift(
            task,
            version=stored.version,
            baseline_version_no=latest.version_no if latest else None,
        )
        return {"error": 0}

    async def detect_and_store_report_drift(
        self,
        task,
        *,
        version: WordExportTaskVersion,
        baseline_version_no: int | None,
    ) -> dict | None:
        """财务报表 xlsx 保存后跑差异检测并落 ``version.drift_report``（需求 10.2）。

        **这是差异检测的唯一生产触发点**。为什么只挂在 OO 保存路径上：

        - 报表 xlsx 是由 ``ReportExcelExporter`` **按试算表重算值写出**的，生成路径
          天然一致；文件能与重算值分叉的唯一途径就是有人在 OO 里改了单元格
          （``_document_type`` 对 ``.xlsx`` 返回 ``cell``、``_editor_mode`` 对非终态
          返回 ``edit``、交付中心的编辑入口不按 doc_type 拦 ⇒ 这条路径真实可达）。
        - 反过来，若把检测挂在**生成**路径上，一旦 ``cell_mapping.json`` 的坐标与
          模板变体布局不一致，刚生成的报表就会被判有差异并阻断 confirmed
          （真实库实测项目 0ec33ac9 会立刻中招 22 处）—— 那是把配置问题变成业务阻塞。

        非财务报表（附注 / 报告正文）直接跳过 —— 它们走文字回填路径。
        检测/落库失败一律 fail-open（warning 不阻断保存）：保存已成功，
        再抛异常只会让 OnlyOffice 认为保存失败并重试。
        """
        doc_type = getattr(task, "doc_type", "") or ""
        if not doc_type.startswith("financial_report"):
            return None
        try:
            from app.services.financial_report_drift_service import (
                FinancialReportDriftService,
            )

            report = await FinancialReportDriftService(self.db).detect(
                task.id,
                version.version_no,
                baseline_version_no=baseline_version_no,
            )
            # None = 未配映射（放行态）。**照实写 None**，不要写 {} —— 两者虽都放行，
            # 但 None 表达「未检测/未配」，{} 会被误读成「已检测且无差异」。
            version.drift_report = report
            await self.db.flush()
            logger.info(
                "drift: 已落库 task=%s v%s report=%s",
                task.id,
                version.version_no,
                "None" if report is None else list(report.keys()),
            )
            return report
        except Exception:  # noqa: BLE001 — 检测失败不得回滚已保存的版本
            logger.warning(
                "drift: 检测/落库失败 task=%s v%s（保存本身已成功）",
                task.id,
                version.version_no,
                exc_info=True,
            )
            return None

    async def _resolve_verified_editor(
        self, body: dict, *, task, task_id: UUID
    ) -> UUID | None:
        """解析编辑人并校验其**属于本项目**（需求 7.2）。

        两道闸：
        1. `resolve_editor_id` 从回调体解析 UUID（解析不出 → None + warning）。
        2. 该 UUID 必须是平台在册用户**且**在本项目成员表内 —— 回调是外部可达端点，
           虽有 JWT 但 body 由 Document Server 组装，不校验等于让外部值直接落审计留痕。

        任一闸不通过一律返回 ``None``（如实记为未知）。
        **绝不回退 ``task.created_by``** —— 伪装成创建人比留空更坏。
        """
        editor_id = resolve_editor_id(body, task_id=task_id)
        if editor_id is None:
            return None

        try:
            import sqlalchemy as sa

            # 🔴 类名是 ProjectUser（表 project_users），不是 ProjectMember；
            # 且它带 SoftDeleteMixin → 必须排除已移出项目的成员。
            from app.models.core import ProjectUser

            stmt = sa.select(ProjectUser.id).where(
                ProjectUser.project_id == task.project_id,
                ProjectUser.user_id == editor_id,
                ProjectUser.is_deleted == sa.false(),
            )
            result = await self.db.execute(stmt)
            if result.first() is None:
                logger.warning(
                    "OnlyOffice callback 编辑人 %s 不属于项目 %s，如实记为未知 task=%s",
                    editor_id,
                    task.project_id,
                    task_id,
                )
                return None
        except Exception:  # noqa: BLE001 — 校验失败不阻断保存，但也不采信该 id
            logger.warning(
                "OnlyOffice callback 编辑人归属校验失败，如实记为未知 task=%s",
                task_id,
                exc_info=True,
            )
            return None

        return editor_id

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

        # 需求 7.4/7.5：doc_key 必须确定性派生且与席位 key 同源。
        # 历史实现带 int(time.time()) → 每次请求都是"新文档" → 协同编辑失效
        # （两人同开进入两个独立会话，后 forcesave 者静默覆盖前者）。
        doc_key = deliverable_doc_key(task.id, version.version_no)
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
