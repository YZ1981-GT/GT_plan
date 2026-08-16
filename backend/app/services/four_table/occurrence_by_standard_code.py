"""按**标准码**归集本期借/贷方发生额（供公式引擎 ``TB(code,'本期借方')`` 用）。

**为什么需要这一件**

``trial_balance`` **没有发生额列**（只有 ``opening_balance`` /
``unadjusted_amount`` / ``audited_amount`` / ``aje_adjustment`` /
``rje_adjustment``），而发生额明细只在 ``tb_balance``（客户**原始码**体系）。

于是两个 ``tb_data`` 构造点长期只产出余额类键：

- ``wp_template_files._get_tb_data_for_prefill``（注释自承认「发生额明细在
  tb_balance，此处不取」）
- ``formula_management.adjudication_writeback.build_context``（6 键，无发生额）

配合 `formula_engine` 改造前的**静默回退期末余额**，全库 48 个预设格
（``本期借方`` 19 / ``本期贷方`` 17 / ``贷方发生额`` 7 / ``借方发生额`` 5，
其中 H 类 16 格）算出来的「本期增加/本期减少」实际是**期末余额** ——
是数字错不是取空。

**取数链路**

::

    tb_balance.account_code（原始码，点号体系）
        │  只取叶子（平台铁律：父子不双算）
        │  account_mapping(project_id, original → standard)
        ▼
    {standard_code: {'本期借方': Σdebit, '本期贷方': Σcredit}}

**三条口径约定**

1. **只汇总叶子**。`tb_balance` 父子并存，直接 SUM 会双算。用共享
   :func:`leaf_aggregation.select_leaves`。
2. **发生额不做方向归一**。``debit_amount`` / ``credit_amount`` 本身就是
   分侧金额（不是带符号余额），按侧原样求和即业务口径；套 ``direction``
   反而会把「贷方发生额」翻成负数。
3. **未映射叶子按最长前缀继承祖先映射**（平台 recalc 铁律）。没有任何
   映射的叶子退化为「原始码的一级科目段」作标准码 —— 与
   `report_line_accounts._standard_prefix` 的兜底口径一致。

fail-open：任一环失败返回 ``{}`` 并 rollback，绝不阻断 render/预填。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
      Requirements 2.2, 2.4 / Property 6~8
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from .leaf_aggregation import LeafRow, select_leaves, to_leaf_rows

logger = logging.getLogger(__name__)

#: 引擎侧标准字段名（与 `formula_engine.COLUMN_ALIASES` 的**值**一致）
DEBIT_KEY = "本期借方"
CREDIT_KEY = "本期贷方"

#: 一级科目段（原始码 `1231.02` / `123102` → `1231`）
_TOP_SEG_RE = re.compile(r"^(\d{4})")


def _top_segment(code: str) -> str:
    """取原始码的一级科目段；非 4 位数字开头时返回原码。"""
    m = _TOP_SEG_RE.match(code or "")
    return m.group(1) if m else (code or "")


def _longest_prefix_standard(
    code: str, mapping: dict[str, str]
) -> str:
    """按**最长前缀**继承祖先映射。

    实证：``account_mapping`` 常只登记父科目（``1601``），而 `tb_balance`
    的叶子是 ``1601.02.03``。逐字查会 miss ⇒ 必须按最长前缀继承
    （平台 recalc 铁律：未映射叶子按最长前缀继承祖先映射）。

    全不中时退化为一级科目段（与 `report_line_accounts` 兜底口径一致）。
    """
    if code in mapping:
        return mapping[code]
    best = ""
    for orig, std in mapping.items():
        if not orig:
            continue
        if code.startswith(orig) and len(orig) > len(best):
            # 边界：`1221` 不得命中 `12210`（点号/非数字才算分级）
            tail = code[len(orig) :]
            if tail and tail[0].isdigit():
                continue
            best = orig
    return mapping[best] if best else _top_segment(code)


def aggregate_occurrence(
    leaves: list[LeafRow], mapping: dict[str, str]
) -> dict[str, dict[str, Decimal]]:
    """**纯函数**：叶子行 + 原始码→标准码映射 → 按标准码归集的发生额。

    Args:
        leaves: 已筛过的**叶子**行（调用方须先 :func:`select_leaves`）。
        mapping: ``{original_account_code: standard_account_code}``；
            空 dict 时全部按一级科目段归集。

    Returns:
        ``{standard_code: {'本期借方': Decimal, '本期贷方': Decimal}}``。
        **不产出零值键** —— 借贷双方都为 0 的标准码不进结果，让
        `_resolve_tb_column` 的「列无数据」分支如实生效（区分
        「余额为 0」与「本项目无此科目」）。
    """
    acc: dict[str, dict[str, Decimal]] = {}
    for leaf in leaves:
        code = (leaf.account_code or "").strip()
        if not code:
            continue
        std = _longest_prefix_standard(code, mapping)
        if not std:
            continue
        bucket = acc.setdefault(
            std, {DEBIT_KEY: Decimal("0"), CREDIT_KEY: Decimal("0")}
        )
        bucket[DEBIT_KEY] += Decimal(str(leaf.debit or 0))
        bucket[CREDIT_KEY] += Decimal(str(leaf.credit or 0))
    return {
        std: vals
        for std, vals in acc.items()
        if vals[DEBIT_KEY] != 0 or vals[CREDIT_KEY] != 0
    }


async def fetch_occurrence_by_standard_code(
    db, project_id: UUID, year: int
) -> dict[str, dict[str, Decimal]]:
    """从 `tb_balance` 取全量叶子发生额并归集到标准码。fail-open 返 ``{}``。"""
    try:
        active = await get_active_filter(
            db, TbBalance.__table__, project_id, year or 0
        )
        rows = (
            await db.execute(
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
                ).where(active)
            )
        ).fetchall()
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning(
            "发生额归集: tb_balance 查询失败 pid=%s year=%s: %s",
            project_id,
            year,
            e,
        )
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {}

    if not rows:
        return {}

    leaves = select_leaves(to_leaf_rows(rows))
    if not leaves:
        return {}

    mapping = await _fetch_code_mapping(db, project_id)
    return aggregate_occurrence(leaves, mapping)


async def _fetch_code_mapping(db, project_id: UUID) -> dict[str, str]:
    """``{original_account_code: standard_account_code}``；失败返 ``{}``。"""
    try:
        rows = (
            await db.execute(
                sa.text(
                    "SELECT original_account_code, standard_account_code "
                    "FROM account_mapping "
                    "WHERE project_id = CAST(:pid AS uuid) AND is_deleted = false"
                ),
                {"pid": str(project_id)},
            )
        ).fetchall()
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("发生额归集: account_mapping 查询失败: %s", e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {}
    out: dict[str, str] = {}
    for r in rows:
        orig = (r.original_account_code or "").strip()
        std = (r.standard_account_code or "").strip()
        if orig and std:
            out[orig] = std
    return out


def merge_occurrence_into_tb_data(
    tb_data: dict[str, dict],
    occurrence: dict[str, dict[str, Decimal]],
    *,
    as_float: bool = False,
) -> dict[str, dict]:
    """把发生额 **additive** 合并进已有 ``tb_data``（就地修改并返回）。

    🔴 零回归保证：只**新增**两个键，既有余额键逐字不动 ⇒ 既有公式求值结果不变。
    发生额里有但 ``tb_data`` 没有的标准码**也会建条目** —— 否则「只有发生额
    没有余额」的损益类科目取不到发生额。

    :param as_float: ``wp_template_files`` 侧的 ``tb_data`` 是 ``dict[str, float]``，
        传 True 转 float；``adjudication_writeback`` 侧是 Decimal，保持默认。
    """
    for std, vals in (occurrence or {}).items():
        bucket = tb_data.setdefault(std, {})
        for key, val in vals.items():
            bucket[key] = float(val) if as_float else val
    return tb_data


__all__ = [
    "DEBIT_KEY",
    "CREDIT_KEY",
    "aggregate_occurrence",
    "fetch_occurrence_by_standard_code",
    "merge_occurrence_into_tb_data",
]
