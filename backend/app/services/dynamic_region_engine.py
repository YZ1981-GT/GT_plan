"""Sprint A.2 Batch 1 — 动态区域引擎.

实现：
- expand_dynamic_rows(table_data, ctx) — 按 _dynamic_regions axis=row 展开
- expand_dynamic_columns(table_data, ctx) — 按 _dynamic_regions axis=column 展开
- auto_populate_row_labels(table_data, ctx) — 动态行 label 自动填充

设计原则：
- 纯函数 / 无 DB / 无副作用
- 输入 table_data dict，返回新 dict（不 mutate 原对象）
- ctx 提供数据源（aux_data / wp_data / manual list / labels），由调用方注入

ctx 支持的 key（按 region.dynamic_source 选取）：
- ``aux_data``      : ``{region_name: [{"label": str, "values": [...]}]}``
- ``wp_data``       : ``{region_name: [{"label": str, "values": [...]}]}``
- ``manual``        : ``{region_name: [{"label": str, "values": [...]}]}``
- ``columns``       : ``{region_name: [ColumnMeta-like dict, ...]}`` 用于列展开
- ``labels``        : ``{region_name: [str, str, ...]}`` 用于 auto_populate_row_labels

ctx 也可顶层直接传 ``items`` 走简化路径（行展开），用于单 region 单测场景。

详见 design.md §一 D1/D2 + Sprint A.2 任务卡。
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Iterable, Mapping
from typing import Any

from app.schemas.note_dynamic_schema import DynamicRegion, RowType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _validate_region(region: Mapping[str, Any]) -> None:
    """校验 region 字段完整性（CI-1：start/end 索引有效）.

    抛 ValueError 而非 pydantic ValidationError —— 这层位于 service，
    调用方期望业务异常，而非 schema 异常。
    """
    if "axis" not in region:
        raise ValueError(f"region missing 'axis': {region}")
    if region["axis"] not in ("row", "column"):
        raise ValueError(f"region.axis must be 'row' or 'column': {region['axis']}")
    if "start_idx" not in region or "end_idx" not in region:
        raise ValueError(f"region missing start_idx/end_idx: {region.get('name')}")
    if region["start_idx"] < 0:
        raise ValueError(f"region.start_idx must be >= 0: {region['start_idx']}")
    if region["end_idx"] < region["start_idx"]:
        raise ValueError(
            f"region.end_idx ({region['end_idx']}) must be >= "
            f"start_idx ({region['start_idx']})"
        )


def _coerce_region(region: Any) -> dict[str, Any]:
    """支持 dict / DynamicRegion 两种入参，统一成 dict."""
    if isinstance(region, DynamicRegion):
        return region.model_dump()
    if isinstance(region, dict):
        return dict(region)
    raise TypeError(f"region must be dict or DynamicRegion, got {type(region)}")


def _find_anchor_row(rows: list[dict], region: Mapping[str, Any]) -> dict | None:
    """找到 region 内的模板锚点行.

    优先返回 ``row_type='dynamic_anchor'``；否则降级到 ``start_idx`` 那行。
    返回的是 deep copy（外层不应回写 anchor 模板）。
    """
    start = region["start_idx"]
    end = region["end_idx"]
    if start >= len(rows):
        return None

    for idx in range(start, min(end + 1, len(rows))):
        row = rows[idx]
        if row.get("row_type") == RowType.dynamic_anchor.value:
            return copy.deepcopy(row)

    # 降级 — 取 start_idx 行作为 anchor
    return copy.deepcopy(rows[start])


def _make_dynamic_data_row(
    anchor: Mapping[str, Any],
    label: str,
    values: list[Any] | None,
    *,
    seq_idx: int = 0,
) -> dict[str, Any]:
    """复制 anchor 生成新动态行.

    保留 anchor 的非 label/values/row_type 字段（如 _cell_modes 模板），
    便于后续公式回填。``seq_idx`` 仅作日志，不写入 row。
    """
    new_row = copy.deepcopy(dict(anchor))
    new_row["row_type"] = RowType.dynamic_data.value
    new_row["label"] = label
    if values is not None:
        new_row["values"] = list(values)
    elif "values" in new_row:
        # anchor 上带模板 values（通常 None / 0），保留长度但清空
        new_row["values"] = [None] * len(new_row["values"])

    new_row.pop("is_total", None)  # data 行禁是合计
    new_row.pop("is_anchor_template", None)
    return new_row


def _make_marker_end_row(num_value_cols: int) -> dict[str, Any]:
    """生成 dynamic_marker_end 行（保持 round-trip 安全）."""
    return {
        "row_type": RowType.dynamic_marker_end.value,
        "label": "",
        "values": [None] * max(num_value_cols, 0),
    }


def _resolve_row_items(
    region: Mapping[str, Any], ctx: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """根据 region.dynamic_source 从 ctx 读取行数据.

    返回 ``[{"label": str, "values": list | None}, ...]``。
    """
    source = region.get("dynamic_source", "manual")
    region_name = region.get("name", "")

    # 顶层 items 简化路径（单 region 测试用）
    if "items" in ctx and not any(
        k in ctx for k in ("aux_data", "wp_data", "manual")
    ):
        return list(ctx["items"])

    bucket = ctx.get(source, {})
    if isinstance(bucket, Mapping):
        items = bucket.get(region_name, [])
    else:
        items = bucket

    return list(items or [])


def _resolve_column_items(
    region: Mapping[str, Any], ctx: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """根据 region.dynamic_source 从 ctx 读取列定义."""
    region_name = region.get("name", "")
    columns_bucket = ctx.get("columns", {})
    if isinstance(columns_bucket, Mapping):
        items = columns_bucket.get(region_name, [])
    else:
        items = columns_bucket
    return list(items or [])


def _columns_meta_extend(
    meta: list[dict], new_cols: Iterable[dict], *, insert_at: int
) -> list[dict]:
    """在 ``insert_at`` 位置插入新列定义并返回新列表（不 mutate 原对象）."""
    out = list(meta)
    for offset, col in enumerate(new_cols):
        out.insert(insert_at + offset, dict(col))
    return out


def _next_unique_id(base: str, existing_ids: set[str]) -> str:
    """给重复 column id 加 _1 / _2 后缀，保证 CI-3 全表唯一."""
    if base not in existing_ids:
        return base
    i = 1
    while f"{base}_{i}" in existing_ids:
        i += 1
    return f"{base}_{i}"


# ---------------------------------------------------------------------------
# A.2.1 — 行展开
# ---------------------------------------------------------------------------


def expand_dynamic_rows(
    table_data: Mapping[str, Any], ctx: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """按 _dynamic_regions axis='row' 展开动态行.

    步骤：
    1. 找到所有 axis=row 的 region（保持声明顺序，逆序处理避免索引漂移）
    2. 在 region.start_idx ~ region.end_idx 之间读取 anchor 模板行
    3. 按 dynamic_source 从 ctx 加载实际数据
    4. 按数据条数 explode anchor 行（label / values 替换）
    5. 在 region 末尾插入 dynamic_marker_end（round-trip 标记）
    6. 同步调整后续 region 的 start_idx/end_idx

    幂等：若 region 内已存在 dynamic_data + dynamic_marker_end，则跳过该 region。
    """
    ctx = dict(ctx or {})
    out = copy.deepcopy(dict(table_data))
    rows: list[dict] = list(out.get("rows", []))
    regions: list[dict] = [
        _coerce_region(r) for r in out.get("_dynamic_regions", [])
    ]

    # 收集 row regions 并按 start_idx 升序、逆序处理（保后续索引）
    row_regions = [
        (i, r) for i, r in enumerate(regions) if r.get("axis") == "row"
    ]
    row_regions.sort(key=lambda x: x[1].get("start_idx", 0))

    # 从右到左展开避免索引漂移
    for region_idx, region in reversed(row_regions):
        _validate_region(region)
        items = _resolve_row_items(region, ctx)

        # 幂等检查：region 内已有 dynamic_data 且末尾是 marker_end
        already_expanded = any(
            r.get("row_type") == RowType.dynamic_data.value
            for r in rows[region["start_idx"] : region["end_idx"] + 1]
        ) and any(
            r.get("row_type") == RowType.dynamic_marker_end.value
            for r in rows[region["start_idx"] : region["end_idx"] + 1]
        )
        if already_expanded:
            logger.debug(
                "region %s already expanded, skip", region.get("name")
            )
            continue

        if not items:
            # 空数据 → 不变
            continue

        anchor = _find_anchor_row(rows, region)
        if anchor is None:
            logger.warning(
                "region %s has no anchor row in [%d:%d]",
                region.get("name"),
                region["start_idx"],
                region["end_idx"],
            )
            continue

        # 生成新动态行 + 末尾 marker
        num_value_cols = len(anchor.get("values") or [])
        new_rows: list[dict] = []
        for seq, item in enumerate(items):
            new_rows.append(
                _make_dynamic_data_row(
                    anchor,
                    label=item.get("label", ""),
                    values=item.get("values"),
                    seq_idx=seq,
                )
            )
        new_rows.append(_make_marker_end_row(num_value_cols))

        # 用 new_rows 替换 region 范围 (保留 region 之外的合计/小计行)
        original_start = region["start_idx"]
        original_end = region["end_idx"]
        before = rows[:original_start]
        after = rows[original_end + 1 :]
        rows = before + new_rows + after

        # 调整本 region 的 end_idx
        new_end = original_start + len(new_rows) - 1
        delta = new_end - original_end
        regions[region_idx]["end_idx"] = new_end

        # 调整其他 region：在本 region 后的需要整体偏移
        for j, other in enumerate(regions):
            if j == region_idx:
                continue
            if other.get("axis") != "row":
                continue
            if other.get("start_idx", 0) > original_end:
                regions[j]["start_idx"] = other["start_idx"] + delta
                regions[j]["end_idx"] = other["end_idx"] + delta

    out["rows"] = rows
    out["_dynamic_regions"] = regions
    return out


# ---------------------------------------------------------------------------
# A.2.2 — 列展开 + 多级表头
# ---------------------------------------------------------------------------


def expand_dynamic_columns(
    table_data: Mapping[str, Any], ctx: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """按 _dynamic_regions axis='column' 展开动态列.

    步骤：
    1. 找到 axis=column 的 region
    2. 读取 _columns_meta 中模板列定义（保留 header_path / col_type 等）
    3. 按 dynamic_source 从 ctx 加载新列定义（含 header_path 多级表头）
    4. 在 region.start_idx 处插入新列（保证 column_id 全表唯一，CI-3）
    5. 同步更新 rows[i].values（按 column_id 对齐，新列默认 None）
    6. 调整本 region 的 end_idx 与后续 column region 偏移

    幂等：若 ctx 中相同 column_id 已存在于 _columns_meta，则跳过该 column。
    """
    ctx = dict(ctx or {})
    out = copy.deepcopy(dict(table_data))
    columns_meta: list[dict] = list(out.get("_columns_meta", []))
    rows: list[dict] = list(out.get("rows", []))
    regions: list[dict] = [
        _coerce_region(r) for r in out.get("_dynamic_regions", [])
    ]

    col_regions = [
        (i, r) for i, r in enumerate(regions) if r.get("axis") == "column"
    ]
    col_regions.sort(key=lambda x: x[1].get("start_idx", 0))

    for region_idx, region in reversed(col_regions):
        _validate_region(region)
        new_col_defs = _resolve_column_items(region, ctx)
        if not new_col_defs:
            continue

        existing_ids = {c.get("id") for c in columns_meta if c.get("id")}
        # 过滤已存在 + 重命名冲突 id
        deduped: list[dict] = []
        for col in new_col_defs:
            cid = col.get("id") or ""
            if not cid:
                logger.warning(
                    "column in region %s missing id, skip", region.get("name")
                )
                continue
            if cid in existing_ids:
                # 幂等：已存在则跳过（不再重复插入，保护 CI-3 唯一性）
                logger.debug(
                    "column id %s already in _columns_meta, skip", cid
                )
                continue
            new_col = dict(col)
            # 防御：col_type 兜底标 dynamic
            new_col.setdefault("col_type", "dynamic")
            new_col.setdefault("header_path", [new_col.get("label", "")])
            deduped.append(new_col)
            existing_ids.add(cid)

        if not deduped:
            continue

        insert_at = region["start_idx"]
        if insert_at < 0:
            insert_at = 0
        if insert_at > len(columns_meta):
            insert_at = len(columns_meta)

        columns_meta = _columns_meta_extend(columns_meta, deduped, insert_at=insert_at)

        # rows[i].values 同步：在 insert_at 处插入 None
        # values 列与 _columns_meta 一一对齐时，values[k] ↔ columns_meta[k]
        n_new = len(deduped)
        new_rows: list[dict] = []
        for r in rows:
            r_copy = dict(r)
            vals = list(r_copy.get("values") or [])
            # 仅当 values 长度 ≥ insert_at（和原 columns 对齐）才扩展
            insert_pos = min(insert_at, len(vals))
            new_vals = vals[:insert_pos] + [None] * n_new + vals[insert_pos:]
            r_copy["values"] = new_vals
            new_rows.append(r_copy)
        rows = new_rows

        # 调整 region.end_idx
        new_end = region["start_idx"] + n_new - 1
        regions[region_idx]["end_idx"] = max(new_end, region["start_idx"])

        # 调整后续 column region 偏移
        for j, other in enumerate(regions):
            if j == region_idx or other.get("axis") != "column":
                continue
            if other.get("start_idx", 0) > region["start_idx"]:
                regions[j]["start_idx"] = other["start_idx"] + n_new
                regions[j]["end_idx"] = other["end_idx"] + n_new

    out["_columns_meta"] = columns_meta
    out["rows"] = rows
    out["_dynamic_regions"] = regions
    return out


# ---------------------------------------------------------------------------
# A.2.7 — 动态行 label 自动填充
# ---------------------------------------------------------------------------


def auto_populate_row_labels(
    table_data: Mapping[str, Any], ctx: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """动态行 label 自动从 ctx 数据源填充.

    场景：
    - 模板行 row_type='dynamic_data' 且 label='' 时，从 ctx['labels'][region_name] 取
    - 已有 label 不覆盖（保护用户编辑）
    - labels 数量与空 label 行数不匹配时，按 min(len) 填充并 warning

    通常 expand_dynamic_rows 会一并填充 label，本函数用于已 expand 的表格做
    label 后置填充（如 binding 解析后再补 label）。
    """
    ctx = dict(ctx or {})
    out = copy.deepcopy(dict(table_data))
    rows: list[dict] = list(out.get("rows", []))
    regions = [
        _coerce_region(r) for r in out.get("_dynamic_regions", [])
    ]

    labels_bucket = ctx.get("labels", {})
    if not isinstance(labels_bucket, Mapping):
        labels_bucket = {}

    for region in regions:
        if region.get("axis") != "row":
            continue
        labels = list(labels_bucket.get(region.get("name", ""), []) or [])
        if not labels:
            continue

        start = region["start_idx"]
        end = region["end_idx"]
        # 收集 region 内的 dynamic_data 空 label 行
        empty_indices = [
            i
            for i in range(start, min(end + 1, len(rows)))
            if rows[i].get("row_type") == RowType.dynamic_data.value
            and not (rows[i].get("label") or "").strip()
        ]

        if len(labels) < len(empty_indices):
            logger.warning(
                "region %s: labels count (%d) < empty rows (%d), partial fill",
                region.get("name"),
                len(labels),
                len(empty_indices),
            )

        for idx, label in zip(empty_indices, labels):
            rows[idx] = {**rows[idx], "label": label}

    out["rows"] = rows
    return out


__all__ = [
    "expand_dynamic_rows",
    "expand_dynamic_columns",
    "auto_populate_row_labels",
]
