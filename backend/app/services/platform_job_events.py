"""Platform durable job 的 typed SSE 通知（B4/B5）。

状态 GET 才是重连/刷新后的权威；此事件只用于唤醒前端提前重拉，绝不携带 payload_ref
或任意用户输入，避免把任务参数经项目 SSE 广播给其他成员。
"""
from __future__ import annotations

from app.services.platform_job_service import PlatformJobClaim

EVENT_TYPE = "platform.job.updated"


def broadcast_job_update(
    claim: PlatformJobClaim,
    *,
    status: str,
    current: int | None = None,
    total: int | None = None,
    stage: str | None = None,
    message: str | None = None,
    error_code: str | None = None,
) -> None:
    """best-effort 唤醒同项目客户端；失败不影响 durable 状态的 DB 真相。"""
    try:
        from app.services.event_bus import event_bus

        event_bus.broadcast_raw(
            EVENT_TYPE,
            {
                "project_id": str(claim.project_id),
                "job_id": str(claim.job_id),
                "operation": claim.operation,
                "status": status,
                "current": current,
                "total": total,
                "stage": stage,
                "message": message,
                "error_code": error_code,
            },
        )
    except Exception:  # noqa: BLE001 - SSE 只是加速层，状态端点仍可恢复
        pass
