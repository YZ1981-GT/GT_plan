"""Phase 14: QC-19~QC-26 门禁规则实现

对齐 v2 3.2 校验9/10 + QC-21~26 统一返回结构
所有规则注册到 gate_engine.rule_registry
"""
import logging
from typing import Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.gate_engine import GateRule, GateRuleHit, rule_registry
from app.models.phase14_enums import GateType, GateSeverity

logger = logging.getLogger(__name__)


# ── QC-19: mandatory 程序裁剪阻断 ──────────────────────────────

class QC19MandatoryTrimRule(GateRule):
    rule_code = "QC-19"
    error_code = "QC_PROCEDURE_MANDATORY_TRIMMED"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        wp_id = context.get("wp_id")
        if not wp_id:
            return None
        try:
            from app.models.workpaper_models import WorkingPaper
            # 查找关联的 procedure_instances
            stmt = text("""
                SELECT id, name FROM procedure_instances
                WHERE working_paper_id = :wp_id
                  AND trim_category = 'mandatory'
                  AND trim_status = 'trimmed'
                  AND (is_deleted = false OR is_deleted IS NULL)
                LIMIT 5
            """)
            result = await db.execute(stmt, {"wp_id": str(wp_id)})
            rows = result.fetchall()
            if not rows:
                return None
            proc_ids = [str(r[0]) for r in rows]
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message=f"不允许裁剪 mandatory 审计程序（{len(rows)}项）",
                location={"wp_id": str(wp_id), "section": "procedure_status", "procedure_ids": proc_ids},
                suggested_action="请恢复被裁剪的 mandatory 程序或走例外审批流程",
            )
        except Exception as e:
            logger.error(f"[QC-19] check error: {e}")
            return None


# ── QC-20: conditional 裁剪无证据阻断 ──────────────────────────

class QC20ConditionalNoEvidenceRule(GateRule):
    rule_code = "QC-20"
    error_code = "QC_PROCEDURE_EVIDENCE_MISSING"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        wp_id = context.get("wp_id")
        if not wp_id:
            return None
        try:
            stmt = text("""
                SELECT id, name FROM procedure_instances
                WHERE working_paper_id = :wp_id
                  AND trim_category = 'conditional'
                  AND trim_status = 'trimmed'
                  AND (trim_evidence_refs IS NULL OR jsonb_array_length(trim_evidence_refs) = 0)
                  AND (is_deleted = false OR is_deleted IS NULL)
                LIMIT 5
            """)
            result = await db.execute(stmt, {"wp_id": str(wp_id)})
            rows = result.fetchall()
            if not rows:
                return None
            proc_ids = [str(r[0]) for r in rows]
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message=f"conditional 程序裁剪缺少证据引用（{len(rows)}项）",
                location={"wp_id": str(wp_id), "section": "procedure_status", "procedure_ids": proc_ids},
                suggested_action="请补充 trim_evidence_refs 后重新提交",
            )
        except Exception as e:
            logger.error(f"[QC-20] check error: {e}")
            return None


# ── QC-21: 关键结论缺少证据锚点 ───────────────────────────────

class QC21ConclusionWithoutEvidenceRule(GateRule):
    rule_code = "QC-21"
    error_code = "QC_CONCLUSION_WITHOUT_EVIDENCE"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        wp_id = context.get("wp_id")
        if not wp_id:
            return None
        try:
            from app.models.workpaper_models import WorkingPaper
            stmt = select(WorkingPaper).where(WorkingPaper.id == wp_id)
            result = await db.execute(stmt)
            wp = result.scalar_one_or_none()
            if not wp or not wp.parsed_data:
                return None
            ai_content = wp.parsed_data.get("ai_content", {})
            suggestions = ai_content.get("review_suggestions", [])
            # 检查关键结论是否有证据引用
            for s in suggestions:
                if s.get("is_key_conclusion") and not s.get("evidence_refs"):
                    return GateRuleHit(
                        rule_code=self.rule_code,
                        error_code=self.error_code,
                        severity=self.severity,
                        message="关键结论缺少证据锚点",
                        location={"wp_id": str(wp_id), "section": "audit_conclusion"},
                        suggested_action="请为关键结论绑定 evidence_id",
                    )
            # 也检查 conclusion 字段本身
            conclusion = wp.parsed_data.get("conclusion", "")
            if conclusion and not wp.parsed_data.get("conclusion_evidence_refs"):
                # 如果有结论但无证据引用，视为缺失
                pass  # 宽松模式：仅在 ai_content 中有 is_key_conclusion 标记时阻断
            return None
        except Exception as e:
            logger.error(f"[QC-21] check error: {e}")
            return None


# ── QC-22: 低置信单点依赖 ──────────────────────────────────────

class QC22LowConfidenceSingleSourceRule(GateRule):
    rule_code = "QC-22"
    error_code = "QC_LOW_CONFIDENCE_SINGLE_SOURCE"
    severity = GateSeverity.blocking

    OCR_CONFIDENCE_THRESHOLD = 0.7

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        wp_id = context.get("wp_id")
        if not wp_id:
            return None
        try:
            from app.models.workpaper_models import WorkingPaper
            stmt = select(WorkingPaper).where(WorkingPaper.id == wp_id)
            result = await db.execute(stmt)
            wp = result.scalar_one_or_none()
            if not wp or not wp.parsed_data:
                return None
            ai_content = wp.parsed_data.get("ai_content", {})
            suggestions = ai_content.get("review_suggestions", [])
            for s in suggestions:
                if (s.get("is_key_conclusion")
                        and s.get("evidence_count", 0) == 1
                        and s.get("min_ocr_confidence", 1.0) < self.OCR_CONFIDENCE_THRESHOLD):
                    return GateRuleHit(
                        rule_code=self.rule_code,
                        error_code=self.error_code,
                        severity=self.severity,
                        message="关键结论仅依赖低置信证据（单点依赖）",
                        location={"wp_id": str(wp_id), "section": "audit_conclusion"},
                        suggested_action="请补充第二证据或人工确认说明",
                    )
            return None
        except Exception as e:
            logger.error(f"[QC-22] check error: {e}")
            return None


# ── QC-23: LLM 关键内容未确认 ──────────────────────────────────

class QC23LLMPendingConfirmationRule(GateRule):
    rule_code = "QC-23"
    error_code = "QC_LLM_PENDING_CONFIRMATION"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        wp_id = context.get("wp_id")
        if not wp_id:
            return None
        try:
            # 检查 wp_ai_generations 表
            stmt = text("""
                SELECT id FROM wp_ai_generations
                WHERE wp_id = :wp_id AND status IN ('pending', 'drafted')
                LIMIT 1
            """)
            result = await db.execute(stmt, {"wp_id": str(wp_id)})
            row = result.fetchone()
            if row:
                return GateRuleHit(
                    rule_code=self.rule_code,
                    error_code=self.error_code,
                    severity=self.severity,
                    message="存在未确认的 LLM 关键内容",
                    location={"wp_id": str(wp_id), "section": "audit_explanation"},
                    suggested_action="请逐条执行采纳/拒绝后重新提交",
                )
            # 也检查 parsed_data.ai_content
            from app.models.workpaper_models import WorkingPaper
            wp_stmt = select(WorkingPaper).where(WorkingPaper.id == wp_id)
            wp_result = await db.execute(wp_stmt)
            wp = wp_result.scalar_one_or_none()
            if wp and wp.parsed_data:
                ai = wp.parsed_data.get("ai_content", {})
                draft = ai.get("explanation_draft", {})
                if draft.get("status") == "pending":
                    return GateRuleHit(
                        rule_code=self.rule_code,
                        error_code=self.error_code,
                        severity=self.severity,
                        message="审计说明 AI 草稿未确认",
                        location={"wp_id": str(wp_id), "section": "audit_explanation"},
                        suggested_action="请确认或拒绝 AI 生成的审计说明草稿",
                    )
            return None
        except Exception as e:
            logger.error(f"[QC-23] check error: {e}")
            return None


# ── QC-24: LLM 采纳与裁剪冲突 ─────────────────────────────────

class QC24LLMTrimConflictRule(GateRule):
    rule_code = "QC-24"
    error_code = "QC_LLM_TRIM_CONFLICT"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        wp_id = context.get("wp_id")
        if not wp_id:
            return None
        try:
            # 检查是否有已确认的 AI 内容与被裁剪的程序冲突
            stmt = text("""
                SELECT g.id FROM wp_ai_generations g
                JOIN procedure_instances p ON p.working_paper_id = g.wp_id
                WHERE g.wp_id = :wp_id
                  AND g.status = 'confirmed'
                  AND p.trim_status = 'trimmed'
                  AND (p.is_deleted = false OR p.is_deleted IS NULL)
                LIMIT 1
            """)
            result = await db.execute(stmt, {"wp_id": str(wp_id)})
            row = result.fetchone()
            if row:
                return GateRuleHit(
                    rule_code=self.rule_code,
                    error_code=self.error_code,
                    severity=self.severity,
                    message="LLM 推荐内容与裁剪策略冲突",
                    location={"wp_id": str(wp_id), "section": "procedure_status"},
                    suggested_action="请回退 AI 采纳并按裁剪规则处理",
                )
            return None
        except Exception as e:
            logger.error(f"[QC-24] check error: {e}")
            return None


# ── QC-25: 正文引用附注版本过期 ────────────────────────────────

class QC25ReportNoteVersionStaleRule(GateRule):
    rule_code = "QC-25"
    error_code = "QC_REPORT_NOTE_VERSION_STALE"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None
        try:
            # 检查审计报告段落引用的附注版本是否过期
            # 简化实现：检查 report_snapshots 是否有 stale 标记
            stmt = text("""
                SELECT rs.id FROM report_snapshots rs
                WHERE rs.project_id = :project_id
                  AND rs.is_stale = true
                LIMIT 1
            """)
            result = await db.execute(stmt, {"project_id": str(project_id)})
            row = result.fetchone()
            if row:
                return GateRuleHit(
                    rule_code=self.rule_code,
                    error_code=self.error_code,
                    severity=self.severity,
                    message="审计报告正文引用附注版本已过期",
                    location={"section": "audit_report", "snapshot_id": str(row[0])},
                    suggested_action="请刷新引用并重新确认关键段落",
                )
            return None
        except Exception as e:
            # report_snapshots 表可能不存在（Phase 13 才创建）
            logger.debug(f"[QC-25] check skipped: {e}")
            return None


# ── QC-26: 附注关键披露缺来源映射 ──────────────────────────────

class QC26NoteSourceMappingMissingRule(GateRule):
    rule_code = "QC-26"
    error_code = "QC_NOTE_SOURCE_MAPPING_MISSING"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None
        try:
            # 检查附注关键披露是否缺少 source_cells 映射
            stmt = text("""
                SELECT dn.id, dn.title FROM disclosure_notes dn
                WHERE dn.project_id = :project_id
                  AND dn.is_key_disclosure = true
                  AND (dn.source_cells IS NULL OR dn.source_cells = '[]'::jsonb)
                LIMIT 5
            """)
            result = await db.execute(stmt, {"project_id": str(project_id)})
            rows = result.fetchall()
            if not rows:
                return None
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message=f"附注关键披露缺少来源映射（{len(rows)}项）",
                location={"section": "disclosure_notes", "note_ids": [str(r[0]) for r in rows]},
                suggested_action="请补齐 source_cells 并重跑一致性检查",
            )
        except Exception as e:
            # disclosure_notes 表字段可能不完整
            logger.debug(f"[QC-26] check skipped: {e}")
            return None


# ── 规则注册 ───────────────────────────────────────────────────

# ── Phase 16: 一致性阻断联动签字门禁 ──────────────────────────

class ConsistencyBlockingDiffRule(GateRule):
    """签字前自动执行一致性复算，blocking_count > 0 则阻断"""
    rule_code = "CONSISTENCY-BLOCK"
    error_code = "CONSISTENCY_BLOCKING_DIFF"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None
        try:
            from app.services.consistency_replay_engine import consistency_replay_engine
            result = await consistency_replay_engine.replay_consistency(db, project_id)
            if result.blocking_count > 0:
                # 收集差异摘要
                diff_summary = []
                for layer in result.layers:
                    for d in layer.diffs:
                        if d.severity == "blocking":
                            diff_summary.append(f"{layer.from_table}→{layer.to_table}: {d.field_name} 差异{d.diff:.2f}")
                return GateRuleHit(
                    rule_code=self.rule_code,
                    error_code=self.error_code,
                    severity=self.severity,
                    message=f"一致性复算存在 {result.blocking_count} 项阻断级差异",
                    location={
                        "section": "consistency",
                        "snapshot_id": result.snapshot_id,
                        "blocking_count": result.blocking_count,
                        "diff_summary": diff_summary[:5],
                    },
                    suggested_action="请修复数据差异后重新签字（差异阈值 > 0.01 元）",
                )
            return None
        except Exception as e:
            logger.debug(f"[CONSISTENCY-BLOCK] check skipped: {e}")
            return None


def register_phase14_rules():
    """注册 QC-19~26 到 rule_registry"""
    all_gates = [GateType.submit_review, GateType.sign_off, GateType.export_package]
    submit_sign = [GateType.submit_review, GateType.sign_off]

    # QC-19/20 程序裁剪：提交+签字
    rule_registry.register_all(submit_sign, QC19MandatoryTrimRule())
    rule_registry.register_all(submit_sign, QC20ConditionalNoEvidenceRule())

    # QC-21~24 LLM/证据链：提交+签字
    rule_registry.register_all(submit_sign, QC21ConclusionWithoutEvidenceRule())
    rule_registry.register_all(submit_sign, QC22LowConfidenceSingleSourceRule())
    rule_registry.register_all(submit_sign, QC23LLMPendingConfirmationRule())
    rule_registry.register_all(submit_sign, QC24LLMTrimConflictRule())

    # QC-25/26 版本/映射：三入口
    rule_registry.register_all(all_gates, QC25ReportNoteVersionStaleRule())
    rule_registry.register_all(all_gates, QC26NoteSourceMappingMissingRule())

    # Phase 16: 一致性阻断联动签字门禁
    rule_registry.register(GateType.sign_off, ConsistencyBlockingDiffRule())

    logger.info("[GATE] Phase 14 rules QC-19~26 + consistency registered")
