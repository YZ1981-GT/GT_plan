# Feature: workpaper-maintainability-convergence-followup, Property 5/6
"""
Property 5: FormData factory migration preserves public API
- For any migrated FormData composable, the exported function name and return type
  (ChecklistFormDataReturn) SHALL remain identical to the pre-migration public API.

Property 6: FormData migration eliminates self-built network
- For any migrated FormData composable, the `check_homogeneous_formdata.py` guard
  SHALL detect zero violations (no self-built checklist-responses GET/PUT patterns present).

Validates: Requirements 4.3, 4.4
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# ─── Import the script under test ────────────────────────────────────────────

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "migration"
    / "migrate_formdata_factory.py"
)
_spec = importlib.util.spec_from_file_location("migrate_formdata_factory", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

generate_migration_template = _mod.generate_migration_template

# ─── Strategies ──────────────────────────────────────────────────────────────

# Generate composable names matching use[A-Z][0-9a-zA-Z]*FormData pattern
_CYCLE_LETTERS = list("ABCDEFGHIKLMN")
_SUFFIXES = ["", "Main", "Ecl", "Sppi", "TraFin", "Valuation", "Detail"]


@st.composite
def composable_names(draw: st.DrawFn) -> str:
    """Generate random composable names: use[A-Z][0-9]+[Suffix]FormData."""
    letter = draw(st.sampled_from(_CYCLE_LETTERS))
    number = draw(st.integers(min_value=1, max_value=99))
    suffix = draw(st.sampled_from(_SUFFIXES))
    return f"use{letter}{number}{suffix}FormData"


# Valid component type segments
_COMPONENT_TYPE_PARTS = [
    "fixed-assets", "intangible-assets", "other-receivables",
    "trading-financial-assets", "long-term-equity-main",
    "inventory-valuation-impairment", "deferred-tax-assets",
    "construction-in-progress", "bonds-payable", "capital-reserve",
    "income-tax-expense", "non-operating-income", "held-for-sale",
    "right-of-use-assets", "development-expenditure",
]

# Valid account code patterns (4-digit Chinese accounting codes)
_ACCOUNT_CODES = [
    "1101", "1123", "1131", "1132", "1221", "1231", "1405", "1411",
    "1501", "1503", "1511", "1521", "1531", "1601", "1602", "1604",
    "1605", "1621", "1631", "1701", "1711", "1801", "1811", "1901",
    "2101", "2201", "2202", "2205", "2221", "2231", "2241", "2245",
    "2401", "2501", "2502", "2601", "2701", "2801", "2901",
    "4001", "4002", "4003", "4101", "4103", "4104", "4201",
    "6001", "6101", "6111", "6115", "6117", "6301", "6403",
    "6601", "6602", "6603", "6701", "6702", "6711", "6801",
]


@st.composite
def migration_configs(draw: st.DrawFn) -> dict:
    """Generate random valid migration config dicts."""
    letter = draw(st.sampled_from(_CYCLE_LETTERS))
    number = draw(st.integers(min_value=1, max_value=99))
    prefix = f"{letter}{number}-"
    label = f"{letter}{number}"

    # Optionally add suffix to label
    suffix = draw(st.sampled_from(["", "-Main", "-ECL", "-SPPI", "-TraFin"]))
    label = label + suffix

    component_type = draw(st.sampled_from(_COMPONENT_TYPE_PARTS))

    # 1-3 account codes
    num_codes = draw(st.integers(min_value=1, max_value=3))
    account_codes = draw(
        st.lists(
            st.sampled_from(_ACCOUNT_CODES),
            min_size=num_codes,
            max_size=num_codes,
        )
    )

    return {
        "prefix": prefix,
        "label": label,
        "componentType": component_type,
        "accountCodes": account_codes,
    }


# ─── Property 5: Migration preserves public API ─────────────────────────────


@settings(max_examples=100)
@given(name=composable_names(), config=migration_configs())
def test_property_5_migration_preserves_public_api(name: str, config: dict) -> None:
    """Property 5: FormData factory migration preserves public API.

    For any migrated FormData composable, the exported function name and return
    type (ChecklistFormDataReturn) SHALL remain identical to the pre-migration
    public API, ensuring consuming components require zero changes.

    Validates: Requirements 4.3
    """
    result = generate_migration_template(name, config)

    # Assert: result contains export function with exact composable name
    assert f"export function {name}(" in result, (
        f"Generated template must export function with name '{name}'.\n"
        f"Got:\n{result[:500]}"
    )

    # Assert: result declares ChecklistFormDataReturn return type
    assert "ChecklistFormDataReturn" in result, (
        f"Generated template must reference ChecklistFormDataReturn type.\n"
        f"Got:\n{result[:500]}"
    )

    # Assert: the function signature includes the return type annotation
    # Pattern: export function useName(...): ChecklistFormDataReturn {
    sig_pattern = re.compile(
        rf"export function {re.escape(name)}\([^)]*\):\s*ChecklistFormDataReturn\s*\{{"
    )
    assert sig_pattern.search(result), (
        f"Function signature must have ': ChecklistFormDataReturn {{' pattern.\n"
        f"Got:\n{result[:500]}"
    )


@settings(max_examples=100)
@given(name=composable_names(), config=migration_configs())
def test_property_5_migration_preserves_parameters(name: str, config: dict) -> None:
    """Property 5 supplementary: Migration preserves standard parameter signature.

    The migrated function must accept (wpId: Ref<string>, projectId: Ref<string>,
    year?: Ref<number | undefined>) — the standard FormData composable API.

    Validates: Requirements 4.3
    """
    result = generate_migration_template(name, config)

    # Assert: standard parameter names are present
    assert "wpId: Ref<string>" in result, (
        "Migrated template must include wpId: Ref<string> parameter"
    )
    assert "projectId: Ref<string>" in result, (
        "Migrated template must include projectId: Ref<string> parameter"
    )
    assert "year?" in result, (
        "Migrated template must include optional year parameter"
    )


# ─── Property 6: Migration eliminates self-built network ────────────────────

# The violation patterns from check_homogeneous_formdata.py
_SELF_NETWORK_PATTERNS = [
    re.compile(r"""api\.put\s*\(\s*[`'"]/api/workpapers/.*checklist-responses"""),
    re.compile(r"""api\.get\s*\(\s*[`'"]/api/workpapers/.*checklist-responses"""),
    re.compile(r"""fetch\s*\(\s*.*checklist-responses"""),
    re.compile(r"""http\.get\s*\("""),
    re.compile(r"""http\.put\s*\("""),
]

# The checklist-responses URL pattern (broader catch)
_CHECKLIST_RESPONSES_RE = re.compile(r"checklist-responses")


@settings(max_examples=100)
@given(name=composable_names(), config=migration_configs())
def test_property_6_migration_eliminates_self_built_network(name: str, config: dict) -> None:
    """Property 6: FormData migration eliminates self-built network.

    For any migrated FormData composable, the output SHALL NOT contain
    self-built checklist-responses GET/PUT patterns.

    Validates: Requirements 4.4
    """
    result = generate_migration_template(name, config)

    # Assert: result uses createChecklistFormData factory
    assert "createChecklistFormData" in result, (
        "Migrated template must use createChecklistFormData factory call.\n"
        f"Got:\n{result[:500]}"
    )

    # Assert: result does NOT contain checklist-responses URL pattern
    assert not _CHECKLIST_RESPONSES_RE.search(result), (
        "Migrated template must NOT contain 'checklist-responses' URL pattern.\n"
        f"Got:\n{result[:500]}"
    )

    # Assert: result does NOT contain http.get or http.put patterns
    for pattern in _SELF_NETWORK_PATTERNS:
        assert not pattern.search(result), (
            f"Migrated template must NOT match self-built network pattern: {pattern.pattern}\n"
            f"Got:\n{result[:500]}"
        )


@settings(max_examples=100)
@given(name=composable_names(), config=migration_configs())
def test_property_6_migration_config_values_present(name: str, config: dict) -> None:
    """Property 6 supplementary: Migration template contains all config values.

    The factory call must include the correct itemPrefix, label, forceComponentType,
    and accountCodes from the config — ensuring the factory is properly parameterized
    to replace the self-built network.

    Validates: Requirements 4.4
    """
    result = generate_migration_template(name, config)

    # Assert: itemPrefix from config is in the template
    assert config["prefix"] in result, (
        f"Template must contain itemPrefix '{config['prefix']}'.\n"
        f"Got:\n{result[:500]}"
    )

    # Assert: label from config is in the template
    assert config["label"] in result, (
        f"Template must contain label '{config['label']}'.\n"
        f"Got:\n{result[:500]}"
    )

    # Assert: componentType from config is in the template
    assert config["componentType"] in result, (
        f"Template must contain forceComponentType '{config['componentType']}'.\n"
        f"Got:\n{result[:500]}"
    )

    # Assert: each account code from config is in the template
    for code in config["accountCodes"]:
        assert code in result, (
            f"Template must contain accountCode '{code}'.\n"
            f"Got:\n{result[:500]}"
        )
