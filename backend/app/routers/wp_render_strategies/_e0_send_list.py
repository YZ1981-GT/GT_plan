"""E0 发函记录表 render 策略 —— 消除 grid 兜底示例值污染。

走 RENDERER_DISPATCH，在 grid 兜底之前 return → extract_grid(data_only=True) 永不执行 →
XX银行/XX财务公司 示例缓存值自动消失。
"""
from __future__ import annotations

import logging
import re

import sqlalchemy as sa

from app.services.e0_send_list.send_list_specs import (
    FORMAT_VERSION,
    SHEET_E03,
    SHEET_E04,
    SHEET_E05,
    column_map,
)
from app.services.e0_send_list.e03_prefill import build_e03_prefill

from ._context import RenderContext

logger = logging.getLogger(__name__)


def _initial_data(sheet: str) -> dict:
    """空的新格式初始载荷 —— 无持久化时返回此结果。"""
    return {
        "_format": FORMAT_VERSION[sheet],
        "rows": [],
        "conclusion": {
            "audit_explanation": "",
            "overall_conclusion": "",
            "remarks": "",
        },
    }


def migrate_legacy_grid_payload(sheet: str, legacy: dict) -> dict:
    """纯函数 / 幂等 / 不写库。

    - 已有正确 _format → 原样返回
    - legacy grid（有 cells/column_meta/header_rows 而无 _format）→ 按 column_map 转 rows
    - 保留 _row_id
    - conclusion 三键原样搬
    - manifest 未声明的列字母收进 row['_unmapped_cells']（不丢弃）
    """
    # 幂等：已有正确 _format → 原样返回
    if legacy.get("_format") == FORMAT_VERSION.get(sheet):
        return legacy

    # 不是 legacy grid 形态 → 原样返回（可能是中间形态或未知形态）
    if "cells" not in legacy and "column_meta" not in legacy:
        if "_format" in legacy:
            return legacy
        if not legacy or legacy == {}:
            return _initial_data(sheet)
        return legacy

    # Legacy grid 形态迁移
    col_map = column_map(sheet)
    cells: dict = legacy.get("cells", {})
    existing_rows: list[dict] = legacy.get("rows", [])

    # 从 cells 中收集行号
    row_numbers: set[int] = set()
    _CELL_RE = re.compile(r"([A-Z]+)(\d+)")
    for cell_ref in cells:
        m = _CELL_RE.match(cell_ref)
        if m:
            row_numbers.add(int(m.group(2)))

    # 按行号排序构建 rows
    migrated_rows: list[dict] = []
    for row_num in sorted(row_numbers):
        row_data: dict = {}
        unmapped: dict = {}

        for cell_ref, cell_val in cells.items():
            m = _CELL_RE.match(cell_ref)
            if not m:
                continue
            col_letter = m.group(1)
            r = int(m.group(2))
            if r != row_num:
                continue

            # 提取值
            value = cell_val.get("v") if isinstance(cell_val, dict) else cell_val
            if value is None or value == "":
                continue

            if col_letter in col_map:
                row_data[col_map[col_letter]] = value
            else:
                unmapped[col_letter] = value

        # 跳过完全空的行
        if not row_data and not unmapped:
            continue

        # 跳过只有 0/0.0 值的行（如 E0-4 R16 残留 G=0 H=0）
        if not unmapped and all(
            v == 0 or v == 0.0 for v in row_data.values()
        ):
            continue

        if unmapped:
            row_data["_unmapped_cells"] = unmapped

        migrated_rows.append(row_data)

    # 分配 _row_id：保留既有行的 _row_id
    import time

    for i, row in enumerate(migrated_rows):
        if i < len(existing_rows) and "_row_id" in existing_rows[i]:
            row["_row_id"] = existing_rows[i]["_row_id"]
        else:
            row["_row_id"] = f"row-migrated-{int(time.time() * 1000)}-{i}"

    # 搬 conclusion
    conclusion = {
        "audit_explanation": "",
        "overall_conclusion": "",
        "remarks": "",
    }
    legacy_conclusion = legacy.get("conclusion", {})
    if isinstance(legacy_conclusion, dict):
        for k in ("audit_explanation", "overall_conclusion", "remarks"):
            if k in legacy_conclusion:
                conclusion[k] = legacy_conclusion[k]

    return {
        "_format": FORMAT_VERSION[sheet],
        "rows": migrated_rows,
        "conclusion": conclusion,
    }


# ─── Render functions (one per componentType) ────────────────────────────────


async def render_e0_send_list_e03(ctx: RenderContext) -> dict | None:
    """Render 策略 for 货币资金发函记录表E0-3."""
    result = _render_send_list(SHEET_E03, ctx)
    # E1-3 取数（transient，不落库）
    if isinstance(result, dict):
        try:
            prefill = await build_e03_prefill(ctx.db, ctx.project_id, ctx.year)
            if prefill is not None:
                result["_prefill"] = prefill
        except Exception:
            logger.warning("E0-3 prefill 注入失败，跳过", exc_info=True)
    return result


async def render_e0_send_list_e04(ctx: RenderContext) -> dict | None:
    """Render 策略 for 借款发函记录表E0-4."""
    return _render_send_list(SHEET_E04, ctx)


async def render_e0_send_list_e05(ctx: RenderContext) -> dict | None:
    """Render 策略 for 应付银行承兑汇票发函记录表E0-5."""
    result = _render_send_list(SHEET_E05, ctx)
    # F3-2 取数（transient，不落库）— 对称 E0-3 的 E1-3 取数
    if isinstance(result, dict):
        try:
            from app.services.e0_send_list.f3_2_notes_source import build_e05_prefill
            prefill = await _build_e05_prefill_from_f3(ctx.db, ctx.project_id)
            if prefill is not None:
                result["_prefill"] = prefill
        except Exception:
            logger.warning("E0-5 prefill 注入失败，跳过", exc_info=True)
    return result


async def _build_e05_prefill_from_f3(db, project_id) -> dict | None:
    """从 F3 底稿读 F3-2 明细行，调用 build_e05_prefill。"""
    from app.services.e0_send_list.f3_2_notes_source import build_e05_prefill

    # 找 F3 底稿
    query = sa.text("""
        SELECT wp.id
        FROM working_paper wp
        JOIN wp_index wi ON wi.id = wp.wp_index_id
        WHERE wp.project_id = :pid
          AND wi.wp_code = 'F3'
          AND wp.is_deleted = false
        LIMIT 1
    """)
    result = await db.execute(query, {"pid": str(project_id)})
    row = result.first()
    if not row:
        return None

    f3_wp_id = str(row[0])

    # 读 F3-2 的行数据（在 checklist_responses 里）
    cr_query = sa.text("""
        SELECT value FROM checklist_responses
        WHERE working_paper_id = :wp_id AND item_id = 'F3-2-rows'
    """)
    cr_result = await db.execute(cr_query, {"wp_id": f3_wp_id})
    cr_row = cr_result.first()
    if not cr_row or not cr_row[0]:
        return None

    import json
    f3_rows = cr_row[0] if isinstance(cr_row[0], list) else json.loads(cr_row[0]) if isinstance(cr_row[0], str) else None
    if not f3_rows or not isinstance(f3_rows, list):
        return None

    return build_e05_prefill(f3_rows)


def _render_send_list(sheet: str, ctx: RenderContext) -> dict | None:
    """Common render logic for all three send-list sheets.

    - If persisted data exists → migrate if needed → return
    - If no persisted data → return initial (empty) data
    - Any error → fail-open: return initial data with warning logged
    """
    try:
        sheet_data = ctx.sheet_html_data
        if not isinstance(sheet_data, dict) or not sheet_data:
            return _initial_data(sheet)

        # Migrate legacy if needed
        return migrate_legacy_grid_payload(sheet, sheet_data)
    except Exception:
        # Fail-open: never block render
        logger.warning(
            f"E0 send list render failed for {sheet}, returning initial data",
            exc_info=True,
        )
        return _initial_data(sheet)
