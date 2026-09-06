"""M6 未分配利润 — 服务层（导入导出 + 分配结转 + 联动核对）

科目：4104利润分配-未分配利润（贷方/权益类）
核心公式链：期末未分配利润=期初+本年净利润-提取盈余公积-分配股利

Requirements: 6.6, 3.2, 4.5
"""

from __future__ import annotations

import io
import logging
from typing import Any

from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

import sqlalchemy as sa

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 常量：sheet配置
# ═══════════════════════════════════════════════════════════════════════════════

_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "M6-2": {
        "title": "M6-2 明细表",
        "headers": [
            "项目", "期初未分配利润", "本年净利润", "前期差错更正",
            "会计政策变更调整", "调整后期初", "可供分配利润",
            "提取法定盈余公积", "提取任意盈余公积", "提取盈余公积合计",
            "应付普通股股利", "应付优先股股利", "应付股利合计",
            "转作股本的普通股股利", "期末未分配利润",
            "未审数", "AJE调整", "RJE调整", "审定数",
        ],
    },
    "M6-1": {
        "title": "M6-1 审定表",
        "headers": [
            "项目", "期初余额", "贷方发生额", "借方发生额",
            "期末余额", "未审数", "AJE调整", "RJE调整",
            "审定数", "差异", "备注",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_num(v: Any) -> float:
    """安全解析数值，无效值返回0.0"""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


async def _get_wp_context(wp_id: str, db: AsyncSession) -> dict[str, Any]:
    """从 wp_id 取关联的 project_id 和 audit_year."""
    result = await db.execute(
        sa.text("""
            SELECT wp.project_id, p.audit_year
            FROM working_paper wp
            JOIN projects p ON p.id = wp.project_id
            WHERE wp.id = :wp_id
        """),
        {"wp_id": wp_id},
    )
    row = result.fetchone()
    if not row:
        raise ValueError(f"底稿不存在: {wp_id}")
    return {
        "project_id": row.project_id,
        "year": int(row.audit_year or 2025),
    }


def _create_sheet_with_headers(wb: Workbook, config: dict[str, Any]) -> None:
    """创建sheet并写入表头"""
    ws = wb.create_sheet(title=config["title"])
    ws.append(config["headers"])


async def _load_responses(wp_id: str, db: AsyncSession) -> dict[str, dict[str, Any]]:
    """加载M6底稿的checklist_responses数据"""
    result = await db.execute(
        sa.text("""
            SELECT item_id, value
            FROM checklist_responses
            WHERE wp_id = :wp_id
              AND item_id LIKE 'M6-%'
        """),
        {"wp_id": wp_id},
    )
    rows = result.fetchall()
    return {r.item_id: {"value": r.value} for r in rows}


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


async def export_template(
    wp_id: str,
    db: AsyncSession,
    *,
    sheet: str | None = None,
) -> io.BytesIO:
    """导出空白xlsx模板（M6-2明细表 + M6-1审定表）

    Requirements: 6.6
    """
    wb = Workbook()
    # 移除默认sheet
    if wb.active:
        wb.remove(wb.active)

    configs_to_export = _SHEET_CONFIGS
    if sheet and sheet in _SHEET_CONFIGS:
        configs_to_export = {sheet: _SHEET_CONFIGS[sheet]}

    for _key, config in configs_to_export.items():
        _create_sheet_with_headers(wb, config)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


async def export_data(
    wp_id: str,
    db: AsyncSession,
    *,
    sheet: str | None = None,
) -> io.BytesIO:
    """导出含当前数据的xlsx（M6-2明细表 + M6-1审定表）

    Requirements: 6.6
    """
    responses = await _load_responses(wp_id, db)

    wb = Workbook()
    if wb.active:
        wb.remove(wb.active)

    configs_to_export = _SHEET_CONFIGS
    if sheet and sheet in _SHEET_CONFIGS:
        configs_to_export = {sheet: _SHEET_CONFIGS[sheet]}

    for key, config in configs_to_export.items():
        ws = wb.create_sheet(title=config["title"])
        ws.append(config["headers"])

        # 填充数据行（从checklist_responses中提取）
        prefix = f"M6-{key.split('-')[1]}-" if "-" in key else "M6-"
        row_data: dict[int, list[Any]] = {}
        for item_id, resp in responses.items():
            if item_id.startswith(prefix):
                # 解析 item_id 格式: M6-{sheet}-row{n}-{field}
                parts = item_id.split("-")
                if len(parts) >= 4:
                    try:
                        row_idx = int(parts[2].replace("row", ""))
                        if row_idx not in row_data:
                            row_data[row_idx] = [""] * len(config["headers"])
                        # 尝试匹配字段到列
                        field = "-".join(parts[3:])
                        for col_idx, header in enumerate(config["headers"]):
                            if field == header:
                                row_data[row_idx][col_idx] = resp.get("value", "")
                                break
                    except (ValueError, IndexError):
                        pass

        # 按行号排序写入
        for _row_idx in sorted(row_data.keys()):
            ws.append(row_data[_row_idx])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


async def import_data(
    wp_id: str,
    content: bytes,
    db: AsyncSession,
    *,
    sheet: str | None = None,
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（仅M6-2明细表动态行）

    Requirements: 6.6
    """
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as e:
        raise ValueError(f"无法解析xlsx文件: {e}")

    target_sheet = sheet or "M6-2"
    config = _SHEET_CONFIGS.get(target_sheet)
    if not config:
        raise ValueError(f"不支持导入的sheet: {target_sheet}")

    # 查找目标sheet
    target_ws = None
    for ws_name in wb.sheetnames:
        if target_sheet in ws_name or config["title"] in ws_name:
            target_ws = wb[ws_name]
            break

    if target_ws is None:
        raise ValueError(f"xlsx中未找到sheet: {target_sheet} 或 {config['title']}")

    # 解析表头行
    headers = [cell.value for cell in target_ws[1]]
    if not headers or not any(headers):
        raise ValueError("xlsx第一行（表头）为空")

    imported_count = 0
    warnings: list[str] = []

    # 从第2行开始读取数据
    for row_idx, row in enumerate(target_ws.iter_rows(min_row=2, values_only=True), start=1):
        if not any(v is not None and str(v).strip() for v in row):
            continue  # 跳过空行

        for col_idx, value in enumerate(row):
            if col_idx >= len(headers) or value is None:
                continue
            header = headers[col_idx]
            if not header:
                continue

            item_id = f"M6-{target_sheet.split('-')[1]}-row{row_idx}-{header}"

            # UPSERT checklist_responses
            await db.execute(
                sa.text("""
                    INSERT INTO checklist_responses (wp_id, item_id, value)
                    VALUES (:wp_id, :item_id, :value)
                    ON CONFLICT (wp_id, item_id)
                    DO UPDATE SET value = EXCLUDED.value
                """),
                {"wp_id": wp_id, "item_id": item_id, "value": str(value)},
            )
            imported_count += 1

    return {"imported_count": imported_count, "warnings": warnings}


# ═══════════════════════════════════════════════════════════════════════════════
# 利润分配结转汇总
# ═══════════════════════════════════════════════════════════════════════════════


async def get_distribution_summary(
    wp_id: str,
    db: AsyncSession,
    project_id: str,
) -> dict[str, Any]:
    """获取利润分配结转汇总（用于M5/M1联动核对）

    核心公式链：期末=期初+本年净利润-提取盈余公积-分配股利

    Requirements: 6.6, 3.2, 4.5
    """
    responses = await _load_responses(wp_id, db)

    # 从checklist_responses提取分配结转数据
    def _get_val(field: str) -> float:
        """从responses中查找包含field关键字的值"""
        for item_id, resp in responses.items():
            if field in item_id:
                return _parse_num(resp.get("value"))
        return 0.0

    begin = _get_val("opening_retained_earnings")
    net_profit = _get_val("net_income")
    prior_adjustment = _get_val("prior_adjustment")
    statutory_surplus = _get_val("statutory_surplus_reserve")
    discretionary_surplus = _get_val("discretionary_surplus_reserve")
    surplus_accrual = statutory_surplus + discretionary_surplus
    dividend = _get_val("dividend_distribution")

    # 如果checklist_responses没有数据，尝试从TB取
    if begin == 0.0 and net_profit == 0.0:
        tb_result = await db.execute(
            sa.text("""
                SELECT
                    COALESCE(tb.unadjusted_amount, 0) as unadj,
                    COALESCE(tb.aje_adjustment, 0) as aje,
                    COALESCE(tb.rje_adjustment, 0) as rje,
                    COALESCE(tb.audited_amount, 0) as audited
                FROM trial_balance tb
                WHERE tb.project_id = :project_id
                  AND tb.standard_account_code = '4104'
                LIMIT 1
            """),
            {"project_id": project_id},
        )
        tb_row = tb_result.fetchone()
        if tb_row:
            # 审定额作为参考
            begin = float(tb_row.unadj or 0)

    # 计算
    distributable = begin + net_profit + prior_adjustment
    retained_end = distributable - surplus_accrual - dividend

    # 公式链校验
    expected_end = begin + net_profit + prior_adjustment - surplus_accrual - dividend
    formula_diff = round(retained_end - expected_end, 2)
    formula_check = abs(formula_diff) < 1.0

    return {
        "begin": round(begin, 2),
        "net_profit": round(net_profit, 2),
        "distributable": round(distributable, 2),
        "surplus_accrual": round(surplus_accrual, 2),
        "dividend": round(dividend, 2),
        "retained_end": round(retained_end, 2),
        "prior_adjustment": round(prior_adjustment, 2),
        "formula_check": formula_check,
        "formula_diff": formula_diff,
    }
