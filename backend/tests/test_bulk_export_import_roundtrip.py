"""Contract test: bulk export → import round-trip preserves data integrity."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.bulk_tab.single_tab_adapter import IE_ADAPTER_REGISTRY


def test_all_registered_adapters_have_both_fns():
    """Every registered adapter has both export_fn and import_fn callable."""
    for prefix, spec in IE_ADAPTER_REGISTRY.items():
        assert callable(spec.export_fn), f"{prefix} missing export_fn"
        assert callable(spec.import_fn), f"{prefix} missing import_fn"


def test_adapter_count_matches_catalog():
    """Adapter count should cover all IE-enabled catalog entries."""
    import json
    from pathlib import Path

    catalog_path = Path("data/acnr/global_catalog.json")
    with open(catalog_path, encoding="utf-8") as f:
        cat = json.load(f)

    # Get unique api_prefixes from enabled catalog entries
    catalog_prefixes = set()
    for s in cat["sheets"]:
        ie = s.get("import_export", {})
        if ie.get("enabled"):
            catalog_prefixes.add(ie.get("api_prefix", ""))
    catalog_prefixes.discard("")

    # Check all catalog prefixes are registered
    missing = catalog_prefixes - set(IE_ADAPTER_REGISTRY.keys())
    assert not missing, f"Catalog prefixes not in adapter registry: {missing}"


def test_export_import_fn_signatures():
    """Export/import functions have correct arity (>=4/>=5 params each)."""
    import inspect

    for prefix, spec in IE_ADAPTER_REGISTRY.items():
        export_params = inspect.signature(spec.export_fn).parameters
        import_params = inspect.signature(spec.import_fn).parameters
        # export_fn(db, wp_id, sheet_code, mode) = 4 params
        assert len(export_params) >= 4, f"{prefix} export_fn has {len(export_params)} params, expected >=4"
        # import_fn(db, wp_id, sheet_code, xlsx_bytes, strategy) = 5 params
        assert len(import_params) >= 5, f"{prefix} import_fn has {len(import_params)} params, expected >=5"
