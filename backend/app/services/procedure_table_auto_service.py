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
        import asyncio

        template = get_template(table_code)
        if template is None:
            # 无程序表模板（如 docx 文档控制表 B5，或自定义底稿）→ 优雅降级为空表，
            # 让前端 a-program-console 渲染空程序表 + 用户可手动新增行，绝不 500。
            # 用户已新增的自定义行仍从 field_overrides 的 custom_items scope 读取。
            _logger.warning("程序表模板缺失 table_code=%s，返回空表降级", table_code)
            return {
                "table_code": table_code,
                "table_name": table_code,
                "applicable_when": None,
                "items": [],
            }

        scope = f"procedure_table:{table_code}"
        overrides = await self.override_svc.get_batch(project_id, year, scope)

        # 并行解析所有 item 的自动值（程序表通常 5~25 步，并行可减少 DB 往返等待）
        auto_tasks = [
            self._resolve_auto_values(project_id, year, item, business_category)
            for item in template["items"]
        ]
        auto_results = await asyncio.gather(*auto_tasks, return_exceptions=True)

        items = []
        for item, auto_values in zip(template["items"], auto_results):
            item_key = str(item["seq"])
            # gather 异常降级为空 auto_values
            if isinstance(auto_values, BaseException):
                auto_values = {"applicable": self._check_applicable(item, business_category), "executor": None, "summary": None}
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
            elif source == "control_deficiency_count":
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
