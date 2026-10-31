"""公式审计日志 API — 记录公式变更历史，满足审计留痕要求

数据源：audit_log_entries 哈希链（action_type='formula.changed'）
  - payload JSONB 含 project_id / module / row_code / action / old_formula / new_formula / result_value / trace / year
  - 写入统一走 audit_log_helper.append_audit_log（Task 14 已收口）

API:
  GET  /api/formula-audit-log/{project_id}/{year}  — 按年度查询公式变更历史；legacy_without_year 含无年度旧条目
  POST /api/formula-audit-log/{project_id}/{year}  — 人工补记（ManualNoteBody，action=manual_note）
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access, require_role
from app.models.core import User

router = APIRouter(prefix="/api/formula-audit-log", tags=["formula-audit-log"])

# ── module → domain 映射（与 rollback.py 共用口径）───────────────────────
_MODULE_TO_DOMAIN = {"report": "report", "consol": "report", "tb_detail": "tb_detail", "wp": "wp",
                     "workpaper": "wp", "note": "note", "consol_note": "consol_note", "push": "push"}

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


class ManualNoteBody(BaseModel, extra="forbid"):
    """人工补记请求体（需求 11.2，ADR-FHIC-12）。

    ``extra='forbid'``：提交 ``old_formula`` / ``new_formula`` / ``result_value`` / ``trace``
    等字段一律 422（客户端只能写备注，不能伪造变更记录）。
    """
    note: str = Field(..., max_length=500, description="人工补记备注（≤500 字）")
    related_formula_id: str | None = Field(None, description="关联公式 ID（可选）")


class RollbackRequest(BaseModel):
    """一键回滚请求体（需求 13.1~13.2，ADR-FHIC-10）。

    ``target_formula`` 已删除——回滚目标定义由服务端从审计日志 ``old_definition`` 读取。
    ``expected_version`` 缺失由服务层抛 428（不靠 pydantic 必填）。
    """
    row_code: str
    module: str = 'report'
    source_log_id: str = ''
    expected_version: int | None = Field(None, ge=0, description="本项目适配的修订号（CAS）")


@router.get("/{project_id}/{year}")
async def get_audit_log(
    project_id: str, year: int,
    module: str = '',
    row_code: str = '',
    legacy_without_year: bool = Query(False, description="同时返回载荷无 year 字段的旧条目"),
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """查询公式变更历史（需求 11.1，ADR-FHIC-12）。

    按 ``payload->>'year'`` 过滤，只返回本年度条目。
    ``legacy_without_year=true`` 时同时返回载荷无 ``year`` 字段的旧条目。
    """
    is_pg = _is_postgres(db)
    year_str = str(year)

    if is_pg:
        query = """
            SELECT id, payload, ts, object_id
            FROM audit_log_entries
            WHERE action_type = 'formula.changed'
              AND payload->>'project_id' = :pid
        """
    else:
        query = """
            SELECT id, payload, ts, object_id
            FROM audit_log_entries
            WHERE action_type = 'formula.changed'
              AND json_extract(payload, '$.project_id') = :pid
        """
    params: dict = {"pid": project_id, "yr": year_str}

    # ── 年度过滤（需求 11.1）──
    if legacy_without_year:
        if is_pg:
            query += " AND (payload->>'year' = :yr OR payload->>'year' IS NULL)"
        else:
            query += " AND (json_extract(payload, '$.year') = :yr OR json_extract(payload, '$.year') IS NULL)"
    else:
        if is_pg:
            query += " AND payload->>'year' = :yr"
        else:
            query += " AND json_extract(payload, '$.year') = :yr"

    if module:
        if is_pg:
            query += " AND payload->>'module' = :mod"
        else:
            query += " AND json_extract(payload, '$.module') = :mod"
        params["mod"] = module

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

    # 映射为与旧表完全一致的返回结构，增加 rollbackable（需求 13.3）与 current_version（需求 13.1：
    # 回滚必带 expected_version，界面只能从这里拿到当前修订号）
    from app.services.formula_settings.rollback import can_rollback, current_version_for_entry
    try:
        pid_uuid: uuid.UUID | None = uuid.UUID(project_id)
    except ValueError:
        pid_uuid = None
    local_cache: dict = {}
    items = []
    for r in rows:
        p = _parse_payload(r[1])
        # 计算 rollbackable
        _domain = p.get("domain") or _MODULE_TO_DOMAIN.get(str(p.get("module") or "report"), "report")
        rollbackable, blocked_reason = can_rollback(_domain, p)
        current_version: int | None = None
        if rollbackable:
            if pid_uuid is None:
                rollbackable, blocked_reason = False, "项目编号无效"
            else:
                current_version, locate_reason = await current_version_for_entry(
                    db, pid_uuid, object_id=_as_uuid(r[3]), payload=p, local_cache=local_cache)
                if current_version is None:
                    rollbackable, blocked_reason = False, locate_reason
        item = {
            "id": str(r[0]),
            "module": p.get("module", "report"),
            "row_code": p.get("row_code", ""),
            "action": p.get("action", ""),
            "old_formula": p.get("old_formula", ""),
            "new_formula": p.get("new_formula", ""),
            "result_value": _safe_float(p.get("result_value")),
            "trace": p.get("trace"),
            "operation": p.get("operation"),
            "source": p.get("source"),
            "created_at": str(r[2]) if r[2] else None,
            "rollbackable": rollbackable,
            "rollback_blocked_reason": blocked_reason or None,
            "current_version": current_version,
        }
        items.append(item)
    return items


def _as_uuid(val) -> uuid.UUID | None:
    """``object_id`` 列：PG 返回 UUID、SQLite 返回 32 位十六进制串；解析不了按「无对象」处理（不让列表 500）。"""
    if val is None or isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (TypeError, ValueError):
        return None


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
    body: ManualNoteBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """人工补记（需求 11.2，ADR-FHIC-12）。

    只接受备注（≤500 字），写 ``action="manual_note"``。
    ``ManualNoteBody(extra='forbid')`` 使得提交 ``old_formula`` / ``new_formula`` /
    ``result_value`` / ``trace`` 等字段一律 422。
    """
    from app.services.audit_log_helper import append_audit_log

    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        pid = None

    details: dict = {
        "event_type": "formula_changed",
        "module": "manual",
        "row_code": "",
        "action": "manual_note",
        "old_formula": "",
        "new_formula": "",
        "result_value": "",
        "trace": [],
        "note": body.note,
        "year": str(year),
    }
    if body.related_formula_id is not None:
        details["related_formula_id"] = body.related_formula_id

    await append_audit_log(db, {
        "user_id": current_user.id,
        "project_id": pid,
        "action": "formula.changed",
        "resource_type": "formula_audit_note",
        "resource_id": body.related_formula_id or "",
        "details": details,
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
    from app.services.formula_settings.outbox import record_changes, publish_pending
    from app.services.formula_settings.rollback import rollback_from_log

    try:
        pid = uuid.UUID(project_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="project_id 格式无效") from None
    await assert_project_permission(db, current_user, pid, "review")
    try:
        result = await rollback_from_log(db, project_id=pid, source_log_id=body.source_log_id,
                                         expected_version=body.expected_version, user_id=current_user.id)
    except FormulaSettingError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from None
    await record_changes(db, events=result["events"], domain=result["domain"], source="history_rollback")
    await db.commit()
    await publish_pending(db)
    return {
        "ok": True,
        "row_code": body.row_code,
        "slot_key": result["slot_key"],
        "restored_formula": result["restored_formula"],
        "previous_formula": result["previous_formula"],
        "created_at": str(datetime.now(timezone.utc)),
    }
