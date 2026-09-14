"""K1 其他应收款 — 专属渲染策略.

componentType: k1-other-receivables

科目定位**不硬编码前缀**，走报表映射规则链路（共享件
`app/services/four_table/report_line_accounts.py`）::

    报表行 BS-009「其他应收款」
      soe_standalone : TB('1221','期末余额') - TB('1231-03','期末余额') + TB('1131','期末余额')
      listed_*       : TB('1221','期末余额')
          │ 标准码 → account_mapping 反解
          ▼
    客户原始码：原值 1221 / 备抵 1231.03 / 附加 1131 应收股利、1132 应收利息

🔴 两条已修正的历史错误（DB 只读实证，项目 `0ec33ac9`/2025）：

1. **备抵科目取整个 `1231` 前缀** —— `1231` 下挂的是按应收款种类拆分的备抵子科目
   （`1231.01` 应收票据 / `1231.02` 应收账款 / `1231.03` 其他应收款 / `1231.05` 长期应收款）。
   旧实现取到 28,464,225.16，其中 26,401,719.77 属**应收账款**；K1 真值仅 `1231.03`
   的 900,217.36 → 虚增 31.6 倍。
2. **只取最深层级（`_aggregate_prefix_deepest`）** —— 客户科目树参差，只取 depth==2 会
   整段丢掉一级叶子 `1221.11 个人往来`（3,597,359.45）与 `1221.12 保证金及押金`
   （55,035,942.52）→ 原值少 21.7%，且「款项性质分布」最核心的保证金押金桶恒 0。
   现改为**叶子口径**（`four_table/leaf_aggregation.select_leaves`），叶子和 == 父科目
   `1221` 期末 269,885,933.03（逐分相等）。

返回 allResponses + projectContext + TB数据 + tb_source_codes（取数溯源）
+ adjudication_prefill（无持久化审定未审数时从 tb_balance 预填，含「与经审计的财务报表
核对」区的应收利息 / 应收股利 / 报表数三项）。

spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/
"""

from __future__ import annotations

import logging
import re

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
from app.services.four_table.k1_detail_seed import (
    build_k1_bad_debt_seed_from_tb,
    seed_k1_bad_debt,
)
from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
from app.services.four_table.parent_check import build_report_line_parent_check
from app.services.four_table.report_line_accounts import (
    ReportLineAccounts,
    resolve_report_line_accounts,
)
from app.services.four_table.tb_query import fetch_trial_balance_rows

from ._context import RenderContext

logger = logging.getLogger(__name__)

#: 🔴 科目定位声明的**唯一真源** = `four_table/k_cycle_specs.K_CYCLE_SPECS['K1']`
#:    （spec k-cycle-…-closure Task 6，2026-08-09 收敛）。
#:
#: 收敛前本模块自建一份 `ReportLineAccountSpec` 字面量，与声明表构成**双真源** ——
#: 改一处另一处不动就会让「render 取数」与「守卫/验收脚本读声明表」结论打架，
#: 而两侧各自的测试都是绿的（这正是平台反复踩到的缺陷模式）。
#:
#: 下面这批 `K1_*` 常量**保留名字但全部从声明表派生**：外部有 3 个消费方
#: （`_k1_import_export._resolve_k1_gross_prefixes` / `test_k1_adjudication_prefill`
#: / 本模块的备抵名称过滤与 `bad_debt_account_prefix`），改名会波及它们且无收益。
_K1_SPEC = K_CYCLE_SPECS["K1"]

#: 报表行次（DB 实证：四个准则的「其他应收款」行 row_code 均为 BS-009）
K1_REPORT_ROW_CODE = _K1_SPEC.row_code_soe

#: 兜底标准码：原值 1221 其他应收款、备抵 1231-03 坏账准备-其他应收款
K1_FALLBACK_GROSS = _K1_SPEC.fallback_standard
K1_FALLBACK_PROVISION = "1231-03"

#: 附加科目（报表行 BS-009 含它们，但 K1-1 第一段「项目【不含应收利息、应收股利】」
#: 明确排除 → 不并入原值，单独喂「与经审计的财务报表核对」区）
#: 声明表里的顺序是 `('1131', '1132')` = (应收股利, 应收利息)。
K1_DIVIDEND_STANDARD = _K1_SPEC.extra_standard_codes[0]
K1_INTEREST_STANDARD = _K1_SPEC.extra_standard_codes[1]

#: 备抵侧名称过滤（仅在反解退化为宽前缀 `1231` 时叠加，防把其它应收科目坏账算进 K1）
K1_PROVISION_NAME_FILTER = _K1_SPEC.provision_name_filter or "其他应收款"

#: 共享件所需的规格 —— 由声明表按准则派生。
#: 🔴 K1 两准则同码（`row_code_listed == row_code_soe == 'BS-009'`），故模块级
#:    常量取 soe 侧即可；`render()` 内仍按 `spec_for(applicable_standards)` 取，
#:    以便将来两侧分叉时自动跟随（本常量只作外部消费方的稳定入口）。
K1_ACCOUNT_SPEC = _K1_SPEC.spec_for(["soe_standalone"])

# 款项性质关键词 → K1-1 nature syncKey（与前端 `classifyK1Nature` 逐条同源）
_NATURE_RULES: list[tuple[str, str]] = [
    (r"保证金", "margin"),
    (r"押金", "deposit"),
    (r"备用金", "petty"),
    (r"往来|代垫|关联", "intercompany"),
]

#: 披露 sheet 名 = 源 xlsx 真实中文 tab 名（openpyxl 实测 `wb.sheetnames`）。
#: 🔴 上市侧是**前半角后全角**括号；国企侧是「国企」而非「国有企业」。
#: 前端同源常量 = `k1NoteSectionMap.K1_DISCLOSURE_SHEET_NAME`（守卫
#: `test_note_k_sheet_names.py` 直读源 xlsx 比对）。
K1_DISCLOSURE_SHEET_LISTED = "附注披露信息(上市公司）"
K1_DISCLOSURE_SHEET_SOE = "附注披露信息（国企）"

K1_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "k1-other-receivables"},
    {"sheet_name": "其他应收款实质性程序表K1A", "component_type": "k1-other-receivables"},
    {"sheet_name": "审定表K1-1", "component_type": "k1-other-receivables"},
    {"sheet_name": "明细表K1-2", "component_type": "k1-other-receivables"},
    {"sheet_name": "坏账准备明细表K1-3", "component_type": "k1-other-receivables"},
    {"sheet_name": "调整分录汇总K1-4", "component_type": "k1-other-receivables"},
    {"sheet_name": "大额其他应收款情况分析表K1-5", "component_type": "k1-other-receivables"},
    {"sheet_name": "信用减值损失会计政策检查K1-6", "component_type": "k1-other-receivables"},
    {"sheet_name": "三阶段划分检查表K1-7", "component_type": "k1-other-receivables"},
    {"sheet_name": "坏账准备测算K1-8", "component_type": "k1-other-receivables"},
    {"sheet_name": "坏账准备转回收回核销检查表K1-9", "component_type": "k1-other-receivables"},
    {"sheet_name": "长期未收回款项检查表K1-10", "component_type": "k1-other-receivables"},
    {"sheet_name": "关联方及交易检查表K1-11", "component_type": "k1-other-receivables"},
    {"sheet_name": "其他应收款检查表K1-12", "component_type": "k1-other-receivables"},
    {"sheet_name": K1_DISCLOSURE_SHEET_LISTED, "component_type": "k1-other-receivables"},
    {"sheet_name": K1_DISCLOSURE_SHEET_SOE, "component_type": "k1-other-receivables"},
]


def _classify_nature(name: str) -> str:
    text = (name or "").strip()
    for pattern, key in _NATURE_RULES:
        if re.search(pattern, text):
            return key
    return "other-nature"


def _apply_provision_name_filter(
    leaves: list[LeafRow], accounts: ReportLineAccounts
) -> list[LeafRow]:
    """备抵侧反解退化为宽前缀时叠加名称过滤（`provision_exact=False` 才生效）。"""
    if accounts.provision_exact:
        return leaves
    kw = K1_PROVISION_NAME_FILTER
    return [r for r in leaves if kw in (r.account_name or "")]


async def _fetch_tb_balance_all(ctx: RenderContext) -> list[LeafRow]:
    """取 active 数据集**全部** `tb_balance` 行（**不筛叶子**，失败返 []，fail-open）。

    🔴 为什么必须给全量而不是叶子：``parent_check`` 的 ``parent`` 口径取的是**父科目
    行本身**的金额（:func:`leaf_aggregation.parent_totals` 按 ``account_code == 前缀``
    精确取行）。预先筛掉父行会让 ``parent`` 恒 0 —— 而共享件对 ``parent == 0`` 的处理
    是「该侧不参与 ``consistent`` 判定」⇒ 三口径静默退化成两口径，**不会报错也不会打红**。

    叶子由调用方经 :func:`leaf_aggregation.select_leaves` 派生（纯函数，无额外查询）。
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
        return to_leaf_rows(result.fetchall())
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 TB balance fetch failed: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        return []


async def _fetch_trial_balance_amounts(
    ctx: RenderContext, standard_codes: list[str]
) -> dict[str, dict[str, float]]:
    """按标准码前缀取 `trial_balance` 未审/审定额。

    返回 ``{标准码: {"unadjusted","audited"}}``；标准码用**精确前缀**匹配
    （`1231-03` 只命中 `1231-03*`，不会误吃 `1231-02`）。失败返 ``{}``。
    """
    codes = [c for c in (standard_codes or []) if c]
    if not codes:
        return {}
    out: dict[str, dict[str, float]] = {c: {"unadjusted": 0.0, "audited": 0.0} for c in codes}
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
            # 最长前缀命中，避免 1231 与 1231-03 双计
            best = ""
            for c in codes:
                if (code == c or code.startswith(c)) and len(c) > len(best):
                    best = c
            if not best:
                continue
            out[best]["unadjusted"] += float(row.unadjusted_amount or 0)
            out[best]["audited"] += float(row.audited_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 trial_balance fetch failed: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
    return out


def _build_tb_values(
    leaves: list[LeafRow],
    accounts: ReportLineAccounts,
    tb_amounts: dict[str, dict[str, float]],
) -> dict[str, float]:
    """组装前端 `tb_values`（键名与 `GtK1OtherReceivables._loadTbData` 逐字对齐）。"""
    rec = aggregate_leaves(leaves, accounts.gross)
    prov_leaves = _apply_provision_name_filter(
        filter_by_prefixes(leaves, accounts.provision), accounts
    )
    bd = aggregate_leaves(prov_leaves, accounts.provision, absolute=True)

    tb: dict[str, float] = {
        "receivable_unadjusted_opening": rec["opening"],
        "receivable_unadjusted_closing": rec["closing"],
        "receivable_unadjusted_debit": rec["debit"],
        "receivable_unadjusted_credit": rec["credit"],
        "bad_debt_unadjusted_opening": bd["opening"],
        "bad_debt_unadjusted_closing": bd["closing"],
        "bad_debt_unadjusted_debit": bd["debit"],
        "bad_debt_unadjusted_credit": bd["credit"],
    }

    rec_tb = {"unadjusted": 0.0, "audited": 0.0}
    for code in accounts.gross_standard:
        got = tb_amounts.get(code)
        if got:
            rec_tb["unadjusted"] += got["unadjusted"]
            rec_tb["audited"] += got["audited"]
    bd_tb = {"unadjusted": 0.0, "audited": 0.0}
    for code in accounts.provision_standard:
        got = tb_amounts.get(code)
        if got:
            bd_tb["unadjusted"] += got["unadjusted"]
            bd_tb["audited"] += got["audited"]

    tb["receivable_unadjusted"] = rec_tb["unadjusted"]
    tb["receivable_audited"] = rec_tb["audited"]
    tb["bad_debt_unadjusted"] = abs(bd_tb["unadjusted"])
    tb["bad_debt_audited"] = abs(bd_tb["audited"])
    return tb


def _build_fs_reconciliation(
    leaves: list[LeafRow],
    accounts: ReportLineAccounts,
) -> dict[str, float]:
    """K1-1「与经审计的财务报表核对」区三项。

    - ``interest`` / ``dividend``：附加科目 1132 / 1131 的叶子期末合计。
    - ``report_total``：按 `BS-009` 公式中各 `TB()` **前置运算符**加权求和
      （`+` 加 / `-` 减），与报表引擎同口径（Property 10）。公式缺失时退化为
      「原值 − 备抵 + 附加」的默认口径。
    """
    def _closing(prefixes, *, absolute=False) -> float:
        return aggregate_leaves(leaves, prefixes, absolute=absolute)["closing"]

    dividend = _closing(accounts.extra.get(K1_DIVIDEND_STANDARD) or [])
    interest = _closing(accounts.extra.get(K1_INTEREST_STANDARD) or [])

    if accounts.signed_codes:
        total = 0.0
        for std_code, sign in accounts.signed_codes:
            if std_code in accounts.provision_standard:
                prefixes = accounts.provision
                amount = _closing(prefixes, absolute=True)
            elif std_code in accounts.extra:
                amount = _closing(accounts.extra[std_code])
            elif std_code in accounts.gross_standard:
                amount = _closing(accounts.gross)
            else:
                continue
            total += sign * amount
    else:
        prov = _closing(accounts.provision, absolute=True)
        total = _closing(accounts.gross) - prov + dividend + interest

    return {
        "interest": interest,
        "dividend": dividend,
        "report_total": total,
    }


def _build_adjudication_prefill(
    leaves: list[LeafRow],
    accounts: ReportLineAccounts,
) -> dict:
    """无持久化审定未审数时，从 `tb_balance` **叶子**预填 K1-1 各区块。

    返回::

        {
          "receivable_total": {"opening","closing","debit","credit"},
          "bad_debt_total": {...},
          "nature": { syncKey: {"opening","closing"}, ... },
          "portfolio": { "aging": {"opening","closing"} },
          "portfolio_provision": { "aging": {...} },
          "fs_reconciliation": {"interest","dividend","report_total"},
        }
    """
    if not leaves:
        return {}

    rec = aggregate_leaves(leaves, accounts.gross)
    prov_leaves = _apply_provision_name_filter(
        filter_by_prefixes(leaves, accounts.provision), accounts
    )
    bd = aggregate_leaves(prov_leaves, accounts.provision, absolute=True)

    # 性质分布：遍历原值侧**全部叶子**（含一级叶子），按科目名归类
    nature: dict[str, dict[str, float]] = {}
    for r in filter_by_prefixes(leaves, accounts.gross):
        key = _classify_nature(r.account_name) if r.account_name else "other-nature"
        bucket = nature.setdefault(key, {"opening": 0.0, "closing": 0.0})
        bucket["opening"] += r.opening
        bucket["closing"] += r.closing

    # 组合：客户科目表无信用风险组合维度 → 总额进账龄组合作未审兜底（审计师可改）
    portfolio = {"aging": {"opening": rec["opening"], "closing": rec["closing"]}}
    portfolio_bd = {"aging": {"opening": bd["opening"], "closing": bd["closing"]}}

    fs = _build_fs_reconciliation(leaves, accounts)

    non_zero = any(
        abs(v) >= 0.005
        for v in (
            rec["opening"], rec["closing"], bd["opening"], bd["closing"],
            fs["interest"], fs["dividend"], fs["report_total"],
        )
    )
    if not non_zero:
        return {}

    return {
        "receivable_total": rec,
        "bad_debt_total": bd,
        "nature": nature,
        "portfolio": portfolio,
        "portfolio_provision": portfolio_bd,
        "fs_reconciliation": fs,
    }


def _has_persisted_adjudication(responses_snapshot: dict) -> bool:
    """任一 K1-1-*-unadj 有非零值 → 视为已编辑，不再预填."""
    for item_id, payload in responses_snapshot.items():
        if not str(item_id).startswith("K1-1-") or not str(item_id).endswith("-unadj"):
            continue
        raw = (payload or {}).get("remark") or (payload or {}).get("conclusion") or ""
        try:
            if abs(float(raw)) >= 0.005:
                return True
        except (TypeError, ValueError):
            continue
    return False


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文（客户名/审计年度/bs_date/关联方）."""
    project_ctx: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "bs_date": "",
        "related_parties": [],
        "bad_debt_account_prefix": K1_FALLBACK_PROVISION,
    }
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
            if row.audit_year:
                project_ctx["bs_date"] = f"{row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 project context load failed: %s", e)

    # B19 关联方清单：供 K1-2 批量匹配 / K1-11 完整性校验
    try:
        rp_rows = (
            await ctx.db.execute(
                sa.text(
                    "SELECT name FROM related_party_registry "
                    "WHERE project_id = :pid AND is_deleted = false "
                    "AND name IS NOT NULL AND name <> ''"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchall()
        project_ctx["related_parties"] = [r.name for r in rp_rows if r.name]
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 render: related_parties 查询失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass

    return project_ctx


async def render(ctx: RenderContext) -> dict | None:
    """K1其他应收款渲染策略：allResponses + projectContext + TB数据 + 预填 + 取数溯源."""
    responses_snapshot: dict = {}
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 2000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "K1-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("K1 render responses load failed: %s", e)

    accounts = await resolve_report_line_accounts(ctx, K1_ACCOUNT_SPEC)
    all_rows = await _fetch_tb_balance_all(ctx)
    leaves = select_leaves(all_rows)
    tb_amounts = await _fetch_trial_balance_amounts(
        ctx,
        list(accounts.gross_standard)
        + list(accounts.provision_standard)
        + list(accounts.extra.keys()),
    )
    tb_values = _build_tb_values(leaves, accounts, tb_amounts)
    project_context = await _load_project_context(ctx)

    # 三口径自检（叶子和 / 父科目行 / trial_balance）——走跨循环共享件，
    # 不在本模块自写。实测本循环在某项目上 leaf==parent 成立而 trial 差 1.69 亿，
    # 只比对前两个口径发现不了（详见 `parent_check.build_report_line_parent_check`）。
    parent_check: dict = {}
    try:
        trial_rows = await fetch_trial_balance_rows(
            ctx.db,
            ctx.project_id,
            ctx.year,
            list(accounts.gross_standard) + list(accounts.provision_standard),
        )
        parent_check = build_report_line_parent_check(accounts, all_rows, trial_rows)
    except Exception as e:  # noqa: BLE001 — fail-open，不影响其余输出
        logger.warning("K1 parent_check 构造失败: %s", e)

    adjudication_prefill: dict = {}
    if not _has_persisted_adjudication(responses_snapshot):
        adjudication_prefill = _build_adjudication_prefill(leaves, accounts)

    # K1-3 坏账准备明细 ← 备抵科目叶子 transient seed（手工优先，fail-open）。
    # 三阶段拆分不做 seed（客户科目表无信用风险阶段维度，来自 K1-7）。
    try:
        bd_seed = build_k1_bad_debt_seed_from_tb(leaves, accounts.provision)
        seed_k1_bad_debt(responses_snapshot, bd_seed)
    except Exception as e:  # noqa: BLE001 — fail-open，不影响其余输出
        logger.warning("K1-3 坏账准备 seed 失败: %s", e)

    return {
        "component_type": "k1-other-receivables",
        "account_codes": list(accounts.gross_standard) + list(accounts.provision_standard),
        "responses_snapshot": responses_snapshot,
        "tb_values": tb_values,
        "tb_source_codes": accounts.as_dict(),
        "adjudication_prefill": adjudication_prefill,
        "parent_check": parent_check,
        "project_context": project_context,
        "prefix": "K1",
        "sheets": K1_SHEETS,
    }
