# Tasks

## 1. 后端：渲染策略

- [x] 1.1 Create `backend/app/routers/wp_render_strategies/_a171_audit_summary.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a171-%'), parses JSON table data from remark, returns {chapters(16), signature_table(10 rows), project_context}
- [x] 1.2 Register "a17-1-audit-summary" in RENDERER_DISPATCH `__init__.py`
- [x] 1.3 Add "a17-1-audit-summary" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1.4 Update `wp_code_overrides.json` — ensure A17-1 maps to "a17-1-audit-summary" (keep skip in A17 bundle)
- [x] 1.5 Write hypothesis PBT: `backend/tests/test_a171_render_pbt.py` — Property 2 (table JSON round-trip), Property 5 (response schema 16 chapters + signature + context)
- [x] 1.6 Write unit test: `backend/tests/test_a171_audit_summary.py` — render strategy (normal/empty/JSON parse failure/missing context)

## 2. 前端：composables

- [x] 2.1 Create `useA171AuditSummary.ts` — reactive chapters(16) + signatureTable(10 rows), textarea/table/yn update, table row add/remove, 2s debounce save (item_id: `a171-ch{N}-*`, `a171-signature-*`), flush
- [x] 2.2 Create `useA171Navigation.ts` — IntersectionObserver tracking, scrollToChapter, activeChapter highlight, completionStatus computed
- [x] 2.3 Write fast-check PBT: `useA171AuditSummary.spec.ts` — Property 1 (item_id format), Property 3 (Y/N conditional visibility)
- [x] 2.4 Write vitest unit tests: chapter update, table add/remove, signature save, navigation highlight, completion status

## 3. 前端：主组件 GtA171AuditSummary.vue

- [x] 3.1 Create `GtA171AuditSummary.vue` (~800 lines) — el-segmented, left nav panel (16 chapters + completion dots), signature table (10×3), 16 el-collapse cards (textarea/table/yn per type), GtIndexChip (B50/A13/A1-15), GtOnlyOfficeSheet
- [x] 3.2 Implement textarea chapters (一/二/三/四/五/七/十三/十四/十五/十六) with AI disabled button
- [x] 3.3 Implement table chapters (六/八) with dynamic el-table add/remove rows
- [x] 3.4 Implement Y/N chapters (九/十/十一/十二) with conditional textarea expand
- [x] 3.5 Implement left navigation panel with scroll sync + IntersectionObserver
- [x] 3.6 Write fast-check PBT: `GtA171AuditSummary.spec.ts` — Property 4 (navigation highlight uniqueness)
- [x] 3.7 Write vitest unit tests: 16 chapters render, mode switch, signature table, navigation, GtIndexChip links

## 4. 前端：注册

- [x] 4.1 Register GtA171AuditSummary in `htmlRendererRegistry.ts` with key "a17-1-audit-summary"

## 5. 契约测试 + E2E

- [x] 5.1 Update `htmlRendererRegistry.spec.ts` expected list to include "a17-1-audit-summary"
- [x] 5.2 Write Playwright E2E: load A17-1 → verify 16 chapters → navigate → edit textarea/table/yn → save → reload → verify persistence → switch modes
