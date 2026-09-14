# Tasks

## 1. 后端：渲染策略 + 跨引用

- [x] 1.1 Create `backend/app/routers/wp_render_strategies/_a121_legal_confirmation.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a121-%'), parses litigation list JSON, loads A5-3 wp_id, returns {meta_info, send_section, reply_section, cross_references, project_context}
- [x] 1.2 Register "a12-1-legal-confirmation" in RENDERER_DISPATCH `__init__.py`
- [x] 1.3 Add "a12-1-legal-confirmation" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1.4 Update `wp_code_overrides.json` — map A12-1 to "a12-1-legal-confirmation" (keep skip)
- [x] 1.5 Write hypothesis PBT: `backend/tests/test_a121_render_pbt.py` — Property 4 (response schema completeness 5 top-level keys), litigation JSON round-trip
- [x] 1.6 Write unit tests: `backend/tests/test_a121_legal_confirmation.py` — render strategy (normal, empty, multiple litigations, A5-3 absent)

## 2. 前端：composable

- [x] 2.1 Create `audit-platform/frontend/src/components/workpaper/composables/useA121LegalConfirmation.ts` — reactive sendSection + replySection, litigation list CRUD (add/remove/update), 2s debounce save (item_id: `a121-{part}-{field}`), flush pending saves, JSON serialization for litigation rows
- [x] 2.2 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/composables/__tests__/useA121LegalConfirmation.spec.ts` — Property 1 (item_id send/reply partition), Property 2 (litigation add/remove consistency)
- [x] 2.3 Write vitest unit tests for useA121LegalConfirmation: debounce timing, litigation CRUD, JSON serialization, field update by part, flush

## 3. 前端：主组件 GtA121LegalConfirmation.vue

- [x] 3.1 Create `audit-platform/frontend/src/components/workpaper/GtA121LegalConfirmation.vue` (~450 lines) — el-segmented mode switch, Part 1 (white card) + Part 2 (light-blue card) layout, GtOnlyOfficeSheet for online mode
- [x] 3.2 Implement Part 1 header: 律师事务所(el-input) + 律师姓名(el-input) + explanation read-only text
- [x] 3.3 Implement Inquiry 1 (未决诉讼): dynamic litigation cards (description textarea + opinion textarea + estimated_loss input-number) + add/delete buttons + GtIndexChip(A5-3)
- [x] 3.4 Implement Inquiry 2 + 3: textarea cards for 其他法律责任 and 律师费
- [x] 3.5 Implement Part 1 footer: simplified note (read-only) + sign area (company auto-fill + date) + reply info table (address/phone/contact inputs)
- [x] 3.6 Implement Part 2 (回函): litigation radio (无/有 + conditional textarea) + fee radio (未积欠/尚有未付 + conditional amount) + lawyer sign (firm/name/date)
- [x] 3.7 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/__tests__/GtA121LegalConfirmation.spec.ts` — Property 3 (conditional visibility for litigation), Property 5 (conditional visibility for fee)
- [x] 3.8 Write vitest unit tests: 2 parts render, litigation CRUD UI, radio conditional show/hide, GtIndexChip presence, mode switch, auto-fill company

## 4. 前端：注册

- [x] 4.1 Register GtA121LegalConfirmation in `htmlRendererRegistry.ts` with key "a12-1-legal-confirmation"

## 5. 契约测试 + E2E

- [x] 5.1 Update `htmlRendererRegistry.spec.ts` expected list to include "a12-1-legal-confirmation"
- [x] 5.2 Write Playwright E2E: load A12-1 → verify 2 parts render → fill recipient → add litigation record → fill reply radio → set fee status "has_outstanding" → enter amount → save → reload → verify all data persisted
