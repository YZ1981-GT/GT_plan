"""项目经理视角服务 — 待复核收件箱 / 批量复核 / 进度总览 / 进度简报 / 交叉引用检查 / 客户沟通"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, func, and_, or_, case, update as sa_update, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import (
    WorkingPaper, WpFileStatus, WpReviewStatus, WpIndex, WpCrossRef, ReviewRecord,
)
from app.models.core import User, Project

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. 待复核收件箱
# ---------------------------------------------------------------------------

class ReviewInboxService:
    """列出当前用户待复核的底稿，按提交时间排序"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_inbox(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """
        返回待当前用户复核的底稿列表。
        review_status in (pending_level1, pending_level2) 且 reviewer == user_id
        """
        conditions = [
            WorkingPaper.is_deleted == False,
            WorkingPaper.reviewer == user_id,
            WorkingPaper.review_status.in_([
                WpReviewStatus.pending_level1,
                WpReviewStatus.pending_level2,
            ]),
        ]
        if project_id:
            conditions.append(WorkingPaper.project_id == project_id)

        # 总数
        count_q = select(func.count()).select_from(WorkingPaper).where(*conditions)
        total = (await self.db.execute(count_q)).scalar() or 0

        # 分页列表
        q = (
            select(WorkingPaper, WpIndex.wp_code, WpIndex.wp_name, WpIndex.audit_cycle, Project.name.label("project_name"))
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .join(Project, WorkingPaper.project_id == Project.id)
            .where(*conditions)
            .order_by(WorkingPaper.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.db.execute(q)).all()

        items = []
        for wp, wp_code, wp_name, audit_cycle, project_name in rows:
            items.append({
                "id": str(wp.id),
                "project_id": str(wp.project_id),
                "project_name": project_name,
                "wp_code": wp_code,
                "wp_name": wp_name,
                "audit_cycle": audit_cycle,
                "status": wp.status.value if wp.status else "draft",
                "review_status": wp.review_status.value if wp.review_status else "not_submitted",
                "assigned_to": str(wp.assigned_to) if wp.assigned_to else None,
                "submitted_at": wp.updated_at.isoformat() if wp.updated_at else None,
                "file_version": wp.file_version,
            })

        return {"items": items, "total": total, "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# 2. 批量复核操作
# ---------------------------------------------------------------------------

class BatchReviewService:
    """批量通过 / 批量退回底稿"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def batch_review(
        self,
        project_id: uuid.UUID,
        wp_ids: list[uuid.UUID],
        action: str,  # "approve" | "reject"
        reviewer_id: uuid.UUID,
        comment: str = "",
    ) -> dict[str, Any]:
        """
        批量操作：
        - approve: pending_level1 → level1_passed, pending_level2 → level2_passed
        - reject:  pending_level1 → level1_rejected, pending_level2 → level2_rejected
        """
        q = (
            select(WorkingPaper)
            .where(
                WorkingPaper.id.in_(wp_ids),
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,
                WorkingPaper.reviewer == reviewer_id,
            )
        )
        result = (await self.db.execute(q)).scalars().all()

        succeeded, skipped = [], []
        for wp in result:
            rs = wp.review_status
            if action == "approve":
                if rs == WpReviewStatus.pending_level1:
                    wp.review_status = WpReviewStatus.level1_passed
                    wp.status = WpFileStatus.review_passed
                elif rs == WpReviewStatus.pending_level2:
                    wp.review_status = WpReviewStatus.level2_passed
                    wp.status = WpFileStatus.review_passed
                else:
                    skipped.append(str(wp.id))
                    continue
            elif action == "reject":
                if rs == WpReviewStatus.pending_level1:
                    wp.review_status = WpReviewStatus.level1_rejected
                    wp.status = WpFileStatus.revision_required
                elif rs == WpReviewStatus.pending_level2:
                    wp.review_status = WpReviewStatus.level2_rejected
                    wp.status = WpFileStatus.revision_required
                else:
                    skipped.append(str(wp.id))
                    continue
            else:
                skipped.append(str(wp.id))
                continue

            wp.updated_at = datetime.utcnow()
            succeeded.append(str(wp.id))

        return {
            "succeeded": succeeded,
            "skipped": skipped,
            "succeeded_count": len(succeeded),
            "skipped_count": len(skipped),
        }


# ---------------------------------------------------------------------------
# 3. 项目进度总览
# ---------------------------------------------------------------------------

class ProjectProgressService:
    """项目底稿进度统计 — 按审计循环分组"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_progress(self, project_id: uuid.UUID) -> dict[str, Any]:
        """返回按审计循环分组的底稿状态统计"""
        q = (
            select(
                WpIndex.audit_cycle,
                WorkingPaper.status,
                WorkingPaper.review_status,
                func.count().label("cnt"),
            )
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,
            )
            .group_by(WpIndex.audit_cycle, WorkingPaper.status, WorkingPaper.review_status)
        )
        rows = (await self.db.execute(q)).all()

        # 汇总
        cycles: dict[str, dict] = {}
        total_stats = {"not_started": 0, "in_progress": 0, "pending_review": 0, "passed": 0, "total": 0}

        for audit_cycle, status, review_status, cnt in rows:
            cycle_key = audit_cycle or "未分类"
            if cycle_key not in cycles:
                cycles[cycle_key] = {"not_started": 0, "in_progress": 0, "pending_review": 0, "passed": 0, "total": 0, "items": []}

            bucket = _classify_status(status, review_status)
            cycles[cycle_key][bucket] += cnt
            cycles[cycle_key]["total"] += cnt
            total_stats[bucket] += cnt
            total_stats["total"] += cnt

        # 获取每个底稿的详细信息（用于看板拖拽）
        detail_q = (
            select(
                WorkingPaper.id, WorkingPaper.status, WorkingPaper.review_status,
                WorkingPaper.assigned_to, WorkingPaper.reviewer,
                WpIndex.wp_code, WpIndex.wp_name, WpIndex.audit_cycle,
            )
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == False)
            .order_by(WpIndex.audit_cycle, WpIndex.wp_code)
        )
        detail_rows = (await self.db.execute(detail_q)).all()

        board_items = []
        for wp_id, status, review_status, assigned_to, reviewer, wp_code, wp_name, audit_cycle in detail_rows:
            board_items.append({
                "id": str(wp_id),
                "wp_code": wp_code,
                "wp_name": wp_name,
                "audit_cycle": audit_cycle or "未分类",
                "status": status.value if status else "draft",
                "review_status": review_status.value if review_status else "not_submitted",
                "bucket": _classify_status(status, review_status),
                "assigned_to": str(assigned_to) if assigned_to else None,
                "reviewer": str(reviewer) if reviewer else None,
            })

        return {
            "cycles": cycles,
            "total": total_stats,
            "board_items": board_items,
        }


def _classify_status(status: WpFileStatus | None, review_status: WpReviewStatus | None) -> str:
    """将底稿状态归类为四个看板列"""
    if status in (WpFileStatus.review_passed, WpFileStatus.archived):
        return "passed"
    if review_status in (
        WpReviewStatus.pending_level1, WpReviewStatus.pending_level2,
        WpReviewStatus.level1_in_progress, WpReviewStatus.level2_in_progress,
    ):
        return "pending_review"
    if status in (WpFileStatus.draft, WpFileStatus.edit_complete, WpFileStatus.under_review, WpFileStatus.revision_required):
        return "in_progress"
    return "not_started"


# ---------------------------------------------------------------------------
# 4. 项目进度简报（AI 生成）
# ---------------------------------------------------------------------------

class ProgressBriefService:
    """AI 生成项目进度简报"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_brief(self, project_id: uuid.UUID, polish_with_llm: bool = False) -> dict[str, Any]:
        """生成进度简报数据，可选 LLM 润色"""
        progress_svc = ProjectProgressService(self.db)
        progress = await progress_svc.get_progress(project_id)
        total = progress["total"]

        # 获取项目基本信息
        proj = (await self.db.execute(
            select(Project).where(Project.id == project_id)
        )).scalar_one_or_none()

        completion_rate = (
            round(total["passed"] / total["total"] * 100, 1)
            if total["total"] > 0 else 0
        )

        # 待复核数量
        pending_q = select(func.count()).select_from(WorkingPaper).where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,
            WorkingPaper.review_status.in_([
                WpReviewStatus.pending_level1, WpReviewStatus.pending_level2,
            ]),
        )
        pending_count = (await self.db.execute(pending_q)).scalar() or 0

        # 退回修改数量
        rejected_q = select(func.count()).select_from(WorkingPaper).where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,
            WorkingPaper.review_status.in_([
                WpReviewStatus.level1_rejected, WpReviewStatus.level2_rejected,
            ]),
        )
        rejected_count = (await self.db.execute(rejected_q)).scalar() or 0

        raw_summary = _build_text_summary(
            proj.name if proj else "项目",
            completion_rate, total, pending_count, rejected_count,
            progress["cycles"],
        )

        # LLM 润色
        polished_summary = raw_summary
        llm_used = False
        if polish_with_llm:
            try:
                from app.services.llm_client import chat_completion
                prompt = (
                    "你是一位资深审计项目经理。请将以下项目进度数据改写为一份专业、简洁的项目进度简报，"
                    "适合发给合伙人和客户阅读。要求：\n"
                    "1. 用 Markdown 格式，包含标题、要点、风险提示\n"
                    "2. 语言正式但不啰嗦，突出关键数字\n"
                    "3. 如有退回或超期情况，明确指出风险和建议\n"
                    "4. 结尾给出下一步工作计划建议\n\n"
                    f"原始数据：\n{raw_summary}"
                )
                result = await chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    max_tokens=1500,
                )
                if result and not result.startswith("[LLM"):
                    polished_summary = result
                    llm_used = True
            except Exception as e:
                _logger.warning("LLM polish failed: %s", e)

        brief = {
            "project_name": proj.name if proj else "未知项目",
            "generated_at": datetime.utcnow().isoformat(),
            "completion_rate": completion_rate,
            "total_workpapers": total["total"],
            "passed_count": total["passed"],
            "in_progress_count": total["in_progress"],
            "pending_review_count": pending_count,
            "rejected_count": rejected_count,
            "not_started_count": total["not_started"],
            "cycles_summary": {
                k: {"total": v["total"], "passed": v["passed"], "rate": round(v["passed"] / v["total"] * 100, 1) if v["total"] > 0 else 0}
                for k, v in progress["cycles"].items()
            },
            "text_summary": polished_summary,
            "raw_summary": raw_summary,
            "llm_polished": llm_used,
        }
        return brief


def _build_text_summary(
    project_name: str, rate: float, total: dict, pending: int, rejected: int, cycles: dict,
) -> str:
    lines = [
        f"## {project_name} 项目进度简报",
        f"",
        f"**整体完成率**：{rate}%（{total['passed']}/{total['total']}）",
        f"",
        f"- 已通过：{total['passed']} 个",
        f"- 编制中：{total['in_progress']} 个",
        f"- 待复核：{pending} 个",
        f"- 退回修改：{rejected} 个",
        f"- 未开始：{total['not_started']} 个",
        f"",
        f"### 各循环进度",
    ]
    for cycle_name, stats in sorted(cycles.items()):
        cycle_rate = round(stats["passed"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0
        lines.append(f"- **{cycle_name}**：{cycle_rate}%（{stats['passed']}/{stats['total']}）")

    if rejected > 0:
        lines.extend(["", f"⚠️ 有 {rejected} 个底稿被退回修改，请关注。"])
    if pending > 0:
        lines.extend(["", f"📋 有 {pending} 个底稿待复核。"])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5. 交叉引用检查
# ---------------------------------------------------------------------------

class CrossRefCheckService:
    """检查底稿之间的交叉引用完整性"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_cross_refs(self, project_id: uuid.UUID) -> dict[str, Any]:
        """检查所有交叉引用是否完整"""
        # 获取所有交叉引用
        ref_q = (
            select(WpCrossRef)
            .where(WpCrossRef.project_id == project_id)
        )
        refs = (await self.db.execute(ref_q)).scalars().all()

        # 获取所有底稿索引
        idx_q = select(WpIndex.id, WpIndex.wp_code, WpIndex.wp_name).where(
            WpIndex.project_id == project_id
        )
        idx_rows = (await self.db.execute(idx_q)).all()
        idx_map = {str(r.id): {"wp_code": r.wp_code, "wp_name": r.wp_name} for r in idx_rows}

        # 获取所有底稿状态
        wp_q = (
            select(WorkingPaper.wp_index_id, WorkingPaper.status, WorkingPaper.review_status)
            .where(WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == False)
        )
        wp_rows = (await self.db.execute(wp_q)).all()
        wp_status_map = {str(r.wp_index_id): {"status": r.status, "review_status": r.review_status} for r in wp_rows}

        issues = []
        for ref in refs:
            source_id = str(ref.source_wp_index_id) if hasattr(ref, 'source_wp_index_id') else str(ref.from_wp_id) if hasattr(ref, 'from_wp_id') else None
            target_id = str(ref.target_wp_index_id) if hasattr(ref, 'target_wp_index_id') else str(ref.to_wp_id) if hasattr(ref, 'to_wp_id') else None

            if not source_id or not target_id:
                continue

            source_info = idx_map.get(source_id, {})
            target_info = idx_map.get(target_id, {})
            target_wp = wp_status_map.get(target_id)

            if not target_wp:
                issues.append({
                    "type": "missing",
                    "severity": "high",
                    "source_code": source_info.get("wp_code", "?"),
                    "source_name": source_info.get("wp_name", "?"),
                    "target_code": target_info.get("wp_code", "?"),
                    "target_name": target_info.get("wp_name", "?"),
                    "message": f"{source_info.get('wp_code', '?')} 引用了 {target_info.get('wp_code', '?')}，但该底稿不存在或未创建",
                })
            elif target_wp["status"] == WpFileStatus.draft:
                issues.append({
                    "type": "incomplete",
                    "severity": "medium",
                    "source_code": source_info.get("wp_code", "?"),
                    "source_name": source_info.get("wp_name", "?"),
                    "target_code": target_info.get("wp_code", "?"),
                    "target_name": target_info.get("wp_name", "?"),
                    "message": f"{source_info.get('wp_code', '?')} 引用了 {target_info.get('wp_code', '?')}，但该底稿仍在编制中",
                })

        return {
            "total_refs": len(refs),
            "issues": issues,
            "issue_count": len(issues),
            "high_count": sum(1 for i in issues if i["severity"] == "high"),
            "medium_count": sum(1 for i in issues if i["severity"] == "medium"),
        }


# ---------------------------------------------------------------------------
# 6. 客户沟通记录
# ---------------------------------------------------------------------------

class ClientCommunicationService:
    """客户沟通记录 — 存储在 project 的 wizard_state.communications JSONB 中"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_communications(self, project_id: uuid.UUID) -> list[dict]:
        proj = (await self.db.execute(
            select(Project).where(Project.id == project_id)
        )).scalar_one_or_none()
        if not proj:
            return []
        ws = proj.wizard_state or {}
        return ws.get("communications", [])

    async def add_communication(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        data: dict,
    ) -> dict:
        proj = (await self.db.execute(
            select(Project).where(Project.id == project_id)
        )).scalar_one_or_none()
        if not proj:
            raise ValueError("项目不存在")

        ws = dict(proj.wizard_state or {})
        comms = list(ws.get("communications", []))

        record = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.utcnow().isoformat(),
            "created_by": str(user_id),
            "date": data.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
            "contact_person": data.get("contact_person", ""),
            "topic": data.get("topic", ""),
            "content": data.get("content", ""),
            "commitments": data.get("commitments", ""),
            "related_wp_codes": data.get("related_wp_codes", []),
            "related_accounts": data.get("related_accounts", []),
        }
        comms.append(record)
        ws["communications"] = comms

        await self.db.execute(
            sa_update(Project).where(Project.id == project_id).values(wizard_state=ws)
        )
        return record

    async def delete_communication(self, project_id: uuid.UUID, comm_id: str) -> bool:
        proj = (await self.db.execute(
            select(Project).where(Project.id == project_id)
        )).scalar_one_or_none()
        if not proj:
            return False
        ws = dict(proj.wizard_state or {})
        comms = [c for c in ws.get("communications", []) if c.get("id") != comm_id]
        ws["communications"] = comms
        await self.db.execute(
            sa_update(Project).where(Project.id == project_id).values(wizard_state=ws)
        )
        return True
