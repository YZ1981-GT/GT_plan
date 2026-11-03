"""单体财务报表：按 A000000 第 107 项会计准则代码自动选格式。

- 300（企业会计制度）：资产负债表 / 续表 / 利润表按 ``fs_enterprise_system.json`` 从试算平衡表页同一份标准科目余额
  （``standard_balance_view_service``）取审定数；上年年末 = 试算表期初；利润表上期取上年项目同一视图（取不到写原因）。
  现金流量表 / 补充资料取平台已生成的现金流量表，按行名对应。
- 1xx（企业会计准则）：复用平台审定报表（``financial_report``）。
- 未填写：按客户科目编码判断（旧编码体系 ⇒ 企业会计制度，否则企业会计准则）并提示去申报表填写；其他代码提示暂不支持。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import AccountChart, AccountSource
from app.models.core import Project
from app.models.report_models import FinancialReport, FinancialReportType
from app.services import tax_workpaper_service as tws
from app.services.legacy_pl_crosswalk import ENTERPRISE_SYSTEM_2001, detect_legacy_pl_crosswalk
from app.services.prior_year_context import resolve_prior_source
from app.services.standard_balance_view_service import build_standard_balance_view
from app.services.tax_assurance.fs_rows import compute_statement, is_pl_code, load_config, normalize_name

FORMAT_SYSTEM = "enterprise_system"
FORMAT_CAS = "cas"
STANDARD_CELL = ("A000000", "F6")
_ZERO = Decimal(0)

FORMAT_LABELS = {FORMAT_SYSTEM: "企业会计制度", FORMAT_CAS: "企业会计准则"}

_CAS_REPORTS = [
    (FinancialReportType.balance_sheet, "资产负债表", ["期末余额", "上年年末余额"]),
    (FinancialReportType.income_statement, "利润表", ["本期金额", "上期金额"]),
    (FinancialReportType.cash_flow_statement, "现金流量表", ["本期金额", "上期金额"]),
    (FinancialReportType.cash_flow_supplement, "现金流量表补充资料", ["本期金额", "上期金额"]),
]


def _d(v: Any) -> Decimal:
    return Decimal(str(v)) if v not in (None, "") else _ZERO


# ── 格式选择 ──
async def standard_code(db: AsyncSession, project_id: UUID, year: int) -> str:
    """A000000 第 107 项「适用会计准则或会计制度」代码（申报表计算值，空串 = 未填）。"""
    wb = tws.load_workbook()
    sheet, ref = STANDARD_CELL
    key = (sheet, *tws.parse_a1(ref))
    ev = await tws.evaluate_keys(db, project_id, year, [key])
    v = ev.value(sheet, ref)
    if isinstance(v, Decimal):
        return str(int(v)) if v == v.to_integral_value() else str(v)
    return str(v or "").strip()


async def _client_codes(db: AsyncSession, project_id: UUID) -> list[str]:
    rows = (await db.execute(sa.select(AccountChart.account_code).where(
        AccountChart.project_id == project_id,
        AccountChart.source == AccountSource.client,
        AccountChart.is_deleted == sa.false(),
    ))).scalars().all()
    return [r for r in rows if r]


async def resolve_format(db: AsyncSession, project_id: UUID, year: int) -> dict:
    code = await standard_code(db, project_id, year)
    if code.startswith("3"):
        return {"format": FORMAT_SYSTEM, "code": code, "source": "tax_return", "notice": None}
    if code.startswith("1"):
        return {"format": FORMAT_CAS, "code": code, "source": "tax_return", "notice": None}
    if code:
        return {"format": None, "code": code, "source": "tax_return",
                "notice": f"A000000 第 107 项会计准则代码为 {code}，暂只支持企业会计准则（1xx）与企业会计制度（300）格式"}
    detected = detect_legacy_pl_crosswalk(await _client_codes(db, project_id))
    fmt = FORMAT_SYSTEM if detected and detected[0] == ENTERPRISE_SYSTEM_2001 else FORMAT_CAS
    return {
        "format": fmt, "code": "", "source": "chart",
        "notice": (f"申报表 A000000 第 107 项（适用会计准则或会计制度）未填写，按客户科目编码暂按「{FORMAT_LABELS[fmt]}」格式显示；"
                   "请在「税审底稿 → 1-12 企业基础信息表」填写（申报表取自该表）"),
    }


# ── 企业会计制度 ──
def balances_of(view: list[dict]) -> tuple[dict[str, Decimal], dict[str, Decimal], Decimal]:
    """标准科目余额视图 → (期末借正贷负, 期初借正贷负, 损益科目未结转余额)。

    期末取平台审定数（自然正数按方向转借正贷负，与底稿取数同一列）；没有审定数时取调整后期末。
    损益科目：审定数是本期发生额，期末另取调整后期末（年末结转后为 0，未结转 / 有审计调整时进未分配利润）。
    """
    closing: dict[str, Decimal] = {}
    opening: dict[str, Decimal] = {}
    pl_close = _ZERO
    for r in view:
        code = r["standard_account_code"]
        sign = Decimal(-1) if r["direction"] == "credit" else Decimal(1)
        audited = r.get("audited_amount")
        closing[code] = _d(audited) * sign if audited is not None else _d(r.get("adjusted_closing_balance"))
        opening[code] = _d(r.get("opening_balance"))
        if is_pl_code(code):
            pl_close += _d(r.get("adjusted_closing_balance"))
    return closing, opening, pl_close


async def _platform_report(db: AsyncSession, project_id: UUID, year: int, report_type: FinancialReportType) -> list[FinancialReport]:
    return list((await db.execute(sa.select(FinancialReport).where(
        FinancialReport.project_id == project_id,
        FinancialReport.year == year,
        FinancialReport.report_type == report_type,
        FinancialReport.is_deleted == sa.false(),
    ).order_by(FinancialReport.row_code))).scalars().all())


def _generated(rows: list[FinancialReport]) -> bool:
    return any(r.current_period_amount is not None or r.prior_period_amount is not None for r in rows)


async def _cf_values(db: AsyncSession, project_id: UUID, year: int) -> tuple[dict[str, Decimal], dict[str, Decimal], bool]:
    cur: dict[str, Decimal] = {}
    prior: dict[str, Decimal] = {}
    any_generated = False
    for rt in (FinancialReportType.cash_flow_statement, FinancialReportType.cash_flow_supplement):
        rows = await _platform_report(db, project_id, year, rt)
        any_generated = any_generated or _generated(rows)
        for r in rows:
            name = normalize_name(r.row_name)
            if r.current_period_amount is not None:
                cur[name] = cur.get(name, _ZERO) + _d(r.current_period_amount)
            if r.prior_period_amount is not None:
                prior[name] = prior.get(name, _ZERO) + _d(r.prior_period_amount)
    return cur, prior, any_generated


def _rows_out(stmt: dict, cur: dict[int, Decimal | None], prior: dict[int, Decimal | None]) -> list[dict]:
    out = []
    for row in stmt["rows"]:
        r = row["r"]
        out.append({
            "r": r,
            "label": row["label"],
            "indent": row.get("indent", 0),
            "heading": bool(row.get("heading")),
            "total": bool(row.get("total")),
            "note": row.get("note"),
            "current": tws.encode_value(cur.get(r)),
            "prior": tws.encode_value(prior.get(r)),
        })
    return out


async def build_enterprise_system(db: AsyncSession, project_id: UUID, year: int, view: list[dict]) -> dict:
    closing, opening, pl_close = balances_of(view)
    notices: list[str] = []
    prior_src = await resolve_prior_source(db, project_id, year)
    prior_closing = None
    if prior_src.project_id is not None:
        prior_view = await build_standard_balance_view(db, prior_src.project_id, prior_src.year)
        prior_closing = balances_of(prior_view)[0] if prior_view else None
    if prior_closing is None:
        notices.append(f"利润表上期金额为空：{prior_src.reason or '上年试算表没有数据'}")
    cf_cur, cf_prior, cf_generated = await _cf_values(db, project_id, year)
    if not cf_generated:
        notices.append("现金流量表取平台已生成的现金流量表，尚未生成；请先在「审定报表」生成报表（现金流量表需编制现金流量表底稿）")

    statements = []
    values: dict[str, tuple[dict, dict]] = {}
    for stmt in load_config()["statements"]:
        if stmt["side"] == "cash":
            from_cur = {k: v[0] for k, v in values.items()}
            from_prior = {k: v[1] for k, v in values.items()}
            cur = compute_statement(stmt, None, cf_values=cf_cur if cf_generated else None, from_values=from_cur)
            prior = compute_statement(stmt, None, cf_values=cf_prior if cf_generated else None, from_values=from_prior)
        elif stmt["period"] == "date":
            cur = compute_statement(stmt, closing, pl_close)
            # 上年年末 = 本年试算表期初；期初已结转，损益科目未结转余额按 0
            prior = compute_statement(stmt, opening, _ZERO)
        else:
            cur = compute_statement(stmt, closing)
            prior = compute_statement(stmt, prior_closing)
        values[stmt["key"]] = (cur, prior)
        statements.append({
            "key": stmt["key"], "title": stmt["title"], "attachment": stmt.get("attachment"),
            "columns": stmt["columns"], "rows": _rows_out(stmt, cur, prior),
        })
    return {"statements": statements, "notices": notices, "checks": _checks(values)}


def _checks(values: dict[str, tuple[dict, dict]]) -> list[dict]:
    """资产总计 = 负债和所有者权益总计（期末 / 上年年末）。"""
    assets, liab = values.get("balance_sheet"), values.get("balance_sheet_liabilities")
    if not assets or not liab:
        return []
    out = []
    for i, label in ((0, "期末"), (1, "上年年末")):
        a = assets[i].get(47) or _ZERO
        b = liab[i].get(46) or _ZERO
        out.append({"label": f"{label}资产总计 − 负债和所有者权益总计", "difference": tws.encode_value(a - b), "ok": abs(a - b) < Decimal("0.005")})
    return out


# ── 企业会计准则：平台审定报表 ──
async def build_cas(db: AsyncSession, project_id: UUID, year: int) -> dict:
    statements = []
    missing = []
    for rt, title, columns in _CAS_REPORTS:
        rows = await _platform_report(db, project_id, year, rt)
        if not _generated(rows):
            missing.append(title)
        statements.append({
            "key": rt.value, "title": title, "attachment": None, "columns": columns,
            "rows": [{
                "r": i + 1,
                "label": r.row_name or "",
                "indent": r.indent_level or 0,
                "heading": False,
                "total": bool(r.is_total_row),
                "note": None,
                "current": tws.encode_value(r.current_period_amount),
                "prior": tws.encode_value(r.prior_period_amount),
            } for i, r in enumerate(rows)],
        })
    notices = [f"{'、'.join(missing)}尚未生成，请先在「审定报表」生成报表"] if missing else []
    return {"statements": statements, "notices": notices, "checks": []}


async def build(db: AsyncSession, project_id: UUID, year: int, scope_codes: set[str] | None = None) -> dict:
    """``scope_codes``：受限成员可见的标准科目（与试算平衡表页同口径）；None = 不限。"""
    project = await db.get(Project, project_id)
    # 立即取成普通值：之后的取数查询失败时 get_active_filter 会 rollback，ORM 对象过期后再访问会触发懒加载报错
    entity_name = (project.client_name or project.name) if project else ""
    chosen = await resolve_format(db, project_id, year)
    base = {
        "year": year,
        "entity_name": entity_name,
        "format": chosen["format"],
        "format_label": FORMAT_LABELS.get(chosen["format"] or "", ""),
        "standard_code": chosen["code"],
        "format_source": chosen["source"],
    }
    notices = [chosen["notice"]] if chosen["notice"] else []
    if chosen["format"] == FORMAT_SYSTEM:
        view = await build_standard_balance_view(db, project_id, year)
        if scope_codes is not None:
            view = [r for r in view if r["standard_account_code"] in scope_codes]
            notices.append("你只能看到分配给你的审计循环的科目，报表数可能不完整")
        if not view:
            notices.append(f"{year} 年度还没有试算表数据，请先导入账套并重算试算表")
        body = await build_enterprise_system(db, project_id, year, view)
    elif chosen["format"] == FORMAT_CAS:
        body = await build_cas(db, project_id, year)
    else:
        body = {"statements": [], "notices": [], "checks": []}
    return {**base, **body, "notices": notices + body["notices"]}
