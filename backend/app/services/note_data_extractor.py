"""附注表格数据提取引擎 — 支持三种表格样式 + 三种取数模式

═══ 三种附注表格样式 ═══
1. fixed_rows    — 固定行（如货币资金：库存现金/银行存款/其他/合计）
2. dynamic_rows  — 浮动可变行（如长期股权投资明细：被投资单位数量不固定）
3. mixed         — 固定+浮动（如固定资产变动表：行固定=原值/折旧，列浮动=资产分类）

═══ 三种取数模式 ═══
1. cell_fetch    — 固定单元格取数：NOTE_CELL(section, row_label, col_header)
2. column_fetch  — 列取数：NOTE_COL(section, col_header) → 返回该列所有行数据
3. row_fetch     — 行取数：NOTE_ROW(section, row_label) → 返回该行所有列数据

列取数和行取数支持浮动行的填充映射：
- 浮动行从底稿明细表/辅助余额表动态生成
- 映射规则：底稿明细行 → 附注浮动行（按名称匹配或按顺序填充）
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance, TbAuxBalance
from app.services.dataset_query import get_active_filter

_logger = logging.getLogger(__name__)


class TableStyle(str, Enum):
    """附注表格样式"""
    fixed_rows = "fixed_rows"       # 固定行
    dynamic_rows = "dynamic_rows"   # 浮动可变行
    mixed = "mixed"                 # 固定行+浮动列（或固定列+浮动行）


class FetchMode(str, Enum):
    """取数模式"""
    cell = "cell"       # 固定单元格
    column = "column"   # 整列取数
    row = "row"         # 整行取数


# ═══ 表格样式识别规则 ═══

# 固定行科目（行数确定，不随企业变化）
_FIXED_ROW_SECTIONS = {
    "五、1": TableStyle.fixed_rows,    # 货币资金（库存现金/银行存款/其他）
    "五、4": TableStyle.fixed_rows,    # 预付款项
    "五、16": TableStyle.fixed_rows,   # 短期借款
    "五、20": TableStyle.fixed_rows,   # 应交税费
    "五、24": TableStyle.fixed_rows,   # 实收资本
    "五、25": TableStyle.fixed_rows,   # 资本公积
    "五、27": TableStyle.fixed_rows,   # 盈余公积
    "五、28": TableStyle.fixed_rows,   # 未分配利润
    "五、30": TableStyle.fixed_rows,   # 税金及附加
}

# 浮动行科目（明细行数随企业变化）
_DYNAMIC_ROW_SECTIONS = {
    "五、7": TableStyle.dynamic_rows,   # 长期股权投资（被投资单位不固定）
    "五、3": TableStyle.dynamic_rows,   # 应收账款（按客户/账龄明细）
    "五、5": TableStyle.dynamic_rows,   # 其他应收款（按往来单位明细）
    "五、6": TableStyle.dynamic_rows,   # 存货（明细分类可变）
    "五、17": TableStyle.dynamic_rows,  # 应付账款（按供应商明细）
    "五、21": TableStyle.dynamic_rows,  # 其他应付款（按往来单位明细）
}

# 固定+浮动（变动表：行固定=原值/折旧/减值，列浮动=资产分类）
_MIXED_SECTIONS = {
    "五、9": TableStyle.mixed,    # 固定资产（行=原值期初/增加/减少/期末/折旧/减值，列=分类）
    "五、10": TableStyle.mixed,   # 在建工程（行=期初/增加/转固/期末，列=项目名）
    "五、12": TableStyle.mixed,   # 无形资产（行=原值/摊销/减值，列=分类）
    "五、14": TableStyle.mixed,   # 长期待摊费用（行=期初/增加/摊销/期末，列=项目）
}


def identify_table_style(note_section: str) -> TableStyle:
    """识别附注章节的表格样式"""
    if note_section in _FIXED_ROW_SECTIONS:
        return _FIXED_ROW_SECTIONS[note_section]
    if note_section in _DYNAMIC_ROW_SECTIONS:
        return _DYNAMIC_ROW_SECTIONS[note_section]
    if note_section in _MIXED_SECTIONS:
        return _MIXED_SECTIONS[note_section]
    # 默认固定行
    return TableStyle.fixed_rows


# ═══ 取数公式执行 ═══

async def note_cell_fetch(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    note_section: str,
    row_label: str,
    col_header: str,
) -> Decimal | None:
    """固定单元格取数：NOTE_CELL(section, row_label, col_header)

    适用于固定行表格，精确定位到某行某列的值。
    数据来源：trial_balance 按科目汇总。
    """
    from app.services.wp_data_rules import get_mapping_for_note

    mapping = get_mapping_for_note(note_section)
    if not mapping:
        return None

    account_codes = mapping.get("account_codes", [])
    if not account_codes:
        return None

    # 确定取哪个字段
    field = _resolve_column_field(col_header)
    if not field:
        return None

    # 如果 row_label 是"合计"，汇总所有科目
    if row_label in ("合计", "小计", "总计"):
        return await _sum_accounts(db, project_id, year, account_codes, field)

    # 否则尝试匹配子科目
    sub_code = _match_sub_account(row_label, account_codes)
    if sub_code:
        return await _get_account_value(db, project_id, year, sub_code, field)

    # 兜底：返回第一个科目的值
    if account_codes:
        return await _get_account_value(db, project_id, year, account_codes[0], field)

    return None


async def note_column_fetch(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    note_section: str,
    col_header: str,
) -> list[dict[str, Any]]:
    """整列取数：NOTE_COL(section, col_header) → 返回该列所有行数据

    支持浮动行：从辅助余额表/底稿明细动态生成行。
    """
    from app.services.wp_data_rules import get_mapping_for_note

    mapping = get_mapping_for_note(note_section)
    if not mapping:
        return []

    account_codes = mapping.get("account_codes", [])
    field = _resolve_column_field(col_header)
    if not field:
        return []

    style = identify_table_style(note_section)

    if style == TableStyle.dynamic_rows:
        # 浮动行：从辅助余额表获取明细
        return await _fetch_dynamic_column(db, project_id, year, account_codes, field)
    else:
        # 固定行：从 trial_balance 逐科目取值
        rows = []
        for code in account_codes:
            val = await _get_account_value(db, project_id, year, code, field)
            tb_row = await _get_tb_row(db, project_id, year, code)
            rows.append({
                "account_code": code,
                "account_name": tb_row.account_name if tb_row else code,
                "value": str(val) if val is not None else "0",
            })
        # 追加合计行
        total = await _sum_accounts(db, project_id, year, account_codes, field)
        rows.append({
            "account_code": "_total",
            "account_name": "合计",
            "value": str(total),
            "is_total": True,
        })
        return rows


async def note_row_fetch(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    note_section: str,
    row_label: str,
) -> dict[str, Any]:
    """整行取数：NOTE_ROW(section, row_label) → 返回该行所有列数据

    适用于变动表（mixed样式）：一行包含多个期间/分类的数据。
    """
    from app.services.wp_data_rules import get_mapping_for_note

    mapping = get_mapping_for_note(note_section)
    if not mapping:
        return {"row_label": row_label, "columns": {}}

    account_codes = mapping.get("account_codes", [])
    style = identify_table_style(note_section)

    if style == TableStyle.mixed:
        # 变动表：行标签决定取哪个字段
        field = _resolve_movement_row_field(row_label)
        if not field:
            return {"row_label": row_label, "columns": {}, "error": "未识别的行标签"}

        # 列=各资产分类，从辅助余额表按维度获取
        return await _fetch_mixed_row(db, project_id, year, account_codes, row_label, field)
    else:
        # 固定行：返回所有标准列
        columns = {}
        for col_name in ["期末余额", "期初余额"]:
            field = _resolve_column_field(col_name)
            if field and row_label in ("合计", "小计"):
                val = await _sum_accounts(db, project_id, year, account_codes, field)
                columns[col_name] = str(val)
        return {"row_label": row_label, "columns": columns}


# ═══ 浮动行填充映射 ═══

async def generate_dynamic_rows(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    note_section: str,
    top_n: int = 20,
    min_amount: float = 0,
) -> list[dict[str, Any]]:
    """为浮动行表格生成动态行数据

    数据来源优先级：
    1. 辅助余额表（tb_aux_balance）按维度分组
    2. 底稿 parsed_data 中的明细行
    3. 模板预设行（兜底）

    参数：
    - top_n: 最多显示行数（默认20），超出合并为"其他"
    - min_amount: 最小金额阈值（默认0），低于此值合并为"其他"

    返回格式：[{label, 期末余额, 期初余额, source}, ...]
    """
    from app.services.wp_data_rules import get_mapping_for_note

    mapping = get_mapping_for_note(note_section)
    if not mapping:
        return []

    account_codes = mapping.get("account_codes", [])
    if not account_codes:
        return []

    # 从辅助余额表获取明细
    result = await db.execute(
        sa.select(TbAuxBalance).where(
            await get_active_filter(db, TbAuxBalance.__table__, project_id, year),
            TbAuxBalance.account_code.in_(account_codes),
        ).order_by(TbAuxBalance.aux_code)
    )
    aux_rows = result.scalars().all()

    if aux_rows:
        # 按辅助名称分组汇总
        grouped: dict[str, dict] = {}
        for row in aux_rows:
            key = row.aux_name or row.aux_code or "未分类"
            if key not in grouped:
                grouped[key] = {"label": key, "closing": Decimal("0"), "opening": Decimal("0"), "source": "aux_balance"}
            if row.closing_balance:
                grouped[key]["closing"] += Decimal(str(row.closing_balance))
            if row.opening_balance:
                grouped[key]["opening"] += Decimal(str(row.opening_balance))

        # 按期末余额绝对值排序
        sorted_items = sorted(
            grouped.values(),
            key=lambda x: abs(x["closing"]),
            reverse=True,
        )

        # 应用阈值过滤 + Top N 限制
        rows = []
        other_closing = Decimal("0")
        other_opening = Decimal("0")
        other_count = 0
        total_closing = Decimal("0")
        total_opening = Decimal("0")

        for i, item in enumerate(sorted_items):
            total_closing += item["closing"]
            total_opening += item["opening"]

            if i < top_n and abs(float(item["closing"])) >= min_amount:
                rows.append({
                    "label": item["label"],
                    "期末余额": str(item["closing"]),
                    "期初余额": str(item["opening"]),
                    "source": "aux_balance",
                })
            else:
                other_closing += item["closing"]
                other_opening += item["opening"]
                other_count += 1

        # 追加"其他"合并行
        if other_count > 0:
            rows.append({
                "label": f"其他（{other_count}项）",
                "期末余额": str(other_closing),
                "期初余额": str(other_opening),
                "source": "aggregated",
                "is_other": True,
            })

        # 追加合计行
        rows.append({
            "label": "合计",
            "期末余额": str(total_closing),
            "期初余额": str(total_opening),
            "is_total": True,
            "source": "calculated",
        })
        return rows

    # 兜底：从 trial_balance 生成单行
    total_closing = Decimal("0")
    total_opening = Decimal("0")
    for code in account_codes:
        val = await _get_account_value(db, project_id, year, code, "audited_amount")
        if val:
            total_closing += val
        opening = await _get_account_value(db, project_id, year, code, "opening_balance")
        if opening:
            total_opening += opening

    return [{
        "label": mapping.get("account_name", "合计"),
        "期末余额": str(total_closing),
        "期初余额": str(total_opening),
        "source": "trial_balance",
        "is_total": True,
    }]


# ═══ 内部辅助函数 ═══

# 列名 → trial_balance 字段映射
_COL_FIELD_MAP = {
    "期末余额": "audited_amount",
    "期末数": "audited_amount",
    "期末审定": "audited_amount",
    "期初余额": "opening_balance",
    "期初数": "opening_balance",
    "年初余额": "opening_balance",
    "本期增加": "_period_increase",
    "本期减少": "_period_decrease",
    "本期计提": "_period_provision",
    "未审数": "unadjusted_amount",
    "调整数": "_adjustment_total",
}

# 变动表行标签 → 字段映射
_MOVEMENT_ROW_MAP = {
    "原值期初": "opening_balance",
    "期初余额": "opening_balance",
    "期初": "opening_balance",
    "本期增加": "_period_increase",
    "增加": "_period_increase",
    "本期减少": "_period_decrease",
    "减少": "_period_decrease",
    "原值期末": "audited_amount",
    "期末余额": "audited_amount",
    "期末": "audited_amount",
    "累计折旧期初": "_depreciation_opening",
    "本期计提": "_period_provision",
    "累计折旧期末": "_depreciation_closing",
    "账面价值期末": "_book_value_closing",
    "账面价值期初": "_book_value_opening",
}

# 子科目名称 → 科目编码前缀映射
_SUB_ACCOUNT_HINTS = {
    "库存现金": "1001",
    "银行存款": "1002",
    "其他货币资金": "1012",
    "原材料": "1401",
    "在产品": "1402",
    "库存商品": "1405",
}


def _resolve_column_field(col_header: str) -> str | None:
    """列名解析为 trial_balance 字段"""
    col = col_header.strip()
    return _COL_FIELD_MAP.get(col)


def _resolve_movement_row_field(row_label: str) -> str | None:
    """变动表行标签解析为字段"""
    label = row_label.strip()
    return _MOVEMENT_ROW_MAP.get(label)


def _match_sub_account(row_label: str, account_codes: list[str]) -> str | None:
    """根据行标签匹配子科目编码"""
    hint = _SUB_ACCOUNT_HINTS.get(row_label.strip())
    if hint and hint in account_codes:
        return hint
    return None


async def _get_account_value(
    db: AsyncSession, project_id: UUID, year: int,
    account_code: str, field: str,
) -> Decimal | None:
    """获取单个科目的指定字段值"""
    if field.startswith("_"):
        # 衍生字段需要特殊计算
        return await _calc_derived_field(db, project_id, year, account_code, field)

    result = await db.execute(
        sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.standard_account_code == account_code,
            TrialBalance.is_deleted == sa.false(),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return getattr(row, field, None)


async def _get_tb_row(
    db: AsyncSession, project_id: UUID, year: int, account_code: str,
):
    """获取试算表行"""
    result = await db.execute(
        sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.standard_account_code == account_code,
            TrialBalance.is_deleted == sa.false(),
        )
    )
    return result.scalar_one_or_none()


async def _sum_accounts(
    db: AsyncSession, project_id: UUID, year: int,
    account_codes: list[str], field: str,
) -> Decimal:
    """汇总多个科目的指定字段"""
    total = Decimal("0")
    for code in account_codes:
        val = await _get_account_value(db, project_id, year, code, field)
        if val is not None:
            total += val
    return total


async def _calc_derived_field(
    db: AsyncSession, project_id: UUID, year: int,
    account_code: str, field: str,
) -> Decimal | None:
    """计算衍生字段

    变动表的"本期增加/减少"从序时账(tb_ledger)按借贷方向汇总，
    而非简单的余额差推算（余额差不准确，如固定资产有多笔增减）。
    """
    if field == "_adjustment_total":
        aje = await _get_account_value(db, project_id, year, account_code, "aje_adjustment")
        rje = await _get_account_value(db, project_id, year, account_code, "rje_adjustment")
        return (aje or Decimal("0")) + (rje or Decimal("0"))

    if field == "_period_increase":
        # 本期增加 = 序时账借方发生额合计（资产类科目借方增加）
        from app.models.audit_platform_models import TbLedger
        result = await db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(TbLedger.debit_amount), 0)).where(
                await get_active_filter(db, TbLedger.__table__, project_id, year),
                TbLedger.account_code == account_code,
            )
        )
        val = result.scalar()
        return Decimal(str(val)) if val else Decimal("0")

    if field == "_period_decrease":
        # 本期减少 = 序时账贷方发生额合计（资产类科目贷方减少）
        from app.models.audit_platform_models import TbLedger
        result = await db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(TbLedger.credit_amount), 0)).where(
                await get_active_filter(db, TbLedger.__table__, project_id, year),
                TbLedger.account_code == account_code,
            )
        )
        val = result.scalar()
        return Decimal(str(val)) if val else Decimal("0")

    if field == "_period_provision":
        # 本期计提（折旧/摊销）= 贷方发生额（累计折旧科目贷方增加）
        from app.models.audit_platform_models import TbLedger
        result = await db.execute(
            sa.select(sa.func.coalesce(sa.func.sum(TbLedger.credit_amount), 0)).where(
                await get_active_filter(db, TbLedger.__table__, project_id, year),
                TbLedger.account_code == account_code,
            )
        )
        val = result.scalar()
        return Decimal(str(val)) if val else Decimal("0")

    if field == "_book_value_closing":
        return await _get_account_value(db, project_id, year, account_code, "audited_amount")

    if field == "_book_value_opening":
        return await _get_account_value(db, project_id, year, account_code, "opening_balance")

    if field == "_depreciation_opening":
        # 累计折旧期初 = 上年累计折旧审定数
        return await _get_account_value(db, project_id, year - 1, account_code, "audited_amount")

    if field == "_depreciation_closing":
        # 累计折旧期末 = 当年审定数
        return await _get_account_value(db, project_id, year, account_code, "audited_amount")

    return None


async def _fetch_dynamic_column(
    db: AsyncSession, project_id: UUID, year: int,
    account_codes: list[str], field: str,
) -> list[dict[str, Any]]:
    """浮动行列取数：从辅助余额表按维度获取"""
    result = await db.execute(
        sa.select(TbAuxBalance).where(
            await get_active_filter(db, TbAuxBalance.__table__, project_id, year),
            TbAuxBalance.account_code.in_(account_codes),
        ).order_by(TbAuxBalance.aux_name)
    )
    aux_rows = result.scalars().all()

    rows = []
    for row in aux_rows:
        val = getattr(row, field, None) if not field.startswith("_") else (
            row.closing_balance if "期末" in field or "audited" in field
            else row.opening_balance
        )
        rows.append({
            "account_code": row.account_code,
            "aux_code": row.aux_code,
            "aux_name": row.aux_name or row.aux_code or "",
            "value": str(val) if val is not None else "0",
        })
    return rows


async def _fetch_mixed_row(
    db: AsyncSession, project_id: UUID, year: int,
    account_codes: list[str], row_label: str, field: str,
) -> dict[str, Any]:
    """变动表行取数：按资产分类（辅助维度）获取一行多列数据"""
    result = await db.execute(
        sa.select(TbAuxBalance).where(
            await get_active_filter(db, TbAuxBalance.__table__, project_id, year),
            TbAuxBalance.account_code.in_(account_codes),
        ).order_by(TbAuxBalance.aux_name)
    )
    aux_rows = result.scalars().all()

    columns = {}
    total = Decimal("0")
    for row in aux_rows:
        col_name = row.aux_name or row.aux_code or "其他"
        val = getattr(row, field, None) if not field.startswith("_") else (
            row.closing_balance if "closing" in field or "期末" in field or "audited" in field
            else row.opening_balance
        )
        val = val or Decimal("0")
        columns[col_name] = str(val)
        total += val

    columns["合计"] = str(total)

    return {
        "row_label": row_label,
        "columns": columns,
        "source": "aux_balance" if aux_rows else "empty",
    }
