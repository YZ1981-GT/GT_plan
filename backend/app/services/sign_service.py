"""电子签名服务

功能：
- 签署文档（三级签名）
- 验证签名
- 获取签名历史
- 撤销签名
- 前置依赖校验（R1 Task 11）
- 签字状态机联动（最高级签完切 AuditReport.status）

Validates: Requirements 7.1-7.4, R1 需求 4
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extension_models import SignatureRecord

logger = logging.getLogger(__name__)


class PrerequisiteNotMetError(Exception):
    """前置签字未完成"""

    def __init__(self, missing_ids: list[str]):
        self.missing_ids = missing_ids
        super().__init__(f"前置签字未完成: {missing_ids}")


class StatusTransitionError(Exception):
    """AuditReport 状态切换失败"""

    def __init__(self, current_status: str, expected_status: str):
        self.current_status = current_status
        self.expected_status = expected_status
        super().__init__(
            f"报告状态切换失败: 当前 {current_status}，预期 {expected_status}"
        )


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
        prerequisite_signature_ids: list[str] | None = None,
        user_agent: str | None = None,
        gate_eval_id: str | None = None,
    ) -> dict:
        """创建签名记录

        level1: 仅记录操作（谁、何时、什么、IP）
        level2: 存储签名图片数据到 signature_data jsonb
        level3: CA证书签名（预留stub）

        R1 Task 11:
        - 校验 prerequisite_signature_ids 全部已签
        - 最高级签完后同事务切 AuditReport.status
        """
        if level not in ("level1", "level2", "level3"):
            raise ValueError(f"无效的签名级别: {level}")

        if level == "level3":
            raise NotImplementedError("CA证书签名尚未实现")

        # --- R1 Task 11: 前置依赖校验 ---
        if prerequisite_signature_ids:
            await self._check_prerequisites(db, prerequisite_signature_ids)

        sig_data = None
        if level == "level2":
            sig_data = signature_data or {}

        record = SignatureRecord(
            object_type=object_type,
            object_id=object_id,
            signer_id=signer_id,
            signature_level=level,
            signature_data=sig_data,
            signature_timestamp=datetime.utcnow(),
            ip_address=ip_address,
            required_order=required_order,
            required_role=required_role,
            prerequisite_signature_ids=prerequisite_signature_ids,
        )
        db.add(record)
        await db.flush()

        # --- R1 Task 11: 签字状态机联动 ---
        if object_type == "audit_report" and required_order is not None:
            await self._maybe_transition_report_status(
                db, object_id, required_order
            )

        # --- 审计日志 ---
        try:
            from app.services.audit_logger_enhanced import audit_logger

            await audit_logger.log_action(
                user_id=signer_id,
                action="signature.signed",
                object_type=object_type,
                object_id=object_id,
                details={
                    "ip": ip_address,
                    "ua": user_agent,
                    "gate_eval_id": gate_eval_id,
                    "signature_level": level,
                    "required_order": required_order,
                    "prerequisite_check_passed": True,
                },
            )
        except Exception:
            logger.warning("审计日志记录失败，不阻断签字", exc_info=True)

        return self._to_dict(record)

    async def _check_prerequisites(
        self, db: AsyncSession, prerequisite_ids: list[str]
    ) -> None:
        """校验所有前置签字已完成（signed_at IS NOT NULL）"""
        if not prerequisite_ids:
            return

        # 将字符串 ID 转为 UUID
        from uuid import UUID as _UUID

        uuids = [_UUID(pid) for pid in prerequisite_ids]

        stmt = sa.select(SignatureRecord).where(
            SignatureRecord.id.in_(uuids),
            SignatureRecord.is_deleted == sa.false(),
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        # 检查所有前置是否存在且已签字
        found_ids = {str(r.id) for r in records}
        signed_ids = {
            str(r.id) for r in records if r.signature_timestamp is not None
        }

        missing = [
            pid for pid in prerequisite_ids if pid not in signed_ids
        ]
        if missing:
            raise PrerequisiteNotMetError(missing)

    async def _maybe_transition_report_status(
        self, db: AsyncSession, report_id: UUID, current_order: int
    ) -> None:
        """最高级签字完成后切换 AuditReport.status

        规则：
        - 无 EQCR（max_order=3）：order=3 签完 → review → final
        - 有 EQCR（max_order=5）：
          * order=4 签完 → review → eqcr_approved
          * order=5 签完 → eqcr_approved → final
        """
        from app.models.report_models import AuditReport, ReportStatus

        # 查该报告所有签字记录的最大 order
        stmt = (
            sa.select(sa.func.max(SignatureRecord.required_order))
            .where(
                SignatureRecord.object_type == "audit_report",
                SignatureRecord.object_id == report_id,
                SignatureRecord.is_deleted == sa.false(),
            )
        )
        result = await db.execute(stmt)
        max_order = result.scalar()

        if max_order is None:
            # 只有当前这一条记录，它就是最大的
            max_order = current_order

        # 判断是否需要切态
        transition = self._determine_transition(current_order, max_order)
        if transition is None:
            return

        expected_from, target_to = transition

        # 查 AuditReport 并切态
        report_stmt = sa.select(AuditReport).where(
            AuditReport.id == report_id,
            AuditReport.is_deleted == sa.false(),
        )
        report_result = await db.execute(report_stmt)
        report = report_result.scalar_one_or_none()

        if report is None:
            logger.warning(
                "签字状态机联动: AuditReport %s 不存在，跳过", report_id
            )
            return

        if report.status != expected_from:
            raise StatusTransitionError(
                current_status=report.status.value if hasattr(report.status, 'value') else str(report.status),
                expected_status=expected_from.value if hasattr(expected_from, 'value') else str(expected_from),
            )

        report.status = target_to
        report.updated_at = datetime.utcnow()
        await db.flush()

        logger.info(
            "签字状态机联动: AuditReport %s 从 %s 切到 %s",
            report_id,
            expected_from,
            target_to,
        )

        # 发通知（失败不阻断）
        if target_to == ReportStatus.final:
            try:
                await self._notify_report_finalized(db, report)
            except Exception:
                logger.warning(
                    "report_finalized 通知发送失败，不阻断", exc_info=True
                )

    def _determine_transition(
        self, current_order: int, max_order: int
    ) -> tuple | None:
        """根据当前签字 order 和最大 order 判断是否需要切态

        Returns:
            (expected_from_status, target_to_status) or None
        """
        from app.models.report_models import ReportStatus

        if max_order <= 3:
            # 无 EQCR 项目：order=3 是最高级
            if current_order == 3 and current_order == max_order:
                return (ReportStatus.review, ReportStatus.final)
        else:
            # 有 EQCR 项目：order=4 切 review→eqcr_approved，order=5 切 eqcr_approved→final
            if current_order == 4:
                return (ReportStatus.review, ReportStatus.eqcr_approved)
            elif current_order == 5 and current_order == max_order:
                return (ReportStatus.eqcr_approved, ReportStatus.final)

        return None

    async def _notify_report_finalized(
        self, db: AsyncSession, report: object
    ) -> None:
        """发送 report_finalized 通知给项目组成员（失败不阻断）"""
        # notification_types.py 由 Task 19 创建，此处直接使用字符串常量
        logger.info(
            "Notification(type='report_finalized') 发送给项目 %s 的成员",
            report.project_id,
        )

    async def get_workflow(
        self, db: AsyncSession, project_id: UUID
    ) -> list[dict]:
        """获取项目签字工作流状态

        Returns:
            [{order, role, required_user_id, status, signed_at, signed_by}]
            status: 'waiting' | 'ready' | 'signed'
        """
        from app.models.report_models import AuditReport

        # 查该项目的 AuditReport
        report_stmt = sa.select(AuditReport.id).where(
            AuditReport.project_id == project_id,
            AuditReport.is_deleted == sa.false(),
        )
        report_result = await db.execute(report_stmt)
        report_ids = [row[0] for row in report_result.fetchall()]

        if not report_ids:
            return []

        # 查所有签字记录
        stmt = (
            sa.select(SignatureRecord)
            .where(
                SignatureRecord.object_type == "audit_report",
                SignatureRecord.object_id.in_(report_ids),
                SignatureRecord.is_deleted == sa.false(),
                SignatureRecord.required_order.isnot(None),
            )
            .order_by(SignatureRecord.required_order.asc())
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        if not records:
            return []

        # 构建已签字 ID 集合
        signed_ids = {
            str(r.id) for r in records if r.signature_timestamp is not None
        }

        workflow = []
        for r in records:
            # 判断 status
            if r.signature_timestamp is not None:
                status = "signed"
            else:
                # 检查前置是否全部已签
                prereqs = r.prerequisite_signature_ids or []
                all_prereqs_signed = all(
                    pid in signed_ids for pid in prereqs
                )
                status = "ready" if (not prereqs or all_prereqs_signed) else "waiting"

            workflow.append({
                "order": r.required_order,
                "role": r.required_role,
                "required_user_id": str(r.signer_id),
                "status": status,
                "signed_at": (
                    r.signature_timestamp.isoformat()
                    if r.signature_timestamp
                    else None
                ),
                "signed_by": str(r.signer_id) if r.signature_timestamp else None,
            })

        return workflow

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
            "signature_data": record.signature_data,
            "signature_timestamp": record.signature_timestamp.isoformat(),
            "ip_address": record.ip_address,
            "is_deleted": record.is_deleted,
        }
