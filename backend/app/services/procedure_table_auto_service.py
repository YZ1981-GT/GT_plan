"""程序表自动填充服务

从 procedure_table_templates.json 加载模板定义，
对每个 item 按 auto_data_source 解析自动值，
与 FieldOverrideService 用户覆盖值合并，返回前端渲染数据。

Features:
- P1: TTL 内存缓存（auto_data_source 结果 30s~5min）
- P1: consol_trial_balance_check 真实查询
- P0: 异常 ERROR 日志（非静默降级）
- P3: 模板 mtime 热重载

Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 3.5
"""

from __future__ import annotations

import json
import logging
import os
import time
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import Adjustment, Materiality
from app.services.field_override_service import FieldOverrideService

_logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "procedure_table_templates.json"

# ─── P3: 模板热重载（mtime 检测替代手动 invalidate） ─────────────────
_template_cache: dict[str, Any] | None = None
_template_mtime: float = 0.0


def _load_templates() -> dict[str, Any]:
    """加载模板，自动检测文件变更（开发期间无需重启）"""
    global _template_cache, _template_mtime
    try:
        current_mtime = os.path.getmtime(_TEMPLATE_PATH)
    except OSError:
        current_mtime = 0.0
    if _template_cache is None or current_mtime != _template_mtime:
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            _template_cache = json.load(f)
        _template_mtime = current_mtime
    return _template_cache  # type: ignore


# ─── P1: auto_data_source 结果 TTL 缓存 ────────────────────────────
_auto_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SHORT = 30.0   # 变动频繁源（adjustment/trial_balance）30s
_CACHE_TTL_LONG = 300.0   # 变动低频源（materiality/archive/template_recommend）5min

# 哪些 source 用长 TTL
_LONG_TTL_SOURCES = frozenset([
    "materiality_set", "archive_completion", "a16_template_recommend",
    "control_test_completion", "substantive_completion", "workpaper_completion_rate",
    "analytical_review_done", "review_progress", "a16_sign_status_check",
    "a21_sign_status", "a22_sign_status", "a23_sign_status",
])


def _cache_key(project_id: UUID, year: int, source: str) -> str:
    return f"{project_id}:{year}:{source}"


def _get_cached(project_id: UUID, year: int, source: str) -> dict[str, Any] | None:
    key = _cache_key(project_id, year, source)
    entry = _auto_cache.get(key)
    if entry is None:
        return None
    ts, data = entry
    ttl = _CACHE_TTL_LONG if source in _LONG_TTL_SOURCES else _CACHE_TTL_SHORT
    if time.time() - ts > ttl:
        del _auto_cache[key]
        return None
    return data


def _set_cached(project_id: UUID, year: int, source: str, data: dict[str, Any]) -> None:
    key = _cache_key(project_id, year, source)
    _auto_cache[key] = (time.time(), data)


def invalidate_auto_cache(project_id: UUID | None = None, year: int | None = None, source: str | None = None) -> int:
    """失效指定缓存条目。返回清除条数。供 EventBus handler 调用。"""
    if project_id is None:
        count = len(_auto_cache)
        _auto_cache.clear()
        return count
    prefix = str(project_id)
    if year is not None:
        prefix += f":{year}"
    keys_to_del = [k for k in _auto_cache if k.startswith(prefix) and (source is None or k.endswith(f":{source}"))]
    for k in keys_to_del:
        del _auto_cache[k]
    return len(keys_to_del)


def get_template(table_code: str) -> dict[str, Any] | None:
    """获取单个程序表模板定义"""
    tables = _load_templates().get("tables", {})
    return tables.get(table_code)


def list_table_codes() -> list[str]:
    """返回所有程序表编码"""
    return list(_load_templates().get("tables", {}).keys())


class ProcedureTableService:
    """程序表自动填充+渲染数据服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.override_svc = FieldOverrideService(db)

    async def get_procedure_table(
        self,
        project_id: UUID,
        year: int,
        table_code: str,
        business_category: str = "C",
    ) -> dict[str, Any]:
        """返回完整程序表数据（模板 + 自动值 + 用户覆盖）"""
        template = get_template(table_code)
        if template is None:
            raise ValueError(f"未知程序表编码: {table_code}")

        scope = f"procedure_table:{table_code}"
        overrides = await self.override_svc.get_batch(project_id, year, scope)

        items = []
        for item in template["items"]:
            item_key = str(item["seq"])
            # 自动填充
            auto_values = await self._resolve_auto_values(
                project_id, year, item, business_category
            )
            # 合并覆盖
            user_override = overrides.get(item_key, {})
            merged = FieldOverrideService.merge(auto_values, user_override)

            items.append({
                "_key": item_key,
                "seq": item["seq"],
                "content": item["content"],
                "ref_index": item.get("ref_index", ""),
                "phase": item.get("phase"),
                **merged,
            })

        return {
            "table_code": table_code,
            "table_name": template["name"],
            "items": items,
        }

    async def _resolve_auto_values(
        self,
        project_id: UUID,
        year: int,
        item: dict[str, Any],
        business_category: str,
    ) -> dict[str, Any]:
        """按 auto_data_source 解析自动值"""
        source = item.get("auto_data_source")
        result: dict[str, Any] = {
            "applicable": self._check_applicable(item, business_category),
            "executor": None,
            "summary": None,
        }

        if not source:
            return result

        try:
            if source == "adjustment_count_aje":
                count, pending, amount = await self._count_adjustments_with_pending(project_id, year, "aje")
                if count == 0:
                    result["summary"] = "无"
                elif pending > 0:
                    result["summary"] = f"共{count}笔 ¥{amount:,.0f}（⚠️{pending}笔待审）"
                else:
                    result["summary"] = f"共{count}笔 ¥{amount:,.0f}（全部已批）"
            elif source == "adjustment_count_rje":
                count, pending, amount = await self._count_adjustments_with_pending(project_id, year, "rje")
                if count == 0:
                    result["summary"] = "无"
                elif pending > 0:
                    result["summary"] = f"共{count}笔 ¥{amount:,.0f}（⚠️{pending}笔待审）"
                else:
                    result["summary"] = f"共{count}笔 ¥{amount:,.0f}（全部已批）"
            elif source == "adjustment_count_passed":
                count = await self._count_adjustments(project_id, year, "passed")
                result["summary"] = f"共{count}笔" if count else "无"
            elif source == "adjustment_count_consol":
                # 合并项目查实际抵销分录笔数（复用 A3 的 consol_elimination_count 逻辑）
                try:
                    from app.models.consolidation_models import EliminationEntry
                    elim_stmt = sa.select(sa.func.count()).select_from(EliminationEntry).where(
                        EliminationEntry.project_id == project_id,
                        EliminationEntry.is_deleted == sa.false(),
                    )
                    elim_r = await self.db.execute(elim_stmt)
                    elim_count = elim_r.scalar() or 0
                    result["summary"] = f"共{elim_count}笔合并调整" if elim_count else "无合并调整"
                except Exception:
                    result["summary"] = "见合并底稿"
            elif source == "misstatement_summary":
                count = await self._count_adjustments(project_id, year, "passed")
                result["summary"] = f"未更正错报{count}笔" if count else "无未更正错报"
            elif source == "misstatement_evaluation":
                # 错报评价结论：汇总未更正错报金额与执行重要性比对
                try:
                    from app.models.audit_platform_models import Adjustment, Materiality
                    from app.models.audit_platform_models import AdjustmentEntry
                    # 统计未更正错报总金额（借方合计）
                    passed_stmt = sa.select(
                        sa.func.coalesce(sa.func.sum(AdjustmentEntry.debit_amount), 0)
                    ).join(
                        Adjustment, AdjustmentEntry.adjustment_id == Adjustment.id
                    ).where(
                        Adjustment.project_id == project_id,
                        Adjustment.year == year,
                        Adjustment.passed_reason.isnot(None),
                        Adjustment.is_deleted == sa.false(),
                    )
                    passed_r = await self.db.execute(passed_stmt)
                    passed_amount = passed_r.scalar() or 0
                    # 获取执行重要性
                    mat_stmt = sa.select(Materiality.performance_materiality, Materiality.trivial_threshold).where(
                        Materiality.project_id == project_id,
                    )
                    mat_r = await self.db.execute(mat_stmt)
                    mat_row = mat_r.first()
                    if not mat_row or not mat_row.performance_materiality:
                        result["summary"] = f"未更正错报 ¥{passed_amount:,.0f}（重要性待设置）"
                    else:
                        perf_mat = float(mat_row.performance_materiality)
                        trivial = float(mat_row.trivial_threshold) if mat_row.trivial_threshold else 0
                        if passed_amount == 0:
                            result["summary"] = "无未更正错报"
                        elif passed_amount > perf_mat:
                            result["summary"] = f"⚠️ 未更正错报 ¥{passed_amount:,.0f} 超执行重要性 ¥{perf_mat:,.0f}"
                        elif passed_amount <= trivial:
                            result["summary"] = f"未更正错报 ¥{passed_amount:,.0f}，低于明显微小阈值 → 不影响意见"
                        else:
                            result["summary"] = f"未更正错报 ¥{passed_amount:,.0f}，低于执行重要性 ¥{perf_mat:,.0f}"
                except Exception:
                    result["summary"] = "见 A13-3 评价"
            elif source == "materiality_set":
                mat = await self._get_materiality(project_id)
                result["summary"] = f"重要性水平 {mat:,.0f} 元" if mat else "待设置"
            elif source == "trial_balance_check":
                # 真实借贷差验证（从 tb_balance 原始数据，v1 口径 SUM=0 为平衡）
                try:
                    from app.models.audit_platform_models import TbBalance
                    from app.services.dataset_query import get_active_filter
                    tb = TbBalance.__table__
                    active_filter = await get_active_filter(self.db, tb, project_id, year)
                    bal_stmt = sa.select(
                        sa.func.coalesce(
                            sa.func.sum(sa.case((tb.c.closing_balance > 0, tb.c.closing_balance), else_=sa.literal(0))), 0
                        ).label("debit_total"),
                        sa.func.coalesce(
                            sa.func.sum(sa.case((tb.c.closing_balance < 0, sa.func.abs(tb.c.closing_balance)), else_=sa.literal(0))), 0
                        ).label("credit_total"),
                    ).where(active_filter, tb.c.level == 1)
                    bal_r = await self.db.execute(bal_stmt)
                    bal_row = bal_r.first()
                    if bal_row:
                        debit = float(bal_row.debit_total)
                        credit = float(bal_row.credit_total)
                        diff = abs(debit - credit)
                        if diff < 0.01:
                            result["summary"] = f"✓ 试算平衡（借=贷 ¥{debit:,.0f}）"
                        else:
                            result["summary"] = f"⚠️ 不平衡（差异 ¥{diff:,.2f}）"
                    else:
                        result["summary"] = "无余额数据"
                except Exception:
                    result["summary"] = "见试算平衡表"
            elif source == "consol_scope_status":
                # 合并范围确定状态
                try:
                    from app.models.consolidation_models import ConsolScope
                    scope_stmt = sa.select(sa.func.count()).select_from(ConsolScope).where(
                        ConsolScope.project_id == project_id,
                        ConsolScope.is_included == sa.true(),
                        ConsolScope.is_deleted == sa.false(),
                    )
                    scope_r = await self.db.execute(scope_stmt)
                    scope_count = scope_r.scalar() or 0
                    result["summary"] = f"已纳入{scope_count}家子公司" if scope_count else "待确定"
                except Exception:
                    result["summary"] = "见合并范围"
            elif source == "consol_elimination_count":
                # 合并抵销分录统计
                try:
                    from app.models.consolidation_models import EliminationEntry
                    elim_stmt = sa.select(sa.func.count()).select_from(EliminationEntry).where(
                        EliminationEntry.project_id == project_id,
                        EliminationEntry.is_deleted == sa.false(),
                    )
                    elim_r = await self.db.execute(elim_stmt)
                    elim_count = elim_r.scalar() or 0
                    result["summary"] = f"共{elim_count}笔抵销分录" if elim_count else "无"
                except Exception:
                    result["summary"] = "见合并抵销"
            elif source == "consol_internal_trade_status":
                # 内部往来核对状态
                try:
                    from app.models.consolidation_models import InternalTrade
                    trade_stmt = sa.select(sa.func.count()).select_from(InternalTrade).where(
                        InternalTrade.project_id == project_id,
                    )
                    trade_r = await self.db.execute(trade_stmt)
                    trade_count = trade_r.scalar() or 0
                    result["summary"] = f"内部往来{trade_count}笔" if trade_count else "无内部往来"
                except Exception:
                    result["summary"] = "见内部往来"
            elif source == "consol_trial_balance_check":
                # P1: 合并试算平衡真实验证
                try:
                    from app.models.audit_platform_models import TrialBalance
                    tb_t = TrialBalance.__table__
                    check_stmt = sa.select(
                        sa.func.coalesce(sa.func.sum(tb_t.c.aje_adjustment), 0).label("aje_sum"),
                        sa.func.coalesce(sa.func.sum(tb_t.c.rje_adjustment), 0).label("rje_sum"),
                    ).where(
                        tb_t.c.project_id == project_id,
                        tb_t.c.year == year,
                        tb_t.c.is_deleted == sa.false(),
                    )
                    check_r = await self.db.execute(check_stmt)
                    check_row = check_r.first()
                    if check_row:
                        aje_sum = float(check_row.aje_sum)
                        rje_sum = float(check_row.rje_sum)
                        if abs(aje_sum) < 0.01 and abs(rje_sum) < 0.01:
                            result["summary"] = "✓ 合并试算平衡"
                        else:
                            result["summary"] = f"⚠️ 调整净差异 AJE ¥{aje_sum:,.0f} / RJE ¥{rje_sum:,.0f}"
                    else:
                        result["summary"] = "无合并试算数据"
                except Exception as inner_e:
                    _logger.error("auto_data_source %s inner error: %s", source, inner_e)
                    result["summary"] = "见合并试算"
            elif source == "cf_verification_status":
                status = await self._get_cf_verification_status(project_id, year)
                result["summary"] = status
                result["link"] = {"type": "cf_verification", "target": "cash_flow_verification"}
            elif source == "review_progress":
                from app.services.review_checklist_service import get_review_sign_status_batch

                statuses = await get_review_sign_status_batch(self.db, project_id)
                passed = sum(1 for v in statuses.values() if v == "pass")
                total = len(statuses)
                result["summary"] = f"复核{passed}/{total}级完成" if total else "无适用复核"
            elif source == "a21_sign_status":
                from app.services.review_checklist_service import get_review_sign_status_batch

                statuses = await get_review_sign_status_batch(self.db, project_id)
                st = statuses.get("A21-1") or statuses.get("A21-2")
                if st == "pass":
                    result["summary"] = "✓ 现场负责人已签字"
                elif st == "reject":
                    result["summary"] = "⚠️ 现场负责人退回"
                else:
                    result["summary"] = "待现场负责人复核签字"
            elif source == "a22_sign_status":
                from app.services.review_checklist_service import get_review_sign_status_batch

                statuses = await get_review_sign_status_batch(self.db, project_id)
                st = statuses.get("A22-1") or statuses.get("A22-2")
                if st == "pass":
                    result["summary"] = "✓ 经理已签字"
                elif st == "reject":
                    result["summary"] = "⚠️ 经理退回"
                else:
                    result["summary"] = "待经理复核签字"
            elif source == "a23_sign_status":
                from app.services.review_checklist_service import get_review_sign_status_batch

                statuses = await get_review_sign_status_batch(self.db, project_id)
                st = statuses.get("A23-1") or statuses.get("A23-2")
                if st == "pass":
                    result["summary"] = "✓ 合伙人已签字"
                elif st == "reject":
                    result["summary"] = "⚠️ 合伙人退回"
                else:
                    result["summary"] = "待合伙人复核签字"
            elif source == "workpaper_completion_rate":
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
                pct = round(done / total * 100) if total else 0
                result["summary"] = f"编制完成{done}/{total}（{pct}%）"
            elif source == "control_test_completion":
                # 统计 C 循环底稿完成率
                from app.models.workpaper_models import WorkingPaper
                from app.models.workpaper_models import WpIndex
                # 查 C 循环底稿（wp_code 以 C 开头）
                c_total_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).join(
                    WpIndex, WorkingPaper.wp_index_id == WpIndex.id
                ).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WpIndex.wp_code.like("C%"),
                )
                c_done_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).join(
                    WpIndex, WorkingPaper.wp_index_id == WpIndex.id
                ).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WpIndex.wp_code.like("C%"),
                    WorkingPaper.status.in_(["completed", "reviewed"]),
                )
                c_total_r = await self.db.execute(c_total_stmt)
                c_done_r = await self.db.execute(c_done_stmt)
                c_total = c_total_r.scalar() or 0
                c_done = c_done_r.scalar() or 0
                if c_total == 0:
                    result["summary"] = "无控制测试底稿"
                else:
                    pct = round(c_done / c_total * 100)
                    result["summary"] = f"控制测试 {c_done}/{c_total}张（{pct}%）"
            elif source == "substantive_completion":
                # 统计 D~N 循环实质性程序底稿完成率
                from app.models.workpaper_models import WorkingPaper
                from app.models.workpaper_models import WpIndex
                sub_total_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).join(
                    WpIndex, WorkingPaper.wp_index_id == WpIndex.id
                ).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WpIndex.wp_code.op("~")("^[D-N]"),
                )
                sub_done_stmt = sa.select(sa.func.count()).select_from(WorkingPaper).join(
                    WpIndex, WorkingPaper.wp_index_id == WpIndex.id
                ).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WpIndex.wp_code.op("~")("^[D-N]"),
                    WorkingPaper.status.in_(["completed", "reviewed"]),
                )
                sub_total_r = await self.db.execute(sub_total_stmt)
                sub_done_r = await self.db.execute(sub_done_stmt)
                sub_total = sub_total_r.scalar() or 0
                sub_done = sub_done_r.scalar() or 0
                if sub_total == 0:
                    result["summary"] = "无实质性程序底稿"
                else:
                    pct = round(sub_done / sub_total * 100)
                    result["summary"] = f"实质性程序 {sub_done}/{sub_total}张（{pct}%）"
            elif source == "analytical_review_done":
                # 检查 A1-13/A1-14 底稿是否存在并完成
                from app.models.workpaper_models import WorkingPaper
                from app.models.workpaper_models import WpIndex
                ar_stmt = sa.select(WpIndex.wp_code, WorkingPaper.status).join(
                    WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id
                ).where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WpIndex.wp_code.in_(["A1-13", "A1-14"]),
                )
                ar_r = await self.db.execute(ar_stmt)
                ar_rows = ar_r.all()
                if not ar_rows:
                    result["summary"] = "分析性复核底稿未生成"
                else:
                    done_codes = [r[0] for r in ar_rows if r[1] in ("completed", "reviewed")]
                    all_codes = [r[0] for r in ar_rows]
                    if len(done_codes) == len(all_codes):
                        result["summary"] = f"通过（{'/'.join(all_codes)} 已完成）"
                    else:
                        result["summary"] = f"{'/'.join(all_codes)} — 完成{len(done_codes)}/{len(all_codes)}"
            elif source == "archive_completion":
                # 归档完成状态
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
                    result["summary"] = "无底稿"
                elif reviewed == total:
                    result["summary"] = "通过（全部完成复核，可归档）"
                else:
                    unsigned = total - reviewed
                    result["summary"] = f"待归档（{unsigned}张未完成复核）"
            elif source == "a16_template_recommend":
                from app.services.a16_version_service import recommend_main_version
                rec = await recommend_main_version(self.db, project_id)
                suffix = "（请项目组确认）" if rec.get("confidence") != "high" else ""
                result["summary"] = f"推荐 {rec['code']} {rec['label']}{suffix}"
                result["detail"] = rec
            elif source == "related_party_transaction_count":
                # P2: A7 关联交易统计（优先查 related_party_transactions 真实表）
                # A16 seq3: applicable_default="no"; 当有交易时 auto 建议 applicable="yes"
                try:
                    from app.models.related_party_models import (
                        RelatedPartyRegistry,
                        RelatedPartyTransaction,
                    )
                    # 1) 统计关联方数量
                    party_stmt = sa.select(sa.func.count()).select_from(RelatedPartyRegistry).where(
                        RelatedPartyRegistry.project_id == project_id,
                        RelatedPartyRegistry.is_deleted == sa.false(),
                    )
                    party_r = await self.db.execute(party_stmt)
                    party_count = party_r.scalar() or 0

                    # 2) 统计交易笔数和合计金额
                    txn_count_stmt = sa.select(
                        sa.func.count(),
                        sa.func.coalesce(sa.func.sum(RelatedPartyTransaction.amount), 0),
                    ).select_from(RelatedPartyTransaction).where(
                        RelatedPartyTransaction.project_id == project_id,
                        RelatedPartyTransaction.is_deleted == sa.false(),
                    )
                    txn_r = await self.db.execute(txn_count_stmt)
                    txn_row = txn_r.one()
                    txn_count = txn_row[0] or 0
                    txn_total = txn_row[1] or 0

                    if txn_count > 0:
                        result["summary"] = f"已识别{txn_count}笔关联交易，涉及{party_count}个关联方，合计{txn_total:,.2f}元"
                        # 有交易时自动建议适用（用户仍可手动覆盖为 no）
                        result["applicable"] = "yes"
                    elif party_count > 0:
                        result["summary"] = f"已登记{party_count}个关联方，尚未录入交易"
                    else:
                        result["summary"] = "待识别"
                except Exception as inner_e:
                    _logger.error("auto_data_source %s inner error: %s", source, inner_e, exc_info=True)
                    result["summary"] = "见关联方底稿"
            elif source == "related_party_disclosure_check":
                # P2: A7 步骤6 关联方交易↔附注披露一致性比对
                try:
                    from app.models.related_party_models import (
                        RelatedPartyRegistry,
                        RelatedPartyTransaction,
                    )
                    from app.models.disclosure_models import DisclosureNote

                    # 1) 已录入关联方交易数
                    txn_stmt = sa.select(sa.func.count()).select_from(RelatedPartyTransaction).where(
                        RelatedPartyTransaction.project_id == project_id,
                        RelatedPartyTransaction.is_deleted == sa.false(),
                    )
                    txn_r = await self.db.execute(txn_stmt)
                    txn_count = txn_r.scalar() or 0

                    # 2) 附注中关联方章节数（十一 = 关联方及关联交易）
                    note_stmt = sa.select(sa.func.count()).select_from(DisclosureNote).where(
                        DisclosureNote.project_id == project_id,
                        DisclosureNote.year == year,
                        DisclosureNote.is_deleted == sa.false(),
                        sa.or_(
                            DisclosureNote.note_section.like("十一%"),
                            DisclosureNote.note_section.like("十、%"),
                            DisclosureNote.note_section.like("十一、%"),
                        ),
                    )
                    note_r = await self.db.execute(note_stmt)
                    note_count = note_r.scalar() or 0

                    if txn_count > 0 and note_count > 0:
                        result["summary"] = f"已录入{txn_count}笔交易，附注已有{note_count}个章节披露，待核对一致性"
                    elif txn_count > 0 and note_count == 0:
                        result["summary"] = f"已录入{txn_count}笔交易，但附注尚无关联方披露章节"
                    elif txn_count == 0 and note_count > 0:
                        result["summary"] = f"附注已有{note_count}个关联方章节，但尚未录入交易明细"
                    else:
                        result["summary"] = "关联方交易及附注均待完善"
                except Exception as inner_e:
                    _logger.error("auto_data_source %s inner error: %s", source, inner_e, exc_info=True)
                    result["summary"] = "见关联方底稿"
            elif source == "a16_sign_status_check":
                # A16-plus: A1 seq9 自动建议步骤完成状态
                # 读 A16 主版本 selected_version + 该版本的 sign_status
                try:
                    override_svc = FieldOverrideService(self.db)
                    selected_version = await override_svc.get(
                        project_id, year,
                        "word_template:A16", "selected_version", "value"
                    )
                    if selected_version:
                        sign_scope = f"word_template:A16:{selected_version}"
                        sign_status = await override_svc.get(
                            project_id, year, sign_scope, "sign_status", "value"
                        )
                        if sign_status == "signed":
                            result["summary"] = f"✓ 主版本 {selected_version} 已签署"
                            result["step_status"] = "completed"
                        elif sign_status == "sent":
                            result["summary"] = f"主版本 {selected_version} 已发出，待签回"
                            result["step_status"] = "in_progress"
                        else:
                            result["summary"] = f"主版本 {selected_version}，待签署"
                    else:
                        result["summary"] = "待确定主版本"
                except Exception as inner_e:
                    _logger.error("auto_data_source %s inner error: %s", source, inner_e, exc_info=True)
                    result["summary"] = "见 A16 声明书"
            elif source == "control_deficiency_count":
                # P2: A14 内控缺陷统计（从 issue_tickets 查内控类缺陷）
                try:
                    from app.models.issue_ticket_models import IssueTicket
                    deficiency_stmt = sa.select(sa.func.count()).select_from(IssueTicket).where(
                        IssueTicket.project_id == project_id,
                        IssueTicket.category == "internal_control",
                        IssueTicket.is_deleted == sa.false(),
                    )
                    def_r = await self.db.execute(deficiency_stmt)
                    def_count = def_r.scalar() or 0
                    result["summary"] = f"已识别{def_count}项内控缺陷" if def_count else "暂无已识别缺陷"
                except Exception as inner_e:
                    _logger.error("auto_data_source %s inner error: %s", source, inner_e)
                    result["summary"] = "见内控缺陷汇总"
            else:
                # 未实现的 data_source 保留空
                _logger.debug("auto_data_source '%s' 未实现，跳过", source)
        except Exception as e:
            _logger.error("auto_data_source '%s' failed [project=%s year=%s]: %s", source, project_id, year, e, exc_info=True)

        return result

    def _check_applicable(self, item: dict, business_category: str) -> str:
        """判定适用性：按模板项的 applicable_categories 和项目分类"""
        from app.services.business_category_service import get_category_prefix

        categories = item.get("applicable_categories")
        if not categories:
            return item.get("applicable_default", "yes")

        prefix = get_category_prefix(business_category)
        if prefix in categories:
            return item.get("applicable_default", "yes")
        return "na"

    async def _count_adjustments(self, project_id: UUID, year: int, adj_type: str) -> int:
        """按类型统计调整分录数"""
        if adj_type == "passed":
            # 未更正错报：review_status 枚举无 'passed' 值（draft/pending_review/
            # approved/rejected）。"未更正"的语义标记是 V078 的 passed_reason 列
            # （管理层不予更正原因）非空 → 该调整被 Passed（不予更正）。
            stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
                Adjustment.project_id == project_id,
                Adjustment.year == year,
                Adjustment.passed_reason.isnot(None),
                Adjustment.is_deleted == sa.false(),
            )
        else:
            stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
                Adjustment.project_id == project_id,
                Adjustment.year == year,
                Adjustment.adjustment_type == adj_type,
                Adjustment.is_deleted == sa.false(),
            )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _count_adjustments_with_pending(
        self, project_id: UUID, year: int, adj_type: str
    ) -> tuple[int, int, float]:
        """按类型统计调整分录数，同时返回待审批数 + 借方总金额（万元）"""
        from app.models.audit_platform_models import AdjustmentEntry
        total_stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.adjustment_type == adj_type,
            Adjustment.is_deleted == sa.false(),
        )
        pending_stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.adjustment_type == adj_type,
            Adjustment.review_status != "approved",
            Adjustment.passed_reason.is_(None),
            Adjustment.is_deleted == sa.false(),
        )
        # 借方合计金额（衡量调整影响规模）
        amount_stmt = sa.select(
            sa.func.coalesce(sa.func.sum(AdjustmentEntry.debit_amount), 0)
        ).join(
            Adjustment, AdjustmentEntry.adjustment_id == Adjustment.id
        ).where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.adjustment_type == adj_type,
            Adjustment.is_deleted == sa.false(),
        )
        total_r = await self.db.execute(total_stmt)
        pending_r = await self.db.execute(pending_stmt)
        amount_r = await self.db.execute(amount_stmt)
        return (total_r.scalar() or 0, pending_r.scalar() or 0, float(amount_r.scalar() or 0))

    async def _get_materiality(self, project_id: UUID) -> Decimal:
        stmt = sa.select(Materiality.overall_materiality).where(
            Materiality.project_id == project_id,
        )
        result = await self.db.execute(stmt)
        val = result.scalar_one_or_none()
        return Decimal(str(val)) if val else Decimal("0")

    async def _get_cf_verification_status(self, project_id: UUID, year: int) -> str:
        """获取 CF 核查完成状态摘要"""
        from app.models.cf_verification_models import CfVerificationResult

        stmt = sa.select(
            sa.func.count(),
            sa.func.count().filter(CfVerificationResult.pass_ == sa.true()),
        ).where(
            CfVerificationResult.project_id == project_id,
            CfVerificationResult.year == year,
        )
        result = await self.db.execute(stmt)
        total, passed = result.one()
        if total == 0:
            return "未执行"
        if passed == total:
            return f"全部通过（{total}项）"
        return f"通过{passed}/{total}项"


def invalidate_cache() -> None:
    """清除模板缓存 + auto_data_source 缓存"""
    global _template_cache
    _template_cache = None
    _auto_cache.clear()
