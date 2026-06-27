# Tasks

## 1. 后端：渲染策略

- [x] 1.1 Create `backend/app/routers/wp_render_strategies/_a81_other_info_representation.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a81-%'), parses JSON file lists from remark, returns {statements, signature_data, project_context}
- [x] 1.2 Register "a8-1-other-info-representation" in RENDERER_DISPATCH `__init__.py`
- [x] 1.3 Add "a8-1-other-info-representation" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1.4 Update `wp_code_overrides.json` — change A8-1 mapping to "a8-1-other-info-representation"
- [x] 1.5 Write hypothesis PBT: `backend/tests/test_a81_render_pbt.py` — Property 2 (file list JSON round-trip), Property 5 (response schema completeness)
- [x] 1.6 Write unit test: `backend/tests/test_a81_other_info_representation.py` — render strategy with mock data (normal flow, empty file lists, JSON parse failure, missing project context)

## 2. 前端：composable

- [x] 2.1 Create `audit-platform/frontend/src/components/workpaper/composables/useA81OtherInfoRepresentation.ts` — reactive statements (6 items) + signatureData, file list add/remove, 2s debounce save to checklist-responses batch API (item_id: `a81-statement-*`, `a81-signature-*`), flush pending saves
- [x] 2.2 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/composables/__tests__/useA81OtherInfoRepresentation.spec.ts` — Property 1 (item_id format), Property 3 (file list add/remove consistency), Property 7 (mode switch data persistence)
- [x] 2.3 Write vitest unit tests for useA81OtherInfoRepresentation: debounce save, file list JSON serialization, flush promise, empty state initialization

## 3. 前端：主组件 GtA81OtherInfoRepresentation.vue

- [x] 3.1 Create `audit-platform/frontend/src/components/workpaper/GtA81OtherInfoRepresentation.vue` (~400 lines) — el-segmented mode switch, header (auto-fill client_name + 致 CPA), intro paragraph (read-only muted), 6 statement cards, signature area, GtOnlyOfficeSheet for online mode
- [x] 3.2 Implement Statement 1/4/5 cards: file list with el-tag (closable) + el-input + add button, AI disabled button on Statement 1 only
- [x] 3.3 Implement Statement 2 card: el-date-picker for publication date
- [x] 3.4 Implement Statement 3 card: Y/N el-radio-group + conditional textarea (visible when N)
- [x] 3.5 Implement Statement 6 card: textarea with placeholder
- [x] 3.6 Implement signature area: auto-fill company name + el-input (法定代表人) + el-date-picker (default audit_report_date)
- [x] 3.7 Implement guidance panel: el-collapse (default collapsed) with el-alert styling
- [x] 3.8 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/__tests__/GtA81OtherInfoRepresentation.spec.ts` — Property 4 (consistency conditional visibility), Property 6 (signature date default)
- [x] 3.9 Write vitest unit tests: 6 statement cards render, file tag add/remove UI, Y/N interaction, signature auto-fill, AI button disabled, mode switch, OO health check

## 4. 前端：注册

- [x] 4.1 Register GtA81OtherInfoRepresentation in `htmlRendererRegistry.ts` with key "a8-1-other-info-representation"

## 5. 契约测试 + 回归验证

- [x] 5.1 Update `htmlRendererRegistry.spec.ts` expected componentType list to include "a8-1-other-info-representation"
- [x] 5.2 Verify `wp_code_overrides.json` A8-1 entry passes `validate_overrides` startup check
- [x] 5.3 Write Playwright E2E: load A8-1 workpaper → verify 6 statement cards → add file to list 1 → select date in statement 2 → confirm Y/N in statement 3 → save → reload → verify persistence → switch modes
