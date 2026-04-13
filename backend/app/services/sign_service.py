"""电子签名服务

功能：
- 签署文档（三级签名）
- 验证签名
- 获取签名历史
- 撤销签名

Validates: Requirements 7.1-7.4
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extension_models import SignatureRecord


class SignService:
    """电子签名服务"""

    async def sign_document(
        self,
        db: AsyncSession,
        object_type: str,
        object_id: UUID,
        signer_id: UUID,
        level: str,
        signature_data: dict | None = None,
        ip_address: str | None = None,
    ) -> dict:
        """创建签名记录

        level1: 仅记录操作（谁、何时、什么、IP）
        level2: 存储签名图片数据到 signature_data jsonb
        level3: CA证书签名（预留stub）
        """
        if level not in ("level1", "level2", "level3"):
            raise ValueError(f"无效的签名级别: {level}")

        if level == "level3":
            raise NotImplementedError("CA证书签名尚未实现")

        sig_data = None
        if level == "level2":
            sig_data = signature_data or {}

        record = SignatureRecord(
            object_type=object_type,
            object_id=object_id,
            signer_id=signer_id,
            signature_level=level,
            signature_data=sig_data,
            signature_timestamp=datetime.now(timezone.utc),
            ip_address=ip_address,
        )
        db.add(record)
        await db.flush()
        return self._to_dict(record)

    async def verify_signature(self, db: AsyncSession, signature_id: UUID) -> dict:
        """验证签名"""
        result = await db.execute(
            sa.select(SignatureRecord).where(
                SignatureRecord.id == signature_id,
                SignatureRecord.is_deleted == sa.false(),
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError("签名记录不存在")

        if record.signature_level == "level3":
            raise NotImplementedError("CA证书验证尚未实现")

        # level1/level2 始终验证通过
        return {
            "signature_id": str(record.id),
            "valid": True,
            "level": record.signature_level,
            "signer_id": str(record.signer_id),
            "timestamp": record.signature_timestamp.isoformat(),
        }

    async def get_signatures(
        self, db: AsyncSession, object_type: str, object_id: UUID
    ) -> list[dict]:
        """获取对象的签名历史"""
        stmt = (
            sa.select(SignatureRecord)
            .where(
                SignatureRecord.object_type == object_type,
                SignatureRecord.object_id == object_id,
                SignatureRecord.is_deleted == sa.false(),
            )
            .order_by(SignatureRecord.signature_timestamp.desc())
        )
        result = await db.execute(stmt)
        return [self._to_dict(r) for r in result.scalars().all()]

    async def revoke_signature(self, db: AsyncSession, signature_id: UUID) -> dict:
        """撤销签名（软删除）"""
        result = await db.execute(
            sa.select(SignatureRecord).where(SignatureRecord.id == signature_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError("签名记录不存在")

        record.is_deleted = True
        await db.flush()
        return {"signature_id": str(signature_id), "revoked": True}

    def _to_dict(self, record: SignatureRecord) -> dict:
        return {
            "id": str(record.id),
            "object_type": record.object_type,
            "object_id": str(record.object_id),
            "signer_id": str(record.signer_id),
            "signature_level": record.signature_level,
            "signature_data": record.signature_data,
            "signature_timestamp": record.signature_timestamp.isoformat(),
            "ip_address": record.ip_address,
            "is_deleted": record.is_deleted,
        }
