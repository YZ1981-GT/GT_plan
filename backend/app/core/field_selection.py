"""
字段选择核心模块 — F5 API 响应字段选择

提供 ?fields=id,wp_code,status 查询参数解析和动态 SQLAlchemy column 投影，
减少列表 API 响应体积（排除 parsed_data 等 MB 级 JSONB 字段）。

Requirements: 5.1, 5.2, 5.4, 5.5
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import InstrumentedAttribute


# ---------------------------------------------------------------------------
# 默认摘要字段（WorkpaperList 场景）
# 排除 parsed_data / file_content / raw_html 等大字段
# ---------------------------------------------------------------------------
DEFAULT_SUMMARY_FIELDS: set[str] = {
    "id",
    "wp_code",
    "wp_name",
    "status",
    "cycle",
    "assignee_id",
    "updated_at",
    "created_at",
}

# ---------------------------------------------------------------------------
# 屏蔽字段列表（安全：不暴露敏感字段）
# ---------------------------------------------------------------------------
BLOCKED_FIELDS: set[str] = {
    "parsed_data",
    "file_content",
    "raw_html",
    "password_hash",
}


def parse_fields(fields: str | None) -> set[str] | None:
    """解析 ?fields=id,wp_code,status → {'id', 'wp_code', 'status'}

    Args:
        fields: 逗号分隔的字段名字符串，或 None

    Returns:
        字段名集合，或 None（表示使用默认字段集）
    """
    if not fields or not fields.strip():
        return None
    result = {f.strip() for f in fields.split(",") if f.strip()}
    return result if result else None


def resolve_columns(
    model: type[Any],
    requested_fields: set[str] | None,
    default_fields: set[str] | None = None,
    blocked_fields: set[str] | None = None,
) -> list[InstrumentedAttribute]:
    """动态 SQLAlchemy column 投影

    根据请求的字段列表，返回对应的 SQLAlchemy column 对象列表，
    用于 select(col1, col2, ...) 动态构建查询。

    Args:
        model: SQLAlchemy 模型类（如 WorkingPaper）
        requested_fields: 用户请求的字段集合（parse_fields 返回值）
            - None 表示使用 default_fields
        default_fields: 默认字段集合（当 requested_fields 为 None 时使用）
            - None 则使用模型全部字段（减去 blocked）
        blocked_fields: 屏蔽字段集合（安全：永远不返回这些字段）
            - None 则使用 BLOCKED_FIELDS 模块默认值

    Returns:
        SQLAlchemy column 对象列表，可直接用于 select()

    Notes:
        - 无效字段名静默忽略（不报错）
        - blocked 字段即使被显式请求也不返回
        - 返回列表至少包含 id 字段（如果模型有 id 列）
    """
    if blocked_fields is None:
        blocked_fields = BLOCKED_FIELDS

    # 获取模型的所有实际列名
    mapper = inspect(model)
    all_column_names: set[str] = {col.key for col in mapper.column_attrs}

    # 确定目标字段集
    if requested_fields is not None:
        # 用户指定了字段：取交集（忽略无效字段名）
        target_fields = requested_fields & all_column_names
    elif default_fields is not None:
        # 使用默认字段集：取交集（忽略默认集中不存在的字段）
        target_fields = default_fields & all_column_names
    else:
        # 无默认集：使用全部字段
        target_fields = all_column_names

    # 移除屏蔽字段
    target_fields = target_fields - blocked_fields

    # 确保至少包含 id 字段（如果模型有）
    if "id" in all_column_names and not target_fields:
        target_fields = {"id"}

    # 转换为 SQLAlchemy column 对象
    columns: list[InstrumentedAttribute] = []
    for field_name in sorted(target_fields):  # 排序保证稳定输出
        col = getattr(model, field_name, None)
        if col is not None and isinstance(col, InstrumentedAttribute):
            columns.append(col)

    return columns
