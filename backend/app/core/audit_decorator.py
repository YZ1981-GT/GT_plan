"""服务层审计日志装饰器 — 记录 before/after diff

用法:
    from app.core.audit_decorator import audit_log

    class AdjustmentService:
        @audit_log(action="delete", object_type="adjustment")
        async def delete_entry(self, project_id, entry_group_id):
            ...

装饰器会：
1. 在方法执行前捕获 before 状态快照
2. 执行原方法
3. 在方法执行后捕获 after 状态快照
4. 计算 diff 并写入 logs 表

Validates: Requirements R7.5
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from app.core.database import async_session

logger = logging.getLogger("audit_platform.audit_decorator")


# ---------------------------------------------------------------------------
# Diff 计算
# ---------------------------------------------------------------------------


def compute_diff(before: dict | None, after: dict | None) -> list[dict]:
    """计算两个状态快照之间的差异。

    返回格式:
        [{"field": "status", "old": "draft", "new": "approved"}, ...]
    """
    if before is None and after is None:
        return []
    if before is None:
        return [{"field": k, "old": None, "new": v} for k, v in (after or {}).items()]
    if after is None:
        return [{"field": k, "old": v, "new": None} for k, v in (before or {}).items()]

    diff: list[dict] = []
    all_keys = set(before.keys()) | set(after.keys())
    for key in sorted(all_keys):
        old_val = before.get(key)
        new_val = after.get(key)
        if old_val != new_val:
            diff.append({"field": key, "old": old_val, "new": new_val})
    return diff


# ---------------------------------------------------------------------------
# 状态快照序列化
# ---------------------------------------------------------------------------


def _serialize_value(val: Any) -> Any:
    """将 ORM 对象或特殊类型序列化为 JSON 兼容值。"""
    if val is None:
        return None
    if isinstance(val, UUID):
        return str(val)
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, (int, float, str, bool)):
        return val
    if hasattr(val, "value"):  # enum
        return val.value
    return str(val)


def snapshot_from_row(row: Any) -> dict:
    """从 SQLAlchemy ORM 行对象提取可序列化的快照。"""
    if row is None:
        return {}
    result = {}
    mapper = getattr(row.__class__, "__mapper__", None)
    if mapper is not None:
        for col in mapper.columns:
            key = col.key
            val = getattr(row, key, None)
            result[key] = _serialize_value(val)
    return result


def snapshot_from_rows(rows: list[Any]) -> dict:
    """从多行 ORM 对象提取快照（用于分录组等多行场景）。"""
    if not rows:
        return {}
    return {
        "count": len(rows),
        "rows": [snapshot_from_row(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# 审计日志写入
# ---------------------------------------------------------------------------


async def _write_audit_log(
    user_id: UUID | None,
    action: str,
    object_type: str,
    object_id: UUID | None,
    before_state: dict | None,
    after_state: dict | None,
    diff: list[dict],
    project_id: UUID | None = None,
) -> None:
    """写入审计日志到 logs 表，使用独立会话避免影响业务事务。"""
    try:
        from app.models.core import Log

        async with async_session() as session:
            log_entry = Log(
                user_id=user_id,
                action_type=action,
                object_type=object_type,
                object_id=object_id,
                old_value=before_state,
                new_value={
                    "after": after_state,
                    "diff": diff,
                    "project_id": str(project_id) if project_id else None,
                },
            )
            session.add(log_entry)
            await session.commit()
            logger.debug(
                "audit_log written: action=%s type=%s id=%s diff_count=%d",
                action, object_type, object_id, len(diff),
            )
    except Exception:
        logger.error("Failed to write service audit log", exc_info=True)


# ---------------------------------------------------------------------------
# 参数提取辅助
# ---------------------------------------------------------------------------


def _extract_param(name: str, args: tuple, kwargs: dict, sig: inspect.Signature) -> Any:
    """从 args/kwargs 中按参数名提取值。"""
    # 先查 kwargs
    if name in kwargs:
        return kwargs[name]
    # 再按位置查 args（跳过 self）
    params = list(sig.parameters.keys())
    if name in params:
        idx = params.index(name)
        if idx < len(args):
            return args[idx]
    return None


def _extract_db_session(args: tuple, kwargs: dict, sig: inspect.Signature, self_obj: Any):
    """提取 AsyncSession 参数 — 支持方法参数或 self.db 属性。"""
    from sqlalchemy.ext.asyncio import AsyncSession

    # 1. 从 kwargs 中查找
    for key in ("db", "session", "db_session"):
        if key in kwargs and isinstance(kwargs[key], AsyncSession):
            return kwargs[key]

    # 2. 从 args 中按类型查找
    for arg in args:
        if isinstance(arg, AsyncSession):
            return arg

    # 3. 从 self.db 属性获取
    if self_obj is not None and hasattr(self_obj, "db"):
        db = getattr(self_obj, "db")
        if isinstance(db, AsyncSession):
            return db

    return None


def _extract_user_id(args: tuple, kwargs: dict, sig: inspect.Signature) -> UUID | None:
    """尝试从参数中提取 user_id。"""
    for name in ("user_id", "reviewer_id", "current_user_id"):
        val = _extract_param(name, args, kwargs, sig)
        if val is not None:
            if isinstance(val, UUID):
                return val
            try:
                return UUID(str(val))
            except (ValueError, AttributeError):
                pass
    return None


# ---------------------------------------------------------------------------
# 装饰器
# ---------------------------------------------------------------------------


def audit_log(
    action: str,
    object_type: str | None = None,
    *,
    snapshot_fn: Callable[..., Any] | None = None,
):
    """服务层审计日志装饰器。

    Parameters
    ----------
    action : str
        操作类型，如 "delete", "approve", "reject", "status_change"
    object_type : str | None
        对象类型，如 "adjustment", "working_paper"。
        为 None 时自动从类名推断。
    snapshot_fn : Callable | None
        自定义快照函数。默认使用内置的 ORM 行快照。

    Notes
    -----
    装饰器假设被装饰方法是 async 实例方法，且：
    - 有 project_id 参数（UUID）
    - 有某种 object_id 参数（entry_group_id / wp_id 等）
    - db session 来自 self.db 或方法参数
    """

    def decorator(fn: Callable) -> Callable:
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            # 提取 self
            self_obj = args[0] if args else None

            # 推断 object_type
            resolved_type = object_type
            if resolved_type is None and self_obj is not None:
                cls_name = self_obj.__class__.__name__
                # AdjustmentService → adjustment
                resolved_type = cls_name.replace("Service", "").lower()

            # 提取关键参数
            # 使用完整的 args（含 self）和完整签名进行参数提取
            project_id = _extract_param("project_id", args, kwargs, sig)
            user_id = _extract_user_id(args, kwargs, sig)

            # 提取 object_id（尝试多种参数名）
            obj_id = None
            for id_name in ("entry_group_id", "wp_id", "object_id", "id"):
                val = _extract_param(id_name, args, kwargs, sig)
                if val is not None:
                    obj_id = val if isinstance(val, UUID) else None
                    if obj_id is None:
                        try:
                            obj_id = UUID(str(val))
                        except (ValueError, AttributeError):
                            pass
                    if obj_id is not None:
                        break

            # 获取 db session
            db = _extract_db_session(args, kwargs, sig, self_obj)

            # ── Before 快照 ──
            before_state = None
            if db is not None and obj_id is not None:
                try:
                    before_state = await _capture_before_state(
                        db, resolved_type, obj_id, project_id, snapshot_fn
                    )
                except Exception:
                    logger.warning("audit_log: failed to capture before state", exc_info=True)

            # ── 执行原方法 ──
            result = await fn(*args, **kwargs)

            # ── After 快照 ──
            after_state = None
            if db is not None and obj_id is not None:
                try:
                    after_state = await _capture_after_state(
                        db, resolved_type, obj_id, project_id, action, snapshot_fn
                    )
                except Exception:
                    logger.warning("audit_log: failed to capture after state", exc_info=True)

            # ── 计算 diff 并写入 ──
            diff = compute_diff(before_state, after_state)

            await _write_audit_log(
                user_id=user_id,
                action=action,
                object_type=resolved_type or "unknown",
                object_id=obj_id,
                before_state=before_state,
                after_state=after_state,
                diff=diff,
                project_id=project_id if isinstance(project_id, UUID) else None,
            )

            return result

        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# 状态捕获
# ---------------------------------------------------------------------------


async def _capture_before_state(
    db, object_type: str | None, object_id: UUID,
    project_id: Any, snapshot_fn: Callable | None,
) -> dict | None:
    """捕获操作前的状态快照。"""
    if snapshot_fn is not None:
        return await snapshot_fn(db, object_id, "before")

    return await _default_snapshot(db, object_type, object_id, project_id)


async def _capture_after_state(
    db, object_type: str | None, object_id: UUID,
    project_id: Any, action: str, snapshot_fn: Callable | None,
) -> dict | None:
    """捕获操作后的状态快照。"""
    if snapshot_fn is not None:
        return await snapshot_fn(db, object_id, "after")

    # 删除操作后对象可能已被软删除，仍然尝试查询
    return await _default_snapshot(db, object_type, object_id, project_id, include_deleted=True)


async def _default_snapshot(
    db, object_type: str | None, object_id: UUID,
    project_id: Any, include_deleted: bool = False,
) -> dict | None:
    """默认快照策略 — 根据 object_type 查询对应模型。"""
    import sqlalchemy as sa

    model = _resolve_model(object_type)
    if model is None:
        return None

    try:
        query = sa.select(model).where(model.id == object_id)
        # 如果模型有 project_id 字段且提供了 project_id，加入过滤
        if project_id is not None and hasattr(model, "project_id"):
            query = query.where(model.project_id == project_id)
        # 软删除过滤
        if not include_deleted and hasattr(model, "is_deleted"):
            query = query.where(model.is_deleted == sa.false())

        result = await db.execute(query)
        row = result.scalar_one_or_none()
        if row is not None:
            return snapshot_from_row(row)

        # 对于分录组等多行场景，尝试按 entry_group_id 查询
        if object_type == "adjustment" and hasattr(model, "entry_group_id"):
            query = sa.select(model).where(model.entry_group_id == object_id)
            if project_id is not None:
                query = query.where(model.project_id == project_id)
            if not include_deleted and hasattr(model, "is_deleted"):
                query = query.where(model.is_deleted == sa.false())
            result = await db.execute(query)
            rows = result.scalars().all()
            if rows:
                return snapshot_from_rows(list(rows))
    except Exception:
        logger.warning("audit_log: default snapshot failed for %s/%s", object_type, object_id, exc_info=True)

    return None



# ---------------------------------------------------------------------------
# 模型注册表（注册表模式，替代 if/elif 链）
# ---------------------------------------------------------------------------

# 格式：{ object_type_lower: (module_path, class_name) }
# 新增模型时只需在此处添加一行，无需修改 _resolve_model 函数
_MODEL_REGISTRY: dict[str, tuple[str, str]] = {
    "adjustment":        ("app.models.audit_platform_models", "Adjustment"),
    "adjustmentservice": ("app.models.audit_platform_models", "Adjustment"),
    "workingpaper":      ("app.models.workpaper_models",      "WorkingPaper"),
    "working_paper":     ("app.models.workpaper_models",      "WorkingPaper"),
    "wp":                ("app.models.workpaper_models",      "WorkingPaper"),
    "workpaper":         ("app.models.workpaper_models",      "WorkingPaper"),
}


def register_audit_model(object_type: str, module_path: str, class_name: str) -> None:
    """向注册表动态注册新的模型映射。

    供插件或扩展模块在启动时调用，无需修改本文件。

    Parameters
    ----------
    object_type : str
        object_type 字符串（不区分大小写）
    module_path : str
        模型所在模块路径，如 "app.models.my_models"
    class_name : str
        模型类名，如 "MyModel"
    """
    _MODEL_REGISTRY[object_type.lower()] = (module_path, class_name)


def _resolve_model(object_type: str | None):
    """根据 object_type 字符串解析对应的 SQLAlchemy 模型类。

    使用注册表模式（_MODEL_REGISTRY），新增模型只需在注册表中添加一行，
    无需修改本函数。
    """
    if object_type is None:
        return None

    entry = _MODEL_REGISTRY.get(object_type.lower())
    if entry is None:
        return None

    module_path, class_name = entry
    try:
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, class_name, None)
    except ImportError:
        logger.warning("audit_log: cannot import model for type=%s (module=%s)", object_type, module_path)
        return None
