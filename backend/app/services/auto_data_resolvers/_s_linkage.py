"""S 类跨底稿只读联动 resolver。

本模块只提供取数，不提供任何 TB/底稿写入能力：

* ``s6_related_party_summary`` 读取项目级关联方登记和交易；
* ``s33_5_revenue_cost_check`` 复用已注册的 D4/F5 只读 resolver；
* ``s14_estimate_related_data`` 从 B50 的会计估计标记定位科目，再读取
  ``trial_balance`` 的当前数据集。

关联方表和 B50 checklist 没有可用的 ``year`` 列，因此它们按项目的 active
记录读取；试算表仍通过 ``get_active_filter`` 按项目/年度/数据集隔离。
异常按 auto-data 的诊断约定返回 ``_error``，并先回滚当前异常事务状态，
不把读取错误伪装成成功的零值。
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver, resolve_auto_data_source

logger = logging.getLogger(__name__)

NEW_S_RESOLVER_SOURCES: tuple[str, ...] = (
    "s6_related_party_summary",
    "s33_5_revenue_cost_check",
    "s14_estimate_related_data",
)


_MAPPING_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "wp_account_mapping.json"
)


@lru_cache(maxsize=1)
def _load_linked_workpapers_index() -> dict[str, list[str]]:
    """从 wp_account_mapping.json 读取 wp_code -> linked_workpapers（单一来源）。

    R7.1 的关联声明权威源是映射表；resolver 不再硬编码关联底稿，避免双写漂移。
    文件缺失/解析失败降级为空索引，不阻断取数。
    """
    try:
        data = json.loads(_MAPPING_PATH.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001 - 降级为空索引
        logger.warning("加载 wp_account_mapping linked_workpapers 失败", exc_info=True)
        return {}
    index: dict[str, list[str]] = {}
    for item in data.get("mappings", []) if isinstance(data, dict) else []:
        code = str(item.get("wp_code") or "").strip()
        links = item.get("linked_workpapers")
        if code and isinstance(links, list) and links:
            index[code] = [str(x).strip() for x in links if str(x).strip()]
    return index


def linked_workpapers_for(wp_code: str) -> list[str]:
    """返回映射表声明的关联底稿列表（复用既有链接消费方的输入）。"""
    return list(_load_linked_workpapers_index().get(wp_code, []))


def _as_float(value: Any, default: float | None = None) -> float | None:
    """将 Decimal/数字安全转换为 float，NULL 保持 NULL。"""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _row_value(row: Any, key: str, position: int) -> Any:
    """兼容 SQLAlchemy Row、mapping 和测试用轻量 row。"""
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        try:
            return mapping[key]
        except (KeyError, TypeError):
            pass
    value = getattr(row, key, None)
    if value is not None:
        return value
    try:
        return row[position]
    except (IndexError, KeyError, TypeError):
        return None


async def _rollback_after_read_error(db: AsyncSession) -> None:
    """读取失败后恢复会话，避免后续 resolver 继承 aborted 事务。"""
    try:
        await db.rollback()
    except Exception:  # pragma: no cover - 仅数据库连接已失效时触发
        logger.debug("S resolver rollback failed", exc_info=True)


def _diagnostic(source: str, error: Exception) -> dict[str, Any]:
    """返回与 auto_data dispatcher 一致的可诊断失败结果。"""
    return {
        "summary": f"⚠️ {source}数据获取失败",
        "_error": True,
        "_error_detail": str(error),
    }


@auto_resolver("s6_related_party_summary")
async def s6_related_party_summary(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """S6 关联方登记和交易摘要（只读）。

    ``related_party_registry`` / ``related_party_transactions`` 是项目级表，
    真实模型没有 ``year`` 字段，所以这里不拼接不存在的年度列；``year`` 保留
    以满足统一 resolver 调度协议。
    """
    del kwargs  # 统一协议保留行级参数；S6 数据源没有行级过滤参数
    try:
        from app.models.related_party_models import (
            RelatedPartyRegistry,
            RelatedPartyTransaction,
        )

        party_result = await db.execute(
            sa.select(sa.func.count())
            .select_from(RelatedPartyRegistry)
            .where(
                RelatedPartyRegistry.project_id == project_id,
                RelatedPartyRegistry.is_deleted == sa.false(),
            )
        )
        party_count = int(party_result.scalar() or 0)

        transaction_result = await db.execute(
            sa.select(
                sa.func.count().label("transaction_count"),
                sa.func.coalesce(sa.func.sum(RelatedPartyTransaction.amount), 0).label(
                    "transaction_total"
                ),
            )
            .select_from(RelatedPartyTransaction)
            .where(
                RelatedPartyTransaction.project_id == project_id,
                RelatedPartyTransaction.is_deleted == sa.false(),
            )
        )
        transaction_row = transaction_result.one()
        transaction_count = int(transaction_row[0] or 0)
        transaction_total = float(transaction_row[1] or 0)
    except Exception as exc:  # noqa: BLE001 - resolver 统一诊断失败
        await _rollback_after_read_error(db)
        logger.warning(
            "s6_related_party_summary 查询失败 project=%s year=%s: %s",
            project_id,
            year,
            exc,
        )
        return _diagnostic("S6关联方", exc)

    if transaction_count:
        summary = (
            f"已识别{transaction_count}笔关联交易，涉及{party_count}个关联方，"
            f"合计{transaction_total:,.2f}元"
        )
    elif party_count:
        summary = f"已登记{party_count}个关联方，尚未录入交易"
    else:
        summary = "关联方登记及交易均待完善"

    return {
        "summary": summary,
        "party_count": party_count,
        "transaction_count": transaction_count,
        "transaction_total": transaction_total,
        "linked_workpapers": linked_workpapers_for("S6"),
    }


@auto_resolver("s33_5_revenue_cost_check")
async def s33_5_revenue_cost_check(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """S33-5 收入及毛利率核查（只读复用 D4/F5 取数）。

    D4 的 ``d4_analysis_indicators`` 使用报表行驱动的动态收入/成本科目，
    F5 的 ``f5_ledger_monthly_by_product`` 提供成本明细。这里不复制科目码
    规则，也不读取或写入任何工作底稿/TB写回端点。
    """
    try:
        d4_result = await resolve_auto_data_source(
            db, project_id, year, "d4_analysis_indicators", **kwargs
        )
        f5_result = await resolve_auto_data_source(
            db, project_id, year, "f5_ledger_monthly_by_product", **kwargs
        )
    except Exception as exc:  # pragma: no cover - dispatcher 已有失败兜底
        await _rollback_after_read_error(db)
        logger.warning(
            "s33_5_revenue_cost_check 关联取数失败 project=%s year=%s: %s",
            project_id,
            year,
            exc,
        )
        return _diagnostic("S33-5收入毛利", exc)

    d4_data = d4_result if isinstance(d4_result, dict) else {}
    f5_data = f5_result if isinstance(f5_result, dict) else {}
    balances = d4_data.get("balances") if isinstance(d4_data.get("balances"), dict) else {}
    revenue = _as_float(balances.get("revenue"))
    d4_cost = _as_float(balances.get("cost"))

    f5_rows = f5_data.get("rows") if isinstance(f5_data.get("rows"), list) else []
    f5_cost = None
    if f5_rows:
        f5_cost = sum(
            _as_float(row.get("annual"), 0.0) or 0.0
            for row in f5_rows
            if isinstance(row, dict)
        )
    cost = d4_cost if d4_cost is not None else f5_cost

    gross_margin_rate = None
    if revenue not in (None, 0) and cost is not None:
        gross_margin_rate = round((revenue - cost) / revenue, 4)

    summary_parts: list[str] = []
    if revenue is not None:
        summary_parts.append(f"营业收入={revenue:,.2f}")
    if cost is not None:
        summary_parts.append(f"营业成本={cost:,.2f}")
    if gross_margin_rate is not None:
        summary_parts.append(f"毛利率={gross_margin_rate:.1%}")
    if f5_cost is not None and d4_cost is not None:
        summary_parts.append(f"F5成本明细={f5_cost:,.2f}")

    return {
        "summary": "；".join(summary_parts) if summary_parts else "D4/F5暂无可用收入成本数据",
        "revenue": revenue,
        "cost": cost,
        "d4_cost": d4_cost,
        "f5_cost": f5_cost,
        "gross_margin_rate": gross_margin_rate,
        "d4_indicators": d4_data.get("indicators", {}),
        "f5_rows": f5_rows,
        "linked_workpapers": linked_workpapers_for("S33-5"),
    }


@auto_resolver("s14_estimate_related_data")
async def s14_estimate_related_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """S14 会计估计相关试算表数据（只读）。

    会计估计标记的真实来源是 B50 ``checklist_responses`` 中的
    ``B50-T3-estimate-{account}``，由 ``load_b50_accounts`` 解析；该字段保存的
    account 身份是前端填写的科目名称。随后按同一名称在 ``trial_balance`` 读取
    当前年度的未审/调整/审定数，避免按命名习惯臆造科目码。
    """
    del kwargs
    try:
        from app.models.audit_platform_models import TrialBalance
        from app.services.b50_risk_reader import load_b50_accounts
        from app.services.dataset_query import get_active_filter

        b50_accounts = await load_b50_accounts(db, project_id)
        estimate_accounts = [
            item
            for item in b50_accounts
            if str(item.get("is_estimate") or "").strip().upper() == "Y"
            and str(item.get("account") or "").strip()
        ]
        account_names = list(
            dict.fromkeys(str(item["account"]).strip() for item in estimate_accounts)
        )
        if not account_names:
            return {
                "summary": "B50尚未标记会计估计相关科目",
                "items": [],
                "account_count": 0,
                "total_audited": None,
                "source": "B50.checklist_responses → trial_balance",
            }

        active_filter = await get_active_filter(
            db, TrialBalance.__table__, project_id, year
        )
        result = await db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.account_name,
                TrialBalance.unadjusted_amount,
                TrialBalance.aje_adjustment,
                TrialBalance.rje_adjustment,
                TrialBalance.audited_amount,
            )
            .where(
                active_filter,
                TrialBalance.account_name.in_(account_names),
            )
            .order_by(
                TrialBalance.account_name,
                TrialBalance.standard_account_code,
            )
        )
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001 - resolver 统一诊断失败
        await _rollback_after_read_error(db)
        logger.warning(
            "s14_estimate_related_data 查询失败 project=%s year=%s: %s",
            project_id,
            year,
            exc,
        )
        return _diagnostic("S14会计估计", exc)

    items: list[dict[str, Any]] = []
    total_audited = 0.0
    for row in rows:
        audited = _as_float(_row_value(row, "audited_amount", 5))
        if audited is not None:
            total_audited += audited
        items.append(
            {
                "standard_account_code": _row_value(row, "standard_account_code", 0),
                "account_name": _row_value(row, "account_name", 1),
                "unadjusted_amount": _as_float(_row_value(row, "unadjusted_amount", 2)),
                "aje_adjustment": _as_float(_row_value(row, "aje_adjustment", 3), 0.0),
                "rje_adjustment": _as_float(_row_value(row, "rje_adjustment", 4), 0.0),
                "audited_amount": audited,
            }
        )

    if not items:
        summary = f"已标记{len(account_names)}个会计估计科目，但试算表暂无匹配数据"
        total_value: float | None = None
    else:
        summary = f"已读取{len(items)}行会计估计相关试算表数据，审定合计={total_audited:,.2f}"
        total_value = total_audited

    return {
        "summary": summary,
        "items": items,
        "account_count": len(account_names),
        "matched_row_count": len(items),
        "total_audited": total_value,
        "estimate_accounts": account_names,
        "source": "B50.checklist_responses → trial_balance",
    }
