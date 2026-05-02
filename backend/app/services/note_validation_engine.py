"""附注校验引擎 — 8种校验规则 + 汇总结果

核心功能：
- validate_all: 执行全部校验规则
- BalanceValidator: 报表余额 vs 附注合计行
- SubItemValidator: 明细行求和 = 合计行
- WideTableValidator / VerticalValidator / CrossTableValidator / etc: 存根实现

Validates: Requirements 5.1, 5.2, 5.3, 5.5
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import (
    DisclosureNote,
    FinancialReport,
    FinancialReportType,
    NoteValidationResult,
)

logger = logging.getLogger(__name__)

SEED_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_templates_seed.json"


def _load_seed_data() -> dict:
    with open(SEED_DATA_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


# ------------------------------------------------------------------
# Validator functions
# ------------------------------------------------------------------


async def validate_balance(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """余额核对：附注合计行 = 报表对应行金额。

    Validates: Requirements 5.1 (balance check)
    """
    findings = []
    table_data = note.table_data
    if not table_data or "rows" not in table_data:
        return findings

    # Find the template for this note to get report_row_code
    tmpl = _find_template(note.note_section, seed_templates)
    if not tmpl:
        return findings

    report_row_code = tmpl.get("report_row_code")
    if not report_row_code:
        return findings

    # Determine report_type from row_code prefix
    report_type = _row_code_to_report_type(report_row_code)
    if not report_type:
        return findings

    # Get report amount
    result = await db.execute(
        sa.select(FinancialReport.current_period_amount).where(
            FinancialReport.project_id == note.project_id,
            FinancialReport.year == note.year,
            FinancialReport.report_type == report_type,
            FinancialReport.row_code == report_row_code,
            FinancialReport.is_deleted == sa.false(),
        )
    )
    report_amount = result.scalar_one_or_none()
    if report_amount is None:
        return findings

    # Find total row in note table_data
    total_amount = _get_total_row_amount(table_data)
    if total_amount is None:
        return findings

    diff = Decimal(str(report_amount)) - Decimal(str(total_amount))
    if diff != Decimal("0"):
        findings.append({
            "note_section": note.note_section,
            "table_name": note.section_title,
            "check_type": "balance",
            "severity": "error",
            "message": f"附注合计行({total_amount})与报表行({report_amount})不一致，差异{diff}",
            "expected_value": float(report_amount),
            "actual_value": float(total_amount),
        })

    return findings


async def validate_sub_item(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """其中项校验：明细行求和 = 合计行。

    Validates: Requirements 5.1 (sub_item check)
    """
    findings = []
    table_data = note.table_data
    if not table_data or "rows" not in table_data:
        return findings

    rows = table_data["rows"]
    # Find total row and sum detail rows
    detail_sum_current = Decimal("0")
    detail_sum_prior = Decimal("0")
    total_current = None
    total_prior = None

    for row in rows:
        values = row.get("values", [])
        is_total = row.get("is_total", False)
        if is_total:
            total_current = Decimal(str(values[0])) if len(values) > 0 else None
            total_prior = Decimal(str(values[1])) if len(values) > 1 else None
        else:
            if len(values) > 0:
                detail_sum_current += Decimal(str(values[0]))
            if len(values) > 1:
                detail_sum_prior += Decimal(str(values[1]))

    if total_current is not None:
        diff = detail_sum_current - total_current
        if diff != Decimal("0"):
            findings.append({
                "note_section": note.note_section,
                "table_name": note.section_title,
                "check_type": "sub_item",
                "severity": "error",
                "message": f"期末明细行合计({detail_sum_current})与合计行({total_current})不一致，差异{diff}",
                "expected_value": float(total_current),
                "actual_value": float(detail_sum_current),
            })

    if total_prior is not None:
        diff = detail_sum_prior - total_prior
        if diff != Decimal("0"):
            findings.append({
                "note_section": note.note_section,
                "table_name": note.section_title,
                "check_type": "sub_item",
                "severity": "error",
                "message": f"期初明细行合计({detail_sum_prior})与合计行({total_prior})不一致，差异{diff}",
                "expected_value": float(total_prior),
                "actual_value": float(detail_sum_prior),
            })

    return findings


async def validate_wide_table(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """宽表公式校验：检查横向公式（如 期初+增加-减少=期末）。"""
    findings: list[dict] = []
    table_data = note.table_data if hasattr(note, 'table_data') else None
    if not table_data or not isinstance(table_data, dict):
        return findings

    headers = table_data.get("headers") or []
    rows = table_data.get("rows") or []
    if len(headers) < 4:
        return findings

    # 检测是否有"期初""期末"列
    opening_idx = next((i for i, h in enumerate(headers) if "期初" in str(h)), None)
    closing_idx = next((i for i, h in enumerate(headers) if "期末" in str(h)), None)
    if opening_idx is None or closing_idx is None:
        return findings

    for row_idx, row in enumerate(rows):
        if row.get("is_total"):
            continue
        values = row.get("values") or []
        if len(values) <= max(opening_idx - 1, closing_idx - 1):
            continue
        try:
            opening = float(values[opening_idx - 1] or 0)
            closing = float(values[closing_idx - 1] or 0)
            # 中间列求和
            mid_sum = sum(float(values[i] or 0) for i in range(opening_idx, closing_idx - 1))
            expected = opening + mid_sum
            if abs(expected - closing) > 0.01:
                findings.append({
                    "rule": "wide_table_formula",
                    "severity": "warning",
                    "message": f"第 {row_idx+1} 行横向公式不平：期初({opening})+变动({mid_sum})≠期末({closing})，差额 {expected-closing:.2f}",
                    "note_section": note.note_section,
                })
        except (TypeError, ValueError, IndexError):
            continue

    # book_value 专项：原值 - 累计折旧/摊销 - 减值准备 = 账面价值
    bv_row_idx = next((i for i, r in enumerate(rows) if "账面价值" in str(r.get("label", "")) and "期末" in str(r.get("label", ""))), None)
    orig_row_idx = next((i for i, r in enumerate(rows) if "原值期末" in str(r.get("label", ""))), None)
    depr_row_idx = next((i for i, r in enumerate(rows) if any(kw in str(r.get("label", "")) for kw in ("累计折旧期末", "累计摊销期末"))), None)
    impair_row_idx = next((i for i, r in enumerate(rows) if "减值准备期末" in str(r.get("label", "")) or r.get("label", "") == "减值准备"), None)

    if bv_row_idx is not None and orig_row_idx is not None:
        bv_values = rows[bv_row_idx].get("values") or []
        orig_values = rows[orig_row_idx].get("values") or []
        depr_values = rows[depr_row_idx].get("values") or [] if depr_row_idx is not None else []
        impair_values = rows[impair_row_idx].get("values") or [] if impair_row_idx is not None else []

        for col in range(min(len(bv_values), len(orig_values))):
            try:
                bv = float(bv_values[col] or 0)
                orig = float(orig_values[col] or 0)
                depr = float(depr_values[col] or 0) if col < len(depr_values) else 0
                impair = float(impair_values[col] or 0) if col < len(impair_values) else 0
                expected_bv = orig - depr - impair
                if abs(expected_bv - bv) > 0.01 and orig != 0:
                    col_name = headers[col + 1] if col + 1 < len(headers) else f"第{col+1}列"
                    findings.append({
                        "rule": "book_value_formula",
                        "severity": "warning",
                        "message": f"「{col_name}」账面价值({bv})≠原值({orig})-折旧({depr})-减值({impair})={expected_bv}，差额 {bv-expected_bv:.2f}",
                        "note_section": note.note_section,
                    })
            except (TypeError, ValueError):
                continue

    return findings


async def validate_vertical(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """纵向勾稽校验：检查合计行是否等于明细行之和。"""
    findings: list[dict] = []
    table_data = note.table_data if hasattr(note, 'table_data') else None
    if not table_data or not isinstance(table_data, dict):
        return findings

    rows = table_data.get("rows") or []
    headers = table_data.get("headers") or []
    if not rows or len(headers) < 2:
        return findings

    # 找到合计行
    total_rows = [(i, r) for i, r in enumerate(rows) if r.get("is_total")]
    if not total_rows:
        return findings

    for total_idx, total_row in total_rows:
        total_values = total_row.get("values") or []
        # 合计行上方的非合计行
        detail_rows = [r for i, r in enumerate(rows) if i < total_idx and not r.get("is_total")]
        if not detail_rows:
            continue

        for col_idx in range(len(total_values)):
            try:
                total_val = float(total_values[col_idx] or 0)
                if total_val == 0:
                    continue
                detail_sum = sum(float((r.get("values") or [])[col_idx] or 0) for r in detail_rows if len(r.get("values") or []) > col_idx)
                if abs(total_val - detail_sum) > 0.01:
                    col_name = headers[col_idx + 1] if col_idx + 1 < len(headers) else f"第{col_idx+1}列"
                    findings.append({
                        "rule": "vertical_sum",
                        "severity": "warning",
                        "message": f"「{col_name}」合计行({total_val})≠明细行之和({detail_sum})，差额 {total_val-detail_sum:.2f}",
                        "note_section": note.note_section,
                    })
            except (TypeError, ValueError, IndexError):
                continue

    return findings


async def validate_cross_table(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """交叉校验：报表数 vs 附注合计行。"""
    findings: list[dict] = []
    from app.models.report_models import FinancialReport

    table_data = note.table_data if hasattr(note, 'table_data') else None
    if not table_data or not isinstance(table_data, dict):
        return findings

    # 获取附注合计值
    rows = table_data.get("rows") or []
    total_rows = [r for r in rows if r.get("is_total")]
    if not total_rows:
        return findings

    # 尝试从报表中找到对应科目的金额
    note_section = note.note_section or ""
    try:
        import sqlalchemy as sa
        result = await db.execute(
            sa.select(FinancialReport.amount).where(
                FinancialReport.project_id == note.project_id,
                FinancialReport.year == note.year,
                FinancialReport.note_reference == note_section,
                FinancialReport.is_deleted == sa.false(),
            )
        )
        report_amount = result.scalar_one_or_none()
        if report_amount is not None:
            # 取附注合计行第一个数值列
            total_values = total_rows[-1].get("values") or []
            if total_values:
                try:
                    note_total = float(total_values[0] or 0)
                    report_val = float(report_amount)
                    if abs(note_total - report_val) > 0.01:
                        findings.append({
                            "rule": "cross_table",
                            "severity": "error",
                            "message": f"附注合计({note_total})≠报表金额({report_val})，差额 {note_total-report_val:.2f}",
                            "note_section": note_section,
                        })
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass  # 报表数据不可用时跳过

    return findings


async def validate_aging_transition(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """账龄衔接校验：上年期末各区间 → 当年期初各区间应顺移一档。"""
    findings: list[dict] = []
    # 账龄衔接需要上年数据，当前阶段仅检查表格结构完整性
    table_data = note.table_data if hasattr(note, 'table_data') else None
    if not table_data or not isinstance(table_data, dict):
        return findings

    headers = table_data.get("headers") or []
    rows = table_data.get("rows") or []

    # 检查是否有账龄相关列
    aging_keywords = ["1年以内", "1-2年", "2-3年", "3年以上", "合计"]
    has_aging = any(any(kw in str(h) for kw in aging_keywords) for h in headers)
    if not has_aging:
        return findings

    # 检查合计行是否等于各区间之和
    total_rows = [r for r in rows if r.get("is_total")]
    if total_rows:
        total_values = total_rows[-1].get("values") or []
        detail_rows = [r for r in rows if not r.get("is_total")]
        if detail_rows and total_values:
            for col_idx in range(len(total_values)):
                try:
                    total_val = float(total_values[col_idx] or 0)
                    if total_val == 0:
                        continue
                    detail_sum = sum(float((r.get("values") or [])[col_idx] or 0) for r in detail_rows if len(r.get("values") or []) > col_idx)
                    if abs(total_val - detail_sum) > 0.01:
                        findings.append({
                            "rule": "aging_sum",
                            "severity": "warning",
                            "message": f"账龄表合计({total_val})≠各区间之和({detail_sum})",
                            "note_section": note.note_section,
                        })
                        break  # 只报一次
                except (TypeError, ValueError, IndexError):
                    continue

    return findings


async def validate_completeness(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """完整性校验：检查数值列非空率。"""
    findings: list[dict] = []
    table_data = note.table_data if hasattr(note, 'table_data') else None
    if not table_data or not isinstance(table_data, dict):
        return findings

    rows = table_data.get("rows") or []
    if not rows:
        return findings

    # 统计非合计行的数值列非空率
    data_rows = [r for r in rows if not r.get("is_total")]
    if not data_rows:
        return findings

    total_cells = 0
    empty_cells = 0
    for row in data_rows:
        values = row.get("values") or []
        for v in values:
            total_cells += 1
            if v is None or v == "" or v == 0:
                empty_cells += 1

    if total_cells > 0:
        empty_rate = empty_cells / total_cells
        if empty_rate > 0.5:
            findings.append({
                "rule": "completeness",
                "severity": "warning",
                "message": f"数据完整性偏低：{empty_cells}/{total_cells} 个单元格为空（{empty_rate:.0%}）",
                "note_section": note.note_section,
            })

    return findings


async def validate_llm_review(
    db: AsyncSession,
    note: DisclosureNote,
    seed_templates: list[dict],
) -> list[dict]:
    """LLM 辅助审核：检查叙述文字表述合理性。

    降级策略：LLM 不可用时返回空（不阻断校验流程）。
    """
    findings: list[dict] = []

    # 只对有叙述文字的附注执行
    text_content = ""
    if hasattr(note, 'text_content') and note.text_content:
        text_content = note.text_content
    elif hasattr(note, 'content') and isinstance(note.content, str):
        text_content = note.content

    if not text_content or len(text_content) < 50:
        return findings

    try:
        from app.services.llm_client import chat_completion
        prompt = f"""请检查以下审计附注文字是否存在明显问题（错别字、前后矛盾、数据引用错误）。
如果没有问题，回复"无问题"。如果有问题，简要列出（每条一行）。

附注内容：
{text_content[:2000]}"""

        result = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )

        if result and "无问题" not in result and "[LLM" not in result:
            findings.append({
                "rule": "llm_review",
                "severity": "info",
                "message": f"AI 审核建议：{result[:200]}",
                "note_section": note.note_section,
            })
    except Exception:
        pass  # LLM 不可用时静默跳过

    return findings


# Validator registry
VALIDATORS = {
    "balance": validate_balance,
    "sub_item": validate_sub_item,
    "wide_table": validate_wide_table,
    "vertical": validate_vertical,
    "cross_table": validate_cross_table,
    "aging": validate_aging_transition,
    "completeness": validate_completeness,
    "llm_review": validate_llm_review,
}


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------


def _find_template(note_section: str, templates: list[dict]) -> dict | None:
    for t in templates:
        if t.get("note_section") == note_section:
            return t
    return None


def _row_code_to_report_type(row_code: str) -> FinancialReportType | None:
    if row_code.startswith("BS-"):
        return FinancialReportType.balance_sheet
    elif row_code.startswith("IS-"):
        return FinancialReportType.income_statement
    elif row_code.startswith("CF-"):
        return FinancialReportType.cash_flow_statement
    elif row_code.startswith("EQ-"):
        return FinancialReportType.equity_statement
    return None


def _get_total_row_amount(table_data: dict) -> Decimal | None:
    """从 table_data 中获取合计行的期末余额（第一个 values 值）"""
    rows = table_data.get("rows", [])
    for row in rows:
        if row.get("is_total", False):
            values = row.get("values", [])
            if values:
                return Decimal(str(values[0]))
    return None


# ------------------------------------------------------------------
# NoteValidationEngine
# ------------------------------------------------------------------


class NoteValidationEngine:
    """附注校验引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_all(
        self,
        project_id: UUID,
        year: int,
    ) -> dict:
        """执行全部校验规则，返回校验结果。

        Validates: Requirements 5.2, 5.3
        """
        seed = _load_seed_data()
        templates = seed.get("account_mapping_template", [])
        check_presets = seed.get("check_presets", {})

        # Load all notes
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        notes = result.scalars().all()

        all_findings: list[dict] = []

        for note in notes:
            account_name = note.account_name or ""
            applicable_checks = check_presets.get(account_name, [])

            for check_type in applicable_checks:
                validator_fn = VALIDATORS.get(check_type)
                if validator_fn is None:
                    continue
                try:
                    findings = await validator_fn(self.db, note, templates)
                    all_findings.extend(findings)
                except Exception as e:
                    logger.warning(
                        "Validator %s failed for note %s: %s",
                        check_type, note.note_section, e,
                    )

        # Count by severity
        error_count = sum(1 for f in all_findings if f.get("severity") == "error")
        warning_count = sum(1 for f in all_findings if f.get("severity") == "warning")
        info_count = sum(1 for f in all_findings if f.get("severity") == "info")

        # Save to note_validation_results
        now = datetime.utcnow()
        validation_result = NoteValidationResult(
            project_id=project_id,
            year=year,
            validation_timestamp=now,
            findings=all_findings,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
        )
        self.db.add(validation_result)
        await self.db.flush()

        return {
            "id": str(validation_result.id),
            "project_id": str(project_id),
            "year": year,
            "validation_timestamp": now.isoformat(),
            "findings": all_findings,
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
        }

    async def get_latest_results(
        self,
        project_id: UUID,
        year: int,
    ) -> NoteValidationResult | None:
        """获取最新校验结果"""
        result = await self.db.execute(
            sa.select(NoteValidationResult)
            .where(
                NoteValidationResult.project_id == project_id,
                NoteValidationResult.year == year,
            )
            .order_by(NoteValidationResult.validation_timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def confirm_finding(
        self,
        validation_id: UUID,
        finding_index: int,
        reason: str,
    ) -> bool:
        """确认校验发现为"已确认-无需修改"。

        Validates: Requirements 5.5
        """
        result = await self.db.execute(
            sa.select(NoteValidationResult).where(
                NoteValidationResult.id == validation_id,
            )
        )
        validation = result.scalar_one_or_none()
        if validation is None:
            return False

        findings = validation.findings
        if not isinstance(findings, list) or finding_index >= len(findings):
            return False

        # Deep copy to force SQLAlchemy to detect the change
        import copy
        new_findings = copy.deepcopy(findings)
        new_findings[finding_index]["confirmed"] = True
        new_findings[finding_index]["confirm_reason"] = reason
        validation.findings = new_findings

        # Explicit UPDATE for SQLite compatibility
        await self.db.execute(
            sa.update(NoteValidationResult)
            .where(NoteValidationResult.id == validation_id)
            .values(findings=new_findings)
        )
        await self.db.flush()
        return True
