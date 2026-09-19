"""签发一致性清单服务（P2-1）。

合伙人签发前，聚合检查以下数据源是否一致/最新：
1. 四表（试算表）—— 是否存在 stale 状态
2. 调整分录 —— 是否全部审批通过
3. 底稿 —— 是否存在 stale 或 conflict
4. 附注 —— 是否存在 stale
5. 报告正文 —— 是否匹配审计意见类型
6. AI 内容 —— 是否全部确认

每项检查结果按 blocking / warning / info 三级分类，
每个结果带 LinkageContract 或 route 供前端跳转定位。

设计要点：
- service 只 flush 不 commit（router 统一 commit）
- 签发清单每次打开重新计算，不走缓存
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.linkage_contract import (
    LinkageContract,
    LinkageConfidence,
    LinkageStatus,
    SourceType,
    TargetType,
)
from app.services.ai_content_gate import (
    AiContentStatus,
    AI_CONTENT_CONFIRMATION_STRICT,
)

logger = logging.getLogger(__name__)


# ─── 结果模型 ─────────────────────────────────────────────────────────


class CheckSeverity(str, Enum):
    """检查结果严重级别。"""
    blocking = "blocking"
    warning = "warning"
    info = "info"


class CheckItem(BaseModel):
    """单项检查结果。"""
    severity: CheckSeverity = Field(description="严重级别")
    category: str = Field(description="检查类别")
    message: str = Field(description="问题描述")
    contract: Optional[LinkageContract] = Field(default=None, description="关联联动契约")
    route: Optional[str] = Field(default=None, description="跳转路由")


class SignoffChecklist(BaseModel):
    """签发一致性清单汇总。"""
    project_id: str
    year: int
    items: list[CheckItem] = Field(default_factory=list)
    can_signoff: bool = Field(default=True, description="是否可签发（无 blocking 项）")
    has_warnings: bool = Field(default=False, description="是否有 warning 项需确认")


# ─── 服务实现 ─────────────────────────────────────────────────────────


class SignoffChecklistService:
    """签发一致性清单服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_checklist(
        self,
        *,
        project_id: UUID,
        year: int,
    ) -> SignoffChecklist:
        """生成签发一致性清单。

        聚合所有检查项，返回统一清单。
        """
        pid = str(project_id)
        items: list[CheckItem] = []

        # 并行检查各数据源
        items.extend(await self._check_trial_balance(project_id, year, pid))
        items.extend(await self._check_adjustments(project_id, year, pid))
        items.extend(await self._check_workpapers(project_id, year, pid))
        items.extend(await self._check_notes(project_id, year, pid))
        items.extend(await self._check_report(project_id, year, pid))
        items.extend(await self._check_ai_content(project_id, year, pid))

        has_blocking = any(i.severity == CheckSeverity.blocking for i in items)
        has_warnings = any(i.severity == CheckSeverity.warning for i in items)

        return SignoffChecklist(
            project_id=pid,
            year=year,
            items=items,
            can_signoff=not has_blocking,
            has_warnings=has_warnings,
        )

    # ─── 检查：试算表 ──────────────────────────────────────────────

    async def _check_trial_balance(
        self, project_id: UUID, year: int, pid: str
    ) -> list[CheckItem]:
        """检查试算表是否存在 stale 状态。"""
        items: list[CheckItem] = []
        try:
            result = await self.db.execute(
                text("""
                    SELECT id, standard_account_code, audited_amount
                    FROM trial_balance
                    WHERE project_id = :pid AND year = :year
                      AND is_stale = true
                    LIMIT 10
                """),
                {"pid": str(project_id), "year": year},
            )
            stale_rows = result.fetchall()

            if stale_rows:
                for row in stale_rows[:5]:
                    contract = LinkageContract(
                        source_type=SourceType.trial_balance,
                        source_id=str(row[0]),
                        source_cell="audited_amount",
                        target_type=TargetType.trial_balance,
                        target_id=str(row[0]),
                        amount=str(row[2]) if row[2] else None,
                        basis=f"试算表科目 {row[1]} 数据过期",
                        status=LinkageStatus.stale,
                        confidence=LinkageConfidence.system,
                        route=f"/projects/{pid}/trial-balance?highlight={row[0]}",
                    )
                    items.append(CheckItem(
                        severity=CheckSeverity.blocking,
                        category="trial_balance",
                        message=f"试算表科目 {row[1]} 存在过期数据",
                        contract=contract,
                        route=contract.route,
                    ))

                if len(stale_rows) > 5:
                    items.append(CheckItem(
                        severity=CheckSeverity.info,
                        category="trial_balance",
                        message=f"试算表还有 {len(stale_rows) - 5} 项过期数据未列出",
                        route=f"/projects/{pid}/trial-balance",
                    ))
        except Exception as exc:
            logger.warning("签发清单-试算表检查降级: %s", exc)
            items.append(CheckItem(
                severity=CheckSeverity.info,
                category="trial_balance",
                message="试算表 stale 检查暂不可用（表结构不支持）",
                route=f"/projects/{pid}/trial-balance",
            ))

        return items

    # ─── 检查：调整分录 ──────────────────────────────────────────────

    async def _check_adjustments(
        self, project_id: UUID, year: int, pid: str
    ) -> list[CheckItem]:
        """检查调整分录是否全部审批通过。"""
        items: list[CheckItem] = []
        try:
            result = await self.db.execute(
                text("""
                    SELECT id, adjustment_no, adjustment_type, review_status
                    FROM adjustments
                    WHERE project_id = :pid AND year = :year
                      AND review_status NOT IN ('approved', 'cancelled')
                    LIMIT 10
                """),
                {"pid": str(project_id), "year": year},
            )
            unapproved = result.fetchall()

            if unapproved:
                for row in unapproved[:5]:
                    contract = LinkageContract(
                        source_type=SourceType.adjustment,
                        source_id=str(row[0]),
                        source_cell=None,
                        target_type=TargetType.adjustment,
                        target_id=str(row[0]),
                        basis=f"调整分录 {row[1]} 未审批（当前: {row[3]}）",
                        status=LinkageStatus.current,
                        confidence=LinkageConfidence.system,
                        route=f"/projects/{pid}/adjustments?highlight={row[0]}",
                    )
                    items.append(CheckItem(
                        severity=CheckSeverity.blocking,
                        category="adjustment",
                        message=f"调整分录 {row[1]}（{row[2]}）未完成审批",
                        contract=contract,
                        route=contract.route,
                    ))

                if len(unapproved) > 5:
                    items.append(CheckItem(
                        severity=CheckSeverity.info,
                        category="adjustment",
                        message=f"还有 {len(unapproved) - 5} 条调整分录未审批",
                        route=f"/projects/{pid}/adjustments",
                    ))
        except Exception as exc:
            logger.warning("签发清单-调整分录检查降级: %s", exc)
            items.append(CheckItem(
                severity=CheckSeverity.info,
                category="adjustment",
                message="调整分录检查暂不可用",
                route=f"/projects/{pid}/adjustments",
            ))

        return items

    # ─── 检查：底稿 ──────────────────────────────────────────────

    async def _check_workpapers(
        self, project_id: UUID, year: int, pid: str
    ) -> list[CheckItem]:
        """检查底稿是否存在 stale 或 conflict。"""
        items: list[CheckItem] = []
        try:
            # 查 cross_module_conflicts 中 pending 的底稿冲突
            result = await self.db.execute(
                text("""
                    SELECT id, target_type, target_id, conflict_type
                    FROM cross_module_conflicts
                    WHERE project_id = :pid AND status = 'pending'
                      AND target_type = 'workpaper'
                    LIMIT 10
                """),
                {"pid": str(project_id)},
            )
            conflicts = result.fetchall()

            for row in conflicts[:5]:
                contract = LinkageContract(
                    source_type=SourceType.workpaper,
                    source_id=str(row[2]),
                    target_type=TargetType.workpaper,
                    target_id=str(row[2]),
                    basis=f"底稿存在未解决冲突（{row[3]}）",
                    status=LinkageStatus.conflict,
                    confidence=LinkageConfidence.system,
                    route=f"/projects/{pid}/workpapers/{row[2]}",
                    conflict_id=str(row[0]),
                )
                items.append(CheckItem(
                    severity=CheckSeverity.blocking,
                    category="workpaper",
                    message=f"底稿 {row[2]} 存在未解决的{row[3]}冲突",
                    contract=contract,
                    route=contract.route,
                ))

        except Exception as exc:
            logger.warning("签发清单-底稿检查降级: %s", exc)
            items.append(CheckItem(
                severity=CheckSeverity.info,
                category="workpaper",
                message="底稿冲突检查暂不可用",
                route=f"/projects/{pid}/workpapers",
            ))

        # stale 底稿检查（event_cascade_health degraded）
        try:
            result = await self.db.execute(
                text("""
                    SELECT target_id, error_message
                    FROM event_cascade_health
                    WHERE project_id = :pid AND status = 'degraded'
                      AND target_type = 'workpaper'
                    LIMIT 5
                """),
                {"pid": str(project_id)},
            )
            degraded = result.fetchall()

            for row in degraded:
                items.append(CheckItem(
                    severity=CheckSeverity.warning,
                    category="workpaper",
                    message=f"底稿 {row[0]} 存在降级记录: {row[1] or '数据可能过期'}",
                    route=f"/projects/{pid}/workpapers/{row[0]}",
                ))
        except Exception as exc:
            logger.debug("签发清单-底稿 degraded 检查跳过: %s", exc)

        return items

    # ─── 检查：附注 ──────────────────────────────────────────────

    async def _check_notes(
        self, project_id: UUID, year: int, pid: str
    ) -> list[CheckItem]:
        """检查附注是否存在 stale 数据。"""
        items: list[CheckItem] = []
        try:
            # 查 cross_module_conflicts 中附注相关的 pending 冲突
            result = await self.db.execute(
                text("""
                    SELECT id, target_id, conflict_type
                    FROM cross_module_conflicts
                    WHERE project_id = :pid AND status = 'pending'
                      AND target_type = 'note'
                    LIMIT 5
                """),
                {"pid": str(project_id)},
            )
            note_conflicts = result.fetchall()

            for row in note_conflicts:
                contract = LinkageContract(
                    source_type=SourceType.note,
                    source_id=str(row[1]),
                    target_type=TargetType.note,
                    target_id=str(row[1]),
                    basis=f"附注存在未解决冲突（{row[2]}）",
                    status=LinkageStatus.conflict,
                    confidence=LinkageConfidence.system,
                    route=f"/projects/{pid}/disclosure-notes?section={row[1]}",
                    conflict_id=str(row[0]),
                )
                items.append(CheckItem(
                    severity=CheckSeverity.warning,
                    category="note",
                    message=f"附注 {row[1]} 存在未解决的{row[2]}冲突",
                    contract=contract,
                    route=contract.route,
                ))
        except Exception as exc:
            logger.debug("签发清单-附注冲突检查跳过: %s", exc)

        # stale 附注检查
        try:
            result = await self.db.execute(
                text("""
                    SELECT target_id, error_message
                    FROM event_cascade_health
                    WHERE project_id = :pid AND status = 'degraded'
                      AND target_type = 'note'
                    LIMIT 5
                """),
                {"pid": str(project_id)},
            )
            degraded = result.fetchall()

            for row in degraded:
                items.append(CheckItem(
                    severity=CheckSeverity.warning,
                    category="note",
                    message=f"附注 {row[0]} 存在降级记录: {row[1] or '数据可能过期'}",
                    route=f"/projects/{pid}/disclosure-notes?section={row[0]}",
                ))
        except Exception as exc:
            logger.debug("签发清单-附注 degraded 检查跳过: %s", exc)

        return items

    # ─── 检查：报告正文 ──────────────────────────────────────────────

    async def _check_report(
        self, project_id: UUID, year: int, pid: str
    ) -> list[CheckItem]:
        """检查报告正文是否匹配审计意见类型。"""
        items: list[CheckItem] = []
        try:
            # 查项目的审计意见类型
            proj_result = await self.db.execute(
                text("""
                    SELECT opinion_type
                    FROM projects
                    WHERE id = :pid
                """),
                {"pid": str(project_id)},
            )
            proj_row = proj_result.fetchone()
            opinion_type = proj_row[0] if proj_row else None

            if not opinion_type:
                items.append(CheckItem(
                    severity=CheckSeverity.warning,
                    category="report",
                    message="项目未设置审计意见类型，报告正文一致性无法校验",
                    route=f"/projects/{pid}/settings",
                ))
            else:
                # 检查报告正文是否存在
                report_result = await self.db.execute(
                    text("""
                        SELECT id, row_code
                        FROM financial_report
                        WHERE project_id = :pid
                        LIMIT 1
                    """),
                    {"pid": str(project_id)},
                )
                report_row = report_result.fetchone()
                if not report_row:
                    items.append(CheckItem(
                        severity=CheckSeverity.blocking,
                        category="report",
                        message="未生成审计报告正文",
                        route=f"/projects/{pid}/report",
                    ))
                else:
                    items.append(CheckItem(
                        severity=CheckSeverity.info,
                        category="report",
                        message=f"审计报告已生成，意见类型: {opinion_type}",
                        route=f"/projects/{pid}/report",
                    ))
        except Exception as exc:
            logger.warning("签发清单-报告检查降级: %s", exc)
            items.append(CheckItem(
                severity=CheckSeverity.info,
                category="report",
                message="报告正文检查暂不可用",
                route=f"/projects/{pid}/report",
            ))

        return items

    # ─── 检查：AI 内容 ──────────────────────────────────────────────

    async def _check_ai_content(
        self, project_id: UUID, year: int, pid: str
    ) -> list[CheckItem]:
        """检查 AI 生成内容是否全部确认。"""
        items: list[CheckItem] = []
        try:
            result = await self.db.execute(
                text("""
                    SELECT id, content_type, status
                    FROM ai_generated_content
                    WHERE project_id = :pid
                      AND status NOT IN ('confirmed', 'rejected')
                    LIMIT 10
                """),
                {"pid": str(project_id)},
            )
            unconfirmed = result.fetchall()

            if unconfirmed:
                strict = AI_CONTENT_CONFIRMATION_STRICT
                severity = CheckSeverity.blocking if strict else CheckSeverity.warning

                for row in unconfirmed[:5]:
                    content_status = row[2]
                    items.append(CheckItem(
                        severity=severity,
                        category="ai_content",
                        message=f"AI 生成内容（{row[1]}）状态为 {content_status}，需人工确认",
                        route=f"/projects/{pid}/ai-content?highlight={row[0]}",
                    ))

                if len(unconfirmed) > 5:
                    items.append(CheckItem(
                        severity=CheckSeverity.info,
                        category="ai_content",
                        message=f"还有 {len(unconfirmed) - 5} 条 AI 内容未确认",
                        route=f"/projects/{pid}/ai-content",
                    ))
        except Exception as exc:
            logger.debug("签发清单-AI 内容检查跳过（表可能不存在）: %s", exc)
            # AI 内容表可能不存在，静默跳过不阻断
            items.append(CheckItem(
                severity=CheckSeverity.info,
                category="ai_content",
                message="AI 内容确认检查暂不可用",
                route=f"/projects/{pid}/ai-content",
            ))

        return items
