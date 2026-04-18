"""底稿质量自检引擎 — QCRule 基类 + 12条规则 + QCEngine + 项目汇总

MVP实现：所有规则为 stub，返回空 findings。框架完整可扩展。

Validates: Requirements 8.1, 8.2, 8.4, 9.1
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import (
    WpIndex,
    WpQcResult,
    WpStatus,
    WorkingPaper,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# QCContext — 检查上下文
# ---------------------------------------------------------------------------

class QCContext:
    """QC检查上下文，包含底稿元数据和项目数据。"""

    def __init__(
        self,
        db: AsyncSession,
        working_paper: WorkingPaper,
        wp_index: WpIndex | None = None,
        project_id: UUID | None = None,
        year: int = 2025,
    ):
        self.db = db
        self.working_paper = working_paper
        self.wp_index = wp_index
        self.project_id = project_id or working_paper.project_id
        self.year = year


# ---------------------------------------------------------------------------
# QCFinding — 检查发现
# ---------------------------------------------------------------------------

class QCFindingItem:
    """单条检查发现。"""

    def __init__(
        self,
        rule_id: str,
        severity: str,
        message: str,
        cell_reference: str | None = None,
        expected_value: Any = None,
        actual_value: Any = None,
    ):
        self.rule_id = rule_id
        self.severity = severity
        self.message = message
        self.cell_reference = cell_reference
        self.expected_value = expected_value
        self.actual_value = actual_value

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "cell_reference": self.cell_reference,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
        }


# ---------------------------------------------------------------------------
# QCRule — 抽象基类
# ---------------------------------------------------------------------------

class QCRule(ABC):
    """QC规则抽象基类。"""

    severity: str  # "blocking" | "warning" | "info"
    rule_id: str   # "QC-01" ~ "QC-12"

    @abstractmethod
    async def check(self, context: QCContext) -> list[QCFindingItem]:
        """执行检查，返回发现列表。"""
        ...


# ---------------------------------------------------------------------------
# 12.2  阻断级规则 (3条) — stubs
# ---------------------------------------------------------------------------

class ConclusionNotEmptyRule(QCRule):
    """Rule 1: 结论区已填写（从 parsed_data 检查）。"""
    severity = "blocking"
    rule_id = "QC-01"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        wp = context.working_paper
        pd = wp.parsed_data or {}
        conclusion = pd.get("conclusion") or pd.get("conclusion_text") or ""
        if not conclusion.strip():
            return [QCFindingItem(
                rule_id=self.rule_id, severity=self.severity,
                description="底稿结论区为空，请填写审计结论",
                cell_reference="结论区",
            )]
        return []


class AIFillConfirmedRule(QCRule):
    """Rule 2: AI 填充内容全部已确认。"""
    severity = "blocking"
    rule_id = "QC-02"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        wp = context.working_paper
        pd = wp.parsed_data or {}
        ai_items = pd.get("ai_content", [])
        unconfirmed = [a for a in ai_items if a.get("status") == "pending"]
        if unconfirmed:
            return [QCFindingItem(
                rule_id=self.rule_id, severity=self.severity,
                description=f"存在 {len(unconfirmed)} 项未确认的 AI 生成内容",
                cell_reference=unconfirmed[0].get("cell_ref", ""),
            )]
        return []


class FormulaConsistencyRule(QCRule):
    """Rule 3: 审定数 = 未审数 + AJE + RJE（从 parsed_data 检查）。"""
    severity = "blocking"
    rule_id = "QC-03"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        wp = context.working_paper
        pd = wp.parsed_data or {}
        findings = []
        unadj = pd.get("unadjusted_amount")
        aje = pd.get("aje_adjustment", 0)
        rje = pd.get("rje_adjustment", 0)
        audited = pd.get("audited_amount")
        if unadj is not None and audited is not None:
            expected = float(unadj) + float(aje) + float(rje)
            if abs(float(audited) - expected) > 0.01:
                findings.append(QCFindingItem(
                    rule_id=self.rule_id, severity=self.severity,
                    description=f"审定数({audited})≠未审数({unadj})+AJE({aje})+RJE({rje})={expected:.2f}",
                    cell_reference="审定数",
                    expected_value=str(round(expected, 2)),
                    actual_value=str(audited),
                ))
        return findings


class ReviewerAssignedRule(QCRule):
    """Rule 4: 复核人已分配。"""
    severity = "blocking"
    rule_id = "QC-04"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        wp = context.working_paper
        if not wp.reviewer:
            return [QCFindingItem(
                rule_id=self.rule_id, severity=self.severity,
                description="复核人未分配，请先分配复核人再提交复核",
            )]
        return []


class UnresolvedAnnotationsRule(QCRule):
    """Rule 5: 无未解决的复核意见。"""
    severity = "blocking"
    rule_id = "QC-05"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        from app.models.phase10_models import CellAnnotation
        result = await context.db.execute(
            sa.select(sa.func.count()).select_from(CellAnnotation).where(
                CellAnnotation.project_id == context.project_id,
                CellAnnotation.object_type == "workpaper",
                CellAnnotation.object_id == context.working_paper.id,
                CellAnnotation.status != "resolved",
                CellAnnotation.is_deleted == sa.false(),
            )
        )
        count = result.scalar() or 0
        if count > 0:
            return [QCFindingItem(
                rule_id=self.rule_id, severity=self.severity,
                description=f"存在 {count} 条未解决的复核意见",
            )]
        return []


# ---------------------------------------------------------------------------
# 12.3  警告级规则 (8条) — stubs
# ---------------------------------------------------------------------------

class ManualInputCompleteRule(QCRule):
    """Rule 4: 人工填写区完整。"""
    severity = "warning"
    rule_id = "QC-04"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        return []


class SubtotalAccuracyRule(QCRule):
    """Rule 5: 内部合计数正确。"""
    severity = "warning"
    rule_id = "QC-05"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        return []


class CrossRefConsistencyRule(QCRule):
    """Rule 6: 交叉索引一致性。"""
    severity = "warning"
    rule_id = "QC-06"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        return []


class IndexRegistrationRule(QCRule):
    """Rule 7: 索引表登记。"""
    severity = "warning"
    rule_id = "QC-07"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        return []


class CrossRefExistsRule(QCRule):
    """Rule 8: 引用底稿存在。"""
    severity = "warning"
    rule_id = "QC-08"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        return []


class AuditProcedureStatusRule(QCRule):
    """Rule 9: 审计程序执行状态。"""
    severity = "warning"
    rule_id = "QC-09"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        return []


class SamplingCompletenessRule(QCRule):
    """Rule 10: 抽样记录完整。"""
    severity = "warning"
    rule_id = "QC-10"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        return []


class AdjustmentRecordedRule(QCRule):
    """Rule 11: 调整事项已录入。"""
    severity = "warning"
    rule_id = "QC-11"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        return []


# ---------------------------------------------------------------------------
# 12.4  提示级规则 (1条) — stub
# ---------------------------------------------------------------------------

class PreparationDateRule(QCRule):
    """Rule 12: 编制日期合理。"""
    severity = "info"
    rule_id = "QC-12"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        return []


# ---------------------------------------------------------------------------
# QCEngine
# ---------------------------------------------------------------------------

class QCEngine:
    """底稿质量自检引擎。

    Validates: Requirements 8.1, 8.2, 8.4
    """

    def __init__(self) -> None:
        self.rules: list[QCRule] = [
            # 阻断级
            ConclusionNotEmptyRule(),
            AIFillConfirmedRule(),
            FormulaConsistencyRule(),
            ReviewerAssignedRule(),
            UnresolvedAnnotationsRule(),
            # 警告级
            ManualInputCompleteRule(),
            SubtotalAccuracyRule(),
            CrossRefConsistencyRule(),
            IndexRegistrationRule(),
            CrossRefExistsRule(),
            AuditProcedureStatusRule(),
            SamplingCompletenessRule(),
            AdjustmentRecordedRule(),
            # 提示级
            PreparationDateRule(),
        ]

    async def check(
        self,
        db: AsyncSession,
        wp_id: UUID,
        checked_by: UUID | None = None,
    ) -> dict:
        """执行所有检查规则，汇总结果，存储到 wp_qc_results。

        Validates: Requirements 8.1, 8.2, 8.4
        """
        # Load working paper
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise ValueError("底稿不存在")

        # Load wp_index
        idx_result = await db.execute(
            sa.select(WpIndex).where(WpIndex.id == wp.wp_index_id)
        )
        idx = idx_result.scalar_one_or_none()

        # Build context
        context = QCContext(
            db=db,
            working_paper=wp,
            wp_index=idx,
            project_id=wp.project_id,
        )

        # Execute all rules
        all_findings: list[dict] = []
        blocking_count = 0
        warning_count = 0
        info_count = 0

        for rule in self.rules:
            try:
                findings = await rule.check(context)
                for f in findings:
                    all_findings.append(f.to_dict())
                    if f.severity == "blocking":
                        blocking_count += 1
                    elif f.severity == "warning":
                        warning_count += 1
                    elif f.severity == "info":
                        info_count += 1
            except Exception:
                logger.exception("QC rule %s failed", rule.rule_id)

        passed = blocking_count == 0
        now = datetime.now(timezone.utc)

        # Store result
        qc_result = WpQcResult(
            working_paper_id=wp_id,
            check_timestamp=now,
            findings=all_findings,
            passed=passed,
            blocking_count=blocking_count,
            warning_count=warning_count,
            info_count=info_count,
            checked_by=checked_by,
        )
        db.add(qc_result)
        await db.flush()

        return {
            "id": str(qc_result.id),
            "working_paper_id": str(wp_id),
            "check_timestamp": now.isoformat(),
            "findings": all_findings,
            "passed": passed,
            "blocking_count": blocking_count,
            "warning_count": warning_count,
            "info_count": info_count,
        }

    # ------------------------------------------------------------------
    # 12.5  get_project_summary
    # ------------------------------------------------------------------

    async def get_project_summary(
        self,
        db: AsyncSession,
        project_id: UUID,
    ) -> dict:
        """项目级QC汇总。

        Validates: Requirements 9.1
        """
        # Total workpapers
        total_result = await db.execute(
            sa.select(sa.func.count())
            .select_from(WpIndex)
            .where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == sa.false(),
            )
        )
        total_workpapers = total_result.scalar() or 0

        # Not started
        not_started_result = await db.execute(
            sa.select(sa.func.count())
            .select_from(WpIndex)
            .where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == sa.false(),
                WpIndex.status == WpStatus.not_started,
            )
        )
        not_started = not_started_result.scalar() or 0

        # Get all working papers with their latest QC results
        wp_result = await db.execute(
            sa.select(WorkingPaper.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
        wp_ids = [row[0] for row in wp_result.all()]

        passed_qc = 0
        has_blocking = 0
        not_checked = 0

        for wp_id in wp_ids:
            qc_result = await db.execute(
                sa.select(WpQcResult)
                .where(WpQcResult.working_paper_id == wp_id)
                .order_by(WpQcResult.check_timestamp.desc())
                .limit(1)
            )
            qc = qc_result.scalar_one_or_none()
            if qc is None:
                not_checked += 1
            elif qc.passed:
                passed_qc += 1
            else:
                has_blocking += 1

        pass_rate = 0.0
        denominator = total_workpapers - not_started
        if denominator > 0:
            pass_rate = round(passed_qc / denominator * 100, 1)

        return {
            "total_workpapers": total_workpapers,
            "passed_qc": passed_qc,
            "has_blocking": has_blocking,
            "not_started": not_started,
            "not_checked": not_checked,
            "pass_rate": pass_rate,
        }
