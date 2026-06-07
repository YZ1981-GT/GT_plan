"""临时授权服务

P2-1: 管理项目级临时授权的创建、查询、过期失效和审计日志。
铁律：service 只 flush 不 commit（router 统一 commit）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.temporary_grant_models import TemporaryGrant
from app.models.temporary_grant_schemas import TemporaryGrantCreate
from app.services.permission_matrix_service import OPERATION_CODES


class TemporaryGrantError(Exception):
    """临时授权业务异常"""

    pass


class TemporaryGrantService:
    """临时授权服务

    职责：
    - 创建临时授权（校验 operation_code 合法性、expires_at 在未来）
    - 查询用户在项目中的有效授权
    - 判断用户是否拥有临时授权的某操作
    - 过期自动失效（惰性 + 批量）
    - 审计日志记录
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_grant(
        self,
        project_id: uuid.UUID,
        approver_id: uuid.UUID,
        data: TemporaryGrantCreate,
    ) -> TemporaryGrant:
        """创建临时授权

        Args:
            project_id: 项目 ID
            approver_id: 审批人（当前登录用户）
            data: 创建请求数据

        Returns:
            新建的 TemporaryGrant 实例

        Raises:
            TemporaryGrantError: 参数校验失败
        """
        # 校验 operation_code 合法
        if data.operation_code not in OPERATION_CODES:
            raise TemporaryGrantError(
                f"无效的操作代码: {data.operation_code}，"
                f"合法值: {OPERATION_CODES}"
            )

        # 校验 expires_at 在未来
        now = datetime.now(timezone.utc)
        if data.expires_at <= now:
            raise TemporaryGrantError("expires_at 必须在当前时间之后")

        # 校验审批人不是被授权人
        if data.grantee == approver_id:
            raise TemporaryGrantError("审批人不能授权给自己")

        grant = TemporaryGrant(
            id=uuid.uuid4(),
            project_id=project_id,
            operation_code=data.operation_code,
            grantee=data.grantee,
            approver=approver_id,
            reason=data.reason,
            expires_at=data.expires_at,
            is_active=True,
        )
        self.db.add(grant)
        await self.db.flush()

        # 写审计日志
        await self._write_audit_log(
            user_id=approver_id,
            action="temp_grant:create",
            resource_id=str(grant.id),
            details={
                "project_id": str(project_id),
                "operation_code": data.operation_code,
                "grantee": str(data.grantee),
                "reason": data.reason,
                "expires_at": data.expires_at.isoformat(),
            },
        )

        return grant

    async def has_active_grant(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        operation_code: str,
    ) -> bool:
        """检查用户是否有指定操作的有效临时授权

        同时惰性失效过期授权。
        """
        now = datetime.now(timezone.utc)

        # 惰性失效：将过期的标记为非活跃
        await self._expire_stale_grants(project_id, user_id)

        stmt = select(TemporaryGrant.id).where(
            and_(
                TemporaryGrant.project_id == project_id,
                TemporaryGrant.grantee == user_id,
                TemporaryGrant.operation_code == operation_code,
                TemporaryGrant.is_active == True,  # noqa: E712
                TemporaryGrant.expires_at > now,
            )
        ).limit(1)

        result = await self.db.execute(stmt)
        grant_row = result.scalar_one_or_none()

        if grant_row:
            # 记录使用审计
            await self._write_audit_log(
                user_id=user_id,
                action="temp_grant:use",
                resource_id=str(grant_row),
                details={
                    "project_id": str(project_id),
                    "operation_code": operation_code,
                },
            )
            return True
        return False

    async def list_grants(
        self,
        project_id: uuid.UUID,
        active_only: bool = True,
    ) -> list[TemporaryGrant]:
        """列出项目的临时授权"""
        conditions = [TemporaryGrant.project_id == project_id]
        if active_only:
            now = datetime.now(timezone.utc)
            conditions.extend([
                TemporaryGrant.is_active == True,  # noqa: E712
                TemporaryGrant.expires_at > now,
            ])

        stmt = select(TemporaryGrant).where(and_(*conditions)).order_by(
            TemporaryGrant.created_at.desc()
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def revoke_grant(
        self,
        grant_id: uuid.UUID,
        revoker_id: uuid.UUID,
    ) -> TemporaryGrant | None:
        """撤销临时授权"""
        stmt = select(TemporaryGrant).where(
            and_(
                TemporaryGrant.id == grant_id,
                TemporaryGrant.is_active == True,  # noqa: E712
            )
        )
        result = await self.db.execute(stmt)
        grant = result.scalar_one_or_none()
        if not grant:
            return None

        grant.is_active = False
        await self.db.flush()

        await self._write_audit_log(
            user_id=revoker_id,
            action="temp_grant:revoke",
            resource_id=str(grant_id),
            details={
                "project_id": str(grant.project_id),
                "operation_code": grant.operation_code,
                "grantee": str(grant.grantee),
            },
        )
        return grant

    async def expire_all_stale(self) -> int:
        """批量过期所有到期授权（供定时任务调用）

        Returns:
            过期的授权数量
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(TemporaryGrant)
            .where(
                and_(
                    TemporaryGrant.is_active == True,  # noqa: E712
                    TemporaryGrant.expires_at <= now,
                )
            )
            .values(is_active=False)
            .returning(TemporaryGrant.id)
        )
        result = await self.db.execute(stmt)
        expired_ids = list(result.scalars().all())

        # 为每个过期的授权写审计日志
        for grant_id in expired_ids:
            await self._write_audit_log(
                user_id=None,
                action="temp_grant:expire",
                resource_id=str(grant_id),
                details={"reason": "auto_expire"},
            )

        await self.db.flush()
        return len(expired_ids)

    async def _expire_stale_grants(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """惰性过期：查询时顺带将该用户在该项目的过期授权标为非活跃"""
        now = datetime.now(timezone.utc)
        stmt = (
            update(TemporaryGrant)
            .where(
                and_(
                    TemporaryGrant.project_id == project_id,
                    TemporaryGrant.grantee == user_id,
                    TemporaryGrant.is_active == True,  # noqa: E712
                    TemporaryGrant.expires_at <= now,
                )
            )
            .values(is_active=False)
            .returning(TemporaryGrant.id)
        )
        result = await self.db.execute(stmt)
        expired_ids = list(result.scalars().all())

        for grant_id in expired_ids:
            await self._write_audit_log(
                user_id=user_id,
                action="temp_grant:expire",
                resource_id=str(grant_id),
                details={
                    "project_id": str(project_id),
                    "reason": "lazy_expire_on_query",
                },
            )

    async def _write_audit_log(
        self,
        user_id: uuid.UUID | None,
        action: str,
        resource_id: str,
        details: dict | None = None,
    ) -> None:
        """写入审计日志到 app_audit_log"""
        from sqlalchemy import text

        await self.db.execute(
            text(
                "INSERT INTO app_audit_log (id, user_id, action, resource_type, resource_id, details) "
                "VALUES (gen_random_uuid(), :user_id, :action, :resource_type, :resource_id, :details::jsonb)"
            ),
            {
                "user_id": str(user_id) if user_id else None,
                "action": action,
                "resource_type": "temporary_grant",
                "resource_id": resource_id,
                "details": __import__("json").dumps(details) if details else None,
            },
        )
