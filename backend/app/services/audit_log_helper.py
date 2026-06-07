"""审计日志统一写入 helper — V3 收官增强横切组件

提供 append_audit_log 函数作为统一审计日志写入入口，
自动维护 hash_chain（复用 V007 引入的哈希链逻辑）。

调用方：deps.py / time_machine_service / conflict_resolution_service / consol_audit_helper / ...
内部：复用既有 hash_chain 逻辑（audit_log_writer_worker._compute_entry_hash）

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

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log_models import AuditLogEntry

# --------------------------------------------------------------------------
# 类型定义
# --------------------------------------------------------------------------

EventType = Literal[
    "archived_exception_access",
    "archive_unarchive",
    "delete_with_confirm",
    "ai_content_lifecycle",
    "cross_module_conflict_resolved",
    "time_machine_restore",
    "consol_lifecycle",
    "formula_changed",
    "report_config_changed",
    "onlyoffice_callback_rejected",
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
}

# 创世哈希（与 audit_log_writer_worker 保持一致）
GENESIS_HASH = "0" * 64


# --------------------------------------------------------------------------
# 内部工具函数
# --------------------------------------------------------------------------


def _compute_entry_hash(
    ts: str,
    user_id: str,
    action_type: str,
    object_id: str | None,
    payload_json: str,
    prev_hash: str,
) -> str:
    """计算审计日志条目哈希（与 audit_log_writer_worker 保持一致）。

    entry_hash = sha256(ts|user_id|action_type|object_id|payload_json|prev_hash)
    """
    raw = f"{ts}|{user_id or ''}|{action_type}|{object_id or ''}|{payload_json}|{prev_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _get_prev_hash(db: AsyncSession, project_id: str | None) -> str:
    """获取指定 project_id 链的最新 entry_hash 作为新条目的 prev_hash。

    每个 project_id 独立链；project_id 为 None 时使用全局链。
    兼容 SQLite 测试环境。
    """
    try:
        from app.core.config import settings

        is_postgres = settings.DATABASE_URL.startswith("postgresql")
    except Exception:
        is_postgres = False

    try:
        if project_id:
            if is_postgres:
                stmt = (
                    select(AuditLogEntry.entry_hash)
                    .where(AuditLogEntry.payload["project_id"].astext == project_id)
                    .order_by(desc(AuditLogEntry.ts))
                    .limit(1)
                )
            else:
                # SQLite fallback: 使用 json_extract
                from sqlalchemy import text

                stmt = (
                    select(AuditLogEntry.entry_hash)
                    .where(text("json_extract(payload, '$.project_id') = :pid"))
                    .params(pid=project_id)
                    .order_by(desc(AuditLogEntry.ts))
                    .limit(1)
                )
        else:
            if is_postgres:
                stmt = (
                    select(AuditLogEntry.entry_hash)
                    .where(
                        AuditLogEntry.payload["project_id"].astext.is_(None)
                        | ~AuditLogEntry.payload.has_key("project_id")
                    )
                    .order_by(desc(AuditLogEntry.ts))
                    .limit(1)
                )
            else:
                from sqlalchemy import text

                stmt = (
                    select(AuditLogEntry.entry_hash)
                    .where(text("json_extract(payload, '$.project_id') IS NULL"))
                    .order_by(desc(AuditLogEntry.ts))
                    .limit(1)
                )

        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return row if row else GENESIS_HASH
    except Exception:
        return GENESIS_HASH


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
    # 校验 event_type schema
    details = payload.get("details") or {}
    validate_event_type_details(details)

    now = datetime.now(timezone.utc)
    ts_str = now.isoformat()
    user_id_str = str(payload["user_id"]) if payload.get("user_id") else ""
    project_id_str = str(payload["project_id"]) if payload.get("project_id") else None
    resource_id_str = payload.get("resource_id") or ""

    # 构建 payload JSONB 内容（注入 project_id 以便后续按项目查询）
    log_payload: dict[str, Any] = {**details}
    if project_id_str:
        log_payload["project_id"] = project_id_str

    payload_json = json.dumps(log_payload, sort_keys=True, ensure_ascii=False, default=str)

    # 获取链上最新 hash
    prev_hash = await _get_prev_hash(db, project_id_str)

    # 计算 entry_hash
    entry_hash = _compute_entry_hash(
        ts_str,
        user_id_str,
        payload["action"],
        resource_id_str,
        payload_json,
        prev_hash,
    )

    # 构建 ORM 对象
    entry_id = uuid.uuid4()

    # object_id 是 UUID 列；resource_id 可能是非 UUID 字符串（如 row_code）
    # 非 UUID 时 object_id 设 None，但 resource_id_str 仍参与 hash 计算保证完整性
    try:
        object_id_val = uuid.UUID(resource_id_str) if resource_id_str else None
    except (ValueError, AttributeError):
        object_id_val = None

    log_entry = AuditLogEntry(
        id=entry_id,
        ts=now,
        user_id=payload["user_id"] if payload.get("user_id") else None,
        session_id=None,
        action_type=payload["action"],
        object_type=payload["resource_type"],
        object_id=object_id_val,
        payload=log_payload,
        ip=None,
        ua=None,
        trace_id=None,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )

    db.add(log_entry)
    await db.flush()

    return entry_id
