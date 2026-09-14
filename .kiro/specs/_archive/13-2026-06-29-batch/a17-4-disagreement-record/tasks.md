# Tasks

## 1. 后端：渲染策略

- [x] 1. 1 Create `backend/app/routers/wp_render_strategies/_a174_disagreement_record.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a174-%'), parses JSON personnel array from remark, returns {personnel, sections(6), signature_data, project_context}
- [x] 1. 2 Register "a17-4-disagreement-record" in RENDERER_DISPATCH `__init__.py`
- [x] 1. 3 Add "a17-4-disagreement-record" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1. 4 Update `wp_code_overrides.json` — ensure A17-4 maps to "a17-4-disagreement-record" (keep skip)
- [x] 1. 5 Write hypothesis PBT: `backend/tests/test_a174_render_pbt.py` — Property 2 (personnel JSON round-trip)
- [x] 1. 6 Write unit test: `backend/tests/test_a174_disagreement_record.py` — render strategy (normal/empty personnel/JSON failure)

## 2. 前端：composable

- [x] 2. 1 Create `useA174DisagreementRecord.ts` — reactive personnel(dynamic rows) + sections(6) + signatureData, personnel add/remove/update, 2s debounce save (item_id: `a174-*`), flush
- [x] 2. 2 Write fast-check PBT: `useA174DisagreementRecord.spec.ts` — Property 1 (item_id format), Property 3 (personnel add/remove length consistency)
- [x] 2. 3 Write vitest unit tests: personnel CRUD, section update, signature auto-fill, debounce save

## 3. 前端：主组件 GtA174DisagreementRecord.vue

- [x] 3. 1 Create `GtA174DisagreementRecord.vue` (~400 lines) — el-segmented, Personnel_Table (el-table 4 columns + add/remove), 6 Section_Cards (textarea autosize), Signature_Area (preparer auto + reviewer + date), GtOnlyOfficeSheet
- [x] 3. 2 Implement Personnel_Table with dynamic add/remove rows
- [x] 3. 3 Implement signature area with auto-fill 编制人
- [x] 3. 4 Write fast-check PBT: `GtA174DisagreementRecord.spec.ts` — Property 4 (signature auto-fill)
- [x] 3. 5 Write vitest unit tests: personnel table UI, 6 section cards render, signature area, mode switch

## 4. 前端：注册

- [x] 4. 1 Register GtA174DisagreementRecord in `htmlRendererRegistry.ts` with key "a17-4-disagreement-record"

## 5. 契约测试 + E2E

- [x] 5. 1 Update `htmlRendererRegistry.spec.ts` expected list to include "a17-4-disagreement-record"
- [ ] 5. 2 Write Playwright E2E: load A17-4 → add personnel → fill 6 sections → sign → save → reload → verify
