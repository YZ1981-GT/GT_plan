"""WorkflowGate — 工作流状态门禁（Req 4.3, 4.4, 9.1, 9.2, 9.3）

职责：
  - classify(items): 按底稿状态分类 → blocked / revert_needed / writable
  - revert_if_under_review(db, wp_id, user): 有编制权时回退为编制中+审计日志；无权则不改

核心逻辑：
  - review_passed / archived / locked → blocked（Req 9.1: refuse import, mark blocked_by_status）
  - under_review → revert_needed（需回退为编制中才可写入）
  - 其余（draft / edit_complete / revision_required 等）→ writable

铁律：
  - service 只 flush 不 commit
  - 门禁只分类，不阻断——调用方（BulkImport_Service）决定如何处理分类结果
  - 无编制权限时 SHALL NOT 改变任何底稿状态或写入任何数据（Req 9.3）
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.models.workpaper_models import WpFileStatus, WorkingPaper
from app.services.permission_service import Permission, check_permission

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 类型定义
# ---------------------------------------------------------------------------

WorkflowClassification = Literal["blocked", "revert_needed", "writable"]

# 被视为"锁定"的状态集合（review_passed / archived + 任何 locked 标识）
_BLOCKED_STATUSES: set[str] = {
    WpFileStatus.review_passed.value,
    WpFileStatus.archived.value,
    # 兼容旧值
    WpFileStatus.review_level1_passed.value,
    WpFileStatus.review_level2_passed.value,
}

_REVERT_NEEDED_STATUSES: set[str] = {
    WpFileStatus.under_review.value,
}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ClassifiedItem:
    """单个底稿的门禁分类结果。"""

    wp_id: uuid.UUID
    status: str  # 原始 status 值
    classification: WorkflowClassification
    reason: str | None = None  # blocked 时记录原因（如 'review_passed'）


# ---------------------------------------------------------------------------
# WorkflowGate
# ---------------------------------------------------------------------------


class WorkflowGate:
    """工作流状态门禁。

    classify() 按底稿当前状态分类，返回每个 wp_id 的分类结果。
    revert_if_under_review() 在有编制权时回退 under_review → draft 并记审计日志。
    """

    def classify(
        self,
        items: list[dict[str, Any]],
    ) -> dict[uuid.UUID, ClassifiedItem]:
        """按底稿状态分类。

        Args:
            items: 每个 dict 需包含 'wp_id' (UUID) 和 'status' (str) 字段。
                   status 为 working_paper.status 的值。

        Returns:
            wp_id → ClassifiedItem 映射。
        """
        result: dict[uuid.UUID, ClassifiedItem] = {}

        for item in items:
            wp_id = item["wp_id"]
            status = item.get("status", "")

            if status in _BLOCKED_STATUSES:
                result[wp_id] = ClassifiedItem(
                    wp_id=wp_id,
                    status=status,
                    classification="blocked",
                    reason=status,
                )
            elif status in _REVERT_NEEDED_STATUSES:
                result[wp_id] = ClassifiedItem(
                    wp_id=wp_id,
                    status=status,
                    classification="revert_needed",
                )
            else:
                result[wp_id] = ClassifiedItem(
                    wp_id=wp_id,
                    status=status,
                    classification="writable",
                )

        return result

    async def revert_if_under_review(
        self,
        db: AsyncSession,
        wp_id: uuid.UUID,
        user: User,
    ) -> bool:
        """将 under_review 底稿回退为编制中（draft）。

        条件：用户必须有编制权限（WORKPAPER_WRITE）。
        无编制权限时不改状态、不写审计日志（Req 9.3）。

        Args:
            db: 异步数据库会话
            wp_id: 目标底稿 ID
            user: 当前操作用户

        Returns:
            True = 成功回退；False = 无权限未回退
        """
        # ① 检查用户是否有编制权限
        role = user.role.value if hasattr(user.role, "value") else str(user.role)
        if not check_permission(role, Permission.WORKPAPER_WRITE):
            logger.info(
                "WorkflowGate: 用户 %s (role=%s) 无编制权限，不回退 wp_id=%s",
                user.id,
                role,
                wp_id,
            )
            return False

        # ② 回退状态 under_review → draft
        stmt = (
            update(WorkingPaper)
            .where(
                WorkingPaper.id == wp_id,
                WorkingPaper.status == WpFileStatus.under_review,
            )
            .values(status=WpFileStatus.draft)
        )
        result = await db.execute(stmt)
        await db.flush()

        if result.rowcount == 0:  # type: ignore[union-attr]
            # 状态已经不是 under_review（可能并发已回退），视为成功
            logger.info(
                "WorkflowGate: wp_id=%s 状态已非 under_review，跳过回退",
                wp_id,
            )
            return True

        # ③ 写审计日志（Req 4.3 / 9.2）
        await self._write_revert_audit_log(db, wp_id, user)

        logger.info(
            "WorkflowGate: 用户 %s 回退 wp_id=%s 从 under_review → draft",
            user.id,
            wp_id,
        )
        return True

    async def _write_revert_audit_log(
        self,
        db: AsyncSession,
        wp_id: uuid.UUID,
        user: User,
    ) -> None:
        """写入状态回退审计日志。

        复用 audit_log_helper.append_audit_log，event_type 不在既有 schema 中
        则不校验详情字段（audit_log_helper 对未知 event_type 跳过校验）。
        """
        try:
            from app.services.audit_log_helper import append_audit_log

            # 查询底稿所属项目
            project_id = (
                await db.execute(
                    select(WorkingPaper.project_id).where(WorkingPaper.id == wp_id)
                )
            ).scalar_one_or_none()

            await append_audit_log(
                db,
                {
                    "user_id": user.id,
                    "project_id": project_id,
                    "action": "bulk_import_revert_status",
                    "resource_type": "working_paper",
                    "resource_id": str(wp_id),
                    "details": {
                        "event_type": "bulk_import_revert_status",
                        "from_status": WpFileStatus.under_review.value,
                        "to_status": WpFileStatus.draft.value,
                        "reason": "批量导入前自动回退复核中状态为编制中",
                    },
                },
            )
        except Exception:
            # 审计日志写入失败不阻断主流程（fail-soft）
            logger.warning(
                "WorkflowGate: 审计日志写入失败 wp_id=%s",
                wp_id,
                exc_info=True,
            )
