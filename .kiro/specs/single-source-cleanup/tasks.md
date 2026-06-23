# Implementation Plan

## Overview

6 项独立的去重/收口重构任务，可并行实施，验证方式为全量测试通过 + TypeScript 编译无错。

## Tasks

- [x] 1. Merge confirmation enum definitions (§6.2)
  - Delete `audit-platform/frontend/src/components/workpaper/confirmation/confirmationEnums.ts`
  - Global search-replace all imports from `confirmationEnums` → `confirmationDicts`
  - Verify `MATCH_STATUS` usage — if still referenced, add to `confirmationDicts.ts`; if dead, remove references
  - Run `npx tsc --noEmit` → 0 errors
  - Run `npx vitest --run` → all pass
  - _Requirements: 1.1, 1.2_

- [x] 2. Add lru_cache to parse_to_ast (§4.6)
  - In `backend/app/services/formula_engine.py`, add `@functools.lru_cache(maxsize=2048)` to `parse_to_ast`
  - Verify AST nodes are immutable (frozen dataclass / tuple) — safe for cache sharing
  - Run `python -m pytest backend/tests/ -x` → all pass
  - Optionally: add micro-benchmark confirming repeated parse is faster
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 3. Extract shared _has_grid_cells (§2.5)
  - Create `backend/app/routers/wp_render_strategies/_utils.py` with `_has_grid_cells` function
  - Modify `_univer_grid.py`: delete local `_has_grid_cells`, add `from ._utils import _has_grid_cells`
  - Modify `_c_note.py`: same
  - Run `python -m pytest backend/tests/ -x` → all pass
  - _Requirements: 3.1, 3.2_

- [x] 4. Remove duplicate build_preparation_info (§2.9)
  - In `backend/app/routers/wp_render_config.py`, delete `_build_preparation_info` function (~L355)
  - Replace all calls with `from app.services.wp_preparation_info_service import build_preparation_info`
  - Run `python -m pytest backend/tests/ -x` → all pass
  - _Requirements: 4.1, 4.2_

- [x] 5. Create formula_grammar.py single source for token regexes (§9.2)
  - New file: `backend/app/services/formula_grammar.py`
  - Move all formula token regexes (TB_PATTERN, SUM_TB_PATTERN, ROW_PATTERN, REPORT_PATTERN, NOTE_PATTERN, WP_PATTERN, PREV_PATTERN, AUX_PATTERN, SUM_ROW_PATTERN) + function name set + arity map
  - Update `formula_engine.py`: `from app.services.formula_grammar import ...`
  - Update `report_engine.py`: same
  - Update `address_registry.py`: same (rename `_FORMULA_PATTERNS` dict to use grammar imports)
  - Run `python -m pytest backend/tests/ -x` → all pass
  - _Requirements: 5.1, 5.2_

- [x] 6. Deduplicate componentType whitelist (§2.15)
  - In `audit-platform/frontend/src/composables/useEditorMode.ts`:
    - Delete internal `HTML_COMPONENT_TYPES` Set definition
    - Add `import { HTML_COMPONENT_TYPE_SET as HTML_COMPONENT_TYPES } from '../components/workpaper/htmlRendererRegistry'`
  - Run `npx tsc --noEmit` → 0 errors
  - Run `npx vitest --run` → all pass
  - _Requirements: 6.1, 6.2_

- [x] 7. Checkpoint
  - Full backend test suite: `python -m pytest backend/tests/`
  - Full frontend: `npx vitest --run` + `npx tsc --noEmit`
  - No new tests needed (pure refactor, behavior unchanged)
  - Verify codegraph sync (no broken references)

## Task Dependency Graph

```json
{"waves":[["1","2","3","4","5","6"],["7"]]}
```

## Notes

- All 6 tasks are INDEPENDENT and can be done in any order or parallel
- Each task is self-contained: one file/module change + verify tests pass
- No DB migrations, no API contract changes (except §6.2 frontend-only)
- Total estimated LOC change: ~100 lines (mostly deletions + import rewiring)
