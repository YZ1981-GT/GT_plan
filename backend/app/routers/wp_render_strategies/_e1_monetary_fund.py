"""E1 货币资金 — 专属渲染策略.

component_type = "e1-monetary-fund"

E1 前端组件 GtE1MonetaryFund 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/现金明细/银行明细/盘点/截止测试/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 E1 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

数据持久化在 checklist_responses 表，item_id 前缀为 "E1-*"。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# E1 货币资金科目：库存现金/银行存款/其他货币资金（均为资产/借方科目）
_CASH_PREFIX = "1001"
_BANK_PREFIX = "1002"
_OTHER_PREFIX = "1012"


def _num(value: object) -> float:
    """安全转 float，None → 0.0。"""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def _fetch_leaf_accounts(
    ctx: RenderContext, prefix: str, year: int
) -> list[dict]:
    """取某科目前缀下的**叶子**子科目余额行（借正贷负，资产类：借为正）。

    叶子判定：其 account_code 不是任何其它 code 的前缀（铁律「只汇总叶子」，
    避免 tb_balance 中间级 rollup 与其子科目同时计入导致双算）。
    若该前缀下只有一级科目（无子科目），则一级科目自身即叶子。

    返回 [{code, name, currency, opening, increase, decrease, ending}]，
    资产类：increase = 借方发生额、decrease = 贷方发生额、ending = 期末余额。
    """
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code.label("code"),
                sa.func.max(TbBalance.account_name).label("name"),
                sa.func.max(TbBalance.currency_code).label("currency"),
                sa.func.sum(TbBalance.opening_balance).label("opening"),
                sa.func.sum(TbBalance.debit_amount).label("debit"),
                sa.func.sum(TbBalance.credit_amount).label("credit"),
                sa.func.sum(TbBalance.closing_balance).label("closing"),
            )
            .where(active_filter, TbBalance.account_code.startswith(prefix))
            .group_by(TbBalance.account_code)
        )
        raw = [
            {
                "code": (r.code or "").strip(),
                "name": (r.name or "").strip(),
                "currency": (r.currency or "").strip(),
                "opening": _num(r.opening),
                "increase": _num(r.debit),
                "decrease": _num(r.credit),
                "ending": _num(r.closing),
            }
            for r in result.fetchall()
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 four-table leaf fetch failed (%s): %s", prefix, e)
        return []

    if not raw:
        return []

    all_codes = [x["code"] for x in raw if x["code"]]

    def _is_leaf(code: str) -> bool:
        if not code:
            return True
        return not any(c != code and c.startswith(code) for c in all_codes)

    leaves = [x for x in raw if _is_leaf(x["code"])]
    # 过滤全零空账户（无期初、无发生、无期末）：这些子科目对底稿无意义
    leaves = [
        x
        for x in leaves
        if abs(x["opening"]) >= 0.005
        or abs(x["increase"]) >= 0.005
        or abs(x["decrease"]) >= 0.005
        or abs(x["ending"]) >= 0.005
    ]
    leaves.sort(key=lambda x: x["code"])
    return leaves


async def _build_four_table_prefill(ctx: RenderContext, year: int) -> dict:
    """从四表库（tb_balance）提取 E1 明细预填数据 + 取数来源公式。

    对齐 J1/K9 审定表预填铁律：底稿明细行应从四表库自动提取，而非空表手填。
    每条记录附带 ``source``（人可读来源）与 ``formula``（TB() 取数公式），
    供前端「四表取数」公式管理面板展示与编辑。

    返回：
    - cash:  1001 库存现金 叶子（按币种/子科目）
    - bank:  1002 银行存款 叶子（每个 = 一个银行账户）
    - other: 1012 其他货币资金 叶子（受限类别/保证金）
    - account_list: 银行账户清单（供 E1-10 核对）
    """
    cash = await _fetch_leaf_accounts(ctx, _CASH_PREFIX, year)
    bank = await _fetch_leaf_accounts(ctx, _BANK_PREFIX, year)
    other = await _fetch_leaf_accounts(ctx, _OTHER_PREFIX, year)

    def _decorate(rows: list[dict]) -> list[dict]:
        out: list[dict] = []
        for r in rows:
            code = r["code"]
            out.append(
                {
                    **r,
                    "source": f"tb_balance:{code} {r['name']}",
                    # 期末余额取数公式（四表库叶子源，只读）
                    "formula": f"TB('{code}','期末余额')",
                    "formulaOpening": f"TB('{code}','期初余额')",
                }
            )
        return out

    cash_rows = _decorate(cash)
    bank_rows = _decorate(bank)
    other_rows = _decorate(other)

    # 银行账户清单（1002 叶子 = 银行账户，供 E1-10 核对完整性）
    account_list = [
        {"code": r["code"], "name": r["name"], "ending": r["ending"]}
        for r in bank
    ]

    return {
        "cash": cash_rows,
        "bank": bank_rows,
        "other": other_rows,
        "account_list": account_list,
        "meta": {
            "as_of": f"{year}-12-31" if year else "",
            "cash_count": len(cash_rows),
            "bank_count": len(bank_rows),
            "other_count": len(other_rows),
            "note": "资产/借方科目：本期增加=借方发生额，本期减少=贷方发生额，期末=期末余额（借正）。仅取叶子子科目，全零空账户已过滤。",
        },
    }


async def render(ctx: RenderContext) -> dict | None:
    """E1 货币资金渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtE1MonetaryFund，而非 grid 兜底或 OnlyOffice。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 E1-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'E1-%' "
                "LIMIT 1000"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
        "bs_date": "",
        "tb_amount": 0,
        "tb_amount_opening": 0,
        "tb_source_codes": [],
        "related_parties": [],
    }
    try:
        proj_row = (
            await db.execute(
                sa.text(
                    "SELECT client_name, audit_year, business_category "
                    "FROM projects WHERE id = :pid"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = (
                proj_row.business_category or ctx.business_category or ""
            )
            # bs_date（资产负债表日）
            if proj_row.audit_year:
                project_context["bs_date"] = f"{proj_row.audit_year}-12-31"
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 render: project context 查询失败: %s", e)

    # ─── 试算平衡表「货币资金」（参照报表规则映射 BS-002，而非硬编码前缀）─────
    # 科目编号从 report_config 规则映射解析（项目级覆盖→标准级），兼容企业自定义映射；
    # 无配置时回退 1001/1002/1012（零回归）。审定表以此为「试算平衡表数」核对基准。
    year = project_context.get("audit_year")
    if year:
        try:
            from app.services.report_account_mapping import (
                resolve_report_line_account_codes,
                build_trial_balance_code_filter,
            )

            codes = await resolve_report_line_account_codes(
                db, ctx.project_id, "BS-002", fallback=["1001", "1002", "1012"]
            )
            where_clause, code_params = build_trial_balance_code_filter(codes)
            project_context["tb_source_codes"] = codes  # 供前端/追溯展示规则映射来源
            tb_row = (
                await db.execute(
                    sa.text(
                        "SELECT COALESCE(SUM(audited_amount), 0) AS audited, "
                        "COALESCE(SUM(unadjusted_amount), 0) AS unadjusted "
                        "FROM trial_balance "
                        "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                        f"AND {where_clause}"
                    ),
                    {"pid": str(ctx.project_id), "year": int(year), **code_params},
                )
            ).fetchone()
            if tb_row:
                audited = float(tb_row.audited or 0)
                unadjusted = float(tb_row.unadjusted or 0)
                project_context["tb_amount"] = audited if audited else unadjusted
        except Exception as e:  # noqa: BLE001
            logger.warning("E1 render: trial_balance 货币资金查询失败: %s", e)

    # ─── 关联方清单 ──────────────────────────────────────────────────────
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
        logger.warning("E1 render: related_parties 查询失败: %s", e)

    # ─── 四表库明细预填（现金/银行/其他货币资金 叶子子科目 + 取数公式）────
    four_table_prefill: dict = {
        "cash": [], "bank": [], "other": [], "account_list": [], "meta": {}
    }
    if year:
        try:
            four_table_prefill = await _build_four_table_prefill(ctx, int(year))
        except Exception as e:  # noqa: BLE001
            logger.warning("E1 render: four_table_prefill 构建失败: %s", e)

    # ─── 期初 TB（供审定表期初核对）───────────────────────────────────────
    # trial_balance 无期初列，故期初取 tb_balance 期初余额叶子合计（复用 four_table_prefill 已做叶子提取，
    # 与明细表 seed 同源，保证审定期初合计 ≈ 期初 TB 数，期初差异归零）。
    try:
        tb_opening = 0.0
        for _grp in ("cash", "bank", "other"):
            for _row in four_table_prefill.get(_grp, []) or []:
                tb_opening += float(_row.get("opening") or 0)
        project_context["tb_amount_opening"] = tb_opening
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 render: tb_amount_opening 汇总失败: %s", e)
        project_context["tb_amount_opening"] = 0

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "four_table_prefill": four_table_prefill,
    }
