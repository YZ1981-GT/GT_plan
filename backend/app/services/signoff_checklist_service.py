"""签发一致性清单服务（合伙人签字页）。

合伙人签发前逐项核对：试算表审定数不变式、调整分录审批、跨模块冲突、审计报告、数据过期、AI 内容确认。
每项结果按 blocking / warning / info 分级，带可跳转的前端路由（无页面可跳则为 None）。

设计要点（spec deliverable-writeback-and-online-edit-integrity §1）：
- **每项检查在独立 SAVEPOINT 内执行，失败即 blocking（fail-closed）**。历史实现 9 条裸 SQL 有 8 条对真实 schema 无效、
  又共用一个会话无 SAVEPOINT：首条失败使事务中止，其余全部失败，再各自降级成 info「暂不可用」⇒ 真实 PG 上恒
  ``can_signoff = true``（四个真实项目实测）。「检查不了」不等于「没问题」。
- 只用真实 schema / 既有权威实现：试算表 ``TrialBalanceService.check_consistency``、跨模块冲突
  ``conflict_resolution_service``（与签字门禁规则同口径）、过期汇总 ``stale_summary_aggregate.get_full_summary``
  （与签字页「项目状态摘要」同源）。
- service 只 flush 不 commit；每次打开实时计算，不走缓存。
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Awaitable, Callable, Optional
from uuid import UUID

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.linkage_contract import LinkageContract
from app.services import ai_content_gate

logger = logging.getLogger(__name__)

#: 每类列出的明细上限（其余以一条 info 汇总计数）
_LIST_LIMIT = 5

_OPINION_LABELS = {
    "unqualified": "无保留意见",
    "qualified": "保留意见",
    "adverse": "否定意见",
    "disclaimer": "无法表示意见",
}
_REPORT_STATUS_LABELS = {"draft": "草稿", "review": "复核中", "eqcr_approved": "EQCR 已通过", "final": "定稿"}
_AI_CONTENT_TYPE_LABELS = {
    "data_fill": "数据填充",
    "analytical_review": "分析性复核",
    "risk_alert": "风险提示",
    "test_summary": "测试汇总",
    "note_draft": "附注草稿",
    "review_finding": "复核发现",
}


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
    route: Optional[str] = Field(default=None, description="跳转路由（前端真实存在的页面；无则为空）")


class SignoffChecklist(BaseModel):
    """签发一致性清单汇总。"""
    project_id: str
    year: int
    items: list[CheckItem] = Field(default_factory=list)
    can_signoff: bool = Field(default=True, description="是否可签发（无 blocking 项）")
    has_warnings: bool = Field(default=False, description="是否有 warning 项需确认")


CheckFn = Callable[[UUID, int, str], Awaitable[list[CheckItem]]]


# ─── 服务实现 ─────────────────────────────────────────────────────────


class SignoffChecklistService:
    """签发一致性清单服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _checks(self) -> list[tuple[str, str, CheckFn]]:
        """(category, 中文名, 检查函数)，按清单展示顺序。"""
        return [
            ("trial_balance", "试算表", self._check_trial_balance),
            ("adjustment", "调整分录", self._check_adjustments),
            ("conflict", "跨模块冲突", self._check_conflicts),
            ("report", "审计报告", self._check_report),
            ("stale", "数据过期", self._check_stale),
            ("ai_content", "AI 内容", self._check_ai_content),
        ]

    async def generate_checklist(self, *, project_id: UUID, year: int) -> SignoffChecklist:
        """生成签发一致性清单（逐项独立执行，任一项失败按阻断处理）。"""
        pid = str(project_id)
        items: list[CheckItem] = []
        for category, label, fn in self._checks():
            items.extend(await self._run_check(category, label, fn, project_id, year, pid))

        has_blocking = any(i.severity == CheckSeverity.blocking for i in items)
        has_warnings = any(i.severity == CheckSeverity.warning for i in items)
        return SignoffChecklist(
            project_id=pid,
            year=year,
            items=items,
            can_signoff=not has_blocking,
            has_warnings=has_warnings,
        )

    async def _run_check(
        self, category: str, label: str, fn: CheckFn, project_id: UUID, year: int, pid: str
    ) -> list[CheckItem]:
        """在独立 SAVEPOINT 内跑一项检查；失败只回滚本项并产出阻断项（fail-closed）。"""
        try:
            async with self.db.begin_nested():
                return await fn(project_id, year, pid)
        except Exception as exc:  # noqa: BLE001 — 失败即阻断，原因写进清单与日志
            logger.warning("签发清单-%s检查执行失败 project=%s year=%s: %s", label, pid, year, exc, exc_info=True)
            return [CheckItem(
                severity=CheckSeverity.blocking,
                category=category,
                message=f"{label}检查执行失败，无法确认一致性（{type(exc).__name__}），请联系管理员处理后再签发",
                route=None,
            )]

    # ─── 检查：试算表（审定数 = 未审数 + RJE + AJE + 底稿调整） ─────────────

    async def _check_trial_balance(self, project_id: UUID, year: int, pid: str) -> list[CheckItem]:
        """试算表没有「过期」状态（审批调整分录即同步重算），签发前核对的是审定数不变式。"""
        from app.models.audit_platform_models import TrialBalance
        from app.services.trial_balance_service import TrialBalanceService

        route = f"/projects/{pid}/trial-balance"
        total = (await self.db.execute(
            sa.select(sa.func.count()).select_from(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
        )).scalar_one()
        if not total:
            return [_item(CheckSeverity.blocking, "trial_balance", f"{year} 年度试算表无数据，报表数字无来源", route)]

        issues = await TrialBalanceService(self.db).check_consistency(project_id, year)
        if not issues:
            return [_item(CheckSeverity.info, "trial_balance",
                          f"试算表 {total} 个科目审定数与「未审数 + 调整数」一致", route)]
        items = [
            _item(CheckSeverity.blocking, "trial_balance",
                  f"试算表科目 {i.get('account_code')} 审定数 {i.get('actual')} 与「未审数 + 调整数」{i.get('expected')} 不一致",
                  route)
            for i in issues[:_LIST_LIMIT]
        ]
        return items + _more(issues, "trial_balance", "个试算表科目审定数不一致", route)

    # ─── 检查：调整分录审批 ─────────────────────────────────────────────

    async def _check_adjustments(self, project_id: UUID, year: int, pid: str) -> list[CheckItem]:
        """草稿 / 待复核的调整分录未进入试算表（只有已审批才计入），签发前必须处理完。"""
        from app.models.audit_platform_models import Adjustment

        route = f"/projects/{pid}/adjustments"
        cond = (
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.is_deleted == sa.false(),
            Adjustment.review_status.in_(("draft", "pending_review")),
        )
        rows = (await self.db.execute(
            sa.select(Adjustment.adjustment_no, Adjustment.adjustment_type, Adjustment.review_status)
            .where(*cond).distinct().order_by(Adjustment.adjustment_no)
        )).all()
        if not rows:
            return [_item(CheckSeverity.info, "adjustment", "调整分录均已审批（或无调整分录）", route)]
        items = [
            _item(CheckSeverity.blocking, "adjustment",
                  f"调整分录 {no}（{_ADJ_TYPE_LABELS.get(_val(t), _val(t))}）{_ADJ_STATUS_LABELS.get(_val(s), _val(s))}，"
                  "未完成审批、未计入试算表", route)
            for no, t, s in rows[:_LIST_LIMIT]
        ]
        return items + _more(rows, "adjustment", "笔调整分录未完成审批", route)

    # ─── 检查：跨模块冲突（与签字门禁 V3-CROSS-MODULE-CONFLICT-UNRESOLVED 同口径） ─

    async def _check_conflicts(self, project_id: UUID, year: int, pid: str) -> list[CheckItem]:
        from app.services import conflict_resolution_service as crs

        total = await crs.count_pending(db=self.db, project_id=project_id)
        if not total:
            return [_item(CheckSeverity.info, "conflict", "无未调解的跨模块冲突", None)]
        rows = await crs.list_pending(db=self.db, project_id=project_id, limit=_LIST_LIMIT)
        items = []
        for c in rows:
            route = (f"/projects/{pid}/workpapers/{c.target_id}/edit" if c.target_module == "workpaper"
                     else f"/projects/{pid}/disclosure-notes" if c.target_module == "disclosure" else None)
            items.append(_item(
                CheckSeverity.blocking, "conflict",
                f"{_MODULE_LABELS.get(c.source_module, c.source_module)} → {_MODULE_LABELS.get(c.target_module, c.target_module)}"
                f"「{c.target_field}」存在未调解冲突（上游值与手工值不一致）", route,
            ))
        return items + _more(int(total), "conflict", "条跨模块冲突未调解", None)

    # ─── 检查：审计报告（报告正文） ───────────────────────────────────────

    async def _check_report(self, project_id: UUID, year: int, pid: str) -> list[CheckItem]:
        from app.models.report_models import AuditReport

        route = f"/projects/{pid}/audit-report"
        report = (await self.db.execute(
            sa.select(AuditReport).where(
                AuditReport.project_id == project_id,
                AuditReport.year == year,
                AuditReport.is_deleted == sa.false(),
            ).limit(1)
        )).scalar_one_or_none()
        if report is None:
            return [_item(CheckSeverity.blocking, "report", f"未生成 {year} 年度审计报告（报告正文），无法签发", route)]
        opinion = _OPINION_LABELS.get(_val(report.opinion_type), _val(report.opinion_type) or "未设置")
        status = _REPORT_STATUS_LABELS.get(_val(report.status), _val(report.status) or "未知")
        items = [_item(CheckSeverity.info, "report", f"审计报告已生成（{status}），意见类型：{opinion}", route)]
        if report.is_stale:
            items.append(_item(CheckSeverity.warning, "report",
                               "报告正文所依据的数据已变更（已标记过期），建议重新生成后再签发", route))
        return items

    # ─── 检查：数据过期（与签字页「项目状态摘要」同源） ─────────────────────

    async def _check_stale(self, project_id: UUID, year: int, pid: str) -> list[CheckItem]:
        from app.services.stale_summary_aggregate import get_full_summary

        summary = await get_full_summary(self.db, project_id, year)
        items: list[CheckItem] = []
        wp = summary.get("workpapers") or {}
        n_wp = int(wp.get("stale") or 0) + int(wp.get("inconsistent") or 0)
        if n_wp:
            names = _names(wp.get("items"), lambda r: r.get("wp_code") or r.get("wp_name"))
            items.append(_item(CheckSeverity.warning, "stale",
                               f"{n_wp} 张底稿预填数据过期或与上游不一致{names}，签发前建议刷新",
                               f"/projects/{pid}/workpapers"))
        rpt = summary.get("reports") or {}
        if int(rpt.get("stale") or 0):
            names = _names(rpt.get("items"), lambda r: r.get("row_name") or r.get("row_code"))
            items.append(_item(CheckSeverity.warning, "stale",
                               f"{rpt['stale']} 个报表行标记为过期{names}，建议重新生成报表",
                               f"/projects/{pid}/reports"))
        notes = summary.get("notes") or {}
        if int(notes.get("stale") or 0):
            names = _names(notes.get("items"), lambda r: r.get("note_section"))
            items.append(_item(CheckSeverity.warning, "stale",
                               f"{notes['stale']} 个附注章节标记为过期{names}，建议刷新附注",
                               f"/projects/{pid}/disclosure-notes"))
        miss = summary.get("misstatements") or {}
        if miss.get("unavailable"):
            # 汇总服务内部降级成 0 的部分：对签发而言「查不了」必须按阻断处理（fail-closed）
            items.append(_item(CheckSeverity.blocking, "stale",
                               "未更正错报重新评估检查执行失败，无法确认，请联系管理员处理后再签发",
                               f"/projects/{pid}/misstatements"))
        elif int(miss.get("recheck_needed") or 0):
            items.append(_item(CheckSeverity.warning, "stale",
                               f"{miss['recheck_needed']} 条未更正错报在重要性水平变更后未重新评估",
                               f"/projects/{pid}/misstatements"))
        if not items:
            items.append(_item(CheckSeverity.info, "stale", "底稿、报表、附注、未更正错报均无过期标记", None))
        return items

    # ─── 检查：AI 内容确认 ─────────────────────────────────────────────

    async def _check_ai_content(self, project_id: UUID, year: int, pid: str) -> list[CheckItem]:
        """两张真表：底稿 AI 内容 ``ai_content``（pending 待确认）+ 证据治理 AI 输出 ``ai_content_governance``
        （draft / revised / stale 待确认，按审计年度）。strict 开关开启时阻断，否则提示。"""
        from app.models.ai_models import AIConfirmationStatus, AIContent
        from app.models.evidence_governance_models import AiContentGovernance

        # 运行时读开关（模块级常量在导入时求值，测试 / 运维改开关后需读到最新值）
        strict = ai_content_gate.AI_CONTENT_CONFIRMATION_STRICT
        severity = CheckSeverity.blocking if strict else CheckSeverity.warning
        legacy_cond = (
            AIContent.project_id == project_id,
            AIContent.is_deleted == sa.false(),
            AIContent.confirmation_status == AIConfirmationStatus.pending,
        )
        gov_cond = (
            AiContentGovernance.project_id == project_id,
            AiContentGovernance.audit_year == year,
            AiContentGovernance.lifecycle_status.in_(("draft", "revised", "stale")),
        )
        n_legacy = (await self.db.execute(
            sa.select(sa.func.count()).select_from(AIContent).where(*legacy_cond))).scalar_one()
        n_gov = (await self.db.execute(
            sa.select(sa.func.count()).select_from(AiContentGovernance).where(*gov_cond))).scalar_one()
        total = int(n_legacy) + int(n_gov)
        if not total:
            return [_item(CheckSeverity.info, "ai_content", "AI 生成内容均已人工确认（或未使用 AI 生成）", None)]

        items = [_item(severity, "ai_content",
                       f"{total} 条 AI 生成内容尚未人工确认（底稿 AI 内容 {n_legacy} 条、证据治理 AI 输出 {n_gov} 条）", None)]
        # content_type 以 text 读取：真实 PG 枚举已有 review_finding，但旧 ORM AIContentType 少该成员；
        # 直接反序列化 Enum 会 LookupError，把一条合法存量数据变成「整项检查执行失败」。清单只展示标签，不应依赖旧枚举完整性。
        rows = (await self.db.execute(
            sa.select(AIContent.workpaper_id, sa.cast(AIContent.content_type, sa.String).label("content_type"))
            .where(*legacy_cond).order_by(AIContent.created_at).limit(_LIST_LIMIT)
        )).all()
        for wp_id, ctype in rows:
            label = _AI_CONTENT_TYPE_LABELS.get(_val(ctype), _val(ctype))
            items.append(_item(CheckSeverity.info, "ai_content", f"待确认：底稿 AI 内容（{label}）",
                               f"/projects/{pid}/workpapers/{wp_id}/edit" if wp_id else None))
        return items


# ─── 辅助 ─────────────────────────────────────────────────────────────

_ADJ_TYPE_LABELS = {"aje": "审计调整", "rje": "重分类调整"}
_ADJ_STATUS_LABELS = {"draft": "为草稿", "pending_review": "待复核"}
_MODULE_LABELS = {"workpaper": "底稿", "disclosure": "附注", "report": "报表", "trial_balance": "试算表"}


def _item(severity: CheckSeverity, category: str, message: str, route: str | None) -> CheckItem:
    return CheckItem(severity=severity, category=category, message=message, route=route)


def _val(v: object) -> str:
    """枚举成员取 value；字符串原样；None → 空串。"""
    if v is None:
        return ""
    return str(getattr(v, "value", v))


def _more(seq_or_count: object, category: str, unit_text: str, route: str | None) -> list[CheckItem]:
    """超过列出上限的部分汇总为一条 info。"""
    total = seq_or_count if isinstance(seq_or_count, int) else len(seq_or_count)  # type: ignore[arg-type]
    rest = total - _LIST_LIMIT
    if rest <= 0:
        return []
    return [_item(CheckSeverity.info, category, f"另有 {rest} {unit_text}（未逐条列出）", route)]


def _names(rows: object, pick: Callable[[dict], object]) -> str:
    """「（如 A、B、C）」——最多 3 个名称，取不到返回空串。"""
    names = [str(pick(r)) for r in (rows or [])[:3] if isinstance(r, dict) and pick(r)]  # type: ignore[index]
    return f"（如 {'、'.join(names)}）" if names else ""
