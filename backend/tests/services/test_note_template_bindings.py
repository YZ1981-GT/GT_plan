"""CI 卡点：note_template_bindings.json schema 校验.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.1
Source: scripts/generate_note_template_bindings.py
Reqs:   R1.1 验收标准 1 — 每条 binding 必含 source / field / mode /
        account_codes 必填项。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BINDINGS_PATH = REPO_ROOT / "backend" / "data" / "note_template_bindings.json"

# 与 generator 同步：7 种合法 source / 3 种合法 mode
VALID_SOURCES = {
    "trial_balance",
    "ledger_sum",
    "aux_balance",
    "aux_ledger_aging",
    "formula",
    "prior_year_note",
    "manual",
}
VALID_MODES = {"auto", "manual", "locked"}

# binding 必填字段（Sprint 1 单测断言）
REQUIRED_BINDING_FIELDS = ("source", "field", "mode", "account_codes")


@pytest.fixture(scope="module")
def bindings_payload() -> dict[str, Any]:
    assert BINDINGS_PATH.exists(), (
        f"missing {BINDINGS_PATH}; run "
        f"`python scripts/generate_note_template_bindings.py` first"
    )
    return json.loads(BINDINGS_PATH.read_text(encoding="utf-8"))


def _iter_cell_bindings(
    payload: dict[str, Any],
):
    """Yield (section_number, table_index, row_label, semantic_key, cell_dict)."""
    for sec_num, sec_binding in payload.get("bindings", {}).items():
        for tbl in sec_binding.get("tables", []):
            ti = tbl.get("table_index")
            for row_label, row in tbl.get("rows", {}).items():
                cells = row.get("binding") or {}
                for sem_key, cell in cells.items():
                    yield sec_num, ti, row_label, sem_key, cell


# ---------------------------------------------------------------------------
# 顶层结构
# ---------------------------------------------------------------------------


def test_top_level_keys_present(bindings_payload: dict[str, Any]) -> None:
    for key in ("version", "auto_generated", "generator", "bindings"):
        assert key in bindings_payload, f"missing top-level key: {key}"


def test_version_format(bindings_payload: dict[str, Any]) -> None:
    assert isinstance(bindings_payload["version"], str)
    assert bindings_payload["version"]


def test_bindings_is_non_empty_dict(bindings_payload: dict[str, Any]) -> None:
    bindings = bindings_payload["bindings"]
    assert isinstance(bindings, dict)
    assert bindings, "bindings dict should be non-empty"


def test_section_keys_match_pattern(bindings_payload: dict[str, Any]) -> None:
    """章节 key 应为 section_number 字符串（含中文标号）."""
    for sec_num in bindings_payload["bindings"]:
        assert isinstance(sec_num, str) and sec_num
        # 至少包含中文顿号「、」
        assert "、" in sec_num, (
            f"section key looks malformed: {sec_num!r}"
        )


# ---------------------------------------------------------------------------
# section / table / row 结构
# ---------------------------------------------------------------------------


def test_each_section_has_tables(bindings_payload: dict[str, Any]) -> None:
    for sec_num, sec in bindings_payload["bindings"].items():
        assert "tables" in sec, f"section {sec_num} missing 'tables'"
        assert isinstance(sec["tables"], list) and sec["tables"], (
            f"section {sec_num} has empty tables"
        )


def test_each_table_has_header_normalize(
    bindings_payload: dict[str, Any],
) -> None:
    for sec_num, sec in bindings_payload["bindings"].items():
        for tbl in sec["tables"]:
            assert "header_normalize" in tbl, (
                f"section {sec_num} table missing header_normalize"
            )
            for hdr in tbl["header_normalize"]:
                assert "text" in hdr and "semantic" in hdr


def test_header_normalize_semantic_in_valid_set(
    bindings_payload: dict[str, Any],
) -> None:
    """header_normalize.semantic 必须 ∈ VALID_SEMANTICS."""
    from backend.app.services.note_column_semantics import VALID_SEMANTICS

    valid = set(VALID_SEMANTICS)
    invalid: list[tuple] = []
    for sec_num, sec in bindings_payload["bindings"].items():
        for ti, tbl in enumerate(sec["tables"]):
            for hdr in tbl.get("header_normalize", []):
                sem = hdr.get("semantic")
                if sem not in valid:
                    invalid.append((sec_num, ti, hdr))
    assert not invalid, f"invalid semantics: {invalid[:5]}"


# ---------------------------------------------------------------------------
# 单元格 binding 必填字段
# ---------------------------------------------------------------------------


def test_every_binding_has_required_fields(
    bindings_payload: dict[str, Any],
) -> None:
    """每条 binding 必含 source / field / mode / account_codes."""
    missing: list[tuple] = []
    for sec_num, ti, row_label, sem_key, cell in _iter_cell_bindings(
        bindings_payload
    ):
        for f in REQUIRED_BINDING_FIELDS:
            if f not in cell:
                missing.append((sec_num, ti, row_label, sem_key, f))
    assert not missing, (
        f"{len(missing)} bindings missing required fields "
        f"(first 5: {missing[:5]})"
    )


def test_every_binding_source_in_valid_set(
    bindings_payload: dict[str, Any],
) -> None:
    bad: list[tuple] = []
    for sec_num, ti, row_label, sem_key, cell in _iter_cell_bindings(
        bindings_payload
    ):
        if cell.get("source") not in VALID_SOURCES:
            bad.append((sec_num, ti, row_label, sem_key, cell.get("source")))
    assert not bad, f"invalid source values: {bad[:5]}"


def test_every_binding_mode_in_valid_set(
    bindings_payload: dict[str, Any],
) -> None:
    bad: list[tuple] = []
    for sec_num, ti, row_label, sem_key, cell in _iter_cell_bindings(
        bindings_payload
    ):
        if cell.get("mode") not in VALID_MODES:
            bad.append((sec_num, ti, row_label, sem_key, cell.get("mode")))
    assert not bad, f"invalid mode values: {bad[:5]}"


def test_account_codes_is_list(bindings_payload: dict[str, Any]) -> None:
    """account_codes 必须是 list（即便为空）."""
    bad: list[tuple] = []
    for sec_num, ti, row_label, sem_key, cell in _iter_cell_bindings(
        bindings_payload
    ):
        codes = cell.get("account_codes")
        if not isinstance(codes, list):
            bad.append((sec_num, ti, row_label, sem_key, type(codes).__name__))
        else:
            for c in codes:
                if not isinstance(c, str):
                    bad.append(
                        (sec_num, ti, row_label, sem_key, f"non-str: {c!r}")
                    )
                    break
    assert not bad, f"account_codes type errors: {bad[:5]}"


def test_field_is_non_empty_string(bindings_payload: dict[str, Any]) -> None:
    bad: list[tuple] = []
    for sec_num, ti, row_label, sem_key, cell in _iter_cell_bindings(
        bindings_payload
    ):
        f = cell.get("field")
        if not isinstance(f, str) or not f:
            bad.append((sec_num, ti, row_label, sem_key, f))
    assert not bad, f"field type errors: {bad[:5]}"


# ---------------------------------------------------------------------------
# 合计行约束
# ---------------------------------------------------------------------------


def test_subtotal_total_rows_have_formula_not_binding(
    bindings_payload: dict[str, Any],
) -> None:
    """row_type ∈ {subtotal, total} 必须有 formula + mode=auto，不写 binding."""
    bad: list[tuple] = []
    for sec_num, sec in bindings_payload["bindings"].items():
        for ti, tbl in enumerate(sec["tables"]):
            for row_label, row in tbl.get("rows", {}).items():
                if row.get("row_type") in {"subtotal", "total"}:
                    if "binding" in row:
                        bad.append(
                            (sec_num, ti, row_label, "has unexpected binding")
                        )
                    if not row.get("formula"):
                        bad.append((sec_num, ti, row_label, "missing formula"))
                    if row.get("mode") != "auto":
                        bad.append(
                            (sec_num, ti, row_label, f"mode={row.get('mode')}")
                        )
    assert not bad, f"subtotal/total row violations: {bad[:5]}"


# ---------------------------------------------------------------------------
# 自动生成元数据
# ---------------------------------------------------------------------------


def test_auto_generated_flag_true(bindings_payload: dict[str, Any]) -> None:
    assert bindings_payload.get("auto_generated") is True


def test_coverage_note_mentions_p1(bindings_payload: dict[str, Any]) -> None:
    note = bindings_payload.get("coverage_note") or ""
    assert "P-1" in note or "审计师" in note, (
        "coverage_note must reference P-1 / 审计师 followup"
    )
