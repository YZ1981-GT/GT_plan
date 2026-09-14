# Tasks

## 1. 后端：渲染策略 + 跨引用

- [x] 1.1 Create `backend/app/routers/wp_render_strategies/_a101_governance_communication.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a101-%'), loads cross-reference wp_ids for A9-2 and A13, returns {meta_info, recipient, introduction_text, chapters(16), service_fees(5), signing_section, guidance_notes, cross_references, project_context}
- [x] 1.2 Implement `_load_cross_references(project_id, db)` helper — finds A9-2 and A13 workpapers via wp_index JOIN, returns their wp_ids for GtIndexChip
- [x] 1.3 Register "a10-1-governance-communication" in RENDERER_DISPATCH `__init__.py`
- [x] 1.4 Add "a10-1-governance-communication" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1.5 Update `wp_code_overrides.json` — map A10-1 to "a10-1-governance-communication" (keep skip)
- [x] 1.6 Write hypothesis PBT: `backend/tests/test_a101_render_pbt.py` — Property 3 (chapters array exactly 16 sequential), Property 4 (response schema 9 top-level keys)
- [x] 1.7 Write unit tests: `backend/tests/test_a101_governance_communication.py` — render strategy (normal, empty, cross-ref absent, service fees parsing)

## 2. 前端：composable

- [x] 2.1 Create `audit-platform/frontend/src/components/workpaper/composables/useA101GovernanceCommunication.ts` — reactive state for recipient, 16 chapters, 5 service fee rows, signing section, computed totalFee, 2s debounce save (item_id: `a101-*`), flush
- [x] 2.2 Create `audit-platform/frontend/src/components/workpaper/composables/useA101Navigation.ts` — IntersectionObserver scrollspy for 16+ sections, activeChapter ref, scrollToChapter smooth scroll
- [x] 2.3 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/composables/__tests__/useA101GovernanceCommunication.spec.ts` — Property 1 (item_id format), Property 2 (service fee total correctness)
- [x] 2.4 Write vitest unit tests for useA101GovernanceCommunication: debounce timing, chapter update, fee calculation, flush; for useA101Navigation: scrollspy trigger, activeChapter update

## 3. 前端：主组件 GtA101GovernanceCommunication.vue

- [x] 3.1 Create `audit-platform/frontend/src/components/workpaper/GtA101GovernanceCommunication.vue` (~600 lines) — el-segmented mode switch, left nav sidebar (fixed, ~180px), right content area with 16 chapter cards, GtOnlyOfficeSheet for online mode
- [x] 3.2 Implement header area: recipient el-input (auto-fill client_name + "董事会") + 2 read-only introduction paragraphs (el-alert info)
- [x] 3.3 Implement 16 chapter collapse cards (el-collapse): chapters 1-5 default expanded, 6-16 collapsed, each with textarea autosize min 4 rows
- [x] 3.4 Implement Chapter 3 special: service fee table (el-table 5 rows × 2 columns, editable el-input-number for amounts, auto-calculated total row)
- [x] 3.5 Implement cross-reference chips: Chapter 9 → GtIndexChip(A9-2), Chapter 13 → GtIndexChip(A13)
- [x] 3.6 Implement signing section: firm name (auto-fill), partner name (el-input), date (el-date-picker)
- [x] 3.7 Implement guidance tip section: el-collapse at bottom with template Table 0 notes
- [x] 3.8 Implement left navigation sidebar: 18+ items (recipient/intro/ch1~16/sign/tip), scrollspy highlight, click-to-scroll
- [x] 3.9 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/__tests__/GtA101GovernanceCommunication.spec.ts` — Property 2 (fee total UI display), Property 5 (navigation highlight single active)
- [x] 3.10 Write vitest unit tests: 16 chapter cards render, collapse state, fee table editing, total calculation, navigation items, GtIndexChip presence, mode switch, recipient auto-fill

## 4. 前端：注册

- [x] 4.1 Register GtA101GovernanceCommunication in `htmlRendererRegistry.ts` with key "a10-1-governance-communication"

## 5. 契约测试 + E2E

- [x] 5.1 Update `htmlRendererRegistry.spec.ts` expected list to include "a10-1-governance-communication"
- [x] 5.2 Write Playwright E2E: load A10-1 → verify 16 chapter cards → fill recipient → expand chapter 3 → edit service fee → verify total → click nav item → verify scroll → save → reload → verify persistence
