"""四表库读取的统一入口（跨循环共享，全程 fail-open）。

K1/K2 各自在 render 文件里写了一份 `fetch_tb_balance_leaves` /
`fetch_trial_balance_amounts`，K3~K13 十一个循环再抄一份必然分叉
（`LIKE '2701%'` 的父子双计就是分叉产物，横跨 5 个文件）。本模块是收敛点。

**两条必须由本模块保证的不变量**

1. **叶子口径** —— 只汇总无子科目的最明细行，其金额之和等于父科目行金额。
   「只取最深层级」会在参差科目树上整段丢掉浅层叶子（K1 实测少算 21.7%）。
2. **最长前缀归属** —— `trial_balance` 中父码与子码并存（`2801` 与 `2801-01`），
   `LIKE '2801%'` 会把父行与全部子行一并累加 ≈ 真值 2 倍。每行只归属到最长命中前缀。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 2.1~2.5 / Property 1, 8
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from .leaf_aggregation import LeafRow, select_leaves, to_leaf_rows

logger = logging.getLogger(__name__)


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


async def fetch_tb_balance_leaves(ctx, *, label: str = "四表取数") -> list[LeafRow]:
    """取 active 数据集全部 `tb_balance` 行并筛出叶子。失败返 ``[]``。

    🔴 ``get_active_filter`` 是 **async**、签名 ``(db, table, project_id, year)``。
    单参调用会抛 ``TypeError`` 被 fail-open 吞成空结果，取数恒空且无任何线索
    （N2/N5 各踩一次）—— 守卫必须以真实签名调用并断言返回非零。

    Args:
        ctx: `RenderContext`（鸭子类型，只用 ``db`` / ``project_id`` / ``year``）。
        label: 日志前缀（循环名），便于定位是哪个循环取数失败。
    """
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
                TbBalance.dataset_id,
            ).where(active_filter)
        )
        return select_leaves(to_leaf_rows(result.fetchall()))
    except Exception as e:  # noqa: BLE001
        logger.warning("%s: tb_balance 叶子查询失败: %s", label, e)
        try:
            await ctx.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return []


async def fetch_tb_balance_all(ctx, *, label: str = "四表取数") -> list[LeafRow]:
    """同 :func:`fetch_tb_balance_leaves` 但**不筛叶子**（供「叶子和 == 父额」自检）。"""
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
                TbBalance.dataset_id,
            ).where(active_filter)
        )
        return to_leaf_rows(result.fetchall())
    except Exception as e:  # noqa: BLE001
        logger.warning("%s: tb_balance 全表查询失败: %s", label, e)
        try:
            await ctx.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return []


async def fetch_trial_balance_amounts(
    ctx, standard_codes, *, label: str = "四表取数"
) -> dict[str, dict[str, float]]:
    """按标准码取 `trial_balance` 未审/审定额，**最长前缀**归属（防父子双计）。

    入参先 strip —— 空白串是「真前缀」会命中**所有**行
    （``code.startswith('')`` 恒真），必须与空串同样剔除。

    Returns:
        ``{标准码: {"unadjusted","audited","hit"}}``。``hit`` 区分「该科目不存在」
        与「存在但为 0」—— 后者是合法零值，不应触发兜底口径。
    """
    codes = [s for c in (standard_codes or []) if (s := str(c or "").strip())]
    if not codes:
        return {}
    out: dict[str, dict[str, float]] = {
        c: {"unadjusted": 0.0, "audited": 0.0, "hit": 0.0} for c in codes
    }
    try:
        result = await ctx.db.execute(
            sa.text(
                """
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                """
            ),
            {"pid": str(ctx.project_id), "year": ctx.year},
        )
        rows = result.fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("%s: trial_balance 查询失败: %s", label, e)
        try:
            await ctx.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return out

    for row in rows:
        code = (row.standard_account_code or "").strip()
        if not code:
            continue
        best = ""
        for c in codes:
            if (code == c or code.startswith(c)) and len(c) > len(best):
                best = c
        if not best:
            continue
        out[best]["unadjusted"] += _f(row.unadjusted_amount)
        out[best]["audited"] += _f(row.audited_amount)
        out[best]["hit"] = 1.0
    return out


def sum_amounts(tb_amounts: dict[str, dict[str, float]], codes) -> tuple[float, float]:
    """把 :func:`fetch_trial_balance_amounts` 的结果按码集求和。

    Returns:
        ``(unadjusted, audited)``。
    """
    unadj = 0.0
    audited = 0.0
    for code in codes or []:
        got = tb_amounts.get(str(code or "").strip())
        if got:
            unadj += got["unadjusted"]
            audited += got["audited"]
    return unadj, audited


def any_hit(tb_amounts: dict[str, dict[str, float]], codes) -> bool:
    """码集中是否有任一码在 `trial_balance` 里真实存在（区别于「存在但为 0」）。"""
    for code in codes or []:
        got = tb_amounts.get(str(code or "").strip())
        if got and got.get("hit"):
            return True
    return False


async def load_project_context(ctx, *, label: str = "四表取数") -> dict:
    """加载项目上下文（客户名 / 审计年度 / 业务类别）。失败返 ``{}``。"""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                """
                SELECT p.client_name, p.audit_year, p.business_category
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
                """
            ),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row:
            project_ctx["client_name"] = row.client_name or ""
            project_ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
            project_ctx["business_category"] = row.business_category or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("%s: 项目上下文加载失败: %s", label, e)
    return project_ctx


async def load_responses_snapshot(
    ctx, prefix: str, *, limit: int = 5000, label: str = "四表取数"
) -> dict:
    """加载该底稿的 `checklist_responses` 快照（``item_id LIKE '{prefix}-%'``）。"""
    snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT :lim"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": f"{prefix}-%", "lim": limit},
        )
        for row in result.fetchall():
            snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("%s: checklist_responses 加载失败: %s", label, e)
    return snapshot


__all__ = [
    "any_hit",
    "fetch_tb_balance_all",
    "fetch_tb_balance_leaves",
    "fetch_trial_balance_amounts",
    "load_project_context",
    "load_responses_snapshot",
    "sum_amounts",
]
