"""导入运维操作审计服务。

为 replay/reset 等高风险运维入口记录结构化审计日志：
- 操作者
- 作用域
- 请求参数
- 执行结果与耗时
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from starlette.requests import Request
from sqlalchemy.exc import IntegrityError

from app.core.database import async_session as async_session_factory
from app.models.core import Log
from app.models.core import User

logger = logging.getLogger(__name__)


class ImportOpsAuditService:
    """导入运维操作审计（独立事务，不影响主业务返回）。"""

    @staticmethod
    def extract_client_ip(request: Request | None) -> str | None:
        if request is None:
            return None
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        if request.client:
            return request.client.host
        return None

    @classmethod
    async def log_operation(
        cls,
        *,
        user_id: UUID | None,
        action_type: str,
        project_id: UUID | None,
        params: dict[str, Any] | None = None,
        scope: dict[str, Any] | None = None,
        outcome: str,
        duration_ms: int | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        request: Request | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "actor_user_id": str(user_id) if user_id else None,
            "scope": scope or {},
            "params": params or {},
            "outcome": outcome,
            "duration_ms": duration_ms,
            "result": result or {},
        }
        if error:
            payload["error"] = error[:1000]

        async def _insert_log(target_user_id: UUID | None, body: dict[str, Any]) -> None:
            async with async_session_factory() as session:
                session.add(
                    Log(
                        user_id=target_user_id,
                        action_type=action_type,
                        object_type="import_operations",
                        object_id=project_id,
                        new_value=body,
                        ip_address=cls.extract_client_ip(request),
                    )
                )
                await session.commit()

        async def _user_exists(candidate_user_id: UUID | None) -> bool:
            if candidate_user_id is None:
                return True
            async with async_session_factory() as session:
                row = await session.execute(
                    sa.select(User.id).where(User.id == candidate_user_id)
                )
                return row.scalar_one_or_none() is not None

        # 先做用户存在性预检，避免在 FK 严格环境下触发无意义失败。
        if user_id is not None and not await _user_exists(user_id):
            degraded_payload = {
                **payload,
                "audit_write_degraded": True,
                "audit_write_note": "user_id not found, fallback to null user_id",
            }
            try:
                await _insert_log(None, degraded_payload)
            except Exception:
                logger.error(
                    "IMPORT_OPS_AUDIT_FALLBACK %s",
                    json.dumps(
                        {
                            "action_type": action_type,
                            "project_id": str(project_id) if project_id else None,
                            "payload": degraded_payload,
                        },
                        ensure_ascii=False,
                        default=str,
                    )[:4000],
                    exc_info=True,
                )
            return

        try:
            await _insert_log(user_id, payload)
        except IntegrityError:
            degraded_payload = {
                **payload,
                "audit_write_degraded": True,
                "audit_write_note": "user_id foreign key not found, fallback to null user_id",
            }
            try:
                await _insert_log(None, degraded_payload)
            except Exception:
                logger.error(
                    "IMPORT_OPS_AUDIT_FALLBACK %s",
                    json.dumps(
                        {
                            "action_type": action_type,
                            "project_id": str(project_id) if project_id else None,
                            "payload": degraded_payload,
                        },
                        ensure_ascii=False,
                        default=str,
                    )[:4000],
                    exc_info=True,
                )
        except Exception:
            logger.error(
                "IMPORT_OPS_AUDIT_FALLBACK %s",
                json.dumps(
                    {
                        "action_type": action_type,
                        "project_id": str(project_id) if project_id else None,
                        "payload": payload,
                    },
                    ensure_ascii=False,
                    default=str,
                )[:4000],
                exc_info=True,
            )
