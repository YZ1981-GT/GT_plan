# G2-1 BP-21 Managed-Region Typography Rows

Owner: current G2-1 coding session.
Status: guard closed. Production rule already landed; this package adds the missing
platform-rule unit/guard tests and mutation counter-proof.

## Prior state (verified read-only)

BP-21 production code was already in place before this package:

- platform single-source module `backend/app/services/workpaper_sync/excel_typography_rows.py`
  (`is_typography_placeholder` / `trailing_typography_rows` / `last_business_data_row` /
  `assert_last_data_row_is_not_typography_placeholder`);
- H1 / D2 pilots split physical vs business last row
  (`TEMPLATE_TYPOGRAPHY_TAIL_ROWS`, `LAST_DATA_ROW` vs `TEMPLATE_PHYSICAL_LAST_ROW`);
- instrumentation-time fail-closed gate;
- acceptance script `backend/scripts/check/check_managed_region_typography_rows.py`.

Acceptance script run (this session):
`--expect-managed-region-hits 0` → exit 0. Managed regions: H1 `A13..26` (14 rows), D2
`A13..24` (12 rows), G7 `A79..83` unchanged; placeholder rows in regions = 0. The
typography placeholder cells / footer-adjacent rows census settled at 879 / 182 / 39
templates.

## Real gap this package closes

The module docstring referenced a guard test
`test_excel_typography_rows.py::TestAsciiDotFormIsRegisteredNotSilent`, but **the test
file did not exist** — the platform-level predicate had no unit tests locking its
boundaries, and the handoff's required mutation counter-proof was never committed as a
test.

Added `backend/tests/workpaper_sync/test_excel_typography_rows.py` (27 tests):

- predicate boundaries: pure ellipsis vs empty vs business-content-adjacent; trailing-only
  vs mid-region; all-placeholder empty-region marker;
- `decode_cell_text` numeric char refs (decimal + hex) and no silent HTML-entity replace;
- instrumentation gate fail-closed: placeholder last row raises with corrected
  `last_data_row`; empty label column does not pass; all-placeholder region raises;
  non-A first column locked;
- `TestAsciiDotFormIsRegisteredNotSilent`: full-library `scan()` census equals the
  registered `ASCII_DOT_PLACEHOLDER_CENSUS` narrow counts (879 / 182 / 39) — registration,
  not silent hole;
- BP-21 acceptance: `scan_managed_regions()` → 0 placeholder rows in regions, pilots
  resolve to shrunk ranges (H1 26, D2 24);
- mutation counter-proof: short-circuiting `trailing_typography_rows` stops
  `last_business_data_row` from shrinking, so the placeholder row is wrongly kept — proving
  the shrink is load-bearing.

## Result

`27 passed`. Acceptance script exit 0.

## Note on scope

The trailing-typography shrink is applied upstream at instrumentation time (the pilots'
frozen `table_ref` already excludes the placeholder row), which is stronger than the
handoff's originally-envisioned runtime shrink in `resolve_managed_region`. The mutation
counter-proof is therefore at the predicate/behavior level; a script-level mutation would
require mutating the frozen instrumentation of real templates, which is out of scope and
would pollute production template facts.
