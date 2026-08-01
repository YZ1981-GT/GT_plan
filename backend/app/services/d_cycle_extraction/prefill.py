"""D-cycle Tier B 审定表预填（通用 `_build_adjudication_prefill` 范式）.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/
      (Requirements 1.1, 1.2, 1.3, 1.4, 1.6 / Property 1, 4, 12)

**收敛铁律**：镜像 K9/K1/N5 已证明的审定表预填范式（对齐 `_k9_admin_expenses.py::
_build_adjudication_prefill` / `_k1_other_receivables.py`），**不新造第 3 套四表库读取**：

  ① `get_active_filter(db, TbBalance.__table__, project_id, year)` —— 数据集版本过滤
     （canonical 异步 4 参签名，K9/K1 权威用法；**不用** N5 发散的单参降级写法，
      **不用**裸 `is_deleted`）。
  ② 按 `account_code + account_name` 汇总 `startswith(account_prefix)` 且 `!= account_prefix`
     的子科目（排除科目本身，只看明细）。
  ③ **只取叶子科目**（其 code 不是任何其它 code 的前缀）—— 防中间级 rollup 与子科目
     双算（Property 1 / R1.4）。
  ④ 跳过零发生/零余额与无名称子科目（R1.4）。
  ⑤ `mode='balance'` → 返回 `opening_balance`/`closing_balance`（余额类 D1/D2/D3/D5/D6/D7）；
     `mode='occurrence'` → 返回 `debit_amount`/`credit_amount`（发生额类 D4 收入 6001）。
  ⑥ 无子科目 → 返回 `[]`（前端回退默认/空，Property 4 / R1.6）；查询异常 → `logger.warning`
     + 返回 `[]`（fail-open，不阻断 render）。

本模块为**可复用服务**：D1–D7 render 策略以各自 `account_prefix`/`mode` 调用。
本 Wave（Task 1.3）仅交付服务，不接入任何 render 策略（接入属 Wave 1+）。
手工优先（R1.5 / Property 2）由调用方（render）用 `responses_snapshot` 判定并入，
不在本函数职责内。
"""
from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)

# 支持的取数模式
MODE_BALANCE = "balance"
MODE_OCCURRENCE = "occurrence"
_VALID_MODES = (MODE_BALANCE, MODE_OCCURRENCE)

# 金额判零阈值（对齐 K9/K1：< 0.005 视为零，跳过）
_ZERO_EPS = 0.005


def _is_leaf(code: str, all_codes: list[str]) -> bool:
    """判定 `code` 是否为叶子科目（其 code 不是任何其它 code 的前缀）.

    铁律「只汇总叶子」——防止 tb_balance 中间级 rollup 与其子科目同时计入导致双算。
    与 K9 `_build_adjudication_prefill` 内联的 `_is_leaf` 同款语义。
    """
    if not code:
        return True
    return not any(c != code and c.startswith(code) for c in all_codes)


async def build_d_adjudication_prefill(
    ctx,
    *,
    account_prefix: str,
    mode: str,
) -> list[dict]:
    """从 `tb_balance` 指定科目前缀的叶子子科目预填 D-cycle 审定表未审数行.

    镜像 K9/K1 范式（get_active_filter + 叶子级 SUM + 跳零/无名）。

    Args:
        ctx: RenderContext（需 `db` / `project_id` / `year`）。
        account_prefix: 科目前缀（D1=1121 / D2=1122 / D3=2203 / D4=6001 /
            D5=1124 / D6=1141 / D7=2205）。
        mode: `'balance'`（余额类，取期初/期末余额）或
            `'occurrence'`（发生额类，取借/贷发生额）。

    Returns:
        `list[dict]`：
          * balance → `[{code, name, opening_balance, closing_balance}, ...]`
          * occurrence → `[{code, name, debit_amount, credit_amount}, ...]`
        按金额降序。无子科目 / 查询失败 → `[]`（fail-open，不阻断 render）。
    """
    if mode not in _VALID_MODES:
        logger.warning(
            "build_d_adjudication_prefill: 非法 mode=%r（应为 balance/occurrence），返回空",
            mode,
        )
        return []
    if not account_prefix:
        return []

    rows: list[dict] = []
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        # 按 account_code 汇总（保留 code 以做叶子判定），排除科目本身（只看明细子科目）
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code.label("code"),
                TbBalance.account_name.label("name"),
                sa.func.sum(TbBalance.opening_balance).label("opening"),
                sa.func.sum(TbBalance.closing_balance).label("closing"),
                sa.func.sum(TbBalance.debit_amount).label("debit"),
                sa.func.sum(TbBalance.credit_amount).label("credit"),
            )
            .where(
                active_filter,
                TbBalance.account_code.startswith(account_prefix),
                TbBalance.account_code != account_prefix,
            )
            .group_by(TbBalance.account_code, TbBalance.account_name)
        )
        raw = [
            {
                "code": (r.code or "").strip(),
                "name": (r.name or "").strip(),
                "opening": float(r.opening or 0),
                "closing": float(r.closing or 0),
                "debit": float(r.debit or 0),
                "credit": float(r.credit or 0),
            }
            for r in result.fetchall()
        ]

        # 只取叶子科目（Property 1 / R1.4：防 rollup 双算）
        all_codes = [x["code"] for x in raw if x["code"]]
        leaves = [x for x in raw if _is_leaf(x["code"], all_codes)]

        if mode == MODE_BALANCE:
            leaves.sort(key=lambda x: abs(x["closing"]), reverse=True)
            for x in leaves:
                name = x["name"]
                # 跳过无名称或零余额子科目（R1.4）
                if not name or (
                    abs(x["opening"]) < _ZERO_EPS and abs(x["closing"]) < _ZERO_EPS
                ):
                    continue
                rows.append({
                    "code": x["code"],
                    "name": name,
                    "opening_balance": x["opening"],
                    "closing_balance": x["closing"],
                })
        else:  # MODE_OCCURRENCE
            leaves.sort(key=lambda x: abs(x["debit"]) + abs(x["credit"]), reverse=True)
            for x in leaves:
                name = x["name"]
                # 跳过无名称或零发生额子科目（R1.4）
                if not name or (
                    abs(x["debit"]) < _ZERO_EPS and abs(x["credit"]) < _ZERO_EPS
                ):
                    continue
                rows.append({
                    "code": x["code"],
                    "name": name,
                    "debit_amount": x["debit"],
                    "credit_amount": x["credit"],
                })
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "build_d_adjudication_prefill 失败（prefix=%s, mode=%s）: %s",
            account_prefix, mode, e,
        )
        return []

    return rows
