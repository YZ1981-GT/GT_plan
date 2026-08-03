"""K2 其他流动资产 — 专属渲染策略.

componentType: k2-other-current-assets

科目定位**不硬编码前缀**，走报表映射规则链路（共享件
`app/services/four_table/report_line_accounts.py`，K1 spec 建立，K2 是第三个消费者）::

    报表行 BS-014「其他流动资产」
      soe_* / listed_consolidated : TB('1901','期末余额')
      listed_standalone          : TB('1901','期末余额') + TB('1131','期末余额')
          │ 标准码 → account_mapping 反解
          ▼
    客户原始码：原值 1901 待处理财产损溢（1131 应收股利单列，见下）

🔴 已修正的历史错误（DB 只读 + 活体 render-config 实证）：

**原实现把 `1231 坏账准备` 当成其他流动资产**（注释还写着「1231其他流动资产(借方/资产类)」）。
`1231` 是应收款项的**贷方备抵科目**，与其他流动资产毫无关系，且会与 D1/D2/K1 的坏账准备
重复计入。实测后果：

  * 项目 `0ec33ac9` / wp `919e3387`：`tb_values.other_current_audited = 28,464,225.16`，
    `adjudication_prefill` 建出 3 行「坏账准备_应收账款 26,401,719.77 /
    坏账准备_应收票据 1,162,288.03 / 坏账准备_其他应收款 900,217.36」——
    把别的循环的备抵科目当资产列示。
  * 项目 `2aa00f57` / wp `d5f0d168`：同款，金额为负（备抵原始符号）。

`1131 应收股利` 虽被 `BS-014 listed_standalone` 公式引用，但它已被 `BS-009 其他应收款`
占用（K1 循环），并入其他流动资产会**重复计入资产** → 声明为 `extra_standard_codes`
单列输出，不进原值。这条属 `report_config` 的 data-hygiene 问题，本模块只做不重复计入。

其他流动资产**无备抵科目** → `provision` 为空是正常态。

明细项目行按客户实际情况增删（源模板上市披露 sheet A5 逐字写「根据实际情况列示；
不存在的项目请删除」），故预填只按**实际叶子科目**建候选行，**宁缺勿造** ——
解析不出科目就返回空列表，不再塞兜底行。

spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.leaf_aggregation import (
    LeafRow,
    aggregate_leaves,
    filter_by_prefixes,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.report_line_accounts import (
    ReportLineAccounts,
    ReportLineAccountSpec,
    resolve_report_line_accounts,
)

from ._context import RenderContext
from app.services.four_table.semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec, resolve_semantic_accounts

logger = logging.getLogger(__name__)

#: 报表行次（DB 实证：四个准则的「其他流动资产」行 row_code 均为 BS-014；
#: 另有 `BS-017` 同名行但 formula 为 NULL，故必须按 **row_code 精确匹配**，不按 row_name）
K2_REPORT_ROW_CODE = "BS-014"

#: 兜底标准码：1901 待处理财产损溢（报表公式实际引用的科目）
K2_FALLBACK_GROSS = "1901"

#: 报表公式引用但**不并入原值**的科目：1131 应收股利已属 BS-009 其他应收款
K2_DIVIDEND_STANDARD = "1131"

K2_ACCOUNT_SPEC = ReportLineAccountSpec(
    row_code=K2_REPORT_ROW_CODE,
    fallback_gross=(K2_FALLBACK_GROSS,),
    fallback_provision=(),  # 其他流动资产无备抵科目
    provision_name_filter=None,
    extra_standard_codes=(K2_DIVIDEND_STANDARD,),
)

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测 `wb.sheetnames`）。
#: 🔴 国企侧是「国企」而非「国有企业」（原写错，导致 `?sheet=` 深链落空）。
#: 前端同源常量 = `k2NoteSectionMap.K2_DISCLOSURE_SHEET_NAME`。
K2_DISCLOSURE_SHEET_LISTED = "附注披露信息（上市公司）"
K2_DISCLOSURE_SHEET_SOE = "附注披露信息（国企）"

K2_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k2-other-current-assets"},
    {"sheet_name": "其他流动资产实质性程序表K2A", "component_type": "k2-other-current-assets"},
    {"sheet_name": "审定表K2-1", "component_type": "k2-other-current-assets"},
    {"sheet_name": "明细表K2-2", "component_type": "k2-other-current-assets"},
    {"sheet_name": "调整分录汇总K2-3", "component_type": "k2-other-current-assets"},
    {"sheet_name": "合同取得成本明细表K2-4", "component_type": "k2-other-current-assets"},
    {"sheet_name": "摊销测算表K2-5", "component_type": "k2-other-current-assets"},
    {"sheet_name": "其他流动资产检查表K2-6", "component_type": "k2-other-current-assets"},
    {"sheet_name": K2_DISCLOSURE_SHEET_LISTED, "component_type": "k2-other-current-assets"},
    {"sheet_name": K2_DISCLOSURE_SHEET_SOE, "component_type": "k2-other-current-assets"},
]

#: `tb_values` 键前缀（**保持不变** —— 前端 `GtK2OtherCurrentAssets` 已在读这些键，
#: 改键名会静默断链；本次只改取数口径）
_UNADJ_KEY = "other_current_unadjusted"
_AUDITED_KEY = "other_current_audited"


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（可单测，无 DB）
# ─────────────────────────────────────────────────────────────────────────────


def build_tb_values(
    leaves: list[LeafRow],
    accounts: ReportLineAccounts,
    tb_amounts: dict[str, dict[str, float]],
) -> dict[str, float]:
    """组装前端 `tb_values`（键名与 `GtK2OtherCurrentAssets` 读取的字段逐字对齐）。

    `tb_amounts` 是 ``{标准码: {"unadjusted","audited"}}``，由
    :func:`fetch_trial_balance_amounts` 按**最长前缀**归属后给出（防父子双计）。
    """
    agg = aggregate_leaves(leaves, accounts.gross)
    tb: dict[str, float] = {
        f"{_UNADJ_KEY}_opening": agg["opening"],
        f"{_UNADJ_KEY}_closing": agg["closing"],
        f"{_UNADJ_KEY}_debit": agg["debit"],
        f"{_UNADJ_KEY}_credit": agg["credit"],
    }
    unadj = 0.0
    audited = 0.0
    for code in accounts.gross_standard:
        got = tb_amounts.get(code)
        if got:
            unadj += got["unadjusted"]
            audited += got["audited"]
    tb[_UNADJ_KEY] = unadj
    tb[_AUDITED_KEY] = audited
    return tb


def build_adjudication_prefill(
    leaves: list[LeafRow],
    accounts: ReportLineAccounts,
) -> list[dict]:
    """按**原值侧叶子科目**建 K2-1 动态行候选。

    返回 ``[{name, code, opening_balance, closing_balance}]``，按期末绝对值降序；
    前端在**无持久化行**时据此建动态行（行名 = 科目名，审计师可改可删）。

    **宁缺勿造**：科目名为空或期初期末双零的叶子跳过；解析不出任何科目返回 ``[]``
    —— 不再像旧实现那样把无法匹配的行一律塞进「其他」兜底行。
    """
    picked = filter_by_prefixes(leaves, accounts.gross)
    rows: list[dict] = []
    for r in picked:
        name = (r.account_name or "").strip()
        if not name:
            continue
        if abs(r.opening) < 0.005 and abs(r.closing) < 0.005:
            continue
        rows.append(
            {
                "name": name,
                "code": r.account_code,
                "opening_balance": r.opening,
                "closing_balance": r.closing,
            }
        )
    rows.sort(key=lambda x: abs(x["closing_balance"]), reverse=True)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# DB 访问（全程 fail-open）
# ─────────────────────────────────────────────────────────────────────────────


async def fetch_tb_balance_leaves(ctx: RenderContext) -> list[LeafRow]:
    """取 active 数据集全部 `tb_balance` 行并筛出叶子（失败返 []，fail-open）。"""
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
        logger.warning("K2 TB balance fetch failed: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        return []


async def fetch_trial_balance_amounts(
    ctx: RenderContext, standard_codes: list[str]
) -> dict[str, dict[str, float]]:
    """按标准码取 `trial_balance` 未审/审定额，**最长前缀**归属（防父子双计）。

    入参先 strip —— 空白串是「真前缀」会命中**所有**行（`code.startswith('')` 恒真），
    必须与空串同样剔除。
    """
    codes = [s for c in (standard_codes or []) if (s := str(c or "").strip())]
    if not codes:
        return {}
    out: dict[str, dict[str, float]] = {
        c: {"unadjusted": 0.0, "audited": 0.0} for c in codes
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
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            if not code:
                continue
            best = ""
            for c in codes:
                if (code == c or code.startswith(c)) and len(c) > len(best):
                    best = c
            if not best:
                continue
            out[best]["unadjusted"] += float(row.unadjusted_amount or 0)
            out[best]["audited"] += float(row.audited_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("K2 trial_balance fetch failed: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
    return out


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度）."""
    project_ctx: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": str(ctx.wp_id)},
        )
        row = result.fetchone()
        if row:
            project_ctx["client_name"] = row.client_name or ""
            project_ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
            project_ctx["business_category"] = row.business_category or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("K2 project context load failed: %s", e)
    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K2其他流动资产渲染策略：allResponses + projectContext + TB数据 + 取数溯源."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K2-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K2 render responses load failed: %s", e)

    accounts = await resolve_report_line_accounts(ctx, K2_ACCOUNT_SPEC)
    leaves = await fetch_tb_balance_leaves(ctx)
    tb_amounts = await fetch_trial_balance_amounts(
        ctx, list(accounts.gross_standard) + list(accounts.extra.keys())
    )
    tb_values = build_tb_values(leaves, accounts, tb_amounts)
    project_context = await _load_project_context(ctx)
    adjudication_prefill = build_adjudication_prefill(leaves, accounts)

    return {
        "component_type": "k2-other-current-assets",
        "account_codes": list(accounts.gross_standard),
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": accounts.as_dict(),
        "project_context": project_context,
        "adjudication_prefill": adjudication_prefill,
        "prefix": "K2",
        "sheets": K2_SHEETS,
    }
