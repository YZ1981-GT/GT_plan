"""Sprint A.2.5 — 多源 fallback 链 + provenance 记录（A.2.6）.

核心 API:
- ``resolve_with_fallback(binding, ctx)``         主源 + fallback 链解析
- ``attach_cell_provenance(table_data, key, prov)``  写 ``_cell_provenance``
- ``get_cell_provenance(table_data, key)``           读

binding 协议（v2 多源）::

    {
      "primary": {"source": "wp_data", "wp_code": "h08", ...},
      "fallback": [
        {"source": "trial_balance", "account_codes": ["1601"]},
        {"source": "manual", "default_value": 0},
      ],
      "show_provenance": true
    }

或 v1 单源（向后兼容）::

    {"source": "wp_data", "wp_code": "h08", ...}

CI-9: fallback 列表最多 3 项（超过抛 ``ValueError``）.
CI-10: provenance 字典必含 ``"source"`` 字段.

详见 design.md §一 D3 / D4 + Sprint A.2.5/2.6 任务卡。
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any

from app.services.note_source_resolvers import dispatch_resolver

logger = logging.getLogger(__name__)


# CI-9：fallback 链最多 3 级
MAX_FALLBACK_DEPTH: int = 3

# 哪些 binding 字段属于"数据源参数"，要写进 source_detail
_SOURCE_DETAIL_KEYS: tuple[str, ...] = (
    "wp_code",
    "sheet",
    "extract",
    "cell_ref",
    "col_letter",
    "row_range",
    "label_col",
    "value_cols",
    "row_filter",
    "account_codes",
    "field",
    "agg",
    "aux_type",
    "bucket",
    "period_filter",
    "section",
    "manual_value",
    "default_value",
)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _normalize_binding(binding: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """把任意 binding 归一化成 ``(primary, fallback_list)``.

    - v2: 含 ``primary`` key → 直接拆
    - v1: 不含 ``primary`` 但含 ``source`` → 视为 primary，fallback 空
    - 其他：抛 ValueError
    """
    if not isinstance(binding, dict):
        raise ValueError(f"binding must be dict, got {type(binding).__name__}")

    if "primary" in binding:
        primary = binding.get("primary")
        fallback = binding.get("fallback") or []
    else:
        # v1：整个 binding 当 primary
        primary = binding
        fallback = []

    if not isinstance(primary, dict):
        raise ValueError("binding.primary must be a dict")
    if not isinstance(fallback, list):
        raise ValueError("binding.fallback must be a list")

    return primary, list(fallback)


def _validate_fallback_depth(fallback: list[dict[str, Any]]) -> None:
    """CI-9：fallback 列表最多 ``MAX_FALLBACK_DEPTH`` 项."""
    if len(fallback) > MAX_FALLBACK_DEPTH:
        raise ValueError(
            f"fallback chain exceeds CI-9 limit: "
            f"{len(fallback)} > {MAX_FALLBACK_DEPTH}"
        )


def _build_source_detail(source_binding: dict[str, Any]) -> dict[str, Any]:
    """从单个 source binding 中收集 source_detail（供 provenance 审计追溯）."""
    detail: dict[str, Any] = {}
    for key in _SOURCE_DETAIL_KEYS:
        if key in source_binding:
            detail[key] = source_binding[key]
    return detail


def _now_iso() -> str:
    """ISO8601 UTC 时间戳."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_provenance(
    source: str,
    value: Any,
    fallback_used: bool,
    fallback_index: int | None,
    source_detail: dict[str, Any],
) -> dict[str, Any]:
    """构造 provenance dict（CI-10：必含 source 字段）."""
    return {
        "source": source,
        "fallback_used": fallback_used,
        "fallback_index": fallback_index,
        "value": value,
        "fetched_at": _now_iso(),
        "source_detail": source_detail,
    }


# ---------------------------------------------------------------------------
# Public API: resolve_with_fallback
# ---------------------------------------------------------------------------


async def resolve_with_fallback(
    binding: dict[str, Any],
    ctx: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    """主源 + fallback 链解析，返回 ``(value, provenance)``.

    provenance 字段：
    - ``source``:         实际取值的 source（CI-10 必填）
    - ``fallback_used``:  bool
    - ``fallback_index``: int | None  (0-based；None = 主源命中)
    - ``value``:          取到的值（用于审计追溯）
    - ``fetched_at``:     取数时间 ISO 格式
    - ``source_detail``:  dict（如 wp_code / sheet / cell_ref / account_codes）

    场景：
    - 主源命中:           ``(value, {source: <primary>, fallback_used: False, fallback_index: None})``
    - fallback[0] 命中:   ``(value, {source: <fb0>, fallback_used: True, fallback_index: 0})``
    - 全部失败:           ``(None,  {source: 'none', fallback_used: True, fallback_index: None})``

    CI-9: fallback 列表 > 3 抛 ValueError；CI-10: provenance 始终含 source.
    """
    primary, fallback = _normalize_binding(binding)
    _validate_fallback_depth(fallback)

    # 主源
    primary_source = primary.get("source")
    if isinstance(primary_source, str) and primary_source:
        try:
            value = await dispatch_resolver(primary, ctx)
        except Exception as err:
            logger.warning("resolve_with_fallback: primary raised %s", err)
            value = None
        if _is_value_present(value):
            return value, _make_provenance(
                source=primary_source,
                value=value,
                fallback_used=False,
                fallback_index=None,
                source_detail=_build_source_detail(primary),
            )

    # fallback 链
    for idx, fb in enumerate(fallback):
        if not isinstance(fb, dict):
            continue
        fb_source = fb.get("source")
        if not isinstance(fb_source, str) or not fb_source:
            continue
        try:
            value = await dispatch_resolver(fb, ctx)
        except Exception as err:
            logger.warning("resolve_with_fallback: fallback[%d] raised %s", idx, err)
            value = None
        if _is_value_present(value):
            return value, _make_provenance(
                source=fb_source,
                value=value,
                fallback_used=True,
                fallback_index=idx,
                source_detail=_build_source_detail(fb),
            )

    # 全部失败 — provenance 仍含 source='none'（CI-10）
    return None, _make_provenance(
        source="none",
        value=None,
        fallback_used=True,
        fallback_index=None,
        source_detail={},
    )


def _is_value_present(value: Any) -> bool:
    """value 是否视为命中（非 None / 非空 list）.

    None / 空 list → 视为缺失，进入下一级 fallback；
    0 / 0.0 / "" → 视为有效命中（用户显式赋零或空文本是合法答案）.
    """
    if value is None:
        return False
    if isinstance(value, list) and len(value) == 0:
        return False
    return True


# ---------------------------------------------------------------------------
# Public API: provenance 写入辅助 (A.2.6)
# ---------------------------------------------------------------------------


def attach_cell_provenance(
    table_data: dict[str, Any],
    cell_key: str,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """把 provenance 写入 ``table_data._cell_provenance[cell_key]``.

    Args:
        table_data: 附注 table_data dict（含 rows / _columns_meta / 等）。
        cell_key:   ``"row_idx:col_id"`` 或自定义 key。
        provenance: 由 :func:`resolve_with_fallback` 返回的 provenance dict。

    Returns:
        新 table_data（不 mutate 原对象，深拷贝后写入）。

    校验：CI-10 — provenance 必含 ``source`` 字段，否则抛 ValueError。
    """
    if not isinstance(table_data, dict):
        raise TypeError("table_data must be dict")
    if not isinstance(cell_key, str) or not cell_key:
        raise ValueError("cell_key must be non-empty str")
    if not isinstance(provenance, dict):
        raise TypeError("provenance must be dict")
    if "source" not in provenance:
        # CI-10 卡点
        raise ValueError("provenance missing required 'source' field (CI-10)")

    new_td = copy.deepcopy(table_data)
    bucket = new_td.get("_cell_provenance")
    if not isinstance(bucket, dict):
        bucket = {}
        new_td["_cell_provenance"] = bucket
    bucket[cell_key] = copy.deepcopy(provenance)
    return new_td


def get_cell_provenance(
    table_data: dict[str, Any],
    cell_key: str,
) -> dict[str, Any] | None:
    """读取已记录的 provenance（前端 UI 数据源 chip 显示用）.

    Returns:
        provenance dict / None（缺失或非 dict）。
    """
    if not isinstance(table_data, dict):
        return None
    bucket = table_data.get("_cell_provenance")
    if not isinstance(bucket, dict):
        return None
    val = bucket.get(cell_key)
    return val if isinstance(val, dict) else None


__all__ = [
    "MAX_FALLBACK_DEPTH",
    "attach_cell_provenance",
    "get_cell_provenance",
    "resolve_with_fallback",
]
