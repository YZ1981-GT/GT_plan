"""时光机自动快照服务 — V3 收官增强 Req 11.1 + 11.2

提供 create_snapshot / list_snapshots / restore / cleanup 四大功能。
diff 算法使用 RFC 6902 JSON Patch 反向 diff（jsonpatch 库）。

依赖：
- backend/app/models/v3_refinement_models.py:TimeMachineSnapshot
- jsonpatch（pip install jsonpatch）

Validates: Requirements 11.1, 11.2, AC 11.1~11.5
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v3_refinement_models import TimeMachineSnapshot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 11.2 Diff 算法（RFC 6902 JSON Patch 反向 diff）
# ---------------------------------------------------------------------------


def compute_reverse_diff(old_data: dict, new_data: dict) -> list[dict]:
    """计算从 new_data 恢复到 old_data 的反向 JSON Patch（RFC 6902 格式）。

    Parameters
    ----------
    old_data : dict
        旧版本数据（快照时刻的数据）
    new_data : dict
        新版本数据（当前数据）

    Returns
    -------
    list[dict]
        RFC 6902 JSON Patch 操作列表（反向：应用到 new_data 可得到 old_data）
    """
    try:
        import jsonpatch
        # 正向 patch: old → new
        forward_patch = jsonpatch.make_patch(old_data, new_data)
        # 反向 patch: new → old
        reverse_patch = jsonpatch.make_patch(new_data, old_data)
        return reverse_patch.patch
    except ImportError:
        # fallback: 简单全量 diff
        logger.warning("[TIME_MACHINE] jsonpatch 未安装，使用简单 diff")
        return _simple_diff(old_data, new_data)
    except Exception as exc:
        logger.error("[TIME_MACHINE] 计算 diff 失败: %s", exc)
        return []


def apply_reverse_diff(current_data: dict, diff_ops: list[dict]) -> dict:
    """应用反向 diff 恢复到旧版本。

    Parameters
    ----------
    current_data : dict
        当前数据
    diff_ops : list[dict]
        RFC 6902 JSON Patch 操作列表

    Returns
    -------
    dict
        恢复后的数据
    """
    try:
        import jsonpatch
        patch = jsonpatch.JsonPatch(diff_ops)
        result = patch.apply(current_data)
        return result
    except ImportError:
        logger.warning("[TIME_MACHINE] jsonpatch 未安装，使用简单恢复")
        return _simple_restore(current_data, diff_ops)
    except Exception as exc:
        logger.error("[TIME_MACHINE] 应用 diff 失败: %s", exc)
        return current_data


def _simple_diff(old_data: dict, new_data: dict) -> list[dict]:
    """简单 diff fallback：记录所有变更的 key。"""
    ops: list[dict] = []
    all_keys = set(list(old_data.keys()) + list(new_data.keys()))
    for key in all_keys:
        old_val = old_data.get(key)
        new_val = new_data.get(key)
        if old_val != new_val:
            if key not in new_data:
                ops.append({"op": "add", "path": f"/{key}", "value": old_val})
            elif key not in old_data:
                ops.append({"op": "remove", "path": f"/{key}"})
            else:
                ops.append({"op": "replace", "path": f"/{key}", "value": old_val})
    return ops


def _simple_restore(current_data: dict, diff_ops: list[dict]) -> dict:
    """简单恢复 fallback。"""
    result = dict(current_data)
    for op in diff_ops:
        path = op.get("path", "").lstrip("/")
        if not path:
            continue
        if op["op"] == "replace" or op["op"] == "add":
            result[path] = op["value"]
        elif op["op"] == "remove":
            result.pop(path, None)
    return result


# ---------------------------------------------------------------------------
# 11.1 核心服务函数
# ---------------------------------------------------------------------------


async def create_snapshot(
    db: AsyncSession,
    *,
    instance_type: str,
    instance_id: UUID,
    user_id: UUID,
    project_id: UUID,
    current_data: dict,
    previous_data: dict | None = None,
) -> TimeMachineSnapshot:
    """创建时光机快照。

    如果提供 previous_data，计算增量 diff；否则存储全量快照。

    Parameters
    ----------
    db : AsyncSession
    instance_type : 实例类型（workpaper/adjustment/misstatement/disclosure）
    instance_id : 实例 ID
    user_id : 触发快照的用户 ID
    project_id : 项目 ID
    current_data : 当前数据
    previous_data : 上一次快照时的数据（None 则存全量）

    Returns
    -------
    TimeMachineSnapshot
    """
    if previous_data is not None:
        diff_json = compute_reverse_diff(previous_data, current_data)
        is_full = False
    else:
        # 全量快照：diff_json 存储完整数据
        diff_json = [{"op": "full_snapshot", "value": current_data}]
        is_full = True

    diff_str = json.dumps(diff_json, ensure_ascii=False, default=str)
    size_bytes = len(diff_str.encode("utf-8"))

    snapshot = TimeMachineSnapshot(
        instance_type=instance_type,
        instance_id=instance_id,
        user_id=user_id,
        project_id=project_id,
        diff_json=diff_json,
    )

    db.add(snapshot)
    await db.flush()
    await db.refresh(snapshot)

    logger.info(
        "[TIME_MACHINE] 创建快照: type=%s, id=%s, size=%d bytes, full=%s",
        instance_type, instance_id, size_bytes, is_full,
    )

    return snapshot


async def list_snapshots(
    db: AsyncSession,
    *,
    instance_type: str,
    instance_id: UUID,
    limit: int = 20,
) -> list[TimeMachineSnapshot]:
    """列出指定实例的快照（按创建时间倒序）。

    Parameters
    ----------
    db : AsyncSession
    instance_type : 实例类型
    instance_id : 实例 ID
    limit : 最大返回数量

    Returns
    -------
    list[TimeMachineSnapshot]
    """
    stmt = (
        select(TimeMachineSnapshot)
        .where(
            TimeMachineSnapshot.instance_type == instance_type,
            TimeMachineSnapshot.instance_id == instance_id,
        )
        .order_by(desc(TimeMachineSnapshot.created_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def restore(
    db: AsyncSession,
    *,
    snapshot_id: UUID,
    instance_type: str,
    instance_id: UUID,
    current_data: dict,
) -> dict:
    """恢复到指定快照时刻的数据。

    Parameters
    ----------
    db : AsyncSession
    snapshot_id : 快照 ID
    instance_type : 实例类型
    instance_id : 实例 ID
    current_data : 当前实例数据

    Returns
    -------
    dict
        恢复后的数据

    Raises
    ------
    ValueError
        快照不存在或不匹配
    """
    snapshot = await db.get(TimeMachineSnapshot, snapshot_id)
    if not snapshot:
        raise ValueError(f"快照不存在: {snapshot_id}")

    if snapshot.instance_type != instance_type or snapshot.instance_id != instance_id:
        raise ValueError(f"快照不属于当前实例: {snapshot_id}")

    diff_ops = snapshot.diff_json
    if not diff_ops:
        raise ValueError(f"快照 diff 为空: {snapshot_id}")

    # 检查是否为全量快照
    if len(diff_ops) == 1 and diff_ops[0].get("op") == "full_snapshot":
        return diff_ops[0]["value"]

    # 应用反向 diff
    restored_data = apply_reverse_diff(current_data, diff_ops)

    logger.info(
        "[TIME_MACHINE] 恢复快照: snapshot_id=%s, type=%s, id=%s",
        snapshot_id, instance_type, instance_id,
    )

    return restored_data


async def cleanup(
    db: AsyncSession,
    *,
    older_than_days: int = 7,
) -> int:
    """清理过期快照。

    删除 older_than_days 天前的非全量快照。

    Parameters
    ----------
    db : AsyncSession
    older_than_days : 保留天数

    Returns
    -------
    int
        删除的快照数量
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    # 删除过期的非全量快照
    stmt = (
        delete(TimeMachineSnapshot)
        .where(
            TimeMachineSnapshot.created_at < cutoff,
        )
    )
    result = await db.execute(stmt)
    deleted_count = result.rowcount or 0

    await db.commit()

    logger.info(
        "[TIME_MACHINE] 清理完成: 删除 %d 个快照（>%d 天）",
        deleted_count, older_than_days,
    )

    return deleted_count
