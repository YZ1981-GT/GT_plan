"""Contract for concurrent Ledger index operations, including V222 windows."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "backend" / "scripts" / "ops" / "build_ledger_query_indexes.py"
spec = importlib.util.spec_from_file_location("build_ledger_query_indexes", PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_all_large_ledger_indexes_are_explicit_concurrent_partial_indexes() -> None:
    assert set(mod.INDEXES) == {"aux-account-prefix", "ledger-window", "aux-window"}
    for key, index in mod.INDEXES.items():
        assert index.definition.startswith("CREATE INDEX CONCURRENTLY "), key
        assert " WHERE is_deleted = false" in index.definition, key
        assert "public." + index.table in index.definition, key


def test_window_indexes_share_the_server_keyset_order() -> None:
    ordinary = mod.INDEXES["ledger-window"].definition
    auxiliary = mod.INDEXES["aux-window"].definition
    for definition in (ordinary, auxiliary):
        assert "voucher_date ASC NULLS LAST, voucher_no ASC NULLS LAST, id ASC" in definition
        assert "project_id, year, dataset_id, account_code" in definition
    assert "aux_type, aux_code" in auxiliary


def test_apply_requires_explicit_matching_confirmation() -> None:
    parser = mod._parser()
    args = parser.parse_args(["--index", "ledger-window"])
    assert args.apply is False
    args = parser.parse_args(["--index", "ledger-window", "--apply", "--confirm", "BUILD_LEDGER_INDEXES"])
    assert args.apply is True and args.confirm == "BUILD_LEDGER_INDEXES"
