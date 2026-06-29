# Tasks

## 1. 后端：渲染策略 + 跨引用

- [x] 1.1 Create `backend/app/routers/wp_render_strategies/_a271_it_audit_memo.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a271-%'), parses team JSON, loads cross-reference wp_ids for B22A-4-3/C22/C21-1/B23-15, returns {meta_info, header, purpose_text, it_team_table, chapters(7), cross_references(4), project_context}
- [x] 1.2 Implement `_load_it_cross_references(project_id, db)` helper — finds B22A-4-3, C22, C21-1, B23-15 workpapers via wp_index JOIN, returns dict of wp_ids (graceful None when absent)
- [x] 1.3 Register "a27-1-it-audit-memo" in RENDERER_DISPATCH `__init__.py`
- [x] 1.4 Add "a27-1-it-audit-memo" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1.5 Update `wp_code_overrides.json` — map A27-1 to "a27-1-it-audit-memo" (keep skip)
- [x] 1.6 Write hypothesis PBT: `backend/tests/test_a271_render_pbt.py` — Property 5 (response schema completeness: 7 top-level keys, chapters array length 7, cross_references 4 keys)
- [x] 1.7 Write unit tests: `backend/tests/test_a271_it_audit_memo.py` — render strategy (normal, empty, partial cross-refs absent, team JSON parsing)

## 2. 前端：composable

- [x] 2.1 Create `audit-platform/frontend/src/components/workpaper/composables/useA271ItAuditMemo.ts` — reactive header(4), it_team_table (CRUD), 7 chapters state, computed showChapter4/showCh3Deficiency/showCh6Deficiency based on conclusions, 2s debounce save (item_id: `a271-*`), flush
- [x] 2.2 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/composables/__tests__/useA271ItAuditMemo.spec.ts` — Property 1 (item_id format), Property 2 (team add/remove consistency), Property 3 (ch3 conditional logic), Property 4 (ch6 conditional logic), Property 6 (radio mutual exclusion)
- [x] 2.3 Write vitest unit tests for useA271ItAuditMemo: debounce timing, team CRUD, conclusion computed properties, chapter update, flush, header auto-fill

## 3. 前端：主组件 GtA271ItAuditMemo.vue

- [x] 3.1 Create `audit-platform/frontend/src/components/workpaper/GtA271ItAuditMemo.vue` (~500 lines) — el-segmented mode switch, memo header (4 fields), purpose el-alert, IT team table, 7 chapter cards with conditional logic, GtOnlyOfficeSheet for online mode
- [x] 3.2 Implement memo header: date picker + 致(el-input auto-fill partner) + 发自(auto-fill current user) + 主题(default "IT审计总结")
- [x] 3.3 Implement IT team table: el-table dynamic rows (序号/姓名/职级) + add/delete, default 6 rows
- [x] 3.4 Implement Chapters 1-2: textarea cards with GtIndexChip (B22A-4-3 for ch1, C22 for ch2)
- [x] 3.5 Implement Chapter 3: el-radio-group (部分有效/没有有效/已有效) + conditional deficiency textarea
- [x] 3.6 Implement Chapter 4: conditional card (v-show based on ch3 conclusion) + textarea + GtIndexChip(C21-1)
- [x] 3.7 Implement Chapter 5: textarea + GtIndexChip(B23-15)
- [x] 3.8 Implement Chapter 6: el-radio-group (3 options) + conditional deficiency textarea
- [x] 3.9 Implement Chapter 7: textarea + conclusion input
- [x] 3.10 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/__tests__/GtA271ItAuditMemo.spec.ts` — Property 3 (ch3→ch4 visibility), Property 4 (ch6 deficiency visibility)
- [x] 3.11 Write vitest unit tests: 7 chapter cards render, memo header auto-fill, IT team CRUD UI, radio interactions, conditional show/hide (ch3→ch4, ch6), GtIndexChip×4, mode switch

## 4. 前端：注册

- [x] 4.1 Register GtA271ItAuditMemo in `htmlRendererRegistry.ts` with key "a27-1-it-audit-memo"

## 5. 契约测试 + E2E

- [x] 5.1 Update `htmlRendererRegistry.spec.ts` expected list to include "a27-1-it-audit-memo"
- [x] 5.2 Write Playwright E2E: load A27-1 → verify memo header auto-fill → add IT team member → select ch3 "部分有效" → verify ch4 visible → change to "已有效" → verify ch4 hidden → fill ch5 → save → reload → verify persistence + conditional states restored
