"""二次密码验证端点 — Phase 6 F6

提供 POST /api/auth/verify-password 端点：
- 验证密码 → 生成 UUID v4 token → Redis 存储（TTL=300s）
- 失败计数 + 锁定机制（5 次失败锁定 30 分钟）
- require_confirmation_token 依赖函数（一次性消费 token）

Validates: Requirements F6.1, F6.2, F6.3, F6.4, F6.5, F6.8
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import verify_password
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 配置常量
CONFIRM_TOKEN_TTL = 300  # 5 分钟
CONFIRM_FAIL_TTL = 1800  # 30 分钟
MAX_ATTEMPTS = settings.LOGIN_MAX_ATTEMPTS  # 5
LOCK_MINUTES = settings.LOGIN_LOCK_MINUTES  # 30


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------


class PasswordVerifyRequest(BaseModel):
    password: str


# ---------------------------------------------------------------------------
# POST /api/auth/verify-password
# ---------------------------------------------------------------------------


@router.post("/verify-password")
async def verify_password_endpoint(
    body: PasswordVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis: Redis | None = Depends(get_redis),
) -> dict:
    """验证密码并返回一次性 confirmation_token。

    成功: { confirmation_token, expires_in: 300 }
    失败: 401 + 失败计数
    锁定: 423 + locked_until
    """
    if redis is None:
        raise HTTPException(status_code=503, detail={"message": "服务暂时不可用", "message_en": "Service temporarily unavailable"})

    user_id = str(current_user.id)
    fail_key = f"confirm_fail:{user_id}"

    # 检查是否已锁定
    fail_count_raw = await redis.get(fail_key)
    fail_count = int(fail_count_raw) if fail_count_raw else 0

    if fail_count >= MAX_ATTEMPTS:
        # 获取 TTL 计算锁定到期时间
        ttl = await redis.ttl(fail_key)
        locked_until = datetime.now(timezone.utc) + timedelta(seconds=max(ttl, 0))
        raise HTTPException(
            status_code=423,
            detail={
                "detail": "Account locked",
                "locked_until": locked_until.isoformat(),
            },
        )

    # 验证密码
    if not verify_password(body.password, current_user.hashed_password):
        # 递增失败计数
        new_count = await redis.incr(fail_key)
        if new_count == 1:
            await redis.expire(fail_key, CONFIRM_FAIL_TTL)

        attempts_remaining = max(0, MAX_ATTEMPTS - new_count)

        # 写入审计日志
        await _write_audit_log(
            db, current_user.id, "password_verify_failed",
            {"attempts_remaining": attempts_remaining},
        )

        raise HTTPException(
            status_code=401,
            detail={
                "detail": "Invalid password",
                "attempts_remaining": attempts_remaining,
            },
        )

    # 密码正确 — 清除失败计数
    await redis.delete(fail_key)

    # 生成 confirmation_token
    token = str(uuid.uuid4())
    token_key = f"confirm:{token}"
    await redis.setex(token_key, CONFIRM_TOKEN_TTL, user_id)

    # 写入审计日志
    await _write_audit_log(
        db, current_user.id, "password_verify_success",
        {"token_id": token[:8]},  # 仅记录前 8 位
    )

    return {
        "confirmation_token": token,
        "expires_in": CONFIRM_TOKEN_TTL,
    }


# ---------------------------------------------------------------------------
# require_confirmation_token 依赖
# ---------------------------------------------------------------------------


async def require_confirmation_token(
    request: Request,
    current_user: User = Depends(get_current_user),
    redis: Redis | None = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> None:
    """从 X-Confirmation-Token header 验证 token 有效性（一次性消费）。

    - Token 缺失 → 403
    - Token 过期/已使用 → 403
    - Redis 不可用 → 503
    - 成功/失败均写入 audit_log
    """
    if redis is None:
        raise HTTPException(status_code=503, detail={"message": "服务暂时不可用", "message_en": "Service temporarily unavailable"})

    token = request.headers.get("X-Confirmation-Token")
    if not token:
        await _write_audit_log(
            db, current_user.id, "confirmation_token_missing",
            {"path": str(request.url.path)},
        )
        raise HTTPException(status_code=403, detail="X-Confirmation-Token header required")

    token_key = f"confirm:{token}"

    # GETDEL 原子操作：获取并删除（一次性使用）
    stored_user_id = await redis.getdel(token_key)

    if stored_user_id is None:
        await _write_audit_log(
            db, current_user.id, "confirmation_token_invalid",
            {"token_prefix": token[:8], "path": str(request.url.path)},
        )
        raise HTTPException(status_code=403, detail={"message": "令牌已过期或已使用", "message_en": "Token expired or already consumed"})

    # 验证 token 属于当前用户
    if stored_user_id != str(current_user.id):
        await _write_audit_log(
            db, current_user.id, "confirmation_token_user_mismatch",
            {"token_prefix": token[:8], "path": str(request.url.path)},
        )
        raise HTTPException(status_code=403, detail={"message": "令牌已过期或已使用", "message_en": "Token expired or already consumed"})

    # 成功 — 写入审计日志
    await _write_audit_log(
        db, current_user.id, "confirmation_token_consumed",
        {"token_prefix": token[:8], "path": str(request.url.path)},
    )


# ---------------------------------------------------------------------------
# 审计日志辅助
# ---------------------------------------------------------------------------


async def _write_audit_log(
    db: AsyncSession,
    user_id: uuid.UUID,
    action: str,
    details: dict,
) -> None:
    """写入审计日志（best-effort，不阻断主流程）。"""
    try:
        import json
        from sqlalchemy import text
        await db.execute(
            text(
                "INSERT INTO app_audit_log (id, user_id, action, details, created_at) "
                "VALUES (:id, :user_id, :action, CAST(:details AS JSONB), NOW())"
            ),
            {
                "id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "action": action,
                "details": json.dumps(details, ensure_ascii=False, default=str),
            },
        )
        await db.commit()
    except Exception as e:
        logger.warning("Failed to write audit log: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
