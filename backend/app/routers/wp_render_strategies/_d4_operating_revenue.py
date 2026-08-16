"""D4 营业收入 — 专属渲染策略.

component_type = "d4-operating-revenue"
返回 html_data 含：sections结构 / visible_groups（基于business_category）/ sheet配置。
数据持久化在 checklist_responses 表，item_id前缀为 "D4-{sheetCode}-{field}"。

──────────────────────────────────────────────────────────────────────────
2026-08 推翻既有「宁缺勿造」判定
──────────────────────────────────────────────────────────────────────────
原注释结论「无干净 TB→审定表明细行映射」依据「产品/项目维度只在序时账、非科目结构」。
**推翻依据**（9 项目只读实证 + 源模板 openpyxl 逐格读取）：
  1) 6001 在 9 个在册项目中**存在业务板块级子科目**（批发/零售/物流/物业与
     租赁/医疗/服务费及其他），子科目后缀天然对应 D4-1 审定表分部行。
  2) D4-1 源模板 R8:R11 / R14:R17 是**主营/其他各 4 行空白可扩行**（非固定行集）。
  3) 叶子科目 `account_name` 直接作分部行标签（同 F1 `1123` / G7 `1511` 范式）。
→ 故可按 tb_balance 叶子子科目名建动态行并预填未审数。
──────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.core.config import settings
from app.services.d_cycle_extraction.d_tb_fetch import (
    build_parent_check_for_specs,
)
from app.services.d4_extraction.account_scope import (
    D4AccountScope,
    D4_ROOT_PAIRS,
    SegmentPair,
    build_d4_source_codes,
    code_in_specs,
    fetch_d4_leaf_rows,
    pair_revenue_cost_leaves,
    resolve_d4_accounts,
    rollup_asymmetric_pairs,
    split_leaf_head_suffix,
    strip_segment_name_prefix,
)
from app.services.d_cycle_extraction.presets import resolve_effective
from app.services.d_cycle_extraction.tier_a_seed import (
    seed_tier_a_reconciliation,
)
from app.services.four_table import LeafRow
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

from ._context import RenderContext

logger = logging.getLogger(__name__)

# D4 wp_code base（Tier A 提取公式 / 锚点登记 key）
_D4_WP_CODE = "D4"

#: 主营业务收入标准码前缀（审定表分段用）—— `D4_ROOT_PAIRS[0][0]`
D4_MAIN_REVENUE_STANDARD = "6001"
#: 其他业务收入标准码前缀
D4_OTHER_REVENUE_STANDARD = "6051"


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（无 DB 依赖，可独立单测）
# ─────────────────────────────────────────────────────────────────────────────


def build_d4_tb_values(
    leaves: list[LeafRow],
    scope: D4AccountScope,
) -> dict[str, float | None]:
    """为 D4-1 审定表生成 TB 核对行数据（IS-001 口径发生额）。纯函数。

    TB 核对行逻辑：
    - 「试算平衡表数」= 收入叶子 credit 发生额汇总（IS-001 单侧口径）
    - 「差异数」由前端 = 审定合计 − 试算平衡表数（本函数不计算审定合计）

    Args:
        leaves: 收入侧叶子行（已 select_leaves，应属 IS-001 区间）。
        scope: 已解析的 D4 科目定位结果。

    Returns:
        ``{"tb_revenue_total": float|None}``；无叶子时返回 ``{"tb_revenue_total": None}``
        （不返空 dict，以区分「取数结果 0」与「无数据」）。

    **Validates: Requirements 3.7**
    """
    if not leaves:
        return {"tb_revenue_total": None}

    # 只汇总属于收入规格集的叶子（scope 可能已语义收敛，但叶子是按宽区间取的
    # → 用 code_in_specs 二次过滤保守处理，避免把其它循环科目算入）
    rev_specs = scope.revenue_standard_expanded or scope.revenue_standard
    total = 0.0
    count = 0
    for leaf in leaves:
        if code_in_specs(leaf.account_code, rev_specs):
            total += leaf.credit
            count += 1
    if count == 0:
        return {"tb_revenue_total": None}
    return {"tb_revenue_total": round(total, 2)}


def build_d4_adjudication_prefill(
    leaves: list[LeafRow],
    scope: D4AccountScope,
    *,
    existing_rows: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """为 D4-1 审定表生成动态预填行（按标准码分主营/其他段）。纯函数。

    设计判断（推翻既有「宁缺勿造」）：
    - 9 个在册项目的 ``6001`` 存在业务板块级子科目（批发/零售/物流/物业与租赁/
      医疗/服务费及其他），源模板 D4-1 主营/其他两段各 4 行空白可扩行。
    - 叶子科目 ``account_name`` 直接作行标签（同 F1/G7 铁律：编码语义在项目间
      冲突，禁按编码归类）。

    分段规则（按标准码归属，Req 3.3）：
    - ``6001`` 子树 → 主营业务收入段
    - ``6051`` 子树 → 其他业务收入段
    - 两者之外（如 ``6002``）→ 归入主营段（保守，不丢弃）

    手工优先（Req 3.4）：
    - ``existing_rows`` 中已有值的账户码不覆盖（手工永不被自动值替换）。

    宁缺勿造（Req 3.6）：
    - 无任何可映射叶子时返回空列表。

    Args:
        leaves: 收入侧叶子行（已 select_leaves）。
        scope: 已解析的 D4 科目定位结果。
        existing_rows: 已持久化的行数据 ``{account_code: {...}}``，有值的行不覆盖。

    Returns:
        动态行列表 ``[{account_code, account_name, section, unadjusted, ...}]``；
        按 ``(section 顺序, account_code)`` 稳定排序。空叶子返回 ``[]``。

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6**
    """
    if not leaves:
        return []

    existing = existing_rows or {}

    # 收入侧标准码根（用于分段判定）
    rev_roots = [rp[0] for rp in D4_ROOT_PAIRS]  # ["6001", "6051"]
    # 只保留属于收入规格集的叶子
    rev_specs = scope.revenue_standard_expanded or scope.revenue_standard

    rows: list[dict[str, Any]] = []
    for leaf in leaves:
        if not code_in_specs(leaf.account_code, rev_specs):
            continue

        # 分段判定：按标准码前缀归属主营/其他
        hit = split_leaf_head_suffix(leaf.account_code, rev_roots)
        if hit is not None:
            root, _suffix = hit
            if root == D4_OTHER_REVENUE_STANDARD:
                section = "其他业务收入"
            else:
                section = "主营业务收入"
        else:
            # 不属任何已知根（如客户挂 6002）→ 保守归入主营段
            section = "主营业务收入"

        # 行标签：取 account_name（剥前缀），禁按编码语义归类
        label = strip_segment_name_prefix(leaf.account_name) or leaf.account_name or leaf.account_code

        # 手工优先：已有值的行不覆盖（Req 3.4）
        if leaf.account_code in existing:
            continue

        rows.append({
            "account_code": leaf.account_code,
            "account_name": label,
            "section": section,
            "unadjusted": round(leaf.credit, 2),  # 收入取贷方发生额（单侧口径）
        })

    # 按 (section 顺序, account_code) 稳定排序
    section_order = {"主营业务收入": 0, "其他业务收入": 1}
    rows.sort(key=lambda r: (section_order.get(r["section"], 99), r["account_code"]))
    return rows


def build_d4_segment_prefill(
    revenue_leaves: list[LeafRow],
    cost_leaves: list[LeafRow],
    scope: D4AccountScope,
) -> list[dict[str, Any]]:
    """为附注（2）「营业收入、营业成本按行业（或产品类型）划分」生成镜像配对行。纯函数。

    编排逻辑：
    1. `pair_revenue_cost_leaves` —— 按后缀镜像配对收入/成本叶子（Property 7/8）
    2. `rollup_asymmetric_pairs` —— 归并层级不对称行（父收入+子成本 → 一行）
    3. 转换为 render 输出格式

    每个输出 dict 对应一个披露分部行（行业 / 产品类型），含：
    - ``label``: 分部名称（取自 account_name，已剥前缀）
    - ``section``: 主营业务 / 其他业务（取自 D4_ROOT_PAIRS 第三元素）
    - ``current_revenue``: 本期收入发生额（或 None）
    - ``current_cost``: 本期成本发生额（或 None）
    - ``name_mismatch``: 名称差异告警（后缀配对成立但名称不等，如 医疗收入/医疗支出）
    - ``cost_missing``: 该分部只有收入侧、无成本子科目
    - ``revenue_missing``: 该分部只有成本侧、无收入子科目

    宁缺勿造（Property 10）：
    - 两侧叶子均为空时返回空列表。

    Args:
        revenue_leaves: 收入侧叶子行（已 select_leaves，属 IS-001 区间）。
        cost_leaves: 成本侧叶子行（已 select_leaves，属 IS-002 区间）。
        scope: 已解析的 D4 科目定位结果（提供 root_pairs 与规格集信息）。

    Returns:
        分部行列表；按 ``(section 顺序, suffix)`` 稳定排序。
        两侧均无叶子时返回 ``[]``。

    **Validates: Requirements 4.2**
    """
    if not revenue_leaves and not cost_leaves:
        return []

    # Step 1: 后缀镜像配对（Property 7: 不重不漏；Property 8: 名称不等不解除配对）
    pairs: list[SegmentPair] = pair_revenue_cost_leaves(
        revenue_leaves, cost_leaves
    )

    # Step 2: 层级不对称归并（父收入+子成本 → 合并为一行）
    pairs = rollup_asymmetric_pairs(pairs)

    # Step 3: 转换为 render 输出格式
    result: list[dict[str, Any]] = []
    for p in pairs:
        result.append({
            "label": p.label,
            "section": p.section,
            "current_revenue": round(p.revenue_amount, 2) if p.revenue_amount is not None else None,
            "current_cost": round(p.cost_amount, 2) if p.cost_amount is not None else None,
            "name_mismatch": p.name_mismatch,
            "cost_missing": p.cost_missing,
            "revenue_missing": p.revenue_missing,
        })

    return result


# IPO/舞弊组可见性关键字
_IPO_KEYWORDS = ("ipo", "listed", "neeq", "restructuring", "fraud_risk")


def _is_ipo_visible(business_category: str) -> bool:
    """判断IPO/舞弊组一级Tab是否可见"""
    if not business_category:
        return False
    bc_lower = business_category.lower()
    return any(kw in bc_lower for kw in _IPO_KEYWORDS)


async def render(ctx: RenderContext) -> dict | None:
    """D4 营业收入渲染策略.

    返回完整 html_data：
    - sections: 7组嵌套Tab结构配置
    - visible_groups: 各组可见性标记
    - project_context: 项目上下文
    - responses_snapshot: 关键item_id的已保存数据
    """
    wp_id = ctx.wp_id
    db = ctx.db
    business_category = ctx.business_category or ""

    # ─── 可见性判断 ────────────────────────────────────────────────────────
    ipo_visible = _is_ipo_visible(business_category)

    visible_groups = {
        "core": True,
        "policy": True,
        "analysis": True,
        "inspection": True,
        "related": True,
        "ipo": ipo_visible,
        "other": True,
    }

    # ─── sections 结构定义 ─────────────────────────────────────────────────
    sections = [
        {
            "key": "core",
            "label": "核心",
            "sheets": [
                {"code": "D4-INDEX", "label": "底稿目录"},
                {"code": "D4-1", "label": "审定表"},
                {"code": "D4-2", "label": "主营明细"},
                {"code": "D4-3", "label": "其他明细"},
                {"code": "D4-4", "label": "调整分录"},
                {"code": "D4-NOTE-LISTED", "label": "附注(上市)"},
                {"code": "D4-NOTE-SOE", "label": "附注(国企)"},
            ],
        },
        {
            "key": "policy",
            "label": "政策",
            "sheets": [
                {"code": "D4-5", "label": "会计政策检查"},
            ],
        },
        {
            "key": "analysis",
            "label": "分析程序",
            "sheets": [
                {"code": "D4-6", "label": "重要指标"},
                {"code": "D4-7", "label": "毛利率月度"},
                {"code": "D4-8", "label": "产品毛利"},
                {"code": "D4-9", "label": "客户结构"},
                {"code": "D4-10", "label": "客户价格"},
                {"code": "D4-11", "label": "产品价格"},
            ],
        },
        {
            "key": "inspection",
            "label": "检查程序",
            "sheets": [
                {"code": "D4-12", "label": "合同检查"},
                {"code": "D4-13", "label": "ERP核对"},
                {"code": "D4-14", "label": "发生检查"},
                {"code": "D4-15", "label": "完整性检查"},
                {"code": "D4-16", "label": "出口核对"},
                {"code": "D4-17", "label": "截止(正向)"},
                {"code": "D4-18", "label": "截止(反向)"},
                {"code": "D4-19", "label": "折扣折让"},
                {"code": "D4-20", "label": "退货检查"},
            ],
        },
        {
            "key": "related",
            "label": "关联方",
            "sheets": [
                {"code": "D4-21", "label": "关联价格分析"},
            ],
        },
        {
            "key": "ipo",
            "label": "IPO/舞弊",
            "sheets": [
                {"code": "D4-22A", "label": "IPO程序表"},
                {"code": "D4-22", "label": "IPO指标"},
                {"code": "D4-23", "label": "发票对比"},
                {"code": "D4-24", "label": "第三方回款"},
                {"code": "D4-25", "label": "经销商"},
                {"code": "D4-26", "label": "境外销售"},
                {"code": "D4-27", "label": "未披露关联方"},
                {"code": "D4-28", "label": "核查清单"},
                {"code": "D4-29", "label": "核查详细"},
                {"code": "D4-30", "label": "访谈汇总"},
                {"code": "D4-31", "label": "访谈详细"},
                {"code": "D4-32", "label": "资金流水"},
            ],
        },
        {
            "key": "other",
            "label": "其他收入",
            "sheets": [
                {"code": "D4-33", "label": "其他毛利"},
                {"code": "D4-34", "label": "合同测算"},
                {"code": "D4-35", "label": "其他检查"},
                {"code": "D4-36", "label": "其他截止"},
            ],
        },
    ]

    # ─── 从 checklist_responses 加载关键数据快照 ──────────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'D4-%' "
                "LIMIT 500"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("D4 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": business_category,
        "applicable_standards": "",
        "has_export_business": False,
    }

    try:
        proj_result = await db.execute(
            sa.text(
                "SELECT client_name, audit_year, business_category "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = proj_row.business_category or business_category
    except Exception as e:  # noqa: BLE001
        logger.warning("D4 render: project context 查询失败: %s", e)

    html_data = {
        "sections": sections,
        "visible_groups": visible_groups,
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
    }

    # ─── 四表取数：D4 动态科目定位 + 预填 + 溯源（灰度开关控制）─────────────────
    # spec: d4-four-table-extraction-and-disclosure-alignment
    # Requirements: 2.6（tb_source_codes）、3.1（推翻「宁缺勿造」判定）
    #
    # 【推翻既有「宁缺勿造」判定 —— 2026-08 实证】
    # 原结论「无干净 TB→审定表明细行映射（收入按产品/项目 SUMIF from D4-2/D4-3）」
    # 基于「产品/项目维度只在序时账、非科目结构」的判断。
    # **推翻依据**（只读实证，非推断）：
    #   1) 6001 在 9 个在册项目中**存在业务板块级子科目**（批发/零售/物流/物业与
    #      租赁/医疗/服务费及其他），子科目后缀天然对应 D4-1 审定表分部行。
    #   2) D4-1 源模板 R8:R11 / R14:R17 是**主营/其他各 4 行空白可扩行**（非固定行集）。
    #   3) 叶子科目 `account_name` 直接作分部行标签（同 F1 `1123` / G7 `1511` 范式）。
    # → 故 D4 现在输出 `tb_values` / `adjudication_prefill` / `segment_prefill` /
    #   `tb_source_codes`，与 K1/K2/F1/G7 同范式。
    if settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        try:
            # Step 1: 解析 D4 科目定位（报表行驱动 → 区间展开 → 逐项目反解）
            scope = await resolve_d4_accounts(ctx)

            # Step 2: 按收入/成本规格集取叶子行
            rev_specs = scope.revenue_standard_expanded or scope.revenue_standard
            cost_specs = scope.cost_standard_expanded or scope.cost_standard
            revenue_leaves = await fetch_d4_leaf_rows(ctx, rev_specs)
            cost_leaves = await fetch_d4_leaf_rows(ctx, cost_specs)

            # Step 3: 纯函数构建各输出
            html_data["tb_values"] = build_d4_tb_values(revenue_leaves, scope)
            html_data["adjudication_prefill"] = build_d4_adjudication_prefill(
                revenue_leaves, scope
            )
            segment_prefill = build_d4_segment_prefill(
                revenue_leaves, cost_leaves, scope
            )

            # Step 3.5: 上期数据二次取数 → 合并 prior_revenue / prior_cost
            # 用 ctx.year - 1 取上年叶子行，按 label 匹配合并到 segment_prefill 每行
            prior_year = (ctx.year or 0) - 1
            if prior_year > 0 and segment_prefill:
                try:
                    from dataclasses import replace as _dc_replace
                    from copy import copy as _copy

                    # 构造上期 context（替换 year 字段）
                    ctx_prior = _dc_replace(ctx, year=prior_year)
                    prior_rev_leaves = await fetch_d4_leaf_rows(ctx_prior, rev_specs)
                    prior_cost_leaves = await fetch_d4_leaf_rows(ctx_prior, cost_specs)

                    if prior_rev_leaves or prior_cost_leaves:
                        # 用同一配对逻辑构建上期 segment
                        prior_segments = build_d4_segment_prefill(
                            prior_rev_leaves, prior_cost_leaves, scope
                        )
                        # 按 label + section 匹配合并
                        prior_map: dict[tuple[str, str], dict] = {
                            (row["label"], row["section"]): row
                            for row in prior_segments
                        }
                        for row in segment_prefill:
                            key = (row["label"], row["section"])
                            prior_row = prior_map.get(key)
                            if prior_row:
                                row["prior_revenue"] = prior_row.get("current_revenue")
                                row["prior_cost"] = prior_row.get("current_cost")
                            else:
                                row["prior_revenue"] = None
                                row["prior_cost"] = None
                except Exception as e:  # noqa: BLE001
                    logger.warning("D4 render: 上期 segment 取数异常（fail-open）: %s", e)
                    # 上期取数失败时给每行填 None（不阻塞当期数据）
                    for row in segment_prefill:
                        row.setdefault("prior_revenue", None)
                        row.setdefault("prior_cost", None)

            html_data["segment_prefill"] = segment_prefill

            # tb_source_codes → project_context（踩坑铁律：在 html_data.project_context 里，
            # 以便每个 sheet 都能访问；非 html_data 顶层）
            project_context["tb_source_codes"] = build_d4_source_codes(scope)

            # ─── 三口径自检（新增，纯加法）─────────────────────────────────
            # spec: d-cycle-four-table-extraction-and-disclosure-completion R1.6
            # 损益类走 occurrence 口径（发生额）。
            # 🔴 不能直接把 `revenue_leaves` 喂给 `build_parent_check` —— 那已是
            # **筛过的叶子**，父行不在集合里会让 `parent` 侧恒 0；故经
            # `build_parent_check_for_specs` 按规格集重新宽取一次含父行的子树。
            project_context["parent_check"] = await build_parent_check_for_specs(
                ctx,
                {"revenue": list(rev_specs), "cost": list(cost_specs)},
                {
                    "revenue": list(scope.revenue_standard or []),
                    "cost": list(scope.cost_standard or []),
                },
                occurrence=True,
            )

        except Exception as e:  # noqa: BLE001 — fail-open：单点失败不让整张底稿打不开
            logger.warning(
                "D4 render: 四表取数异常（fail-open），其余部分正常 wp_id=%s: %s",
                wp_id, e,
            )

        # ─── Tier A 公式驱动 TB 核对行 transient seed（D4 双标量）────────────────
        try:
            await seed_tier_a_reconciliation(
                ctx,
                _D4_WP_CODE,
                responses_snapshot,
                resolve_effective=resolve_effective,
                evaluate_wp_formula_expression=evaluate_wp_formula_expression,
            )
        except Exception as e:  # noqa: BLE001 — 兜底 fail-open，不阻断 render
            logger.warning("D4 render: Tier A seed 兜底异常（fail-open）: %s", e)

    return html_data
