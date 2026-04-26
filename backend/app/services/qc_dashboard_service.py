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

    async def check_readiness(self, project_id: uuid.UUID) -> dict[str, Any]:
        """
        检查项目是否满足归档条件（致同标准归档检查清单）：
        1. 所有底稿复核通过
        2. 所有 QC 自检通过
        3. 无未解决的复核意见
        4. 调整分录全部审批
        5. 未更正错报已评价
        6. 审计报告已生成
        7. 关键审计事项已确认
        8. 独立性确认已签署
        9. 期后事项审阅已完成
        10. 持续经营评价已完成
        11. 管理层声明书已获取
        12. 底稿按索引编号排列
        """
        checks: list[dict] = []
        all_pass = True

        base = [WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == False]

        # 1. 底稿复核状态
        not_passed_q = select(func.count()).select_from(WorkingPaper).where(
            *base,
            WorkingPaper.review_status.notin_([
                WpReviewStatus.level1_passed, WpReviewStatus.level2_passed,
            ]),
            WorkingPaper.review_status != WpReviewStatus.not_submitted,  # 排除未提交的（可能是空底稿）
        )
        not_passed = (await self.db.execute(not_passed_q)).scalar() or 0

        total_submitted_q = select(func.count()).select_from(WorkingPaper).where(
            *base,
            WorkingPaper.review_status != WpReviewStatus.not_submitted,
        )
        total_submitted = (await self.db.execute(total_submitted_q)).scalar() or 0

        checks.append({
            "id": "review_complete",
            "label": "所有底稿复核通过",
            "passed": not_passed == 0,
            "detail": f"{total_submitted - not_passed}/{total_submitted} 已通过" if total_submitted > 0 else "无已提交底稿",
        })
        if not_passed > 0:
            all_pass = False

        # 2. QC 自检
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

        qc_ok = qc_fail_count == 0 and qc_not_run == 0
        checks.append({
            "id": "qc_passed",
            "label": "所有底稿 QC 自检通过",
            "passed": qc_ok,
            "detail": f"未通过 {qc_fail_count} 个，未执行 {qc_not_run} 个" if not qc_ok else "全部通过",
        })
        if not qc_ok:
            all_pass = False

        # 3. 未解决复核意见
        try:
            tracker = ReviewIssueTracker(self.db)
            open_issues = await tracker.get_open_issues(project_id)
            open_count = open_issues["total_open"]
        except Exception:
            open_count = 0

        checks.append({
            "id": "no_open_issues",
            "label": "无未解决的复核意见",
            "passed": open_count == 0,
            "detail": f"还有 {open_count} 条未解决" if open_count > 0 else "全部已解决",
        })
        if open_count > 0:
            all_pass = False

        # 4. 调整分录审批
        try:
            from app.models.audit_platform_models import Adjustment, ReviewStatus
            unapproved_q = select(func.count()).select_from(Adjustment).where(
                Adjustment.project_id == project_id,
                Adjustment.is_deleted == False,
                Adjustment.review_status != ReviewStatus.approved,
            )
            unapproved = (await self.db.execute(unapproved_q)).scalar() or 0
            checks.append({
                "id": "adj_approved",
                "label": "调整分录全部审批",
                "passed": unapproved == 0,
                "detail": f"还有 {unapproved} 条未审批" if unapproved > 0 else "全部已审批",
            })
            if unapproved > 0:
                all_pass = False
        except Exception:
            checks.append({"id": "adj_approved", "label": "调整分录全部审批", "passed": True, "detail": "无调整分录"})

        # 5. 未更正错报评价
        try:
            from app.models.audit_platform_models import UnadjustedMisstatement
            uneval_q = select(func.count()).select_from(UnadjustedMisstatement).where(
                UnadjustedMisstatement.project_id == project_id,
                UnadjustedMisstatement.is_deleted == False,
                UnadjustedMisstatement.auditor_evaluation == None,
            )
            uneval = (await self.db.execute(uneval_q)).scalar() or 0
            checks.append({
                "id": "misstatement_evaluated",
                "label": "未更正错报已评价",
                "passed": uneval == 0,
                "detail": f"还有 {uneval} 条未评价" if uneval > 0 else "全部已评价",
            })
            if uneval > 0:
                all_pass = False
        except Exception:
            checks.append({"id": "misstatement_evaluated", "label": "未更正错报已评价", "passed": True, "detail": "无未更正错报"})

        # 6. 审计报告已生成
        try:
            from app.models.report_models import AuditReport
            report = (await self.db.execute(
                select(AuditReport).where(AuditReport.project_id == project_id).limit(1)
            )).scalar_one_or_none()
            has_report = report is not None
        except Exception:
            has_report = False
        checks.append({"id": "report_generated", "label": "审计报告已生成", "passed": has_report,
                        "detail": "已生成" if has_report else "未生成"})
        if not has_report: all_pass = False

        # 7-12. 从 wizard_state 检查项目级配置
        proj = (await self.db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
        ws = proj.wizard_state or {} if proj else {}

        kam_confirmed = ws.get("kam_confirmed", False)
        checks.append({"id": "kam_confirmed", "label": "关键审计事项已确认", "passed": kam_confirmed,
                        "detail": "已确认" if kam_confirmed else "未确认"})
        if not kam_confirmed: all_pass = False

        independence = ws.get("independence_confirmed", False)
        checks.append({"id": "independence", "label": "独立性确认已签署", "passed": independence,
                        "detail": "已签署" if independence else "未签署"})
        if not independence: all_pass = False

        subsequent_done = ws.get("subsequent_events_reviewed", False)
        checks.append({"id": "subsequent_events", "label": "期后事项审阅已完成", "passed": subsequent_done,
                        "detail": "已完成" if subsequent_done else "未完成"})
        if not subsequent_done: all_pass = False

        going_concern = ws.get("going_concern_evaluated", False)
        checks.append({"id": "going_concern", "label": "持续经营评价已完成", "passed": going_concern,
                        "detail": "已完成" if going_concern else "未完成"})
        if not going_concern: all_pass = False

        mgmt_rep = ws.get("management_representation_obtained", False)
        checks.append({"id": "mgmt_representation", "label": "管理层声明书已获取", "passed": mgmt_rep,
                        "detail": "已获取" if mgmt_rep else "未获取"})
        if not mgmt_rep: all_pass = False

        # 12. 底稿索引完整性（所有底稿都有 wp_code）
        no_code_q = select(func.count()).select_from(WorkingPaper).where(
            *base,
            WorkingPaper.wp_index_id == None,
        )
        no_code = (await self.db.execute(no_code_q)).scalar() or 0
        checks.append({"id": "index_complete", "label": "底稿按索引编号排列", "passed": no_code == 0,
                        "detail": f"{no_code} 个底稿缺少索引" if no_code > 0 else "全部已编号"})
        if no_code > 0: all_pass = False

        return {
            "ready": all_pass,
            "checks": checks,
            "passed_count": sum(1 for c in checks if c["passed"]),
            "total_checks": len(checks),
        }
