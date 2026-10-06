"""Batch C audited totals agree with the public report TB resolver.

Spec: formula-push-balance-adj-batch-c · requirement C10.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.audit_platform_models import (
    AccountCategory,
    Adjustment,
    AdjustmentEntry,
    TrialBalance,
)
from app.services.formula_push.bindings import get_binding, supported_wp_codes
from app.services.formula_push.bindings.balance_adj import (
    _SPECS,
    BalanceAdjudicationBinding,
)
from app.services.formula_push.rules import load_rules, rules_for
from app.services.report_engine import ReportFormulaParser
from tests._formula_push_env import YEAR, make_env


_BATCH_C_CODES = tuple(sorted(_SPECS))
_RULES = load_rules()


def _audited_rules(wp_code: str):
    return tuple(
        rule
        for rule in rules_for(_RULES, wp_code=wp_code)
        if rule.stage == "derived"
        and rule.source.kind == "derivation"
        and rule.source.name == f"{wp_code.lower()}_audited_total"
    )


def _expected_by_kind(wp_code: str, amounts: dict[str, Decimal]) -> dict[str, Decimal]:
    spec = _SPECS[wp_code]
    if spec.sections:
        return {
            section: amounts[spec.account_codes[index]]
            for index, (section, _) in enumerate(spec.sections)
        }
    total = sum((amounts[code] for code in spec.account_codes), Decimal("0"))
    return {"receivable": total, "net": total}


def _entries_for_spec(wp_code: str, amounts: dict[str, Decimal]) -> dict[str, str]:
    """Build rows whose audited totals equal the TB prefix amounts.

    Each dynamic account row carries one declared prefix's TB value.  A child
    TB row is inserted separately by the fixture, so this also exercises the
    report resolver's prefix aggregation rather than only exact-code lookup.
    """
    spec = _SPECS[wp_code]
    entries: dict[str, str] = {}

    if spec.sections:
        for index, (section, row_keys) in enumerate(spec.sections):
            expected = amounts[spec.account_codes[index]]
            for row_index, row_key in enumerate(row_keys):
                base = f"{spec.sheet_code}-{section}-{row_key}"
                entries[f"{base}-unadj"] = str(expected if row_index == 0 else Decimal("0"))
                entries[f"{base}-aje"] = "0"
                entries[f"{base}-rje"] = "0"
        return entries

    if spec.dynamic_rows:
        row_ids = tuple(f"account-{index}" for index, _ in enumerate(spec.account_codes, start=1))
        entries[f"{spec.sheet_code}-rows"] = json.dumps(
            [
                {"rowId": row_id, "label": account_code, "source": "manual"}
                for row_id, account_code in zip(row_ids, spec.account_codes)
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for row_index, (row_id, account_code) in enumerate(zip(row_ids, spec.account_codes)):
            base = f"{spec.sheet_code}-{row_id}"
            entries[f"{base}-unadj"] = str(amounts[account_code])
            entries[f"{base}-aje"] = "0"
            entries[f"{base}-rje"] = "0"
        return entries

    if not spec.fixed_row_keys:
        raise AssertionError(f"{wp_code} has no declared row shape")
    expected = amounts[spec.account_codes[0]]
    for row_index, row_key in enumerate(spec.fixed_row_keys):
        prefix = f"{spec.fixed_row_prefix}-" if spec.fixed_row_prefix else ""
        base = f"{spec.sheet_code}-{prefix}{row_key}"
        entries[f"{base}-unadj"] = str(expected if row_index == 0 else Decimal("0"))
        entries[f"{base}-aje"] = "0"
        entries[f"{base}-rje"] = "0"
    return entries


async def _insert_workpaper(env, wp_code: str) -> uuid.UUID:
    index_id, wp_id = uuid.uuid4(), uuid.uuid4()
    async with env.factory() as db:
        await db.execute(
            sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) "
                "VALUES (:i, :p, :c)"
            ),
            {"i": str(index_id), "p": str(env.pid), "c": wp_code},
        )
        await db.execute(
            sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) "
                "VALUES (:w, :p, :i)"
            ),
            {"w": str(wp_id), "p": str(env.pid), "i": str(index_id)},
        )
        await db.commit()
    return wp_id


async def _insert_tb_rows(env, wp_code: str) -> dict[str, Decimal]:
    spec = _SPECS[wp_code]
    amounts = {
        code: Decimal("1000") + Decimal(index)
        for index, code in enumerate(spec.account_codes, start=1)
    }
    category = AccountCategory.liability if spec.is_liability else AccountCategory.asset
    async with env.factory() as db:
        for code, amount in amounts.items():
            for standard_code, value in ((code, amount), (f"{code}01", Decimal("0.37"))):
                db.add(
                    TrialBalance(
                        project_id=env.pid,
                        year=YEAR,
                        company_code="001",
                        standard_account_code=standard_code,
                        account_name=standard_code,
                        account_category=category,
                        audited_amount=value,
                        opening_balance=Decimal("0"),
                    )
                )
        await db.commit()
    return {code: amount + Decimal("0.37") for code, amount in amounts.items()}


async def _seed_entries(env, wp_id: uuid.UUID, entries: dict[str, str]) -> None:
    async with env.factory() as db:
        for item_id, remark in entries.items():
            await db.execute(
                sa.text(
                    "INSERT INTO checklist_responses "
                    "(id, project_id, wp_id, item_id, remark, updated_at) "
                    "VALUES (:id, :p, :w, :i, :r, :t)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "p": str(env.pid),
                    "w": str(wp_id),
                    "i": item_id,
                    "r": remark,
                    "t": "2026-10-01 08:00:00.000000+00:00",
                },
            )
        await db.commit()


async def _read_entries(env, wp_id: uuid.UUID) -> dict[str, str]:
    async with env.factory() as db:
        rows = (
            await db.execute(
                sa.text(
                    "SELECT item_id, remark FROM checklist_responses WHERE wp_id = :w"
                ),
                {"w": str(wp_id)},
            )
        ).all()
    return {row[0]: row[1] for row in rows}


@pytest.fixture
def batch_c_codes() -> tuple[str, ...]:
    return _BATCH_C_CODES


@pytest.mark.asyncio
@pytest.mark.parametrize("wp_code", _BATCH_C_CODES)
async def test_batch_c_audited_total_matches_report_tb(
    monkeypatch, wp_code: str, batch_c_codes: tuple[str, ...]
) -> None:
    """Every registered Batch C subject matches ReportFormulaParser.resolve_tb."""
    # Keep each parameter isolated: the shared account prefixes (1901/1503)
    # must still be tested independently without duplicate TB unique keys.
    async with make_env(
        monkeypatch,
        extra_tables=(TrialBalance.__table__, Adjustment.__table__, AdjustmentEntry.__table__),
    ) as env:
        assert wp_code in batch_c_codes
        wp_id = await _insert_workpaper(env, wp_code)
        amounts = await _insert_tb_rows(env, wp_code)
        await _seed_entries(env, wp_id, _entries_for_spec(wp_code, amounts))

        result = await env.push(codes=(wp_code,))
        assert result.status == "succeeded"

        saved = await _read_entries(env, wp_id)
        async with env.factory() as db:
            parser = ReportFormulaParser(db, env.pid, YEAR)
            report_values: dict[str, Decimal] = {}
            for rule in _audited_rules(wp_code):
                kind = rule.source.params_map["kind"]
                spec = _SPECS[wp_code]
                if spec.sections:
                    account_code = spec.account_codes[
                        next(index for index, (section, _) in enumerate(spec.sections) if section == kind)
                    ]
                    report_values[kind] = await parser.resolve_tb(account_code, "期末余额")
                else:
                    report_values[kind] = sum(
                        [
                            await parser.resolve_tb(account_code, "期末余额")
                            for account_code in spec.account_codes
                        ],
                        Decimal("0"),
                    )

        assert report_values == _expected_by_kind(wp_code, amounts)
        for rule in _audited_rules(wp_code):
            kind = rule.source.params_map["kind"]
            item_id = rule.target.item_id
            assert item_id in saved, f"{wp_code} 未写入审定合计 {item_id}"
            assert Decimal(saved[item_id]) == report_values[kind], (
                f"{wp_code} {kind}：推送={saved[item_id]}，"
                f"报表 TB={report_values[kind]}"
            )


def test_batch_c_subject_registry_and_rule_coverage() -> None:
    """The C10 parameter set is the complete registered binding family."""
    registered_balance_adj = {
        code
        for code in supported_wp_codes()
        if isinstance(get_binding(code), BalanceAdjudicationBinding)
    }
    assert set(_BATCH_C_CODES) == registered_balance_adj
    assert len(_BATCH_C_CODES) == 30
    for code in _BATCH_C_CODES:
        rules = _audited_rules(code)
        assert rules
        expected_kinds = {"asset", "liab"} if _SPECS[code].sections else {"receivable", "net"}
        assert {rule.source.params_map["kind"] for rule in rules} == expected_kinds
