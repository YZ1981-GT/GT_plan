# Implementation Plan

## Overview

通过 Redis 分布式锁、地址坐标库 single-flight、OCR 服务化三组改动，消除单 worker 假设，支持水平扩展。

## Tasks

- [x] 1. Pressure test baseline (PREREQUISITE — confirm bottleneck before implementation)
  - Run Locust load test with 2+ workers, concurrent imports on same project → document failure mode
  - Measure address_registry wp-domain rebuild latency under concurrent cache miss
  - Measure web worker RSS with/without PaddleOCR loaded
  - Document results as baseline; abort spec if impact < threshold
  - _Requirements: prerequisite for all_

- [x] 2. Import distributed lock — Redis + DB fallback
  - [x] 2.1 Add Redis lock acquisition in `ImportQueueService.acquire_lock` (SET NX EX pattern)
  - [x] 2.2 Add `import_jobs.cancel_requested` column (migration V092)
  - [x] 2.3 Modify `ImportJobRunner.run_job` to poll `cancel_requested` every 5s
  - [x] 2.4 Add global concurrency limit via Redis Set `import_lock:active_set`
  - [x] 2.5 Fallback: if Redis unavailable, use `SELECT FOR UPDATE` on import_jobs
  - [x] 2.6 Tests: 2-worker concurrent import → one rejected; cancel signal cross-process
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 3. Address registry single-flight + incremental invalidation
  - [x] 3.1 Add per-slot_key `asyncio.Lock` dict in `AddressRegistryService`
  - [x] 3.2 In `_get_domain`: on cache miss, acquire lock → double-check → build → release
  - [x] 3.3 Modify `invalidate_async` to accept optional `wp_id` param for incremental wp domain invalidation
  - [x] 3.4 Add `exists(domain, uri)` method for point-check (validate_formula_refs optimization)
  - [x] 3.5 Tests: concurrent cache miss → DB query count = 1; incremental invalidate only affects target wp
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 4. OCR service extraction
  - [x] 4.1 Create `docker-compose.ocr.yml` with PaddleOCR + Tesseract container
  - [x] 4.2 Add simple HTTP API in OCR container (`POST /recognize` → returns text + regions)
  - [x] 4.3 Modify `unified_ocr_service.recognize` to HTTP-call OCR service instead of in-process
  - [x] 4.4 Add fallback: HTTP timeout/error → 503 + log warning
  - [x] 4.5 Remove `from paddleocr import PaddleOCR` from web worker code path
  - [x] 4.6 Test: web worker RSS < 200MB after OCR extraction; OCR service responds correctly
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 5. Post-implementation pressure test
  - Re-run same Locust scenarios from task 1
  - Verify concurrent imports properly serialized across workers
  - Verify address_registry cache miss latency improved (no stampede)
  - Verify web worker memory reduced

- [x] 6. Checkpoint
  - All tests pass; pressure test results documented; memory baseline confirmed

## Task Dependency Graph

```json
{"waves":[["1"],["2","3","4"],["5"],["6"]]}
```

## Notes

- Task 1 is a HARD PREREQUISITE — if pressure test shows no significant impact at current scale, defer tasks 2-4 to avoid premature optimization
- OCR service extraction (task 4) can be deployed independently of tasks 2/3
- Migration V092 (task 2.2) must be idempotent (`IF NOT EXISTS`)
