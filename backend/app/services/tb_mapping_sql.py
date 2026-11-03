"""客户科目余额（tb_balance）→ 标准科目 的 SQL 片段（单一来源）。

试算表未审数重算（``TrialBalanceService.recalc_unadjusted``）与标准科目余额视图
（``standard_balance_view_service``）共用：两处对「哪些行参与汇总、归到哪个标准科目、
金额按什么符号累加」必须同一口径，否则视图里的发生额与试算表未审数对不上。
"""

from __future__ import annotations

import sqlalchemy as sa

from app.models.audit_platform_models import AccountMapping


def normalized_code(code: sa.ColumnElement) -> sa.ColumnElement[str]:
    """科目码比较口径：剥掉表格读出的 ``.0`` 尾巴（Excel 数字格式的编码 → ``"1001.0"``）。

    导入端已改为写 ``"1001"``（``app.core.code_text``），但此前导入的余额表 / 客户科目表 /
    映射仍是 ``"1001.0"``；同一项目新旧两批混在一起时（重新导入余额表、科目表与映射沿用旧的），
    原样比较一行都对不上，试算表整张为 0。``"1002.01"`` 这类真点号分级不受影响。
    """
    # type_coerce：CASE 里 substr 的类型推不出来，后续 .concat / .like 需要按字符串编译
    return sa.type_coerce(
        sa.case(
            (code.like("%.0"), sa.func.substr(code, 1, sa.func.length(code) - 2)),
            else_=code,
        ),
        sa.String,
    )


def is_descendant(child_code: sa.ColumnElement, parent_code: sa.ColumnElement) -> sa.ColumnElement[bool]:
    """child 是 parent 的下级科目：编码以上级编码开头且更长。

    同时覆盖两种编码习惯：点号分级（``1122`` / ``1122.01``）与连写（``1122`` / ``112201``）。
    原先只认点号，连写编码的账套父级与明细都被当成叶子 ⇒ 父子重复汇总、试算表翻倍。
    """
    c, p = normalized_code(child_code), normalized_code(parent_code)
    return sa.and_(c != p, c.like(p.concat("%")))


def leaf_condition(bal: sa.Table) -> sa.ColumnElement[bool]:
    """只取叶子节点（没有下级明细的最明细行）。

    客户科目表是多级树（1122 父级 / 1122.01 或 112201 子级），父级余额 = 子级之和。
    account_mapping 把每一级都映射到标准科目，父子全加会重复计算 ⇒ 只汇总叶子。
    子级须与父级同数据集才算其子科目（active dataset 由调用方的 filter 锁定 bal）。
    """
    child = bal.alias("tb_child")
    return ~sa.exists(
        sa.select(sa.literal(1))
        .select_from(child)
        .where(
            child.c.project_id == bal.c.project_id,
            child.c.year == bal.c.year,
            child.c.is_deleted == sa.false(),
            is_descendant(child.c.account_code, bal.c.account_code),
            sa.or_(
                child.c.dataset_id == bal.c.dataset_id,
                sa.and_(child.c.dataset_id.is_(None), bal.c.dataset_id.is_(None)),
            ),
        )
    )


def resolved_standard_code(bal: sa.Table) -> sa.ScalarSelect:
    """按「最长前缀匹配」解析每行的标准科目码。

    叶子自身有映射用自身，否则回退到最近的已映射祖先（1651.02 / 165102 → 1651 → 1641）；
    无任何已映射祖先返回 NULL（调用方丢弃）。每次调用新建别名，可在同一查询里用多次。
    科目码按 ``normalized_code`` 比较（``"1001"`` 与旧数据的 ``"1001.0"`` 视为同一科目）。
    """
    mp_anc = AccountMapping.__table__.alias("mp_anc")
    bal_code = normalized_code(bal.c.account_code)
    map_code = normalized_code(mp_anc.c.original_account_code)
    return (
        sa.select(mp_anc.c.standard_account_code)
        .where(
            mp_anc.c.project_id == bal.c.project_id,
            mp_anc.c.is_deleted == sa.false(),
            sa.or_(bal_code == map_code, is_descendant(bal.c.account_code, mp_anc.c.original_account_code)),
        )
        .order_by(sa.func.length(map_code).desc())
        .limit(1)
        .correlate(bal)
        .scalar_subquery()
    )


def signed_balance(amount: sa.ColumnElement, direction: sa.ColumnElement) -> sa.Case:
    """余额归一到「借正贷负」。

    部分账套 closing/opening_balance 存无符号绝对值、方向在 *_direction 里：
    debit → +ABS，credit → -ABS，方向缺失 → 原值（兼容已带符号的存储）。
    """
    return sa.case(
        (direction == "credit", -sa.func.abs(amount)),
        (direction == "debit", sa.func.abs(amount)),
        else_=amount,
    )
