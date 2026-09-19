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
from app.services.four_table import (
    LeafRow,
    aggregate_leaves,
    classify_e1_restricted_leaf,
    fetch_tb_subtree,
    filter_by_prefixes,
    parent_totals,
    resolve_semantic_accounts,
    select_leaves,
)
from app.services.four_table.e1_bank_accounts import (
    assign_accounts_to_slots,
    build_e1_account_prefill,
    fetch_e1_bank_accounts,
)
from app.services.four_table.e_cycle_specs import (
    E1_MONETARY_FUND_SPEC,
    E1_SLOT_BANK,
    E1_SLOT_CASH,
    E1_SLOT_DIGITAL,
    E1_SLOT_FINANCE_CO,
    E1_SLOT_OTHER,
    E1_TOTAL_SLOT_KEYS,
)
from app.services.four_table.e1_restricted_buckets import bucket_defs_payload

from ._context import RenderContext

logger = logging.getLogger(__name__)

#: 明细预填的槽（R2.1 扩至 5 槽）。
#:
#: 🔴 前三个的**键名与顺序**是既有前端契约（`four_table_prefill.{cash,bank,other}`），
#: 不得改动；`finance_co`/`digital` 是加法式新增（准则解释 15 号「可增设」项，
#: 两槽在 `e_cycle_specs` 里**故意无兜底码** ⇒ 多数项目 `found=False` 返空列表，
#: 前端据此显示「本项目无此科目」而不是 0（R2.2/R2.5）。
_DETAIL_SLOT_KEYS: tuple[str, ...] = (
    E1_SLOT_CASH,
    E1_SLOT_BANK,
    E1_SLOT_OTHER,
    E1_SLOT_FINANCE_CO,
    E1_SLOT_DIGITAL,
)

#: 账户级取数覆盖的槽（`tb_aux_balance` 的 `银行账户` 维度只对存款类科目有意义）。
#: `finance_co` 一并纳入 —— 存放财务公司款项也是「按户」管理的（R2.3）。
_ACCOUNT_SLOT_KEYS: tuple[str, ...] = (
    E1_SLOT_BANK,
    E1_SLOT_OTHER,
    E1_SLOT_FINANCE_CO,
)

#: 金额零值判定阈值（分以下视为 0）
_ZERO_EPS = 0.005


def _num(value: object) -> float:
    """安全转 float，None → 0.0。"""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_all_zero(row: LeafRow) -> bool:
    """四项金额全为 0（无期初、无发生、无期末）。"""
    return (
        abs(row.opening) < _ZERO_EPS
        and abs(row.debit) < _ZERO_EPS
        and abs(row.credit) < _ZERO_EPS
        and abs(row.closing) < _ZERO_EPS
    )


async def _fetch_currency_map(
    ctx: RenderContext, year: int, prefixes: list[str]
) -> dict[str, str]:
    """取 `account_code → currency_code` 映射（外币披露表需要，`LeafRow` 不含该列）。

    单独一条轻量查询，不动共享件 `fetch_tb_subtree` 的列集（其它循环不需要币种）。
    fail-open：失败返 {}，币种降级为空串。
    """
    ps = [p for p in (str(x or "").strip() for x in prefixes or []) if p]
    if not ps:
        return {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, year or 0
        )
        prefix_filter = sa.or_(*[TbBalance.account_code.like(f"{p}%") for p in ps])
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code.label("code"),
                sa.func.max(TbBalance.currency_code).label("currency"),
            )
            .where(sa.and_(active_filter, prefix_filter))
            .group_by(TbBalance.account_code)
        )
        return {
            (r.code or "").strip(): (r.currency or "").strip()
            for r in result.fetchall()
            if (r.code or "").strip()
        }
    except Exception as e:  # noqa: BLE001 — fail-open
        logger.warning("E1 render: currency map 查询失败: %s", e)
        try:
            await ctx.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {}


def build_e1_slot_leaves(
    subtree: list[LeafRow], accounts
) -> dict[str, list[LeafRow]]:
    """把整棵子树按语义槽分组并筛出叶子。纯函数。

    🔴 叶子筛选在**全子树**上做（`select_leaves` 需要看到兄弟行才能判叶子），
    再按各槽的原始码前缀分配 —— 反过来先分组再筛叶子会因看不到兄弟而误判。

    Returns:
        ``{slot_key: [LeafRow, ...]}``；槽未命中科目时为空列表。
    """
    leaves = select_leaves(subtree)
    out: dict[str, list[LeafRow]] = {}
    for slot_key, slot in (accounts.slots or {}).items():
        codes = list(slot.codes or [])
        picked = filter_by_prefixes(leaves, codes) if codes else []
        out[slot_key] = sorted(picked, key=lambda r: r.account_code)
    return out


def build_e1_detail_rows(
    slot_leaves: dict[str, list[LeafRow]],
    currency_map: dict[str, str],
) -> dict[str, list[dict]]:
    """各语义槽的明细预填行（前端 `four_table_prefill.{cash,bank,other,...}`）。

    字段与既有前端契约逐字一致（`code/name/currency/opening/increase/decrease/
    ending/source/formula/formulaOpening`），零回归。

    🔴 槽集合由 `_DETAIL_SLOT_KEYS` 声明（R2.1 已扩到 5 槽）。新增的
    `finance_co`/`digital` 在多数项目 `found=False` ⇒ 该键为 `[]`（**不是缺键、
    也不产生 0 值占位行**），前端据此显示「本项目无此科目」（R2.2/R2.5）。
    前三槽的键名与产出顺序**逐字不变** —— Property 9 characterization 钉死。

    **过滤全零账户**：这些子科目对金额明细无意义。注意银行账户清单
    （`build_e1_account_list`）**不做**此过滤 —— 见其 docstring。
    """
    out: dict[str, list[dict]] = {}
    for slot_key in _DETAIL_SLOT_KEYS:
        rows: list[dict] = []
        for r in slot_leaves.get(slot_key, []):
            if _is_all_zero(r):
                continue
            rows.append(
                {
                    "code": r.account_code,
                    "name": r.account_name,
                    "currency": currency_map.get(r.account_code, ""),
                    "opening": r.opening,
                    "increase": r.debit,
                    "decrease": r.credit,
                    "ending": r.closing,
                    "source": f"tb_balance:{r.account_code} {r.account_name}",
                    "formula": f"TB('{r.account_code}','期末余额')",
                    "formulaOpening": f"TB('{r.account_code}','期初余额')",
                }
            )
        out[slot_key] = rows
    return out


def build_e1_account_list(
    slot_leaves: dict[str, list[LeafRow]],
    currency_map: dict[str, str],
) -> list[dict]:
    """银行账户清单（供 E1-10「已开立银行账户清单核对」）。纯函数。

    🔴 **不过滤零余额账户** —— 与金额明细口径故意不同：银行账户**完整性**核对
    恰恰要看「本年新开立但期末余额为 0」的账户（体外账户/未入账账户是货币资金
    舞弊的常见切入点）。旧实现统一过滤全零行，把这些账户从清单里抹掉，
    反而削弱了完整性程序。
    """
    return [
        {
            "code": r.account_code,
            "name": r.account_name,
            "currency": currency_map.get(r.account_code, ""),
            "opening": r.opening,
            "ending": r.closing,
            "isZeroBalance": _is_all_zero(r),
        }
        for r in slot_leaves.get(E1_SLOT_BANK, [])
    ]


def build_e1_tb_values(slot_leaves: dict[str, list[LeafRow]]) -> dict[str, float]:
    """各槽的叶子聚合金额 + 三族合计（供审定表 TB 核对与披露主表）。纯函数。"""
    out: dict[str, float] = {}
    total_open = 0.0
    total_close = 0.0
    for slot_key, rows in slot_leaves.items():
        agg = {
            "opening": sum(r.opening for r in rows),
            "closing": sum(r.closing for r in rows),
        }
        out[f"{slot_key}_opening"] = agg["opening"]
        out[f"{slot_key}_closing"] = agg["closing"]
        if slot_key in E1_TOTAL_SLOT_KEYS:
            total_open += agg["opening"]
            total_close += agg["closing"]
    out["total_opening"] = total_open
    out["total_closing"] = total_close
    return out


def build_e1_adjudication_prefill(
    slot_leaves: dict[str, list[LeafRow]], accounts
) -> dict[str, dict]:
    """审定表 E1-1 未审数预填（按语义槽，仅无持久化时套用）。纯函数。

    每槽给 ``{opening, closing, accountCode, accountCodes, found}``；
    ``found=False`` 表示本项目无该科目 → 前端显示「本项目无此科目」而非 0。
    """
    out: dict[str, dict] = {}
    for slot_key, slot in (accounts.slots or {}).items():
        rows = slot_leaves.get(slot_key, [])
        codes = list(slot.codes or [])
        out[slot_key] = {
            "opening": sum(r.opening for r in rows),
            "closing": sum(r.closing for r in rows),
            "accountCode": codes[0] if codes else "",
            "accountCodes": codes,
            "found": bool(slot.found),
        }
    return out


def build_e1_restricted_prefill(
    slot_leaves: dict[str, list[LeafRow]], accounts
) -> dict:
    """受限制货币资金动态取数（映射规则驱动 + 逐叶子按名称分类）。纯函数。

    候选集**只来自货币资金三族的叶子**（受限资金必然是货币资金的一部分，
    校验预设 F1-5「②表合计 = 报表货币资金 − 现金及现金等价物」即此含义），
    不跨族去猜。

    🔴 **下发扁平叶子清单而不是预聚合的桶**：审计师可在「待归类科目」面板把叶子
    改归到别的类别，若后端只给聚合值，前端就无法重算被改动桶的余额（预聚合是
    有损表示）。故这里给逐叶子明细 + ``autoBucket`` 自动分类标记，聚合全部由前端
    按「人工归类 > 自动分类」做，单一真源、无不可重算状态。

    ``autoBucket=None`` 表示按名称判不出来 —— 交审计师点选归类，
    **既不静默丢弃也不臆造归属**（宁缺勿造）。

    全零叶子不下发：活体项目有 50+ 个零余额空壳分支户，全下发会淹没面板；
    金额为 0 不影响「叶子和 == 三族合计」的求和恒等式。

    Returns:
        ``{leaves: [{code,name,opening,closing,slot,autoBucket}],
        bucketDefs: [...], source: {...}}``
    """
    leaves: list[dict] = []
    for slot_key in E1_TOTAL_SLOT_KEYS:
        for r in slot_leaves.get(slot_key, []):
            if _is_all_zero(r):
                continue
            leaves.append(
                {
                    "code": r.account_code,
                    "name": r.account_name,
                    "opening": r.opening,
                    "closing": r.closing,
                    "slot": slot_key,
                    "autoBucket": classify_e1_restricted_leaf(r.account_name),
                }
            )
    return {
        "leaves": leaves,
        "bucketDefs": bucket_defs_payload(),
        "source": {
            "report_row_code": accounts.row_code,
            "chart_available": bool(accounts.chart_available),
        },
    }


def build_e1_parent_check(
    subtree: list[LeafRow], accounts
) -> dict[str, dict[str, float]]:
    """「叶子和 == 父科目额」勾稽自检（不阻断，供 UI 提示数据质量）。纯函数。"""
    leaves = select_leaves(subtree)
    out: dict[str, dict[str, float]] = {}
    for slot_key, slot in (accounts.slots or {}).items():
        for code in slot.codes or []:
            # 🔴 `setdefault` 而非赋值：同一科目码理论上可被多个槽声明（如客户把
            # 「数字货币」挂在 1012 下），此时应保留**首个**声明它的槽，
            # 否则最后一个槽会把 `slot` 标签覆盖成误导值（实测曾把三个码都标成 `digital`）。
            if code in out:
                continue
            parent = parent_totals(subtree, code)
            leaf = aggregate_leaves(leaves, [code])
            out.setdefault(
                code,
                {
                    "slot": slot_key,
                    "parent_closing": parent["closing"],
                    "leaf_closing": leaf["closing"],
                    "diff": round(leaf["closing"] - parent["closing"], 2),
                },
            )
    return out


#: 账户级取数覆盖的槽（银行存款 / 其他货币资金 / 存放财务公司款项）。
#: 🔴 `cash`（库存现金）与 `digital`（数字货币）**不参与** —— 前者无银行账户维度，
#: 后者是数字人民币钱包不走 `aux_type='银行账户'`。
_ACCOUNT_SLOT_KEYS: tuple[str, ...] = (
    E1_SLOT_BANK,
    E1_SLOT_OTHER,
    E1_SLOT_FINANCE_CO,
)


def _empty_account_prefill() -> dict:
    """账户级取数的空态载荷。

    🔴 形态必须与 `build_e1_account_prefill` 一致（各槽键存在、值为 `[]`）——
    前端 `normalizeAccountPrefill` 据「`accounts` 各键为空数组」退回叶子口径；
    若这里少给键，前端拿到 `undefined` 会与「注入整体失败」不可区分。
    """
    return {
        "accounts": {**{k: [] for k in _ACCOUNT_SLOT_KEYS}, "unassigned": []},
        "reconcile": {},
        "meta": {"source": "", "account_count": 0, "parsed_level_dist": {}},
    }


async def _build_account_prefill(
    ctx: RenderContext,
    year: int,
    accounts,
    slot_leaves: dict[str, list[LeafRow]],
) -> dict:
    """账户级取数（`tb_aux_balance` 的 `银行账户` 维度）→ `account_prefill` 载荷。

    客户的 `1002 银行存款` 在 `tb_balance` 里**不分户**（叶子恒 1 行），而 E1-3
    要逐户列示、E1-10 要做账户完整性核对 —— 账户级明细的唯一来源是 aux 维度。

    加法式：只新增返回键，既有 `four_table_prefill` 逐字不变（Property 9 零回归支点）。
    aux 无数据 / 取数失败时返 `_empty_account_prefill()`，前端退回叶子口径。

    🔴 **本函数必须有自己的 fail-open** —— 它是加法式新增的一步，若让异常冒泡到
    `_build_four_table_extraction`，会被那里的 fail-open 吞成「整个 extraction 失败」，
    把**已经通了的三槽明细预填 / 审定预填 / 受限分类一起打掉**（新功能坏掉不该
    连累既有功能）。守卫 `test_account_prefill_is_fail_open` 钉死这条。
    """
    try:
        slot_codes: dict[str, list[str]] = {}
        for slot_key in _ACCOUNT_SLOT_KEYS:
            slot = (accounts.slots or {}).get(slot_key)
            codes = [c for c in (getattr(slot, "codes", None) or []) if c]
            if codes:
                slot_codes[slot_key] = codes
        if not slot_codes:
            return _empty_account_prefill()

        prefixes = [c for codes in slot_codes.values() for c in codes]
        rows = await fetch_e1_bank_accounts(
            ctx.db, ctx.project_id, year, account_prefixes=prefixes
        )
        if not rows:
            return _empty_account_prefill()

        assignment = assign_accounts_to_slots(rows, slot_codes)
        # 勾稽基准取各槽**叶子期末合计**（与 `build_e1_tb_values` 同口径）
        slot_leaf_closing = {
            slot_key: sum(r.closing for r in slot_leaves.get(slot_key, []))
            for slot_key in slot_codes
        }
        payload = build_e1_account_prefill(assignment, slot_leaf_closing)
        # 未声明码的槽也要有键（前端按槽渲染，缺键会退化成「无此科目」的误导态）
        for slot_key in _ACCOUNT_SLOT_KEYS:
            payload["accounts"].setdefault(slot_key, [])
        return payload
    except Exception as e:  # noqa: BLE001 — 见上方 docstring 的零回归论证
        logger.warning("E1 render: 账户级取数构建失败（退回叶子口径）: %s", e)
        return _empty_account_prefill()


async def _build_four_table_extraction(ctx: RenderContext, year: int) -> dict:
    """从四表库提取 E1 全套取数结果（明细预填 + 审定预填 + 受限分类 + 溯源）。

    科目定位走 `four_table.resolve_semantic_accounts`（**按科目名逐项目定位**）——
    标准码在项目间并不一致、且「数字货币」「存放财务公司款项」没有一级标准科目，
    写死任何码都会在部分项目取空或取错（详见 `e_cycle_specs` 模块 docstring）。

    Returns:
        ``{four_table_prefill, account_prefill, adjudication_prefill,
        restricted_prefill, tb_values, tb_source_codes}``
    """
    accounts = await resolve_semantic_accounts(ctx, E1_MONETARY_FUND_SPEC)

    all_prefixes: list[str] = []
    for slot in (accounts.slots or {}).values():
        all_prefixes.extend(slot.codes or [])
    all_prefixes = [p for p in dict.fromkeys(all_prefixes) if p]

    subtree = await fetch_tb_subtree(ctx.db, ctx.project_id, year, all_prefixes)
    currency_map = await _fetch_currency_map(ctx, year, all_prefixes)

    slot_leaves = build_e1_slot_leaves(subtree, accounts)
    detail = build_e1_detail_rows(slot_leaves, currency_map)
    account_list = build_e1_account_list(slot_leaves, currency_map)

    source_codes = accounts.as_dict()
    source_codes["parent_check"] = build_e1_parent_check(subtree, accounts)

    account_prefill = await _build_account_prefill(ctx, year, accounts, slot_leaves)

    return {
        "four_table_prefill": {
            **detail,
            "account_list": account_list,
            "meta": {
                "as_of": f"{year}-12-31" if year else "",
                "cash_count": len(detail.get(E1_SLOT_CASH, [])),
                "bank_count": len(detail.get(E1_SLOT_BANK, [])),
                "other_count": len(detail.get(E1_SLOT_OTHER, [])),
                "account_count": len(account_list),
                "note": (
                    "资产/借方科目：本期增加=借方发生额，本期减少=贷方发生额，"
                    "期末=期末余额（借正）。仅取叶子子科目；金额明细已过滤全零账户，"
                    "但银行账户清单保留零余额账户以支持 E1-10 完整性核对。"
                ),
            },
        },
        "account_prefill": account_prefill,
        "adjudication_prefill": build_e1_adjudication_prefill(slot_leaves, accounts),
        "restricted_prefill": build_e1_restricted_prefill(slot_leaves, accounts),
        "tb_values": build_e1_tb_values(slot_leaves),
        "tb_source_codes": source_codes,
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

    year = project_context.get("audit_year")

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

    # ─── 四表库取数（语义科目定位 → 叶子聚合 → 明细/审定/受限预填 + 溯源）────
    extraction: dict = {
        "four_table_prefill": {
            "cash": [], "bank": [], "other": [], "account_list": [], "meta": {}
        },
        # 🔴 空态也要给齐全部键（不是缺键）—— 前端 `normalizeAccountPrefill`
        # 据「accounts 各槽为 []」退回既有 tb_balance 叶子口径（R1.6 零回归）。
        # 缺键会让「取数整体失败」与「本项目无 aux 数据」不可区分。
        "account_prefill": _empty_account_prefill(),
        "adjudication_prefill": {},
        "restricted_prefill": {
            "leaves": [],
            "bucketDefs": bucket_defs_payload(),
            "source": {},
        },
        "tb_values": {},
        "tb_source_codes": {},
    }
    if year:
        try:
            extraction = await _build_four_table_extraction(ctx, int(year))
        except Exception as e:  # noqa: BLE001 — fail-open，取数失败不阻断底稿打开
            logger.warning("E1 render: 四表取数构建失败: %s", e)

    tb_values = extraction.get("tb_values") or {}
    # 供前端/追溯展示科目定位来源（含 conflicts / unmapped_candidates / parent_check）
    project_context["tb_source_codes"] = extraction.get("tb_source_codes") or {}
    # 审定表「试算平衡表数」核对基准 —— 取 tb_balance 三族**叶子**合计。
    # 🔴 不用 trial_balance：该表存在旧版 recalc 写入的父子双算陈旧数据
    # （见 four_table/tb_query.fetch_trial_balance_amounts 的警示），
    # 而叶子口径有「叶子和 == 父额」自检（parent_check）可验证。
    project_context["tb_amount"] = _num(tb_values.get("total_closing"))
    project_context["tb_amount_opening"] = _num(tb_values.get("total_opening"))

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "four_table_prefill": extraction.get("four_table_prefill") or {},
        # 🔴 账户级取数（E1-3 逐户 / E1-10 完整性核对的唯一数据源）。
        # 缺这一键 = 后端算了但前端拿不到 = dead output（平台已踩多次）。
        # 无 aux 数据时是形态合法的空载荷（各槽 `[]`），前端据此退回叶子口径。
        "account_prefill": extraction.get("account_prefill") or _empty_account_prefill(),
        "adjudication_prefill": extraction.get("adjudication_prefill") or {},
        "restricted_prefill": extraction.get("restricted_prefill") or {},
        "tb_values": tb_values,
    }
