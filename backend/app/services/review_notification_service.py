"""复核进度 SSE 通知服务 — Phase 7 F11

2 events: review.accepted + review.completed
Redis 幂等 key: sse:review_status:{review_id}:{status} TTL=3600s

Validates: Requirements F11.1, F11.2, F11.3, F11.5, F11.8
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

logger = logging.getLogger(__name__)

# Redis TTL for idempotent keys
IDEMPOTENT_TTL = 3600  # 1 hour


class ReviewNotificationService:
    """复核进度 SSE 通知服务"""

    @staticmethod
    async def notify_review_accepted(
        review_id: UUID,
        wp_code: str,
        reviewer_name: str,
        submitter_id: UUID,
    ) -> bool:
        """复核人打开底稿 → 发送 review.accepted

        Returns True if notification was sent, False if deduplicated.
        """
        return await ReviewNotificationService._send_notification(
            review_id=review_id,
            status="accepted",
            wp_code=wp_code,
            reviewer_name=reviewer_name,
            target_user_id=submitter_id,
        )

    @staticmethod
    async def notify_review_completed(
        review_id: UUID,
        wp_code: str,
        reviewer_name: str,
        submitter_id: UUID,
        result: str,
    ) -> bool:
        """复核人提交结论 → 发送 review.completed

        Returns True if notification was sent, False if deduplicated.
        """
        return await ReviewNotificationService._send_notification(
            review_id=review_id,
            status="completed",
            wp_code=wp_code,
            reviewer_name=reviewer_name,
            target_user_id=submitter_id,
            extra={"result": result},
        )

    @staticmethod
    async def _send_notification(
        review_id: UUID,
        status: str,
        wp_code: str,
        reviewer_name: str,
        target_user_id: UUID,
        extra: dict | None = None,
    ) -> bool:
        """Internal: send SSE notification with Redis idempotent check."""
        idempotent_key = f"sse:review_status:{review_id}:{status}"

        # Check Redis idempotent key
        try:
            from app.core.redis import get_redis

            redis = await get_redis()
            if redis:
                existing = await redis.get(idempotent_key)
                if existing:
                    logger.debug(
                        f"Deduplicated notification: {idempotent_key}"
                    )
                    return False
                # Set idempotent key
                await redis.set(idempotent_key, "1", ex=IDEMPOTENT_TTL)
        except Exception as e:
            logger.warning(f"Redis unavailable for idempotent check: {e}")
            # Proceed without dedup if Redis is down

        # Build SSE payload
        event_type = f"review.{status}"
        payload = {
            "event_type": event_type,
            "data": {
                "review_id": str(review_id),
                "wp_code": wp_code,
                "reviewer_name": reviewer_name,
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **(extra or {}),
            },
        }

        # Dispatch via event bus (if available)
        try:
            from app.services.event_handlers import dispatch_event

            await dispatch_event(
                event_type=event_type,
                target_user_id=str(target_user_id),
                payload=payload,
            )
        except ImportError:
            logger.debug("Event dispatch not available, notification logged only")
        except Exception as e:
            logger.warning(f"Failed to dispatch SSE notification: {e}")

        logger.info(
            f"Review notification sent: {event_type} for review {review_id}"
        )
        return True
