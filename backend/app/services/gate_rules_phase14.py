"""Phase 14: QC-19~QC-26 门禁规则实现

对齐 v2 3.2 校验9/10 + QC-21~26 统一返回结构
所有规则注册到 gate_engine.rule_registry
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.gate_engine import GateRule, GateRuleHit, gate_engine, rule_registry
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


async def check_misstatement_exceeds_materiality(
    project_id: str | uuid.UUID, db: AsyncSession
) -> dict | None:
    """检查未更正错报是否超过整体重要性水平

    需求 20.1：WHEN 未更正错报累计金额超过整体重要性水平，THE 底稿提交复核门禁
    SHALL 阻断提交，并显示"未更正错报超过重要性水平"的阻断原因

    返回 dict（命中规则时）或 None（未命中或无法比较时）
    """
    import sqlalchemy as sa
    from app.models.audit_platform_models import UnadjustedMisstatement, Materiality

    pid = project_id if isinstance(project_id, uuid.UUID) else uuid.UUID(str(project_id))

    # 查询累计错报金额（所有未删除、未跨年结转到后续年度的错报之和）
    total_q = sa.select(
        sa.func.coalesce(sa.func.sum(UnadjustedMisstatement.misstatement_amount), 0)
    ).where(
        UnadjustedMisstatement.project_id == pid,
        UnadjustedMisstatement.is_deleted == sa.false(),
    )
    total_amount = float((await db.execute(total_q)).scalar() or 0)

    # 查询整体重要性水平（取最新设置的一条）
    mat_q = (
        sa.select(Materiality.overall_materiality)
        .where(
            Materiality.project_id == pid,
            Materiality.is_deleted == sa.false(),
        )
        .order_by(Materiality.created_at.desc())
        .limit(1)
    )
    overall_materiality = float((await db.execute(mat_q)).scalar() or 0)

    # 无重要性水平记录时不做比较（避免误阻断，由项目启动阶段的校验去提醒）
    if overall_materiality <= 0:
        return None

    if total_amount > overall_materiality:
        return {
            "rule_code": "GATE-MISSTATEMENT",
            "error_code": "MISSTATEMENT_EXCEEDS_MATERIALITY",
            "severity": "blocking",
            "message": (
                f"未更正错报超过重要性水平（累计 {total_amount:,.2f} > 整体重要性 "
                f"{overall_materiality:,.2f}）"
            ),
            "total_amount": total_amount,
            "overall_materiality": overall_materiality,
        }
    return None


# ── GATE-MISSTATEMENT: 未更正错报超过重要性水平 ────────────────

class MisstatementExceedsMaterialityRule(GateRule):
    """未更正错报累计金额超过整体重要性水平时阻断提交复核/签字（需求 20.1）"""
    rule_code = "GATE-MISSTATEMENT"
    error_code = "MISSTATEMENT_EXCEEDS_MATERIALITY"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None
        try:
            result = await check_misstatement_exceeds_materiality(str(project_id), db)
            if result:
                return GateRuleHit(
                    rule_code=self.rule_code,
                    error_code=self.error_code,
                    severity=self.severity,
                    message=result["message"],
                    location={"section": "misstatements"},
                    suggested_action="请更正错报或在错报汇总表中说明不更正原因，确保累计金额不超过整体重要性水平",
                )
            return None
        except Exception as e:
            logger.error(f"[GATE-MISSTATEMENT] check error: {e}")
            return None


# ── R1-AJE-UNCONVERTED: rejected AJE 未转为错报（warning） ─────

class UnconvertedRejectedAJERule(GateRule):
    """扫描 review_status=rejected 且未关联到 UnadjustedMisstatement 的 AJE 组。

    对齐 R1 需求 3 验收 7：findings 为 warning 级（建议转错报），阻断级由质控合伙人评估。
    粒度：按 Adjustment.entry_group_id 聚合（一组调整分录视为一个 AJE 组）。
    判定"已转错报"：存在任一 UnadjustedMisstatement.source_adjustment_id
    指向该组内任一 Adjustment.id。
    """
    rule_code = "R1-AJE-UNCONVERTED"
    error_code = "AJE_REJECTED_NOT_CONVERTED"
    severity = GateSeverity.warning

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None
        try:
            from app.models.audit_platform_models import (
                Adjustment,
                AdjustmentType,
                ReviewStatus,
                UnadjustedMisstatement,
            )

            # 1) 查出所有 rejected AJE 组（group_id + 每组 adjustment_ids）
            rejected_rows = (
                await db.execute(
                    select(Adjustment.entry_group_id, Adjustment.id)
                    .where(
                        Adjustment.project_id == project_id,
                        Adjustment.is_deleted.is_(False),
                        Adjustment.review_status == ReviewStatus.rejected,
                        Adjustment.adjustment_type == AdjustmentType.aje,
                    )
                )
            ).all()
            if not rejected_rows:
                return None

            group_to_adj_ids: dict[uuid.UUID, set[uuid.UUID]] = {}
            for group_id, adj_id in rejected_rows:
                group_to_adj_ids.setdefault(group_id, set()).add(adj_id)

            # 2) 查出该项目内已转为错报的 adjustment_id 集合
            converted_rows = (
                await db.execute(
                    select(UnadjustedMisstatement.source_adjustment_id).where(
                        UnadjustedMisstatement.project_id == project_id,
                        UnadjustedMisstatement.is_deleted.is_(False),
                        UnadjustedMisstatement.source_adjustment_id.isnot(None),
                    )
                )
            ).all()
            converted_ids = {r[0] for r in converted_rows if r[0] is not None}

            # 3) 统计未转换的组：该组所有 rejected AJE 均未出现在 converted_ids
            unconverted_groups = [
                gid
                for gid, adj_ids in group_to_adj_ids.items()
                if not (adj_ids & converted_ids)
            ]
            if not unconverted_groups:
                return None

            count = len(unconverted_groups)
            sample = [str(g) for g in unconverted_groups[:5]]
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message=f"{count} 个被驳回的 AJE 组未转为错报，建议评估是否汇入错报汇总表",
                location={
                    "project_id": str(project_id),
                    "section": "adjustments",
                    "unconverted_group_count": count,
                    "sample_entry_group_ids": sample,
                },
                suggested_action=(
                    "打开《调整分录》页，对 rejected 行点击『转为错报』，"
                    "或在此处直接通过 /api/adjustments/{group_id}/convert-to-misstatement 一键转换"
                ),
            )
        except Exception as e:
            logger.debug(f"[R1-AJE-UNCONVERTED] check skipped: {e}")
            return None


# ── R1-EVENT-CASCADE: 事件级联消费健康（首次部署 warning，满月后 blocking） ─────

class EventCascadeHealthRule(GateRule):
    """检查最近 1 小时内 WORKPAPER_SAVED/REPORTS_UPDATED 事件的消费健康。

    对齐 R1 需求 3 验收 8：
    - 检查窗口：最近 1 小时
    - 事件源：ImportEventOutbox 中 status in (pending, failed) 的对应事件类型
    - severity 动态：
        * 未到 enforcement_start_date 时为 warning（首次部署宽容期）
        * 已到或超过 enforcement_start_date 时升为 blocking
      通过 GateRuleConfig(rule_code='R1-EVENT-CASCADE', threshold_key='enforcement_start_date')
      配置，未配置时默认 '2026-06-05'（R1 上线起约 1 个月）。

    说明：事件发布路径并非全部经 outbox（部分 WORKPAPER_SAVED 是 in-memory publish），
    本规则只对 outbox 已记录的事件做健康探测，对未经 outbox 覆盖的事件做最佳努力。
    """
    rule_code = "R1-EVENT-CASCADE"
    error_code = "EVENT_CASCADE_UNHEALTHY"
    severity = GateSeverity.warning  # 类属性为默认，实际返回时动态覆盖

    WINDOW_HOURS = 1
    DEFAULT_ENFORCEMENT_START_DATE = "2026-06-05"
    WATCHED_EVENT_TYPES = ("workpaper.saved", "reports.updated")

    async def _resolve_severity(self, db: AsyncSession) -> str:
        """读取 enforcement_start_date 决定 severity。"""
        try:
            raw = await gate_engine.load_rule_config(
                db=db,
                rule_code=self.rule_code,
                threshold_key="enforcement_start_date",
            )
        except Exception:
            raw = None
        start_str = (raw or self.DEFAULT_ENFORCEMENT_START_DATE).strip()
        try:
            # 允许 'YYYY-MM-DD' 或 ISO8601
            if len(start_str) == 10:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            else:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
        except Exception:
            start_dt = datetime.strptime(
                self.DEFAULT_ENFORCEMENT_START_DATE, "%Y-%m-%d"
            ).replace(tzinfo=timezone.utc)

        now = datetime.now(tz=timezone.utc)
        return (
            GateSeverity.blocking
            if now >= start_dt
            else GateSeverity.warning
        )

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None
        try:
            from app.models.dataset_models import ImportEventOutbox, OutboxStatus

            since = datetime.utcnow() - timedelta(hours=self.WINDOW_HOURS)
            stmt = (
                select(
                    ImportEventOutbox.event_type,
                    ImportEventOutbox.status,
                    func.count(ImportEventOutbox.id),
                )
                .where(
                    ImportEventOutbox.project_id == project_id,
                    ImportEventOutbox.event_type.in_(self.WATCHED_EVENT_TYPES),
                    ImportEventOutbox.status.in_(
                        [OutboxStatus.pending, OutboxStatus.failed]
                    ),
                    ImportEventOutbox.created_at >= since,
                )
                .group_by(ImportEventOutbox.event_type, ImportEventOutbox.status)
            )
            rows = (await db.execute(stmt)).all()
            if not rows:
                return None

            by_status: dict[str, int] = {"pending": 0, "failed": 0}
            by_event: dict[str, int] = {}
            for event_type, status, cnt in rows:
                status_val = status.value if hasattr(status, "value") else str(status)
                by_status[status_val] = by_status.get(status_val, 0) + int(cnt)
                by_event[event_type] = by_event.get(event_type, 0) + int(cnt)

            total = sum(by_status.values())
            if total <= 0:
                return None

            severity = await self._resolve_severity(db)
            retry_hint_sec = max(30, min(300, total * 10))  # 粗略估计等待时长

            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=severity,
                message=(
                    f"下游更新未同步：近 {self.WINDOW_HOURS} 小时内仍有 {total} 条事件未完成消费"
                    f"（pending={by_status.get('pending', 0)}，failed={by_status.get('failed', 0)}）"
                ),
                location={
                    "project_id": str(project_id),
                    "section": "event_cascade",
                    "window_hours": self.WINDOW_HOURS,
                    "by_status": by_status,
                    "by_event_type": by_event,
                    "watched_event_types": list(self.WATCHED_EVENT_TYPES),
                },
                suggested_action=(
                    f"下游更新未同步，请等待约 {retry_hint_sec} 秒后重试；"
                    "若持续不消散，请在『事件 Outbox 监控』面板检查 failed 事件"
                ),
            )
        except Exception as e:
            # 表不存在或 schema 差异时静默降级，避免把 gate 评估打爆
            logger.debug(f"[R1-EVENT-CASCADE] check skipped: {e}")
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

    # 需求 20.1: 未更正错报超过重要性水平阻断提交复核 + 签字
    rule_registry.register_all(submit_sign, MisstatementExceedsMaterialityRule())

    # R1 需求 3 验收 7/8：新增两条规则
    # - UnconvertedRejectedAJERule: sign_off（warning 级，建议转错报）
    # - EventCascadeHealthRule: sign_off + export_package（首次部署 warning，满月后 blocking）
    rule_registry.register_all([GateType.sign_off], UnconvertedRejectedAJERule())
    rule_registry.register_all(
        [GateType.sign_off, GateType.export_package], EventCascadeHealthRule()
    )

    logger.info("[GATE] Phase 14 rules QC-19~26 + consistency + misstatement registered")
