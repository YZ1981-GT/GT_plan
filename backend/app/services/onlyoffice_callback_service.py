"""OnlyOffice 回调鉴权与健康检查 — P1 安全刚需"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx
import sqlalchemy as sa
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.core import User
from app.models.phase13_models import WordExportStatus, WordExportTaskVersion
from app.services.deliverable_doc_key import deliverable_doc_key, parse_deliverable_doc_key
from app.services.deliverable_service import DeliverableService
from app.services.onlyoffice_docx_normalize import normalize_onlyoffice_docx
from app.services.onlyoffice_editor_identity import resolve_editor_id

logger = logging.getLogger(__name__)

# OnlyOffice callback status codes
STATUS_READY_FOR_SAVE = 2
STATUS_FORCE_SAVE = 6
_SAVE_STATUSES = frozenset({STATUS_READY_FOR_SAVE, STATUS_FORCE_SAVE})


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
            async with self.db.begin_nested():
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
        except Exception as exc:  # best_effort — 安全日志写入不应阻断拒绝流程
            logger.error("OnlyOffice callback 安全日志写入失败: %s", exc)

    async def health_check(self) -> bool:
        """探测 OnlyOffice /healthcheck

        🔴 2026-09-22 修复：此前用 `urllib.request.urlopen`（同步阻塞 IO），标了
        `async def` 却在方法体内真阻塞事件循环最多 `timeout` 秒——调用方
        `wp_onlyoffice_router.get_onlyoffice_health` 是 D4 每次切换底稿都会打的
        无鉴权探针（见 `useD4SyncMode.ts` mount 期 `void checkOoHealth()`），一次
        阻塞会连累同进程内**所有**并发请求（同 batch1 教训：纯 CPU/阻塞 IO 必须
        offload，否则一人的慢请求拖累所有人的轮询）。改用本文件已有的
        `httpx.AsyncClient`（真异步，非阻塞），不引入新依赖。
        """
        base = settings.ONLYOFFICE_URL.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{base}/healthcheck")
                return resp.status_code == 200
        except Exception as exc:
            logger.debug("OnlyOffice healthcheck 不可用: %s", exc)
            return False

    def _parse_base_version(self, body: dict, task_id: UUID) -> int | None:
        """从回调体 ``key`` 反解底版版本号，并校验该 key 属于本交付物。

        返回 ``None`` 表示 key 缺失 / 格式不符 / 指向别的 task —— 调用方据此拒绝（写安全日志）。
        """
        raw_key = body.get("key")
        if not isinstance(raw_key, str) or not raw_key.strip():
            return None
        parsed = parse_deliverable_doc_key(raw_key.strip())
        if parsed is None:
            return None
        key_task_id, base_no = parsed
        if key_task_id != task_id:
            logger.warning(
                "OnlyOffice callback key 指向交付物 %s，与路径 %s 不符，拒绝",
                key_task_id,
                task_id,
            )
            return None
        return base_no

    async def handle_callback(
        self,
        task_id: UUID,
        body: dict,
        *,
        user_id: UUID,
        year: int,
    ) -> dict:
        """status 2（关闭保存）/ 6（强制保存）下载编辑后文件并创建新版本。

        Args:
            user_id: 版本记录的 ``created_by`` 占位（NOT NULL 列，回调无鉴权用户上下文，
                由路由传交付物创建人）。**实际编辑人**另由 ``resolve_editor_id`` 从回调体
                解析并落 ``edited_by``；解析不出记 None（需求 7.2/7.3）。

        四项加固（spec deliverable-writeback-and-online-edit-integrity §3）：
        1. **status 6 也落版本** —— 编辑器开了 ``forcesave``，用户点「保存」发的是 6；旧实现只认 2，
           丢「保存但不关闭」的中间版本（见 OnlyOffice callback-handler 文档）。
        2. **key 校验** —— 回调体 ``key`` 必须是本交付物的 doc_key，否则写安全日志并拒绝（外部可达端点）。
        3. **幂等** —— 规范化后的字节 SHA-256 与最新版本相同则不建新版本（Document Server 重试 / 强制保存后关闭同内容）。
        4. **陈旧底版** —— 底版之后已有非本会话版本则仍保存（不丢编辑），标 ``base_version_no`` 并写审计日志。

        快照绑定（需求 7.1）：OO 编辑**不重新捕获** ``tb_hash``，继承底版。
        """
        status = body.get("status")
        if status not in _SAVE_STATUSES:
            return {"error": 0}

        url = body.get("url")
        if not url:
            logger.warning("OnlyOffice callback status=%s 但缺少 url task=%s", status, task_id)
            return {"error": 1}

        task = await self._deliverable_svc.get_task(task_id)
        if task is None:
            return {"error": 1}

        base_version_no = self._parse_base_version(body, task_id)
        doc_key = body.get("key")
        if base_version_no is None:
            # key 缺失 / 非法 / 跨 task：外部组装的回调体不可采信，写安全日志后拒绝。
            await self.write_security_log(
                task_id,
                project_id=task.project_id,
                reason=f"callback key 无效或与交付物不符: {doc_key!r}",
            )
            return {"error": 1}

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            docx_bytes = resp.content

        # 规范化在幂等判定之前：规范化改变字节，必须对最终入库字节判幂等，否则「同内容」每次仍落新版本。
        if (Path(url).suffix or ".docx").lower() == ".docx":
            docx_bytes = normalize_onlyoffice_docx(docx_bytes)
        incoming_sha = hashlib.sha256(docx_bytes).hexdigest()

        latest = await self._deliverable_svc._latest_version(task_id)
        if latest is not None and latest.file_hash == incoming_sha:
            # 幂等：与最新版本逐字节相同（强制保存后关闭、Document Server 重试）⇒ 不建新版本。
            logger.info(
                "OnlyOffice callback 内容与最新版本 v%s 一致，幂等跳过 task=%s status=%s",
                latest.version_no, task_id, status,
            )
            return {"error": 0}

        overwrote = await self._stale_base_overwrites(task_id, base_version_no, doc_key)

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
            base_version_no=base_version_no,
            oo_doc_key=doc_key if isinstance(doc_key, str) else None,
        )

        if overwrote:
            # 不丢用户编辑，但留痕「本版基于旧底版、覆盖了期间产生的新版本」，并提示版本链。
            await self._log_stale_base_save(
                task=task,
                saved_version_no=stored.version.version_no,
                base_version_no=base_version_no,
                overwrote=overwrote,
                editor_id=editor_id,
            )

        await self.detect_and_store_report_drift(
            task,
            version=stored.version,
            baseline_version_no=base_version_no,
        )
        return {"error": 0}

    async def _stale_base_overwrites(
        self, task_id: UUID, base_version_no: int, doc_key: object
    ) -> list[int]:
        """返回「底版之后、非本会话」的版本号列表 —— 非空即本次保存基于陈旧底版。

        同一会话（同 doc_key）产生的更高版本（强制保存串）不算陈旧：它们本就是本次编辑的中间态。
        """
        rows = (await self.db.execute(
            sa.select(WordExportTaskVersion.version_no, WordExportTaskVersion.oo_doc_key).where(
                WordExportTaskVersion.word_export_task_id == task_id,
                WordExportTaskVersion.version_no > base_version_no,
            ).order_by(WordExportTaskVersion.version_no)
        )).all()
        same_key = doc_key.strip() if isinstance(doc_key, str) and doc_key.strip() else None
        return [no for no, key in rows if not (same_key is not None and key == same_key)]

    async def _log_stale_base_save(
        self, *, task, saved_version_no: int, base_version_no: int,
        overwrote: list[int], editor_id: UUID | None,
    ) -> None:
        from app.services.audit_log_helper import append_audit_log

        try:
            async with self.db.begin_nested():
                await append_audit_log(
                    self.db,
                    {
                        "user_id": editor_id,
                        "project_id": task.project_id,
                        "action": "deliverable_oo_stale_base_save",
                        "resource_type": "word_export_task_version",
                        "resource_id": str(task.id),
                        "details": {
                            "event_type": "deliverable_oo_stale_base_save",
                            "saved_version_no": saved_version_no,
                            "base_version_no": base_version_no,
                            "overwrote_versions": overwrote,
                        },
                    },
                )
        except Exception:  # noqa: BLE001 — best_effort: 留痕失败不得回滚已保存的版本
            logger.warning("陈旧底版保存留痕写入失败 task=%s", task.id, exc_info=True)
        logger.warning(
            "OnlyOffice 保存基于陈旧底版 v%s：期间已有版本 %s；本版 v%s 以旧内容为底 task=%s",
            base_version_no, overwrote, saved_version_no, task.id,
        )

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
            # 🔴 类名是 ProjectUser（表 project_users），不是 ProjectMember；
            # 且它带 SoftDeleteMixin → 必须排除已移出项目的成员。
            from app.models.core import ProjectUser, User

            # 第一道闸：平台在册用户（未删除、未停用）。回调体由 Document Server 组装，不校验等于让外部值落留痕。
            user_row = (await self.db.execute(
                sa.select(User.role).where(
                    User.id == editor_id,
                    User.is_deleted == sa.false(),
                    User.is_active == sa.true(),
                )
            )).first()
            if user_row is None:
                logger.warning(
                    "OnlyOffice callback 编辑人 %s 非在册有效用户，如实记为未知 task=%s",
                    editor_id, task_id,
                )
                return None

            # 第二道闸：与项目权限同口径（assert_project_permission）—— admin 免项目成员校验，
            # 其余必须在 project_users 内。历史实现只查 project_users，使 admin 编辑恒记空（admin 不在成员表）。
            role_val = getattr(user_row[0], "value", user_row[0])
            if role_val != "admin":
                member = (await self.db.execute(
                    sa.select(ProjectUser.id).where(
                        ProjectUser.project_id == task.project_id,
                        ProjectUser.user_id == editor_id,
                        ProjectUser.is_deleted == sa.false(),
                    )
                )).first()
                if member is None:
                    logger.warning(
                        "OnlyOffice callback 编辑人 %s 不属于项目 %s，如实记为未知 task=%s",
                        editor_id, task.project_id, task_id,
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
