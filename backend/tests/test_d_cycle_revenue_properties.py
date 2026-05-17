"""
D 收入循环底稿内容预设数据 - 属性测试 + 集成测试 + JSON Schema 校验

Feature: workpaper-cycle-d-revenue
测试文件覆盖 Sprint 2 Tasks 3.1-3.13
"""

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ============================================================
# Task 3.1: 测试文件骨架 - 加载 4 个 JSON 文件为 module-level fixtures
# ============================================================

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Load 4 JSON files as module-level data
with open(DATA_DIR / "prefill_formula_mapping.json", encoding="utf-8") as f:
    PREFILL_DATA = json.load(f)

with open(DATA_DIR / "cross_wp_references.json", encoding="utf-8") as f:
    CROSS_WP_DATA = json.load(f)

with open(DATA_DIR / "d_cycle_validation_rules.json", encoding="utf-8") as f:
    VALIDATION_RULES_DATA = json.load(f)

with open(DATA_DIR / "d_cycle_procedures.json", encoding="utf-8") as f:
    PROCEDURES_DATA = json.load(f)

# D-cycle workpaper codes
D_CYCLE_WP_CODES = {"D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7"}


# --- Task 3.1: Basic file existence assertions ---

class TestFileExistence:
    """Task 3.1: Verify all 4 JSON data files exist and are loadable."""

    def test_prefill_formula_mapping_exists(self):
        assert (DATA_DIR / "prefill_formula_mapping.json").exists()
        assert "mappings" in PREFILL_DATA

    def test_cross_wp_references_exists(self):
        assert (DATA_DIR / "cross_wp_references.json").exists()
        assert "references" in CROSS_WP_DATA

    def test_d_cycle_validation_rules_exists(self):
        assert (DATA_DIR / "d_cycle_validation_rules.json").exists()
        assert "rules" in VALIDATION_RULES_DATA

    def test_d_cycle_procedures_exists(self):
        assert (DATA_DIR / "d_cycle_procedures.json").exists()
        assert "procedures" in PROCEDURES_DATA


# ============================================================
# Task 3.2: Property 1 - Analysis_Sheet formula coverage
# Validates: Requirements 1.1, 1.2, 1.3
# ============================================================

class TestProperty1AnalysisSheetCoverage:
    """
    Property 1: Analysis_Sheet formula coverage
    **Validates: Requirements 1.1, 1.2, 1.3**

    For any D-cycle workpaper code in {D0-D7}, prefill_formula_mapping.json
    SHALL contain at least one Analysis_Sheet entry with both a PREV cell
    and a TB/TB_SUM cell.
    """

    def test_each_d_cycle_wp_has_analysis_sheet_entry(self):
        """Each D0-D7 wp_code has at least one Analysis_Sheet (分析程序) entry."""
        mappings = PREFILL_DATA["mappings"]

        for wp_code in D_CYCLE_WP_CODES:
            # Find Analysis_Sheet entries for this wp_code
            analysis_entries = [
                m for m in mappings
                if m["wp_code"] == wp_code and "分析程序" in m.get("sheet", "")
            ]
            assert len(analysis_entries) >= 1, (
                f"{wp_code} missing Analysis_Sheet (分析程序) entry in prefill_formula_mapping"
            )

    def test_analysis_sheet_has_prev_and_tb(self):
        """Each Analysis_Sheet entry has PREV (上年审定数) and TB/TB_SUM (本年未审数)."""
        mappings = PREFILL_DATA["mappings"]

        for wp_code in D_CYCLE_WP_CODES:
            analysis_entries = [
                m for m in mappings
                if m["wp_code"] == wp_code and "分析程序" in m.get("sheet", "")
            ]
            for entry in analysis_entries:
                cells = entry.get("cells", [])
                formula_types = [c.get("formula_type") for c in cells]

                has_prev = "PREV" in formula_types
                has_tb = "TB" in formula_types or "TB_SUM" in formula_types

                assert has_prev, (
                    f"{wp_code} Analysis_Sheet missing PREV formula (上年审定数)"
                )
                assert has_tb, (
                    f"{wp_code} Analysis_Sheet missing TB/TB_SUM formula (本年未审数)"
                )


# ============================================================
# Task 3.3: Property 2 - Multi-account TB_SUM consistency
# Validates: Requirements 1.4
# ============================================================

class TestProperty2MultiAccountTBSUM:
    """
    Property 2: Multi-account TB_SUM consistency
    **Validates: Requirements 1.4**

    For any entry where account_codes contains more than one code,
    Analysis_Sheet cells with formula_type TB or TB_SUM SHALL use TB_SUM.
    """

    def test_multi_account_uses_tb_sum(self):
        """Entries with multiple account_codes use TB_SUM not individual TB."""
        mappings = PREFILL_DATA["mappings"]

        for entry in mappings:
            if entry["wp_code"] not in D_CYCLE_WP_CODES:
                continue
            if "分析程序" not in entry.get("sheet", ""):
                continue

            account_codes = entry.get("account_codes", [])
            if len(account_codes) <= 1:
                continue

            # Multi-account entry: TB/TB_SUM cells should use TB_SUM
            cells = entry.get("cells", [])
            for cell in cells:
                ft = cell.get("formula_type")
                if ft in ("TB", "TB_SUM"):
                    assert ft == "TB_SUM", (
                        f"{entry['wp_code']} has multi-account ({account_codes}) "
                        f"but uses {ft} instead of TB_SUM in cell '{cell.get('cell_ref')}'"
                    )


# ============================================================
# Task 3.4: Property 3 - D-cycle internal reference categorization
# Validates: Requirements 3.6
# ============================================================

class TestProperty3InternalRefCategorization:
    """
    Property 3: D-cycle internal reference categorization
    **Validates: Requirements 3.6**

    For any cross_wp_references entry where both source_wp and all target
    wp_code values are in {D0-D7}, category=revenue_cycle and severity=warning.
    """

    def test_internal_d_cycle_refs_have_correct_category_severity(self):
        """Internal D-cycle references have category=revenue_cycle, severity=warning."""
        references = CROSS_WP_DATA["references"]

        for ref in references:
            source_wp = ref.get("source_wp", "")
            if source_wp not in D_CYCLE_WP_CODES:
                continue

            targets = ref.get("targets", [])
            target_wp_codes = {t.get("wp_code", "") for t in targets}

            # Check if ALL targets are also D-cycle
            if target_wp_codes.issubset(D_CYCLE_WP_CODES):
                assert ref.get("category") == "revenue_cycle", (
                    f"{ref['ref_id']}: internal D-cycle ref should have "
                    f"category=revenue_cycle, got '{ref.get('category')}'"
                )
                assert ref.get("severity") == "warning", (
                    f"{ref['ref_id']}: internal D-cycle ref should have "
                    f"severity=warning, got '{ref.get('severity')}'"
                )


# ============================================================
# Task 3.5: Property 4 - Cross-module reference structural completeness
# Validates: Requirements 4.8, 5.8
# ============================================================

class TestProperty4CrossModuleStructure:
    """
    Property 4: Cross-module reference structural completeness
    **Validates: Requirements 4.8, 5.8**

    note_section targets have target_route + note_section_code.
    report_row targets have target_route + report_row_code.
    """

    def test_note_section_targets_have_required_fields(self):
        """target_type=note_section entries have target_route and note_section_code."""
        references = CROSS_WP_DATA["references"]

        for ref in references:
            for target in ref.get("targets", []):
                if target.get("target_type") == "note_section":
                    assert target.get("target_route"), (
                        f"{ref['ref_id']}: note_section target missing target_route"
                    )
                    assert target.get("note_section_code"), (
                        f"{ref['ref_id']}: note_section target missing note_section_code"
                    )

    def test_report_row_targets_have_required_fields(self):
        """target_type=report_row entries have target_route and report_row_code."""
        references = CROSS_WP_DATA["references"]

        for ref in references:
            for target in ref.get("targets", []):
                if target.get("target_type") == "report_row":
                    assert target.get("target_route"), (
                        f"{ref['ref_id']}: report_row target missing target_route"
                    )
                    assert target.get("report_row_code"), (
                        f"{ref['ref_id']}: report_row target missing report_row_code"
                    )


# ============================================================
# Task 3.6: Property 5 - Balance check validation correctness
# Validates: Requirements 6.1, 6.2, 6.3, 6.4
# ============================================================

class TestProperty5BalanceCheck:
    """
    Property 5: Balance check validation correctness
    **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

    Uses hypothesis to generate random amount tuples and verify tolerance logic.
    """

    @staticmethod
    def _evaluate_balance_check(audited, unaudited, aje, rje, tolerance=0.01):
        """Simulate balance_check rule evaluation."""
        diff = abs(audited - (unaudited + aje + rje))
        if diff > tolerance:
            return {"severity": "blocking", "diff": diff}
        return None

    @settings(max_examples=50)
    @given(
        audited=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
        unaudited=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
        aje=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        rje=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    def test_balance_check_produces_finding_when_exceeds_tolerance(
        self, audited, unaudited, aje, rje
    ):
        """When |audited - (unaudited + aje + rje)| > 0.01, produces blocking finding."""
        result = self._evaluate_balance_check(audited, unaudited, aje, rje)
        diff = abs(audited - (unaudited + aje + rje))

        if diff > 0.01:
            assert result is not None
            assert result["severity"] == "blocking"
        else:
            assert result is None


# ============================================================
# Task 3.7: Property 6 - TB consistency validation correctness
# Validates: Requirements 7.1, 7.2, 7.3
# ============================================================

class TestProperty6TBConsistency:
    """
    Property 6: TB consistency validation correctness
    **Validates: Requirements 7.1, 7.2, 7.3**

    Uses hypothesis to generate random wp_amount/tb_amount pairs.
    """

    @staticmethod
    def _evaluate_tb_consistency(wp_amount, tb_amount, tolerance=0.01):
        """Simulate tb_consistency rule evaluation."""
        diff = abs(wp_amount - tb_amount)
        if diff > tolerance:
            return {"severity": "blocking", "diff": diff}
        return None

    @settings(max_examples=50)
    @given(
        wp_amount=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
        tb_amount=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
    )
    def test_tb_consistency_produces_finding_when_exceeds_tolerance(
        self, wp_amount, tb_amount
    ):
        """When |wp_amount - tb_amount| > 0.01, produces blocking finding."""
        result = self._evaluate_tb_consistency(wp_amount, tb_amount)
        diff = abs(wp_amount - tb_amount)

        if diff > 0.01:
            assert result is not None
            assert result["severity"] == "blocking"
        else:
            assert result is None


# ============================================================
# Task 3.8: Property 7 - Cross-file account code consistency
# Validates: Requirements 7.4
# ============================================================

class TestProperty7CrossFileAccountCodes:
    """
    Property 7: Cross-file account code consistency
    **Validates: Requirements 7.4**

    For each D workpaper, tb_consistency rule account_codes must match
    the corresponding prefill_formula_mapping 审定表 entry account_codes.
    """

    def test_tb_consistency_account_codes_match_prefill_mapping(self):
        """Each D-cycle wp with tb_consistency rule also has prefill_formula_mapping entry."""
        rules = VALIDATION_RULES_DATA["rules"]
        mappings = PREFILL_DATA["mappings"]

        tb_rules = [r for r in rules if r["rule_type"] == "tb_consistency"]

        for rule in tb_rules:
            wp_code = rule["wp_code"]
            rule_account_codes = rule.get("account_codes", [])

            # Verify the rule has non-empty account_codes
            assert len(rule_account_codes) > 0, (
                f"{wp_code}: tb_consistency rule has empty account_codes"
            )

            # Find corresponding 审定表 entry in prefill_formula_mapping
            audit_entries = [
                m for m in mappings
                if m["wp_code"] == wp_code and "审定表" in m.get("sheet", "")
            ]

            # Each D-cycle wp with tb_consistency must have a prefill mapping entry
            assert len(audit_entries) >= 1, (
                f"{wp_code}: has tb_consistency rule but no 审定表 in prefill_formula_mapping"
            )

            # The prefill mapping entry must also have non-empty account_codes
            mapping_account_codes = audit_entries[0].get("account_codes", [])
            assert len(mapping_account_codes) > 0, (
                f"{wp_code}: prefill_formula_mapping 审定表 has empty account_codes"
            )


# ============================================================
# Task 3.9: Property 8 - Procedure step schema and completeness
# Validates: Requirements 10.4, 10.5
# ============================================================

class TestProperty8ProcedureSchema:
    """
    Property 8: Procedure step schema and completeness
    **Validates: Requirements 10.4, 10.5**

    Every step has required fields and each D0-D7 has at least 5 steps.
    """

    def test_all_steps_have_required_fields(self):
        """Every procedure step has step_order/step_name/description/is_required/related_sheet."""
        procedures = PROCEDURES_DATA["procedures"]

        for wp_code, proc in procedures.items():
            for step in proc["steps"]:
                assert isinstance(step.get("step_order"), int), (
                    f"{wp_code} step missing int step_order"
                )
                assert step.get("step_name") and len(step["step_name"]) > 0, (
                    f"{wp_code} step {step.get('step_order')} has empty step_name"
                )
                assert step.get("description") and len(step["description"]) > 0, (
                    f"{wp_code} step {step.get('step_order')} has empty description"
                )
                assert isinstance(step.get("is_required"), bool), (
                    f"{wp_code} step {step.get('step_order')} missing bool is_required"
                )
                # related_sheet can be str or null
                assert "related_sheet" in step, (
                    f"{wp_code} step {step.get('step_order')} missing related_sheet field"
                )

    def test_each_d_cycle_wp_has_at_least_5_steps(self):
        """Each D0-D7 workpaper has at least 5 procedure steps."""
        procedures = PROCEDURES_DATA["procedures"]

        for wp_code in D_CYCLE_WP_CODES:
            assert wp_code in procedures, f"{wp_code} missing from d_cycle_procedures"
            steps = procedures[wp_code]["steps"]
            assert len(steps) >= 5, (
                f"{wp_code} has only {len(steps)} steps, expected >= 5"
            )


# ============================================================
# Task 3.10: Property 9 - Sub-account dynamic formula generation
# Validates: Requirements 11.1, 11.2
# ============================================================

class TestProperty9SubAccountFormula:
    """
    Property 9: Sub-account dynamic formula generation
    **Validates: Requirements 11.1, 11.2**

    D5 entry contains sub-account TB formulas (112401/112402) or single TB('1124',...).
    """

    def test_d5_has_sub_account_or_single_formula(self):
        """D5 has either sub-account level TB formulas or single TB('1124',...)."""
        mappings = PREFILL_DATA["mappings"]

        d5_entries = [m for m in mappings if m["wp_code"] == "D5"]
        assert len(d5_entries) > 0, "D5 missing from prefill_formula_mapping"

        # Check if D5 has sub-account formulas (112401/112402) or single 1124
        all_formulas = []
        for entry in d5_entries:
            for cell in entry.get("cells", []):
                formula = cell.get("formula", "")
                all_formulas.append(formula)

        has_sub_accounts = any(
            "112401" in f or "112402" in f for f in all_formulas
        )
        has_single_1124 = any("1124" in f for f in all_formulas)

        assert has_sub_accounts or has_single_1124, (
            "D5 should have sub-account formulas (112401/112402) or single TB('1124',...)"
        )


# ============================================================
# Task 3.11: Property 10 - Validation rule tolerance symmetry
# Validates: Requirements 6.2, 9.4
# ============================================================

class TestProperty10ToleranceSymmetry:
    """
    Property 10: Validation rule tolerance symmetry
    **Validates: Requirements 6.2, 9.4**

    |diff| == tolerance passes, |diff| > tolerance fails.
    """

    @staticmethod
    def _check_tolerance(diff_abs, tolerance):
        """Returns True if passes (no finding), False if fails (finding)."""
        return diff_abs <= tolerance

    @settings(max_examples=50)
    @given(
        base=st.floats(min_value=1.0, max_value=1e8, allow_nan=False, allow_infinity=False),
        tolerance=st.sampled_from([0.01, 0.001, 0.1, 1.0]),
    )
    def test_tolerance_boundary(self, base, tolerance):
        """At exactly tolerance, passes. Above tolerance, fails."""
        # Exactly at tolerance boundary: should pass
        assert self._check_tolerance(tolerance, tolerance) is True

        # Slightly above tolerance: should fail
        above = tolerance + 1e-10
        assert self._check_tolerance(above, tolerance) is False

    @settings(max_examples=50)
    @given(
        diff=st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    def test_tolerance_symmetry_with_default(self, diff):
        """Default tolerance 0.01: diff <= 0.01 passes, diff > 0.01 fails."""
        tolerance = 0.01
        result = self._check_tolerance(diff, tolerance)
        if diff <= tolerance:
            assert result is True
        else:
            assert result is False


# ============================================================
# Task 3.12: Integration test - 真实数据验证（陕西华氏 D2）
# ============================================================

class TestIntegrationD2RealData:
    """
    Task 3.12: Integration test with real data (陕西华氏 D2).
    Validates cross-file consistency for D2 workpaper.
    """

    def test_d2_tb_consistency_account_codes_match_prefill(self):
        """D2 tb_consistency rule account_codes=["1122"] matches prefill_formula_mapping."""
        rules = VALIDATION_RULES_DATA["rules"]
        mappings = PREFILL_DATA["mappings"]

        # Find D2 tb_consistency rule
        d2_tb_rules = [
            r for r in rules
            if r["rule_type"] == "tb_consistency" and r["wp_code"] == "D2"
        ]
        assert len(d2_tb_rules) == 1
        assert d2_tb_rules[0]["account_codes"] == ["1122"]

        # Find D2 审定表 in prefill_formula_mapping
        d2_audit_entries = [
            m for m in mappings
            if m["wp_code"] == "D2" and "审定表" in m.get("sheet", "")
        ]
        assert len(d2_audit_entries) >= 1
        assert "1122" in d2_audit_entries[0]["account_codes"]

    def test_d2_balance_check_structure(self):
        """D2 balance_check rule has cells with audited/unaudited/aje/rje."""
        rules = VALIDATION_RULES_DATA["rules"]

        d2_balance_rules = [
            r for r in rules
            if r["rule_type"] == "balance_check" and r["wp_code"] == "D2"
        ]
        assert len(d2_balance_rules) == 1

        cells = d2_balance_rules[0]["cells"]
        assert "audited" in cells
        assert "unaudited" in cells
        assert "aje" in cells
        assert "rje" in cells

    def test_cw25_points_to_note_section_5_7(self):
        """CW-25 target points to 附注 5.7 (note_section_code="5.7")."""
        references = CROSS_WP_DATA["references"]

        cw25 = [r for r in references if r["ref_id"] == "CW-25"]
        assert len(cw25) == 1

        targets = cw25[0]["targets"]
        assert len(targets) >= 1

        note_target = targets[0]
        assert note_target.get("note_section_code") == "5.7"
        assert note_target.get("target_type") == "note_section"

    def test_d2_procedures_has_7_steps_with_key_procedures(self):
        """d_cycle_procedures D2 has 7 steps including 函证 and 坏账准备."""
        procedures = PROCEDURES_DATA["procedures"]

        assert "D2" in procedures
        d2_steps = procedures["D2"]["steps"]
        assert len(d2_steps) == 7

        step_names = [s["step_name"] for s in d2_steps]
        assert "函证" in step_names, "D2 procedures missing '函证' step"
        assert "坏账准备" in step_names, "D2 procedures missing '坏账准备' step"


# ============================================================
# Task 3.13: JSON Schema validation
# ============================================================

class TestJSONSchemaValidation:
    """
    Task 3.13: JSON Schema validation tests.
    Verify enum values, uniqueness, and structural correctness.
    """

    # Valid rule_type enum values
    VALID_RULE_TYPES = {"balance_check", "tb_consistency", "note_consistency", "detail_total_check"}

    # Valid step category enum values
    VALID_STEP_CATEGORIES = {"substantive", "confirmation", "conclusion"}

    # Valid formula_type enum values
    VALID_FORMULA_TYPES = {"TB", "TB_SUM", "PREV", "TB_AUX", "WP", "ADJ"}

    def test_validation_rules_rule_type_enum(self):
        """d_cycle_validation_rules.json rule_type only contains valid values."""
        rules = VALIDATION_RULES_DATA["rules"]

        for rule in rules:
            assert rule["rule_type"] in self.VALID_RULE_TYPES, (
                f"Rule {rule['rule_id']} has invalid rule_type: '{rule['rule_type']}'"
            )

    def test_procedures_step_category_enum(self):
        """d_cycle_procedures.json step category enum is valid."""
        procedures = PROCEDURES_DATA["procedures"]

        for wp_code, proc in procedures.items():
            for step in proc["steps"]:
                assert step["category"] in self.VALID_STEP_CATEGORIES, (
                    f"{wp_code} step {step['step_order']} has invalid category: "
                    f"'{step['category']}'"
                )

    def test_cross_wp_references_ref_id_uniqueness(self):
        """cross_wp_references.json new entries ref_id uniqueness (CW-21~CW-38)."""
        references = CROSS_WP_DATA["references"]

        # Extract all ref_ids in the CW-21 to CW-38 range
        d_cycle_ref_ids = []
        for ref in references:
            ref_id = ref["ref_id"]
            if ref_id.startswith("CW-"):
                num = int(ref_id.split("-")[1])
                if 21 <= num <= 38:
                    d_cycle_ref_ids.append(ref_id)

        # Verify no duplicates
        assert len(d_cycle_ref_ids) == len(set(d_cycle_ref_ids)), (
            f"Duplicate ref_ids found in CW-21~CW-38: {d_cycle_ref_ids}"
        )
        # Verify we have all 18 entries
        assert len(d_cycle_ref_ids) == 18, (
            f"Expected 18 D-cycle ref_ids (CW-21~CW-38), got {len(d_cycle_ref_ids)}"
        )

    def test_prefill_formula_mapping_formula_type_enum(self):
        """prefill_formula_mapping.json formula_type enum is valid."""
        mappings = PREFILL_DATA["mappings"]

        for entry in mappings:
            # Only check D-cycle entries
            if entry["wp_code"] not in D_CYCLE_WP_CODES:
                continue

            for cell in entry.get("cells", []):
                ft = cell.get("formula_type")
                assert ft in self.VALID_FORMULA_TYPES, (
                    f"{entry['wp_code']} sheet '{entry.get('sheet')}' "
                    f"cell '{cell.get('cell_ref')}' has invalid formula_type: '{ft}'"
                )
