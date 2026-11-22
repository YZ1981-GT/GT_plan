# -*- coding: utf-8 -*-
# B22A IT overview store merge facade (spec b22a-whole-workbook-provider-lane
# Phase 2). Companion of phase5_b22a_control_matrix: owns the HTML store
# identity + the OO->HTML merge direction. The main module re-exports.
#
# Store shape (user adjudication 2026-11-21): coordinate-keyed independent
# items under checklist_responses, empty store is legal. Rows live in one JSON
# array item keyed by row identity (GTROW-B22A41-XXXX); scalar meta fields live
# in a dict item. Phase 2 ships the rows item; meta dict rides the same
# merge pass when present.
from __future__ import annotations

from typing import Any, Final, Mapping

__all__ = [
    'STORE_ITEM_ID',
    'ROW_IDENTITY_STORE_KEY',
    'EMPTY_STORE_PAYLOAD',
    'html_store_payload',
    'merge_projection_into_store_rows',
]


# checklist_responses.item_id holding the managed-row JSON array.
STORE_ITEM_ID: Final[str] = 'B22A41-rows'

# Row identity key inside each store row object. Must match the contract
# row_identity json_pointer and the eventual HTML renderer key. The B22A lane
# uses the injected Excel identity GTROW-B22A41-XXXX as the stable key.
ROW_IDENTITY_STORE_KEY: Final[str] = 'rowId'

# Empty store is legal for this lane: first publication may run before any
# HTML-side content exists (phase 2 acceptance).
EMPTY_STORE_PAYLOAD: Final[str] = '[]'


def html_store_payload() -> dict[str, Any]:
    """Contract review.html_store section (identity + merge live here: change together)."""
    return {
        'table': 'checklist_responses',
        'payload_column': 'remark',
        'payload_column_mode': 'remark_only',
        'shape': 'json_array_of_row_objects',
        'item_ids': [STORE_ITEM_ID],
        'payload_column_source': 'user adjudication 2026-11-21: coordinate-keyed independent store items; B22A host flushHtml returns empty projection and the backend adapter reads checklist_responses.',
        'note': (
            'B22A-4-1 IT overview managed rows (GTROW-B22A41-0007..0048) live in '
            + STORE_ITEM_ID + ' as a JSON array; row identity key is '
            + ROW_IDENTITY_STORE_KEY + '. Empty store is a legal publish state for this lane (EMPTY_STORE_PAYLOAD=[]).'
        ),
    }


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """Merge an extracted projection back into the B22A41 rows store (no disk I/O).

    Returns (merged_rows, applied, visited, touched_row_ids) matching the
    oo_to_html rows-branch signature. Formula columns (H complexity array
    formula, I impact IF formula) never enter the store: writing Excel-computed
    values would fork the truth (same rule as B60 budget_cost)."""
    from app.services.workpaper_sync.phase5_b22a_control_matrix import (
        MANAGED_FIELD_SPECS,
        ROW_IDENTITY_STORE_KEY as _IDENTITY_FROM_MAIN,
    )

    identity_key = ROW_IDENTITY_STORE_KEY or str(_IDENTITY_FROM_MAIN)
    writable_fields = {
        spec[0] for spec in MANAGED_FIELD_SPECS if spec[2] == 'editable'
    }
    # Ghost-row anchor: the first business identity column (app_name).
    name_field = 'app_name'

    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(identity_key) or '').strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    pre_existing = set(by_id)
    applied = 0
    visited = 0
    touched: set[str] = set()
    for key in projection.stable_keys():
        fv = projection.get(key)
        if fv is None or getattr(fv, 'is_protected', False):
            continue
        rid = getattr(fv, 'row_key', None)
        if not rid:
            continue
        field_id = str(key).rsplit('/', 1)[-1]
        if field_id not in writable_fields:
            continue
        target = by_id.get(str(rid))
        if target is None:
            target = {identity_key: str(rid)}
            by_id[str(rid)] = target
            order.append(str(rid))
        visited += 1
        new_value = getattr(fv, 'value', None)
        if target.get(field_id) != new_value:
            target[field_id] = new_value
            applied += 1
            touched.add(str(rid))

    ghost_ids = {
        rid
        for rid in order
        if rid not in pre_existing
        and not str(by_id[rid].get(name_field) or '').strip()
    }
    if ghost_ids:
        order = [rid for rid in order if rid not in ghost_ids]
        touched -= ghost_ids

    return [by_id[rid] for rid in order], applied, visited, touched
