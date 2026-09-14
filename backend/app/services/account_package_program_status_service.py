"""科目工作包程序状态服务

职责：
- 查询单个/全部程序状态
- Upsert 程序状态（创建或更新）
- 业务验证（applicable=False 时 not_applicable_reason 必填）

规则：
- Service 只 flush 不 commit（router 统一 commit）
- review_result 变更时自动记录 reviewer 和 reviewed_at

Requirements: 2.3, 5.1
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_package_models import AccountPackageProgramStatus


class ProgramStatusValidationError(Exception):
    """程序状态业务验证错误"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class AccountPackageProgramStatusService:
    """科目工作包程序状态服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_status(
        self,
        project_id: uuid.UUID,
        account_package_id: str,
        program_code: str,
    ) -> AccountPackageProgramStatus | None:
        """获取单个程序状态"""
        stmt = select(AccountPackageProgramStatus).where(
            AccountPackageProgramStatus.project_id == project_id,
            AccountPackageProgramStatus.account_package_id == account_package_id,
            AccountPackageProgramStatus.program_code == program_code,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_statuses(
        self,
        project_id: uuid.UUID,
        account_package_id: str,
    ) -> list[AccountPackageProgramStatus]:
        """获取工作包下所有程序状态"""
        stmt = select(AccountPackageProgramStatus).where(
            AccountPackageProgramStatus.project_id == project_id,
            AccountPackageProgramStatus.account_package_id == account_package_id,
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def upsert_status(
        self,
        project_id: uuid.UUID,
        account_package_id: str,
        program_code: str,
        data: dict[str, Any],
        user_id: uuid.UUID,
    ) -> AccountPackageProgramStatus:
        """创建或更新程序状态

        Args:
            project_id: 项目 ID
            account_package_id: 工作包 ID
            program_code: 程序编号
            data: 更新字段字典
            user_id: 当前操作用户 ID

        Returns:
            更新后的程序状态对象

        Raises:
            ProgramStatusValidationError: 业务验证失败
        """
        # 业务验证：applicable=False 时 not_applicable_reason 必填
        applicable = data.get("applicable")
        if applicable is False:
            reason = data.get("not_applicable_reason")
            if not reason or (isinstance(reason, str) and not reason.strip()):
                raise ProgramStatusValidationError(
                    "程序标记为不适用时，必须填写不适用理由 (not_applicable_reason)"
                )

        # 查找现有记录
        existing = await self.get_status(project_id, account_package_id, program_code)

        if existing is None:
            # 创建新记录（显式设置 server-side defaults for in-memory compatibility）
            existing = AccountPackageProgramStatus(
                id=uuid.uuid4(),
                project_id=project_id,
                account_package_id=account_package_id,
                program_code=program_code,
                applicable=True,
                status="pending",
            )
            self._db.add(existing)

        # 更新字段
        allowed_fields = {
            "applicable", "status", "evidence", "review_result",
            "conclusion", "not_applicable_reason",
        }
        for field_name in allowed_fields:
            if field_name in data:
                setattr(existing, field_name, data[field_name])

        # 自动设置 updated_by 和 updated_at
        existing.updated_by = user_id
        existing.updated_at = datetime.now(timezone.utc)

        # 如果 review_result 正在被设置，自动记录 reviewer 和 reviewed_at
        if "review_result" in data and data["review_result"] is not None:
            existing.reviewer = user_id
            existing.reviewed_at = datetime.now(timezone.utc)

        # 如果标记不适用，同时设 status 为 not_applicable（如果未显式传 status）
        if applicable is False and "status" not in data:
            existing.status = "not_applicable"

        await self._db.flush()
        return existing
