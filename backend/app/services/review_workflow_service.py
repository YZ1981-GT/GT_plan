"""复核流程服务

A21~A25 作为复核对话的汇总视图：
- 从 review_checklist_templates.json 加载检查要点模板
- 按角色+审计类型匹配正确模板
- 聚合已关联该检查项的复核对话记录
- 自动检查项从系统状态取值
- 保存复核记录+意见
- 生成归档 Excel
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase10_models import ReviewConversation
from app.models.review_workflow_models import ReviewChecklistRecord

_logger = logging.getLogger(__name__)
_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "review_checklist_templates.json"


@lru_cache(maxsize=1)
def _load_templates() -> dict[str, Any]:
    with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class ReviewWorkflowService:
    """复核流程服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_review_panel(
        self,
        project_id: UUID,
        year: int,
        role: str,
        audit_type: str = "financial",
        business_category: str = "C",
    ) -> dict[str, Any]:
        """获取指定角色的复核面板数据（检查要点 + 关联对话 + 自动检查）"""
        template = self._get_template_for_role(role, audit_type, business_category)
        if not template:
            return {"error": f"未找到角色 {role} 对应的复核模板"}

        code = template["code"]

        # 加载已保存的复核记录
        saved = await self._get_saved_review(project_id, year, code)

        # 加载关联的复核对话
        conversations_by_item = await self._get_linked_conversations(project_id, code)

        # 未关联的对话
        unlinked = await self._get_unlinked_conversations(project_id)

        # 构建面板数据
        items = []
        for item in template["items"]:
            seq = item["seq"]
            ref_key = f"{code}:{seq}"

            # 自动检查项
            auto_result = None
            if item.get("auto_check"):
                auto_result = await self._resolve_auto_check(item["auto_check"], project_id, year)

            # 已保存的勾选状态
            saved_item = next((s for s in (saved.get("items") or []) if s.get("seq") == seq), None)

            items.append({
                "seq": seq,
                "content": item["content"],
                "auto_check": item.get("auto_check"),
                "auto_result": auto_result,
                "checked": saved_item.get("checked", False) if saved_item else False,
                "remark": saved_item.get("remark", "") if saved_item else "",
                "ref_key": ref_key,
                "conversations": conversations_by_item.get(ref_key, []),
            })

        return {
            "template_code": code,
            "title": template["title"],
            "role": template["role"],
            "items": items,
            "opinion": saved.get("opinion", ""),
            "status": saved.get("status", "draft"),
            "unlinked_conversations": unlinked,
        }

    async def save_review(
        self,
        project_id: UUID,
        year: int,
        template_code: str,
        reviewer_id: UUID,
        items: list[dict],
        opinion: str = "",
        submit: bool = False,
    ) -> dict[str, Any]:
        """保存复核记录（勾选+意见）

        ⚠️ A21~A25 新写入请走 checklist_responses + POST review-sign；
        本方法保留旧 ReviewChecklistRecord 路径供历史面板只读兼容。
        """
        stmt = sa.select(ReviewChecklistRecord).where(
            ReviewChecklistRecord.project_id == project_id,
            ReviewChecklistRecord.year == year,
            ReviewChecklistRecord.template_code == template_code,
            ReviewChecklistRecord.reviewer_id == reviewer_id,
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        status = "submitted" if submit else "draft"

        if record:
            record.items = items
            record.opinion = opinion
            record.status = status
            record.updated_at = now
            if submit:
                record.submitted_at = now
        else:
            record = ReviewChecklistRecord(
                project_id=project_id,
                year=year,
                template_code=template_code,
                reviewer_id=reviewer_id,
                items=items,
                opinion=opinion,
                status=status,
                submitted_at=now if submit else None,
            )
            self.db.add(record)

        await self.db.flush()

        # P1-4: 提交后推送 SSE 通知下一级复核人
        if submit:
            try:
                from app.core.event_bus import event_bus
                from app.models.audit_platform_schemas import EventPayload, EventType
                event_bus.broadcast_raw(
                    "review_submitted",
                    {"project_id": str(project_id), "year": year, "template_code": template_code, "reviewer_id": str(reviewer_id)},
                )
            except Exception:
                pass  # 通知失败不阻塞主流程

        return {"success": True, "status": status, "all_checked": all(i.get("checked") for i in items)}

    async def link_conversation(
        self, conversation_id: UUID, checklist_ref: str
    ) -> bool:
        """将复核对话关联到检查要点"""
        stmt = sa.select(ReviewConversation).where(
            ReviewConversation.id == conversation_id
        )
        result = await self.db.execute(stmt)
        conv = result.scalar_one_or_none()
        if conv:
            conv.checklist_ref = checklist_ref
            await self.db.flush()
            return True
        return False

    async def unlink_conversation(self, conversation_id: UUID) -> bool:
        """取消复核对话与检查要点的关联"""
        stmt = sa.select(ReviewConversation).where(
            ReviewConversation.id == conversation_id
        )
        result = await self.db.execute(stmt)
        conv = result.scalar_one_or_none()
        if conv:
            conv.checklist_ref = None
            await self.db.flush()
            return True
        return False

    async def get_completion_checklist(
        self, project_id: UUID, year: int, project_type: str = "general"
    ) -> dict[str, Any]:
        """A17-5 完成核对表（签发前置关卡）"""
        templates = _load_templates()
        checklists = templates.get("completion_checklists", {})

        # 按项目类型匹配
        matched = None
        for code, checklist in checklists.items():
            if checklist.get("project_type") == project_type:
                matched = checklist
                break
        if not matched:
            matched = checklists.get("A17-5-1", {})  # fallback to general

        items = []
        for item in matched.get("items", []):
            auto_result = None
            if item.get("auto_check"):
                auto_result = await self._resolve_auto_check(item["auto_check"], project_id, year)
            items.append({
                "seq": item["seq"],
                "content": item["content"],
                "auto_result": auto_result,
                "auto_pass": auto_result == "通过" if auto_result else None,
            })

        all_pass = all(i.get("auto_pass") is not False for i in items)
        return {
            "code": matched.get("code", "A17-5-1"),
            "title": matched.get("title", ""),
            "items": items,
            "can_proceed": all_pass,
        }

    async def generate_archive_file(
        self, project_id: UUID, year: int, template_code: str | None = None
    ) -> bytes:
        """生成 A21~A25 归档 Excel（致同标准格式）"""
        import io
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = openpyxl.Workbook()
        header_font = Font(bold=True)
        header_fill = PatternFill(start_color="F4F0FA", end_color="F4F0FA", fill_type="solid")
        title_font = Font(bold=True, size=14, color="4B2D77")
        thin_border = Border(
            left=Side(style="thin"), right=Side(style="thin"),
            top=Side(style="thin"), bottom=Side(style="thin"),
        )

        templates = _load_templates()["templates"]
        codes_to_export = [template_code] if template_code else list(templates.keys())

        first_sheet = True
        for code in codes_to_export:
            tmpl = templates.get(code)
            if not tmpl:
                continue

            if first_sheet:
                ws = wb.active
                ws.title = code
                first_sheet = False
            else:
                ws = wb.create_sheet(code)

            # 致同标准表头
            ws.merge_cells("A1:E1")
            ws["A1"] = "致同会计师事务所（特殊普通合伙）"
            ws["A1"].font = Font(size=10, color="666666")
            ws["A1"].alignment = Alignment(horizontal="center")

            ws.merge_cells("A2:E2")
            ws["A2"] = tmpl["title"]
            ws["A2"].font = title_font
            ws["A2"].alignment = Alignment(horizontal="center")

            ws["A3"] = f"项目年度：{year}"
            ws["A3"].font = Font(size=9, color="666666")

            # 表头行
            row_start = 5
            headers = ["序号", "检查要点", "是否通过", "备注", "关联对话"]
            for col, h in enumerate(headers, 1):
                cell = ws.cell(row=row_start, column=col, value=h)
                cell.font = header_font
                cell.fill = header_fill
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="center")

            # 设置列宽
            ws.column_dimensions["A"].width = 8
            ws.column_dimensions["B"].width = 45
            ws.column_dimensions["C"].width = 12
            ws.column_dimensions["D"].width = 25
            ws.column_dimensions["E"].width = 20

            # Load saved review
            saved = await self._get_saved_review(project_id, year, code)
            saved_items = {s["seq"]: s for s in (saved.get("items") or [])}

            for i, item in enumerate(tmpl["items"]):
                seq = item["seq"]
                si = saved_items.get(seq, {})
                row_num = row_start + 1 + i
                ws.cell(row=row_num, column=1, value=seq).border = thin_border
                ws.cell(row=row_num, column=2, value=item["content"]).border = thin_border
                check_cell = ws.cell(row=row_num, column=3, value="✓" if si.get("checked") else "")
                check_cell.border = thin_border
                check_cell.alignment = Alignment(horizontal="center")
                ws.cell(row=row_num, column=4, value=si.get("remark", "")).border = thin_border
                ws.cell(row=row_num, column=5, value="").border = thin_border

            # 复核意见
            opinion_row = row_start + len(tmpl["items"]) + 2
            ws.cell(row=opinion_row, column=1, value="复核意见：")
            ws.cell(row=opinion_row, column=1).font = Font(bold=True)
            ws.merge_cells(start_row=opinion_row, start_column=2, end_row=opinion_row, end_column=5)
            ws.cell(row=opinion_row, column=2, value=saved.get("opinion", ""))

            # 签名行
            sign_row = opinion_row + 2
            ws.cell(row=sign_row, column=1, value="复核人签名：")
            ws.cell(row=sign_row, column=3, value="日期：")

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    async def get_review_progress(self, project_id: UUID, year: int) -> dict[str, Any]:
        """获取复核阶段进度 — 读 checklist_responses -sign（不再写 ReviewChecklistRecord）。"""
        from app.services.review_checklist_service import get_review_sign_status_batch

        statuses = await get_review_sign_status_batch(self.db, project_id)
        total_levels = len(statuses) or 5
        submitted = sum(1 for v in statuses.values() if v == "pass")
        return {
            "total_levels": total_levels,
            "submitted": submitted,
            "progress_pct": round(submitted / total_levels * 100) if total_levels else 0,
            "records": [{"code": k, "status": v or "draft"} for k, v in statuses.items()],
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_template_for_role(
        self, role: str, audit_type: str, business_category: str
    ) -> dict | None:
        """按角色+审计类型匹配模板"""
        templates = _load_templates()["templates"]
        for code, tmpl in templates.items():
            if tmpl["role"] == role and tmpl["audit_type"] == audit_type:
                # A类专属检查
                if tmpl.get("a_only") and business_category != "A":
                    continue
                return tmpl
        return None

    async def _get_saved_review(self, project_id: UUID, year: int, template_code: str) -> dict:
        """获取已保存的复核记录"""
        stmt = sa.select(ReviewChecklistRecord).where(
            ReviewChecklistRecord.project_id == project_id,
            ReviewChecklistRecord.year == year,
            ReviewChecklistRecord.template_code == template_code,
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        if record:
            return {
                "items": record.items or [],
                "opinion": record.opinion or "",
                "status": record.status,
            }
        return {}

    async def _get_linked_conversations(
        self, project_id: UUID, template_code: str
    ) -> dict[str, list[dict]]:
        """获取已关联到该模板各检查项的复核对话（含最新2条消息）"""
        from app.models.phase10_models import ReviewMessage

        prefix = f"{template_code}:"
        stmt = sa.select(
            ReviewConversation.id,
            ReviewConversation.checklist_ref,
            ReviewConversation.title,
            ReviewConversation.status,
            ReviewConversation.initiator_id,
            ReviewConversation.created_at,
        ).where(
            ReviewConversation.project_id == project_id,
            ReviewConversation.checklist_ref.ilike(f"{prefix}%"),
            ReviewConversation.is_deleted == sa.false(),
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        grouped: dict[str, list[dict]] = {}
        for row in rows:
            ref = row.checklist_ref
            if ref not in grouped:
                grouped[ref] = []

            # 获取最新2条消息
            msg_stmt = sa.select(
                ReviewMessage.sender_id,
                ReviewMessage.content,
                ReviewMessage.created_at,
            ).where(
                ReviewMessage.conversation_id == row.id,
            ).order_by(ReviewMessage.created_at.desc()).limit(2)
            msg_result = await self.db.execute(msg_stmt)
            messages = [
                {"sender_id": str(m.sender_id), "content": m.content[:100], "created_at": m.created_at.isoformat() if m.created_at else None}
                for m in msg_result.all()
            ]

            grouped[ref].append({
                "id": str(row.id),
                "title": row.title,
                "status": row.status,
                "initiator_id": str(row.initiator_id),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "recent_messages": list(reversed(messages)),
            })
        return grouped

    async def _get_unlinked_conversations(self, project_id: UUID) -> list[dict]:
        """获取未关联检查项的复核对话（供手动归类）"""
        stmt = sa.select(
            ReviewConversation.id,
            ReviewConversation.title,
            ReviewConversation.status,
            ReviewConversation.related_object_type,
            ReviewConversation.created_at,
        ).where(
            ReviewConversation.project_id == project_id,
            ReviewConversation.checklist_ref.is_(None),
            ReviewConversation.is_deleted == sa.false(),
        ).order_by(ReviewConversation.created_at.desc()).limit(50)
        result = await self.db.execute(stmt)
        return [
            {
                "id": str(row.id),
                "title": row.title,
                "status": row.status,
                "related_object_type": row.related_object_type,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in result.all()
        ]

    async def _resolve_auto_check(self, check_type: str, project_id: UUID, year: int) -> str | None:
        """解析自动检查项"""
        try:
            if check_type == "workpaper_plan_coverage":
                from app.models.workpaper_models import WorkingPaper
                total_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                )
                done_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WorkingPaper.status.in_(["completed", "reviewed", "edit_complete"]),
                )
                total_r = await self.db.execute(total_stmt)
                done_r = await self.db.execute(done_stmt)
                total = total_r.scalar() or 0
                done = done_r.scalar() or 0
                if total == 0:
                    return "无底稿"
                pct = round(done / total * 100)
                return f"覆盖 {done}/{total} 张（{pct}%）" if done < total else "通过（全部完成）"
            elif check_type == "workpaper_quality_check":
                from app.models.phase15_models import IssueTicket
                stmt = sa.select(sa.func.count()).select_from(IssueTicket).where(
                    IssueTicket.project_id == project_id,
                    IssueTicket.status.notin_(["closed", "rejected"]),
                )
                result = await self.db.execute(stmt)
                open_issues = result.scalar() or 0
                return "通过" if open_issues == 0 else f"待处理 {open_issues} 项"
            elif check_type == "confirmation_status":
                from app.models.confirmation_models import Confirmation
                total_stmt = sa.select(sa.func.count()).select_from(Confirmation).where(
                    Confirmation.project_id == project_id,
                )
                returned_stmt = sa.select(sa.func.count()).select_from(Confirmation).where(
                    Confirmation.project_id == project_id,
                    Confirmation.status.in_(["returned", "matched", "discrepancy"]),
                )
                total_r = await self.db.execute(total_stmt)
                returned_r = await self.db.execute(returned_stmt)
                total = total_r.scalar() or 0
                returned = returned_r.scalar() or 0
                if total == 0:
                    return "无函证"
                return f"已回 {returned}/{total} 封" if returned < total else "通过（全部回函）"
            elif check_type == "materiality_set":
                from app.models.audit_platform_models import Materiality
                stmt = sa.select(Materiality.overall_materiality).where(
                    Materiality.project_id == project_id
                )
                result = await self.db.execute(stmt)
                val = result.scalar_one_or_none()
                return f"重要性水平 {val:,.0f} 元" if val else "待设置"
            elif check_type == "adjustment_review_status":
                from app.models.audit_platform_models import Adjustment
                stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
                    Adjustment.project_id == project_id,
                    Adjustment.year == year,
                    Adjustment.review_status == "pending",
                    Adjustment.is_deleted == sa.false(),
                )
                result = await self.db.execute(stmt)
                pending = result.scalar() or 0
                return "通过" if pending == 0 else f"待审批{pending}笔"
            elif check_type == "independence_signing_status":
                from app.models.review_workflow_models import IndependenceSigningTask
                stmt = sa.select(
                    sa.func.count(),
                    sa.func.count().filter(IndependenceSigningTask.status == "signed"),
                ).where(IndependenceSigningTask.project_id == project_id)
                result = await self.db.execute(stmt)
                total, signed = result.one()
                if total == 0:
                    return "未发起"
                return "通过" if signed == total else f"已签{signed}/{total}"
            elif check_type == "all_procedures_done":
                from app.models.workpaper_models import WorkingPaper
                total_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                )
                done_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WorkingPaper.status.in_(["completed", "reviewed"]),
                )
                total_r = await self.db.execute(total_stmt)
                done_r = await self.db.execute(done_stmt)
                total = total_r.scalar() or 0
                done = done_r.scalar() or 0
                return "通过" if done == total and total > 0 else f"完成{done}/{total}"
            elif check_type == "all_workpapers_reviewed":
                from app.models.workpaper_models import WorkingPaper
                total_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                )
                reviewed_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WorkingPaper.status == "reviewed",
                )
                total_r = await self.db.execute(total_stmt)
                reviewed_r = await self.db.execute(reviewed_stmt)
                total = total_r.scalar() or 0
                reviewed = reviewed_r.scalar() or 0
                if total == 0:
                    return "无底稿"
                return "通过" if reviewed == total else f"已复核{reviewed}/{total}"
            elif check_type == "all_adjustments_approved":
                from app.models.audit_platform_models import Adjustment
                # 已处理 = 已批准(approved) 或 已 Passed(不予更正, passed_reason 非空)。
                # 待处理 = 未批准 且 未 Passed。review_status 枚举无 'passed' 值，
                # 故 Passed 用 passed_reason IS NULL 判定（避免无效枚举比较报错）。
                stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
                    Adjustment.project_id == project_id,
                    Adjustment.year == year,
                    Adjustment.review_status != "approved",
                    Adjustment.passed_reason.is_(None),
                    Adjustment.is_deleted == sa.false(),
                )
                result = await self.db.execute(stmt)
                pending = result.scalar() or 0
                return "通过" if pending == 0 else f"待处理{pending}笔"
            elif check_type == "representation_letter_signed":
                # A16 管理层声明书签回状态（从 field_overrides 读）
                from app.services.field_override_service import FieldOverrideService
                svc = FieldOverrideService(self.db)
                overrides = await svc.get_batch(project_id, year, "word_template:A16")
                sign_data = overrides.get("sign_status", {})
                status = sign_data.get("value") if isinstance(sign_data, dict) else sign_data
                if status == "signed":
                    sign_date = overrides.get("sign_date", {})
                    date_val = sign_date.get("value") if isinstance(sign_date, dict) else sign_date
                    if date_val:
                        return f"通过（{date_val} 签回）"
                    return "通过（已签回）"
                elif status == "sent":
                    return "未通过（已发送，待签回）"
                return "未通过（声明书未发送）"
            elif check_type == "signoff_readiness":
                # 聚合签发阻断项：stale + 未复核底稿 + 未批调整 + AI 未确认
                blockers = []
                # 1) 未批调整
                from app.models.audit_platform_models import Adjustment
                adj_stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
                    Adjustment.project_id == project_id,
                    Adjustment.year == year,
                    Adjustment.review_status != "approved",
                    Adjustment.passed_reason.is_(None),
                    Adjustment.is_deleted == sa.false(),
                )
                adj_r = await self.db.execute(adj_stmt)
                adj_pending = adj_r.scalar() or 0
                if adj_pending > 0:
                    blockers.append(f"调整{adj_pending}笔待审")
                # 2) 未复核底稿
                from app.models.workpaper_models import WorkingPaper
                unreview_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WorkingPaper.status.notin_(["reviewed", "completed"]),
                )
                unreview_r = await self.db.execute(unreview_stmt)
                unreview = unreview_r.scalar() or 0
                if unreview > 0:
                    blockers.append(f"底稿{unreview}张未完成")
                # 3) 问题单未关闭
                from app.models.phase15_models import IssueTicket
                issue_stmt = sa.select(sa.func.count()).select_from(IssueTicket).where(
                    IssueTicket.project_id == project_id,
                    IssueTicket.severity.in_(["blocker", "major"]),
                    IssueTicket.status.notin_(["closed", "rejected"]),
                )
                issue_r = await self.db.execute(issue_stmt)
                open_issues = issue_r.scalar() or 0
                if open_issues > 0:
                    blockers.append(f"重大问题{open_issues}项")
                if not blockers:
                    return "通过（可签发）"
                return "⚠️ " + "；".join(blockers)
        except Exception as e:
            _logger.warning("auto_check %s failed: %s", check_type, e)
        return None


def invalidate_cache() -> None:
    _load_templates.cache_clear()
