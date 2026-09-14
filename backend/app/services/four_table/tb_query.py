"""`tb_balance` / `trial_balance` 取数的共享 DB 访问层（跨循环复用）。

**为什么要共享**

F1~F5、D、G、K 各循环原本各写一份「按前缀集查 tb_balance → 筛叶子」的私有函数，
每份都要重复处理四件容易出错的事：

1. ``get_active_filter`` 的**完整签名是 4 参且是 async**
   （``await get_active_filter(db, table, project_id, year)``）—— 实证 N2/N5 都踩过
   单参调用，`TypeError` 被 ``except Exception`` 吞成 warning → 取数恒空且无报错线索。
2. SQL 必须 ``LIKE '{prefix}%'`` **宽取整棵子树**（父行也要），否则无法判叶子、
   也拿不到父额做勾稽自检。
3. 必须 select ``opening_direction``（不只 ``closing_direction``）—— 两期方向可能不同。
4. fail-open + rollback（取数失败不得阻断 render）。

spec: .kiro/specs/f-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.2, 2.2, 3.6
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from .leaf_aggregation import LeafRow, to_leaf_rows

logger = logging.getLogger(__name__)


def _normalize_prefixes(prefixes) -> list[str]:
    """去重 + 去空 + 去掉区间符（区间由 `sql_prefixes_for_specs` 预处理为宽前缀）。"""
    return [p for p in dict.fromkeys(str(p or "").strip() for p in prefixes or []) if p]


async def fetch_tb_subtree(
    db,
    project_id,
    year,
    prefixes,
) -> list[LeafRow]:
    """按前缀集取 `tb_balance` 的**整棵子树**（含父行），active 数据集。

    🔴 **不做叶子筛选** —— 返回值须交给 :func:`four_table.select_leaves` 或
    :func:`four_table.resolve_leaf_totals`：后者需要父行做「叶子和 == 父额」勾稽，
    预先筛掉父行会让勾稽自检永久失效。

    Args:
        db: `AsyncSession`。
        project_id / year: 项目与审计年度。
        prefixes: 原始码宽前缀集（区间规格请先过 `sql_prefixes_for_specs`）。

    Returns:
        `LeafRow` 列表（含父行）；任何异常返回 ``[]`` 并 rollback（fail-open）。
    """
    ps = _normalize_prefixes(prefixes)
    if not ps:
        return []
    try:
        # 🔴 全签名 4 参 + await —— 单参调用会 TypeError 并被下方 except 吞成空结果
        active_filter = await get_active_filter(
            db, TbBalance.__table__, project_id, year or 0
        )
        prefix_filter = sa.or_(*[TbBalance.account_code.like(f"{p}%") for p in ps])
        result = await db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.account_name,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_direction,
                TbBalance.opening_direction,
                TbBalance.dataset_id,
            ).where(sa.and_(active_filter, prefix_filter))
        )
        return to_leaf_rows(result.fetchall())
    except Exception as e:  # noqa: BLE001 — fail-open，取数失败不阻断 render
        logger.warning("四表取数: tb_balance 查询失败 prefixes=%s: %s", ps, e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return []


async def fetch_trial_balance_amounts(
    db,
    project_id,
    year,
    standard_codes,
) -> dict[str, float] | None:
    """从 `trial_balance`（v2 正数口径）按标准码集取未审 / 审定合计。

    ⚠️ **`trial_balance` 不是唯一权威**（本 spec 的范围外发现 G1/G2）：
    实测部分项目该表存在**旧版 recalc 写入的父子双算**陈旧数据
    （`2aa00f57` 的 `2202` 是真值 2 倍、`6401` 是 3 倍），且损益类发生额用
    ``debit − credit`` 在含年末结转损益的全年账上结构性恒为 0。

    故调用方应把本函数的结果与 `tb_balance` **叶子聚合口径并列展示**，
    差异超容差时提示审计师（而不是静默取其一）。

    Returns:
        ``{"unadjusted": x, "audited": y}``；无记录返回 ``None``（区别于全 0）。
    """
    from app.services.report_account_mapping import build_trial_balance_code_filter

    codes = [c for c in (str(x or "").strip() for x in standard_codes or []) if c]
    if not codes:
        return None
    where_clause, params = build_trial_balance_code_filter(codes)
    try:
        result = await db.execute(
            sa.text(
                "SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadjusted, "
                "COALESCE(SUM(audited_amount), 0) AS audited, COUNT(*) AS n "
                "FROM trial_balance "
                "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                f"AND {where_clause}"
            ),
            {"pid": str(project_id), "year": int(year or 0), **params},
        )
        row = result.fetchone()
        if row is None:
            return None
        # 🔴 `n` 用 getattr 兼容读取（2026-08-05）：`COUNT(*)` 是本函数为区分
        # 「无记录」与「全 0」而加的，而各循环既有的测试替身只准备了
        # `unadjusted` / `audited` 两个字段。缺 `n` 时按「有记录」处理 —— 与改造前
        # 各 render 直接 `COALESCE(SUM(...),0)`（总拿到一行）的行为一致，故零回归。
        # 真实 DB 一定有 `n`，三态区分不受影响。
        n = getattr(row, "n", None)
        if n is not None and not int(n or 0):
            return None
        return {
            "unadjusted": float(row.unadjusted or 0),
            "audited": float(row.audited or 0),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("四表取数: trial_balance 查询失败 codes=%s: %s", codes, e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


async def fetch_trial_balance_rows(
    db,
    project_id,
    year,
    standard_codes,
) -> list:
    """按标准码集取 `trial_balance` **行**（供 :func:`parent_check.build_parent_check`）。

    与 :func:`fetch_trial_balance_amounts` 的区别：后者返回合计 dict，本函数返回
    逐行记录 —— ``build_parent_check`` 需要按 ``standard_account_code`` 逐码归集，
    拿不到行就没法算 ``diff_trial``。

    **为什么要共享**：H1/H2/H4/H5/H6/H7/H8/H9 已各自抄了一份形态完全相同的裸 SQL
    （``standard_account_code = ANY(:codes)`` + try/except + WARNING），D 类不该抄第 8 份。
    新循环一律调本函数。

    Args:
        db: `AsyncSession`。
        project_id / year: 项目与审计年度。
        standard_codes: 标准码集（横杠体系，如 ``1231-01``）。空集直接返 ``[]``。

    Returns:
        行序列（含 ``standard_account_code`` / ``unadjusted_amount`` / ``audited_amount``）；
        任何异常返回 ``[]`` 并 rollback（fail-open）。

    .. note::
       本函数**不做**父子双算校正 —— `trial_balance` 存在旧版 recalc 写入的
       父子双算陈旧数据（实证 `2aa00f57` 的 `1651` 是叶子和的 2 倍）。这正是
       ``build_parent_check`` 要三口径并列而非取其一的原因。
    """
    codes = [c for c in (str(x or "").strip() for x in standard_codes or []) if c]
    if not codes:
        return []
    try:
        result = await db.execute(
            sa.text(
                "SELECT standard_account_code, unadjusted_amount, audited_amount "
                "FROM trial_balance "
                "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                "  AND standard_account_code = ANY(:codes)"
            ),
            {"pid": str(project_id), "year": int(year or 0), "codes": codes},
        )
        return list(result.fetchall())
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("四表取数: trial_balance 行查询失败 codes=%s: %s", codes, e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return []


__all__ = [
    "fetch_tb_subtree",
    "fetch_trial_balance_amounts",
    "fetch_trial_balance_rows",
]
