# G2-2 / G2-3 Structure-Engine Owner Separation & Delete Coverage

Owner: current session.
Status: verified already-implemented; one pre-existing stale delete test fixed for BP-21
consistency.

## Investigation conclusion (read-only)

Per master control §3.5 the two structure engines must have disjoint write-set owners and
the coordinator must fail on cross-engine double-writes. Both are already implemented and
guarded:

- `excel_row_shift.py` owns the managed sheet's internal coordinates. In
  `shift_sheet_rows` the rewriter is called **without `current_sheet`**, so self-qualified
  references (`'sheet'!A20` written on that sheet) fall into the "leave unchanged" branch —
  they are NOT shifted by pass 1.
- `excel_workbook_row_change.py` owns the reference side. `propagate_reference_side` uses
  `qualified_only=True` + `propagate_sheets={target}`, rewriting only prefixed references
  pointing at the managed sheet — bare references (the managed sheet's own cells) are left
  to the local engine.
- `apply_workbook_row_change` composes them: on the managed sheet part it runs
  `shift_sheet_rows` then `propagate_reference_side`; a self-qualified ref is therefore
  shifted **exactly once** (pass 1 skips it, pass 2 propagates it).
- Guards already exist: `WorkbookRowChangePlan._duplicate_locators` (duplicate propagation
  locators fail), and `TestManagedSheetPassesThroughTwice` in
  `test_workbook_row_change_apply.py` pins the "shifted exactly once" behavior including an
  **AST guard** (`test_shift_sheet_rows_does_not_pass_current_sheet`) that goes red if
  someone adds `current_sheet` to the shift path (which would cause double-shift).
- G2-3 delete machinery exists and is tested: `find_undeletable_rows`,
  `resolve_deleted_row_keys`, `build_delete_plan`, `find_dangling_sites`,
  `PropagationReport.assert_matches_plan`, plus dangling-reference fail-closed at plan time.

## Pre-existing failure found and fixed

`test_workbook_row_change_delete.py::test_d2_region_is_13_to_25_not_11_to_25` was failing
at HEAD (not caused by this session — both the test file and the D2 contract are clean vs
HEAD). BP-21 shrank D2's managed region from `13..25` to `13..24` (row 25 is the `……`
typography placeholder) and updated the contract's `formula_mask` to `13:24`, but this
delete test still asserted `13..25`.

Fixed the stale region arithmetic to match the committed contract, verified against the
real template via read-only probe:

- `D2_REGION = (13, 24)`, `d2_region_rows = 12`, mask assertion checks `24`;
- range-ref endpoints within the region are now `[13]` (the `$AI$13:$AI$25` range ends at
  25, now outside the region);
- the widening test collapses the `$AI$13:$AI$25` range at `count = 25 - 13 + 1 = 13`
  (deleting the 12-row region alone leaves row 25, so nothing locks — the widening invariant
  now demonstrates at the true range extent);
- footer row (26) and its 24 single-cell references are unchanged (physical template facts).

## Verification

- `test_workbook_row_change_delete.py`: 38 passed.
- Full structure-engine suite (row_shift + 9 workbook_row_change files): 292 passed.

## Note

This is a test-consistency fix, not a production-code change; the engines themselves were
already correct. No business DB writes, no template changes.
