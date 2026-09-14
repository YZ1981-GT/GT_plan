"""M9 其他综合收益 — 业务逻辑服务

提供功能：
- OCI 税后净额计算（纯函数）
- 多来源核对差异计算
- OCI 汇总（不可重分类 + 可重分类）
- 权益类余额公式校验
- 导出模板 / 导出数据 / 导入数据（xlsx三级）

科目4103其他综合收益（**贷方/权益类！**）：期末=期初+贷方-借方
OCI按税后净额列示（税前发生-所得税影响=税后净额）。
OCI汇聚多来源：G8公允变动/J2重计量/其他债权投资/套期/外币折算。
分两大类：不能重分类进损益 + 能重分类进损益。

Requirements: 3.3, 4.5
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

_M9_ACCOUNT_CODE = "4103"
_ROW_LIMIT = 500


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：OCI 计算引擎
# ═══════════════════════════════════════════════════════════════════════════════


def calc_after_tax_net(pre_tax: float, tax_effect: float) -> float:
    """OCI 税后净额 = 税前发生 - 所得税影响

    方向说明：
    - pre_tax > 0 表示 OCI 本期增加（贷方）
    - tax_effect > 0 表示所得税影响（减少净额）
    - 结果为正 → 税后净额贷方增加

    Args:
        pre_tax: 本期税前发生额
        tax_effect: 所得税影响额

    Returns:
        税后净额

    Example:
        >>> calc_after_tax_net(1000, 250)
        750.0
    """
    return float(pre_tax or 0) - float(tax_effect or 0)


def calc_reconcile_diff(source: float, booked: float) -> float:
    """核对差异 = 来源金额 - 账面OCI增加

    方向说明：
    - 正差 → 来源大于账面（OCI可能漏记）
    - 负差 → 账面大于来源（OCI可能多记）
    - 零 → 核对一致

    来源包括：G8其他权益工具投资公允变动、J2设定受益计划重计量、
    其他债权投资公允变动、现金流量套期损益、外币折算差额等。

    Args:
        source: 来源底稿金额（税后）
        booked: 账面OCI增加额

    Returns:
        核对差异

    Example:
        >>> calc_reconcile_diff(500, 480)
        20.0
    """
    return float(source or 0) - float(booked or 0)


def aggregate_oci(items: list[dict[str, Any]]) -> dict[str, float]:
    """OCI 两大类汇总

    将各 OCI 项目按分类汇总：
    - non_reclass: 以后不能重分类进损益（G8公允变动、J2重计量）
    - reclass: 以后能重分类进损益（其他债权投资、套期、外币折算）
    - total: 两大类合计

    Args:
        items: OCI 项目列表，每项含 { category: "non_reclass"|"reclass", amount: float }

    Returns:
        { non_reclass: float, reclass: float, total: float }

    Example:
        >>> aggregate_oci([
        ...     {"category": "non_reclass", "amount": 100},
        ...     {"category": "reclass", "amount": 200},
        ...     {"category": "non_reclass", "amount": 50},
        ... ])
        {'non_reclass': 150.0, 'reclass': 200.0, 'total': 350.0}
    """
    non_reclass = 0.0
    reclass = 0.0
    for item in items:
        amount = float(item.get("amount", 0) or 0)
        category = item.get("category", "")
        if category == "non_reclass":
            non_reclass += amount
        elif category == "reclass":
            reclass += amount
    return {
        "non_reclass": non_reclass,
        "reclass": reclass,
        "total": non_reclass + reclass,
    }


def validate_equity_formula(
    begin: float, credit: float, debit: float, end_balance: float
) -> bool:
    """权益类公式校验：期末 = 期初 + 贷方 - 借方

    科目4103其他综合收益为权益类贷方科目：
    - OCI增加 → 贷方增加
    - OCI减少/重分类进损益 → 借方减少
    - 期末余额 = 期初余额 + 贷方发生额 - 借方发生额

    Args:
        begin: 期初余额
        credit: 贷方发生额（OCI增加）
        debit: 借方发生额（OCI减少/重分类）
        end_balance: 期末余额

    Returns:
        True 如果公式成立（容差0.01元）

    Example:
        >>> validate_equity_formula(1000, 300, 100, 1200)
        True
    """
    expected = float(begin or 0) + float(credit or 0) - float(debit or 0)
    return abs(float(end_balance or 0) - expected) <= 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 多来源核对综合执行
# ═══════════════════════════════════════════════════════════════════════════════


def run_oci_reconciliation(sources: list[dict[str, Any]], threshold: float = 0.0) -> dict[str, Any]:
    """执行完整 OCI 多来源核对

    对每个来源计算核对差异，并汇总判断是否全部一致。

    Args:
        sources: 各来源 [{ code, name, source_amount, booked_amount }, ...]
        threshold: 差异阈值（|diff|>threshold 视为重大差异）

    Returns:
        {
            "items": [{ code, name, source, booked, diff, abs_diff, exceed }...],
            "total_source": float,
            "total_booked": float,
            "total_diff": float,
            "all_consistent": bool,
            "inconsistent_count": int,
        }
    """
    items: list[dict[str, Any]] = []
    total_source = 0.0
    total_booked = 0.0
    inconsistent_count = 0

    for src in sources:
        source_amt = float(src.get("source_amount", 0) or 0)
        booked_amt = float(src.get("booked_amount", 0) or 0)
        diff = calc_reconcile_diff(source_amt, booked_amt)
        abs_diff = abs(diff)
        exceed = abs_diff > threshold if threshold > 0 else False

        if exceed:
            inconsistent_count += 1

        items.append({
            "code": src.get("code", ""),
            "name": src.get("name", ""),
            "source": round(source_amt, 2),
            "booked": round(booked_amt, 2),
            "diff": round(diff, 2),
            "abs_diff": round(abs_diff, 2),
            "exceed_threshold": exceed,
        })
        total_source += source_amt
        total_booked += booked_amt

    total_diff = total_source - total_booked

    return {
        "items": items,
        "total_source": round(total_source, 2),
        "total_booked": round(total_booked, 2),
        "total_diff": round(total_diff, 2),
        "all_consistent": inconsistent_count == 0,
        "inconsistent_count": inconsistent_count,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出配置
# ═══════════════════════════════════════════════════════════════════════════════

_SHEET_CONFIGS: dict[str, dict[str, Any]] = {
    "M9-2": {
        "title": "M9-2 明细表（OCI分项 税后净额）",
        "headers": [
            "分类", "OCI项目", "来源编码", "期初余额",
            "本期税前发生", "所得税影响", "本期税后净额", "期末余额", "备注",
        ],
        "fields": [
            "category", "itemName", "sourceCode", "beginning",
            "preTax", "taxEffect", "afterTaxNet", "endBalance", "remark",
        ],
    },
    "M9-4": {
        "title": "M9-4 OCI核对表（多来源核对）",
        "headers": [
            "来源编码", "来源底稿", "来源金额(税后)", "账面OCI增加", "差异", "备注",
        ],
        "fields": [
            "sourceCode", "sourceName", "sourceAmount", "bookedAmount", "diff", "remark",
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
    db: AsyncSession,
    wp_id: str,
    sheet: str | None = None,
) -> io.BytesIO:
    """导出空白xlsx模板

    Args:
        db: 数据库会话（保留接口一致性，此处未查询）
        wp_id: 底稿ID
        sheet: 可选，指定导出单个sheet（M9-2/M9-4）
    """
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    sheets_to_export = [sheet] if sheet and sheet in _SHEET_CONFIGS else list(_SHEET_CONFIGS.keys())

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
            ws.column_dimensions[col_letter].width = 18

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


async def export_data(
    db: AsyncSession,
    wp_id: str,
    sheet: str | None = None,
) -> io.BytesIO:
    """导出含当前数据的xlsx

    从 checklist_responses 查询 M9-2/M9-4 行数据，写入 xlsx。
    """
    from app.models.audit_platform_models import ChecklistResponse
    import sqlalchemy as sa

    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    sheets_to_export = [sheet] if sheet and sheet in _SHEET_CONFIGS else list(_SHEET_CONFIGS.keys())

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
        stmt = sa.select(ChecklistResponse).where(
            ChecklistResponse.wp_id == wp_id,
            ChecklistResponse.item_id.like(f"{sheet_key}-row-%-data"),
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
    db: AsyncSession,
    wp_id: str,
    sheet: str | None = None,
    file: bytes | None = None,
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses

    解析xlsx文件，按 M9-2 明细表 / M9-4 核对表结构写入。
    M9-2: 自动计算税后净额 = 税前 - 所得税影响
    M9-4: 自动计算核对差异 = 来源金额 - 账面OCI增加

    Args:
        db: 数据库会话（只flush不commit）
        wp_id: 底稿ID
        sheet: 目标sheet（M9-2/M9-4）
        file: xlsx文件内容bytes

    Returns:
        { imported_count: int, sheet: str, warnings: list[str] }
    """
    from app.models.audit_platform_models import ChecklistResponse
    import sqlalchemy as sa

    if file is None:
        raise ValueError("未提供文件内容")

    target_sheet = sheet or "M9-2"
    if target_sheet not in _SHEET_CONFIGS:
        raise ValueError(f"不支持的sheet: {target_sheet}，可选: {list(_SHEET_CONFIGS.keys())}")

    cfg = _SHEET_CONFIGS[target_sheet]
    expected_headers = cfg["headers"]
    fields = cfg["fields"]

    try:
        wb = load_workbook(io.BytesIO(file), read_only=True, data_only=True)
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
    key_headers = expected_headers[:4]
    missing = [h for h in key_headers if h not in header_row]
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

        # M9-2: 自动计算税后净额
        if target_sheet == "M9-2":
            try:
                pre_tax = float(row_data.get("preTax") or 0)
                tax_effect = float(row_data.get("taxEffect") or 0)
                row_data["afterTaxNet"] = calc_after_tax_net(pre_tax, tax_effect)
            except (ValueError, TypeError):
                pass

        # M9-4: 自动计算核对差异
        if target_sheet == "M9-4":
            try:
                source_amt = float(row_data.get("sourceAmount") or 0)
                booked_amt = float(row_data.get("bookedAmount") or 0)
                row_data["diff"] = calc_reconcile_diff(source_amt, booked_amt)
            except (ValueError, TypeError):
                pass

        items_to_save.append(row_data)
        imported_count += 1

    # 写入 checklist_responses（只flush不commit）
    for idx, row_data in enumerate(items_to_save, start=1):
        item_id = f"{target_sheet}-row-{idx}-data"

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

    await db.flush()

    return {
        "imported_count": imported_count,
        "sheet": target_sheet,
        "warnings": warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 数据库查询：OCI 汇总数据（跨底稿联动）
# ═══════════════════════════════════════════════════════════════════════════════


async def get_m9_summary(
    session: AsyncSession,
    project_id: str,
    wp_id: str,
) -> dict[str, Any]:
    """获取M9底稿汇总数据

    从TB取科目4103余额 + 从checklist_responses提取OCI分类合计。
    用于跨底稿联动核对（G8/J2/外币来源验证）。

    Args:
        session: 数据库会话
        project_id: 项目ID
        wp_id: M9底稿ID

    Returns:
        {
            "account_code": "4103",
            "tb_unadjusted": float,
            "tb_audited": float,
            "begin_balance": float,
            "credit_total": float,  # 贷方发生（OCI增加）
            "debit_total": float,   # 借方发生（OCI减少/重分类）
            "end_balance": float,   # 期末=期初+贷方-借方
            "non_reclass_total": float,  # 不可重分类合计
            "reclass_total": float,      # 可重分类合计
            "oci_total": float,          # OCI总额
            "reconciliation": {...} | None,  # 核对结果
            "ready": bool,
        }
    """
    import sqlalchemy as sa
    from app.models.audit_platform_models import ChecklistResponse

    # Step 1: 从TB取科目4103余额
    tb_unadjusted = 0.0
    tb_audited = 0.0
    try:
        tb_result = await session.execute(
            sa.text("""
                SELECT
                    COALESCE(tb.unadjusted_amount, 0) as unadj,
                    COALESCE(tb.aje_adjustment, 0) as aje,
                    COALESCE(tb.rje_adjustment, 0) as rje,
                    COALESCE(tb.audited_amount, 0) as audited
                FROM trial_balance tb
                WHERE tb.project_id = :project_id
                  AND tb.standard_account_code = :account_code
                LIMIT 1
            """),
            {"project_id": project_id, "account_code": _M9_ACCOUNT_CODE},
        )
        tb_row = tb_result.fetchone()
        if tb_row:
            tb_unadjusted = float(tb_row.unadj or 0)
            tb_audited = float(tb_row.audited or 0)
    except Exception as e:
        logger.warning("M9 TB查询失败: %s", e)

    # Step 2: 从checklist_responses提取审定表/明细表汇总数据
    begin_balance = 0.0
    credit_total = 0.0
    debit_total = 0.0
    non_reclass_total = 0.0
    reclass_total = 0.0

    try:
        stmt = sa.select(ChecklistResponse).where(
            ChecklistResponse.wp_id == wp_id,
            ChecklistResponse.item_id.like("M9-%"),
        )
        result = await session.execute(stmt)
        responses = result.scalars().all()

        for resp in responses:
            if not resp.remark:
                continue
            try:
                data = json.loads(resp.remark)
            except (json.JSONDecodeError, TypeError):
                continue

            item_id = resp.item_id

            # 审定表M9-1的汇总行
            if item_id.startswith("M9-1-"):
                if "begin" in item_id or "opening" in item_id:
                    begin_balance += float(data.get("value", 0) or 0)
                elif "credit" in item_id:
                    credit_total += float(data.get("value", 0) or 0)
                elif "debit" in item_id:
                    debit_total += float(data.get("value", 0) or 0)

            # 明细表M9-2的分类合计
            if item_id.startswith("M9-2-row-") and item_id.endswith("-data"):
                category = data.get("category", "")
                after_tax = float(data.get("afterTaxNet", 0) or 0)
                if category == "non_reclass":
                    non_reclass_total += after_tax
                elif category == "reclass":
                    reclass_total += after_tax
    except Exception as e:
        logger.warning("M9 checklist_responses查询失败: %s", e)

    # 权益类期末 = 期初 + 贷方 - 借方
    end_balance = begin_balance + credit_total - debit_total
    oci_total = non_reclass_total + reclass_total

    return {
        "account_code": _M9_ACCOUNT_CODE,
        "tb_unadjusted": round(tb_unadjusted, 2),
        "tb_audited": round(tb_audited, 2),
        "begin_balance": round(begin_balance, 2),
        "credit_total": round(credit_total, 2),
        "debit_total": round(debit_total, 2),
        "end_balance": round(end_balance, 2),
        "non_reclass_total": round(non_reclass_total, 2),
        "reclass_total": round(reclass_total, 2),
        "oci_total": round(oci_total, 2),
        "reconciliation": None,
        "ready": tb_audited != 0.0 or begin_balance != 0.0,
    }
