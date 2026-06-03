"""working_paper.parsed_data 变更后的地址注册表缓存失效钩子。

custom-workpaper-formula-binding 任务 4.3：统一在 commit 之后调用，
避免 invalidate 散落在各写 parsed_data 路径。

已接线：wp_formula / wp_html_save / wp_user_formulas / working_paper（解析+univer_save）/
wp_fine_rules / wp_procedure_status / wp_ai_confirm / 各专题计算路由（wp_g_* / wp_h_* / wp_i_* / wp_j_* / wp_k_* / wp_l_* / wp_m_* / wp_f2_*）/ wp_procedure_trim。
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.models.workpaper_models import WorkingPaper
from app.services.address_registry import address_registry

logger = logging.getLogger(__name__)


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
    """使项目 WP 域地址注册表缓存失效（L1 + L2）。

    失败仅 warning，不阻断主流程；TTL 120s 为最终兜底。
    """
    try:
        await address_registry.invalidate_async(str(project_id), domain="wp")
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
