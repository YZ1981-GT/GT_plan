"""账号级显示偏好 service。

service 只 flush，不 commit——commit/rollback 由 router 层负责。
design §2：无记录时返回平台默认，首写用 SAVEPOINT 竞争用 409。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_display_preferences import UserDisplayPreferences
from app.schemas.display_preferences import (
    PLATFORM_DEFAULTS,
    DisplayPreferencesPatch,
    DisplayPreferencesResponse,
    _UNSET,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------


class DisplayPrefsRevisionConflict(Exception):
    """乐观锁冲突：base_revision 与数据库不一致。"""

    def __init__(self, current: DisplayPreferencesResponse) -> None:
        self.current = current
        super().__init__("revision conflict")


class DisplayPrefsStorageLimitExceeded(Exception):
    """规范化后的 fixed_columns 超过 64KiB 存储合同（design §2）。"""


#: design §2：fixed_columns 按存储后的规范 JSON 计算大小，上限 64KiB。
_FIXED_COLUMNS_MAX_BYTES = 64 * 1024


def _enforce_fixed_columns_storage_limit(fixed_columns: dict[str, Any]) -> None:
    """按规范 JSON 序列化后检查 64KiB 上限，超限抛异常拒绝写入。"""
    canonical = json.dumps(
        fixed_columns, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    if canonical.encode("utf-8").__len__() > _FIXED_COLUMNS_MAX_BYTES:
        raise DisplayPrefsStorageLimitExceeded(
            "fixed_columns 规范化后超过 64KiB 存储上限，"
            "请删除部分页面的固定列设置后重试"
        )


def _normalize_user_id(user_id: str | uuid.UUID) -> uuid.UUID:
    """把调用方传入的 user_id 统一归一成 UUID 实例。

    ``UserDisplayPreferences.user_id`` 在 SQLAlchemy 侧映射为 PG UUID（SQLite 测试
    库经 ``Uuid`` 方言实现同样要求 UUID 对象）；传字符串会在绑定参数阶段抛
    ``'str' object has no attribute 'hex'``，把 500 伪装成数据库故障。
    """
    if isinstance(user_id, uuid.UUID):
        return user_id
    return uuid.UUID(str(user_id))


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------


async def get_preferences(
    db: AsyncSession,
    user_id: str,
) -> DisplayPreferencesResponse:
    """获取当前用户偏好，无记录时返回平台默认。"""
    stmt = select(UserDisplayPreferences).where(
        UserDisplayPreferences.user_id == _normalize_user_id(user_id),
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        return PLATFORM_DEFAULTS.model_copy()

    return _row_to_response(row)


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------


async def patch_preferences(
    db: AsyncSession,
    user_id: str,
    patch: DisplayPreferencesPatch,
) -> tuple[DisplayPreferencesResponse, list[str]]:
    """部分更新偏好。

    Returns:
        (完整归一响应, 变更的顶层字段名列表)

    Raises:
        DisplayPrefsRevisionConflict: base_revision 不匹配
    """
    fields = patch.business_fields_dict()
    if not fields:
        raise ValueError("empty patch")

    changed_fields = list(fields.keys())
    now = datetime.now(timezone.utc)

    # 查现有行
    stmt = select(UserDisplayPreferences).where(
        UserDisplayPreferences.user_id == _normalize_user_id(user_id),
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is None:
        # 首写——base_revision 必须为 0
        if patch.base_revision != 0:
            raise DisplayPrefsRevisionConflict(PLATFORM_DEFAULTS.model_copy())
        return await _insert_new(db, user_id, fields, now, changed_fields)

    # 已有行——CAS
    if existing.revision != patch.base_revision:
        raise DisplayPrefsRevisionConflict(_row_to_response(existing))

    return await _update_existing(db, existing, fields, now, changed_fields)


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------


async def _insert_new(
    db: AsyncSession,
    user_id: str,
    fields: dict[str, Any],
    now: datetime,
    changed_fields: list[str],
) -> tuple[DisplayPreferencesResponse, list[str]]:
    """插入新行，用 SAVEPOINT 处理唯一键竞争。"""
    row = UserDisplayPreferences(user_id=_normalize_user_id(user_id))

    # 应用业务字段
    _apply_fields(row, fields)
    row.revision = 1
    row.updated_at = now

    # 处理 fixed_columns：给每个 pageKey 加 saved_at
    if "fixed_columns" in fields and fields["fixed_columns"] is not None:
        stamped = _stamp_fixed_columns(fields["fixed_columns"], now)
        _enforce_fixed_columns_storage_limit(stamped)
        row.fixed_columns = stamped

    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        # 唯一键竞争：另一个请求先写了
        await db.rollback()
        stmt = select(UserDisplayPreferences).where(
            UserDisplayPreferences.user_id == _normalize_user_id(user_id),
        )
        result = await db.execute(stmt)
        winner = result.scalar_one_or_none()
        if winner is not None:
            raise DisplayPrefsRevisionConflict(_row_to_response(winner))
        raise  # 其他完整性错误

    return _row_to_response(row), changed_fields


async def _update_existing(
    db: AsyncSession,
    existing: UserDisplayPreferences,
    fields: dict[str, Any],
    now: datetime,
    changed_fields: list[str],
) -> tuple[DisplayPreferencesResponse, list[str]]:
    """更新已有行（revision CAS 已在调用方验证）。"""
    # 应用业务字段
    _apply_fields(existing, fields)

    # 处理 fixed_columns：整表替换（design §17 G3③：请求是完整目标映射，
    # 没出现的键即删除），逐键保留未变化键的 saved_at
    if "fixed_columns" in fields:
        new_fc = fields["fixed_columns"]
        if new_fc is None:
            existing.fixed_columns = {}
        else:
            stamped = _stamp_fixed_columns(
                new_fc, now, previous=existing.fixed_columns or {},
            )
            _enforce_fixed_columns_storage_limit(stamped)
            existing.fixed_columns = stamped

    existing.revision += 1
    existing.updated_at = now

    await db.flush()
    return _row_to_response(existing), changed_fields


def _apply_fields(row: UserDisplayPreferences, fields: dict[str, Any]) -> None:
    """把业务字段应用到 ORM 行（fixed_columns 由调用方单独处理）。"""
    simple_fields = {
        "amount_unit_override", "font_size", "show_zero", "decimals",
        "negative_red", "highlight_threshold", "density", "grid_edit_mode",
    }
    for name, value in fields.items():
        if name in simple_fields:
            setattr(row, name, value)


def _stamp_fixed_columns(
    fc: dict[str, Any],
    now: datetime,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """给 fixed_columns 的每个 pageKey 加 ``saved_at``。

    design §17 G3③：``columns`` 与已存值相同的键保留原 ``saved_at``，
    新增或内容变化的键写当前时间。``previous`` 是数据库中的现有映射。
    """
    stamped: dict[str, Any] = {}
    iso_now = now.isoformat()
    previous = previous or {}
    for pk, pv in fc.items():
        entry = dict(pv) if isinstance(pv, dict) else {}
        prior = previous.get(pk)
        prior_columns = prior.get("columns") if isinstance(prior, dict) else None
        prior_saved_at = prior.get("saved_at") if isinstance(prior, dict) else None
        if (
            isinstance(prior_columns, list)
            and prior_columns == entry.get("columns")
            and isinstance(prior_saved_at, str)
            and prior_saved_at
        ):
            entry["saved_at"] = prior_saved_at
        else:
            entry["saved_at"] = iso_now
        stamped[pk] = entry
    return stamped


def _row_to_response(row: UserDisplayPreferences) -> DisplayPreferencesResponse:
    """ORM 行 → 线协议响应。"""
    return DisplayPreferencesResponse(
        amount_unit_override=row.amount_unit_override,
        font_size=row.font_size,
        show_zero=row.show_zero,
        decimals=row.decimals,
        negative_red=row.negative_red,
        highlight_threshold=float(row.highlight_threshold)
        if row.highlight_threshold is not None
        else 0.2,
        density=row.density,
        grid_edit_mode=row.grid_edit_mode,
        fixed_columns=row.fixed_columns or {},
        revision=row.revision,
        updated_at=row.updated_at,
    )
