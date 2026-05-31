"""公式审计日志 API — 记录公式变更历史，满足审计留痕要求

数据源：audit_log_entries 哈希链（action_type='formula.changed'）
  - payload JSONB 含 project_id / module / row_code / action / old_formula / new_formula / result_value / trace
  - 写入统一走 audit_log_helper.append_audit_log（Task 14 已收口）

API:
  GET  /api/formula-audit-log/{project_id}/{year}  — 查询公式变更历史（前端零改动）
  POST /api/formula-audit-log/{project_id}/{year}  — 记录一条日志（委托 append_audit_log）
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/api/formula-audit-log", tags=["formula-audit-log"])


class LogEntry(BaseModel):
    module: str = 'report'
    row_code: str
    action: str  # create | update | delete | execute
    old_formula: str = ''
    new_formula: str = ''
    result_value: float | None = None
    trace: list | None = None


class RollbackRequest(BaseModel):
    """一键回滚请求体"""
    row_code: str
    module: str = 'report'
    target_formula: str  # 要回滚到的公式（old_formula）
    source_log_id: str = ''  # 来源日志 ID（留痕用）


@router.get("/{project_id}/{year}")
async def get_audit_log(
    project_id: str, year: int,
    module: str = '',
    row_code: str = '',
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """查询公式变更历史 — 改查 audit_log_entries WHERE action_type='formula.changed'。

    payload JSONB 过滤 project_id / module / row_code。
    返回结构与旧 formula_audit_log 表完全一致（前端零改动）。
    year 参数保留（API 路径兼容）但新哈希链不存 year 字段。
    """
    # 检测数据库方言（PG 用 ->>，SQLite 用 json_extract）
    is_pg = _is_postgres(db)

    if is_pg:
        # PostgreSQL: payload JSONB ->> 操作符
        query = """
            SELECT id, payload, ts
            FROM audit_log_entries
            WHERE action_type = 'formula.changed'
              AND payload->>'project_id' = :pid
        """
    else:
        # SQLite: json_extract 函数
        query = """
            SELECT id, payload, ts
            FROM audit_log_entries
            WHERE action_type = 'formula.changed'
              AND json_extract(payload, '$.project_id') = :pid
        """
    params: dict = {"pid": project_id}

    # payload JSONB 过滤 module
    if module:
        if is_pg:
            query += " AND payload->>'module' = :mod"
        else:
            query += " AND json_extract(payload, '$.module') = :mod"
        params["mod"] = module

    # payload JSONB 过滤 row_code
    if row_code:
        if is_pg:
            query += " AND payload->>'row_code' = :rc"
        else:
            query += " AND json_extract(payload, '$.row_code') = :rc"
        params["rc"] = row_code

    query += " ORDER BY ts DESC LIMIT :lim"
    params["lim"] = limit

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    # 映射为与旧表完全一致的返回结构
    return [
        {
            "id": str(r[0]),
            "module": _parse_payload(r[1]).get("module", "report"),
            "row_code": _parse_payload(r[1]).get("row_code", ""),
            "action": _parse_payload(r[1]).get("action", ""),
            "old_formula": _parse_payload(r[1]).get("old_formula", ""),
            "new_formula": _parse_payload(r[1]).get("new_formula", ""),
            "result_value": _safe_float(_parse_payload(r[1]).get("result_value")),
            "trace": _parse_payload(r[1]).get("trace"),
            "created_at": str(r[2]) if r[2] else None,
        }
        for r in rows
    ]


def _safe_float(val) -> float | None:
    """安全转换 result_value 为 float，无效值返回 None。"""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_payload(raw) -> dict:
    """将 payload 解析为 dict（兼容 PG JSONB 返回 dict / SQLite 返回 JSON 字符串）。"""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _is_postgres(db: AsyncSession) -> bool:
    """检测当前数据库方言是否为 PostgreSQL。"""
    try:
        dialect_name = db.bind.dialect.name if db.bind else ""
        return dialect_name == "postgresql"
    except Exception:
        # 回退：尝试从 settings 判断
        try:
            from app.core.config import settings
            return settings.DATABASE_URL.startswith("postgresql")
        except Exception:
            return True  # 默认假设 PG（生产环境）


@router.post("/{project_id}/{year}")
async def add_audit_log(
    project_id: str, year: int,
    body: LogEntry,
    db: AsyncSession = Depends(get_db),
):
    """记录公式变更日志 — 委托 append_audit_log 写入哈希链。"""
    from app.services.audit_log_helper import append_audit_log

    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        pid = None

    await append_audit_log(db, {
        "user_id": uuid.UUID("00000000-0000-0000-0000-000000000000"),  # POST 端点无 current_user 上下文
        "project_id": pid,
        "action": "formula.changed",
        "resource_type": "report_config",
        "resource_id": body.row_code,
        "details": {
            "event_type": "formula_changed",
            "module": body.module,
            "row_code": body.row_code,
            "action": body.action,
            "old_formula": body.old_formula,
            "new_formula": body.new_formula,
            "result_value": str(body.result_value) if body.result_value is not None else "",
            "trace": body.trace or [],
        },
    })
    await db.commit()
    now = datetime.now(timezone.utc)
    return {"ok": True, "created_at": str(now)}


@router.post("/{project_id}/{year}/rollback")
async def rollback_formula(
    project_id: str, year: int,
    body: RollbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """一键回滚公式：将指定行次的公式写回 old_formula。

    复用时光机思路：
    1. 查 report_config 找到对应行
    2. 将 formula 写回 target_formula（old_formula）
    3. 记录一条 rollback 审计日志（统一走哈希链 formula.changed，不再写旧 formula_audit_log 表）
    """
    from app.services.audit_log_helper import append_audit_log

    # 1. 查找 report_config 中对应行并更新公式
    current_formula = None
    row_id = None
    try:
        result = await db.execute(text("""
            SELECT id, formula FROM report_config
            WHERE project_id = :pid AND row_code = :rc
            LIMIT 1
        """), {"pid": project_id, "rc": body.row_code})
        row = result.fetchone()
        if row:
            row_id = row[0]
            current_formula = row[1]
            await db.execute(text("""
                UPDATE report_config SET formula = :f WHERE id = :id
            """), {"f": body.target_formula, "id": str(row_id)})
    except Exception:
        # report_config 表可能不存在或结构不同，静默处理
        pass

    # 2. 记录回滚审计日志 — 统一走哈希链 audit_log_entries（action='formula.changed'）
    try:
        pid = uuid.UUID(project_id)
    except (ValueError, AttributeError):
        pid = None

    await append_audit_log(db, {
        "user_id": uuid.UUID("00000000-0000-0000-0000-000000000000"),
        "project_id": pid,
        "action": "formula.changed",
        "resource_type": "report_config",
        "resource_id": body.row_code,
        "details": {
            "event_type": "formula_changed",
            "module": body.module,
            "row_code": body.row_code,
            "action": "rollback",
            "old_formula": current_formula or '',
            "new_formula": body.target_formula,
            "result_value": None,
            "source_log_id": body.source_log_id,
        },
    })

    await db.commit()
    now = datetime.now(timezone.utc)
    return {
        "ok": True,
        "row_code": body.row_code,
        "restored_formula": body.target_formula,
        "previous_formula": current_formula,
        "created_at": str(now),
    }
