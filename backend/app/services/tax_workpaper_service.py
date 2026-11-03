"""税审底稿：按项目取数 + 公式计算 + 手工值保存（spec tax-workpaper-data-fetch）。

- ``compute_sheet``：读本项目本年度全部手工值与表头参数 → 求本表打印区依赖到的取数格
  （``tax_workpaper_rule_runner``）与公式格（``tax_workbook``）→ 返回本表各段的值与来源说明。
- ``save_sheet_inputs`` / ``save_params``：带版本号保存，版本不一致抛 409；service 只 flush，由 router commit。
- ``account_workpaper_map``：客户科目 → 取数规则实际用到它的税审底稿（底稿映射页，spec citar-account-workpaper-map）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import AccountChart, AccountSource
from app.models.core import Project
from app.models.tax_workpaper_models import PARAMS_SHEET_CODE, RESERVED_SHEET_CODES, TaxWorkpaperInput
from app.services.tax_formula_engine import XlError, number_text
from app.services.tax_workbook import Key, TaxWorkbook, json_to_value, load_workbook, parse_a1, to_a1
from app.services.tax_workpaper_fetch import AccountBook, load_account_book
from app.services.tax_workpaper_rule_runner import RuleResult, RuleRunner

MAX_TEXT = 2000
MAX_REFS = 5000


def encode_value(v: Any) -> dict | None:
    """值 → 接口格式：{"n": "123.45"} 数字 / {"s": 文字} / {"b": true} / {"e": "#DIV/0!"}；空格 None。"""
    if v is None:
        return None
    if isinstance(v, XlError):
        return {"e": str(v)}
    if isinstance(v, bool):
        return {"b": v}
    if isinstance(v, Decimal):
        q = v.quantize(Decimal("0.0000000001")) if v.as_tuple().exponent < -10 else v
        return {"n": number_text(q)}
    return {"s": str(v)}


# ── 读写存储 ──
async def _rows(db: AsyncSession, project_id: UUID, year: int) -> dict[str, TaxWorkpaperInput]:
    # populate_existing：保存后（commit / onupdate 使 updated_at 过期）同一会话再读，
    # 不重新加载会在访问属性时触发懒加载，异步会话下报 MissingGreenlet
    rows = (await db.execute(
        sa.select(TaxWorkpaperInput)
        .where(TaxWorkpaperInput.project_id == project_id, TaxWorkpaperInput.year == year)
        .execution_options(populate_existing=True)
    )).scalars().all()
    return {r.sheet_code: r for r in rows}


def _merge_inputs(rows: dict[str, TaxWorkpaperInput]) -> dict[Key, Any]:
    out: dict[Key, Any] = {}
    for code, row in rows.items():
        if code in RESERVED_SHEET_CODES:
            continue
        for sheet, cells in (row.inputs or {}).items():
            for ref, raw in cells.items():
                out[(sheet, *parse_a1(ref))] = json_to_value(raw)
    return out


async def _project(db: AsyncSession, project_id: UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def param_defaults(project: Project, year: int) -> dict[str, str | None]:
    return {
        "client_name": project.client_name or project.name,
        "legal_representative": getattr(project, "legal_representative", None),
        "period": f"{year}年度",
    }


def _param_values(wb: TaxWorkbook, project: Project, year: int, row: TaxWorkpaperInput | None) -> list[dict]:
    defaults = param_defaults(project, year)
    saved = (row.inputs or {}).get(wb.model["params_sheet"], {}) if row else {}
    out = []
    for p in wb.model["params"]:
        default = defaults.get(p["default"]) if p["default"] else None
        value = saved[p["ref"]] if p["ref"] in saved else default
        out.append({**p, "default_value": default, "value": value, "saved": p["ref"] in saved})
    return out


# ── 计算 ──
class Evaluation:
    """一次求值的结果：手工值、取数值（含来源说明）、公式值；``value`` 按格取最终值。"""

    def __init__(self, wb: TaxWorkbook, inputs: dict[Key, Any], rule_values: dict[Key, Any],
                 results_meta: dict[Key, RuleResult], computed: dict[Key, Any], notices: list[str]) -> None:
        self.wb = wb
        self.inputs = inputs
        self.rule_values = rule_values
        self.results_meta = results_meta
        self.computed = computed
        self.notices = notices

    def value(self, sheet: str, ref: str) -> Any:
        """显示值（只引用一个空格的公式为空白）。"""
        return self.wb.cell_value((sheet, *parse_a1(ref)), self.inputs, self.rule_values, self.computed)

    def calc_value(self, sheet: str, ref: str) -> Any:
        """计算值（与 Excel 一致：引用空格的公式得 0）；审核说明的占位用它，「账载金额{0}元」不会成「账载金额元」。"""
        key = (sheet, *parse_a1(ref))
        if key in self.wb.formulas:
            return self.computed.get(key)
        return self.value(sheet, ref)


async def _prepare_inputs(db: AsyncSession, wb: TaxWorkbook, project_id: UUID, year: int, rows: dict | None) -> dict[Key, Any]:
    """本项目本年度全部手工值 + 表头参数（取数、公式、底稿映射页共用同一份）。"""
    project = await _project(db, project_id)
    if rows is None:
        rows = await _rows(db, project_id, year)
    inputs = _merge_inputs(rows)
    params_sheet = wb.model["params_sheet"]
    for p in _param_values(wb, project, year, rows.get(PARAMS_SHEET_CODE)):
        if p["value"] not in (None, ""):
            inputs[(params_sheet, *parse_a1(p["ref"]))] = json_to_value(p["value"])
    return inputs


def _make_runner(wb: TaxWorkbook, book: AccountBook, inputs: dict[Key, Any]) -> RuleRunner:
    """取数执行器；行标签（本行科目名）依次读手工值、名称列取数结果、样表常量。"""

    def label_text(sheet: str, ref: str) -> str | None:
        key = (sheet, *parse_a1(ref))
        if key in inputs:
            v = inputs[key]
            return str(v).strip() if v not in (None, "") else None
        if key in wb.rules:
            r = runner.run(wb.rules[key])
            return str(r.value).strip() if r.value not in (None, "") else None
        v = wb.consts.get(key)
        return str(v).strip() if v not in (None, "") else None

    runner = RuleRunner(book, wb.model["lists"], label_text)
    return runner


async def evaluate_keys(db: AsyncSession, project_id: UUID, year: int, seeds: list[Key], rows: dict | None = None) -> Evaluation:
    """求 ``seeds`` 及其依赖：读本项目本年度全部手工值与表头参数 → 取数 → 公式。

    ``rows``：调用方已读的手工值行（省一次查询）。
    """
    wb = load_workbook()
    inputs = await _prepare_inputs(db, wb, project_id, year, rows)

    needed = wb.closure(seeds)
    rule_keys = [k for k in needed if k in wb.rules]
    results_meta: dict[Key, RuleResult] = {}
    rule_values: dict[Key, Any] = {}
    notices: list[str] = []
    if rule_keys:
        with_ledger = any(wb.rules[k]["op"] == "month" for k in rule_keys)
        book = await load_account_book(db, project_id, year, with_ledger=with_ledger)
        if book.empty:
            notices.append(f"{year} 年度尚未导入科目余额表，取数格为空")
        runner = _make_runner(wb, book, inputs)
        # 名称列先算（金额按名称找明细）
        for key in sorted(rule_keys, key=lambda k: 0 if wb.rules[k]["op"] == "list_name" else 1):
            res = runner.run(wb.rules[key])
            results_meta[key] = res
            rule_values[key] = res.value

    computed = wb.evaluate(needed, inputs, rule_values)
    return Evaluation(wb, inputs, rule_values, results_meta, computed, notices)


WORKPAPER_DOMAIN = "workpaper"


def code_domain(wb: TaxWorkbook, code: str) -> str | None:
    """编号属于哪一类：``workpaper`` 税审底稿 / ``tax_return`` 汇算申报表 / ``review_notes`` 审核说明；不存在 None。"""
    if not wb.sheets_of(code):
        return None
    for domain, codes in (wb.model.get("groups") or {}).items():
        if code in codes:
            return domain
    return WORKPAPER_DOMAIN


def _sheets_in_domain(wb: TaxWorkbook, code: str, domain: str) -> list[str]:
    if code_domain(wb, code) != domain:
        label = {"workpaper": "底稿编号", "tax_return": "申报表编号"}.get(domain, "编号")
        raise HTTPException(status_code=404, detail=f"{label} {code} 不存在")
    return wb.sheets_of(code)


async def compute_sheet(db: AsyncSession, project_id: UUID, year: int, code: str, domain: str = WORKPAPER_DOMAIN) -> dict:
    wb = load_workbook()
    sheets = _sheets_in_domain(wb, code, domain)
    await _project(db, project_id)
    rows = await _rows(db, project_id, year)
    # 版本 / 时间立即取成普通值：之后的取数查询失败时 get_active_filter 会 rollback，
    # 会话里的 ORM 对象全部过期，再访问属性会在异步会话里触发懒加载报错
    own = rows.get(code)
    version = own.version if own else 0
    updated_at = own.updated_at.isoformat() if own and own.updated_at else None
    ev = await evaluate_keys(db, project_id, year, [k for s in sheets for k in wb.print_keys(s)], rows)
    inputs, rule_values, computed, results_meta, notices = ev.inputs, ev.rule_values, ev.computed, ev.results_meta, ev.notices

    parts = []
    issues = []
    for sheet in sheets:
        values: dict[str, Any] = {}
        cells: dict[str, dict] = {}
        for key in wb.print_keys(sheet):
            ref = to_a1(key[1], key[2])
            values[ref] = encode_value(wb.cell_value(key, inputs, rule_values, computed))
            meta = results_meta.get(key)
            if meta is not None:
                cell = {"origin": "rule", "status": meta.status, "rule": meta.rule}
                if meta.issue:
                    cell["issue"] = meta.issue
                    issues.append({"sheet": sheet, "ref": ref, "message": meta.issue})
                if key in inputs:
                    cell["origin"] = "input"
                    cell["auto"] = encode_value(meta.value)
                cells[ref] = cell
        for key, v in inputs.items():
            if key[0] == sheet and key not in wb.formulas:
                ref = to_a1(key[1], key[2])
                values[ref] = encode_value(v)
                cells.setdefault(ref, {"origin": "input"})
        parts.append({"source": sheet, "values": values, "cells": cells})

    return {
        "code": code,
        "year": year,
        "version": version,
        "updated_at": updated_at,
        "parts": parts,
        "issues": issues,
        "notices": notices,
    }


# ── 科目 → 税审底稿 ──
MAX_PENDING_REASONS = 3


async def account_workpaper_map(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """逐条跑税审底稿的取数规则（与取数同一执行器），记下每张底稿用到的客户科目。

    - ``workpapers``：取数实际用到本科目、或其上级 / 下级的底稿（上级的数含下级，下级的数被上级合计取走）；
    - ``pending``：规则的一级科目指向本科目（或其上级 / 下级），但没取到数的底稿，``reasons`` 为取不到的原因
      （只在规则直接指向的那一级给出）；已在 ``workpapers`` 里的不重复列。
    需人工填写的规则不算；没读序时账（按月规则）照样能反查到科目。
    """
    wb = load_workbook()
    inputs = await _prepare_inputs(db, wb, project_id, year, None)
    book = await load_account_book(db, project_id, year, with_ledger=False)
    notices: list[str] = []
    if book.empty:
        notices.append(f"{year} 年度尚未导入科目余额表")

    sheet_code = {s: c for c, sheets in wb.codes.items() for s in sheets if code_domain(wb, c) == WORKPAPER_DOMAIN}
    direct: dict[str, set[str]] = {}
    pending_direct: dict[str, dict[str, list[str]]] = {}  # 科目 → 底稿 → 原因
    if not book.empty:
        runner = _make_runner(wb, book, inputs)
        for item in wb.model["rules"]:
            code = sheet_code.get(item["sheet"])
            if code is None:
                continue
            # manual 规则不取数，执行器返回的 nodes / scope 都为空，这里不另判
            res = runner.run(item)
            for node in res.nodes:
                direct.setdefault(node.code, set()).add(code)
            for node in res.scope:
                reasons = pending_direct.setdefault(node.code, {}).setdefault(code, [])
                if res.issue not in reasons and len(reasons) < MAX_PENDING_REASONS:
                    reasons.append(res.issue)

    def spread(seed: dict[str, set[str]]) -> dict[str, set[str]]:
        """本身 ∪ 全部上级 ∪ 全部下级。"""
        up: dict[str, set[str]] = {}
        for node in sorted(book.nodes.values(), key=lambda n: len(n.code)):  # 上级编码更短，先算
            up[node.code] = seed.get(node.code, set()) | (up[node.parent] if node.parent else set())
        down: dict[str, set[str]] = {}
        for node in sorted(book.nodes.values(), key=lambda n: -len(n.code)):
            down[node.code] = seed.get(node.code, set()).union(*(down[c] for c in node.children))
        return {c: up[c] | down[c] for c in book.nodes}

    fetched = spread(direct)
    pointed = spread({c: set(sheets) for c, sheets in pending_direct.items()})

    std_names = dict((await db.execute(
        sa.select(AccountChart.account_code, AccountChart.account_name).where(
            AccountChart.project_id == project_id,
            AccountChart.source == AccountSource.standard,
            AccountChart.is_deleted == sa.false(),
        )
    )).all())

    def reasons_of(node_code: str, sheet: str) -> list[str]:
        """规则直接指向本科目或最近上级时的原因；只因下级被指向的不给原因。"""
        cur: str | None = node_code
        while cur:
            hit = pending_direct.get(cur, {}).get(sheet)
            if hit:
                return hit
            cur = book.nodes[cur].parent
        return []

    accounts = []
    for node in sorted(book.nodes.values(), key=lambda n: n.code):
        sheets = fetched[node.code]
        pending = [{"code": c, "reasons": reasons_of(node.code, c)} for c in sorted(pointed[node.code] - sheets)]
        accounts.append({
            "code": node.code,
            "name": node.name,
            "level": book.depth(node) + 1,
            "parent": node.parent,
            "standard_code": node.standard,
            "standard_name": std_names.get(node.standard) if node.standard else None,
            "debit": number_text(node.debit),
            "credit": number_text(node.credit),
            "closing": number_text(node.closing),
            "has_activity": book.has_activity(node),
            "workpapers": sorted(sheets),
            "direct": sorted(direct.get(node.code, ())),
            "pending": pending,
        })
    return {"year": year, "accounts": accounts, "notices": notices}


# ── 保存 ──
def _validate_value(v: Any) -> Any:
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        if len(v) > MAX_TEXT:
            raise HTTPException(status_code=422, detail=f"文字超过 {MAX_TEXT} 字")
        return v
    raise HTTPException(status_code=422, detail="单元格值只能是数字、文字或空")


async def _upsert(db: AsyncSession, project_id: UUID, year: int, code: str, version: int, inputs: dict, user_id: UUID) -> TaxWorkpaperInput:
    row = (await db.execute(
        sa.select(TaxWorkpaperInput).where(
            TaxWorkpaperInput.project_id == project_id, TaxWorkpaperInput.year == year,
            TaxWorkpaperInput.sheet_code == code,
        ).with_for_update()
    )).scalar_one_or_none()
    current = row.version if row else 0
    if version != current:
        raise HTTPException(status_code=409, detail="底稿已被他人修改，请刷新后再保存")
    if row is None:
        row = TaxWorkpaperInput(project_id=project_id, year=year, sheet_code=code, inputs=inputs, version=1, updated_by=user_id)
        db.add(row)
    else:
        row.inputs = inputs
        row.version = current + 1
        row.updated_by = user_id
    await db.flush()
    return row


async def save_sheet_inputs(
    db: AsyncSession, project_id: UUID, year: int, code: str, version: int, inputs: dict, user_id: UUID,
    domain: str = WORKPAPER_DOMAIN,
) -> None:
    wb = load_workbook()
    sheets = _sheets_in_domain(wb, code, domain)
    if code in (wb.model.get("readonly_codes") or []):
        raise HTTPException(status_code=422, detail=f"{code} 不能填写")
    await _project(db, project_id)
    clean: dict[str, dict[str, Any]] = {}
    total = 0
    for sheet, cells in (inputs or {}).items():
        if sheet not in sheets:
            raise HTTPException(status_code=422, detail=f"{sheet} 不属于底稿 {code}")
        area = wb.print_areas.get(sheet)
        for ref, raw in (cells or {}).items():
            try:
                row, col = parse_a1(ref)
            except ValueError:
                raise HTTPException(status_code=422, detail=f"单元格地址无效：{ref}") from None
            if area and not (area[0] <= row <= area[2] and area[1] <= col <= area[3]):
                raise HTTPException(status_code=422, detail=f"{ref} 不在底稿范围内")
            if (sheet, row, col) in wb.formulas:
                raise HTTPException(status_code=422, detail=f"{ref} 是公式格，不能填写")
            clean.setdefault(sheet, {})[to_a1(row, col)] = _validate_value(raw)
            total += 1
    if total > MAX_REFS:
        raise HTTPException(status_code=422, detail="填写的单元格过多")
    await _upsert(db, project_id, year, code, version, clean, user_id)


async def get_params(db: AsyncSession, project_id: UUID, year: int) -> dict:
    wb = load_workbook()
    project = await _project(db, project_id)
    row = (await _rows(db, project_id, year)).get(PARAMS_SHEET_CODE)
    return {"year": year, "version": row.version if row else 0, "params": _param_values(wb, project, year, row)}


async def save_params(db: AsyncSession, project_id: UUID, year: int, version: int, values: dict, user_id: UUID) -> None:
    wb = load_workbook()
    await _project(db, project_id)
    allowed = {p["ref"] for p in wb.model["params"]}
    clean = {}
    for ref, raw in (values or {}).items():
        if ref not in allowed:
            raise HTTPException(status_code=422, detail=f"未知参数 {ref}")
        clean[ref] = _validate_value(raw)
    await _upsert(db, project_id, year, PARAMS_SHEET_CODE, version, {wb.model["params_sheet"]: clean}, user_id)
