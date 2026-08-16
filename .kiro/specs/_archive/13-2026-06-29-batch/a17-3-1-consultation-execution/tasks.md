# Tasks

## 1. 后端：渲染策略

- [x] 1. 1 Create `backend/app/routers/wp_render_strategies/_a1731_consultation_execution.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a1731-%'), also queries A17-3 data (item_id LIKE 'a173-sec1-%') for reference, returns {meta_info, sections(4), a173_reference, project_context}
- [x] 1. 2 Register "a17-3-1-consultation-execution" in RENDERER_DISPATCH `__init__.py`
- [x] 1. 3 Add "a17-3-1-consultation-execution" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1. 4 Update `wp_code_overrides.json` — ensure A17-3-1 maps to "a17-3-1-consultation-execution" (keep skip)
- [x] 1. 5 Write hypothesis PBT: `backend/tests/test_a1731_render_pbt.py` — Property 2 (A17-3 reference consistency)
- [x] 1. 6 Write unit test: `backend/tests/test_a1731_consultation_execution.py` — render strategy (normal/no A17-3 data/empty)

## 2. 前端：composable

- [x] 2. 1 Create `useA1731ConsultationExecution.ts` — reactive metaInfo + sections(4) + a173Reference, 2s debounce save (item_id: `a1731-*`), flush
- [x] 2. 2 Write fast-check PBT: `useA1731ConsultationExecution.spec.ts` — Property 1 (item_id format), Property 3 (auto-fill)
- [x] 2. 3 Write vitest unit tests: meta update, section fields, A17-3 reference display, debounce, auto-fill

## 3. 前端：主组件 GtA1731ConsultationExecution.vue

- [x] 3. 1 Create `GtA1731ConsultationExecution.vue` (~250 lines) — el-segmented, meta card (4 fields auto-fill), Section 一 (read-only A17-3 reference + GtIndexChip + supplementary textarea), Section 二 (textarea), Section 三 (textarea), Section 四 (textarea), GtOnlyOfficeSheet
- [x] 3. 2 Implement A17-3 reference area with read-only styling + GtIndexChip navigation
- [x] 3. 3 Write fast-check PBT: `GtA1731ConsultationExecution.spec.ts` — Property 2 (A17-3 reference rendering)
- [x] 3. 4 Write vitest unit tests: 5 blocks render, A17-3 reference area, meta auto-fill, mode switch, save status

## 4. 前端：注册

- [x] 4. 1 Register GtA1731ConsultationExecution in `htmlRendererRegistry.ts` with key "a17-3-1-consultation-execution"

## 5. 契约测试 + E2E

- [x] 5. 1 Update `htmlRendererRegistry.spec.ts` expected list to include "a17-3-1-consultation-execution"
- [ ] 5. 2 Write Playwright E2E: load A17-3-1 → verify A17-3 reference → fill sections → save → reload → verify persistence
