"""
confirmation_service — 函证管理服务（stub）

当前为 stub 实现，后续 O1 spec（7 循环函证统一管理中心）将完善。
F6 spec workpaper-d-sales-cycle task 2.11: 函证回函 → 触发 D2 stale 传播
F spec workpaper-f-purchase-inventory task 2.20: 通用化 wp_code 参数,
支持 F0 函证 → F2 反向回填 (经 cross_wp_references CW-176 触发 stale 传播).
G spec workpaper-g-investment-cycle task 2.21: 注册 G0 函证 → G7 长期股权投资反向回填
(经 cross_wp_references CW-267 触发 stale 传播 / 与 D0/F0 同模式).
"""
from __future__ import annotations

from uuid import UUID

from app.services.event_bus import event_bus
from app.models.audit_platform_schemas import EventPayload, EventType


async def apply_confirmation_result(
    project_id: UUID,
    year: int,
    confirmation_id: UUID,
    *,
    reply_status: str = "confirmed_match",
    reply_amount: float | None = None,
    wp_code: str = "D0",
) -> dict:
    """
    应用函证回函结果。

    当前为 stub 实现：
    - 真实业务逻辑（更新 confirmation_result 表、计算差异等）待 O1 spec 实现
    - 本方法末尾 emit CONFIRMATION_RECEIVED 事件，触发下游 stale 传播链路

    Args:
        project_id: 项目 ID
        year: 审计年度
        confirmation_id: 函证记录 ID
        reply_status: 回函状态（confirmed_match/confirmed_mismatch/no_reply/returned）
        reply_amount: 回函确认金额
        wp_code: 函证来源底稿编码 (D0=应收函证 / F0=采购存货函证 / E0=货币资金函证
                 / G0=投资函证 ...).
                 默认 "D0" 保持向下兼容; F0/G0 函证场景需显式传入对应 wp_code,
                 stale 传播将沿 cross_wp_references 中 source_wp=对应 wp_code 的条目下游进行
                 (含 CW-176 F0→F2 反向回填 / CW-267 G0→G7 反向回填).

    Returns:
        dict with status info
    """
    # TODO: O1 spec 实现真实业务逻辑（更新 DB、计算差异、生成差异调节表等）
    result = {
        "confirmation_id": str(confirmation_id),
        "reply_status": reply_status,
        "reply_amount": reply_amount,
        "wp_code": wp_code,
        "applied": True,
    }

    # F6 spec workpaper-d-sales-cycle task 2.11: 函证回函 → 触发 D2 stale 传播
    # F spec workpaper-f-purchase-inventory task 2.20: 通用化 wp_code,
    # 同一事件类型也用于 F0 → F2 反向回填.
    # G spec workpaper-g-investment-cycle task 2.21: G0 → G7 长期股权投资反向回填
    # 同样复用 CONFIRMATION_RECEIVED 事件 + wp_code='G0' 路由分发.
    await event_bus.publish_immediate(EventPayload(
        event_type=EventType.CONFIRMATION_RECEIVED,
        project_id=project_id,
        year=year,
        extra={"wp_code": wp_code, "confirmation_id": str(confirmation_id)},
    ))

    return result
