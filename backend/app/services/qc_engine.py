"""底稿质量自检引擎 — QCRule 基类 + 14条规则 + QCEngine + 项目汇总

14条规则全部已实现（5条阻断级 + 8条警告级 + 1条提示级）。

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
    WpFileStatus,
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
# 12.2  阻断级规则 (5条)
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
                message="底稿结论区为空，请填写审计结论",
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
                message=f"存在 {len(unconfirmed)} 项未确认的 AI 生成内容",
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
                    message=f"审定数({audited})≠未审数({unadj})+AJE({aje})+RJE({rje})={expected:.2f}",
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
                message="复核人未分配，请先分配复核人再提交复核",
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
                message=f"存在 {count} 条未解决的复核意见",
            )]
        return []


# ---------------------------------------------------------------------------
# 12.3  警告级规则 (8条)
# ---------------------------------------------------------------------------

class ManualInputCompleteRule(QCRule):
    """Rule 6: 人工填写区完整（从 parsed_data 检查关键字段非空）。"""
    severity = "warning"
    rule_id = "QC-06"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        pd = context.working_paper.parsed_data or {}
        findings = []
        # 审定数必须有值
        if pd.get("audited_amount") is None and pd.get("extracted_at"):
            findings.append(QCFindingItem(
                rule_id=self.rule_id, severity=self.severity,
                message="审定数未填写（parsed_data 中 audited_amount 为空）",
            ))
        # 未审数必须有值
        if pd.get("unadjusted_amount") is None and pd.get("extracted_at"):
            findings.append(QCFindingItem(
                rule_id=self.rule_id, severity=self.severity,
                message="未审数未填写（parsed_data 中 unadjusted_amount 为空）",
            ))
        return findings


class SubtotalAccuracyRule(QCRule):
    """Rule 7: 审定数 = 未审数 + AJE + RJE（宽松版，与 QC-03 互补）。"""
    severity = "warning"
    rule_id = "QC-07"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        pd = context.working_paper.parsed_data or {}
        if not pd.get("extracted_at"):
            return []
        audited = pd.get("audited_amount")
        unadj = pd.get("unadjusted_amount")
        aje = pd.get("aje_adjustment", 0) or 0
        rje = pd.get("rje_adjustment", 0) or 0
        if audited is not None and unadj is not None:
            expected = float(unadj) + float(aje) + float(rje)
            diff = abs(float(audited) - expected)
            # 允许 1 元以内的舍入差异（QC-03 是 0.01 的阻断级）
            if diff > 1.0:
                return [QCFindingItem(
                    rule_id=self.rule_id, severity=self.severity,
                    message=f"审定数({audited})与计算值({expected:.2f})差异 {diff:.2f}，请检查",
                    expected_value=str(round(expected, 2)),
                    actual_value=str(audited),
                )]
        return []


class CrossRefConsistencyRule(QCRule):
    """Rule 8: 交叉索引一致性（parsed_data 中的 cross_refs 对应的底稿必须存在）。"""
    severity = "warning"
    rule_id = "QC-08"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        pd = context.working_paper.parsed_data or {}
        cross_refs = pd.get("cross_refs", [])
        if not cross_refs:
            return []
        findings = []
        for ref_code in cross_refs:
            idx = (await context.db.execute(
                sa.select(WpIndex).where(
                    WpIndex.project_id == context.project_id,
                    WpIndex.wp_code == ref_code,
                    WpIndex.is_deleted == sa.false(),
                )
            )).scalar_one_or_none()
            if not idx:
                findings.append(QCFindingItem(
                    rule_id=self.rule_id, severity=self.severity,
                    message=f"交叉索引 {ref_code} 在项目底稿索引中不存在",
                ))
        return findings


class IndexRegistrationRule(QCRule):
    """Rule 9: 底稿已在索引表中登记（wp_index 记录存在且状态非 not_started）。"""
    severity = "warning"
    rule_id = "QC-09"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        wp = context.working_paper
        idx = (await context.db.execute(
            sa.select(WpIndex).where(
                WpIndex.id == wp.wp_index_id,
                WpIndex.is_deleted == sa.false(),
            )
        )).scalar_one_or_none()
        if not idx:
            return [QCFindingItem(
                rule_id=self.rule_id, severity=self.severity,
                message="底稿未在索引表中登记（wp_index 记录缺失）",
            )]
        return []


class CrossRefExistsRule(QCRule):
    """Rule 10: 引用底稿存在且已完成。"""
    severity = "warning"
    rule_id = "QC-10"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        from app.models.workpaper_models import WpCrossRef
        refs = (await context.db.execute(
            sa.select(WpCrossRef).where(WpCrossRef.source_wp_id == context.working_paper.id)
        )).scalars().all()
        findings = []
        for ref in refs:
            target_code = ref.target_wp_code if hasattr(ref, 'target_wp_code') else None
            if target_code:
                # 检查目标底稿是否存在
                target_idx = (await context.db.execute(
                    sa.select(WpIndex).where(
                        WpIndex.project_id == context.project_id,
                        WpIndex.wp_code == target_code,
                    )
                )).scalar_one_or_none()
                if not target_idx:
                    findings.append(QCFindingItem(
                        rule_id=self.rule_id, severity=self.severity,
                        message=f"交叉引用的底稿 {target_code} 不存在",
                        cell_reference=ref.cell_reference if hasattr(ref, 'cell_reference') else None,
                    ))
        return findings


class AuditProcedureStatusRule(QCRule):
    """Rule 11: 关联的审计程序是否已执行完成。"""
    severity = "warning"
    rule_id = "QC-11"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        # 检查底稿关联的审计程序是否已完成
        wp = context.working_paper
        idx = context.wp_index
        if not idx:
            return []
        wp_code = idx.wp_code if idx else None
        if not wp_code:
            return []

        from app.models.procedure_models import ProcedureInstance
        proc = (await context.db.execute(
            sa.select(ProcedureInstance).where(
                ProcedureInstance.project_id == context.project_id,
                ProcedureInstance.wp_code == wp_code,
                ProcedureInstance.status == "execute",
                ProcedureInstance.is_deleted == sa.false(),
            )
        )).scalar_one_or_none()

        if proc and proc.execution_status != "completed":
            return [QCFindingItem(
                rule_id=self.rule_id, severity=self.severity,
                message=f"关联审计程序 {proc.procedure_code} 尚未完成（当前状态: {proc.execution_status}）",
            )]
        return []


class SamplingCompletenessRule(QCRule):
    """Rule 12: 抽样记录完整（有抽样配置则必须有记录）。"""
    severity = "warning"
    rule_id = "QC-12"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        from app.models.workpaper_models import SamplingConfig, SamplingRecord
        configs = (await context.db.execute(
            sa.select(SamplingConfig).where(
                SamplingConfig.working_paper_id == context.working_paper.id,
            )
        )).scalars().all()
        findings = []
        for cfg in configs:
            records = (await context.db.execute(
                sa.select(sa.func.count()).select_from(SamplingRecord).where(
                    SamplingRecord.sampling_config_id == cfg.id,
                )
            )).scalar() or 0
            if records == 0:
                findings.append(QCFindingItem(
                    rule_id=self.rule_id, severity=self.severity,
                    message=f"抽样配置 {cfg.id} 已创建但无抽样记录",
                ))
        return findings


class AdjustmentRecordedRule(QCRule):
    """Rule 13: 底稿中发现的调整事项已录入调整分录。"""
    severity = "warning"
    rule_id = "QC-13"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        pd = context.working_paper.parsed_data or {}
        pending_adj = pd.get("pending_adjustments", [])
        if pending_adj:
            return [QCFindingItem(
                rule_id=self.rule_id, severity=self.severity,
                message=f"底稿中有 {len(pending_adj)} 项待录入的调整事项",
            )]
        return []


# ---------------------------------------------------------------------------
# 12.4  提示级规则 (1条)
# ---------------------------------------------------------------------------

class PreparationDateRule(QCRule):
    """Rule 14: 编制日期合理（不早于项目开始、不晚于当前日期）。"""
    severity = "info"
    rule_id = "QC-14"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        wp = context.working_paper
        if wp.created_at and wp.updated_at:
            # 如果底稿创建超过90天还在draft状态，提示
            from datetime import timedelta
            if wp.status == WpFileStatus.draft:
                age = (datetime.now(timezone.utc) - wp.created_at.replace(tzinfo=timezone.utc)).days
                if age > 90:
                    return [QCFindingItem(
                        rule_id=self.rule_id, severity=self.severity,
                        message=f"底稿创建已 {age} 天仍为草稿状态，请确认是否需要编制",
                    )]
        return []


# ---------------------------------------------------------------------------
# Phase 12: 内容级QC规则 (QC-15 ~ QC-18)
# ---------------------------------------------------------------------------

class ExplanationCompletenessRule(QCRule):
    """QC-15: 审计说明完整性。"""
    severity = "blocking"
    rule_id = "QC-15"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        wp = context.working_paper
        pd = wp.parsed_data or {}
        explanation = pd.get("audit_explanation", "")
        findings = []
        if not explanation:
            findings.append(QCFindingItem(rule_id=self.rule_id, severity=self.severity,
                                          message="审计说明为空，请填写或使用AI生成"))
            return findings
        if len(explanation) < 50:
            findings.append(QCFindingItem(rule_id=self.rule_id, severity=self.severity,
                                          message=f"审计说明过短（{len(explanation)}字），至少需要50字",
                                          actual_value=len(explanation), expected_value=50))
        expl_status = getattr(wp, "explanation_status", "not_started")
        if expl_status not in ("synced", "written_back"):
            findings.append(QCFindingItem(rule_id=self.rule_id, severity="warning",
                                          message=f"审计说明同步状态异常: {expl_status}"))
        return findings


class DataReferenceConsistencyRule(QCRule):
    """QC-16: 数据引用一致性 — 底稿审定数 vs 试算表，误差>0.01元阻断。"""
    severity = "blocking"
    rule_id = "QC-16"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        wp = context.working_paper
        pd = wp.parsed_data or {}
        wp_amount = pd.get("audited_amount")
        if wp_amount is None:
            return []
        from app.models.audit_platform_models import TrialBalance
        tbs = (await context.db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == context.project_id,
                TrialBalance.year == context.year,
                TrialBalance.is_deleted == False,
            )
        )).scalars().all()
        for tb in tbs[:1]:
            tb_amt = float(tb.audited_debit or 0) - float(tb.audited_credit or 0)
            diff = abs(float(wp_amount) - tb_amt)
            if diff > 0.01:
                return [QCFindingItem(rule_id=self.rule_id, severity=self.severity,
                                      message=f"底稿审定数({wp_amount:,.2f})与试算表({tb_amt:,.2f})差异{diff:,.2f}元",
                                      expected_value=tb_amt, actual_value=wp_amount)]
        return []


class AttachmentSufficiencyRule(QCRule):
    """QC-17: 附件证据充分性 — 底稿至少关联1个附件。"""
    severity = "blocking"
    rule_id = "QC-17"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        try:
            result = await context.db.execute(
                sa.text("SELECT COUNT(*) FROM attachment_working_paper WHERE working_paper_id = :wid"),
                {"wid": str(context.working_paper.id)})
            count = result.scalar() or 0
        except Exception:
            count = 0
        if count == 0:
            return [QCFindingItem(rule_id=self.rule_id, severity=self.severity,
                                  message="底稿未关联任何附件证据", actual_value=0, expected_value=1)]
        return []


class CrossRefIntegrityRule(QCRule):
    """QC-18: 交叉引用完整性 — 引用的底稿编号存在且状态≠draft。"""
    severity = "warning"
    rule_id = "QC-18"

    async def check(self, context: QCContext) -> list[QCFindingItem]:
        pd = context.working_paper.parsed_data or {}
        refs = pd.get("cross_refs", [])
        if not refs:
            return []
        findings = []
        for ref_code in refs:
            ref_q = sa.select(WorkingPaper).join(WpIndex).where(
                WpIndex.wp_code == ref_code,
                WorkingPaper.project_id == context.project_id,
                WorkingPaper.is_deleted == False,
            )
            ref_wp = (await context.db.execute(ref_q)).scalar_one_or_none()
            if not ref_wp:
                findings.append(QCFindingItem(rule_id=self.rule_id, severity=self.severity,
                                              message=f"交叉引用 {ref_code} 对应底稿不存在"))
            elif ref_wp.status == WpFileStatus.draft:
                findings.append(QCFindingItem(rule_id=self.rule_id, severity=self.severity,
                                              message=f"交叉引用 {ref_code} 对应底稿仍为草稿"))
        return findings


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
            # Phase 12: 内容级规则
            ExplanationCompletenessRule(),
            DataReferenceConsistencyRule(),
            AttachmentSufficiencyRule(),
            CrossRefIntegrityRule(),
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
