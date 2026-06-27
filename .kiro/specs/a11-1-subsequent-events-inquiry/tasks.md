# Tasks

## 1. 后端：渲染策略

- [ ] 1.1 Create `backend/app/routers/wp_render_strategies/_a111_subsequent_events_inquiry.py` with QUESTIONS_CONFIG (10 static question definitions) and `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a111-%'), assembles {meta_data, qa_list, evidence, project_context, questions_config}
- [ ] 1.2 Register "a11-1-subsequent-events-inquiry" in RENDERER_DISPATCH `__init__.py`
- [ ] 1.3 Add "a11-1-subsequent-events-inquiry" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [ ] 1.4 Update `wp_code_overrides.json` — change A11-1 mapping to "a11-1-subsequent-events-inquiry"
- [ ] 1.5 Write hypothesis PBT: `backend/tests/test_a111_render_pbt.py` — Property 2 (questions_config always 10 items), Property 3 (answer round-trip), Property 6 (response schema completeness)
- [ ] 1.6 Write unit test: `backend/tests/test_a111_subsequent_events_inquiry.py` — render strategy with mock data (normal flow, empty answers, missing project context)

## 2. 前端：composable

- [ ] 2.1 Create `audit-platform/frontend/src/components/workpaper/composables/useA111SubsequentEvents.ts` — reactive meta/qaList/evidence, 2s debounce save to checklist-responses batch API (item_id: `a111-meta-*`, `a111-qa-*`, `a111-evidence-*`), flush pending saves, scrollspy navigation
- [ ] 2.2 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/composables/__tests__/useA111SubsequentEvents.spec.ts` — Property 1 (item_id format), Property 7 (mode switch data persistence)
- [ ] 2.3 Write vitest unit tests for useA111SubsequentEvents: debounce save timing, flush promise, all 10 qa items initialized, meta field save

## 3. 前端：主组件 GtA111SubsequentEventsInquiry.vue

- [ ] 3.1 Create `audit-platform/frontend/src/components/workpaper/GtA111SubsequentEventsInquiry.vue` (~450 lines) — el-segmented mode switch, left nav (12 items), meta card (4 fields), 10 Q&A cards (question read-only + answer textarea + AI disabled button), evidence card, GtOnlyOfficeSheet for online mode
- [ ] 3.2 Implement 10 Q&A cards: numbered title + muted question text + conditional el-alert guidance + textarea + disabled AI button
- [ ] 3.3 Implement meta card: el-date-picker (询问日期) + 3 el-inputs (受访对象/地点/签字), balance_sheet_date as date default
- [ ] 3.4 Implement left navigation (12 anchor items) + smooth scroll + scrollspy highlight
- [ ] 3.5 Implement collapsible 问询目的 section (el-collapse, default collapsed, muted text)
- [ ] 3.6 Implement timing guidance el-alert at top of form
- [ ] 3.7 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/__tests__/GtA111SubsequentEventsInquiry.spec.ts` — Property 4 (nav always 12 items), Property 5 (guidance conditional display)
- [ ] 3.8 Write vitest unit tests: 10 Q&A cards render, meta form fields, AI button disabled, navigation 12 items, mode switch, OO health check disable

## 4. 前端：注册

- [ ] 4.1 Register GtA111SubsequentEventsInquiry in `htmlRendererRegistry.ts` with key "a11-1-subsequent-events-inquiry"

## 5. 契约测试 + 回归验证

- [ ] 5.1 Update `htmlRendererRegistry.spec.ts` expected componentType list to include "a11-1-subsequent-events-inquiry"
- [ ] 5.2 Verify `wp_code_overrides.json` A11-1 entry passes `validate_overrides` startup check
- [ ] 5.3 Write Playwright E2E: load A11-1 workpaper → verify 10 Q&A cards render → fill Q1 answer → fill meta fields → save → reload → verify persistence → navigate via left nav → switch modes
