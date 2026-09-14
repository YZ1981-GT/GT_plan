"""working_paper.parsed_data 变更后的地址注册表缓存失效钩子。

custom-workpaper-formula-binding 任务 4.3：统一在 commit 之后调用，
避免 invalidate 散落在各写 parsed_data 路径。

已接线：wp_formula / wp_html_save / wp_user_formulas / working_paper（解析+univer_save）/
wp_fine_rules / wp_procedure_status / wp_ai_confirm / 各专题计算路由（wp_g_* / wp_h_* / wp_i_* / wp_j_* / wp_k_* / wp_l_* / wp_m_* / wp_f2_*）/ wp_procedure_trim。
"""

from __future__ import annotations

import logging
import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.models.workpaper_models import WorkingPaper

logger = logging.getLogger(__name__)


def _cell_ref_to_rc(cell_ref: str) -> tuple[int, int]:
    """单元格引用 → (row, col)，均为 1-based；解析失败返回 (0, 0)。

    `B5` → (5, 2)；多字母列 `AA3` → (3, 27)；`$B$5` → (5, 2)。
    非法输入（`B` / `5` / 空串 / `None`）一律返回 (0, 0)，由调用方按「不更新边界」处理
    —— 返回 0 而不是抛异常，是因为本函数在公式求值回填这条 fail-open 路径上，
    一个坏 cell_ref 不应让整次保存失败。
    """
    if not cell_ref:
        return (0, 0)
    m = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d{1,7})", str(cell_ref).strip())
    if not m:
        return (0, 0)
    letters, digits = m.group(1).upper(), m.group(2)
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - 64)
    row = int(digits)
    if row <= 0 or col <= 0:
        return (0, 0)
    return (row, col)


def write_cell_to_parsed_data(
    wp: WorkingPaper,
    *,
    sheet_name: str,
    cell_ref: str,
    value: Any,
) -> None:
    """将求值结果写入 parsed_data.html_data[sheet].cells[cell]（保留 dict 结构）。"""
    cell_up = cell_ref.strip().upper()
    parsed = dict(wp.parsed_data or {})
    html_data = parsed.get("html_data")
    if not isinstance(html_data, dict):
        html_data = {}
    sheet_data = html_data.get(sheet_name)
    if not isinstance(sheet_data, dict):
        sheet_data = {}
    cells = sheet_data.get("cells")
    if not isinstance(cells, dict):
        cells = {}
    existing = cells.get(cell_up)
    if isinstance(existing, dict):
        existing = {**existing, "value": value, "v": value}
    elif existing is not None:
        existing = {"value": value, "v": value}
    else:
        existing = value
    cells[cell_up] = existing
    sheet_data["cells"] = cells

    # 🔴 维护 max_row / max_col —— 前端 `GtGridSheet.hasData` 判据是
    # `Object.keys(cells).length > 0 && maxRow > 0`。改造前本函数**只写 cells**，
    # 于是自定义底稿公式求值后网格仍显示「此表格底稿模板暂无内容」，公式选址列表
    # 也恒空（它读同一份 cells）。
    # 只增不减（单调）：删公式不缩边界，避免把用户其他内容挤出可见范围。
    #
    # 🔴 键存在性先兜底：cell_ref 非法时（`_cell_ref_to_rc` 返 (0,0)）下面两个
    # `if` 都不进，若 sheet_data 是新建的就会出现「有 cells 但没有 max_row/max_col」
    # 这种半成品状态 —— 前端 `hasData` 读 `maxRow` 得 undefined 判 false，网格照样
    # 显示「暂无内容」，而下游按键取值还会 KeyError。setdefault 只补缺失键、
    # 不动既有值，故不破坏单调性。
    sheet_data.setdefault("max_row", 0)
    sheet_data.setdefault("max_col", 0)

    _row, _col = _cell_ref_to_rc(cell_up)
    if _row > 0:
        try:
            _cur_row = int(sheet_data.get("max_row") or 0)
        except (TypeError, ValueError):
            _cur_row = 0
        sheet_data["max_row"] = max(_cur_row, _row)
    if _col > 0:
        try:
            _cur_col = int(sheet_data.get("max_col") or 0)
        except (TypeError, ValueError):
            _cur_col = 0
        sheet_data["max_col"] = max(_cur_col, _col)

    html_data[sheet_name] = sheet_data
    parsed["html_data"] = html_data
    wp.parsed_data = parsed
    flag_modified(wp, "parsed_data")


def format_cell_display_value(value: Decimal | Any) -> Any:
    """网格展示：会计空值习惯显示为数字或原样。"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value == 0:
            return 0
        return float(value) if value % 1 else int(value)
    return value


async def touch_wp_registry(project_id: uuid.UUID | str) -> None:
    """使项目 WP 域地址注册表缓存失效（汇入 canonical ACNR invalidate）。

    Req 10.1/10.2/10.3/10.4：改调 canonical `acnr.events.invalidate`（in-process
    直调，不 re-publish WORKPAPER_SAVED 事件，避免 handler 重复 fan-out）。canonical
    invalidate 的全链（L3 RuntimeIndex → L2 overlay → FormulaReverseIndex →
    legacy `address_registry.invalidate_async(domain="wp")`）是原直接调用的超集，
    确保 reverse_index 清理在该热路径也触发（修复死代码风险）。

    失败仅 warning，不 raise，不阻断主流程；TTL 120s 为最终兜底。
    """
    try:
        from app.services.acnr.events import invalidate as acnr_invalidate

        await acnr_invalidate(str(project_id), trigger="touch_wp_registry")
    except Exception as e:
        logger.warning(
            "touch_wp_registry 失败 project_id=%s: %s", project_id, e
        )


async def touch_after_parsed_data_commit(
    wp: WorkingPaper | None = None,
    *,
    project_id: uuid.UUID | str | None = None,
    source: str = "parsed_data",
) -> None:
    """parsed_data 写入并 commit 之后调用（统一 WP 域缓存失效）。"""
    pid = project_id if project_id is not None else (wp.project_id if wp else None)
    if pid is None:
        return
    try:
        await touch_wp_registry(pid)
    except Exception as e:
        logger.warning(
            "touch_wp_registry after %s project_id=%s: %s", source, pid, e
        )
