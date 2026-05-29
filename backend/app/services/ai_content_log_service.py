"""AI 内容生命周期服务 — V3 收官增强 Req 6.1

提供 ai_content_log 表的生命周期管理函数：

- create(...)               写入 pending 记录（由 wrap_ai_output 调用，6.2 接入）
- confirm(log_id, ...)      标记为 confirmed
- revise(log_id, ..., revised_content)  标记为 revised + 写入 revised_content
- reject(log_id, ...)       标记为 rejected
- list_by_project(...)      全量列表（含状态/类型过滤）
- list_pending_by_project(...)  仅 pending（6.3 守门规则用）
- count_pending_by_project(...)  pending 计数（前端 badge 用）

每次状态变更（generate / confirm / revise / reject）都通过
``audit_log_helper.append_audit_log`` 写入 ``event_type='ai_content_lifecycle'``
事件，复用 V007 哈希链。

依赖：
- backend/app/models/v3_refinement_models.py:AiContentLog
- backend/app/services/audit_log_helper.py:append_audit_log
- backend/migrations/V017__v3_refinement_tables.sql

Validates: Requirements 6.1, AC 6.1~6.4 (生命周期 + 审计写入)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v3_refinement_models import AiContentLog
from app.services.audit_log_helper import append_audit_log

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ConfirmAction = Literal["pending", "confirmed", "revised", "rejected"]
LIFECYCLE_ACTION = Literal["generate", "confirm", "revise", "reject"]

VALID_CONFIRM_ACTIONS: set[str] = {"pending", "confirmed", "revised", "rejected"}

# 记录不存在 / 已处理过 等业务异常使用 ValueError，由 router 层转 422


class AiContentLogNotFoundError(ValueError):
    """AI 内容日志记录不存在。"""


class AiContentLogAlreadyProcessedError(ValueError):
    """AI 内容日志已处理过（confirm_action 已经不是 pending），不可重复确认/修订/拒绝。"""


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


async def _write_lifecycle_audit(
    *,
    db: AsyncSession,
    ai_log: AiContentLog,
    user_id: uuid.UUID,
    action: str,
) -> None:
    """统一写入 ai_content_lifecycle 审计日志事件。"""
    await append_audit_log(
        db,
        {
            "user_id": user_id,
            "project_id": ai_log.project_id,
            "action": f"ai_content_{action}",
            "resource_type": "ai_content_log",
            "resource_id": str(ai_log.id),
            "details": {
                "event_type": "ai_content_lifecycle",
                "ai_content_log_id": str(ai_log.id),
                "action": action,
            },
        },
    )


async def _load_pending_or_raise(
    db: AsyncSession, log_id: uuid.UUID
) -> AiContentLog:
    """加载指定 log，校验存在 + 当前为 pending。"""
    result = await db.execute(
        select(AiContentLog).where(AiContentLog.id == log_id)
    )
    ai_log = result.scalar_one_or_none()
    if ai_log is None:
        raise AiContentLogNotFoundError("AI 内容记录不存在")
    if ai_log.confirm_action != "pending":
        raise AiContentLogAlreadyProcessedError("AI 内容已处理过，不可重复确认")
    return ai_log


# ---------------------------------------------------------------------------
# 公共 API — 生命周期写入
# ---------------------------------------------------------------------------


async def create(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    instance_type: str,
    instance_id: uuid.UUID,
    target_cell: str | None,
    model: str,
    prompt_hash: str | None,
    content_hash: str,
    generated_content: str,
    confidence: Decimal | float | None = None,
    wp_id: uuid.UUID | None = None,
) -> AiContentLog:
    """写入 pending 状态的 AI 内容日志。

    用于 wrap_ai_output 强制溯源（6.2 接入）。

    参数:
        db: 异步数据库会话
        project_id: 所属项目 UUID
        user_id: 触发生成的用户 UUID（通常是当前登录用户）
        instance_type: 业务实例类型（'workpaper' / 'adjustment' / 'misstatement' /
            'disclosure' / 'risk_assessment' 等），用于在 target_cell 中前缀化保存
        instance_id: 业务实例 UUID
        target_cell: 字段定位（如 'narrative' / 'description' / 'cell_A1'）
        model: 生成模型标识（如 'qwen3.5-27b'）
        prompt_hash: 提示词 SHA-256 哈希（可空）
        content_hash: 生成内容 SHA-256 哈希
        generated_content: 生成内容原文
        confidence: 模型置信度 [0.0, 1.0]，可空
        wp_id: 关联底稿 UUID（可空，仅 instance_type='workpaper' 时填）

    返回:
        新创建的 AiContentLog，confirm_action='pending'。

    副作用:
        写入一条 audit_log，event_type='ai_content_lifecycle' action='generate'。
    """
    # 标准化 target_cell：未提供时根据 instance_type/instance_id 拼装
    # 已提供时透传（保留调用方语义）
    if target_cell is None:
        encoded_target = f"{instance_type}:{instance_id}"
    else:
        encoded_target = f"{instance_type}:{instance_id}:{target_cell}"

    confidence_decimal: Decimal | None
    if confidence is None:
        confidence_decimal = None
    elif isinstance(confidence, Decimal):
        confidence_decimal = confidence
    else:
        confidence_decimal = Decimal(str(confidence))

    ai_log = AiContentLog(
        id=uuid.uuid4(),
        project_id=project_id,
        wp_id=wp_id,
        user_id=user_id,
        content_hash=content_hash,
        target_cell=encoded_target,
        prompt_hash=prompt_hash,
        model=model,
        confidence=confidence_decimal,
        generated_content=generated_content,
        revised_content=None,
        confirm_action="pending",
        confirmed_by=None,
        confirmed_at=None,
        # 显式设置 generated_at（DB DEFAULT NOW() 仅 PG 生效，
        # 单元测试 SQLite 环境下需应用层提供值；PG 生产环境此值仍由 DB 兜底）
        generated_at=datetime.now(timezone.utc),
    )
    db.add(ai_log)
    await db.flush()

    await _write_lifecycle_audit(
        db=db, ai_log=ai_log, user_id=user_id, action="generate"
    )

    return ai_log


async def confirm(
    *,
    db: AsyncSession,
    log_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AiContentLog:
    """将 pending 记录标记为 confirmed。

    校验当前 confirm_action='pending'，否则抛 AiContentLogAlreadyProcessedError。

    副作用：写 audit_log，event_type='ai_content_lifecycle' action='confirm'。
    """
    ai_log = await _load_pending_or_raise(db, log_id)
    ai_log.confirm_action = "confirmed"
    ai_log.confirmed_by = user_id
    ai_log.confirmed_at = datetime.now(timezone.utc)
    await db.flush()

    await _write_lifecycle_audit(
        db=db, ai_log=ai_log, user_id=user_id, action="confirm"
    )
    return ai_log


async def revise(
    *,
    db: AsyncSession,
    log_id: uuid.UUID,
    user_id: uuid.UUID,
    revised_content: str,
) -> AiContentLog:
    """将 pending 记录标记为 revised + 写入 revised_content。

    校验当前 confirm_action='pending'，否则抛 AiContentLogAlreadyProcessedError。

    副作用：写 audit_log，event_type='ai_content_lifecycle' action='revise'。
    """
    if revised_content is None:
        raise ValueError("revised_content 不能为 None")

    ai_log = await _load_pending_or_raise(db, log_id)
    ai_log.confirm_action = "revised"
    ai_log.revised_content = revised_content
    ai_log.confirmed_by = user_id
    ai_log.confirmed_at = datetime.now(timezone.utc)
    await db.flush()

    await _write_lifecycle_audit(
        db=db, ai_log=ai_log, user_id=user_id, action="revise"
    )
    return ai_log


async def reject(
    *,
    db: AsyncSession,
    log_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AiContentLog:
    """将 pending 记录标记为 rejected。

    校验当前 confirm_action='pending'，否则抛 AiContentLogAlreadyProcessedError。
    revised_content 保持 NULL（拒绝场景下不需要修订内容）。

    副作用：写 audit_log，event_type='ai_content_lifecycle' action='reject'。
    """
    ai_log = await _load_pending_or_raise(db, log_id)
    ai_log.confirm_action = "rejected"
    ai_log.confirmed_by = user_id
    ai_log.confirmed_at = datetime.now(timezone.utc)
    # revised_content 保持 NULL（语义：拒绝该 AI 输出，不接受任何形式）
    await db.flush()

    await _write_lifecycle_audit(
        db=db, ai_log=ai_log, user_id=user_id, action="reject"
    )
    return ai_log


# ---------------------------------------------------------------------------
# 公共 API — 查询
# ---------------------------------------------------------------------------


async def list_by_project(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    status: str | None = None,
    instance_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AiContentLog]:
    """按项目列出 AI 内容日志，可选状态 + 业务实例类型过滤。

    参数:
        project_id: 项目 UUID
        status: 'pending' / 'confirmed' / 'revised' / 'rejected'，None=不过滤
        instance_type: 'workpaper' / 'adjustment' 等，匹配 target_cell 前缀
        limit: 单次最多返回条数（默认 100）
        offset: 分页偏移（默认 0）

    返回:
        AiContentLog 列表，按 generated_at DESC 排序。
    """
    if status is not None and status not in VALID_CONFIRM_ACTIONS:
        raise ValueError(
            f"status 必须是以下之一: {sorted(VALID_CONFIRM_ACTIONS)}, 收到 {status!r}"
        )

    stmt = select(AiContentLog).where(AiContentLog.project_id == project_id)
    if status is not None:
        stmt = stmt.where(AiContentLog.confirm_action == status)
    if instance_type is not None:
        # target_cell 形如 'workpaper:<uuid>:<field>' / 'workpaper:<uuid>'
        stmt = stmt.where(AiContentLog.target_cell.like(f"{instance_type}:%"))

    stmt = (
        stmt.order_by(AiContentLog.generated_at.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_pending_by_project(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    limit: int = 20,
) -> list[AiContentLog]:
    """仅返回 pending 状态记录（守门规则 / 顶部 banner 用）。

    参数:
        project_id: 项目 UUID
        limit: 最多返回条数（默认 20，避免一次性拉过多）

    返回:
        confirm_action='pending' 的 AiContentLog 列表，按 generated_at DESC。
    """
    stmt = (
        select(AiContentLog)
        .where(
            AiContentLog.project_id == project_id,
            AiContentLog.confirm_action == "pending",
        )
        .order_by(AiContentLog.generated_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_pending_by_project(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
) -> int:
    """pending 计数（前端 badge 用）。"""
    stmt = (
        select(func.count())
        .select_from(AiContentLog)
        .where(
            AiContentLog.project_id == project_id,
            AiContentLog.confirm_action == "pending",
        )
    )
    result = await db.execute(stmt)
    count = result.scalar_one()
    return int(count or 0)
