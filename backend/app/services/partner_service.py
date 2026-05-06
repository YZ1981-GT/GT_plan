"""合伙人视角服务 — 多项目风控总览 / 关键审计事项 / 签字前检查 / 团队效能"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, ProjectStatus, User
from app.models.workpaper_models import WorkingPaper, WpFileStatus, WpReviewStatus, WpIndex, WpQcResult
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour

_logger = logging.getLogger(__name__)


class PartnerOverviewService:
    """合伙人全局总览 — 我负责的所有项目一览"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_my_projects_overview(self, user_id: uuid.UUID) -> dict[str, Any]:
        """
        合伙人看到的：
        - 我负责的项目列表（含进度/风险/关键指标）
        - 跨项目风险预警
        - 待我签字的项目
        """
        # 获取合伙人关联的项目（通过 project_assignments 或 project_users）
        assignment_q = (
            select(ProjectAssignment.project_id)
            .where(
                ProjectAssignment.staff_id.in_(
                    select(StaffMember.id).where(StaffMember.user_id == user_id)
                ),
                ProjectAssignment.is_deleted == False,
            )
        )
        assigned_pids = [r[0] for r in (await self.db.execute(assignment_q)).all()]

        # 也查 project 表的 created_by（合伙人可能是项目创建者）
        created_q = select(Project.id).where(
            Project.created_by == user_id, Project.is_deleted == False,
        )
        created_pids = [r[0] for r in (await self.db.execute(created_q)).all()]

        all_pids = list(set(assigned_pids + created_pids))

        if not all_pids:
            # 如果是 admin，返回所有项目
            user = (await self.db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user and user.role == "admin":
                all_pids_q = select(Project.id).where(Project.is_deleted == False).limit(50)
                all_pids = [r[0] for r in (await self.db.execute(all_pids_q)).all()]

        projects = []
        risk_alerts = []
        pending_sign = []

        for pid in all_pids:
            proj = (await self.db.execute(select(Project).where(Project.id == pid))).scalar_one_or_none()
            if not proj:
                continue

            # 底稿统计
            wp_base = [WorkingPaper.project_id == pid, WorkingPaper.is_deleted == False]
            wp_total = (await self.db.execute(select(func.count()).select_from(WorkingPaper).where(*wp_base))).scalar() or 0
            wp_passed = (await self.db.execute(select(func.count()).select_from(WorkingPaper).where(
                *wp_base, WorkingPaper.status.in_([WpFileStatus.review_passed, WpFileStatus.archived])
            ))).scalar() or 0
            wp_pending = (await self.db.execute(select(func.count()).select_from(WorkingPaper).where(
                *wp_base, WorkingPaper.review_status.in_([WpReviewStatus.pending_level1, WpReviewStatus.pending_level2])
            ))).scalar() or 0
            wp_rejected = (await self.db.execute(select(func.count()).select_from(WorkingPaper).where(
                *wp_base, WorkingPaper.review_status.in_([WpReviewStatus.level1_rejected, WpReviewStatus.level2_rejected])
            ))).scalar() or 0

            completion_rate = round(wp_passed / wp_total * 100, 1) if wp_total > 0 else 0

            # 风险判断
            risk_level = "low"
            risk_reasons = []
            if wp_rejected > 3:
                risk_level = "high"
                risk_reasons.append(f"{wp_rejected} 个底稿被退回")
            elif wp_rejected > 0:
                risk_level = "medium"
                risk_reasons.append(f"{wp_rejected} 个底稿被退回")

            if completion_rate < 30 and wp_total > 10:
                risk_level = "high" if risk_level != "high" else risk_level
                risk_reasons.append(f"完成率仅 {completion_rate}%")

            # 项目创建超过120天还没完成
            if proj.created_at:
                age = (datetime.utcnow() - proj.created_at.replace(tzinfo=timezone.utc)).days
                if age > 120 and proj.status not in ("archived", "reporting"):
                    risk_level = "medium" if risk_level == "low" else risk_level
                    risk_reasons.append(f"项目已进行 {age} 天")

            project_info = {
                "id": str(pid),
                "name": proj.name,
                "client_name": proj.client_name,
                "status": proj.status,
                "wp_total": wp_total,
                "wp_passed": wp_passed,
                "wp_pending": wp_pending,
                "wp_rejected": wp_rejected,
                "completion_rate": completion_rate,
                "risk_level": risk_level,
                "risk_reasons": risk_reasons,
            }
            projects.append(project_info)

            if risk_level in ("high", "medium"):
                risk_alerts.append(project_info)

            # 待签字：所有底稿复核通过 + 报告已生成
            if completion_rate >= 95 and proj.status in ("completion", "reporting"):
                pending_sign.append(project_info)

        projects.sort(key=lambda x: ({"high": 0, "medium": 1, "low": 2}[x["risk_level"]], -x["completion_rate"]))

        return {
            "projects": projects,
            "total_projects": len(projects),
            "risk_alerts": risk_alerts,
            "risk_alert_count": len(risk_alerts),
            "pending_sign": pending_sign,
            "pending_sign_count": len(pending_sign),
        }


class SignReadinessService:
    """签字前检查 — 合伙人签字前必须确认的事项"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_sign_readiness(
        self,
        project_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """R1 Task 7 门面化：内部调 gate_engine.evaluate('sign_off')，
        hit_rules 按 rule_code 映射到原有 8 项 UI 类目；gate 尚未覆盖的
        类目（复核通过率/KAM/独立性等）通过 ``extra_findings`` 补齐。

        返回统一 schema（见 :mod:`app.services.readiness_facade`）：
        ``{ready, groups, gate_eval_id, expires_at, checks(legacy), ...}``

        Parameters
        ----------
        project_id : 项目 UUID
        actor_id : 可选调用人（用于 trace_event 留痕）；未传时尝试
            回落到 ``Project.created_by``，若项目也不存在则用 system
            placeholder UUID（不会阻断 gate 评估）。
        """
        from app.services.gate_engine import gate_engine
        from app.services.gate_eval_store import store_gate_eval
        from app.services.readiness_facade import build_readiness_response

        # 若调用方未给 actor，兜底走 project.created_by
        resolved_actor = actor_id
        proj = (
            await self.db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if resolved_actor is None and proj is not None:
            resolved_actor = proj.created_by
        if resolved_actor is None:
            # 不应发生，但兜底：随机 UUID 仅用于 trace，不代表任何人
            resolved_actor = uuid.uuid4()
            _logger.warning(
                "[sign_readiness] actor_id 缺失，已生成占位符 actor=%s project=%s",
                resolved_actor,
                project_id,
            )

        # 1) 执行 sign_off gate
        gate_result = await gate_engine.evaluate(
            db=self.db,
            gate_type="sign_off",
            project_id=project_id,
            wp_id=None,
            actor_id=resolved_actor,
            context={},
        )

        # 2) 计算 gate 未覆盖的"业务类目"信号，作为 extra_findings
        extra = await self._compute_sign_extra_findings(project_id, proj)

        # 3) 生成 gate_eval_id（5 分钟 TTL）
        gate_decision = str(gate_result.decision)
        has_blocking = any(
            f["severity"] == "blocking"
            for items in extra.values()
            for f in items
        ) or any(
            str(getattr(h, "severity", "")) == "blocking"
            for h in (gate_result.hit_rules or [])
        )
        ready_flag = (gate_decision != "block") and (not has_blocking)

        eval_id, expires_at = await store_gate_eval(
            project_id=project_id,
            gate_type="sign_off",
            ready=ready_flag,
            decision=gate_decision,
        )

        # 4) 聚合为统一响应
        response = build_readiness_response(
            gate_type="sign_off",
            gate_result=gate_result,
            extra_findings=extra,
            gate_eval_id=eval_id,
            expires_at_iso=expires_at.isoformat(),
        )
        _logger.info(
            "[sign_readiness][DEPRECATED_FIELDS] legacy checks/ready_to_sign 仍返回供旧 UI 兼容，"
            "Round 2 前端切换 GateReadinessPanel 后可移除 project=%s",
            project_id,
        )
        return response

    async def _compute_sign_extra_findings(
        self,
        project_id: uuid.UUID,
        proj: "Project | None",
    ) -> dict[str, list[dict[str, Any]]]:
        """gate 暂未覆盖的业务类目检查，按类目 id 返回 findings 列表。

        规则：每项业务信号若未通过，产出 severity='blocking' 的 finding
        并归到对应类目 id，与 legacy 8 项检查语义完全等价，确保现有
        PartnerDashboard"检查全绿"门槛不降级。
        """
        extra: dict[str, list[dict[str, Any]]] = {}
        base = [WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == False]

        # l2_review — 所有底稿二级复核通过
        not_l2 = (
            await self.db.execute(
                select(func.count())
                .select_from(WorkingPaper)
                .where(
                    *base,
                    WorkingPaper.review_status != WpReviewStatus.not_submitted,
                    WorkingPaper.review_status != WpReviewStatus.level2_passed,
                )
            )
        ).scalar() or 0
        if not_l2 > 0:
            extra.setdefault("l2_review", []).append(
                {
                    "rule_code": "READINESS-L2",
                    "error_code": "L2_REVIEW_INCOMPLETE",
                    "severity": "blocking",
                    "message": f"还有 {not_l2} 个底稿未通过二级复核",
                    "location": {"project_id": str(project_id)},
                    "action_hint": "请在复核工作台完成剩余底稿的二级复核",
                }
            )

        # qc_all_pass — 逐底稿最新 QC 结果
        wp_ids = [
            r[0]
            for r in (await self.db.execute(select(WorkingPaper.id).where(*base))).all()
        ]
        qc_fail = 0
        for wp_id in wp_ids:
            qc = (
                await self.db.execute(
                    select(WpQcResult)
                    .where(WpQcResult.working_paper_id == wp_id)
                    .order_by(WpQcResult.check_timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if qc and not qc.passed:
                qc_fail += 1
        if qc_fail > 0:
            extra.setdefault("qc_all_pass", []).append(
                {
                    "rule_code": "READINESS-QC",
                    "error_code": "QC_SELF_CHECK_FAILED",
                    "severity": "blocking",
                    "message": f"{qc_fail} 个底稿 QC 自检未通过",
                    "location": {"project_id": str(project_id)},
                    "action_hint": "请修复底稿 QC 阻断项后重跑 QC",
                }
            )

        # no_open_issues — 复核意见
        try:
            from app.models.phase10_models import CellAnnotation

            open_count = (
                await self.db.execute(
                    select(func.count())
                    .select_from(CellAnnotation)
                    .where(
                        CellAnnotation.project_id == project_id,
                        CellAnnotation.is_deleted == False,
                        CellAnnotation.status != "resolved",
                    )
                )
            ).scalar() or 0
        except Exception:
            open_count = 0
        if open_count > 0:
            extra.setdefault("no_open_issues", []).append(
                {
                    "rule_code": "READINESS-ISSUE",
                    "error_code": "OPEN_REVIEW_COMMENTS",
                    "severity": "blocking",
                    "message": f"还有 {open_count} 条复核意见未解决",
                    "location": {"project_id": str(project_id)},
                    "action_hint": "请在复核收件箱逐条关闭",
                }
            )

        # adj_approved — 调整分录
        try:
            from app.models.audit_platform_models import Adjustment, ReviewStatus

            unapproved = (
                await self.db.execute(
                    select(func.count())
                    .select_from(Adjustment)
                    .where(
                        Adjustment.project_id == project_id,
                        Adjustment.is_deleted == False,
                        Adjustment.review_status != ReviewStatus.approved,
                    )
                )
            ).scalar() or 0
        except Exception:
            unapproved = 0
        if unapproved > 0:
            extra.setdefault("adj_approved", []).append(
                {
                    "rule_code": "READINESS-ADJ",
                    "error_code": "ADJUSTMENTS_UNAPPROVED",
                    "severity": "blocking",
                    "message": f"{unapproved} 条调整分录未审批",
                    "location": {"project_id": str(project_id)},
                    "action_hint": "请审批剩余调整分录",
                }
            )

        # misstatement_eval — 未更正错报
        try:
            from app.models.audit_platform_models import UnadjustedMisstatement

            uneval = (
                await self.db.execute(
                    select(func.count())
                    .select_from(UnadjustedMisstatement)
                    .where(
                        UnadjustedMisstatement.project_id == project_id,
                        UnadjustedMisstatement.is_deleted == False,
                        UnadjustedMisstatement.auditor_evaluation == None,
                    )
                )
            ).scalar() or 0
        except Exception:
            uneval = 0
        if uneval > 0:
            extra.setdefault("misstatement_eval", []).append(
                {
                    "rule_code": "READINESS-MISSTATE",
                    "error_code": "MISSTATEMENTS_UNEVALUATED",
                    "severity": "blocking",
                    "message": f"{uneval} 条未更正错报尚未评价",
                    "location": {"project_id": str(project_id)},
                    "action_hint": "请在错报汇总表中逐条评价",
                }
            )

        # report_generated — 审计报告
        try:
            from app.models.report_models import AuditReport

            report = (
                await self.db.execute(
                    select(AuditReport)
                    .where(AuditReport.project_id == project_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            has_report = report is not None
        except Exception:
            has_report = False
        if not has_report:
            extra.setdefault("report_generated", []).append(
                {
                    "rule_code": "READINESS-REPORT",
                    "error_code": "REPORT_NOT_GENERATED",
                    "severity": "blocking",
                    "message": "审计报告尚未生成",
                    "location": {"project_id": str(project_id)},
                    "action_hint": "请在审计报告模块生成报告",
                }
            )

        # KAM + independence — wizard_state
        ws = (proj.wizard_state or {}) if proj is not None else {}
        if not ws.get("kam_confirmed", False):
            extra.setdefault("kam_confirmed", []).append(
                {
                    "rule_code": "READINESS-KAM",
                    "error_code": "KAM_NOT_CONFIRMED",
                    "severity": "blocking",
                    "message": "关键审计事项尚未确认",
                    "location": {"project_id": str(project_id)},
                    "action_hint": "请在项目向导确认关键审计事项",
                }
            )
        if not ws.get("independence_confirmed", False):
            extra.setdefault("independence", []).append(
                {
                    "rule_code": "READINESS-INDEP",
                    "error_code": "INDEPENDENCE_NOT_CONFIRMED",
                    "severity": "blocking",
                    "message": "独立性确认未完成",
                    "location": {"project_id": str(project_id)},
                    "action_hint": "请完成独立性声明（R1 v1.5 将升级为结构化声明）",
                }
            )

        return extra

    async def check_workpaper_readiness(self, project_id: uuid.UUID) -> dict[str, Any]:
        """Phase 12 P1-7: 签字前底稿专项检查（5项）。"""
        import time
        start = time.monotonic()
        base = [WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == False]
        checks = []
        all_pass = True

        total_q = select(func.count()).select_from(WorkingPaper).where(*base)
        total = (await self.db.execute(total_q)).scalar() or 0

        # 1. 复核状态
        reviewed_q = select(func.count()).select_from(WorkingPaper).where(
            *base, WorkingPaper.review_status == WpReviewStatus.level2_passed)
        reviewed = (await self.db.execute(reviewed_q)).scalar() or 0
        p1 = reviewed == total and total > 0
        checks.append({"check_name": "复核状态", "passed": p1,
                        "detail": f"{reviewed}/{total} 已通过二级复核"})
        if not p1: all_pass = False

        # 2. QC通过
        from app.models.workpaper_models import WpQcResult
        qc_fail_q = select(func.count()).select_from(WpQcResult).where(
            WpQcResult.project_id == project_id, WpQcResult.blocking_count > 0)
        qc_fail = (await self.db.execute(qc_fail_q)).scalar() or 0
        p2 = qc_fail == 0
        checks.append({"check_name": "QC通过", "passed": p2,
                        "detail": f"{qc_fail} 张底稿有阻断项" if qc_fail else "全部通过"})
        if not p2: all_pass = False

        # 3. 说明非空
        no_expl_q = select(func.count()).select_from(WorkingPaper).where(
            *base, sa.or_(
                WorkingPaper.explanation_status == "not_started",
                WorkingPaper.explanation_status.is_(None),
            ))
        no_expl = (await self.db.execute(no_expl_q)).scalar() or 0
        p3 = no_expl == 0
        checks.append({"check_name": "说明非空", "passed": p3,
                        "detail": f"{no_expl} 张底稿审计说明为空" if no_expl else "全部已填写"})
        if not p3: all_pass = False

        # 4. 数据一致
        inconsistent_q = select(func.count()).select_from(WorkingPaper).where(
            *base, WorkingPaper.consistency_status == "inconsistent")
        inconsistent = (await self.db.execute(inconsistent_q)).scalar() or 0
        p4 = inconsistent == 0
        checks.append({"check_name": "数据一致", "passed": p4,
                        "detail": f"{inconsistent} 张底稿数据不一致" if inconsistent else "全部一致"})
        if not p4: all_pass = False

        # 5. 证据充分（简化：检查是否有附件关联）
        try:
            no_att_q = sa.text("""
                SELECT COUNT(*) FROM working_paper wp
                WHERE wp.project_id = :pid AND wp.is_deleted = false
                AND NOT EXISTS (SELECT 1 FROM attachment_working_paper awp WHERE awp.working_paper_id = wp.id)
            """)
            no_att = (await self.db.execute(no_att_q, {"pid": str(project_id)})).scalar() or 0
        except Exception:
            no_att = 0
        p5 = no_att == 0
        checks.append({"check_name": "证据充分", "passed": p5,
                        "detail": f"{no_att} 张底稿无附件" if no_att else "全部有附件"})
        if not p5: all_pass = False

        elapsed = int((time.monotonic() - start) * 1000)
        return {
            "all_passed": all_pass,
            "checks": checks,
            "total_workpapers": total,
            "check_duration_ms": elapsed,
        }


class TeamEfficiencyService:
    """团队效能分析 — 合伙人关注团队产出"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_team_efficiency(self, user_id: uuid.UUID, days: int = 30) -> dict[str, Any]:
        """
        团队效能指标：
        - 人均完成底稿数
        - 平均复核通过率
        - 退回率
        - 工时利用率
        """
        # 获取合伙人负责的项目
        staff_q = select(StaffMember.id).where(StaffMember.user_id == user_id)
        staff_id = (await self.db.execute(staff_q)).scalar()

        if staff_id:
            pid_q = select(ProjectAssignment.project_id).where(
                ProjectAssignment.staff_id == staff_id, ProjectAssignment.is_deleted == False,
            )
        else:
            # admin 看全部
            pid_q = select(Project.id).where(Project.is_deleted == False).limit(50)

        pids = [r[0] for r in (await self.db.execute(pid_q)).all()]
        if not pids:
            return {"staff_metrics": [], "summary": {}}

        # 按人员统计
        q = (
            select(
                WorkingPaper.assigned_to,
                func.count().label("total"),
                func.count().filter(WorkingPaper.status.in_([WpFileStatus.review_passed, WpFileStatus.archived])).label("passed"),
                func.count().filter(WorkingPaper.review_status.in_([WpReviewStatus.level1_rejected, WpReviewStatus.level2_rejected])).label("rejected"),
            )
            .where(
                WorkingPaper.project_id.in_(pids),
                WorkingPaper.is_deleted == False,
                WorkingPaper.assigned_to.isnot(None),
            )
            .group_by(WorkingPaper.assigned_to)
        )
        rows = (await self.db.execute(q)).all()

        # 获取用户名
        user_ids = [r.assigned_to for r in rows if r.assigned_to]
        user_names = {}
        if user_ids:
            for uid, uname in (await self.db.execute(select(User.id, User.username).where(User.id.in_(user_ids)))).all():
                user_names[str(uid)] = uname

        staff_metrics = []
        total_all = 0
        passed_all = 0
        rejected_all = 0

        for r in rows:
            uid = str(r.assigned_to) if r.assigned_to else "?"
            pass_rate = round(r.passed / r.total * 100, 1) if r.total > 0 else 0
            reject_rate = round(r.rejected / r.total * 100, 1) if r.total > 0 else 0
            staff_metrics.append({
                "user_id": uid,
                "user_name": user_names.get(uid, uid[:8]),
                "total": r.total,
                "passed": r.passed,
                "rejected": r.rejected,
                "pass_rate": pass_rate,
                "reject_rate": reject_rate,
            })
            total_all += r.total
            passed_all += r.passed
            rejected_all += r.rejected

        staff_metrics.sort(key=lambda x: -x["pass_rate"])

        return {
            "staff_metrics": staff_metrics,
            "summary": {
                "total_staff": len(staff_metrics),
                "total_workpapers": total_all,
                "avg_pass_rate": round(passed_all / total_all * 100, 1) if total_all > 0 else 0,
                "avg_reject_rate": round(rejected_all / total_all * 100, 1) if total_all > 0 else 0,
                "avg_per_person": round(total_all / len(staff_metrics), 1) if staff_metrics else 0,
            },
        }
