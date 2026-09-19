# Tasks

## 1. 后端：模板解析服务

- [x] 1.1 Create `backend/app/services/wp_docx_template_parser.py` with dataclasses (PlaceholderDef, ParagraphDef, TableDef, TemplateStructure) and `parse_template(file_path)` function using python-docx to extract paragraphs, tables, and placeholders (${...} + legacy Chinese markers)
- [x] 1.2 Implement `get_cached_structure(file_path, wp_code)` with mtime-based cache (same pattern as wp_code_overrides hot-reload)
- [x] 1.3 Implement `format_placeholder_summary(structure)` for round-trip verification support
- [x] 1.4 Write hypothesis PBT: `backend/tests/test_wp_docx_parser_pbt.py` — Property 1 (placeholder extraction completeness), Property 2 (structural completeness), Property 3 (cache idempotence), Property 4 (round-trip)
- [x] 1.5 Write unit tests: `backend/tests/test_wp_docx_template_parser.py` — edge cases (empty doc, no placeholders, legacy markers only, invalid file)

## 2. 后端：渲染策略 + API 端点

- [x] 2.1 Create `backend/app/routers/wp_render_strategies/_word_template.py` with `async def render(ctx: RenderContext) -> dict | None` that returns {template_structure, filled_responses, sign_status}
- [x] 2.2 Register "word-template" in `RENDERER_DISPATCH` dict in `__init__.py`
- [x] 2.3 Add GET `/api/workpapers/{wp_id}/template-structure` endpoint (in wp_onlyoffice_router or dedicated router) that returns merged TemplateStructure + checklist_responses current values
- [x] 2.4 Write hypothesis PBT: `backend/tests/test_word_template_render_pbt.py` — Property 5 (response merge), Property 12 (render strategy response structure)
- [x] 2.5 Write unit tests: `backend/tests/test_word_template_render_strategy.py` — 400/404 errors, non-word-template rejection, cold cache behavior

## 3. 后端：导出扩展 + OO 回调反写

- [x] 3.1 Extend `download_template_prefilled` in `wp_template_download.py` to accept `include_responses: bool = False` query param; when true, read checklist_responses (item_id LIKE 'wt-{wp_code}-%') and replace placeholders preserving formatting
- [x] 3.2 Extend OnlyOffice save callback in `wp_onlyoffice_router.py` for word-template type: after download, parse saved docx to extract placeholder values and upsert checklist_responses
- [x] 3.3 Write hypothesis PBT: `backend/tests/test_word_template_export_pbt.py` — Property 9 (export replacement + format preservation), Property 10 (export round-trip)
- [x] 3.4 Write hypothesis PBT: `backend/tests/test_word_template_callback_pbt.py` — Property 11 (OO callback extracts and syncs)
- [x] 3.5 Write integration test: `backend/tests/test_word_template_integration.py` — prefilled-download e2e, callback→DB write verification

## 4. 前端：composable + 结构化视图组件

- [x] 4.1 Create `audit-platform/frontend/src/components/workpaper/composables/useWordTemplateStructured.ts` — data loading from render-config, field read/write, 2s debounce save to checklist-responses batch API, flush, export, AI stub
- [x] 4.2 Create `audit-platform/frontend/src/components/workpaper/GtWordTemplateStructuredView.vue` — card-based rendering (heading→card title, paragraph→content, placeholder→el-input/textarea/date-picker, table→el-table), AI button (disabled), read-only guidance text
- [x] 4.3 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/composables/__tests__/useWordTemplateStructured.spec.ts` — Property 6 (field value resolution), Property 7 (item_id format), Property 8 (flush ordering)
- [x] 4.4 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/__tests__/GtWordTemplateStructuredView.spec.ts` — Property 14 (AI button presence for text/textarea)
- [x] 4.5 Write vitest unit tests for GtWordTemplateStructuredView: card rendering, table rendering, mode mapping, disabled AI tooltip, no-placeholder message

## 5. 前端：WorkpaperWordEditor 集成

- [x] 5.1 Add el-segmented mode switch to `WorkpaperWordEditor.vue` generic mode (v-if !isA16Mode): "结构化视图" / "在线编辑", default to structured view
- [x] 5.2 Wire GtWordTemplateStructuredView into structured view mode with useWordTemplateStructured composable; wire existing initGenericEditor into online edit mode
- [x] 5.3 Implement mode switch logic: structured→online (flush saves + regenerate docx + init OO), online→structured (reload template-structure API)
- [x] 5.4 Handle OnlyOffice unavailability: disable "在线编辑" option + tooltip + structured view standalone
- [x] 5.5 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/__tests__/WorkpaperWordEditor.spec.ts` — Property 13 (dual-mode scope for all 25 wp_codes, excludes A16)
- [x] 5.6 Write vitest unit tests: mode switch, OO disabled state, flush-before-switch sequence, export button triggers correct API call

## 6. 契约测试 + 回归验证

- [x] 6.1 Update `htmlRendererRegistry.spec.ts` expected componentType list if needed (word-template stays unchanged, no new type)
- [x] 6.2 Update `VALID_COMPONENT_TYPES` in `wp_classification_service.py` if needed (word-template already exists, verify no changes required)
- [x] 6.3 Write Playwright E2E: load a word-template workpaper → verify structured view renders → fill a field → switch to online edit → switch back → verify value persists

## 7. 后端：导出与导入端点

- [x] 7.1 Extend `prefilled-download` endpoint to support `include_responses=true` parameter — merge checklist_responses values into placeholder positions, preserve formatting
- [x] 7.2 Extend `prefilled-download` endpoint to support `include_guidance=true` parameter — inject template guidance notes as blue italic annotations or Word comments alongside placeholders
- [x] 7.3 Create `POST /api/workpapers/{wp_id}/import-structured` endpoint — accept uploaded docx, parse with Template_Parser, compare against template structure, extract values, upsert to checklist_responses, return {imported_count, warnings}
- [x] 7.4 Write unit tests for extended prefilled-download: include_responses merges values + preserves formatting, include_guidance adds annotations
- [x] 7.5 Write unit tests for import-structured: valid import, partial match with warnings, invalid file 422, template mismatch

## 8. 前端：导出/导入工具栏按钮

- [x] 8.1 Add "导出 Word" button to WorkpaperWordEditor structured view toolbar — flush saves + call prefilled-download(include_responses=true) + trigger browser download
- [x] 8.2 Add "导出模板" button to toolbar — call prefilled-download(include_guidance=true) + trigger download with filename `{wp_code}_模板_带说明.docx`
- [x] 8.3 Add "导入数据" button to toolbar — el-upload dialog (.docx only) + call import-structured + refresh structured view on success + display imported field count
- [x] 8.4 Write vitest unit tests: 3 buttons render, export triggers correct API, import dialog flow, success/error messaging
