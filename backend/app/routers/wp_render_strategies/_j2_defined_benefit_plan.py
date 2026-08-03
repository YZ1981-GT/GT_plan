"""J2 长期应付职工薪酬 / 设定受益计划净资产 — 专属渲染策略.

科目：**2705 长期应付职工薪酬**（贷方/负债类）
公式：期末=期初+贷方-借方
精算核心：DBO六要素分解 + ISA620专家利用

🔴 **本文件曾取错整个科目族**：原 `ACCOUNT_CODE = "2221"` 是**应交税费**。活体 8 个项目
里 `2221` 有 18~72 行数据、`2705` 有 7~20 行 → 改造前 J2-1 审定表预填出的是**全部税种行**，
TB 核对数是应交税费余额（不是"恒空"，是把税种当成长期应付职工薪酬显示）。同族缺陷：
K2（`1231` 坏账准备 → `1901`）、D6（`1402` 在途物资 → `1141`）。

科目定位改走报表映射规则（`report_config`）：listed `BS-067` / soe `BS-093`，
两变体公式实证均为 **NULL** → 回退兜底标准码 `2705`，并在 `tb_source_codes.resolved_from`
标注 `fallback` 供前端溯源面板如实展示。

Spec: .kiro/specs/j-cycle-four-table-extraction-and-disclosure-alignment/
Requirements: 1.1, 1.2, 1.3, 1.4
"""
from __future__ import annotations
import json
import logging
import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.j_cycle_account_scope import (
    J2_SPEC_BY_ENTITY,
    classify_j2_movement,
    classify_j2_top_row,
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
from app.services.four_table import resolve_semantic_accounts
from app.services.four_table.j_cycle_account_scope import j_semantic_spec_of

logger = logging.getLogger(__name__)

J2_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "长期应付职工薪酬实质性程序表 J2A", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "审定表J2-1", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "明细表J2-2", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "调整分录汇总表J2-3", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "计提情况检查表J2-4", "component_type": "j2-defined-benefit-plan"},
]

#: 兜底展示用科目码（真实科目码一律取 `tb_source_codes.gross_standard`）。
#: 🔴 绝不是 `2221`（应交税费）也不是 `2611`（不存在的科目，公式预设曾误用）。
ACCOUNT_CODE = "2705"


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（可独立单测，无 DB）
# ─────────────────────────────────────────────────────────────────────────────


def build_j2_tb_values(leaves: list[LeafRow], accounts: ReportLineAccounts) -> dict:
    """聚合范围内叶子，返回 `{opening, closing, debit, credit}`（负债取绝对值）。

    ``leaves`` 已由 :func:`select_scope_leaves` 按科目范围筛过（含平铺形态兼容），
    此处不再二次过滤 —— 二次用 ``filter_by_prefixes`` 会把平铺叶子重新漏掉。

    `tb_balance` 并存「无符号 + 方向列」与「已带符号」两种约定，两者 `abs()` 同解；
    但取绝对值只作用于**聚合结果**（不在行级翻转），以保「叶子和 == 父额」勾稽。
    """
    agg = {
        "opening": sum(r.opening for r in leaves),
        "closing": sum(r.closing for r in leaves),
        "debit": sum(r.debit for r in leaves),
        "credit": sum(r.credit for r in leaves),
    }
    return {k: abs(v) for k, v in agg.items()}


def liability_orientation(all_rows: list[LeafRow], prefixes) -> int:
    """判定「让负债显正」需要的整体取向系数（``+1`` 或 ``-1``）。

    🔴 **逐行 `abs()` 是错的**（改造前即如此，本次真实数据证伪）。实测项目
    `5e193c68` 的 `2705` 叶子**带混合符号**::

        2705.01.99 初始入账金额        -729,000.00   贷方（负债增加）
        2705.01.03 过去服务成本        +375,000.00   借方性质
        2705.01.04 结算利得            -11,000.00
        2705.01.05 利息净额           -116,000.00
        2705.01.06 重新计量           -276,000.00
        2705.01.01 离退休人员费用      +362,720.20   借方性质（已支付）
        ───────────────────────────────────────────
        签名和                        -394,279.80 == 父科目 2705 期末 ✅
        逐行 abs 之和               = 1,831,000.00 ✗ 与父额差 4.6 倍

    正解：**整族**乘同一个系数，保住行间相对关系。父科目余额为负（贷方存负）时取
    ``-1``，此时初始入账变 ``+729,000``、过去服务成本变 ``-375,000``，
    行级和 == 父额的负债口径正数 ``+394,279.80``。

    父科目行缺失时退回按叶子签名和判定；两者皆为 0 时返 ``+1``（无害）。
    """
    for prefix in prefixes or []:
        parent = parent_totals(all_rows, prefix)
        if abs(parent["closing"]) >= 0.005:
            return -1 if parent["closing"] < 0 else 1
        if abs(parent["opening"]) >= 0.005:
            return -1 if parent["opening"] < 0 else 1
    signed = sum(r.closing for r in select_scope_leaves(all_rows, prefixes))
    return -1 if signed < 0 else 1


def build_j2_adjudication_prefill(
    leaves: list[LeafRow],
    accounts: ReportLineAccounts,
    sign: int = 1,
) -> list[dict]:
    """`2705` 叶子 → J2-1 审定表预填行。

    键名沿用改造前形态（`name` / `code` / `opening_balance` / `closing_balance`），
    前端 `useJ2Adjudication` 零改动即可消费。

    - **叶子口径**（不是「最深层级」）：客户科目树参差，取 max_depth 会整段丢一级叶子
    - **整族统一取向**（`sign`，见 :func:`liability_orientation`），不逐行 `abs()`：
      行级金额之和 == 父科目额（负债口径正数），借方性质叶子如实显示为负
    - 期初/期末全为 0 的叶子跳过（宁缺勿造）
    - 无命中叶子时返回 ``[]``，**不回退到任何其它科目族**
    - **不假设层级深度**：行由项目自己的叶子科目动态产生（实测各项目 `2705` 叶子
      7~10 个不等，医疗器械项目无 `当期服务成本`/`辞退福利`，和平药房还无 `结算利得`）
    """
    out: list[dict] = []
    for r in sorted(leaves, key=lambda x: abs(x.closing), reverse=True):
        if not r.account_name:
            continue
        if abs(r.opening) < 0.005 and abs(r.closing) < 0.005:
            continue
        top = classify_j2_top_row(r.account_code, r.account_name)
        movement = classify_j2_movement(r.account_code, r.account_name)
        opening = sign * r.opening
        closing = sign * r.closing
        out.append(
            {
                "name": r.account_name,
                "code": r.account_code,
                "opening_balance": opening,
                "closing_balance": closing,
                # 本期变动额（负债口径：正=增加）。源模板变动表行取的是变动额不是余额。
                "change": round(closing - opening, 2),
                # 披露落点提示（前端「刷新取数」按科目码优先匹配时用）
                "top_row_key": top.key,
                "top_row_label": top.label.strip(),
                "movement_key": movement.key if movement else None,
                "movement_label": movement.label if movement else None,
            }
        )
    return out


def build_j2_movement_prefill(
    leaves: list[LeafRow],
    accounts: ReportLineAccounts,
    sign: int = 1,
) -> dict[str, dict]:
    """`2705.01.xx` 叶子 → 设定受益计划变动行预填 ``{movement_key: {opening, closing}}``。

    🔴 **只映射有变动性质信息的叶子**（当期服务成本 / 过去服务成本 / 结算利得 / 利息净额 /
    重新计量 / 初始入账）。`2705.01` 与 `2705.01.01 离退休人员费用` 等无变动性质的叶子
    返回时不出现在结果里 —— 四表数据推不出「这笔钱属于哪个变动要素」，机械摊入即造假
    （同 G7「损益调整/其他权益变动是变动性质不是被投资单位类别」判断）。
    """
    out: dict[str, dict] = {}
    for r in leaves:
        rule = classify_j2_movement(r.account_code, r.account_name)
        if rule is None:
            continue
        slot = out.setdefault(
            rule.key,
            {
                "label": rule.label,
                "opening": 0.0,
                "increase": 0.0,
                "decrease": 0.0,
                "closing": 0.0,
                "change": 0.0,
                "codes": [],
            },
        )
        slot["opening"] += sign * r.opening
        slot["closing"] += sign * r.closing
        # 负债贷方：credit=增加、debit=减少；发生额以正数存储，不受 sign 影响
        slot["increase"] += r.credit
        slot["decrease"] += r.debit
        if r.account_code not in slot["codes"]:
            slot["codes"].append(r.account_code)
    for slot in out.values():
        for k in ("opening", "increase", "decrease", "closing"):
            slot[k] = round(slot[k], 2)
        slot["change"] = round(slot["closing"] - slot["opening"], 2)
        slot["rollforward_diff"] = round(
            slot["opening"] + slot["increase"] - slot["decrease"] - slot["closing"], 2
        )
    return out


def build_j2_source_codes(
    accounts: ReportLineAccounts, all_rows: list[LeafRow], leaves: list[LeafRow]
) -> dict:
    """取数溯源载荷（前端 `WpFourTableSourcePanel` 消费，非 dead output）。

    附带 `parent_check` 自检：叶子和 vs 父科目行金额，差额应为 0。
    """
    payload = accounts.as_dict()
    leaf_agg = build_j2_tb_values(leaves, accounts)
    parent_codes = {r.account_code for r in all_rows}
    parent_check: dict[str, dict] = {}
    for prefix in accounts.gross:
        parent = parent_totals(all_rows, prefix)
        # 父科目行可能不存在（只有明细行）→ 用 present 区分「无父行」与「真差异」，
        # 否则溯源面板会常亮假告警。
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


async def _load_j2_leaves(
    ctx: RenderContext, accounts: ReportLineAccounts
) -> tuple[list[LeafRow], list[LeafRow]]:
    """一次查询取 active 数据集全量行，返回 ``(全部行, 范围内叶子行)``。失败返 ``([], [])``。

    叶子筛选走 :func:`select_scope_leaves`（按项目自己的科目树动态判定，兼容平铺形态），
    **不假设层级深度**。
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
            ).where(active_filter)
        )
        rows = to_leaf_rows(result.fetchall())
    except Exception as e:  # noqa: BLE001 — 取数失败按空处理，不阻塞渲染
        logger.warning("J2 tb_balance 查询失败: %s", e)
        return [], []
    return rows, select_scope_leaves(rows, accounts.gross)


async def _resolve_j2_accounts(ctx: RenderContext) -> ReportLineAccounts:
    """按变体解析 J2 报表行（listed `BS-067` / soe `BS-093`），兜底 `2705`。"""
    standards = await fetch_applicable_standards(ctx)
    spec = pick_spec(J2_SPEC_BY_ENTITY, standards)
    return await resolve_report_line_accounts(ctx, spec)


async def render(ctx: RenderContext) -> dict | None:
    """渲染 J2 设定受益计划底稿数据.

    负债类贷方：从 trial_balance 读取 2221 余额，
    从 checklist_responses 读取精算假设、ISA620评估、审定表数据。
    """

    # 科目定位（语义驱动，additive）
    _sem_spec = j_semantic_spec_of("J2")
    try:
        _sem_accounts = await resolve_semantic_accounts(ctx, _sem_spec) if _sem_spec else None
    except Exception:  # noqa: BLE001
        _sem_accounts = None

    responses_snapshot: dict = {}
    tb_data: dict = {}

    # ─── 科目定位（报表映射规则驱动，不再硬编码） ─────────────────────────
    accounts = await _resolve_j2_accounts(ctx)

    # ─── 读取 trial_balance（按解析出的**标准码**，不是字面量） ───────────
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
        logger.warning("J2 render TB read failed: %s", e)

    # ─── 读取 checklist_responses ──────────────────────────────────────────
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "J2-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("J2 render checklist read failed: %s", e)

    # ─── 解析精算假设 ──────────────────────────────────────────────────────
    assumptions = _extract_json(responses_snapshot, "J2-actuarial-assumptions", {
        "discountRate": 0.04,
        "salaryGrowthRate": 0.08,
        "mortalityRate": 0.005,
        "turnoverRate": 0.10,
    })

    # ─── 解析 ISA620 数据 ─────────────────────────────────────────────────
    isa620 = _extract_json(responses_snapshot, "J2-isa620-evaluation", {})

    # ─── 解析审定表三区块 ─────────────────────────────────────────────────
    adjudication = _extract_json(responses_snapshot, "J2-adjudication-data", {})

    # ─── 解析明细表 ───────────────────────────────────────────────────────
    detail = _extract_json(responses_snapshot, "J2-detail-data", [])

    # ─── 四表取数（叶子口径） ─────────────────────────────────────────────
    all_rows, leaves = await _load_j2_leaves(ctx, accounts)
    sign = liability_orientation(all_rows, accounts.gross)
    tb_values = build_j2_tb_values(leaves, accounts)
    adjudication_prefill = build_j2_adjudication_prefill(leaves, accounts, sign)
    movement_prefill = build_j2_movement_prefill(leaves, accounts, sign)
    tb_source_codes = build_j2_source_codes(accounts, all_rows, leaves)

    return {
        "component_type": "j2-defined-benefit-plan",
        # 展示用科目码取解析结果首项（无解析结果才落兜底常量）
        "account_code": (accounts.gross_standard or [ACCOUNT_CODE])[0],
        "direction": "credit",
        "liability_formula": "end = begin + credit - debit",
        "tb_data": tb_data,
        "tb_values": tb_values,
        "tb_source_codes": tb_source_codes,
        "assumptions": assumptions,
        "isa620": isa620,
        "adjudication": adjudication,
        "detail": detail,
        "adjudication_prefill": adjudication_prefill,
        "movement_prefill": movement_prefill,
        "responses": responses_snapshot,
        "sheets": J2_SHEETS,
    }


def _extract_json(responses: dict, key: str, default):
    """从 responses 中解析 JSON 数据（存于 remark 字段，对齐前端持久化）."""
    raw = responses.get(key, {})
    if raw and raw.get("remark"):
        try:
            return json.loads(raw["remark"])
        except (json.JSONDecodeError, TypeError):
            pass
    return default


# ─── 负债类公式验证（后端校验） ─────────────────────────────────────────────

def validate_liability_balance(begin: float, credit: float, debit: float, expected_end: float) -> bool:
    """验证负债类期末余额: end = begin + credit - debit."""
    calculated = begin + credit - debit
    return abs(calculated - expected_end) < 0.01


def validate_dbo_decomposition(
    begin_dbo: float,
    service_cost: float,
    interest_cost: float,
    actuarial_loss: float,
    actuarial_gain: float,
    benefits_paid: float,
    expected_end: float,
) -> bool:
    """验证DBO期末完整公式: end = begin + service + interest + loss - gain - paid."""
    calculated = begin_dbo + service_cost + interest_cost + actuarial_loss - actuarial_gain - benefits_paid
    return abs(calculated - expected_end) < 0.01
