"""电子签名服务

功能：
- 签署文档（三级签名）
- 验证签名
- 获取签名历史
- 撤销签名
- R5 状态机联动：order=4 EQCR 签字 → eqcr_approved；order=5 归档签字 → final

Validates: Requirements 7.1-7.4, R5 Requirements 5, 6
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extension_models import SignatureRecord

logger = logging.getLogger(__name__)


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
        required_order: int | None = None,
        required_role: str | None = None,
    ) -> dict:
        """创建签名记录

        level1: 仅记录操作（谁、何时、什么、IP）
        level2: 存储签名图片数据到 signature_data jsonb
        level3: CA证书签名（预留stub）

        R5 状态机联动：
        - object_type='audit_report' + required_order=4 → 切 eqcr_approved
        - object_type='audit_report' + required_order=5 → 切 final
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
            required_order=required_order,
            required_role=required_role,
            signature_data=sig_data if level == "level2" else signature_data,
            signature_timestamp=datetime.now(timezone.utc),
            ip_address=ip_address,
        )
        db.add(record)
        await db.flush()

        # R5 状态机联动：签字完成后自动切审计报告状态
        if object_type == "audit_report" and required_order in (4, 5):
            await self._transition_report_status(
                db, object_id, required_order
            )

        return self._to_dict(record)

    async def _transition_report_status(
        self,
        db: AsyncSession,
        report_id: UUID,
        order: int,
    ) -> None:
        """签字完成后自动切审计报告状态。

        - order=4 (EQCR)：review → eqcr_approved
        - order=5 (归档)：eqcr_approved → final

        Validates: R5 Requirements 5, 6
        """
        from app.models.report_models import AuditReport, ReportStatus

        result = await db.execute(
            sa.select(AuditReport).where(
                AuditReport.id == report_id,
                AuditReport.is_deleted == False,  # noqa: E712
            )
        )
        report = result.scalar_one_or_none()
        if report is None:
            logger.warning(
                "SignService._transition_report_status: report %s not found",
                report_id,
            )
            return

        current_status = (
            report.status.value
            if hasattr(report.status, "value")
            else str(report.status)
        )
        logger.debug(
            "SignService._transition_report_status: report %s current_status=%r, order=%d",
            report_id, current_status, order,
        )

        if order == 4:
            # EQCR 签字完成：review → eqcr_approved
            if current_status == ReportStatus.review.value:
                report.status = ReportStatus.eqcr_approved
                await db.flush()  # 确保状态变更写入 DB，供后续 refresh 读到
                logger.info(
                    "SignService: order=4 EQCR sign complete, "
                    "report %s status → eqcr_approved",
                    report_id,
                )
            else:
                logger.warning(
                    "SignService: order=4 sign but report %s status is '%s' "
                    "(expected 'review'), skipping transition",
                    report_id,
                    current_status,
                )
        elif order == 5:
            # 归档签字完成：eqcr_approved → final
            if current_status == ReportStatus.eqcr_approved.value:
                report.status = ReportStatus.final
                # F50 / Sprint 8.18: final 锁定快照绑定
                if report.bound_dataset_id is None:
                    try:
                        from app.services.dataset_query import bind_to_active_dataset
                        await bind_to_active_dataset(
                            db, report, report.project_id, report.year
                        )
                    except Exception as _bind_err:
                        logger.warning(
                            "SignService: order=5 final 绑定 dataset 失败 "
                            "report=%s err=%s",
                            report_id, _bind_err,
                        )
                await db.flush()  # 确保状态变更写入 DB，供后续 refresh 读到
                logger.info(
                    "SignService: order=5 archive sign complete, "
                    "report %s status → final",
                    report_id,
                )
            else:
                logger.warning(
                    "SignService: order=5 sign but report %s status is '%s' "
                    "(expected 'eqcr_approved'), skipping transition",
                    report_id,
                    current_status,
                )

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

        if record.required_role == 'signing_partner' and record.required_order == 3:
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

        record.soft_delete()
        await db.flush()
        return {"signature_id": str(signature_id), "revoked": True}

    def _to_dict(self, record: SignatureRecord) -> dict:
        return {
            "id": str(record.id),
            "object_type": record.object_type,
            "object_id": str(record.object_id),
            "signer_id": str(record.signer_id),
            "signature_level": record.signature_level,
            "required_order": record.required_order,
            "required_role": record.required_role,
            "signature_data": record.signature_data,
            "signature_timestamp": record.signature_timestamp.isoformat(),
            "ip_address": record.ip_address,
            "is_deleted": record.is_deleted,
        }
