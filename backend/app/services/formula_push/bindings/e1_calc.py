"""E1 货币资金公式推送的纯计算（无 DB / IO），逐式复刻前端。

spec: chain-closure-phase2-formula-push-engine · design §四 · 任务 7 / 8

每个函数都对应一个前端真源（函数 docstring 标出文件与函数名）。**两侧同式由双侧夹具守卫**：
vitest 以真 composable / 纯函数产出 ``backend/tests/fixtures/formula_push_e1_parity.json``，
pytest 以同一夹具断言本模块逐值相等 —— 任一侧改算式另一侧必红。

数值语义一律走 :mod:`app.services.formula_push.js_compat`（``parseNum`` / ``Number`` /
``String(number)``），运算顺序与前端一致（``reduce`` 从 0 起逐项相加），以保证浮点逐位相同。

派生函数返回 ``float``（写该值）、``None``（目标应为空，如语义槽三值全 0）或
:class:`Unavailable`（无从计算，不动目标）。
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple

from app.services.formula_push.js_compat import (
    js_json_number,
    js_number,
    js_or_zero,
    parse_num,
    read_number,
)

# ── 持久化键 ─────────────────────────────────────────────────────────────────
CASH_ROWS_KEY = "E1-cash-detail-rows"
BANK_ROWS_KEY = "E1-bank-detail-rows"
BANK_VARIANT_KEY = "E1-bank-variant"
ACCRUED_ROWS_KEY = "E1-accrued-interest-rows"
CASH_TOTAL_KEYS = {"opening": "E1-cash-detail-opening-unaudited", "ending": "E1-cash-detail-total-unaudited"}
BANK_GROUPS: tuple[str, ...] = ("principal", "institution", "finance", "other")
DIGITAL_TOTAL_KEYS = {"opening": "E1-digital-opening-unaudited", "ending": "E1-digital-total-unaudited"}
#: 大厅已确认调整只进这三行的期末（ADR-PUSH-001）
HALL_ADJ_ITEM_KEYS: tuple[str, ...] = ("cash", "bank_principal", "other_mf")
BANK_VARIANTS: tuple[str, ...] = ("rmb", "multi")
#: E1-3 variant 缺省值 —— 与宿主 `e13Variant`（sheet 名不含「仅人民币」即 multi）一致
DEFAULT_BANK_VARIANT = "multi"

PERIODS: tuple[str, ...] = ("opening", "ending")


def bank_total_key(group: str, period: str) -> str:
    return f"E1-bank-detail-{group}-{'opening' if period == 'opening' else 'total'}-unaudited"


def hall_adj_key(item_key: str) -> str:
    return f"E1-hall-adj-{item_key}-ending"


def adj_total_key(account_code: str, period: str) -> str:
    return f"E1-adj-total-{account_code}" + ("-opening" if period == "opening" else "")


class Unavailable(NamedTuple):
    """派生值无从计算（不写、不清空目标），附中文原因。"""

    reason: str


Entries = Mapping[str, Any]
"""``item_id → remark``（取自 checklist_responses；缺键即未保存过）。"""


def _get(entries: Entries, key: str) -> Any:
    return entries.get(key)


def _parse_row_list(raw: Any) -> list | None:
    """行 JSON → list；缺失 / 解析失败 / 非数组 / 空数组 → None（前端这些情形都退回默认行）。"""
    if not raw:
        return None
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list) or not parsed:
        return None
    return parsed


def _as_dict(row: Any) -> Mapping[str, Any]:
    return row if isinstance(row, Mapping) else {}


def _js_truthy_str(value: Any, fallback: str) -> str:
    """``String(v || fallback)``。"""
    if value is None or value is False or value == "" or value == 0:
        return fallback
    return value if isinstance(value, str) else str(value)


def _sum_or_zero(rows: Iterable[Mapping[str, Any]], field: str) -> float:
    """``rows.reduce((s, r) => s + (Number(r[field]) || 0), 0)``（e1FourTablePrefill.sum）。"""
    total = 0.0
    for r in rows:
        total = total + js_or_zero(r.get(field))
    return total


# ── 币种（e1FourTablePrefill.currencyLabel / e1BankAccountPrefill.isBaseCurrency）────────


def currency_label(currency: Any) -> str:
    """``e1FourTablePrefill.currencyLabel``：空 / CNY / RMB → 人民币，其余原样。"""
    raw = currency if isinstance(currency, str) else ""
    c = raw.upper()
    if not c or c in ("CNY", "RMB"):
        return "人民币"
    return raw or "人民币"


def is_base_currency(currency: Any) -> bool:
    """``e1BankAccountPrefill.isBaseCurrency``。"""
    raw = currency if isinstance(currency, str) else ""
    c = raw.strip().upper()
    return c in ("", "CNY", "RMB") or raw.strip() == "人民币"


def currency_label_of(currency: Any) -> str:
    return "人民币" if is_base_currency(currency) else (currency or "").strip()


# ── 种子行（与宿主 seedFromFourTable 同口径：只用于确定「四表带入的行 id」与其取数值）────


def build_cash_seed_rows(cash: list[Mapping[str, Any]] | None) -> list[dict] | None:
    """``e1FourTablePrefill.buildCashSeedRows``：首个人民币叶子 → ``fixed-rmb``，其余 ``cash-ft-{code}``。"""
    if not cash:
        return None
    rows: list[dict] = []
    used_fixed = False
    for r in cash:
        is_cny = currency_label(r.get("currency")) == "人民币"
        row_id = "fixed-rmb" if (is_cny and not used_fixed) else f"cash-ft-{r.get('code')}"
        if row_id == "fixed-rmb":
            used_fixed = True
        rows.append({
            "id": row_id,
            "currency": currency_label(r.get("currency")),
            "opening": r.get("opening"),
            "increase": r.get("increase"),
            "decrease": r.get("decrease"),
            "fxRate": 1 if is_cny else 0,
            "code": r.get("code"),
        })
    return rows


def build_bank_seed_rows(
    bank: list[Mapping[str, Any]] | None, other: list[Mapping[str, Any]] | None
) -> list[dict] | None:
    """``e1FourTablePrefill.buildBankSeedRows``（叶子口径）：1002 → institution，1012 → other。"""
    bank, other = list(bank or []), list(other or [])
    if not bank and not other:
        return None

    def mk(r: Mapping[str, Any], group: str) -> dict:
        return {
            "id": f"bank-principal-{group}-ft-{r.get('code')}",
            "group": group,
            "opening": r.get("opening"),
            "increase": r.get("increase"),
            "decrease": r.get("decrease"),
            "code": r.get("code"),
        }

    return [*(mk(r, "institution") for r in bank), *(mk(r, "other") for r in other)]


#: e1BankAccountPrefill.ACCOUNT_SLOT_ORDER / ACCOUNT_SLOT_TO_GROUP
ACCOUNT_SLOT_ORDER: tuple[str, ...] = ("bank", "other", "finance_co")
ACCOUNT_SLOT_TO_GROUP: Mapping[str, str] = {"bank": "institution", "finance_co": "finance", "other": "other"}


def _unique_id(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    i = 2
    while f"{base}-{i}" in used:
        i += 1
    rid = f"{base}-{i}"
    used.add(rid)
    return rid


def _str(value: Any) -> str:
    return "" if value is None else (value if isinstance(value, str) else str(value))


def build_bank_seed_rows_from_accounts(account_prefill: Mapping[str, Any] | None) -> list[dict] | None:
    """``e1BankAccountPrefill.buildBankSeedRowsFromAccounts``（账户级口径；id 与取数值，不含展示字段）。"""
    accounts = _as_dict(_as_dict(account_prefill).get("accounts"))
    items: list[tuple[str, Mapping[str, Any]]] = []
    for slot in ACCOUNT_SLOT_ORDER:
        for row in accounts.get(slot) or []:
            if isinstance(row, Mapping):
                items.append((slot, row))
    if not items:
        return None
    used: set[str] = set()
    out: list[dict] = []
    for slot, row in items:
        group = ACCOUNT_SLOT_TO_GROUP.get(slot) or "other"
        key = _str(row.get("account_no")) or _str(row.get("account_code"))
        out.append({
            "id": _unique_id(f"bank-principal-{group}-acct-{key}", used),
            "group": group,
            "opening": row.get("opening"),
            "increase": row.get("debit"),
            "decrease": row.get("credit"),
            "code": _str(row.get("account_code")),
            "foreign": not is_base_currency(_str(row.get("currency"))),
        })
    return out


def bank_seed_rows(four_table_prefill: Mapping[str, Any], account_prefill: Mapping[str, Any] | None) -> list[dict] | None:
    """宿主口径：账户级优先，账户级为 null 时退回叶子口径（``??``）。"""
    acct = build_bank_seed_rows_from_accounts(account_prefill)
    if acct is not None:
        return acct
    return build_bank_seed_rows(four_table_prefill.get("bank"), four_table_prefill.get("other"))


# ── 行解析与重算（useE1CashDetail / useE1BankDetail 的 loadFromResponses + recalcRow）──────


def load_cash_rows(raw: Any) -> list[dict] | None:
    """``useE1CashDetail.loadFromResponses`` + ``recalcRow``。None = 无持久化行。"""
    parsed = _parse_row_list(raw)
    if parsed is None:
        return None
    rows: list[dict] = []
    for item in parsed:
        r = _as_dict(item)
        opening, increase, decrease = parse_num(r.get("opening")), parse_num(r.get("increase")), parse_num(r.get("decrease"))
        fx_rate = parse_num(r.get("fxRate"))
        ending_fc = opening + increase - decrease
        rows.append({
            "id": _js_truthy_str(r.get("id"), ""),
            "opening": opening,
            "increase": increase,
            "decrease": decrease,
            "fxRate": fx_rate,
            "endingRmb": ending_fc * fx_rate,
        })
    return rows


def cash_totals(rows: list[dict]) -> dict[str, float]:
    """``totalRow.opening`` / ``totalRow.endingRmb``（sumField，从 0 起逐项相加）。"""
    opening = 0.0
    ending = 0.0
    for r in rows:
        opening = opening + r["opening"]
    for r in rows:
        ending = ending + r["endingRmb"]
    return {"opening": opening, "ending": ending}


def classify_fx_form(row: Mapping[str, Any]) -> str:
    """``useE1BankDetail.classifyFxForm``。"""
    has_fc = any(parse_num(row.get(f)) != 0 for f in ("openingFc", "increaseFc", "decreaseFc", "adjustmentFc"))
    if has_fc:
        return "fc-authoritative"
    return "base-identity" if is_base_currency(_str(row.get("fxCurrency"))) else "foreign-pending"


def _normalize_bank_row(item: Any) -> dict:
    """``useE1BankDetail.loadFromResponses`` 的字段归一（只取算式需要的字段）。"""
    r = _as_dict(item)
    section = _str(r.get("section")) if _str(r.get("section")) in ("principal", "accrued") else "principal"
    legacy_group = _js_truthy_str(r.get("group"), "")
    group = legacy_group if legacy_group in ("institution", "finance", "other") else "institution"
    fx_raw = r.get("fxRate")
    return {
        "id": _js_truthy_str(r.get("id"), ""),
        "section": section,
        "group": group,
        "opening": parse_num(r.get("opening")),
        "increase": parse_num(r.get("increase")),
        "decrease": parse_num(r.get("decrease")),
        "fxCurrency": _js_truthy_str(r.get("fxCurrency"), "人民币"),
        # 🔴 三态：缺失 / null / 空串 → 1；显式 0 保持 0（外币待录入）
        "fxRate": 1.0 if (fx_raw is None or fx_raw == "") else parse_num(fx_raw),
        "openingFc": parse_num(r.get("openingFc")),
        "increaseFc": parse_num(r.get("increaseFc")),
        "decreaseFc": parse_num(r.get("decreaseFc")),
        "adjustmentFc": parse_num(r.get("adjustmentFc")),
    }


def recalc_bank_row(row: dict, variant: str) -> dict:
    """``useE1BankDetail.recalcRow``（只算合计需要的 opening / ending）。"""
    out = dict(row)
    if variant == "multi" and classify_fx_form(row) != "base-identity":
        ending_fc = row["openingFc"] + row["increaseFc"] - row["decreaseFc"]
        out["opening"] = row["openingFc"] * row["fxRate"]
        out["ending"] = ending_fc * row["fxRate"]
    else:
        out["ending"] = row["opening"] + row["increase"] - row["decrease"]
    return out


def load_bank_rows(raw: Any, variant: str) -> list[dict] | None:
    parsed = _parse_row_list(raw)
    if parsed is None:
        return None
    return [recalc_bank_row(_normalize_bank_row(item), variant) for item in parsed]


def bank_group_totals(rows: list[dict]) -> dict[str, dict[str, float]]:
    """``crossSheetValues``：本金段各组 Σ；principal = institution + finance。"""
    groups: dict[str, dict[str, float]] = {}
    for group in ("institution", "finance", "other"):
        opening = 0.0
        ending = 0.0
        records = [r for r in rows if r["section"] == "principal" and r["group"] == group]
        for r in records:
            opening = opening + r["opening"]
        for r in records:
            ending = ending + r["ending"]
        groups[group] = {"opening": opening, "ending": ending}
    groups["principal"] = {
        "opening": groups["institution"]["opening"] + groups["finance"]["opening"],
        "ending": groups["institution"]["ending"] + groups["finance"]["ending"],
    }
    return groups


def bank_variant(entries: Entries) -> tuple[str, bool]:
    """E1-3 variant：已保存的 ``E1-bank-variant``；缺省 multi。返回 (variant, 是否缺省)。"""
    stored = _get(entries, BANK_VARIANT_KEY)
    if stored in BANK_VARIANTS:
        return stored, False
    return DEFAULT_BANK_VARIANT, True


# ── 行字段推送计划 ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RowPush:
    """一个行字段推送目标。``mirror_field`` 非空时写入同值到该字段（本位币恒等镜像）。"""

    row_id: str
    field: str
    value: float
    current: float | None
    mirror_field: str | None = None


_BASE_FIELDS = ("opening", "increase", "decrease")
_FC_FIELDS = ("openingFc", "increaseFc", "decreaseFc")
UNTOUCHED_DEFAULT_ROW_ID = "fixed-rmb"


def _current_field(row: Mapping[str, Any], field: str) -> float | None:
    raw = row.get(field)
    if raw is None or raw == "":
        return None
    return parse_num(raw)


def is_untouched_default_cash_row(row: Mapping[str, Any]) -> bool:
    """composable 自动补的人民币默认行且从未录入（金额全 0、无备注）—— 其金额视为「空」。

    ``createDefaultRmbRow`` 的占位行不是用户数据；若按「当前 ≠ 公式值、从未推送」判成待确认，
    每个先打开底稿、后导入四表的项目首推都会卡住。只认 id=fixed-rmb 且四个金额全 0、备注为空。
    """
    if _str(row.get("id")) != UNTOUCHED_DEFAULT_ROW_ID:
        return False
    amounts = ("opening", "increase", "decrease", "adjustment")
    return all(parse_num(row.get(f)) == 0 for f in amounts) and not _str(row.get("note")).strip()


def _first_by_id(stored: list) -> dict[str, Mapping[str, Any]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in stored:
        if isinstance(item, Mapping):
            by_id.setdefault(_str(item.get("id")), item)  # 与 JS find/findIndex 一致：首个命中
    return by_id


def plan_cash_row_pushes(raw: Any, seeds: list[dict] | None) -> tuple[list[RowPush], list[tuple[str, str]]]:
    """现金明细：四表带入的行（种子 id 命中已保存行）逐字段推送；其余行不动。"""
    if not seeds:
        return [], []
    stored = _parse_row_list(raw)
    if stored is None:
        return [], [(s["id"], "现金明细尚未建立（打开底稿时由四表带入）") for s in seeds]
    by_id = _first_by_id(stored)
    pushes: list[RowPush] = []
    skips: list[tuple[str, str]] = []
    for seed in seeds:
        row = by_id.get(seed["id"])
        if row is None:
            skips.append((seed["id"], f"现金明细中没有该行（四表科目 {seed.get('code')}，在底稿「重新取数」后纳入）"))
            continue
        untouched = is_untouched_default_cash_row(row)
        for field in _BASE_FIELDS:
            current = None if untouched else _current_field(row, field)
            pushes.append(RowPush(seed["id"], field, parse_num(seed.get(field)), current))
    return pushes, skips


def _bank_push_fields(row: Mapping[str, Any], variant: str) -> tuple[tuple[str, ...], bool] | None:
    """该行由四表推送哪组字段：(字段, 是否镜像到本位币列)；None = 不推送（外币行）。"""
    norm = _normalize_bank_row(row)
    if variant != "multi":
        return _BASE_FIELDS, False
    form = classify_fx_form(norm)
    if form == "base-identity":
        return _BASE_FIELDS, False
    if form == "fc-authoritative" and is_base_currency(norm["fxCurrency"]) and norm["fxRate"] == 1:
        # 本位币账户在多币种版以原币列为权威、汇率 1：原币 == 本位币是恒等事实，两列同写
        return _FC_FIELDS, True
    return None


def plan_bank_row_pushes(
    raw: Any, seeds: list[dict] | None, variant: str
) -> tuple[list[RowPush], list[tuple[str, str]]]:
    """银行明细：四表带入的本金行逐字段推送；外币行（原币 × 汇率派生）不推送。"""
    if not seeds:
        return [], []
    stored = _parse_row_list(raw)
    if stored is None:
        return [], [(s["id"], "银行存款明细尚未建立（打开底稿时由四表带入）") for s in seeds]
    by_id = _first_by_id(stored)
    pushes: list[RowPush] = []
    skips: list[tuple[str, str]] = []
    for seed in seeds:
        row = by_id.get(seed["id"])
        if row is None:
            skips.append((seed["id"], f"银行存款明细中没有该行（四表 {seed.get('code')}，在底稿「重新取数」后纳入）"))
            continue
        if _normalize_bank_row(row)["section"] != "principal":
            skips.append((seed["id"], "该行已移入应计利息段，四表本金数不再推送"))
            continue
        plan = _bank_push_fields(row, variant)
        if plan is None:
            skips.append((seed["id"], "外币行按原币 × 汇率派生，四表只有本位币金额，不推送"))
            continue
        fields, mirror = plan
        for base_field, field in zip(_BASE_FIELDS, fields):
            pushes.append(RowPush(
                seed["id"], field, parse_num(seed.get(base_field)), _current_field(row, field),
                mirror_field=base_field if mirror else None,
            ))
    return pushes, skips


def apply_row_pushes(raw: Any, pushes: Iterable[RowPush]) -> str:
    """把决定写入的行字段落回行 JSON（保持行序与字段序，只改目标字段）。"""
    rows = json.loads(raw) if isinstance(raw, str) else list(raw or [])
    index: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, dict):
            index.setdefault(_str(row.get("id")), row)
    for push in pushes:
        row = index.get(push.row_id)
        if row is None:
            raise KeyError(f"行 {push.row_id} 不存在（计划与写入之间行集被改动）")
        value = js_json_number(push.value)
        row[push.field] = value
        if push.mirror_field:
            row[push.mirror_field] = value
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


# ── 派生：明细合计键（useE1CashDetail / useE1BankDetail 的 cross-sheet 写出 + 宿主种子兜底）──


def cash_detail_total(entries: Entries, cash_leaves: list[Mapping[str, Any]], period: str) -> float:
    """行存在 → Σ行；行不存在 → 四表叶子合计（``buildCrossSheetSeeds``）。"""
    rows = load_cash_rows(_get(entries, CASH_ROWS_KEY))
    if rows is not None:
        return cash_totals(rows)[period]
    return _sum_or_zero(cash_leaves, "opening" if period == "opening" else "ending")


def bank_detail_total(
    entries: Entries,
    variant: str,
    four_table_prefill: Mapping[str, Any],
    group: str,
    period: str,
) -> float | Unavailable:
    rows = load_bank_rows(_get(entries, BANK_ROWS_KEY), variant)
    if rows is not None:
        return bank_group_totals(rows)[group][period]
    field = "opening" if period == "opening" else "ending"
    if group in ("principal", "institution"):
        return _sum_or_zero(four_table_prefill.get("bank") or [], field)
    if group == "other":
        return _sum_or_zero(four_table_prefill.get("other") or [], field)
    return Unavailable("财务公司分组只由银行存款明细行汇总，明细尚未建立")


# ── 派生：审定表（useE1Adjudication.buildRow / aggregateAuditedByCode / syncAuditedTotals）──


def adjustment_for(entries: Entries, item_key: str, period: str) -> float:
    """``e1AdjustmentFor``：E1-5 本地账项调整 + 大厅已确认调整（仅期末、仅三行）。"""
    local = parse_num(_get(entries, f"E1-adjustment-by-item-{item_key}-{period}"))
    hall = parse_num(_get(entries, hall_adj_key(item_key))) if (
        period == "ending" and item_key in HALL_ADJ_ITEM_KEYS
    ) else 0.0
    return local + hall


def _accrued_rows(entries: Entries) -> list:
    raw = _get(entries, ACCRUED_ROWS_KEY)
    if not raw:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


_ACCRUED_CHILDREN: tuple[str, ...] = ("accrued_finance", "accrued_bank", "accrued_other", "accrued_digital")


def _accrued_category_values(entries: Entries, item_key: str, rows: list) -> dict[str, float]:
    totals = {"finance": 0.0, "bank": 0.0, "other": 0.0, "digital": 0.0}
    for item in rows:
        r = _as_dict(item)
        category = _js_truthy_str(r.get("category"), "bank")
        if category in totals:
            totals[category] = totals[category] + parse_num(r.get("accruedRmb"))
    category = item_key.replace("accrued_", "", 1)
    return {
        "opening": parse_num(_get(entries, f"E1-adj-{item_key}-opening-unadj")),
        "ending": (totals.get(category) or 0.0) if rows else parse_num(_get(entries, f"E1-adj-{item_key}-ending-unadj")),
    }


def _accrued_total_values(entries: Entries) -> dict[str, float]:
    rows = _accrued_rows(entries)
    values = [_accrued_category_values(entries, key, rows) for key in _ACCRUED_CHILDREN]
    opening_sum = 0.0
    ending_sum = 0.0
    for v in values:
        opening_sum = opening_sum + v["opening"]
    for v in values:
        ending_sum = ending_sum + v["ending"]
    legacy_opening = parse_num(_get(entries, "E1-adj-accrued_interest-opening-unadj"))
    return {
        "opening": legacy_opening if all(v["opening"] == 0 for v in values) else opening_sum,
        "ending": ending_sum,
    }


def _unaudited(entries: Entries, item_key: str) -> dict[str, float]:
    def pair(opening_key: str, ending_key: str) -> dict[str, float]:
        return {"opening": parse_num(_get(entries, opening_key)), "ending": parse_num(_get(entries, ending_key))}

    if item_key == "cash":
        return pair(CASH_TOTAL_KEYS["opening"], CASH_TOTAL_KEYS["ending"])
    if item_key in ("bank_principal", "finance_co", "bank_institution", "other_mf"):
        group = {"bank_principal": "principal", "finance_co": "finance",
                 "bank_institution": "institution", "other_mf": "other"}[item_key]
        return pair(bank_total_key(group, "opening"), bank_total_key(group, "ending"))
    if item_key == "digital":
        return pair(DIGITAL_TOTAL_KEYS["opening"], DIGITAL_TOTAL_KEYS["ending"])
    if item_key == "accrued_interest":
        return _accrued_total_values(entries)
    if item_key in _ACCRUED_CHILDREN:
        return _accrued_category_values(entries, item_key, _accrued_rows(entries))
    return pair(f"E1-adj-{item_key}-opening-unadj", f"E1-adj-{item_key}-ending-unadj")


def adjudication_row(entries: Entries, item_key: str) -> dict[str, float]:
    """审定表一行：未审 / 账项调整 / 审定（审定 = 未审 + 调整）。"""
    un = _unaudited(entries, item_key)
    out: dict[str, float] = {}
    for period in PERIODS:
        if item_key == "accrued_interest":
            adj = 0.0
            for child in _ACCRUED_CHILDREN:
                adj = adj + adjustment_for(entries, child, period)
        else:
            adj = adjustment_for(entries, item_key, period)
        out[f"{period}_unaudited"] = un[period]
        out[f"{period}_adjustment"] = adj
        out[f"{period}_audited"] = un[period] + adj
    return out


def adjudicated_total(entries: Entries, account_code: str, period: str) -> float:
    """``aggregateAuditedByCode``：1001 = 现金；1002 = 银行存款本金；1012 = 其他货币资金 + 数字货币。"""
    key = f"{period}_audited"
    if account_code == "1001":
        return adjudication_row(entries, "cash")[key]
    if account_code == "1002":
        return adjudication_row(entries, "bank_principal")[key]
    if account_code == "1012":
        return adjudication_row(entries, "other_mf")[key] + adjudication_row(entries, "digital")[key]
    raise ValueError(f"E1 审定合计不含科目 {account_code}")


#: e1MainRowPrefill.E1_MAIN_ROW_SLOTS（披露行 key → 审定表 itemKey）
MAIN_ROW_SLOTS: Mapping[str, str] = {"finance_co": "finance_co", "accrued": "accrued_interest", "digital": "digital"}
MAIN_ROW_DEDUCTIONS: Mapping[str, tuple[str, ...]] = {"bank": ("finance_co",), "other_mf": ("digital",)}


def main_row_slot_key(row_key: str, period: str) -> str:
    """``e1MainRowSlotKey``。"""
    if row_key not in MAIN_ROW_SLOTS:
        return ""
    base = f"E1-adj-slot-{row_key}"
    return f"{base}-opening" if period == "opening" else base


def main_row_slot(entries: Entries, slot: str, period: str) -> float | None:
    """``buildE1MainRowSlotWrites``：该期未审 / 调整 / 审定三值全 0 ⇒ 空（None），否则审定数。"""
    row = adjudication_row(entries, MAIN_ROW_SLOTS[slot])
    trio = (row[f"{period}_unaudited"], row[f"{period}_adjustment"], row[f"{period}_audited"])
    if all(_finite_or_zero(v) == 0 for v in trio):
        return None
    return _finite_or_zero(row[f"{period}_audited"])


def _finite_or_zero(value: Any) -> float:
    """``e1MainRowPrefill.num``：``Number(v)`` 有限则取之，否则 0。"""
    number = js_number(value)
    return number if number == number and number not in (float("inf"), float("-inf")) else 0.0


# ── 附注：披露主表行（e1DisclosureScope 行集 + e1MainRowPrefill 取数 + E1TabDisclosure 合计）──

MAIN_ROWS: Mapping[str, tuple[Mapping[str, Any], ...]] = {
    "listed": (
        {"key": "cash", "label": "库存现金", "note_label": None, "cross_key": "E1-adj-total-1001"},
        {"key": "bank", "label": "银行存款", "note_label": None, "cross_key": "E1-adj-total-1002"},
        {"key": "finance_co", "label": "存放财务公司款项", "note_label": None, "cross_key": ""},
        {"key": "other_mf", "label": "其他货币资金", "note_label": None, "cross_key": "E1-adj-total-1012"},
        {"key": "accrued", "label": "存款应计利息", "note_label": None, "cross_key": ""},
        {"key": "digital", "label": "数字货币", "note_label": None, "cross_key": ""},
        {"key": "total", "label": "合计", "note_label": None, "cross_key": "", "is_total": True},
        {"key": "overseas", "label": "其中：存放在境外的款项总额", "note_label": None, "cross_key": "", "is_memo": True},
    ),
    "soe": (
        {"key": "cash", "label": "现金", "note_label": "库存现金", "cross_key": "E1-adj-total-1001"},
        {"key": "bank", "label": "银行存款", "note_label": None, "cross_key": "E1-adj-total-1002"},
        {"key": "other_mf", "label": "其他货币资金", "note_label": None, "cross_key": "E1-adj-total-1012"},
        {"key": "digital", "label": "数字货币", "note_label": None, "cross_key": ""},
        {"key": "total", "label": "合计", "note_label": None, "cross_key": "", "is_total": True},
        {"key": "overseas", "label": "其中：存放在境外的款项总额", "note_label": "其中：存放在境外的款项总额",
         "cross_key": "", "is_memo": True},
    ),
}


def openings_key(variant: str) -> str:
    return f"E1-disclosure-{variant}-openings"


def _opening_map(entries: Entries, variant: str) -> dict[str, Any]:
    raw = _get(entries, openings_key(variant))
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _amount_key(row: Mapping[str, Any], period: str) -> str:
    """``e1MainRowAmountKey``：crossKey 优先 → 槽键 → ''。"""
    cross = row.get("cross_key") or ""
    if cross:
        return f"{cross}-opening" if period == "opening" else cross
    return main_row_slot_key(row["key"], period)


def _deduction_keys(row: Mapping[str, Any], period: str) -> list[str]:
    if not row.get("cross_key"):
        return []
    return [k for k in (main_row_slot_key(s, period) for s in MAIN_ROW_DEDUCTIONS.get(row["key"], ())) if k]


def resolve_main_row_amount(row: Mapping[str, Any], entries: Entries, period: str) -> float | None:
    """``resolveE1MainRowAmount``：主键取不到 ⇒ None（不是 0）；扣减槽缺值按 0。"""
    key = _amount_key(row, period)
    base = read_number(_get(entries, key)) if key else None
    if base is None:
        return None
    deducted = base
    for k in _deduction_keys(row, period):
        value = read_number(_get(entries, k))
        deducted = deducted - (value if value is not None else 0.0)
    return deducted


def disclosure_main_rows(entries: Entries, variant: str) -> list[dict[str, Any]]:
    """``computeE1DisclosureMainRows``：每行期末 / 期初数与「是否取到值」。

    期末 = 取数（含扣减），取不到为 0 且 ``ending_resolved=False``；
    期初 = 披露表手工覆盖优先（``E1-disclosure-{variant}-openings`` 含该 key），否则同期末取数口径；
    合计 = 参与合计行（非合计、非「其中：」）之和，恒为已取到。
    """
    if variant not in MAIN_ROWS:
        raise ValueError(f"未知披露变体 {variant!r}")
    defs = MAIN_ROWS[variant]
    opening_map = _opening_map(entries, variant)

    def eff_ending(row: Mapping[str, Any]) -> float:
        value = resolve_main_row_amount(row, entries, "ending")
        return value if value is not None else 0.0

    def eff_opening(row: Mapping[str, Any]) -> float:
        if row["key"] in opening_map:
            return js_or_zero(opening_map[row["key"]])
        value = resolve_main_row_amount(row, entries, "opening")
        return value if value is not None else 0.0

    summable = [d for d in defs if not d.get("is_total") and not d.get("is_memo")]
    out: list[dict[str, Any]] = []
    for row in defs:
        if row.get("is_total"):
            ending = 0.0
            opening = 0.0
            for s in summable:
                ending = ending + eff_ending(s)
            for s in summable:
                opening = opening + eff_opening(s)
            ending_resolved = opening_resolved = True
        else:
            ending, opening = eff_ending(row), eff_opening(row)
            ending_resolved = resolve_main_row_amount(row, entries, "ending") is not None
            opening_resolved = row["key"] in opening_map or resolve_main_row_amount(row, entries, "opening") is not None
        out.append({
            "key": row["key"],
            "label": row["label"],
            "note_label": row.get("note_label") or row["label"],
            "is_total": bool(row.get("is_total")),
            "is_memo": bool(row.get("is_memo")),
            "ending": ending,
            "opening": opening,
            "ending_resolved": ending_resolved,
            "opening_resolved": opening_resolved,
        })
    return out
