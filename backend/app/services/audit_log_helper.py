"""审计日志统一写入 helper — V3 收官增强横切组件

提供 append_audit_log 函数作为统一审计日志写入入口，
自动维护 hash_chain（复用 V007 引入的哈希链逻辑）。

调用方：deps.py / time_machine_service / conflict_resolution_service / consol_audit_helper / ...
内部：统一调用 ``audit_chain.head.append_entry``，不再自行读取链尾或计算哈希。

9 种 event_type schema（存储在 details JSONB 中）：
- archived_exception_access: 归档项目例外通道触发
- archive_unarchive: 解除归档
- delete_with_confirm: 删除二次确认通过
- ai_content_lifecycle: AI 内容生成/确认/修订/拒绝
- cross_module_conflict_resolved: 用户调解冲突
- time_machine_restore: 时光机恢复
- consol_lifecycle: 合并关键操作留痕（lock/unlock/抵销审批/recalc/scope变更）
- formula_changed: 公式变更/执行留痕（report/consol 统一入口）
- report_config_changed: 报表配置主模板回填审核留痕（spec D report-config-baseline）
"""

from __future__ import annotations

import uuid
from typing import Literal, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_chain.canonical import (
    GENESIS_HASH,
    hash_v1 as _compute_entry_hash,
)
from app.services.audit_chain.head import append_entry, chain_key_of

__all__ = [
    "AuditLogPayload",
    "EVENT_TYPE_SCHEMAS",
    "EventType",
    "GENESIS_HASH",
    "_compute_entry_hash",
    "append_audit_log",
    "validate_event_type_details",
]

# --------------------------------------------------------------------------
# 类型定义
# --------------------------------------------------------------------------

EventType = Literal[
    "archived_exception_access",
    "archive_unarchive",
    "delete_with_confirm",
    "ai_content_lifecycle",
    "ai_model_config_changed",
    "cross_module_conflict_resolved",
    "time_machine_restore",
    "consol_lifecycle",
    "formula_changed",
    "report_config_changed",
    "onlyoffice_callback_rejected",
    # --- AI Chat Run 哈希链审计（dsh-agent-panel-integration Task 12 / Req 12.6–12.7）---
    "ai_chat_run_lifecycle",
    "ai_chat_access_denied",
    "ai_chat_note_saved",
    "ai_chat_adopt_requested",
    "ai_chat_attachment_cleanup",
    "ai_chat_tool_lifecycle",
    # S2 ADR-CCN-06：门禁逐项确认留痕
    "gate_acknowledgement",
]


class AuditLogPayload(TypedDict):
    """审计日志写入载荷结构。"""

    user_id: uuid.UUID
    project_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict  # 含 event_type 字段


# 8 种 event_type 的 details 必需字段定义
EVENT_TYPE_SCHEMAS: dict[str, set[str]] = {
    "archived_exception_access": {"reason", "approver_id", "endpoint", "original_status"},
    "archive_unarchive": {"reason", "previous_status"},
    "delete_with_confirm": {"object_type", "object_name", "soft_or_hard", "recoverable"},
    "ai_content_lifecycle": {"ai_content_log_id", "action"},
    "ai_model_config_changed": {"action", "model_id", "before", "after", "credential_changed"},
    "cross_module_conflict_resolved": {
        "conflict_id",
        "resolution",
        "upstream_value",
        "manual_value",
        "final_value",
    },
    "time_machine_restore": {
        "from_snapshot_id",
        "to_snapshot_id",
        "instance_type",
        "instance_id",
    },
    "consol_lifecycle": {"sub_action", "before", "after"},
    "formula_changed": {"module", "row_code", "action", "old_formula", "new_formula", "result_value"},
    "report_config_changed": {"sub_action", "standard", "report_type", "row_code", "candidate_id"},
    "onlyoffice_callback_rejected": {"reason"},
    # --- AI Chat Run 审计事件 schemas（Req 12.6/12.7）---
    # 🔴 只存 ID/hash/计数/字节数/时长/error code，禁止记录 token/完整正文/附件内容/未脱敏上下文
    "ai_chat_run_lifecycle": {"run_id", "status", "engine"},
    "ai_chat_access_denied": {"run_id", "denial_code", "resource_type"},
    "ai_chat_note_saved": {"run_id", "message_id", "note_id", "content_hash"},
    "ai_chat_adopt_requested": {"run_id", "message_id", "content_hash", "host_type"},
    "ai_chat_attachment_cleanup": {"run_id", "attachment_id", "status", "bytes_freed"},
    # Property 32：tool call 审计（started + finished/failed 成对）
    "ai_chat_tool_lifecycle": {"run_id", "tool_call_id", "tool_name", "status"},
    # S2 ADR-CCN-06：门禁逐项确认留痕
    "gate_acknowledgement": {"check_name"},
}

# ``_compute_entry_hash`` 与 ``GENESIS_HASH`` 为旧调用方保留兼容导出；
# 实现来自 audit_chain.canonical，不再维护第二份哈希算法。


def validate_event_type_details(details: dict) -> None:
    """校验 details 中 event_type 对应的必需字段是否齐全。

    如果 details 不含 event_type 或 event_type 不在已知列表中则跳过校验。
    """
    event_type = details.get("event_type")
    if not event_type or event_type not in EVENT_TYPE_SCHEMAS:
        return

    required_fields = EVENT_TYPE_SCHEMAS[event_type]
    missing = required_fields - set(details.keys())
    if missing:
        raise ValueError(
            f"event_type '{event_type}' 缺少必需字段: {sorted(missing)}"
        )


# --------------------------------------------------------------------------
# 公共 API
# --------------------------------------------------------------------------


async def append_audit_log(db: AsyncSession, payload: AuditLogPayload) -> uuid.UUID:
    """统一审计日志写入入口，自动维护 hash_chain。

    直接写入数据库（同步落库），适用于需要立即持久化的场景
    （如归档例外通道、删除确认、冲突调解等关键操作）。

    参数:
        db: 异步数据库会话
        payload: 审计日志载荷（含 user_id / project_id / action / resource_type / resource_id / details）

    返回:
        新创建的审计日志条目 UUID

    异常:
        ValueError: details 中 event_type 对应的必需字段缺失
    """
    details = dict(payload.get("details") or {})
    validate_event_type_details(details)

    project_id = payload.get("project_id")
    project_text = str(project_id) if project_id else None
    year_raw = details.get("year", details.get("_year"))
    try:
        year = int(year_raw) if year_raw not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise ValueError(f"审计日志 year 无效: {year_raw!r}") from exc

    entry = await append_entry(
        db,
        chain_key_of(project_text),
        user_id=payload.get("user_id"),
        action_type=payload["action"],
        object_type=payload["resource_type"],
        resource_id=payload.get("resource_id"),
        project_id=project_text,
        year=year,
        payload=details,
    )
    return entry.id
