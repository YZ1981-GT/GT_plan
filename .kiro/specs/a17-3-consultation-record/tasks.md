# Tasks

## 1. 后端：渲染策略

- [ ] 1.1 Create `backend/app/routers/wp_render_strategies/_a173_consultation_record.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a173-%'), parses JSON file tags from remark, returns {meta_info, sections(4), project_context}
- [ ] 1.2 Register "a17-3-consultation-record" in RENDERER_DISPATCH `__init__.py`
- [ ] 1.3 Add "a17-3-consultation-record" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [ ] 1.4 Update `wp_code_overrides.json` — ensure A17-3 maps to "a17-3-consultation-record" (keep skip)
- [ ] 1.5 Write hypothesis PBT: `backend/tests/test_a173_render_pbt.py` — Property 2 (file tag JSON round-trip)
- [ ] 1.6 Write unit test: `backend/tests/test_a173_consultation_record.py` — render strategy (normal/empty/JSON failure)

## 2. 前端：composable

- [ ] 2.1 Create `useA173ConsultationRecord.ts` — reactive metaInfo + sections(4 with sub-fields), file tag add/remove for sec1, 2s debounce save (item_id: `a173-*`), flush
- [ ] 2.2 Write fast-check PBT: `useA173ConsultationRecord.spec.ts` — Property 1 (item_id format), Property 2 (file tag add/remove consistency)
- [ ] 2.3 Write vitest unit tests: meta update, section fields, file tag JSON, debounce, auto-fill

## 3. 前端：主组件 GtA173ConsultationRecord.vue

- [ ] 3.1 Create `GtA173ConsultationRecord.vue` (~350 lines) — el-segmented, meta table (4 fields with el-select for type), Section 一 (3 textarea + el-tag file list + AI disabled), Section 二 (textarea), Section 三 (2 textarea), Section 四 (textarea), GtOnlyOfficeSheet
- [ ] 3.2 Implement meta info table with auto-fill and 咨询类型 el-select (5 options)
- [ ] 3.3 Implement Section 一 with file tag el-tag add/remove + AI button disabled
- [ ] 3.4 Write fast-check PBT: `GtA173ConsultationRecord.spec.ts` — Property 3 (auto-fill verification)
- [ ] 3.5 Write vitest unit tests: 4 sections render, meta select, file tags UI, AI button disabled, mode switch

## 4. 前端：注册

- [ ] 4.1 Register GtA173ConsultationRecord in `htmlRendererRegistry.ts` with key "a17-3-consultation-record"

## 5. 契约测试 + E2E

- [ ] 5.1 Update `htmlRendererRegistry.spec.ts` expected list to include "a17-3-consultation-record"
- [ ] 5.2 Write Playwright E2E: load A17-3 → verify 4 sections → add file tag → select 咨询类型 → fill sections → save → reload → verify
