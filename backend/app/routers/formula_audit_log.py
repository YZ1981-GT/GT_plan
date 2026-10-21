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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access, require_role
from app.models.core import User

router = APIRouter(prefix="/api/formula-audit-log", tags=["formula-audit-log"])

# ─── 鉴权（2026-09-28 补，三个端点原先全裸）──────────────────────────────
#
# 🔴 修复前状态：三个端点只有 `Depends(get_db)`，路径带 `{project_id}` 却零鉴权：
#   · GET  —— 任意调用方可读任意项目的公式变更史（含 old_formula / new_formula）
#   · POST —— **未授权写审计哈希链**，且 `user_id` 写死全零（原注释自称
#             「POST 端点无 current_user 上下文」）⇒ **审计留痕可伪造**，
#             这对以留痕为生命线的审计平台是最严重的一类缺陷
#   · POST /rollback —— **未授权 `UPDATE report_config SET formula`**，而
#             `report_config` 是**全局**报表行模板表（无 project_id 列）
#             ⇒ 任何人可篡改全平台报表公式
#
# 权限分档依据（对齐既有基准，不自造）：
#   · 读 → `require_project_access("readonly")`（与 `disclosure_notes` 全部只读端点同级）
#   · 写审计链 → `require_project_access("edit")`（写的是该项目的留痕）
#   · 回滚 → `require_role([...])` + 本项目 review 级成员：2026-10-20 起回滚只写**本项目适配**
#     （formula-global-settings-sync R9.3），不再改全局行；角色门控保留（与前端按钮逐值对齐）。


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
    source_log_id: str = ''  # 来源历史条目 ID（据此定位公式位）
    expected_version: int | None = None  # 本项目适配的修订号（可选 CAS）


@router.get("/{project_id}/{year}")
async def get_audit_log(
    project_id: str, year: int,
    module: str = '',
    row_code: str = '',
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
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
            # formula-global-settings-sync：本项目适配 / 同步全局 / 恢复 / 处理待确认 / 订阅模板 …（旧记录无）
            "operation": _parse_payload(r[1]).get("operation"),
            "source": _parse_payload(r[1]).get("source"),
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
    current_user: User = Depends(require_project_access("edit")),
):
    """记录公式变更日志 — 委托 append_audit_log 写入哈希链。

    🔴 `user_id` 必须是**真实操作人**：原实现写死
    `00000000-0000-0000-0000-000000000000` 并注释「POST 端点无 current_user 上下文」
    —— 那不是「没有上下文」，是**没挂鉴权依赖**。审计留痕写不出人等于没有留痕
    （既无法追责也无法举证），故与鉴权一并修。
    """
    from app.services.audit_log_helper import append_audit_log

    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        pid = None

    await append_audit_log(db, {
        "user_id": current_user.id,
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
    current_user: User = Depends(require_role(["admin", "partner", "manager"])),
):
    """一键回滚：把这条历史对应的公式位在**本项目**写回 ``target_formula``（spec formula-global-settings-sync R9.3）。

    按历史条目（``source_log_id``）定位公式位，经本项目适配写入（带版本、留痕、触发重算）；
    定位不到返回 404，不再按行次 ``LIMIT 1`` 改任意一个准则的全局行，也不再吞异常返回成功。

    权限：签名保留 ``require_role``（与前端按钮门控逐值对齐，守卫 ``formulaHistoryRollbackGate.spec.ts``），
    函数体再校验本项目成员（review 级：回滚是复核纠错动作，与签名角色同属复核人员）。
    """
    from app.deps import assert_project_permission
    from app.services.formula_settings.errors import FormulaSettingError
    from app.services.formula_settings.propagation import publish_events
    from app.services.formula_settings.rollback import rollback_from_log

    try:
        pid = uuid.UUID(project_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="project_id 格式无效") from None
    await assert_project_permission(db, current_user, pid, "review")
    try:
        result = await rollback_from_log(db, project_id=pid, source_log_id=body.source_log_id,
                                         target_formula=body.target_formula,
                                         expected_version=body.expected_version, user_id=current_user.id)
    except FormulaSettingError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from None
    await db.commit()
    await publish_events(result["events"], domain=result["domain"], source="history_rollback")
    return {
        "ok": True,
        "row_code": body.row_code,
        "slot_key": result["slot_key"],
        "restored_formula": result["restored_formula"],
        "previous_formula": result["previous_formula"],
        "created_at": str(datetime.now(timezone.utc)),
    }
