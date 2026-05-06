"""质控复核人员视角服务 — QC总览 / 按人员进度 / 问题追踪 / 复核意见汇总 / 归档前检查"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, func, and_, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import (
    WorkingPaper, WpFileStatus, WpReviewStatus, WpIndex, WpQcResult, ReviewRecord,
)
from app.models.core import User, Project

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. 项目级 QC 总览看板
# ---------------------------------------------------------------------------

class QCDashboardService:
    """质控总览 — 一眼看清项目质量状态"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_overview(self, project_id: uuid.UUID) -> dict[str, Any]:
        """
        返回：
        - 底稿总数 / 已自检 / 自检通过 / 有阻断 / 未自检
        - 复核状态分布（未提交/待一级/一级通过/待二级/二级通过/退回）
        - 按循环分组的质量矩阵
        - 最近 QC 失败的底稿列表
        """
        base = [WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == False]

        # 总数
        total = (await self.db.execute(
            select(func.count()).select_from(WorkingPaper).where(*base)
        )).scalar() or 0

        # 复核状态分布
        review_dist_q = (
            select(WorkingPaper.review_status, func.count().label("cnt"))
            .where(*base)
            .group_by(WorkingPaper.review_status)
        )
        review_dist = {}
        for row in (await self.db.execute(review_dist_q)).all():
            review_dist[row.review_status.value if row.review_status else "unknown"] = row.cnt

        # QC 结果统计（每个底稿取最新一次）
        # 用子查询取每个 wp 的最新 qc_result
        wp_ids_q = select(WorkingPaper.id).where(*base)
        wp_ids = [r[0] for r in (await self.db.execute(wp_ids_q)).all()]

        qc_passed = 0
        qc_blocking = 0
        qc_not_checked = 0
        recent_failures: list[dict] = []

        for wp_id in wp_ids:
            qc_row = (await self.db.execute(
                select(WpQcResult)
                .where(WpQcResult.working_paper_id == wp_id)
                .order_by(WpQcResult.check_timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()

            if qc_row is None:
                qc_not_checked += 1
            elif qc_row.passed:
                qc_passed += 1
            else:
                qc_blocking += 1
                if len(recent_failures) < 20:
                    recent_failures.append({
                        "wp_id": str(wp_id),
                        "blocking_count": qc_row.blocking_count,
                        "warning_count": qc_row.warning_count,
                        "check_time": qc_row.check_timestamp.isoformat() if qc_row.check_timestamp else None,
                        "findings": qc_row.findings[:3] if qc_row.findings else [],
                    })

        # 按循环分组的质量矩阵
        cycle_q = (
            select(
                WpIndex.audit_cycle,
                WorkingPaper.review_status,
                func.count().label("cnt"),
            )
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(*base)
            .group_by(WpIndex.audit_cycle, WorkingPaper.review_status)
        )
        cycle_matrix: dict[str, dict] = {}
        for cycle, rs, cnt in (await self.db.execute(cycle_q)).all():
            key = cycle or "未分类"
            if key not in cycle_matrix:
                cycle_matrix[key] = {}
            cycle_matrix[key][rs.value if rs else "unknown"] = cnt

        return {
            "total": total,
            "qc_passed": qc_passed,
            "qc_blocking": qc_blocking,
            "qc_not_checked": qc_not_checked,
            "qc_checked": qc_passed + qc_blocking,
            "qc_pass_rate": round(qc_passed / (qc_passed + qc_blocking) * 100, 1) if (qc_passed + qc_blocking) > 0 else 0,
            "review_distribution": review_dist,
            "cycle_matrix": cycle_matrix,
            "recent_failures": recent_failures,
        }


# ---------------------------------------------------------------------------
# 2. 按人员统计底稿进度
# ---------------------------------------------------------------------------

class StaffProgressService:
    """按人员维度统计底稿进度 — 质控人员需要看到每个人的工作量和完成情况"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_staff_progress(self, project_id: uuid.UUID) -> dict[str, Any]:
        """
        返回每个编制人的：
        - 分配数 / 已完成 / 待复核 / 退回 / 未开始
        - 完成率
        """
        base = [WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == False]

        q = (
            select(
                WorkingPaper.assigned_to,
                WorkingPaper.status,
                WorkingPaper.review_status,
                func.count().label("cnt"),
            )
            .where(*base)
            .group_by(WorkingPaper.assigned_to, WorkingPaper.status, WorkingPaper.review_status)
        )
        rows = (await self.db.execute(q)).all()

        staff_map: dict[str, dict] = {}
        for assigned_to, status, review_status, cnt in rows:
            uid = str(assigned_to) if assigned_to else "未分配"
            if uid not in staff_map:
                staff_map[uid] = {"total": 0, "passed": 0, "pending_review": 0, "rejected": 0, "in_progress": 0, "not_started": 0}

            staff_map[uid]["total"] += cnt

            if status in (WpFileStatus.review_passed, WpFileStatus.archived):
                staff_map[uid]["passed"] += cnt
            elif review_status in (WpReviewStatus.pending_level1, WpReviewStatus.pending_level2):
                staff_map[uid]["pending_review"] += cnt
            elif review_status in (WpReviewStatus.level1_rejected, WpReviewStatus.level2_rejected):
                staff_map[uid]["rejected"] += cnt
            elif status in (WpFileStatus.draft, WpFileStatus.edit_complete, WpFileStatus.under_review):
                staff_map[uid]["in_progress"] += cnt
            else:
                staff_map[uid]["not_started"] += cnt

        # 尝试获取用户名
        user_ids = [k for k in staff_map if k != "未分配"]
        user_names: dict[str, str] = {}
        if user_ids:
            try:
                valid_uuids = [uuid.UUID(uid) for uid in user_ids]
                name_q = select(User.id, User.username).where(User.id.in_(valid_uuids))
                for uid, uname in (await self.db.execute(name_q)).all():
                    user_names[str(uid)] = uname
            except Exception:
                pass

        result = []
        for uid, stats in staff_map.items():
            stats["user_id"] = uid
            stats["user_name"] = user_names.get(uid, uid)
            stats["completion_rate"] = round(stats["passed"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0
            result.append(stats)

        result.sort(key=lambda x: x["completion_rate"])
        return {"staff_progress": result, "staff_count": len(result)}


# ---------------------------------------------------------------------------
# 3. 复核意见追踪汇总
# ---------------------------------------------------------------------------

class ReviewIssueTracker:
    """汇总所有未解决的复核意见 — 质控人员需要追踪"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_open_issues(self, project_id: uuid.UUID) -> dict[str, Any]:
        """获取所有未解决的复核意见，按底稿分组"""
        from app.models.phase10_models import CellAnnotation

        q = (
            select(
                CellAnnotation.object_id,
                CellAnnotation.content,
                CellAnnotation.status,
                CellAnnotation.created_by,
                CellAnnotation.created_at,
                CellAnnotation.cell_ref,
            )
            .where(
                CellAnnotation.project_id == project_id,
                CellAnnotation.is_deleted == False,
                CellAnnotation.status != "resolved",
            )
            .order_by(CellAnnotation.created_at.desc())
        )
        rows = (await self.db.execute(q)).all()

        issues = []
        for obj_id, content, status, created_by, created_at, cell_ref in rows:
            issues.append({
                "wp_id": str(obj_id) if obj_id else None,
                "content": content,
                "status": status,
                "created_by": str(created_by) if created_by else None,
                "created_at": created_at.isoformat() if created_at else None,
                "cell_ref": cell_ref,
            })

        # 按底稿分组统计
        by_wp: dict[str, int] = {}
        for issue in issues:
            wp_id = issue["wp_id"] or "unknown"
            by_wp[wp_id] = by_wp.get(wp_id, 0) + 1

        return {
            "total_open": len(issues),
            "issues": issues[:50],  # 最多返回50条
            "by_workpaper": by_wp,
        }


# ---------------------------------------------------------------------------
# 4. 归档前检查清单
# ---------------------------------------------------------------------------

class ArchiveReadinessService:
    """归档前检查 — 质控人员确认项目可以归档"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_readiness(
        self,
        project_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """R1 Task 7 门面化：内部调 ``gate_engine.evaluate('export_package')``，
        findings 按 ``rule_code`` 映射到 12 项 UI 类目；gate 尚未覆盖的
        类目（期后事项/持续经营/管理层声明等 wizard_state 信号）通过
        ``extra_findings`` 补齐，保证归档向导界面类目数不回退。

        返回统一 schema（见 :mod:`app.services.readiness_facade`）：
        ``{ready, groups, gate_eval_id, expires_at, checks(legacy), ...}``
        """
        from app.services.gate_engine import gate_engine
        from app.services.gate_eval_store import store_gate_eval
        from app.services.readiness_facade import build_readiness_response

        # actor 兜底：走 Project.created_by
        resolved_actor = actor_id
        proj = (
            await self.db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if resolved_actor is None and proj is not None:
            resolved_actor = proj.created_by
        if resolved_actor is None:
            resolved_actor = uuid.uuid4()
            _logger.warning(
                "[archive_readiness] actor_id 缺失，已生成占位符 actor=%s project=%s",
                resolved_actor,
                project_id,
            )

        gate_result = await gate_engine.evaluate(
            db=self.db,
            gate_type="export_package",
            project_id=project_id,
            wp_id=None,
            actor_id=resolved_actor,
            context={},
        )

        extra = await self._compute_archive_extra_findings(project_id, proj)

        has_blocking = any(
            f["severity"] == "blocking" for items in extra.values() for f in items
        ) or any(
            str(getattr(h, "severity", "")) == "blocking"
            for h in (gate_result.hit_rules or [])
        )
        gate_decision = str(gate_result.decision)
        ready_flag = (gate_decision != "block") and (not has_blocking)

        eval_id, expires_at = await store_gate_eval(
            project_id=project_id,
            gate_type="export_package",
            ready=ready_flag,
            decision=gate_decision,
        )

        response = build_readiness_response(
            gate_type="export_package",
            gate_result=gate_result,
            extra_findings=extra,
            gate_eval_id=eval_id,
            expires_at_iso=expires_at.isoformat(),
        )
        _logger.info(
            "[archive_readiness][DEPRECATED_FIELDS] legacy checks 仍返回供旧 UI 兼容，"
            "Round 2 归档向导切换后可移除 project=%s",
            project_id,
        )
        return response

    async def _compute_archive_extra_findings(
        self,
        project_id: uuid.UUID,
        proj: "Project | None",
    ) -> dict[str, list[dict[str, Any]]]:
        """归档 12 项类目中 gate 尚未覆盖的业务信号。"""
        extra: dict[str, list[dict[str, Any]]] = {}
        base = [WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == False]

        # 1. review_complete — 底稿复核状态
        not_passed_q = select(func.count()).select_from(WorkingPaper).where(
            *base,
            WorkingPaper.review_status.notin_([
                WpReviewStatus.level1_passed, WpReviewStatus.level2_passed,
            ]),
            WorkingPaper.review_status != WpReviewStatus.not_submitted,
        )
        not_passed = (await self.db.execute(not_passed_q)).scalar() or 0
        if not_passed > 0:
            extra.setdefault("review_complete", []).append({
                "rule_code": "READINESS-REVIEW",
                "error_code": "WORKPAPERS_NOT_REVIEWED",
                "severity": "blocking",
                "message": f"还有 {not_passed} 个底稿未通过复核",
                "location": {"project_id": str(project_id)},
                "action_hint": "请在复核工作台完成剩余底稿复核",
            })

        # 2. qc_passed — 逐底稿最新 QC
        wp_ids = [r[0] for r in (await self.db.execute(select(WorkingPaper.id).where(*base))).all()]
        qc_fail_count = 0
        qc_not_run = 0
        for wp_id in wp_ids:
            qc = (await self.db.execute(
                select(WpQcResult).where(WpQcResult.working_paper_id == wp_id)
                .order_by(WpQcResult.check_timestamp.desc()).limit(1)
            )).scalar_one_or_none()
            if qc is None:
                qc_not_run += 1
            elif not qc.passed:
                qc_fail_count += 1
        if qc_fail_count > 0 or qc_not_run > 0:
            extra.setdefault("qc_passed", []).append({
                "rule_code": "READINESS-QC",
                "error_code": "QC_SELF_CHECK_INCOMPLETE",
                "severity": "blocking",
                "message": f"QC 未通过 {qc_fail_count} 个，未执行 {qc_not_run} 个",
                "location": {"project_id": str(project_id)},
                "action_hint": "请补跑 QC 并修复阻断项",
            })

        # 3. no_open_issues — 复核意见
        try:
            tracker = ReviewIssueTracker(self.db)
            open_issues = await tracker.get_open_issues(project_id)
            open_count = open_issues["total_open"]
        except Exception:
            open_count = 0
        if open_count > 0:
            extra.setdefault("no_open_issues", []).append({
                "rule_code": "READINESS-ISSUE",
                "error_code": "OPEN_REVIEW_COMMENTS",
                "severity": "blocking",
                "message": f"还有 {open_count} 条复核意见未解决",
                "location": {"project_id": str(project_id)},
                "action_hint": "请在复核收件箱逐条关闭",
            })

        # 4. adj_approved — 调整分录
        try:
            from app.models.audit_platform_models import Adjustment, ReviewStatus
            unapproved_q = select(func.count()).select_from(Adjustment).where(
                Adjustment.project_id == project_id,
                Adjustment.is_deleted == False,
                Adjustment.review_status != ReviewStatus.approved,
            )
            unapproved = (await self.db.execute(unapproved_q)).scalar() or 0
        except Exception:
            unapproved = 0
        if unapproved > 0:
            extra.setdefault("adj_approved", []).append({
                "rule_code": "READINESS-ADJ",
                "error_code": "ADJUSTMENTS_UNAPPROVED",
                "severity": "blocking",
                "message": f"{unapproved} 条调整分录未审批",
                "location": {"project_id": str(project_id)},
                "action_hint": "请审批剩余调整分录",
            })

        # 5. misstatement_evaluated — 未更正错报
        try:
            from app.models.audit_platform_models import UnadjustedMisstatement
            uneval_q = select(func.count()).select_from(UnadjustedMisstatement).where(
                UnadjustedMisstatement.project_id == project_id,
                UnadjustedMisstatement.is_deleted == False,
                UnadjustedMisstatement.auditor_evaluation == None,
            )
            uneval = (await self.db.execute(uneval_q)).scalar() or 0
        except Exception:
            uneval = 0
        if uneval > 0:
            extra.setdefault("misstatement_evaluated", []).append({
                "rule_code": "READINESS-MISSTATE",
                "error_code": "MISSTATEMENTS_UNEVALUATED",
                "severity": "blocking",
                "message": f"{uneval} 条未更正错报尚未评价",
                "location": {"project_id": str(project_id)},
                "action_hint": "请在错报汇总表中逐条评价",
            })

        # 6. report_generated — 审计报告
        try:
            from app.models.report_models import AuditReport
            report = (await self.db.execute(
                select(AuditReport).where(AuditReport.project_id == project_id).limit(1)
            )).scalar_one_or_none()
            has_report = report is not None
        except Exception:
            has_report = False
        if not has_report:
            extra.setdefault("report_generated", []).append({
                "rule_code": "READINESS-REPORT",
                "error_code": "REPORT_NOT_GENERATED",
                "severity": "blocking",
                "message": "审计报告尚未生成",
                "location": {"project_id": str(project_id)},
                "action_hint": "请在审计报告模块生成报告",
            })

        # 7-11. wizard_state 项（KAM + independence + subsequent_events +
        # going_concern + mgmt_representation 已由 R6/R7 GateRule 覆盖）
        # 不再在 extra_findings 中重复检查

        # 12. index_complete — 底稿索引完整性
        no_code_q = select(func.count()).select_from(WorkingPaper).where(
            *base,
            WorkingPaper.wp_index_id == None,
        )
        no_code = (await self.db.execute(no_code_q)).scalar() or 0
        if no_code > 0:
            extra.setdefault("index_complete", []).append({
                "rule_code": "READINESS-INDEX",
                "error_code": "WORKPAPERS_WITHOUT_INDEX",
                "severity": "blocking",
                "message": f"{no_code} 个底稿缺少索引编号",
                "location": {"project_id": str(project_id)},
                "action_hint": "请为缺失底稿分配 wp_index",
            })

        return extra
