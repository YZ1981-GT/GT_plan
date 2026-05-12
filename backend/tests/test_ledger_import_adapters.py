"""Unit tests for `backend.app.services.ledger_import.adapters`.

Covers Sprint 1 Tasks 14 / 18 / 19:

- `BaseAdapter` abstract contract
- `AdapterRegistry` register / unregister / detect_best / ordering
- `GenericAdapter` fallback behavior + alias re-export from identifier
- `JsonDrivenAdapter` scoring + `reload_from_json` hot-reload from a tmp dir
- Module-level `registry` singleton has GenericAdapter pre-registered
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.ledger_import.adapters import (
    AdapterRegistry,
    JsonDrivenAdapter,
    registry as module_registry,
)
from backend.app.services.ledger_import.adapters.base import BaseAdapter
from backend.app.services.ledger_import.adapters.generic import GenericAdapter
from backend.app.services.ledger_import.detection_types import (
    ColumnMatch,
    FileDetection,
    SheetDetection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fd(file_name: str = "foo.xlsx", sheets: list[SheetDetection] | None = None) -> FileDetection:
    return FileDetection(
        file_name=file_name,
        file_size_bytes=100,
        file_type="xlsx",
        sheets=sheets or [],
    )


def _sheet(
    sheet_name: str = "Sheet1",
    table_type: str = "balance",
    headers: list[str] | None = None,
) -> SheetDetection:
    return SheetDetection(
        file_name="foo.xlsx",
        sheet_name=sheet_name,
        row_count_estimate=100,
        header_row_index=0,
        data_start_row=1,
        table_type=table_type,  # type: ignore[arg-type]
        table_type_confidence=90,
        confidence_level="high",
        column_mappings=[
            ColumnMatch(
                column_index=i,
                column_header=h,
                standard_field=None,
                column_tier="extra",
                confidence=0,
                source="header_fuzzy",
            )
            for i, h in enumerate(headers or [])
        ],
    )


# ---------------------------------------------------------------------------
# BaseAdapter contract
# ---------------------------------------------------------------------------


def test_base_adapter_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseAdapter()  # type: ignore[abstract]


def test_base_adapter_preprocess_rows_default_is_identity() -> None:
    class Stub(BaseAdapter):
        id = "stub"
        priority = 1

        def match(self, fd: FileDetection) -> float:
            return 0.0

        def get_column_aliases(self, table_type):  # type: ignore[override]
            return {}

    rows = [{"a": 1}, {"a": 2}]
    assert Stub().preprocess_rows("balance", rows) is rows


# ---------------------------------------------------------------------------
# GenericAdapter
# ---------------------------------------------------------------------------


def test_generic_adapter_match_always_positive() -> None:
    g = GenericAdapter()
    assert g.match(_fd()) == 0.1
    assert g.match(_fd(file_name="用友U8.xlsx")) == 0.1


def test_generic_adapter_returns_default_aliases_with_account_code() -> None:
    aliases = GenericAdapter().get_column_aliases("balance")
    assert "account_code" in aliases
    assert any("科目编码" in a for a in aliases["account_code"])
    # Returned list should be a copy — mutations don't leak into subsequent calls
    aliases["account_code"].append("__mutated__")
    fresh = GenericAdapter().get_column_aliases("balance")
    assert "__mutated__" not in fresh["account_code"]


# ---------------------------------------------------------------------------
# AdapterRegistry
# ---------------------------------------------------------------------------


def test_registry_register_rejects_empty_id() -> None:
    reg = AdapterRegistry()

    class Blank(BaseAdapter):
        id = ""

        def match(self, fd: FileDetection) -> float:
            return 0.0

        def get_column_aliases(self, table_type):  # type: ignore[override]
            return {}

    with pytest.raises(ValueError):
        reg.register(Blank())


def test_registry_register_is_idempotent_on_id() -> None:
    reg = AdapterRegistry()
    reg.register(GenericAdapter())
    reg.register(GenericAdapter())  # same id again
    ids = [a.id for a in reg.all()]
    assert ids.count("generic") == 1


def test_registry_sorted_by_negative_priority_then_insertion_order() -> None:
    reg = AdapterRegistry()

    class A(BaseAdapter):
        id = "a"
        priority = 10

        def match(self, fd: FileDetection) -> float:
            return 0.0

        def get_column_aliases(self, table_type):  # type: ignore[override]
            return {}

    class B(BaseAdapter):
        id = "b"
        priority = 20

        def match(self, fd: FileDetection) -> float:
            return 0.0

        def get_column_aliases(self, table_type):  # type: ignore[override]
            return {}

    class C(BaseAdapter):
        id = "c"
        priority = 10

        def match(self, fd: FileDetection) -> float:
            return 0.0

        def get_column_aliases(self, table_type):  # type: ignore[override]
            return {}

    reg.register(A())
    reg.register(B())
    reg.register(C())

    ids = [a.id for a in reg.all()]
    # priority 20 first; then tied 10s stay in insertion order (a before c)
    assert ids == ["b", "a", "c"]


def test_registry_unregister() -> None:
    reg = AdapterRegistry()
    reg.register(GenericAdapter())
    assert reg.unregister("generic") is True
    assert reg.unregister("generic") is False
    assert reg.all() == []


def test_registry_get() -> None:
    reg = AdapterRegistry()
    g = GenericAdapter()
    reg.register(g)
    assert reg.get("generic") is g
    assert reg.get("nope") is None


def test_registry_detect_best_empty_falls_back_to_generic() -> None:
    reg = AdapterRegistry()
    best, score = reg.detect_best(_fd())
    assert best.id == "generic"
    assert score == 0.1


def test_registry_detect_best_higher_score_wins() -> None:
    reg = AdapterRegistry()
    reg.register(GenericAdapter())

    class HighScorer(BaseAdapter):
        id = "vendor"
        priority = 50

        def match(self, fd: FileDetection) -> float:
            return 0.9

        def get_column_aliases(self, table_type):  # type: ignore[override]
            return {}

    reg.register(HighScorer())
    best, score = reg.detect_best(_fd())
    assert best.id == "vendor"
    assert score == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# JsonDrivenAdapter
# ---------------------------------------------------------------------------


def test_json_driven_adapter_scores_filename_and_signature_columns() -> None:
    adapter = JsonDrivenAdapter(
        {
            "id": "yonyou",
            "display_name": "用友",
            "priority": 80,
            "match_patterns": {
                "filename_regex": [r"(?i)用友"],
                "signature_columns": {
                    "balance": ["科目编码", "科目名称", "年初余额", "期末余额"],
                },
            },
            "column_aliases": {
                "balance": {"account_code": ["科目编码", "科目代码"]},
            },
        }
    )

    # Filename only
    assert adapter.match(_fd("用友_账套.xlsx")) == pytest.approx(0.5)

    # Signature columns only (2 of 4 match → 0.5 * 0.5 = 0.25)
    fd_sig = _fd(
        "random.xlsx",
        sheets=[_sheet(table_type="balance", headers=["科目编码", "科目名称", "junk"])],
    )
    assert adapter.match(fd_sig) == pytest.approx(0.25)

    # Both → capped at 1.0
    fd_both = _fd(
        "用友.xlsx",
        sheets=[_sheet(table_type="balance", headers=["科目编码", "科目名称", "年初余额", "期末余额"])],
    )
    assert adapter.match(fd_both) == pytest.approx(1.0)


def test_json_driven_adapter_returns_aliases() -> None:
    adapter = JsonDrivenAdapter(
        {
            "id": "custom",
            "column_aliases": {
                "balance": {"account_code": ["A", "B"]},
                "ledger": {"voucher_date": ["D"]},
            },
        }
    )
    assert adapter.get_column_aliases("balance") == {"account_code": ["A", "B"]}
    assert adapter.get_column_aliases("ledger") == {"voucher_date": ["D"]}
    # Unknown table type → empty dict, not crash
    assert adapter.get_column_aliases("unknown") == {}


def test_json_driven_adapter_tolerates_bad_regex(caplog: pytest.LogCaptureFixture) -> None:
    adapter = JsonDrivenAdapter(
        {
            "id": "broken",
            "match_patterns": {"filename_regex": ["(unclosed"]},
        }
    )
    # Should not raise; broken pattern is silently dropped with a warning
    assert adapter.match(_fd("anything.xlsx")) == 0.0


# ---------------------------------------------------------------------------
# reload_from_json
# ---------------------------------------------------------------------------


def test_reload_from_json_loads_valid_and_skips_invalid(tmp_path: Path) -> None:
    # Valid
    (tmp_path / "vendor_a.json").write_text(
        json.dumps({"id": "vendor_a", "priority": 70}),
        encoding="utf-8",
    )
    # Skipped (underscore prefix)
    (tmp_path / "_draft.json").write_text(
        json.dumps({"id": "draft", "priority": 70}),
        encoding="utf-8",
    )
    # Invalid JSON
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    # Missing id
    (tmp_path / "no_id.json").write_text(json.dumps({"priority": 50}), encoding="utf-8")
    # Non-object top-level
    (tmp_path / "array.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    reg = AdapterRegistry()
    count = reg.reload_from_json(tmp_path)
    assert count == 1
    ids = [a.id for a in reg.all()]
    assert "vendor_a" in ids
    assert "draft" not in ids


def test_reload_from_json_is_idempotent_replace(tmp_path: Path) -> None:
    (tmp_path / "v.json").write_text(
        json.dumps({"id": "v", "priority": 10}),
        encoding="utf-8",
    )
    reg = AdapterRegistry()
    assert reg.reload_from_json(tmp_path) == 1
    assert reg.reload_from_json(tmp_path) == 1
    ids = [a.id for a in reg.all()]
    assert ids.count("v") == 1


def test_reload_from_json_missing_directory_returns_zero(tmp_path: Path) -> None:
    reg = AdapterRegistry()
    assert reg.reload_from_json(tmp_path / "nonexistent") == 0


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------


def test_module_singleton_has_generic_adapter() -> None:
    ids = [a.id for a in module_registry.all()]
    assert "generic" in ids


def test_module_singleton_detect_best_on_empty_file() -> None:
    best, _ = module_registry.detect_best(_fd())
    # On a fresh registry the fallback is generic; but when other vendors
    # are later registered this test only asserts we get something non-None.
    assert best is not None
    assert best.id  # non-empty id
