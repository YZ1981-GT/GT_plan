import json
from pathlib import Path

p = Path(__file__).with_name("global_catalog.schema.json")
d = json.loads(p.read_text(encoding="utf-8"))
print("JSON parse: OK")

# draft-07 schema validity
try:
    from jsonschema import Draft7Validator
    Draft7Validator.check_schema(d)
    print("Draft7 check_schema: OK")
    have_jsonschema = True
except ImportError:
    print("jsonschema not installed - skipped meta validation")
    have_jsonschema = False

defs = d["$defs"]
print("top-level not:", d.get("not"))
print("SheetCatalogEntry not:", defs["SheetCatalogEntry"]["not"])
print("CellCatalogEntry not:", defs["CellCatalogEntry"]["not"])
print("sheet addr_id pattern:", defs["SheetCatalogEntry"]["properties"]["addr_id"]["pattern"])

# assertions
assert d["not"] == {"required": ["project_id", "wp_id"]}
assert defs["SheetCatalogEntry"]["not"] == {"required": ["project_id", "wp_id"]}
assert defs["CellCatalogEntry"]["not"] == {"required": ["project_id", "wp_id"]}
assert defs["SheetCatalogEntry"]["properties"]["addr_id"]["pattern"] == "^[A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+$"
print("constraint assertions: OK")

# functional sanity: exercise the schema against sample data if jsonschema available
if have_jsonschema:
    from jsonschema import Draft7Validator
    v = Draft7Validator(d)
    good = {
        "version": "1",
        "registry_version": "2026.07.01",
        "sheets": [{
            "addr_id": "D2/D2-2",
            "domain": "wp",
            "parent_wp_code": "D2",
            "sheet_code": "D2-2",
            "sheet_name": "detail",
        }],
        "cells": [{
            "addr_id": "D2/D2-2/E100",
            "parent_addr_id": "D2/D2-2",
            "domain": "wp",
            "formula_ref": "WP('D2','detail','total')",
        }],
    }
    errs = list(v.iter_errors(good))
    assert not errs, errs
    print("valid sample: OK")

    # project_id at top-level must be rejected (R6.4)
    bad_top = dict(good); bad_top["project_id"] = "p1"
    assert list(v.iter_errors(bad_top)), "top-level project_id should be rejected"
    # wp_id in a sheet entry must be rejected
    bad_sheet = json.loads(json.dumps(good)); bad_sheet["sheets"][0]["wp_id"] = "w1"
    assert list(v.iter_errors(bad_sheet)), "sheet wp_id should be rejected"
    # wp_id in a cell entry must be rejected
    bad_cell = json.loads(json.dumps(good)); bad_cell["cells"][0]["project_id"] = "p1"
    assert list(v.iter_errors(bad_cell)), "cell project_id should be rejected"
    # bad sheet addr_id pattern must be rejected
    bad_addr = json.loads(json.dumps(good)); bad_addr["sheets"][0]["addr_id"] = "D2/D2-2/E100"
    assert list(v.iter_errors(bad_addr)), "sheet addr_id with 3 segments should be rejected"
    print("negative cases (R6.4 + pattern): OK")

print("ALL CHECKS PASSED")
