# Tasks

## 1. 后端：渲染策略 + B22B 联动

- [x] 1.1 Create `backend/app/routers/wp_render_strategies/_a91_deficiency_letter.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a91-%'), queries B22B deficiencies grouped by severity, returns {section_data, deficiency_list, project_context, b22b_warning}
- [x] 1.2 Implement `_load_b22b_deficiencies(project_id, db)` helper — finds B22B workpaper via wp_index JOIN, reads its checklist_responses (item_id LIKE 'b22b-deficiency-%'), groups by severity field, returns empty dict + warning if B22B not found
- [x] 1.3 Register "a9-1-deficiency-letter" in RENDERER_DISPATCH `__init__.py`
- [x] 1.4 Add "a9-1-deficiency-letter" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1.5 Update `wp_code_overrides.json` — change A9-1 mapping from "word-template" to "a9-1-deficiency-letter"
- [x] 1.6 Write hypothesis PBT: `backend/tests/test_a91_render_pbt.py` — Property 1 (B22B severity grouping correctness), Property 3 (DeficiencyItem JSON round-trip), Property 7 (render response schema completeness), Property 8 (B22B missing graceful degradation)
- [x] 1.7 Write unit tests: `backend/tests/test_a91_deficiency_letter.py` — render strategy with mock data (normal flow, B22B absent, empty responses, invalid JSON remark handling)

## 2. 前端：composable

- [x] 2.1 Create `audit-platform/frontend/src/components/workpaper/composables/useA91DeficiencyLetter.ts` — reactive section data + deficiency list management, 2s debounce save to checklist-responses batch API (item_id: `a91-{section}-{field_id}`), deficiency add/remove/update, flush pending saves, B22B refresh via render-config reload, section navigation scrollspy
- [x] 2.2 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/composables/__tests__/useA91DeficiencyLetter.spec.ts` — Property 2 (item_id format), Property 6 (deficiency add/remove consistency), Property 10 (mode switch data persistence)
- [x] 2.3 Write vitest unit tests for useA91DeficiencyLetter: debounce save timing, flush promise resolution, deficiency JSON serialization, B22B warning handling

## 3. 前端：主组件 GtA91DeficiencyLetter.vue

- [x] 3.1 Create `audit-platform/frontend/src/components/workpaper/GtA91DeficiencyLetter.vue` (~600 lines) — 7 section cards layout with left mini-nav, el-segmented mode switch (structured/OnlyOffice), GtOnlyOfficeSheet for online mode with health check disable logic
- [x] 3.2 Implement Section 1 (收件人): auto-fill from project_context.client_name, editable el-input fallback when empty
- [x] 3.3 Implement Section 2 (正文引言): read-only el-collapse with 3 fixed paragraphs, muted text styling
- [x] 3.4 Implement Section 3 (独立性声明): 4 sub-items with el-radio-group (Y/N), conditional textarea for (二) when N, conditional textarea for 非审计服务 when Y
- [x] 3.5 Implement Section 4 (内部控制缺陷): 3 severity sub-groups, deficiency cards with textarea fields (描述/影响/建议) + GtIndexChip + add/delete buttons + disabled AI button per recommendation field
- [x] 3.6 Implement Section 5 (审计委员会监督): Y/N/NA radio + conditional textarea
- [x] 3.7 Implement Section 6 (签发区): auto-fill firm name + el-date-picker with audit_report_date default
- [x] 3.8 Implement Section 7 (管理层回复区): opinion textarea + conclusion textarea (with default text) + representative input + date-picker
- [x] 3.9 Implement left navigation (anchor links to 7 sections) + smooth scroll behavior
- [x] 3.10 Implement guidance notes rendering: el-collapse panels with el-alert styling for template tables
- [x] 3.11 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/__tests__/GtA91DeficiencyLetter.spec.ts` — Property 4 (independence conditional visibility), Property 5 (committee applicability visibility), Property 9 (default values on empty data)
- [x] 3.12 Write vitest unit tests: 7 section cards render, mode switch, radio interactions, deficiency add/remove UI, AI button disabled state, navigation anchor links, GtIndexChip presence

## 4. 前端：注册 + EventBus 联动

- [x] 4.1 Register GtA91DeficiencyLetter in `htmlRendererRegistry.ts` with key "a9-1-deficiency-letter"
- [x] 4.2 Wire EventBus listener for `DEFICIENCY_EVALUATED` in useA91DeficiencyLetter — on event, call refreshFromB22B() to reload deficiency list from render-config
- [x] 4.3 Write vitest unit test: EventBus subscription triggers refresh, unsubscribe on unmount

## 5. 契约测试 + 回归验证

- [x] 5.1 Update `htmlRendererRegistry.spec.ts` expected componentType list to include "a9-1-deficiency-letter"
- [x] 5.2 Verify `wp_code_overrides.json` A9-1 entry passes `validate_overrides` startup check
- [x] 5.3 Write Playwright E2E: load A9-1 workpaper → verify 7 section cards render → fill independence Y/N → add manual deficiency → save → reload → verify persistence → switch to online edit → switch back → verify data intact
