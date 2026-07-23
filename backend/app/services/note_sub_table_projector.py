"""附注子表投影器：sub_table_data + 列头元数据 → 渲染器可消费的 _tables[]

纯函数、无 IO、读时执行、不持久化 `_tables`（sub_table_data 仍是权威存储）。
供附注模块章节详情读取（``get_note_detail``）与 Word 导出（``note_word_exporter``）
复用同一实现，避免前后端两套逻辑漂移。

spec: disclosure-table-sync-convergence
- design §Projector 逻辑 + §Data Models（Projected_Tables）
- Correctness Properties P1~P8（纯函数 / 列序 / 缺字段空单元 / 额外字段忽略 /
  合计行 / 多表键序 / 来源优先级 / 降级不杜撰）
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ``_source`` 视为"底稿同步来源"的标识（投影权威来源，Req6.1）
_WORKPAPER_SOURCES = ("workpaper", "workpaper_html")


def _is_meta_key(key: Any) -> bool:
    """``_`` 前缀键为元数据（如 ``_note_texts`` / ``_manual_override``），跳过。"""
    return str(key).startswith("_")


def _pick_label_def(defs: list[dict]) -> dict | None:
    """选标签列定义：首个 ``is_label`` 为真者；无则首个有效定义。"""
    for d in defs:
        if isinstance(d, dict) and d.get("is_label"):
            return d
    for d in defs:
        if isinstance(d, dict):
            return d
    return None


def project_sub_tables(table_data: Any) -> list[dict] | None:
    """把 ``sub_table_data`` + ``_sub_table_columns`` 投影为可渲染 ``_tables[]``。

    Returns:
        - ``None``：非 workpaper 来源 → 调用方 SHALL 沿用既有 ``_tables``/``rows``
          （Requirement 6.2 / Property 7），不投影。
        - ``list``：投影出的表列表（可能为空 list，表示 workpaper 来源但无子表）。

    纯函数：不修改入参、无 IO、同输入同输出（Property 1）。
    """
    if not isinstance(table_data, dict):
        return None
    source = table_data.get("_source")
    if source not in _WORKPAPER_SOURCES:
        return None  # Property 7: 非 workpaper 来源不投影

    sub = table_data.get("sub_table_data")
    if not isinstance(sub, dict) or not sub:
        return []  # workpaper 来源但无子表

    cols_map = table_data.get("_sub_table_columns")
    if not isinstance(cols_map, dict):
        cols_map = {}

    tables: list[dict] = []
    for key, rows in sub.items():  # 保持 sub_table_data 键插入序（Property 6）
        if _is_meta_key(key):
            continue
        if not isinstance(rows, list):
            logger.warning(
                "project_sub_tables: sub-table %r rows not a list (%s), skip",
                key, type(rows).__name__,
            )
            continue

        defs_raw = cols_map.get(key)
        defs = (
            [d for d in defs_raw if isinstance(d, dict) and d.get("key")]
            if isinstance(defs_raw, list)
            else []
        )

        if not defs:
            # Property 8 / Requirement 7.2 降级：无列头元数据 → 绝不用英文字段键当 header。
            # 仅以 label 列（行名）可读呈现；不产出任何数据值列（values 恒空）。
            has_label = any(isinstance(r, dict) and ("label" in r) for r in rows)
            projected_rows = [
                {
                    "label": r.get("label", ""),
                    "values": [],
                    "is_total": bool(r.get("is_total", False)),
                }
                for r in rows
                if isinstance(r, dict)
            ]
            tables.append({
                "name": key,
                "headers": ["项目"] if has_label else [],
                "columns": [],
                "rows": projected_rows,
                "_source_sub_table_key": key,
                "_needs_columns": True,  # 前端据此提示"待配置列头"
            })
            continue

        label_def = _pick_label_def(defs)
        label_key = label_def.get("key") if isinstance(label_def, dict) else None
        value_defs = [d for d in defs if d is not label_def]
        headers = [str(label_def.get("label", ""))] + [
            str(d.get("label", "")) for d in value_defs
        ]

        projected_rows = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            label_val = r.get(label_key, "") if label_key else ""
            # 兜底：标签列键值缺失时回退通用 `label`（合计/小计行常用 label 而非业务键）
            if (label_val is None or label_val == "") and label_key != "label":
                label_val = r.get("label", label_val)
            projected_rows.append({
                "label": label_val,
                # 缺字段 → None（Property 3）；未声明字段自动忽略（Property 4）
                "values": [r.get(d.get("key")) for d in value_defs],
                "is_total": bool(r.get("is_total", False)),  # Property 5
            })

        tables.append({
            "name": key,
            "headers": headers,
            "columns": defs,
            "rows": projected_rows,
            "_source_sub_table_key": key,
        })

    return tables
