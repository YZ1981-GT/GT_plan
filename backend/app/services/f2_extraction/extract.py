"""F2-1 审定表从 tb_balance 类别级取数核心服务.

spec: f2-four-table-extraction-refresh
Property 1: 只汇总叶子防双算
Property 2: 科目方向正确（资产借方/备抵贷方 ABS）
Property 3: 跌价 1471 abs 反转
Property 5: 全零跳过不产出
Property 8: 公式驱动—改 binding account 改变取数值
Property 12: 同快照同绑定幂等

**复用铁律**：
- get_active_filter (canonical 异步 4 参)
- TbBalance ORM 模型
- d_cycle_extraction.prefill._is_leaf 等价语义（本地重写避免跨模块依赖）
- **绝不** import evaluate_wp_formula_expression（Property 9 红线）
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbBalance
from app.routers.wp_render_strategies._f2_inventory_main import F2_CATEGORIES
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

F2_COLUMN_MAP: dict[str, str] = {
    "期初余额": "opening_balance",
    "期末余额": "closing_balance",
    "借方发生额": "debit_amount",
    "贷方发生额": "credit_amount",
}

# rowKey→account 映射，从 F2_CATEGORIES 派生避免重复
F2_ROW_KEY_ACCOUNT: dict[str, str] = {
    cat["rowKey"]: cat["account"] for cat in F2_CATEGORIES
}

# TB 公式正则: =TB('account','列') 或 ABS(TB('account','列'))，允许开头等号
_TB_RE = re.compile(
    r"^=?\s*(?P<abs>ABS\s*\(\s*)?"
    r"TB\s*\(\s*['\"](?P<account>[^'\"]+)['\"]\s*,\s*['\"](?P<col>[^'\"]+)['\"]\s*\)"
    r"(?:\s*\))?\s*$",
    re.IGNORECASE,
)

# 金额判零阈值
_ZERO_EPS = 0.005


# ---------------------------------------------------------------------------
# 公式解析
# ---------------------------------------------------------------------------


def parse_tb_formula(expression: str) -> tuple[str, str, bool] | None:
    """解析 TB('account','列') 或 ABS(TB('account','列')).

    Returns:
        (account, column_key, is_abs) 或 None（非法格式/空/列名不在 F2_COLUMN_MAP）
    """
    if not expression or not expression.strip():
        return None

    m = _TB_RE.match(expression.strip())
    if not m:
        return None

    account = m.group("account")
    col_key = m.group("col")
    is_abs = m.group("abs") is not None

    if col_key not in F2_COLUMN_MAP:
        return None

    return (account, col_key, is_abs)


# ---------------------------------------------------------------------------
# 叶子判定
# ---------------------------------------------------------------------------


def _is_leaf(code: str, all_codes: list[str]) -> bool:
    """叶子判定：code 不是任何其它 code 的前缀.

    与 d_cycle_extraction.prefill._is_leaf 等价语义，本地重写避免跨模块依赖。
    空 code → True。
    """
    if not code:
        return True
    return not any(c != code and c.startswith(code) for c in all_codes)


# ---------------------------------------------------------------------------
# 核心取数
# ---------------------------------------------------------------------------


async def extract_f2_category_values(
    ctx,
    effective_bindings: list[dict],
) -> dict[str, dict]:
    """从 tb_balance 按类别级提取 F2-1 审定表取数值.

    Args:
        ctx: 需 db(AsyncSession) / project_id(UUID) / year(int)
        effective_bindings: 来自 presets.resolve_effective 的列表，
            每条含 {anchor, expression, ...}

    Returns:
        {anchor: {"value": float, "account": str, "column": str,
                  "is_abs": bool, "source_codes": [叶子码列表]}}
    """
    db: AsyncSession | None = getattr(ctx, "db", None)
    project_id = getattr(ctx, "project_id", None)
    year = getattr(ctx, "year", None)

    if db is None or project_id is None or year is None:
        return {}

    # a. 解析每条 binding 的公式
    parsed_bindings: list[tuple[dict, str, str, bool]] = []
    for binding in effective_bindings:
        expr = binding.get("expression", "")
        result = parse_tb_formula(expr)
        if result is None:
            continue
        account, col_key, is_abs = result
        parsed_bindings.append((binding, account, col_key, is_abs))

    if not parsed_bindings:
        return {}

    # b. 按 account 归组
    account_groups: dict[str, list[tuple[dict, str, bool]]] = defaultdict(list)
    for binding, account, col_key, is_abs in parsed_bindings:
        account_groups[account].append((binding, col_key, is_abs))

    output: dict[str, dict] = {}

    try:
        # c. 每个 account 组一次 DB 查询
        active_filter = await get_active_filter(
            db, TbBalance.__table__, project_id, year
        )

        for account, group_items in account_groups.items():
            # 查 account_code == account OR startswith(account)
            stmt = sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(
                active_filter,
                sa.or_(
                    TbBalance.account_code == account,
                    TbBalance.account_code.startswith(account),
                ),
            )
            result = await db.execute(stmt)
            rows = result.fetchall()

            if not rows:
                continue

            # d. 只留叶子
            all_codes = [r.account_code for r in rows]
            leaf_rows = [r for r in rows if _is_leaf(r.account_code, all_codes)]

            if not leaf_rows:
                continue

            # 叶子码列表
            source_codes = [r.account_code for r in leaf_rows]

            # e. 对该 account 组内每条 binding 按 column SUM
            for binding, col_key, is_abs in group_items:
                db_col = F2_COLUMN_MAP[col_key]
                total = sum(
                    float(getattr(r, db_col, None) or 0) for r in leaf_rows
                )

                if is_abs:
                    total = abs(total)

                # f. 全零跳过
                if abs(total) < _ZERO_EPS:
                    continue

                anchor = binding.get("anchor", "")
                output[anchor] = {
                    "value": total,
                    "account": account,
                    "column": col_key,
                    "is_abs": is_abs,
                    "source_codes": source_codes,
                }

    except Exception as e:
        logger.warning("F2 extract_f2_category_values 查询异常: %s", e)
        return {}

    return output


# ---------------------------------------------------------------------------
# 默认绑定生成
# ---------------------------------------------------------------------------


#: 锚点里「同一 rowKey+field 对应多个科目码」时的分隔符。
#: 消费方（`_build_adjudication_prefill_v2`）解析前先按它截断，并把值**累加**。
ANCHOR_ACCOUNT_SEP = "@"

_FIELD_MAP_GROSS = {
    "opening": ("期初余额", False),
    "increase": ("借方发生额", False),
    "decrease": ("贷方发生额", False),
}
#: 跌价反转：期初取 ABS；计提=贷方（增加）；转回/核销=借方（减少）
_FIELD_MAP_IMPAIRMENT = {
    "opening": ("期初余额", True),
    "increase": ("贷方发生额", False),
    "decrease": ("借方发生额", False),
}


def build_default_bindings(
    inventory_accounts: list[dict] | None = None,
) -> list[dict]:
    """生成 F2-1 审定表标准公式绑定。

    Args:
        inventory_accounts: 本项目实际存货科目
            ``[{"code", "name", "row_key"}]``（render 由 `account_chart` + 名称归类得出）。
            **给了就按它生成**（一个 rowKey 可能对应多个码，如「周转材料」= 周转材料 +
            包装物 + 低值易耗品 → 每码一条 binding，锚点用 ``@code`` 后缀区分，
            消费方累加）。

            为 ``None`` / 空时回退 `F2_CATEGORIES` 的**兜底编码**，行为与改造前一致
            （零回归）—— 但要注意兜底编码在两版标准科目表下都可能不对，
            详见 `app.services.f2_extraction.category_rules` 的实证表。

    Returns:
        binding 列表（含 ``anchor`` / ``expression`` / ``formula_type`` / ``row_key``）。
    """
    if inventory_accounts:
        pairs = [
            (str(a.get("row_key") or ""), str(a.get("code") or ""))
            for a in inventory_accounts
            if a.get("row_key") and a.get("code")
        ]
    else:
        pairs = [(c["rowKey"], c["account"]) for c in F2_CATEGORIES]

    bindings: list[dict] = []
    multi = len(pairs) != len({rk for rk, _ in pairs})
    for row_key, account in pairs:
        if row_key == "impairment-provision":
            block, fm = "impairment", _FIELD_MAP_IMPAIRMENT
        else:
            block, fm = "gross", _FIELD_MAP_GROSS

        for field, (col_name, use_abs) in fm.items():
            expr = (
                f"ABS(TB('{account}','{col_name}'))"
                if use_abs
                else f"TB('{account}','{col_name}')"
            )
            anchor = f"F2-1-{block}-{row_key}-{field}"
            if multi:
                anchor = f"{anchor}{ANCHOR_ACCOUNT_SEP}{account}"
            bindings.append({
                "anchor": anchor,
                "expression": expr,
                "formula_type": "auto_calc",
                "row_key": row_key,
            })

    return bindings
