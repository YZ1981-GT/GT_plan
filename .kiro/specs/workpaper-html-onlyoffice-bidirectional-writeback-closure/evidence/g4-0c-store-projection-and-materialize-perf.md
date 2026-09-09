# G4-0c Store-Projection Endpoint + Materialize Performance Blocker

Owner: current session.
Status: store-projection endpoint delivered and real-HTTP verified. D2 real OO round-trip
(G4-0d) BLOCKED by a measured super-linear materialize cost. Frontend host migration
(G4-0b/0c UI) intentionally NOT applied because it would make D2 "在线编辑" >5min and wedge
the worker — strictly worse than the current legacy path.

## Delivered: `GET .../sync/entries/{entry}/store-projection`

Store-backed entries (D2) hold the whole detail table as one `checklist_responses` JSON
(`STORE_ITEM_ID='D2-detail-rows'`), not per-cell stable keys. The frontend must NOT
re-implement the 39-column → stable-key mapping (that would be a second source, Requirement
6.1). Added a thin read-only endpoint that projects the store server-side via the single
source `pilot_d2_large_json.build_store_projection`, returning
`{"expected_revision", "field_count", "row_count", "projection": {"values": {...}}}`.

- `read_store_projection` action added to `_READ_ONLY_ACTIONS`; provider resolved from
  `DELIVERED_PER_ENTRY_CONTRACTS` (adapter_id == contract_id) under the registry allowlist.
- `test_task28_sync_router.py` updated (endpoint added to `_REQUIRED_ENDPOINTS` and the
  slashed-entry route matrix); `100 passed`.

Real HTTP verification (live backend, admin token): `GET .../store-projection` → 200,
`field_count=28431`, `row_count=729`, correct `receivable_detail_rows/{rowId}/{field}`
stable keys and row_keys. This is the single-source projection the unified bridge needs.

## Measured materialize performance (the blocker)

Full HTTP chain timing for D2 (127.0.0.1, no proxy):

- `store-projection`: 200 in **16.7s**
- `pending-mutations`: 200 in **12.9s**
- `materialize`: **>300s timeout** (wedges the worker; client disconnect leaves an
  `idle in transaction` session).

Offline profiling of `d2_bidirectional_bridge.push_html_to_excel` (pure function, no
server/DB commit), by row count:

| rows | time | per-added-row |
|---|---|---|
| 10 | 6.7s | ~fixed base |
| 50 | 8.8s | 0.05 s/row |
| 200 | 15.9s | 0.047 s/row |
| 729 | 59.3s | **0.082 s/row** |

Per-row cost roughly doubles from 200→729 ⇒ **super-linear (≈O(n²) tendency)**. And the
unified `ContentMutationService._stage_and_verify` parses the workbook **≥3 times** per
materialize:

1. `adapter.materialize(...)` internally `extract_projection(substrate)` (1st extract);
2. `adapter.extract(artifact=output)` for roundtrip equivalence (2nd extract);
3. `verify_unmanaged_regions(before, after)` re-reads both workbooks (3rd/4th parse).

For 729 rows / 28431 fields this compounds well past the 300s HTTP timeout, blocking the
single dev worker.

## Conclusion / honest boundary

- The unified path is correct and reachable for D2; the store-projection single-source
  wiring is done and proven.
- The remaining blocker to a real D2 OO round-trip is **materialize performance**, not
  supply, not host wiring. This is a **fixable inefficiency** (cache the substrate extract,
  make extract O(n), or move materialize off the request thread / async), NOT inherent cost.
  It is a substantial, correctness-sensitive optimization that must not be hacked onto a
  live audit component.
- Therefore D2-2 remains `REQUEST_PATH_LEGACY`; `working_paper_content_application` = 0; no
  `bidirectional_verified` claim. The frontend host migration is deferred until materialize
  completes in acceptable time.

## Operational incident + recovery (recorded honestly)

While driving the heavy materialize over HTTP, the dev backend worker got wedged
(CPU-bound synchronous workbook build, client timeout leaving `idle in transaction`; then
a lingering listen socket). I recovered it: terminated the orphaned PG session (guarded,
>300s idle-in-transaction only), stopped the wedged worker, waited out the Windows socket
lingering, and restarted uvicorn (single process, no `--reload`) — `HEALTH 200 in 0.4s`.

Lessons: (1) health probes must use `127.0.0.1` (IPv4), not `localhost` (::1 first on
Windows); (2) large-table materialize must be profiled offline / on a small sample before
driving it over HTTP; (3) synchronous materialize of a 28431-field table is not
production-safe and needs async/streaming.
