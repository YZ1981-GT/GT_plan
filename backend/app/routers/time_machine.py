"""时光机 router — V3 收官增强 Req 11.3

提供时光机快照管理端点：

- POST /api/instances/{instance_type}/{instance_id}/time-machine/snapshots  — 创建快照
- GET  /api/instances/{instance_type}/{instance_id}/time-machine/snapshots  — 列出快照
- POST /api/instances/{instance_type}/{instance_id}/time-machine/restore/{snapshot_id} — 恢复

注册位置：backend/app/router_registry/system.py §126

Validates: Requirements 11.3
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services import time_machine_service as svc
from app.services.audit_log_helper import append_audit_log

router = APIRouter(prefix="/api/instances", tags=["时光机"])

_VALID_TYPES = {"workpaper", "adjustment", "misstatement", "disclosure"}


class CreateSnapshotRequest(BaseModel):
    """创建快照请求体。"""
    diff_json: list[dict] | None = None
    current_data: dict | None = None
    previous_data: dict | None = None


class RestoreResponse(BaseModel):
    """恢复响应。"""
    success: bool
    message: str
    restored_data: dict | None = None


@router.post("/{instance_type}/{instance_id}/time-machine/snapshots")
async def create_snapshot(
    instance_type: str,
    instance_id: UUID,
    body: CreateSnapshotRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """创建时光机快照。

    前端 5 分钟自动触发，或用户手动触发。
    """
    if instance_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=422,
            detail={"message": f"不支持的实例类型: {instance_type}"},
        )

    # 获取项目 ID
    project_id = await _get_project_id(db, instance_type, instance_id)

    current_data = body.current_data or {}
    previous_data = body.previous_data

    snapshot = await svc.create_snapshot(
        db,
        instance_type=instance_type,
        instance_id=instance_id,
        user_id=user.id,
        project_id=project_id,
        current_data=current_data,
        previous_data=previous_data,
    )

    await db.commit()

    return {
        "id": str(snapshot.id),
        "instance_type": snapshot.instance_type,
        "instance_id": str(snapshot.instance_id),
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


@router.get("/{instance_type}/{instance_id}/time-machine/snapshots")
async def list_snapshots(
    instance_type: str,
    instance_id: UUID,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[dict]:
    """列出指定实例的快照列表。"""
    if instance_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=422,
            detail={"message": f"不支持的实例类型: {instance_type}"},
        )

    snapshots = await svc.list_snapshots(
        db,
        instance_type=instance_type,
        instance_id=instance_id,
        limit=min(limit, 50),
    )

    return [
        {
            "id": str(s.id),
            "instance_type": s.instance_type,
            "instance_id": str(s.instance_id),
            "user_id": str(s.user_id),
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "diff_summary": _summarize_diff(s.diff_json),
        }
        for s in snapshots
    ]


@router.post("/{instance_type}/{instance_id}/time-machine/restore/{snapshot_id}")
async def restore_snapshot(
    instance_type: str,
    instance_id: UUID,
    snapshot_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RestoreResponse:
    """恢复到指定快照时刻。

    归档项目禁止恢复（Req 1 守卫自动拦截）。
    """
    if instance_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=422,
            detail={"message": f"不支持的实例类型: {instance_type}"},
        )

    # 检查项目是否归档
    project_id = await _get_project_id(db, instance_type, instance_id)
    is_archived = await _check_archived(db, project_id)
    if is_archived:
        raise HTTPException(
            status_code=423,
            detail={"message": "项目已归档，无法恢复时光机快照"},
        )

    # 获取当前数据
    current_data = await _load_instance_data(db, instance_type, instance_id)

    try:
        restored_data = await svc.restore(
            db,
            snapshot_id=snapshot_id,
            instance_type=instance_type,
            instance_id=instance_id,
            current_data=current_data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)})

    # 写回实例数据
    await _save_instance_data(db, instance_type, instance_id, restored_data)

    # 写 audit_log
    await append_audit_log(db, payload={
        "user_id": str(user.id),
        "project_id": str(project_id),
        "action": "time_machine_restore",
        "resource_type": instance_type,
        "resource_id": str(instance_id),
        "details": {
            "event_type": "time_machine_restore",
            "from_snapshot_id": str(snapshot_id),
            "instance_type": instance_type,
            "instance_id": str(instance_id),
        },
    })

    await db.commit()

    return RestoreResponse(
        success=True,
        message="已恢复到快照时刻",
        restored_data=restored_data,
    )


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _summarize_diff(diff_json: list | dict | None) -> str:
    """生成 diff 摘要描述。"""
    if not diff_json:
        return "空快照"
    if isinstance(diff_json, list):
        if len(diff_json) == 1 and isinstance(diff_json[0], dict) and diff_json[0].get("op") == "full_snapshot":
            return "全量快照"
        op_count = len(diff_json)
        return f"{op_count} 项变更"
    return "增量快照"


async def _get_project_id(db: AsyncSession, instance_type: str, instance_id: UUID) -> UUID:
    """获取实例所属项目 ID。"""
    from sqlalchemy import text as sql_text

    table_map = {
        "workpaper": "working_papers",
        "adjustment": "adjustments",
        "misstatement": "misstatements",
        "disclosure": "disclosure_notes",
    }
    table_name = table_map.get(instance_type, "working_papers")

    try:
        stmt = sql_text(f"SELECT project_id FROM {table_name} WHERE id = :iid LIMIT 1")
        result = await db.execute(stmt, {"iid": instance_id})
        row = result.first()
        if row:
            return row[0]
    except Exception:
        pass

    raise HTTPException(status_code=404, detail={"message": f"未找到实例: {instance_type}/{instance_id}"})


async def _check_archived(db: AsyncSession, project_id: UUID) -> bool:
    """检查项目是否归档。"""
    from sqlalchemy import text as sql_text

    try:
        stmt = sql_text("SELECT status FROM projects WHERE id = :pid LIMIT 1")
        result = await db.execute(stmt, {"pid": project_id})
        row = result.first()
        return row[0] == "archived" if row else False
    except Exception:
        return False


async def _load_instance_data(db: AsyncSession, instance_type: str, instance_id: UUID) -> dict:
    """加载实例当前数据（JSON 格式）。"""
    from sqlalchemy import text as sql_text

    # 不同模块的数据字段不同
    data_field_map = {
        "workpaper": "table_data",
        "adjustment": "details",
        "misstatement": "details",
        "disclosure": "parsed_data",
    }
    table_map = {
        "workpaper": "working_papers",
        "adjustment": "adjustments",
        "misstatement": "misstatements",
        "disclosure": "disclosure_notes",
    }

    table_name = table_map.get(instance_type, "working_papers")
    data_field = data_field_map.get(instance_type, "table_data")

    try:
        stmt = sql_text(f"SELECT {data_field} FROM {table_name} WHERE id = :iid LIMIT 1")
        result = await db.execute(stmt, {"iid": instance_id})
        row = result.first()
        if row and row[0]:
            return row[0] if isinstance(row[0], dict) else {}
    except Exception as exc:
        logger.warning("[TIME_MACHINE] 加载实例数据失败: %s", exc)

    return {}


async def _save_instance_data(db: AsyncSession, instance_type: str, instance_id: UUID, data: dict) -> None:
    """保存恢复后的数据到实例。"""
    from sqlalchemy import text as sql_text
    import json

    data_field_map = {
        "workpaper": "table_data",
        "adjustment": "details",
        "misstatement": "details",
        "disclosure": "parsed_data",
    }
    table_map = {
        "workpaper": "working_papers",
        "adjustment": "adjustments",
        "misstatement": "misstatements",
        "disclosure": "disclosure_notes",
    }

    table_name = table_map.get(instance_type, "working_papers")
    data_field = data_field_map.get(instance_type, "table_data")

    try:
        stmt = sql_text(
            f"UPDATE {table_name} SET {data_field} = :data WHERE id = :iid"
        )
        await db.execute(stmt, {"data": json.dumps(data, ensure_ascii=False, default=str), "iid": instance_id})
    except Exception as exc:
        logger.error("[TIME_MACHINE] 保存恢复数据失败: %s", exc)
        raise HTTPException(status_code=500, detail={"message": f"保存恢复数据失败: {exc}"})
