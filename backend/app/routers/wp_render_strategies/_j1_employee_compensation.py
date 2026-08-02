"""J1 应付职工薪酬 — 专属渲染策略.

科目：**2211 应付职工薪酬**（贷方/负债类），由报表映射规则动态解析：
listed `BS-051` / soe `BS-069`，两变体公式实证均为 ``TB('2211','期末余额')``。
公式：期末=期初+贷方-借方
核心：薪酬测算(人数×均薪×月数) + 社保(基数×比例×月数) + 分配闭合 + K8/K9联动

🔴 **改造前三处取数缺陷**（本次修）：

1. **「最深可用层级」口径**：``by_level`` 只建 1~3 级 → 活体存在的**四级**科目
   （``2211.01.01.01 工资_标准薪酬``）被 ``if lvl in by_level`` 直接丢弃；且
   ``by_level[3] or by_level[2]`` 使「没有三级子科目的二级段」（``2211.05 劳动保护费`` /
   ``2211.06 商业保险``）**整段丢失**。→ 改叶子口径（无子科目即叶子，不假设深度）。
2. **逐行 `abs()`**：破坏「叶子和 == 父额」勾稽（J2 已实证同款，差 4.6 倍）。
   → 改整族统一取向。
3. **硬编码 `ACCOUNT_CODE`**：不走报表映射，且无 ``tb_source_codes`` 溯源输出。

**各项目科目表差异极大**（`account_mapping` 实测：``2211`` 原始码 27 / 33 / 51 个不等；
医疗器械项目无 ``2211.01.02 带薪缺勤`` / ``2211.03 劳务派遣`` / ``2211.05``，
宜宾与陕西华氏有 ``2211.03.01~.09`` 九个劳务派遣子科目）→ 预填行**只能由项目自己的
叶子科目动态产生**，归类按科目**名称**（编码语义在项目间会冲突）。

Spec: .kiro/specs/j-cycle-four-table-extraction-and-disclosure-alignment/
Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1
"""
from __future__ import annotations
import json
import logging
import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.j_cycle_account_scope import (
    CAT_POST_EMPLOYMENT,
    CAT_SEVERANCE,
    CAT_SHORT_TERM,
    J1_SPEC_BY_ENTITY,
    classify_j1_dc_row,
    classify_j1_leaf,
    classify_j1_short_term_row,
    pick_spec,
    select_scope_leaves,
)
from app.services.four_table.leaf_aggregation import (
    LeafRow,
    parent_totals,
    to_leaf_rows,
)
from app.services.four_table.report_line_accounts import (
    ReportLineAccounts,
    fetch_applicable_standards,
    resolve_report_line_accounts,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 审定表分类（对齐前端 useJ1Adjudication 的 category 枚举；真源在 j_cycle_account_scope）
_CAT_SHORT_TERM = CAT_SHORT_TERM
_CAT_POST_EMPLOYMENT = CAT_POST_EMPLOYMENT
_CAT_SEVERANCE = CAT_SEVERANCE


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（可独立单测，无 DB）
# ─────────────────────────────────────────────────────────────────────────────


def leaf_label(account_name: str, account_code: str) -> str:
    """科目名 → 展示标签（取最末一级，如 ``应付职工薪酬_短期薪酬_工资`` → ``工资``）。"""
    name = (account_name or "").strip()
    return name.split("_")[-1] if name else (account_code or "").strip()


def liability_orientation(all_rows: list[LeafRow], prefixes) -> int:
    """让负债显正所需的整族取向系数（``+1`` / ``-1``）。见 J2 同名函数的实证说明。

    🔴 **不逐行 `abs()`** —— 客户会把借方性质的支出（已支付福利 / 过去服务成本）
    编在同一科目族下并以正号存储，逐行取绝对值会让行级和与父额差数倍。
    """
    for prefix in prefixes or []:
        parent = parent_totals(all_rows, prefix)
        if abs(parent["closing"]) >= 0.005:
            return -1 if parent["closing"] < 0 else 1
        if abs(parent["opening"]) >= 0.005:
            return -1 if parent["opening"] < 0 else 1
    signed = sum(r.closing for r in select_scope_leaves(all_rows, prefixes))
    return -1 if signed < 0 else 1


def build_j1_tb_values(leaves: list[LeafRow]) -> dict:
    """聚合范围内叶子（负债口径取绝对值，只作用于**聚合结果**）。"""
    agg = {
        "opening": sum(r.opening for r in leaves),
        "closing": sum(r.closing for r in leaves),
        "debit": sum(r.debit for r in leaves),
        "credit": sum(r.credit for r in leaves),
    }
    return {k: abs(v) for k, v in agg.items()}


def build_j1_adjudication_prefill(leaves: list[LeafRow], sign: int = 1) -> list[dict]:
    """`2211` **叶子**科目 → J1-1 审定表预填行。

    键名沿用改造前形态（``id`` / ``label`` / ``category`` / ``begin_unadj`` /
    ``begin_aje`` / ``end_unadj`` / ``end_aje`` / ``analysis``），
    前端 `useJ1Adjudication.initFromHtmlData` 零改动即可消费。

    - **叶子口径**，不假设层级深度（四级科目不丢、无三级子科目的二级段不丢）
    - **整族统一取向**（`sign`），不逐行 `abs()`
    - 期初/期末全为 0 的叶子跳过（宁缺勿造）
    - 新增 ``account_code`` / ``short_term_row_key`` / ``dc_row_key``：
      供前端「刷新取数」**按科目码优先于行名**匹配、以及披露表按行落位
    """
    out: list[dict] = []
    for r in leaves:
        opening = sign * r.opening
        closing = sign * r.closing
        increase = r.credit
        decrease = r.debit
        # 🔴 非空判定含发生额：全年计提又缴清的科目（社保/公积金）期末为 0 但必须建行，
        # 否则审定表拿不到本期增减、披露变动表两列全空。
        if all(abs(v) < 0.005 for v in (opening, closing, increase, decrease)):
            continue
        category = classify_j1_leaf(r.account_code, r.account_name)
        st_rule = classify_j1_short_term_row(r.account_code, r.account_name)
        dc_rule = classify_j1_dc_row(r.account_code, r.account_name)
        out.append(
            {
                "id": f"tb-{r.account_code}",
                "label": leaf_label(r.account_name, r.account_code),
                "category": category,
                "begin_unadj": opening,
                "begin_aje": 0,
                "end_unadj": closing,
                "end_aje": 0,
                "analysis": "",
                "account_code": r.account_code,
                "account_name": r.account_name,
                # 负债贷方：credit=本期增加（计提）、debit=本期减少（发放/缴纳）；
                # 发生额以正数存储，不受 sign 影响
                "increase": round(increase, 2),
                "decrease": round(decrease, 2),
                "change": round(closing - opening, 2),
                "short_term_row_key": st_rule.key if category == _CAT_SHORT_TERM else None,
                "short_term_row_label": (
                    st_rule.label if category == _CAT_SHORT_TERM else None
                ),
                "dc_row_key": dc_rule.key if category == _CAT_POST_EMPLOYMENT else None,
                "dc_row_label": dc_rule.label if category == _CAT_POST_EMPLOYMENT else None,
            }
        )
    return out


def build_j1_detail_prefill(leaves: list[LeafRow], sign: int = 1) -> dict[str, dict]:
    """`2211` 叶子 → 披露/明细**变动行**预填。

    返回 ``{row_key: {label, category, begin, increase, decrease, end, codes, dynamic}}``。

    🔴 **非空判定必须含发生额，不能只看余额**：J1 披露表是变动表（期初余额/本期增加/
    本期减少/期末余额），而职工薪酬的社保、公积金、工会经费等科目**全年计提又全额缴清，
    期末余额为 0 但发生额巨大**。实测医疗器械项目 `2211` 全年
    ``debit=27,438,067.67`` / ``credit=30,144,558.21``，若只按余额判非空则披露表的
    「本期增加/本期减少」两列几乎全空 —— 正是「四表入库后底稿应当有数」的核心诉求落空。

    **负债贷方口径**：``credit_amount`` = 本期增加（计提）、``debit_amount`` = 本期减少
    （发放/缴纳）。发生额本身以正数存储，**不受 `sign` 影响**（实测逐分验证：
    期初 1,769,529.91 + 贷 30,144,558.21 − 借 27,438,067.67 = 期末 4,476,020.45 ✅）。

    行集由**项目实际叶子**决定（不预置源模板全部行）：某项目没有生育保险科目，
    就不产生「3．生育保险费」行 —— 附注推送出去的表即该项目的真实构成。

    「社会保险费」父行不在此产生 —— 它是 SUM 派生行（源模板 R20 为 SUM 公式），
    由前端按 ``J1_SOCIAL_CHILD_KEYS`` 求和。
    """
    out: dict[str, dict] = {}
    for r in leaves:
        opening = sign * r.opening
        closing = sign * r.closing
        increase = r.credit
        decrease = r.debit
        if all(
            abs(v) < 0.005 for v in (opening, closing, increase, decrease)
        ):
            continue
        category = classify_j1_leaf(r.account_code, r.account_name)
        if category == _CAT_SHORT_TERM:
            rule = classify_j1_short_term_row(r.account_code, r.account_name)
        elif category == _CAT_POST_EMPLOYMENT:
            rule = classify_j1_dc_row(r.account_code, r.account_name)
        else:
            # 辞退福利在主表单列一行，无明细表落点
            continue
        slot = out.setdefault(
            rule.key,
            {
                "label": rule.label,
                "category": category,
                "begin": 0.0,
                "increase": 0.0,
                "decrease": 0.0,
                "end": 0.0,
                "codes": [],
                # `……` 可扩位：label 取实际叶子科目名更诚实（源模板该位本就无固定名）
                "dynamic": rule.label == "……",
            },
        )
        slot["begin"] += opening
        slot["increase"] += increase
        slot["decrease"] += decrease
        slot["end"] += closing
        if r.account_code not in slot["codes"]:
            slot["codes"].append(r.account_code)
        if slot["dynamic"] and slot["label"] == "……":
            slot["label"] = leaf_label(r.account_name, r.account_code)
    for slot in out.values():
        for k in ("begin", "increase", "decrease", "end"):
            slot[k] = round(slot[k], 2)
        # roll-forward 自检：期末应 = 期初 + 增加 − 减少（客户账不平时如实暴露）
        slot["rollforward_diff"] = round(
            slot["begin"] + slot["increase"] - slot["decrease"] - slot["end"], 2
        )
    return out


def build_j1_source_codes(
    accounts: ReportLineAccounts, all_rows: list[LeafRow], leaves: list[LeafRow]
) -> dict:
    """取数溯源载荷（前端 `J1FourTableSourcePanel` 消费，非 dead output）。"""
    payload = accounts.as_dict()
    leaf_agg = build_j1_tb_values(leaves)
    parent_codes = {r.account_code for r in all_rows}
    parent_check: dict[str, dict] = {}
    for prefix in accounts.gross:
        parent = parent_totals(all_rows, prefix)
        # 🔴 父科目行可能压根不存在（实测辽宁卫生的 tb_balance 无 `2211` 汇总行，
        # 只有明细行）→ 此时 diff 无意义，必须用 present 标志区分「无父行」与「真差异」，
        # 否则溯源面板会常亮一条 -1,063,715.35 的假告警。
        present = prefix in parent_codes
        parent_check[prefix] = {
            "parent_present": present,
            "parent_closing": abs(parent["closing"]) if present else None,
            "leaf_closing": leaf_agg["closing"],
            "diff": (
                round(abs(parent["closing"]) - leaf_agg["closing"], 2) if present else None
            ),
        }
    payload["parent_check"] = parent_check
    payload["leaf_count"] = len(leaves)
    payload["leaf_codes"] = sorted({r.account_code for r in leaves})
    payload["liability_sign"] = liability_orientation(all_rows, accounts.gross)
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# DB 访问（全程 fail-open）
# ─────────────────────────────────────────────────────────────────────────────


async def _resolve_j1_accounts(ctx: RenderContext) -> ReportLineAccounts:
    """按变体解析 J1 报表行（listed `BS-051` / soe `BS-069`），兜底 `2211`。"""
    standards = await fetch_applicable_standards(ctx)
    spec = pick_spec(J1_SPEC_BY_ENTITY, standards)
    return await resolve_report_line_accounts(ctx, spec)


async def _load_j1_leaves(
    ctx: RenderContext, accounts: ReportLineAccounts
) -> tuple[list[LeafRow], list[LeafRow]]:
    """一次查询取 active 数据集全量行，返回 ``(全部行, 范围内叶子行)``。"""
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
            ).where(active_filter)
        )
        rows = to_leaf_rows(result.fetchall())
    except Exception as e:  # noqa: BLE001 — 取数失败按空处理，不阻塞渲染
        logger.warning("J1 tb_balance 查询失败: %s", e)
        return [], []
    return rows, select_scope_leaves(rows, accounts.gross)

J1_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "j1-employee-compensation"},
    {"sheet_name": "应付职工薪酬实质性程序表 J1A", "component_type": "j1-employee-compensation"},
    {"sheet_name": "审定表J1-1", "component_type": "j1-employee-compensation"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "j1-employee-compensation"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "j1-employee-compensation"},
    {"sheet_name": "明细表J1-2", "component_type": "j1-employee-compensation"},
    {"sheet_name": "调整分录汇总表J1-3", "component_type": "j1-employee-compensation"},
    {"sheet_name": "月度分析表J1-4", "component_type": "j1-employee-compensation"},
    {"sheet_name": "与同行业对比分析表J1-5", "component_type": "j1-employee-compensation"},
    {"sheet_name": "计提情况检查表J1-6", "component_type": "j1-employee-compensation"},
    {"sheet_name": "分配情况检查表J1-7", "component_type": "j1-employee-compensation"},
    {"sheet_name": "检查表J1-8", "component_type": "j1-employee-compensation"},
    {"sheet_name": "非货币性福利检查表J1-9", "component_type": "j1-employee-compensation"},
    {"sheet_name": "辞退福利检查表J1-10", "component_type": "j1-employee-compensation"},
]

#: 兜底展示用科目码（真实科目码一律取 `tb_source_codes.gross_standard`）
ACCOUNT_CODE = "2211"


async def render(ctx: RenderContext) -> dict | None:
    """渲染 J1 应付职工薪酬底稿数据.

    负债类贷方：科目走报表映射规则动态解析，从 trial_balance 读取余额，
    从 checklist_responses 读取薪酬明细、月度数据、检查表数据。
    """
    responses_snapshot: dict = {}
    tb_data: dict = {}

    # ─── 科目定位（报表映射规则驱动，不再硬编码） ─────────────────────────
    accounts = await _resolve_j1_accounts(ctx)

    # ─── 读取 trial_balance（按解析出的**标准码**） ───────────────────────
    try:
        tb_result = await ctx.db.execute(
            sa.text(
                "SELECT unadjusted_amount, aje_adjustment, audited_amount "
                "FROM trial_balance "
                "WHERE project_id = :pid AND year = :year "
                "AND standard_account_code = ANY(:codes) LIMIT 1"
            ),
            {
                "pid": str(ctx.project_id),
                "year": ctx.year,
                "codes": accounts.gross_standard or [ACCOUNT_CODE],
            },
        )
        tb_row = tb_result.fetchone()
        if tb_row:
            tb_data = {
                "unadjusted_amount": float(tb_row.unadjusted_amount or 0),
                "aje_adjustment": float(tb_row.aje_adjustment or 0),
                "audited_amount": float(tb_row.audited_amount or 0),
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("J1 render TB read failed: %s", e)

    # ─── 读取 checklist_responses ──────────────────────────────────────────
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 10000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "J1-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("J1 render checklist read failed: %s", e)

    # ─── 解析审定表数据 ───────────────────────────────────────────────────
    # J1-1-rows 是前端 useJ1Adjudication 的持久化键（新）；J1-adjudication-data 为历史键。
    adjudication_rows = _extract_json(responses_snapshot, "J1-1-rows", [])
    if not adjudication_rows:
        adjudication_rows = _extract_json(responses_snapshot, "J1-adjudication-data", [])

    # ─── 四表取数（叶子口径 + 整族取向，行由项目实际科目动态产生） ─────────
    all_rows, leaves = await _load_j1_leaves(ctx, accounts)
    sign = liability_orientation(all_rows, accounts.gross)
    tb_values = build_j1_tb_values(leaves)
    adjudication_prefill = build_j1_adjudication_prefill(leaves, sign)
    detail_prefill = build_j1_detail_prefill(leaves, sign)
    tb_source_codes = build_j1_source_codes(accounts, all_rows, leaves)

    # 无持久化审定数据 → 用四表预填（手工优先：有持久化就不覆盖）
    if not adjudication_rows:
        adjudication_rows = adjudication_prefill

    # ─── 解析明细表数据 ───────────────────────────────────────────────────
    detail_rows = _extract_json(responses_snapshot, "J1-detail-data", [])

    # ─── 解析月度分析 ─────────────────────────────────────────────────────
    monthly_rows = _extract_json(responses_snapshot, "J1-monthly-data", [])

    # ─── 解析行业对比 ─────────────────────────────────────────────────────
    industry_compare_rows = _extract_json(responses_snapshot, "J1-industry-data", [])
    company_info = _extract_json(responses_snapshot, "J1-company-info", {})

    # ─── 解析5类检查表 ────────────────────────────────────────────────────
    accrual_check_rows = _extract_json(responses_snapshot, "J1-accrual-check", [])
    allocation_check_rows = _extract_json(responses_snapshot, "J1-allocation-check", [])
    general_check_rows = _extract_json(responses_snapshot, "J1-general-check", [])
    non_monetary_rows = _extract_json(responses_snapshot, "J1-non-monetary", [])
    severance_check_rows = _extract_json(responses_snapshot, "J1-severance-check", [])
    cas9_conditions = _extract_json(responses_snapshot, "J1-cas9-conditions", [])

    # ─── 解析附注数据 ─────────────────────────────────────────────────────
    disclosure_listed_rows = _extract_json(responses_snapshot, "J1-disclosure-listed", [])
    disclosure_soe_rows = _extract_json(responses_snapshot, "J1-disclosure-soe", [])

    return {
        "component_type": "j1-employee-compensation",
        # 展示用科目码取解析结果首项（无解析结果才落兜底常量）
        "account_code": (accounts.gross_standard or [ACCOUNT_CODE])[0],
        "direction": "credit",
        "liability_formula": "end = begin + credit - debit",
        "tb_data": tb_data,
        "tb_values": tb_values,
        "tb_source_codes": tb_source_codes,
        "adjudication_prefill": adjudication_prefill,
        "detail_prefill": detail_prefill,
        "adjudication_rows": adjudication_rows,
        "detail_rows": detail_rows,
        "monthly_rows": monthly_rows,
        "industry_compare_rows": industry_compare_rows,
        "company_info": company_info,
        "accrual_check_rows": accrual_check_rows,
        "allocation_check_rows": allocation_check_rows,
        "general_check_rows": general_check_rows,
        "non_monetary_rows": non_monetary_rows,
        "severance_check_rows": severance_check_rows,
        "cas9_conditions": cas9_conditions,
        "disclosure_listed_rows": disclosure_listed_rows,
        "disclosure_soe_rows": disclosure_soe_rows,
        "responses": responses_snapshot,
        "sheets": J1_SHEETS,
    }


def _extract_json(responses: dict, key: str, default):
    """从 responses 中解析 JSON 数据.

    🔴 checklist_responses 无 content 列，业务 JSON 一律存 remark（前端各 tab 统一如此）。
    历史实现只读 raw["content"] → 所有 *_rows 恒为空；此处以 remark 为准并保留 content 兼容。
    """
    raw = responses.get(key, {})
    if not raw:
        return default
    for field in ("remark", "content"):
        val = raw.get(field)
        if not val:
            continue
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            continue
    return default


# ─── 负债类公式验证（后端校验） ─────────────────────────────────────────────

def validate_liability_balance(begin: float, credit: float, debit: float, expected_end: float) -> bool:
    """验证负债类期末余额: end = begin + credit - debit."""
    calculated = begin + credit - debit
    return abs(calculated - expected_end) < 0.01


def validate_salary_estimate(headcount: int, avg_salary: float, months: int, expected: float) -> bool:
    """验证工资测算: 人数×均薪×月数."""
    calculated = headcount * avg_salary * months
    return abs(calculated - expected) < 0.01


def validate_allocation_closure(allocated: list[float], total: float) -> tuple[bool, float]:
    """验证分配闭合: Σ各科目 = 薪酬总额."""
    allocated_total = sum(allocated)
    diff = allocated_total - total
    return abs(diff) < 0.01, diff
