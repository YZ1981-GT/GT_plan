"""Targeted unit tests for Capability Ledger v2 model and migration (task 1.2)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_CHECK = _REPO / "backend" / "scripts" / "check"
sys.path.insert(0, str(_CHECK))

from capability_ledger import (  # noqa: E402
    CAPABILITIES,
    LedgerFormatError,
    capability_record,
    normalize_ledger,
)
from generate_coverage_ledger import generate_ledger  # noqa: E402

_MIGRATION_PATH = (
    _REPO / "backend" / "scripts" / "migrate"
    / "migrate_coverage_ledger_v2.py"
)
_SPEC = importlib.util.spec_from_file_location("migrate_coverage_ledger_v2", _MIGRATION_PATH)
assert _SPEC and _SPEC.loader
migration = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(migration)


def _legacy(exemption=None, detected=None, shell_wrapped=False) -> dict:
    entry = {
        "shellWrapped": shell_wrapped,
        "detected": detected or {},
    }
    if exemption is not None:
        entry["exemption"] = exemption
    return {"generatedAt": "2026-07-13T00:00:00Z", "entries": {"D2": entry}}


def test_legacy_exemption_is_migrated_to_one_capability_only() -> None:
    ledger, warnings = normalize_ledger(_legacy(
        exemption={
            "reason": "无金额表格渲染",
            "approvedBy": "manager",
            "at": "2026-07-13",
        },
        detected={"review": True},
    ))
    records = ledger["entries"]["D2"]["capabilities"]

    assert warnings == []
    assert records["displayPrefs"]["status"] == "exempt"
    assert records["review"]["status"] == "covered"
    assert records["version"]["status"] == "unknown"
    assert records["displayPrefs"]["exemption"]["approvedAt"] == "2026-07-13"
    assert "exemption" not in ledger["entries"]["D2"]


def test_ambiguous_legacy_exemption_never_becomes_blanket_exemption() -> None:
    ledger, warnings = normalize_ledger(_legacy(
        exemption={"reason": "免除复核、版本和保存", "approvedBy": "manager"}
    ))
    records = ledger["entries"]["D2"]["capabilities"]

    assert warnings
    assert all(record["status"] != "exempt" for record in records.values())


def test_shell_compatibility_covers_runtime_capabilities_not_business_capabilities() -> None:
    ledger, _ = normalize_ledger(_legacy(shell_wrapped=True))
    records = ledger["entries"]["D2"]["capabilities"]

    for capability in ("displayPrefs", "agingConfig", "version", "review", "ai"):
        assert records[capability]["status"] == "covered"
    for capability in ("importExport", "acnr", "persistence"):
        assert records[capability]["status"] == "unknown"


def test_v2_rejects_entry_level_exemption() -> None:
    records = {
        capability: {"status": "unknown", "evidence": [], "exemption": None}
        for capability in CAPABILITIES
    }
    with pytest.raises(LedgerFormatError, match="entry-level exemption"):
        normalize_ledger({
            "schemaVersion": 2,
            "entries": {
                "D2": {
                    "exemption": {"reason": "blanket"},
                    "capabilities": records,
                }
            },
        })


def test_capability_record_rejects_invalid_evidence_and_exemption_combinations() -> None:
    with pytest.raises(LedgerFormatError, match="evidence must be a list"):
        capability_record("covered", "source.py:Symbol")  # type: ignore[arg-type]
    with pytest.raises(LedgerFormatError, match="requires capability exemption"):
        capability_record("exempt")
    with pytest.raises(LedgerFormatError, match="requires exempt status"):
        capability_record("covered", ["source.py:Symbol"], {"reason": "not applicable"})


def test_migration_script_writes_complete_idempotent_v2_file(tmp_path: Path) -> None:
    source = tmp_path / "legacy.json"
    output = tmp_path / "coverage-ledger-v2.json"
    source.write_text(
        migration.json.dumps(
            _legacy(
                exemption={
                    "capability": "agingConfig",
                    "reason": "该底稿无账龄维度",
                    "approvedBy": "manager",
                    "at": "2026-07-13",
                },
                detected={"review": True},
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert migration.migrate_file(source, output) == []
    first = migration.json.loads(output.read_text(encoding="utf-8"))
    assert first["schemaVersion"] == 2
    assert "exemption" not in first["entries"]["D2"]
    assert set(first["entries"]["D2"]["capabilities"]) == set(CAPABILITIES)

    assert migration.migrate_file(output, output) == []
    second = migration.json.loads(output.read_text(encoding="utf-8"))
    assert second == first


def test_generator_emits_complete_v2_records_with_no_entry_exemption() -> None:
    ledger = generate_ledger(check_only=True)

    assert ledger["schemaVersion"] == 2
    assert ledger["capabilities"] == list(CAPABILITIES)
    assert ledger["entries"]
    for entry in ledger["entries"].values():
        assert "exemption" not in entry
        assert set(entry["capabilities"]) == set(CAPABILITIES)
        for record in entry["capabilities"].values():
            assert set(record) == {"status", "evidence", "exemption"}
