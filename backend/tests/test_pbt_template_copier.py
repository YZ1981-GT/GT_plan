"""Property 19, 20, 21: TemplateCopier PBT Tests

Property 19: 复制后目标底稿 UUID≠源、project_id=目标、status=draft、review_status=not_submitted
Property 20: 复制后动态表区域数值/日期/文本列为空，结构/公式/只读列保留
Property 21: 批量复制数量=源循环非删除底稿数

**Validates: Requirements 7.1, 7.2, 7.3, 7.5, 7.6**

Testing framework: hypothesis
"""

from __future__ import annotations

from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_export.template_copier import TemplateCopier

# ─── Hypothesis Strategies ────────────────────────────────────────────────────

_CYCLES = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "S"]
_STATUSES = ["draft", "in_review", "approved"]


@st.composite
def st_source_workpaper(draw: st.DrawFn, audit_cycle: str | None = None) -> dict:
    """Generate a source workpaper dict for template copy testing."""
    wp_code = draw(st.from_regex(r"[A-Z]\d{1,2}", fullmatch=True))
    wp_name = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_- "),
        min_size=1,
        max_size=15,
    ))
    cycle = audit_cycle or draw(st.sampled_from(_CYCLES))
    status = draw(st.sampled_from(_STATUSES))
    is_deleted = draw(st.just(False))  # Non-deleted for meaningful tests

    # Generate data with some business values
    rows = []
    num_rows = draw(st.integers(min_value=1, max_value=5))
    for i in range(num_rows):
        row = {
            "procedure_code": f"P{i+1:03d}",
            "description": f"程序步骤 {i+1}",
            "amount": draw(st.floats(min_value=0.01, max_value=999999.99, allow_nan=False)),
            "date_field": "2025-06-15",
            "balance": draw(st.floats(min_value=0.01, max_value=999999.99, allow_nan=False)),
            "conclusion": draw(st.text(min_size=0, max_size=20)),
        }
        rows.append(row)

    data = {"rows": rows}

    schema = {
        "sheets": {
            "Sheet1": {
                "dynamic_table": {
                    "columns": {
                        "A": {"field": "procedure_code", "type": "text", "readonly": True},
                        "B": {"field": "description", "type": "text", "readonly": True},
                        "C": {"field": "amount", "type": "number", "readonly": False},
                        "D": {"field": "date_field", "type": "date", "readonly": False},
                        "E": {"field": "balance", "type": "number", "readonly": False},
                        "F": {"field": "conclusion", "type": "text", "readonly": False},
                    },
                    "start_row": 2,
                }
            }
        }
    }

    return {
        "wp_code": wp_code,
        "wp_name": wp_name,
        "audit_cycle": cycle,
        "status": status,
        "review_status": "approved",
        "is_deleted": is_deleted,
        "file_format": "xlsx",
        "data": data,
        "schema": schema,
        "wp_id": uuid4(),
        "project_id": uuid4(),
    }


@st.composite
def st_source_workpaper_with_formula(draw: st.DrawFn) -> dict:
    """Generate a source workpaper with formula values that should be preserved."""
    wp = draw(st_source_workpaper())

    # Add formula values to some rows
    if wp["data"]["rows"]:
        wp["data"]["rows"][0]["amount"] = "=SUM(C3:C10)"
        wp["data"]["rows"][0]["balance"] = "=C2+D2-E2"

    return wp


@st.composite
def st_cycle_workpapers(
    draw: st.DrawFn,
    target_cycle: str | None = None,
) -> tuple[list[dict], str]:
    """Generate a list of workpapers for a specific cycle, some deleted."""
    cycle = target_cycle or draw(st.sampled_from(_CYCLES))
    count = draw(st.integers(min_value=2, max_value=6))

    workpapers = []
    for i in range(count):
        wp = draw(st_source_workpaper(audit_cycle=cycle))
        wp["wp_code"] = f"{cycle}{i+1}"  # Ensure unique codes within cycle
        # Some may be deleted
        wp["is_deleted"] = draw(st.sampled_from([False, False, False, True]))  # 25% deleted
        workpapers.append(wp)

    # Add some workpapers from other cycles (should be excluded)
    other_cycle = draw(st.sampled_from([c for c in _CYCLES if c != cycle]))
    extra = draw(st_source_workpaper(audit_cycle=other_cycle))
    extra["wp_code"] = f"{other_cycle}99"
    workpapers.append(extra)

    return workpapers, cycle


# ─── Property 19: Template Copy Produces Valid Draft ──────────────────────────


class TestTemplateCopyProducesValidDraft:
    """Property 19: 复制后目标底稿 UUID≠源、project_id=目标、status=draft、review_status=not_submitted

    **Validates: Requirements 7.1, 7.3, 7.6**
    """

    @given(
        source_wp=st_source_workpaper(),
        target_project_id=st.uuids(),
    )
    @settings(max_examples=5)
    def test_copy_produces_valid_draft(
        self,
        source_wp: dict,
        target_project_id: UUID,
    ) -> None:
        """复制后目标底稿 UUID≠源、project_id=目标、status=draft、review_status=not_submitted。

        **Validates: Requirements 7.1, 7.3, 7.6**
        """
        copier = TemplateCopier()

        result = copier.copy_single(
            source_wp=source_wp,
            target_project_id=target_project_id,
            overwrite=False,
            existing_codes=set(),  # No existing codes
        )

        # Status should be "copied"
        assert result.status == "copied", f"Expected 'copied', got {result.status!r}"

        # Target UUID must be different from source
        assert result.target_wp_id is not None
        assert result.target_wp_id != source_wp["wp_id"], (
            "Target UUID must differ from source UUID"
        )

        # Check target record
        target_record = result.target_record  # type: ignore[attr-defined]

        # project_id = target
        assert target_record["project_id"] == target_project_id, (
            f"project_id should be target: {target_record['project_id']} != {target_project_id}"
        )

        # status = draft
        assert target_record["status"] == "draft", (
            f"status should be 'draft': {target_record['status']!r}"
        )

        # review_status = not_submitted
        assert target_record["review_status"] == "not_submitted", (
            f"review_status should be 'not_submitted': {target_record['review_status']!r}"
        )

        # wp_code preserved
        assert target_record["wp_code"] == source_wp["wp_code"]

        # wp_id is new UUID
        assert target_record["wp_id"] == result.target_wp_id

    @given(
        source_wp=st_source_workpaper(),
        target_project_id=st.uuids(),
    )
    @settings(max_examples=5)
    def test_skip_when_code_exists_no_overwrite(
        self,
        source_wp: dict,
        target_project_id: UUID,
    ) -> None:
        """当 overwrite=False 且目标已有同 wp_code 时跳过。

        **Validates: Requirements 7.4**
        """
        copier = TemplateCopier()
        existing_codes = {source_wp["wp_code"]}

        result = copier.copy_single(
            source_wp=source_wp,
            target_project_id=target_project_id,
            overwrite=False,
            existing_codes=existing_codes,
        )

        assert result.status == "skipped"
        assert result.target_wp_id is None


# ─── Property 20: Business Data Cleared on Copy ──────────────────────────────


class TestBusinessDataClearedOnCopy:
    """Property 20: 复制后动态表区域数值/日期/文本列为空，结构/公式/只读列保留

    **Validates: Requirements 7.2**
    """

    @given(
        source_wp=st_source_workpaper(),
        target_project_id=st.uuids(),
    )
    @settings(max_examples=5)
    def test_business_data_cleared(
        self,
        source_wp: dict,
        target_project_id: UUID,
    ) -> None:
        """复制后动态表区域数值/日期/文本列为空，结构/公式/只读列保留。

        **Validates: Requirements 7.2**
        """
        copier = TemplateCopier()

        result = copier.copy_single(
            source_wp=source_wp,
            target_project_id=target_project_id,
            overwrite=False,
            existing_codes=set(),
        )

        assert result.status == "copied"
        target_record = result.target_record  # type: ignore[attr-defined]
        target_data = target_record["data"]

        # The data should have rows (structure preserved)
        assert "rows" in target_data, "Structure (rows key) should be preserved"

        rows = target_data["rows"]
        assert len(rows) == len(source_wp["data"]["rows"]), (
            "Row count should be preserved (structure)"
        )

        for row in rows:
            # Readonly columns preserved (procedure_code, description)
            assert row.get("procedure_code") is not None, (
                "Readonly field 'procedure_code' should be preserved"
            )
            assert row.get("description") is not None, (
                "Readonly field 'description' should be preserved"
            )

            # Non-readonly columns cleared (amount, date_field, balance, conclusion)
            assert row.get("amount") is None, (
                f"Number field 'amount' should be cleared, got {row.get('amount')!r}"
            )
            assert row.get("date_field") is None, (
                f"Date field 'date_field' should be cleared, got {row.get('date_field')!r}"
            )
            assert row.get("balance") is None, (
                f"Number field 'balance' should be cleared, got {row.get('balance')!r}"
            )
            assert row.get("conclusion") is None, (
                f"Text field 'conclusion' should be cleared, got {row.get('conclusion')!r}"
            )

    @given(
        source_wp=st_source_workpaper_with_formula(),
        target_project_id=st.uuids(),
    )
    @settings(max_examples=5)
    def test_formulas_preserved_on_copy(
        self,
        source_wp: dict,
        target_project_id: UUID,
    ) -> None:
        """公式（以 = 开头的字符串）在复制后保留。

        **Validates: Requirements 7.2**
        """
        copier = TemplateCopier()

        result = copier.copy_single(
            source_wp=source_wp,
            target_project_id=target_project_id,
            overwrite=False,
            existing_codes=set(),
        )

        assert result.status == "copied"
        target_record = result.target_record  # type: ignore[attr-defined]
        target_data = target_record["data"]
        rows = target_data["rows"]

        # First row should have formulas preserved
        if rows:
            first_row = rows[0]
            # If source had formula, it should be preserved
            source_first_row = source_wp["data"]["rows"][0]
            if isinstance(source_first_row.get("amount"), str) and source_first_row["amount"].startswith("="):
                assert first_row.get("amount") == source_first_row["amount"], (
                    f"Formula should be preserved: {first_row.get('amount')!r}"
                )
            if isinstance(source_first_row.get("balance"), str) and source_first_row["balance"].startswith("="):
                assert first_row.get("balance") == source_first_row["balance"], (
                    f"Formula should be preserved: {first_row.get('balance')!r}"
                )


# ─── Property 21: Batch Copy Covers Entire Cycle ─────────────────────────────


class TestBatchCopyCoversEntireCycle:
    """Property 21: 批量复制数量=源循环非删除底稿数

    **Validates: Requirements 7.5**
    """

    @given(
        data=st_cycle_workpapers(),
        target_project_id=st.uuids(),
    )
    @settings(max_examples=5)
    def test_batch_copy_covers_entire_cycle(
        self,
        data: tuple[list[dict], str],
        target_project_id: UUID,
    ) -> None:
        """批量复制数量=源循环非删除底稿数。

        **Validates: Requirements 7.5**
        """
        source_workpapers, audit_cycle = data
        copier = TemplateCopier()

        results = copier.copy_cycle(
            source_workpapers=source_workpapers,
            target_project_id=target_project_id,
            audit_cycle=audit_cycle,
            overwrite=False,
            existing_codes=set(),
        )

        # Count non-deleted workpapers in the target cycle
        expected_count = sum(
            1 for wp in source_workpapers
            if wp.get("audit_cycle") == audit_cycle
            and not wp.get("is_deleted", False)
        )

        # Results count should match
        assert len(results) == expected_count, (
            f"Batch copy count {len(results)} != "
            f"expected non-deleted cycle count {expected_count}"
        )

        # All results should be for the correct cycle
        for result in results:
            assert result.status in ("copied", "skipped"), (
                f"Unexpected status: {result.status!r}"
            )

    @given(
        data=st_cycle_workpapers(),
        target_project_id=st.uuids(),
    )
    @settings(max_examples=5)
    def test_batch_copy_excludes_deleted(
        self,
        data: tuple[list[dict], str],
        target_project_id: UUID,
    ) -> None:
        """批量复制排除已删除底稿。

        **Validates: Requirements 7.5**
        """
        source_workpapers, audit_cycle = data
        copier = TemplateCopier()

        results = copier.copy_cycle(
            source_workpapers=source_workpapers,
            target_project_id=target_project_id,
            audit_cycle=audit_cycle,
            overwrite=False,
            existing_codes=set(),
        )

        # Count deleted in cycle
        deleted_in_cycle = sum(
            1 for wp in source_workpapers
            if wp.get("audit_cycle") == audit_cycle
            and wp.get("is_deleted", False)
        )

        # Total in cycle (deleted + non-deleted)
        total_in_cycle = sum(
            1 for wp in source_workpapers
            if wp.get("audit_cycle") == audit_cycle
        )

        # Results should be total minus deleted
        assert len(results) == total_in_cycle - deleted_in_cycle
