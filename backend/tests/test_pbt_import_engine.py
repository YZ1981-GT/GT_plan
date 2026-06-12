"""Property 22 & 24: Import Engine PBT Tests

Property 22: 程序表导入仅更新可编辑列，只读列不变
Property 24: 审定表导入不写 audited_amount 列

**Validates: Requirements 8.2, 8.3, 9.3**

Testing framework: hypothesis
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_export.import_engine import (
    AUDIT_EDITABLE_COLUMNS,
    AUDIT_IGNORED_COLUMNS,
    PROGRAM_EDITABLE_COLUMNS,
    PROGRAM_READONLY_COLUMNS,
    WpImportEngine,
)

# ─── Hypothesis Strategies ────────────────────────────────────────────────────

_SAFE_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=15,
)

_STATUS_VALUES = st.sampled_from(["未执行", "已执行", "不适用", "进行中", ""])


@st.composite
def st_program_procedure(draw: st.DrawFn) -> dict:
    """Generate a single program procedure dict."""
    return {
        "procedure_code": draw(st.text(alphabet="ABCDEFGHIJKLMNOP0123456789", min_size=2, max_size=8)),
        "description": draw(_SAFE_TEXT),
        "execution_status": draw(_STATUS_VALUES),
        "execution_conclusion": draw(_SAFE_TEXT),
        "executor": draw(_SAFE_TEXT),
    }


@st.composite
def st_program_data(draw: st.DrawFn) -> tuple[list[dict], list[dict]]:
    """Generate server procedures and imported data with overlapping codes.

    Returns (server_procedures, imported_data) where imported_data has:
    - some rows matching server procedure_codes (will be updated)
    - some rows with new codes (will be unmatched)
    """
    # Generate server procedures
    num_server = draw(st.integers(min_value=1, max_value=5))
    server_procs = []
    for _ in range(num_server):
        server_procs.append(draw(st_program_procedure()))

    # Generate imported data: mix of matching and non-matching
    imported = []
    # Add rows that match some server codes (with potentially different editable values)
    for proc in server_procs:
        if draw(st.booleans()):
            imp_row = {
                "procedure_code": proc["procedure_code"],
                "description": draw(_SAFE_TEXT),  # imported may have different description
                "execution_status": draw(_STATUS_VALUES),
                "execution_conclusion": draw(_SAFE_TEXT),
                "executor": draw(_SAFE_TEXT),
            }
            imported.append(imp_row)

    # Add some completely new rows
    num_new = draw(st.integers(min_value=0, max_value=2))
    for _ in range(num_new):
        new_row = draw(st_program_procedure())
        # Ensure code doesn't collide with server
        new_row["procedure_code"] = "NEW_" + new_row["procedure_code"]
        imported.append(new_row)

    # Ensure at least one imported row
    if not imported:
        imp_row = {
            "procedure_code": server_procs[0]["procedure_code"],
            "description": draw(_SAFE_TEXT),
            "execution_status": draw(_STATUS_VALUES),
            "execution_conclusion": draw(_SAFE_TEXT),
            "executor": draw(_SAFE_TEXT),
        }
        imported.append(imp_row)

    return server_procs, imported


@st.composite
def st_audit_data(draw: st.DrawFn) -> tuple[list[dict], list[dict]]:
    """Generate server accounts and imported data for audit sheet import.

    Imported data will include audited_amount (which should be ignored).
    """
    num_accounts = draw(st.integers(min_value=1, max_value=5))
    server_accounts = []
    imported = []

    for i in range(num_accounts):
        code = f"{draw(st.integers(min_value=1001, max_value=9999))}"
        server_accounts.append({
            "account_code": code,
            "account_name": draw(_SAFE_TEXT),
            "unadjusted_amount": draw(
                st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
            ),
            "adjustment_amount": draw(
                st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False)
            ),
            "audited_amount": draw(
                st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
            ),
            "notes": draw(_SAFE_TEXT),
            "work_conclusion": draw(_SAFE_TEXT),
        })

        # Import row includes audited_amount (should be ignored) + editable fields
        imported.append({
            "account_code": code,
            "account_name": draw(_SAFE_TEXT),
            "audited_amount": draw(
                st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
            ),
            "notes": draw(_SAFE_TEXT),
            "work_conclusion": draw(_SAFE_TEXT),
        })

    return server_accounts, imported


# ─── Property 22: Program Sheet Editable Column Isolation ─────────────────────


class TestProgramSheetEditableColumnIsolation:
    """Property 22: 程序表导入仅更新可编辑列，只读列不变

    **Validates: Requirements 8.2, 8.3**
    """

    @given(data=st_program_data())
    @settings(max_examples=5, deadline=None)
    def test_only_editable_columns_in_updates(
        self, data: tuple[list[dict], list[dict]]
    ) -> None:
        """Updates only contain editable column keys (execution_status,
        execution_conclusion, executor) plus the matching key (procedure_code).

        **Validates: Requirements 8.2, 8.3**
        """
        server_procs, imported = data
        engine = WpImportEngine()

        result = engine.import_program_sheet(server_procs, imported)

        updates = result["updates"]
        allowed_keys = PROGRAM_EDITABLE_COLUMNS | {"procedure_code"}

        for update in updates:
            update_keys = set(update.keys())
            # All keys must be in the allowed set
            assert update_keys <= allowed_keys, (
                f"Update contains disallowed keys: {update_keys - allowed_keys}. "
                f"Only {allowed_keys} are permitted."
            )

    @given(data=st_program_data())
    @settings(max_examples=5, deadline=None)
    def test_readonly_columns_never_in_updates(
        self, data: tuple[list[dict], list[dict]]
    ) -> None:
        """Readonly columns (description) never appear as update fields.

        **Validates: Requirements 8.2, 8.3**
        """
        server_procs, imported = data
        engine = WpImportEngine()

        result = engine.import_program_sheet(server_procs, imported)

        updates = result["updates"]

        for update in updates:
            for readonly_col in PROGRAM_READONLY_COLUMNS:
                # procedure_code is used as a matching key, not as an update
                if readonly_col == "procedure_code":
                    continue
                assert readonly_col not in update, (
                    f"Readonly column '{readonly_col}' found in update: {update}"
                )

    @given(data=st_program_data())
    @settings(max_examples=5, deadline=None)
    def test_readonly_preserved_invariant(
        self, data: tuple[list[dict], list[dict]]
    ) -> None:
        """The result always asserts readonly_preserved=True.

        **Validates: Requirements 8.2, 8.3**
        """
        server_procs, imported = data
        engine = WpImportEngine()

        result = engine.import_program_sheet(server_procs, imported)

        assert result["readonly_preserved"] is True, (
            "readonly_preserved should always be True"
        )

    @given(data=st_program_data())
    @settings(max_examples=5, deadline=None)
    def test_unmatched_rows_have_no_server_code(
        self, data: tuple[list[dict], list[dict]]
    ) -> None:
        """Unmatched rows contain only codes not present in server.

        **Validates: Requirements 8.4**
        """
        server_procs, imported = data
        engine = WpImportEngine()

        result = engine.import_program_sheet(server_procs, imported)

        server_codes = {p.get("procedure_code") for p in server_procs}
        unmatched = result["unmatched"]

        for row in unmatched:
            assert row.get("procedure_code") not in server_codes, (
                f"Unmatched row has code '{row.get('procedure_code')}' "
                f"which exists in server: {server_codes}"
            )


# ─── Property 24: Audit Sheet Import Ignores Computed Columns ─────────────────


class TestAuditSheetImportIgnoresComputedColumns:
    """Property 24: 审定表导入不写 audited_amount 列

    **Validates: Requirements 9.3**
    """

    @given(data=st_audit_data())
    @settings(max_examples=5, deadline=None)
    def test_audited_amount_never_in_updates(
        self, data: tuple[list[dict], list[dict]]
    ) -> None:
        """audited_amount from imported data is never written to update results.

        **Validates: Requirements 9.3**
        """
        server_accounts, imported = data
        engine = WpImportEngine()

        result = engine.import_audit_sheet(server_accounts, imported)

        updates = result["updates"]

        for update in updates:
            assert "audited_amount" not in update, (
                f"audited_amount found in update: {update}. "
                f"This column should be ignored (system auto-calculates)."
            )

    @given(data=st_audit_data())
    @settings(max_examples=5, deadline=None)
    def test_only_editable_columns_in_audit_updates(
        self, data: tuple[list[dict], list[dict]]
    ) -> None:
        """Audit sheet updates only contain notes and work_conclusion
        (plus matching key account_code).

        **Validates: Requirements 9.3**
        """
        server_accounts, imported = data
        engine = WpImportEngine()

        result = engine.import_audit_sheet(server_accounts, imported)

        updates = result["updates"]
        allowed_keys = AUDIT_EDITABLE_COLUMNS | {"account_code"}

        for update in updates:
            update_keys = set(update.keys())
            assert update_keys <= allowed_keys, (
                f"Audit update contains disallowed keys: {update_keys - allowed_keys}. "
                f"Only {allowed_keys} are permitted. audited_amount and other "
                f"computed columns must be ignored."
            )

    @given(data=st_audit_data())
    @settings(max_examples=5, deadline=None)
    def test_ignored_columns_reported(
        self, data: tuple[list[dict], list[dict]]
    ) -> None:
        """Result reports which columns were ignored.

        **Validates: Requirements 9.3**
        """
        server_accounts, imported = data
        engine = WpImportEngine()

        result = engine.import_audit_sheet(server_accounts, imported)

        assert "ignored_columns" in result, "Result must report ignored_columns"
        assert "audited_amount" in result["ignored_columns"], (
            "audited_amount must be in ignored_columns list"
        )

    @given(data=st_audit_data())
    @settings(max_examples=5, deadline=None)
    def test_all_matched_accounts_produce_updates(
        self, data: tuple[list[dict], list[dict]]
    ) -> None:
        """Every imported row with a matching account_code in server produces an update.

        **Validates: Requirements 9.3**
        """
        server_accounts, imported = data
        engine = WpImportEngine()

        result = engine.import_audit_sheet(server_accounts, imported)

        server_codes = {acc.get("account_code") for acc in server_accounts}
        matched_import_count = sum(
            1 for row in imported
            if row.get("account_code") in server_codes
        )

        assert len(result["updates"]) == matched_import_count, (
            f"Expected {matched_import_count} updates (matched rows), "
            f"got {len(result['updates'])}"
        )
