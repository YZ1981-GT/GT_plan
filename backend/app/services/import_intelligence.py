"""账表导入智能增强层 — 模糊匹配+增量导入+深度校验+导入概览

解决5个薄弱环节：
1. 列映射模糊匹配（编辑距离+LLM辅助）
2. 多Sheet智能识别增强（内容特征分析）
3. 深度数据质量校验（科目格式/金额异常/日期连续性）
4. 增量/追加导入（按月份/维度追加，不全量替换）
5. 导入结果可视化数据（按科目汇总+差异对比+质量评分）
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.dataset_query import get_active_filter

_logger = logging.getLogger(__name__)


# ═══ 1. 列映射模糊匹配增强 ═══

# 常见变体模式（正则）
_FUZZY_PATTERNS: list[tuple[str, str]] = [
    (r"本[年期]累计.*借方", "debit_amount"),
    (r"本[年期]累计.*贷方", "credit_amount"),
    (r"[年期][初始].*借方", "opening_debit"),
    (r"[年期][初始].*贷方", "opening_credit"),
    (r"[年期][末终].*借方", "closing_debit"),
    (r"[年期][末终].*贷方", "closing_credit"),
    (r"[年期][末终].*余额", "closing_balance"),
    (r"[年期][初始].*余额", "opening_balance"),
    (r"科目.*[编代号码]", "account_code"),
    (r"科目.*名称", "account_name"),
    (r"凭证.*[编号]", "voucher_no"),
    (r"凭证.*日期", "voucher_date"),
    (r"记账.*日期", "voucher_date"),
    (r"摘要|备注|说明", "summary"),
    (r"借方.*[金发]", "debit_amount"),
    (r"贷方.*[金发]", "credit_amount"),
    (r"核算.*[维项]", "aux_dimensions"),
    (r"辅助.*[核项]", "aux_dimensions"),
    (r"对方.*科目", "counter_account"),
    (r"币[种别]", "currency_code"),
]

# 标准字段的中文别名（用于编辑距离匹配）
_FIELD_ALIASES: dict[str, list[str]] = {
    "account_code": ["科目编码", "科目代码", "科目编号", "会计科目编码", "科目号"],
    "account_name": ["科目名称", "会计科目名称", "科目全称"],
    "voucher_date": ["凭证日期", "记账日期", "制单日期", "日期"],
    "voucher_no": ["凭证号", "凭证编号", "凭证字号", "记账凭证号"],
    "debit_amount": ["借方金额", "借方发生额", "本期借方", "借方"],
    "credit_amount": ["贷方金额", "贷方发生额", "本期贷方", "贷方"],
    "opening_balance": ["期初余额", "年初余额", "期初数"],
    "closing_balance": ["期末余额", "期末数", "余额"],
    "summary": ["摘要", "备注", "说明", "附注"],
}


def fuzzy_match_column(header: str, threshold: float = 0.6) -> tuple[str | None, float]:
    """模糊匹配列名（编辑距离+正则模式）

    Returns: (matched_field, confidence)
    """
    h = header.strip()
    if not h:
        return None, 0.0

    # 1. 正则模式匹配
    for pattern, field in _FUZZY_PATTERNS:
        if re.search(pattern, h):
            return field, 0.85

    # 2. 编辑距离匹配（与所有别名比较）
    best_field = None
    best_score = 0.0

    for field, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            score = SequenceMatcher(None, h, alias).ratio()
            if score > best_score:
                best_score = score
                best_field = field

    if best_score >= threshold:
        return best_field, best_score

    # 3. 子串包含匹配
    for field, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias in h or h in alias:
                return field, 0.7

    return None, 0.0


def _auto_apply_threshold() -> float:
    threshold = float(settings.LEDGER_IMPORT_AUTO_APPLY_CONFIDENCE_THRESHOLD)
    return min(max(threshold, 0.0), 1.0)


def enhance_column_mapping(headers: list[str], existing_mapping: dict[str, str]) -> dict[str, Any]:
    """增强列映射：对未匹配的列尝试模糊匹配

    Args:
        headers: 原始表头列表
        existing_mapping: smart_match_column 已匹配的结果 {header: field}

    Returns:
        {
            "enhanced": {header: field},  # 新增的模糊匹配
            "suggestions": [{header, field, confidence, reason}],  # 建议（需用户确认）
            "unmatched": [header],  # 仍未匹配
        }
    """
    enhanced = {}
    suggestions = []
    unmatched = []
    auto_apply_threshold = _auto_apply_threshold()

    matched_fields = set(existing_mapping.values())

    for h in headers:
        if h in existing_mapping:
            continue  # 已匹配，跳过

        field, confidence = fuzzy_match_column(h)
        if field and field not in matched_fields:
            if confidence >= auto_apply_threshold:
                enhanced[h] = field
                matched_fields.add(field)
            elif confidence >= 0.6:
                suggestions.append({
                    "header": h,
                    "suggested_field": field,
                    "confidence": round(confidence, 2),
                    "reason": "模糊匹配",
                })
            else:
                unmatched.append(h)
        else:
            unmatched.append(h)

    return {
        "enhanced": enhanced,
        "suggestions": suggestions,
        "unmatched": unmatched,
        "auto_apply_threshold": auto_apply_threshold,
    }


# ═══ 2. 多Sheet智能识别增强 ═══

def detect_sheet_type_by_content(headers: list[str], sample_rows: list[list]) -> dict[str, Any]:
    """通过内容特征分析Sheet类型（补充列名识别不足的情况）

    分析前20行数据的特征：
    - 有日期格式的列 → 可能是序时账
    - 有大量数字列 → 可能是余额表
    - 行数少且有层级结构 → 可能是科目表
    """
    features = {
        "has_date_column": False,
        "has_numeric_columns": 0,
        "has_hierarchy": False,
        "row_count_hint": len(sample_rows),
        "unique_first_col": set(),
    }

    for row in sample_rows[:20]:
        for i, val in enumerate(row):
            if val is None:
                continue
            s = str(val)
            # 日期检测
            if re.match(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', s):
                features["has_date_column"] = True
            # 数字检测
            if i > 0 and re.match(r'^-?[\d,]+\.?\d*$', s.replace(',', '')):
                features["has_numeric_columns"] += 1
        # 第一列唯一值（科目编码特征）
        if row and row[0]:
            features["unique_first_col"].add(str(row[0]))

    # 推断类型
    inferred_type = "unknown"
    confidence = 0.5

    if features["has_date_column"] and features["has_numeric_columns"] > 2:
        inferred_type = "ledger"
        confidence = 0.75
    elif features["has_numeric_columns"] > 4 and not features["has_date_column"]:
        inferred_type = "balance"
        confidence = 0.7
    elif len(features["unique_first_col"]) > 10 and features["row_count_hint"] < 500:
        # 很多不同的第一列值，行数不多 → 可能是科目表
        first_vals = list(features["unique_first_col"])[:5]
        if all(re.match(r'\d{4}', str(v)) for v in first_vals):
            inferred_type = "account_chart"
            confidence = 0.7

    return {
        "inferred_type": inferred_type,
        "confidence": confidence,
        "features": {k: v if not isinstance(v, set) else len(v) for k, v in features.items()},
    }


# ═══ 3. 深度数据质量校验 ═══

async def deep_quality_check(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> dict[str, Any]:
    """深度数据质量校验（导入后执行）

    校验项：
    - DQ-01: 科目编码格式（4位一级+明细）
    - DQ-02: 金额异常检测（单笔超大额/负数余额）
    - DQ-03: 日期连续性（是否有月份缺失）
    - DQ-04: 借贷平衡（按凭证号汇总）
    - DQ-05: 科目余额表vs序时账发生额一致性
    """
    from app.models.audit_platform_models import TbBalance, TbLedger

    findings = []

    # DQ-01: 科目编码格式
    result = await db.execute(
        sa.select(TbBalance.account_code).where(
            await get_active_filter(db, TbBalance.__table__, project_id, year),
        ).distinct()
    )
    codes = [r[0] for r in result.all()]
    invalid_codes = [c for c in codes if not re.match(r'^\d{4}', c)]
    if invalid_codes:
        findings.append({
            "rule": "DQ-01",
            "severity": "warning",
            "message": f"科目编码格式异常：{len(invalid_codes)} 个科目不以4位数字开头",
            "samples": invalid_codes[:5],
        })

    # DQ-02: 金额异常（单笔超1亿）
    result = await db.execute(
        sa.select(sa.func.count()).select_from(TbLedger).where(
            await get_active_filter(db, TbLedger.__table__, project_id, year),
            sa.or_(
                TbLedger.debit_amount > 100000000,
                TbLedger.credit_amount > 100000000,
            ),
        )
    )
    large_count = result.scalar() or 0
    if large_count > 0:
        findings.append({
            "rule": "DQ-02",
            "severity": "info",
            "message": f"大额交易提醒：{large_count} 笔金额超过1亿元",
            "count": large_count,
        })

    # DQ-03: 日期连续性（检查12个月是否都有数据）
    result = await db.execute(
        sa.select(
            sa.func.extract('month', TbLedger.voucher_date).label('month'),
            sa.func.count().label('cnt'),
        ).where(
            await get_active_filter(db, TbLedger.__table__, project_id, year),
            TbLedger.voucher_date.isnot(None),
        ).group_by(sa.text('1'))
    )
    months_with_data = {int(r[0]) for r in result.all() if r[0]}
    missing_months = set(range(1, 13)) - months_with_data
    if missing_months:
        findings.append({
            "rule": "DQ-03",
            "severity": "warning",
            "message": f"月份数据缺失：{sorted(missing_months)} 月无凭证数据",
            "missing_months": sorted(missing_months),
        })

    # DQ-04: 借贷平衡（按凭证号汇总）
    result = await db.execute(
        sa.text("""
            SELECT l.voucher_no,
                   ABS(SUM(COALESCE(l.debit_amount,0)) - SUM(COALESCE(l.credit_amount,0))) as diff
            FROM tb_ledger l
            WHERE l.project_id = :pid AND l.year = :yr
              AND EXISTS (
                SELECT 1 FROM ledger_datasets d
                WHERE d.id = l.dataset_id AND d.status = 'active'
              )
              AND l.voucher_no IS NOT NULL
            GROUP BY l.voucher_no
            HAVING ABS(SUM(COALESCE(l.debit_amount,0)) - SUM(COALESCE(l.credit_amount,0))) > 0.01
            LIMIT 10
        """).bindparams(pid=project_id, yr=year)
    )
    unbalanced = result.all()
    if unbalanced:
        findings.append({
            "rule": "DQ-04",
            "severity": "error",
            "message": f"借贷不平衡：{len(unbalanced)} 张凭证借贷差额>0.01",
            "samples": [{"voucher_no": r[0], "diff": float(r[1])} for r in unbalanced[:5]],
        })

    # DQ-05: 余额表vs序时账发生额
    result = await db.execute(
        sa.text("""
            SELECT b.account_code,
                   COALESCE(b.debit_amount,0) as bal_debit,
                   COALESCE(l.ledger_debit,0) as led_debit,
                   ABS(COALESCE(b.debit_amount,0) - COALESCE(l.ledger_debit,0)) as diff
            FROM tb_balance b
            LEFT JOIN (
                SELECT l2.account_code, SUM(COALESCE(l2.debit_amount,0)) as ledger_debit
                FROM tb_ledger l2
                WHERE l2.project_id = :pid AND l2.year = :yr
                  AND EXISTS (
                    SELECT 1 FROM ledger_datasets d
                    WHERE d.id = l2.dataset_id AND d.status = 'active'
                  )
                GROUP BY l2.account_code
            ) l ON b.account_code = l.account_code
            WHERE b.project_id = :pid AND b.year = :yr
              AND EXISTS (
                SELECT 1 FROM ledger_datasets d
                WHERE d.id = b.dataset_id AND d.status = 'active'
              )
            HAVING ABS(COALESCE(b.debit_amount,0) - COALESCE(l.ledger_debit,0)) > 1
            ORDER BY diff DESC
            LIMIT 5
        """).bindparams(pid=project_id, yr=year)
    )
    inconsistent = result.all()
    if inconsistent:
        findings.append({
            "rule": "DQ-05",
            "severity": "warning",
            "message": f"余额表与序时账不一致：{len(inconsistent)} 个科目借方发生额有差异",
            "samples": [{"account_code": r[0], "balance_debit": float(r[1]),
                         "ledger_debit": float(r[2]), "diff": float(r[3])} for r in inconsistent],
        })

    # 质量评分
    error_count = sum(1 for f in findings if f["severity"] == "error")
    warning_count = sum(1 for f in findings if f["severity"] == "warning")
    score = max(0, 100 - error_count * 20 - warning_count * 5)

    return {
        "score": score,
        "grade": "A" if score >= 90 else "B" if score >= 70 else "C" if score >= 50 else "D",
        "findings": findings,
        "summary": f"质量评分 {score}/100（{error_count} 错误 + {warning_count} 警告）",
    }


# ═══ 4. 增量/追加导入 ═══

class IncrementalImportMode:
    FULL_REPLACE = "full_replace"      # 全量替换（默认）
    APPEND_PERIOD = "append_period"    # 按月份追加
    APPEND_DIMENSION = "append_dimension"  # 按辅助维度追加
    MERGE = "merge"                    # 合并（新增+更新，不删除）


async def prepare_incremental_import(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    mode: str,
    period: str | None = None,
) -> dict[str, Any]:
    """准备增量导入：分析现有数据，确定追加策略

    Args:
        mode: full_replace / append_period / append_dimension / merge
        period: 月份（如 "10" 表示10月），仅 append_period 模式需要

    Returns:
        {"strategy": ..., "existing_count": ..., "will_affect": ...}
    """
    from app.models.audit_platform_models import TbLedger, TbBalance

    if mode == IncrementalImportMode.FULL_REPLACE:
        # 统计现有数据量
        ledger_count = (await db.execute(
            sa.select(sa.func.count()).select_from(TbLedger).where(
                await get_active_filter(db, TbLedger.__table__, project_id, year),
            )
        )).scalar() or 0
        balance_count = (await db.execute(
            sa.select(sa.func.count()).select_from(TbBalance).where(
                await get_active_filter(db, TbBalance.__table__, project_id, year),
            )
        )).scalar() or 0

        return {
            "mode": mode,
            "strategy": "全量替换：旧数据标记superseded，新数据创建新dataset",
            "existing_ledger": ledger_count,
            "existing_balance": balance_count,
            "will_affect": "全部数据",
        }

    elif mode == IncrementalImportMode.APPEND_PERIOD:
        if not period:
            return {"error": "append_period 模式需要指定 period 参数"}

        # 检查该月份是否已有数据
        month = int(period)
        existing = (await db.execute(
            sa.select(sa.func.count()).select_from(TbLedger).where(
                await get_active_filter(db, TbLedger.__table__, project_id, year),
                sa.func.extract('month', TbLedger.voucher_date) == month,
            )
        )).scalar() or 0

        return {
            "mode": mode,
            "period": period,
            "strategy": f"追加{month}月数据：{'覆盖已有' if existing > 0 else '新增'}",
            "existing_in_period": existing,
            "will_affect": f"仅{month}月数据",
        }

    elif mode == IncrementalImportMode.MERGE:
        return {
            "mode": mode,
            "strategy": "合并模式：新增不存在的记录，更新已存在的（按科目+凭证号匹配）",
            "will_affect": "新增+更新，不删除",
        }

    return {"mode": mode, "strategy": "未知模式"}


# ═══ 5. 导入结果可视化数据 ═══

async def generate_import_overview(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> dict[str, Any]:
    """生成导入结果概览（供前端可视化展示）

    包含：
    - 按科目类别汇总（资产/负债/权益/收入/费用各多少笔）
    - 按月份分布（每月凭证数量）
    - 关键指标（总科目数/总凭证数/总金额/辅助维度数）
    - 与上次导入的差异（新增/变化的科目）
    """
    from app.models.audit_platform_models import TbBalance, TbLedger, TbAuxBalance

    overview: dict[str, Any] = {"project_id": str(project_id), "year": year}

    # 关键指标
    balance_count = (await db.execute(
        sa.select(sa.func.count()).select_from(TbBalance).where(
            await get_active_filter(db, TbBalance.__table__, project_id, year),
        )
    )).scalar() or 0

    ledger_count = (await db.execute(
        sa.select(sa.func.count()).select_from(TbLedger).where(
            await get_active_filter(db, TbLedger.__table__, project_id, year),
        )
    )).scalar() or 0

    aux_count = (await db.execute(
        sa.select(sa.func.count()).select_from(TbAuxBalance).where(
            await get_active_filter(db, TbAuxBalance.__table__, project_id, year),
        )
    )).scalar() or 0

    # 总金额
    total_debit = (await db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(TbLedger.debit_amount), 0)).where(
            await get_active_filter(db, TbLedger.__table__, project_id, year),
        )
    )).scalar() or 0

    overview["metrics"] = {
        "balance_accounts": balance_count,
        "ledger_entries": ledger_count,
        "aux_records": aux_count,
        "total_debit": float(total_debit),
    }

    # 按科目类别汇总
    result = await db.execute(
        sa.text("""
            SELECT
                CASE
                    WHEN b.account_code LIKE '1%' THEN '资产'
                    WHEN b.account_code LIKE '2%' THEN '负债'
                    WHEN b.account_code LIKE '3%' OR b.account_code LIKE '4%' THEN '权益'
                    WHEN b.account_code LIKE '5%' OR b.account_code LIKE '60%' THEN '收入'
                    WHEN b.account_code LIKE '6%' THEN '费用'
                    ELSE '其他'
                END as category,
                COUNT(*) as cnt
            FROM tb_balance b
            WHERE b.project_id = :pid AND b.year = :yr
              AND EXISTS (
                SELECT 1 FROM ledger_datasets d
                WHERE d.id = b.dataset_id AND d.status = 'active'
              )
            GROUP BY 1
            ORDER BY 1
        """).bindparams(pid=project_id, yr=year)
    )
    overview["by_category"] = [{"category": r[0], "count": r[1]} for r in result.all()]

    # 按月份分布
    result = await db.execute(
        sa.text("""
            SELECT EXTRACT(MONTH FROM l.voucher_date)::int as month, COUNT(*) as cnt
            FROM tb_ledger l
            WHERE l.project_id = :pid AND l.year = :yr
              AND EXISTS (
                SELECT 1 FROM ledger_datasets d
                WHERE d.id = l.dataset_id AND d.status = 'active'
              )
              AND l.voucher_date IS NOT NULL
            GROUP BY 1
            ORDER BY 1
        """).bindparams(pid=project_id, yr=year)
    )
    overview["by_month"] = [{"month": r[0], "count": r[1]} for r in result.all()]

    return overview
