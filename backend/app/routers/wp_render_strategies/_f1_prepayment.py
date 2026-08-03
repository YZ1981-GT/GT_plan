"""F1 预付账款 — 专属渲染策略.

component_type = "f1-prepayment"

四表库科目映射链路（三层，DB 只读实证 2026-07-31）
--------------------------------------------------

::

    tb_balance.account_code             客户**原始码**（点号分级）  1123 / 1123.02.01 / 1231.03
            │  account_mapping(project_id, original_account_code → standard_account_code)
            ▼
    trial_balance.standard_account_code **标准码**（横杠分级）      1123 / 1231-04
            │  report_config.formula（按 applicable_standard 精确匹配）
            ▼
    报表行 BS-008「预付款项」
      listed_standalone / listed_consolidated / soe_standalone / soe_consolidated
        一律 = TB('1123','期末余额')        ← 四准则同形，且**不减备抵**

由此得到三条实现口径（全部经实证，勿凭直觉改）：

1. **原值科目必须经报表映射解析 + `account_mapping` 反解**，不能硬编码前缀 ——
   客户把预付拆到自定义科目时硬编码必落空。实证 `account_mapping` 把
   `1123` / `1123.01` / `1123.02.*` / `1123.03` / `1123.99` 全部映射到标准码 `1123`，
   `minimal_prefix_set` 收敛为 `['1123']`。
2. **备抵科目（坏账准备-预付账款）报表公式里没有** → 走 `fallback_provision=('1231-04',)`；
   且实证 9 个项目的 `account_mapping` **全部没有** `1231-04` 记录（只有 `-01/-02/-03`
   与裸 `1231`）→ 反解退化为宽前缀 `1231`，**必须叠名称过滤「预付」**，否则会把
   应收账款坏账（实证项目 `0ec33ac9` 为 26,401,719.77）算进 F1。过滤后当前数据集为空
   → 减值准备无预填（宁缺勿造，正确）。
3. **`1123` 的叶子子科目名带业务语义**，可干净映射到 F1-1「按性质分类」五行：

   ===============  ================================  ===========
   原始码            科目名                             性质行
   ===============  ================================  ===========
   ``1123.01``      预付账款_预付货款                    货款
   ``1123.02.01``   预付账款_长期资产款_一次购置          设备款
   ``1123.02.02``   预付账款_长期资产款_分期购置          设备款
   ``1123.02.03``   预付账款_长期资产款_工程款            工程款
   ``1123.03``      预付账款_短期待摊费用                服务费
   ``1123.99``      预付账款_其他                       其他
   ===============  ================================  ===========

   这正是 F1 与 D3（2203 无性质维度，归档 spec 判定「宁缺勿造不做 prefill」）的本质差异，
   故 F1 做审定表预填是有据的。

叶子聚合与科目定位一律复用平台共享件 ``app/services/four_table``（K1 spec 建成、D1 已委托），
禁止再造方言 —— 旧实现的 ``_is_leaf`` 用 ``startswith`` 缺点号边界（``1123.1`` 会被
``1123.10`` 误判为非叶子；前缀 ``2202`` 会误吃 ``22020``）。

spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table import (
    LeafRow,
    ReportLineAccounts,
    ReportLineAccountSpec,
    aggregate_leaves,
    filter_by_code_specs,
    filter_by_prefixes,
    parent_totals,
    resolve_report_line_accounts,
    select_leaves,
    sql_prefixes_for_specs,
    to_leaf_rows,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

#: 预付款项报表行定位规格（原值 BS-008 / 备抵兜底 1231-04 / 宽前缀时叠「预付」名称过滤）
F1_REPORT_LINE_SPEC = ReportLineAccountSpec(
    row_code="BS-008",
    fallback_gross=("1123",),
    fallback_provision=("1231-04",),
    provision_name_filter="预付",
)

#: F1-4 实质性分析跨循环锚点 —— 同样走报表映射规则，不硬编码前缀。
#:
#: 🔴 旧实现用前缀 ``1401`` 取「存货余额」是**错的**：标准科目表 ``1401 = 材料采购``，
#: 存货合计是 ``BS-010 = SUM_TB('1401~1499','期末余额')``（实证两个真实项目的
#: ``1401`` 均为空 → F1-4「存货余额」与「占存货比重」恒 0，该分析从来算不出）。
#: 应付账款报表行是 ``BS-045``（``TB('2202','期末余额')``）。
_F1_INVENTORY_ROW_CODE = "BS-010"
_F1_INVENTORY_FALLBACK = ("1401~1499",)
_F1_PAYABLE_ROW_CODE = "BS-045"
_F1_PAYABLE_FALLBACK = ("2202",)

#: F1-1「按性质分类」行 key（与前端 `useF1Adjudication.NATURE_ROWS` 逐字一致）
F1_NATURE_ROW_KEYS = ("goods", "construction", "equipment", "service", "other")

#: 性质归类关键字。**顺序即优先级**：`1123.02.03 长期资产款_工程款` 同时含
#: 「长期资产」与「工程」，源模板口径归「工程款」→ 工程必须先判。
_NATURE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("construction", ("工程", "施工", "基建")),
    ("equipment", ("设备", "长期资产", "购置", "固定资产", "器具")),
    ("service", ("服务", "待摊", "费用", "保险", "租金", "运费", "咨询")),
    ("goods", ("货款", "材料", "商品", "采购", "存货", "药品")),
)

_NATURE_DEFAULT = "other"


# ─────────────────────────── 纯函数（无 DB，可单测） ───────────────────────────


# 🔴 `sql_prefixes_for_specs` / `filter_by_code_specs` 已提升为四表库共享件
#   （`app/services/four_table/leaf_aggregation`）—— F5 的 `IS-002` 是
#   `SUM_TB('6401~6499')` 区间口径，需要同款能力，不得再抄一份。
#   此处保留同名 re-export：F1 既有测试与本文件下方调用点零改动。
#   spec: .kiro/specs/f-cycle-four-table-extraction-and-disclosure-completion/


def classify_f1_nature(account_name: str) -> str:
    """按科目名把 `1123` 叶子归入 F1-1 五个性质桶。返回 rowKey。

    未命中任何关键字一律归 ``other``（不丢科目，Property 2）。
    """
    name = str(account_name or "")
    for row_key, hints in _NATURE_RULES:
        if any(h in name for h in hints):
            return row_key
    return _NATURE_DEFAULT


def build_nature_prefill(
    leaves: list[LeafRow],
    prefixes,
) -> dict[str, dict[str, float]]:
    """把 `1123` 叶子按性质归集为 F1-1 预填。

    Returns:
        ``{rowKey: {"opening": x, "closing": y}}``；只包含**实际出现**的性质桶
        （前端据此「只覆盖出现的类别、不清零未出现的类别」）。无叶子返回 ``{}``。
    """
    picked = filter_by_prefixes(leaves, prefixes)
    out: dict[str, dict[str, float]] = {}
    for row in picked:
        key = classify_f1_nature(row.account_name)
        bucket = out.setdefault(key, {"opening": 0.0, "closing": 0.0})
        bucket["opening"] += row.opening
        bucket["closing"] += row.closing
    return {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in out.items()}


def build_impairment_prefill(
    leaves: list[LeafRow],
    prefixes,
    *,
    name_filter: str | None = None,
) -> dict[str, float] | None:
    """备抵科目（坏账准备-预付账款）期初/期末预填。

    Args:
        leaves: 已 :func:`select_leaves` 的叶子行。
        prefixes: 备抵侧**原始码**前缀集。
        name_filter: 反解退化为宽前缀时必须传（如 ``"预付"``），否则会把其它
            应收科目的坏账算进来。

    Returns:
        ``{"end": x, "prior": y}``（对聚合结果取绝对值，兼容两种符号约定）；
        无命中科目返回 ``None``（宁缺勿造 —— 由前端保持手工录入）。
    """
    picked = filter_by_prefixes(leaves, prefixes)
    if name_filter:
        picked = [r for r in picked if name_filter in (r.account_name or "")]
    if not picked:
        return None
    agg = aggregate_leaves(picked, [r.account_code for r in picked], absolute=True)
    return {"end": round(agg["closing"], 2), "prior": round(agg["opening"], 2)}


def resolve_impairment_prefill(
    tb_balance_result: dict[str, float] | None,
    trial_balance_end: float | None,
) -> dict[str, float] | None:
    """合并两条减值准备取数路径（纯函数）。

    为什么需要两条路径（postgres 实证，项目 ``0ec33ac9`` / 2025）：

    - ``account_mapping`` 只有 ``1231→1231`` / ``1231.01→1231-01`` / ``1231.02→1231-02``
      / ``1231.03→1231-03``，**没有** ``1231-04``；
    - 而 ``trial_balance`` **确有** ``1231-04 坏账准备-预付账款`` 行。

    → 「标准码 → 反解原始码 → ``tb_balance`` 前缀」路径必然退化为宽前缀 ``1231``，
    叠「预付」名称过滤后命中为空；而标准码直查 ``trial_balance`` 可精确命中。
    这也解释了为什么公式预设 ``TB('1231-04','期末余额')``（走 ``trial_balance``）
    与旧 ``impairment_prefill``（走 ``tb_balance``）口径不同。

    Args:
        tb_balance_result: :func:`build_impairment_prefill` 的结果（含期初+期末）。
        trial_balance_end: ``trial_balance`` 标准码口径的**期末**减值准备。

    Returns:
        - ``tb_balance`` 路径有结果 → 原样返回（它同时给期初+期末，信息更全）；
        - 否则 ``trial_balance`` 期末非零 → ``{"end": x}``（**故意不含 prior**：
          ``trial_balance`` v2 无期初列，臆造期初会让披露表「上年年末减值准备」出错）；
        - 两条都空 → ``None``（宁缺勿造，由前端保持手工录入）。
    """
    if tb_balance_result:
        return tb_balance_result
    if trial_balance_end is not None and abs(trial_balance_end) > 1e-9:
        return {"end": round(float(trial_balance_end), 2)}
    return None


# ─────────────────────────── DB 访问（全程 fail-open） ───────────────────────────


async def _resolve_f1_accounts(ctx: RenderContext) -> ReportLineAccounts:
    """解析 F1 原值 / 备抵科目（报表映射规则驱动；内部已 fail-open）。"""
    return await resolve_report_line_accounts(ctx, F1_REPORT_LINE_SPEC)


async def _resolve_line_codes(
    ctx: RenderContext, row_code: str, fallback
) -> list[str]:
    """解析某报表行的科目编号规格（含 ``lo~hi`` 区间），按项目适用准则精确匹配。"""
    from app.services.four_table.report_line_accounts import fetch_applicable_standards
    from app.services.report_account_mapping import resolve_report_line_account_codes

    try:
        standards = await fetch_applicable_standards(ctx)
        return list(
            await resolve_report_line_account_codes(
                ctx.db,
                ctx.project_id,
                row_code,
                fallback=list(fallback),
                applicable_standards=standards,
            )
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("F1 render: %s 科目解析失败（用兜底）: %s", row_code, e)
        return list(fallback)


async def _fetch_f1_leaf_rows(ctx: RenderContext, prefixes) -> list[LeafRow]:
    """按前缀集从 `tb_balance` 取行并筛出叶子（active 数据集，过滤下推到 SQL）。

    🔴 必须把整棵子树都取回来才能判叶子（父行也要），故 SQL 用 ``LIKE '{prefix}%'``
    宽取，再由 :func:`select_leaves` / :func:`filter_by_prefixes` 做**严格点号边界**收敛。
    """
    ps = [p for p in dict.fromkeys(str(p or "").strip() for p in prefixes) if p]
    if not ps:
        return []
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )
        prefix_filter = sa.or_(
            *[TbBalance.account_code.like(f"{p}%") for p in ps]
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
            ).where(sa.and_(active_filter, prefix_filter))
        )
        return select_leaves(to_leaf_rows(result.fetchall()))
    except Exception as e:  # noqa: BLE001
        logger.warning("F1 render: tb_balance 取数失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        return []


async def _fetch_f1_1123_audited(
    ctx: RenderContext, codes: list[str]
) -> float | None:
    """从 trial_balance(v2 正数口径) 取预付款项审定数(无则未审数)，供 F1-1 试算核对预填."""
    from app.services.report_account_mapping import build_trial_balance_code_filter

    where_clause, params = build_trial_balance_code_filter(codes)
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT unadjusted_amount, audited_amount "
                "FROM trial_balance "
                "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                f"AND {where_clause}"
            ),
            {"pid": str(ctx.project_id), "year": ctx.year, **params},
        )
        audited = 0.0
        unadjusted = 0.0
        found = False
        for row in result.fetchall():
            found = True
            audited += float(row.audited_amount or 0)
            unadjusted += float(row.unadjusted_amount or 0)
        if not found:
            return None
        return audited if abs(audited) > 1e-9 else unadjusted
    except Exception as e:  # noqa: BLE001
        logger.warning("F1 render: trial_balance 1123 取数失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        return None


async def _fetch_provision_from_trial_balance(
    ctx: RenderContext, standard_codes: list[str]
) -> float | None:
    """按备抵**标准码**从 `trial_balance` 取期末减值准备（审定优先、回退未审）。

    与 :func:`_fetch_f1_1123_audited` 同一范式（同一张表、同一过滤器构造），
    差别只在取绝对值 —— 备抵是贷方科目，两种符号约定下 ``abs`` 同解。

    🔴 **不叠名称过滤**：本路径吃的是标准码（`1231-04` 语义就是「坏账准备-预付账款」），
    再叠「预付」会把客户命名不含该词的行误杀。名称过滤只属 ``tb_balance`` 宽前缀路径。

    Returns:
        期末减值准备（绝对值）；无命中行或异常返回 ``None``（fail-open）。
    """
    from app.services.report_account_mapping import build_trial_balance_code_filter

    codes = [c for c in (str(x or "").strip() for x in standard_codes or []) if c]
    if not codes:
        return None
    where_clause, params = build_trial_balance_code_filter(codes)
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT unadjusted_amount, audited_amount "
                "FROM trial_balance "
                "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                f"AND {where_clause}"
            ),
            {"pid": str(ctx.project_id), "year": ctx.year, **params},
        )
        audited = 0.0
        unadjusted = 0.0
        found = False
        for row in result.fetchall():
            found = True
            audited += float(row.audited_amount or 0)
            unadjusted += float(row.unadjusted_amount or 0)
        if not found:
            return None
        picked = audited if abs(audited) > 1e-9 else unadjusted
        return round(abs(picked), 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("F1 render: trial_balance 备抵取数失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:
            pass
        return None


async def render(ctx: RenderContext) -> dict | None:
    """F1 预付账款渲染策略."""
    wp_id = ctx.wp_id
    db = ctx.db

    # rowKey 与前端 useF1Adjudication.NATURE_ROWS 对齐（前端以自身常量为准，此处仅作参考元数据）
    adjudication_config = {
        "nature_rows": [
            {"rowKey": "goods", "label": "货款"},
            {"rowKey": "construction", "label": "工程款"},
            {"rowKey": "equipment", "label": "设备款"},
            {"rowKey": "service", "label": "服务费"},
            {"rowKey": "other", "label": "其他"},
        ],
        "aging_rows": [
            {"rowKey": "within-1-year", "label": "1年以内含1年"},
            {"rowKey": "1-to-2-years", "label": "1至2年含2年"},
            {"rowKey": "2-to-3-years", "label": "2至3年含3年"},
            {"rowKey": "over-3-years", "label": "3年以上"},
        ],
    }

    sections = [
        {"code": "F1A", "label": "F1A 程序表", "type": "procedure"},
        {"code": "F1-1", "label": "F1-1 审定表", "type": "adjudication"},
        {"code": "F1-2", "label": "F1-2 明细表", "type": "detail"},
        {"code": "F1-3", "label": "F1-3 调整分录", "type": "adjustment"},
        {"code": "F1-4", "label": "F1-4 实质性分析", "type": "analysis"},
        {"code": "F1-5", "label": "F1-5 长期挂款检查", "type": "long_term"},
        {"code": "F1-6", "label": "F1-6 关联方检查", "type": "related_party"},
        {"code": "F1-7", "label": "F1-7 综合检查", "type": "comprehensive_check"},
        {"code": "F1-NOTE", "label": "附注", "type": "disclosure"},
        {"code": "F1-CONF", "label": "函证程序", "type": "confirmation_procedure"},
    ]

    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'F1-%' "
                "LIMIT 800"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("F1 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
        "applicable_standards": "",
        "bs_date": "",
        "related_parties": [],
        # F1-4 跨循环取数（tb_balance 期末余额；应付取绝对值供正数展示）
        "inventory_balance_current": 0.0,
        "payable_balance_current": 0.0,
        # F1-1 试算核对预填（预付款项审定/未审；组件只读回退 seed）
        "prepaid_tb_amount": 0.0,
        # 科目余额表叶子合计（与上一项并列，供溯源面板显示两个口径的差异）
        "prepaid_tb_leaf_amount": 0.0,
        # TB 核对科目来源（report_config BS-008 规则映射解析结果，供溯源展示）
        "tb_source_codes": {},
        # F1-4 跨循环锚点科目来源（存货 BS-010 / 应付账款 BS-045）
        "tb_cross_cycle_codes": {},
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, business_category, "
                "applicable_standard_v2 AS applicable_standards "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = proj_row.business_category or ""
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
            raw_standards = proj_row.applicable_standards
            # applicable_standard_v2 可能是 JSONB(dict) 或 string 或 None
            if isinstance(raw_standards, dict):
                project_context["applicable_standards"] = (
                    raw_standards.get("type")
                    or raw_standards.get("entity_type")
                    or ""
                )
            elif isinstance(raw_standards, str):
                project_context["applicable_standards"] = raw_standards
            else:
                project_context["applicable_standards"] = ""
    except Exception as e:  # noqa: BLE001
        logger.warning("F1 render: project context 查询失败: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass

    # 关联方清单：从关联方登记表取项目级名单，供 F1-2 关联方识别 / F1-6 完整性校验
    try:
        rp_rows = (
            await db.execute(
                sa.text(
                    "SELECT name FROM related_party_registry "
                    "WHERE project_id = :pid AND is_deleted = false "
                    "AND name IS NOT NULL AND name <> ''"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchall()
        project_context["related_parties"] = [r.name for r in rp_rows if r.name]
    except Exception as e:  # noqa: BLE001
        logger.warning("F1 render: related_parties 查询失败: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass

    # ── 四表库取数（报表映射规则驱动 + 共享叶子聚合，全程 fail-open）─────────────
    accounts = await _resolve_f1_accounts(ctx)
    # 取数溯源（前端 F1FourTableSourcePanel 消费；旧版是 list[str] 且前端 0 消费）
    source_codes = accounts.as_dict()

    # 备抵第二取数口径：标准码直查 trial_balance（`account_mapping` 常缺 `1231-04`，
    # 反解必退化为宽前缀 `1231` → tb_balance 路径恒空；标准码路径可精确命中）。
    provision_trial_amount = await _fetch_provision_from_trial_balance(
        ctx, list(accounts.provision_standard)
    )
    source_codes["provision_trial_amount"] = provision_trial_amount
    project_context["tb_source_codes"] = source_codes

    # F1-4 跨循环锚点同样走报表映射（存货 BS-010 区间 / 应付账款 BS-045）
    inventory_specs = await _resolve_line_codes(
        ctx, _F1_INVENTORY_ROW_CODE, _F1_INVENTORY_FALLBACK
    )
    payable_specs = await _resolve_line_codes(
        ctx, _F1_PAYABLE_ROW_CODE, _F1_PAYABLE_FALLBACK
    )
    project_context["tb_cross_cycle_codes"] = {
        "inventory": {"row_code": _F1_INVENTORY_ROW_CODE, "codes": inventory_specs},
        "payable": {"row_code": _F1_PAYABLE_ROW_CODE, "codes": payable_specs},
    }

    leaves = await _fetch_f1_leaf_rows(
        ctx,
        list(accounts.gross)
        + list(accounts.provision)
        + sql_prefixes_for_specs(inventory_specs)
        + sql_prefixes_for_specs(payable_specs),
    )

    # 存货：区间内叶子直接求和 —— 借正贷负下跌价准备(1416)本就是负数，已自然抵减，
    # 故**不**照抄 listed_standalone 公式里的 `- TB('1416')`（会二次扣减）。
    inventory_leaves = filter_by_code_specs(leaves, inventory_specs)
    project_context["inventory_balance_current"] = round(
        sum(r.closing for r in inventory_leaves), 2
    )
    # 应付账款为负债贷方，tb_balance 借正贷负 → 取绝对值供 F1-4 正数展示
    payable_leaves = filter_by_code_specs(leaves, payable_specs)
    project_context["payable_balance_current"] = round(
        abs(sum(r.closing for r in payable_leaves)), 2
    )

    # F1-1 试算平衡表数：优先 trial_balance 审定/未审（标准码口径），回退 tb_balance 叶子期末。
    # 前端 allResponses 来自 checklist-responses 端点（非本 responses_snapshot），故同时：
    #  ① 注入 responses_snapshot（供确有消费该键的路径使用）
    #  ② 放入 project_context.prepaid_tb_amount 供 F1-1 组件作只读回退 seed（不覆盖手工录入）
    # 🔴 双口径并列下发（审计追溯）：trial_balance 是**重算产物**，可能与科目余额表叶子
    #   合计不等（实证项目 `2aa00f57`：trial_balance 2,603,836.86 = 科目余额表叶子合计
    #   1,301,918.43 的 2 倍 —— recalc 把 `dataset_id IS NULL` 的历史行一并计入）。
    #   两个数都给出来，由 F1FourTableSourcePanel 显示差异，别让审计师只看到一个数。
    leaf_total = aggregate_leaves(leaves, accounts.gross)["closing"]
    project_context["prepaid_tb_leaf_amount"] = round(leaf_total, 2)

    seed_tb = await _fetch_f1_1123_audited(ctx, list(accounts.gross_standard))
    if seed_tb is None:
        seed_tb = leaf_total
    if seed_tb is not None and abs(seed_tb) > 1e-9:
        project_context["prepaid_tb_amount"] = round(seed_tb, 2)
        if "F1-adj-trial-balance-amount" not in responses_snapshot:
            responses_snapshot["F1-adj-trial-balance-amount"] = {
                "conclusion": "",
                "remark": str(round(seed_tb, 2)),
            }

    raw_std = project_context["applicable_standards"]
    standards = raw_std.lower() if isinstance(raw_std, str) else ""
    disclosure_visibility = {
        "listed": "listed" in standards,
        "soe": "soe" in standards,
    }

    result: dict = {
        "sections": sections,
        "adjudication_config": adjudication_config,
        "project_context": project_context,
        "disclosure_visibility": disclosure_visibility,
        "responses_snapshot": responses_snapshot,
        "account_code": "1123",
    }

    # F1-1「按性质分类」未审数四表预填（前端优先级：手工 > F1-2 明细聚合 > 四表库）。
    # 无叶子数据时**整键省略**（宁缺勿造：不写 0 占位，不清空既有值）。
    nature_prefill = build_nature_prefill(leaves, accounts.gross)
    if nature_prefill:
        result["adjudication_prefill"] = {"nature": nature_prefill}

    # 减值准备（坏账准备-预付账款）预填：备抵侧反解退化为宽前缀时**必须**叠名称过滤，
    # 否则会把应收票据/应收账款/其他应收款的坏账（1231.01/.02/.03）算进 F1。
    impairment_prefill = resolve_impairment_prefill(
        build_impairment_prefill(
            leaves,
            accounts.provision,
            name_filter=(
                None
                if accounts.provision_exact
                else F1_REPORT_LINE_SPEC.provision_name_filter
            ),
        ),
        provision_trial_amount,
    )
    if impairment_prefill is not None:
        result["impairment_prefill"] = impairment_prefill

    return result
