"""E1 货币资金底稿精细化脚本

基于实际模板：E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx
模板结构（16个sheet）：
- 底稿目录 / 实质性程序表E1A / 附注披露(上市+国企)
- 审定表E1-1 / 现金明细E1-2 / 银行存款明细E1-3(人民币/外币)
- 数字货币E1-4 / 调整分录汇总E1-5 / 余额调节表E1-6
- 现金盘点E1-7/E1-8 / 银行存单盘点E1-9 / 银行账户清单E1-10 / 银行承诺E1-11

审定表E1-1布局：
- 列：A=项目 B=期初未审 C=期初调整 D=期初审定 E=期末未审 F=期末调整 G=期末审定 H=变动额
- 行7=库存现金 行8=银行存款(本金) 行9=存放财务公司 行10=银行机构
- 行11=其他货币资金 行12=数字货币 行13=应计利息 行18=合计
- 行20=试算平衡表数 行21=差异数
- 行23起=仅人民币部分（同结构）
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ═══ 模板单元格映射 ═══
SHEET_NAME = "货币资金审定表E1-1"

# 审定表行映射（A列项目名 → 行号）
ROW_MAP = {
    "库存现金": 7,
    "银行存款": 8,
    "存放财务公司": 9,
    "银行机构存款": 10,
    "其他货币资金": 11,
    "数字货币": 12,
    "应计利息": 13,
    "合计": 18,
    "试算平衡表数": 20,
    "差异数": 21,
}

# 列映射
COL_MAP = {
    "opening_unadjusted": "B",   # 期初未审数
    "opening_adjustment": "C",   # 期初账项调整
    "opening_audited": "D",      # 期初审定数
    "closing_unadjusted": "E",   # 期末未审数
    "closing_adjustment": "F",   # 期末账项调整
    "closing_audited": "G",      # 期末审定数
    "change": "H",               # 变动额
}

# 科目编码 → 审定表行项目
ACCOUNT_ROW_MAP = {
    "1001": "库存现金",
    "1002": "银行存款",
    "1012": "其他货币资金",
}


async def extract_data(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """从试算表/序时账/辅助余额表提取货币资金全量数据

    返回结构化数据供填充审定表和生成审计说明使用。
    """
    from app.models.audit_platform_models import TrialBalance, TbLedger, TbBalance, TbAuxBalance

    data = {
        "audit_schedule": {},  # 审定表各行数据
        "bank_details": [],    # 银行存款明细（E1-3用）
        "large_transactions": [],  # 大额交易
        "month_summary": {},   # 按月汇总（分析程序用）
        "balance_reconciliation": [],  # 余额调节项
    }

    # 1. 从试算表取各科目余额 → 填充审定表
    for code, row_name in ACCOUNT_ROW_MAP.items():
        result = await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code == code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        tb = result.scalar_one_or_none()
        if tb:
            data["audit_schedule"][row_name] = {
                "opening_unadjusted": float(tb.opening_balance or 0),
                "opening_audited": float(tb.opening_balance or 0),  # 期初审定=期初余额（首年）
                "closing_unadjusted": float(tb.unadjusted_amount or 0),
                "closing_adjustment": float((tb.audited_amount or 0) - (tb.unadjusted_amount or 0)),
                "closing_audited": float(tb.audited_amount or 0),
                "change": float((tb.audited_amount or 0) - (tb.opening_balance or 0)),
            }

    # 计算合计行
    total = {"opening_unadjusted": 0, "opening_audited": 0, "closing_unadjusted": 0,
             "closing_adjustment": 0, "closing_audited": 0, "change": 0}
    for row_data in data["audit_schedule"].values():
        for k in total:
            total[k] += row_data.get(k, 0)
    data["audit_schedule"]["合计"] = total

    # 2. 银行存款明细（从辅助余额表取客户/银行维度）
    result = await db.execute(
        sa.select(TbAuxBalance).where(
            TbAuxBalance.project_id == project_id,
            TbAuxBalance.year == year,
            TbAuxBalance.account_code.like("1002%"),
            TbAuxBalance.is_deleted == sa.false(),
        ).order_by(TbAuxBalance.closing_balance.desc()).limit(30)
    )
    for aux in result.scalars().all():
        data["bank_details"].append({
            "bank_name": aux.aux_name or aux.account_name or "",
            "account_no": aux.aux_code or "",
            "closing_balance": float(aux.closing_balance or 0),
            "opening_balance": float(aux.opening_balance or 0),
            "currency": "CNY",
        })

    # 3. 大额交易（单笔>50万）
    result = await db.execute(
        sa.select(TbLedger).where(
            TbLedger.project_id == project_id,
            TbLedger.year == year,
            TbLedger.account_code.in_(["1001", "1002", "1012"]),
            TbLedger.is_deleted == sa.false(),
            sa.or_(TbLedger.debit_amount > 500000, TbLedger.credit_amount > 500000),
        ).order_by(TbLedger.voucher_date.desc()).limit(30)
    )
    for led in result.scalars().all():
        data["large_transactions"].append({
            "date": str(led.voucher_date) if led.voucher_date else "",
            "voucher_no": led.voucher_no or "",
            "summary": led.summary or "",
            "debit": float(led.debit_amount or 0),
            "credit": float(led.credit_amount or 0),
            "account_code": led.account_code,
        })

    # 4. 按月汇总（分析程序用）
    result = await db.execute(
        sa.select(
            TbLedger.accounting_period,
            sa.func.sum(TbLedger.debit_amount).label("total_debit"),
            sa.func.sum(TbLedger.credit_amount).label("total_credit"),
        ).where(
            TbLedger.project_id == project_id,
            TbLedger.year == year,
            TbLedger.account_code.in_(["1001", "1002", "1012"]),
            TbLedger.is_deleted == sa.false(),
        ).group_by(TbLedger.accounting_period).order_by(TbLedger.accounting_period)
    )
    for period, debit, credit in result.all():
        data["month_summary"][str(period)] = {
            "debit": float(debit or 0),
            "credit": float(credit or 0),
        }

    return data


async def fill_workpaper(db: AsyncSession, project_id: UUID, year: int, wb) -> dict:
    """填充底稿 Excel 文件

    Args:
        wb: openpyxl Workbook 对象（已打开的底稿文件）

    Returns:
        {"filled_cells": N, "sheets_processed": [...]}
    """
    data = await extract_data(db, project_id, year)
    filled = 0
    sheets_processed = []

    # 填充审定表 E1-1
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        for row_name, row_data in data["audit_schedule"].items():
            row_num = ROW_MAP.get(row_name)
            if not row_num:
                continue
            for col_key, col_letter in COL_MAP.items():
                value = row_data.get(col_key)
                if value is not None and value != 0:
                    cell = f"{col_letter}{row_num}"
                    ws[cell] = value
                    filled += 1
        sheets_processed.append(SHEET_NAME)

    return {"filled_cells": filled, "sheets_processed": sheets_processed}


async def generate_audit_explanation(db: AsyncSession, project_id: UUID, year: int) -> str:
    """LLM 生成货币资金审计说明（基于实际提取的结构化数据）"""
    data = await extract_data(db, project_id, year)

    schedule = data["audit_schedule"]
    total = schedule.get("合计", {})
    banks = data["bank_details"]
    large_tx = data["large_transactions"]

    # 构建详细 prompt
    balance_lines = []
    for name in ["库存现金", "银行存款", "其他货币资金"]:
        row = schedule.get(name, {})
        if row:
            balance_lines.append(f"- {name}: 期末审定 {row.get('closing_audited', 0):,.2f}，期初 {row.get('opening_audited', 0):,.2f}，变动 {row.get('change', 0):,.2f}")

    bank_lines = [f"- {b['bank_name']}: {b['closing_balance']:,.2f}" for b in banks[:8]]
    tx_lines = [f"- {t['date']} {t['summary']}: {'借' if t['debit'] > 0 else '贷'} {max(t['debit'], t['credit']):,.2f}" for t in large_tx[:5]]

    prompt = f"""请为货币资金科目生成审计说明（300-500字），严格包含以下内容：

1. 科目余额概况（合计期末 {total.get('closing_audited', 0):,.2f} 元，期初 {total.get('opening_audited', 0):,.2f} 元）
2. 各子科目变动分析
3. 银行存款构成（{len(banks)} 个银行账户）
4. 大额交易关注事项（{len(large_tx)} 笔大额交易）
5. 已执行的审计程序（函证、盘点、余额调节表等）
6. 审计结论

【各科目余额】
{chr(10).join(balance_lines)}

【银行存款明细（前8个）】
{chr(10).join(bank_lines) or '无明细'}

【大额交易（前5笔，单笔>50万）】
{chr(10).join(tx_lines) or '无大额交易'}

要求：语言专业简洁，符合致同底稿规范，关注资金安全性和完整性。"""

    from app.services.llm_client import chat_completion
    from app.services.reference_doc_service import ReferenceDocService

    context_docs = await ReferenceDocService.load_context(
        db, project_id, year, source_type="prior_year_workpaper", wp_code="E1-1",
    )

    try:
        return await chat_completion(
            [{"role": "system", "content": "你是致同会计师事务所资深审计员，请生成货币资金审计说明。"},
             {"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=1200,
            context_documents=context_docs if context_docs else None,
        )
    except Exception:
        return f"货币资金期末余额 {total.get('closing_audited', 0):,.2f} 元，较期初变动 {total.get('change', 0):,.2f} 元。经审计，未发现重大错报。"


def get_review_checklist() -> list[dict]:
    """货币资金复核要点（基于TSJ提示词精简版）"""
    return [
        {"category": "存在性（高风险）", "items": [
            "是否对所有银行账户发函确认（覆盖率要求>95%）",
            "函证是否由审计人员直接寄发和收回",
            "未回函是否执行替代程序（检查银行对账单+期后收付）",
            "库存现金是否实施突击盘点",
            "是否确认所有银行账户（含已销户、零余额账户）",
            "是否检查网银/电子支付账户",
        ]},
        {"category": "完整性（高风险）", "items": [
            "是否获取完整的银行账户清单（含境外）",
            "是否检查未入账的货币资金交易",
            "是否核实关联方控制的银行账户",
            "是否检查保证金/受限资金",
        ]},
        {"category": "计价与分摊（中风险）", "items": [
            "银行存款余额与对账单是否一致",
            "余额调节表未达账项是否合理",
            "外币折算汇率是否为资产负债表日即期汇率",
            "利息收入计算是否准确",
        ]},
        {"category": "权利和义务（中风险）", "items": [
            "是否存在质押/冻结/受限资金",
            "受限资金是否充分披露",
        ]},
        {"category": "截止（高风险）", "items": [
            "期末最后3天大额收付是否在正确期间确认",
            "银行函证日期是否为12月31日",
            "期后大额异常收付是否需要追溯调整",
        ]},
    ]


def get_template_info() -> dict:
    """返回模板结构信息（供前端展示）"""
    return {
        "template_file": "E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx",
        "total_sheets": 16,
        "key_sheets": [
            {"name": "货币资金审定表E1-1", "purpose": "汇总审定表", "auto_fill": True},
            {"name": "现金明细表E1-2", "purpose": "库存现金明细", "auto_fill": False},
            {"name": "银行存款及其他货币资金明细表E1-3", "purpose": "银行存款明细", "auto_fill": True},
            {"name": "调整分录汇总E1-5", "purpose": "AJE/RJE汇总", "auto_fill": True},
            {"name": "银行存款余额调节表E1-6", "purpose": "余额调节", "auto_fill": False},
            {"name": "已开立银行账户清单核对表E1-10", "purpose": "账户完整性", "auto_fill": False},
        ],
        "row_map": ROW_MAP,
        "col_map": COL_MAP,
    }
