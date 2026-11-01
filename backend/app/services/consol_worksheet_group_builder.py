"""从服务端已保存的合并工作表构造 canonical 草稿分录分组。"""
from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app.models.consolidation_schemas import WorksheetSourceGroup, WorksheetSourceLine
from app.services.consol_tree_service import TreeNode

ORIGIN_SHEETS: dict[str, str] = {
    "ws_equity_sim": "equity_sim",
    "ws_internal_arap": "internal_arap",
    "ws_internal_trade": "internal_trade",
}
SHEET_ORIGINS = {sheet: origin for origin, sheet in ORIGIN_SHEETS.items()}
SOURCE_SHEETS = tuple(SHEET_ORIGINS)
_ZERO = Decimal("0")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return _ZERO
    try:
        number = Decimal(str(value).replace(",", "").replace("，", "").replace(" ", ""))
        return number if number.is_finite() else _ZERO
    except (InvalidOperation, ValueError):
        return _ZERO


def _amount(value: Decimal) -> Decimal:
    return value.normalize() if value else _ZERO


def _nonzero(value: Decimal) -> bool:
    return value.quantize(Decimal("0.01")) != 0


def _values(row: dict[str, Any], key: str) -> list[Any]:
    value = row.get(key)
    return value if isinstance(value, list) else []


def _sum(values: Iterable[Any]) -> Decimal:
    return sum((_decimal(value) for value in values), _ZERO)


def _codes(values: Iterable[str | None]) -> list[str]:
    return sorted({_text(value) for value in values if _text(value)})


def _companies(tree: TreeNode, info_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_code = {_text(row.get("company_code")): row for row in info_rows if _text(row.get("company_code"))}
    companies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for child in tree.children or []:
        if child.role not in {"subsidiary", "consol"}:
            continue
        code = _text(child.company_code)
        if not code or code in seen:
            continue
        seen.add(code)
        row = by_code.get(code, {})
        ratio = (
            row.get("non_common_ratio") or row.get("common_ratio")
            or row.get("no_consol_ratio") or 0
        )
        companies.append({
            "name": child.company_name or code,
            "code": code,
            "ratio": _decimal(ratio),
        })
    return companies


def _code_of(companies: list[dict[str, Any]], root_code: str, name: Any) -> str | None:
    wanted = _text(name)
    if not wanted:
        return None
    if wanted == "母公司":
        return root_code or None
    return next((item["code"] for item in companies if item["name"] == wanted), None)


def _line(subject: Any, detail: Any, direction: Any, amount: Decimal) -> WorksheetSourceLine:
    return WorksheetSourceLine(
        subject=_text(subject), detail=_text(detail) or None,
        direction=_text(direction), amount=_amount(amount),
    )


def equity_groups(
    rows: list[dict[str, Any]], companies: list[dict[str, Any]], root_code: str,
) -> list[WorksheetSourceGroup]:
    steps = (
        (1, "期初长投模拟", "期初模拟"),
        (2, "模拟当期长期股权投资", "当期模拟"),
        (3, "还原分红影响", "还原分红"),
    )
    groups: list[WorksheetSourceGroup] = []
    for number, title, label in steps:
        start = next((i for i, row in enumerate(rows) if row.get("isStep") and _text(row.get("step")) == title), -1)
        if start < 0:
            continue
        body: list[dict[str, Any]] = []
        for row in rows[start + 1:]:
            if row.get("isStep"):
                break
            body.append(row)
        for index, company in enumerate(companies):
            lines = [
                _line(row.get("subject"), row.get("detail"), row.get("direction"), amount)
                for row in body
                if _nonzero(amount := _decimal((_values(row, "values") + [None] * (index + 1))[index]))
            ]
            if not lines:
                continue
            groups.append(WorksheetSourceGroup(
                origin="ws_equity_sim",
                origin_key=f"equity_sim:step{number}:{company['code'] or '名称:' + company['name']}",
                description=f"模拟权益法·{label}：{company['name'] or company['code']}",
                lines=lines,
                related_company_codes=_codes((root_code, company["code"])),
            ))
    return groups


def _arap_pairs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in rows:
        local_subject, remote_subject = _text(row.get("localSubject")), _text(row.get("remoteSubject"))
        if not local_subject and not remote_subject:
            continue
        key = f"{local_subject}|{remote_subject}"
        pair = pairs.setdefault(key, {
            "localSubject": local_subject, "remoteSubject": remote_subject,
            "local": _ZERO, "remote": _ZERO, "localImp": _ZERO, "remoteImp": _ZERO,
            "companies": [],
        })
        pair["local"] += _sum(_values(row, "localAmounts"))
        pair["remote"] += _sum(_values(row, "remoteAmounts"))
        pair["localImp"] += _sum(_values(row, "localImpairments"))
        pair["remoteImp"] += _sum(_values(row, "remoteImpairments"))
        for company in (_text(row.get("localCompany")), _text(row.get("remoteCompany"))):
            if company and company not in pair["companies"]:
                pair["companies"].append(company)
    return list(pairs.values())


def _arap_sides(pair: dict[str, Any]) -> tuple[str, str]:
    local = pair["localSubject"] or pair["remoteSubject"]
    remote = pair["remoteSubject"] or pair["localSubject"]
    liability = lambda value: any(word in value for word in ("应付", "预收", "合同负债"))
    asset = lambda value: any(word in value for word in ("应收", "预付", "合同资产"))
    if asset(local) and liability(remote):
        return remote, local
    return local, remote


def arap_groups(
    rows: list[dict[str, Any]], companies: list[dict[str, Any]], root_code: str,
) -> list[WorksheetSourceGroup]:
    groups: list[WorksheetSourceGroup] = []
    for pair in _arap_pairs(rows):
        key = f"{pair['localSubject']}|{pair['remoteSubject']}"
        related = _codes(_code_of(companies, root_code, name) for name in pair["companies"])
        amount = min(pair["local"], pair["remote"])
        if amount > 0 and _nonzero(amount):
            debit, credit = _arap_sides(pair)
            groups.append(WorksheetSourceGroup(
                origin="ws_internal_arap", origin_key=f"internal_arap:pair:{key}",
                description=f"内部往来抵销：{debit} ↔ {credit}",
                lines=[_line(debit, None, "借", amount), _line(credit, None, "贷", amount)],
                related_company_codes=related,
            ))
        for side, impairment, subject in (
            ("local", pair["localImp"], pair["localSubject"]),
            ("remote", pair["remoteImp"], pair["remoteSubject"]),
        ):
            if impairment <= 0 or not _nonzero(impairment):
                continue
            groups.append(WorksheetSourceGroup(
                origin="ws_internal_arap",
                origin_key=f"internal_arap:bad_debt_{side}:{key}",
                description=f"冲回{'本方' if side == 'local' else '对方'}内部往来坏账准备（{subject or '未填科目'}）",
                lines=[
                    _line("坏账准备", None, "借", impairment),
                    _line("信用减值损失", None, "贷", impairment),
                ],
                related_company_codes=related,
            ))
    return groups


def trade_groups(
    rows: list[dict[str, Any]], companies: list[dict[str, Any]], root_code: str,
) -> list[WorksheetSourceGroup]:
    revenue = cost = unrealized = _ZERO
    names: list[str] = []
    for row in rows:
        seller, buyer = _text(row.get("sellerCompany")), _text(row.get("buyerCompany"))
        if not seller or not buyer:
            continue
        revenue += _decimal(row.get("sellerAmount"))
        cost += _decimal(row.get("buyerAmount"))
        unrealized += _decimal(row.get("unrealizedProfit")) * _decimal(row.get("inventoryRatio")) / 100
        for name in (seller, buyer):
            if name not in names:
                names.append(name)
    related = _codes(_code_of(companies, root_code, name) for name in names)
    groups: list[WorksheetSourceGroup] = []
    amount = min(revenue, cost)
    if amount > 0 and _nonzero(amount):
        groups.append(WorksheetSourceGroup(
            origin="ws_internal_trade", origin_key="internal_trade:revenue",
            description="内部交易收入与成本抵销",
            lines=[_line("营业收入", None, "借", amount), _line("营业成本", None, "贷", amount)],
            related_company_codes=related,
        ))
    if unrealized > 0 and _nonzero(unrealized):
        groups.append(WorksheetSourceGroup(
            origin="ws_internal_trade", origin_key="internal_trade:unrealized",
            description="存货中未实现内部利润抵销", entry_type="unrealized_profit",
            lines=[_line("营业成本", None, "借", unrealized), _line("存货", None, "贷", unrealized)],
            related_company_codes=related,
        ))
    return groups


def build_groups_from_worksheet(
    contents: dict[str, dict[str, Any]],
    tree: TreeNode,
) -> tuple[list[WorksheetSourceGroup], list[str], dict[str, Any]]:
    """纯函数：工作表内容 → canonical groups、负责来源和摘要。"""
    info_rows = (contents.get("info") or {}).get("rows") or []
    info_rows = [row for row in info_rows if isinstance(row, dict)]
    companies = _companies(tree, info_rows)
    root_code = _text(tree.company_code)
    equity_content = contents.get("equity_sim") or {}
    equity_rows_raw = equity_content.get("rows") or {}
    equity_rows = (
        equity_rows_raw.get("direct") or [] if isinstance(equity_rows_raw, dict)
        else equity_rows_raw if isinstance(equity_rows_raw, list) else []
    )
    arap_rows = (contents.get("internal_arap") or {}).get("rows") or []
    trade_rows = (contents.get("internal_trade") or {}).get("rows") or []
    by_origin = {
        "ws_equity_sim": equity_groups(
            [row for row in equity_rows if isinstance(row, dict)], companies, root_code,
        ),
        "ws_internal_arap": arap_groups(
            [row for row in arap_rows if isinstance(row, dict)], companies, root_code,
        ),
        "ws_internal_trade": trade_groups(
            [row for row in trade_rows if isinstance(row, dict)], companies, root_code,
        ),
    }
    origins = [
        origin for origin, sheet in ORIGIN_SHEETS.items()
        if sheet in contents or bool(by_origin[origin])
    ]
    groups = [group for origin in ORIGIN_SHEETS for group in by_origin[origin]]
    summary = {
        "company_count": len(companies),
        "group_count": len(groups),
        "groups_by_origin": {origin: len(items) for origin, items in by_origin.items()},
    }
    return groups, origins, summary
