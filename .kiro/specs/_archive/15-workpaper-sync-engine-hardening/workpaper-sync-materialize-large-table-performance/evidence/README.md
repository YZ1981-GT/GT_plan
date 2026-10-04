# Materialize Large-Table Performance — Evidence

Owner: current session.
Spec: `workpaper-sync-materialize-large-table-performance`

## What landed

| Wave | Task | Status |
|---|---|---|
| 0 | Offline profiler `backend/scripts/diagnose/profile_materialize_large_table.py` | DONE |
| 1 | `SheetCellIndex` + `patch_sheet_xml_indexed`; wired into plan/apply/inventory | DONE |
| 2 | `_read_cell_views_paired` + substrate `source_bytes` share | DONE |
| 3 | `_stage_cpu_segment` via `asyncio.to_thread` + soft limit 120s | DONE |
| 4 | Offline radiation + live HTTP materialize + DEC-10 clear | DONE |

## Measured numbers (script output, not hand-copied)

### Pre-opt baseline (`baseline-pre-opt.json`)

| rows | seconds | seconds_per_row |
|---|---|---|
| 10 | 0.4541 | 0.045411 |
| 50 | 0.8457 | 0.016915 |
| 200 | 3.1176 | 0.015588 |
| 729 | 30.496 | **0.041833** |

Linearity judge: **FAIL** (ratio 729/200 = **2.68** > 1.15).

### Post Wave-1 (`baseline-post-wave1.json`)

729-row wall time: **30.5s → 5.4s (~5.7×)**; linearity **PASS**.

### Post Wave-2 / Wave-3

See `baseline-post-wave2.json` / `baseline-post-wave3.json` (729 ≈ 5.6s, linearity PASS).

### Wave 4 live HTTP (`http-materialize-live.json`)

| step | status | seconds |
|---|---|---|
| store-projection (server overlay) | 200 | ~17s |
| pending-mutations | 200 | ~10s |
| **materialize** | **200** | **~13s** (soft limit 120) |

`overlay_applied=true`, `field_count=28491` (`store_field_count=28431` + 60 GTROW scaffold). Descriptor present. Soft-limit OK.

Server-side change: `store_projection_response` now returns **substrate baseline ⊕ store** (same as `overlay_store_on_baseline_projection`). Frontend flush must not invent GTROW keys.

Backend base: `http://127.0.0.1:9980`. Script: `verify_d2_materialize_http_live.py` (no client overlay).

## DEC-10

Cleared. Host migration (G4) started: `GtD2AccountsReceivable` → `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost` for D2-2 only. `/d2-sync/*` retained until `ONLYOFFICE_VERIFIED`.

## Guards / radiation

- Wave 1–3 unit guards as previously recorded.
- Wave 4 offline radiation: `test_task38` + `test_task37` + `test_task15` + `test_task36` → **393 passed** (`radiation-wave4-offline.log` if present).

## Honest note on artifact sha256 across profiler runs

Repeated profiler runs of the same row count do **not** produce identical `artifact_sha256` because substrate preparation embeds non-content-stable metadata across fresh temp files. Equivalence for the optimization itself is locked by the byte-identical indexed-vs-legacy patch guard on a frozen sheet XML.
