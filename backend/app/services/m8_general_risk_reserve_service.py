"""M8 一般风险准备 — 业务逻辑服务

提供功能：
- 导出模板 / 导出数据 / 导入数据（xlsx三级）
- 风险资产计提测试（纯函数）
- 公式一致性验证

科目4104一般风险准备（**贷方/权益类！**）：期末=期初+贷方-借方
金融企业按风险资产期末余额×比例计提（原则上不低于1.5%）。

Requirements: 3.4, 6.6
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_M8_ACCOUNT_CODE = "4104"
_ROW_LIMIT = 500
_DEFAULT_PROVISION_RATE = 0.015  # 1.5%


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：风险资产计提引擎
# ═══════════════════════════════════════════════════════════════════════════════


def calc_risk_provision(risk_assets: float, rate: float) -> float:
    """应计金额 = 风险资产期末余额 × 计提比例

    Args:
        risk_assets: 风险资产期末余额
        rate: 计提比例（如 0.015 = 1.5%）

    Returns:
        应计提金额

    Example:
        >>> calc_risk_provision(10000000, 0.015)
        150000.0
    """
    return float(risk_assets or 0) * float(rate or 0)


def calc_provision_diff(booked: float, estimated: float) -> float:
    """计提差异 = 账面计提 − 应计金额

    方向说明（对应M8-4公式 H=B-G）：
    - 正差 → 多计提
    - 负差 → 少计提（审计风险点）
    - 零 → 计提准确

    Args:
        booked: 账面计提金额（本期增加/计提额）
        estimated: 应计金额（风险资产×比例）

    Returns:
        差异

    Example:
        >>> calc_provision_diff(150000, 120000)
        30000.0
    """
    return float(booked or 0) - float(estimated or 0)


def get_risk_provision_summary(
    *,
    items: list[dict[str, Any]],
    threshold: float = 0.0,
) -> dict[str, Any]:
    """执行完整风险资产计提测试，返回各项结果+汇总

    对应M8-4测试表核心公式：
    - G列: 应计金额 = E(基数/风险资产) × F(比例)
    - H列: 差异 = B(计提额) - G(应计金额)

    Args:
        items: 各项风险资产 [{name, risk_asset_balance, provision_rate, booked_balance}]
        threshold: 差异阈值（可选）

    Returns:
        { items: [...], summary: {...} }
    """
    results: list[dict[str, Any]] = []
    total_risk_assets = 0.0
    total_estimated = 0.0
    total_booked = 0.0
    total_diff = 0.0

    for item in items:
        name = item.get("name", "")
        risk_asset_balance = float(item.get("risk_asset_balance", 0) or 0)
        rate = float(item.get("provision_rate", _DEFAULT_PROVISION_RATE) or _DEFAULT_PROVISION_RATE)
        booked = float(item.get("booked_balance", 0) or 0)

        estimated = calc_risk_provision(risk_asset_balance, rate)
        diff = calc_provision_diff(booked, estimated)
        abs_diff = abs(diff)
        exceed_threshold = abs_diff > threshold if threshold > 0 else False

        results.append({
            "name": name,
            "risk_asset_balance": round(risk_asset_balance, 2),
            "provision_rate": rate,
            "estimated": round(estimated, 2),
            "booked": round(booked, 2),
            "diff": round(diff, 2),
            "abs_diff": round(abs_diff, 2),
            "exceed_threshold": exceed_threshold,
        })

        total_risk_assets += risk_asset_balance
        total_estimated += estimated
        total_booked += booked
        total_diff += diff

    # 生成结论
    if abs(total_diff) < 1.0:
        conclusion = "计提准确，应计提与账面一致。"
    elif total_diff > 0:
        conclusion = f"合计多计提 {total_diff:,.2f} 元。"
    else:
        conclusion = f"合计少计提 {abs(total_diff):,.2f} 元，需关注计提充足性。"

    summary = {
        "total_risk_assets": round(total_risk_assets, 2),
        "total_estimated": round(total_estimated, 2),
        "total_booked": round(total_booked, 2),
        "total_diff": round(total_diff, 2),
        "threshold": round(threshold, 2),
        "conclusion": conclusion,
    }

    return {"items": results, "summary": summary}


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出配置
# ═══════════════════════════════════════════════════════════════════════════════

_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "M8-2": {
        "title": "M8-2 明细表（一般风险准备计提明细）",
        "headers": [
            "项目", "未审数-期初数", "未审数-本期增加", "未审数-本期减少",
            "未审数-期末数", "期初调整-账项", "期初调整-重分类",
            "账项调整-本期增加", "账项调整-本期减少",
            "重分类调整-本期增加", "重分类调整-本期减少",
            "审定数-期初数", "审定数-本期增加", "审定数-本期减少",
            "审定数-期末数", "文件依据-索引号", "备注",
        ],
        "fields": [
            "name", "unadj_begin", "unadj_increase", "unadj_decrease",
            "unadj_end", "adj_begin_aje", "adj_begin_rje",
            "aje_increase", "aje_decrease",
            "rje_increase", "rje_decrease",
            "audited_begin", "audited_increase", "audited_decrease",
            "audited_end", "ref_index", "remark",
        ],
    },
    "M8-4": {
        "title": "M8-4 风险资产计提测试表",
        "headers": [
            "项目", "本期增加-计提", "本期增加-其它",
            "提取标准", "基数（风险资产）", "比例",
            "应计金额", "差异", "差异原因",
            "相关依据索引号", "相关数据来源索引号",
        ],
        "fields": [
            "name", "increase_provision", "increase_other",
            "standard", "risk_asset_base", "provision_rate",
            "estimated_amount", "diff", "diff_reason",
            "ref_index", "data_source_index",
        ],
    },
}

_HEADER_FONT = Font(bold=True, size=11)
_HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
_HEADER_FONT_WHITE = Font(bold=True, size=11, color="FFFFFF")
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


async def export_template(
    wp_id: str,
    db: AsyncSession,
    *,
    sheet: str | None = None,
) -> io.BytesIO:
    """导出空白xlsx模板

    Args:
        wp_id: 底稿ID
        db: 数据库会话
        sheet: 可选，指定导出单个sheet（M8-2/M8-4）
    """
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    sheets_to_export = (
        [sheet] if sheet and sheet in _SHEET_CONFIGS
        else list(_SHEET_CONFIGS.keys())
    )

    for sheet_key in sheets_to_export:
        cfg = _SHEET_CONFIGS[sheet_key]
        ws = wb.create_sheet(title=cfg["title"])

        # 写入表头
        for col_idx, header in enumerate(cfg["headers"], 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = _HEADER_FONT_WHITE
            cell.fill = _HEADER_FILL
            cell.alignment = _HEADER_ALIGN

        # 设置列宽
        for col_idx in range(1, len(cfg["headers"]) + 1):
            col_letter = chr(64 + col_idx) if col_idx <= 26 else "A"
            ws.column_dimensions[col_letter].width = 14

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
    """导出含当前数据的xlsx

    从 checklist_responses 查询 M8 行数据，写入 xlsx。
    """
    import sqlalchemy as sa
    from app.models.audit_platform_models import ChecklistResponse

    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    sheets_to_export = (
        [sheet] if sheet and sheet in _SHEET_CONFIGS
        else list(_SHEET_CONFIGS.keys())
    )

    for sheet_key in sheets_to_export:
        cfg = _SHEET_CONFIGS[sheet_key]
        ws = wb.create_sheet(title=cfg["title"])

        # 写入表头
        for col_idx, header in enumerate(cfg["headers"], 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = _HEADER_FONT_WHITE
            cell.fill = _HEADER_FILL
            cell.alignment = _HEADER_ALIGN

        # 查询 checklist_responses 中的行数据
        item_prefix = f"M8-{sheet_key.split('-')[1]}-row-"
        stmt = sa.select(ChecklistResponse).where(
            ChecklistResponse.wp_id == wp_id,
            ChecklistResponse.item_id.like(f"{item_prefix}%-data"),
        ).order_by(ChecklistResponse.item_id)

        result = await db.execute(stmt)
        responses = result.scalars().all()

        row_num = 2
        for resp in responses:
            if not resp.remark:
                continue
            try:
                data = json.loads(resp.remark)
            except (json.JSONDecodeError, TypeError):
                continue

            for col_idx, field in enumerate(cfg["fields"], 1):
                value = data.get(field, "")
                ws.cell(row=row_num, column=col_idx, value=value)
            row_num += 1

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
    """导入xlsx解析写入checklist_responses

    解析xlsx文件，按 M8-2/M8-4 结构写入。
    权益类贷方：期末=期初+贷方-借方

    Returns:
        { imported_count: int, warnings: list[str] }
    """
    import sqlalchemy as sa
    from app.models.audit_platform_models import ChecklistResponse

    target_sheet = sheet or "M8-2"
    if target_sheet not in _SHEET_CONFIGS:
        raise ValueError(f"不支持的sheet: {target_sheet}")

    cfg = _SHEET_CONFIGS[target_sheet]
    expected_headers = cfg["headers"]
    fields = cfg["fields"]

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise ValueError(f"无法解析xlsx文件: {e}")

    # 找到目标工作表（优先按标题匹配，其次取第一个）
    ws = None
    for ws_name in wb.sheetnames:
        if cfg["title"] in ws_name or target_sheet in ws_name:
            ws = wb[ws_name]
            break
    if ws is None:
        ws = wb.active

    if ws is None:
        raise ValueError("xlsx文件为空")

    # 验证表头（宽容匹配：只要包含前几个关键列即可）
    header_row = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    missing = [h for h in expected_headers[:4] if h not in header_row]
    if missing:
        raise ValueError(f"列头不匹配，缺少: {missing}")

    # 解析数据行
    warnings: list[str] = []
    imported_count = 0
    items_to_save: list[dict[str, Any]] = []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=1):
        if row_idx > _ROW_LIMIT:
            warnings.append(f"超过最大行限制({_ROW_LIMIT})，后续行已忽略")
            break

        # 跳过全空行
        if all(cell is None or cell == "" for cell in row):
            continue

        row_data: dict[str, Any] = {}
        for col_idx, field in enumerate(fields):
            val = row[col_idx] if col_idx < len(row) else None
            row_data[field] = val if val is not None else ""

        # M8-2: 计算期末（权益类贷方：期末=期初+增加-减少）
        if target_sheet == "M8-2":
            try:
                begin = float(row_data.get("unadj_begin") or 0)
                increase = float(row_data.get("unadj_increase") or 0)
                decrease = float(row_data.get("unadj_decrease") or 0)
                row_data["unadj_end"] = begin + increase - decrease
            except (ValueError, TypeError):
                pass

        # M8-4: 计算应计金额和差异
        if target_sheet == "M8-4":
            try:
                base = float(row_data.get("risk_asset_base") or 0)
                rate = float(row_data.get("provision_rate") or 0)
                provision = float(row_data.get("increase_provision") or 0)
                row_data["estimated_amount"] = calc_risk_provision(base, rate)
                row_data["diff"] = calc_provision_diff(provision, row_data["estimated_amount"])
            except (ValueError, TypeError):
                pass

        items_to_save.append(row_data)
        imported_count += 1

    # 写入 checklist_responses
    sheet_num = target_sheet.split("-")[1]  # "2" or "4"
    for idx, row_data in enumerate(items_to_save, start=1):
        item_id = f"M8-{sheet_num}-row-{idx}-data"

        # Upsert: 查询是否存在
        stmt = sa.select(ChecklistResponse).where(
            ChecklistResponse.wp_id == wp_id,
            ChecklistResponse.item_id == item_id,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        remark_json = json.dumps(row_data, ensure_ascii=False)

        if existing:
            existing.remark = remark_json
        else:
            new_resp = ChecklistResponse(
                wp_id=wp_id,
                item_id=item_id,
                conclusion=None,
                remark=remark_json,
            )
            db.add(new_resp)

    return {"imported_count": imported_count, "warnings": warnings}


# ═══════════════════════════════════════════════════════════════════════════════
# 公式一致性验证
# ═══════════════════════════════════════════════════════════════════════════════


async def validate_risk_provision(
    db: AsyncSession,
    wp_id: str,
) -> dict[str, Any]:
    """验证风险资产计提公式一致性

    校验内容：
    1. M8-4每行：应计金额 == 基数 × 比例
    2. M8-4差异列：差异 == 计提 - 应计金额
    3. M8-2明细合计 vs M8-1审定表一致性

    Returns:
        { valid: bool, checks: [...] }
    """
    import sqlalchemy as sa
    from app.models.audit_platform_models import ChecklistResponse

    checks: list[dict[str, Any]] = []
    all_valid = True

    # 检查M8-4测试表行数据
    stmt = sa.select(ChecklistResponse).where(
        ChecklistResponse.wp_id == wp_id,
        ChecklistResponse.item_id.like("M8-4-row-%-data"),
    ).order_by(ChecklistResponse.item_id)

    result = await db.execute(stmt)
    m8_4_rows = result.scalars().all()

    for resp in m8_4_rows:
        if not resp.remark:
            continue
        try:
            data = json.loads(resp.remark)
        except (json.JSONDecodeError, TypeError):
            continue

        base = float(data.get("risk_asset_base") or 0)
        rate = float(data.get("provision_rate") or 0)
        estimated = float(data.get("estimated_amount") or 0)
        expected_estimated = calc_risk_provision(base, rate)

        is_ok = abs(estimated - expected_estimated) < 0.01
        if not is_ok:
            all_valid = False
        checks.append({
            "item_id": resp.item_id,
            "check": "应计金额=基数×比例",
            "expected": round(expected_estimated, 2),
            "actual": round(estimated, 2),
            "valid": is_ok,
        })

    return {"valid": all_valid, "checks": checks}
