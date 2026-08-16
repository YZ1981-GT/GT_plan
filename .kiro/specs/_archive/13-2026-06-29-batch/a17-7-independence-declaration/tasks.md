# Tasks

## 1. 后端：渲染策略 + 团队预填

- [x] 1. 1 Create `backend/app/routers/wp_render_strategies/_a177_independence_declaration.py` with `async def render(ctx: RenderContext) -> dict | None` — determines variant from wp_code, loads checklist_responses (item_id LIKE '{prefix}%'), queries project assignments for team members, returns {variant, meta_info, declaration_text, period_data, team_sign_table, partner_section, threat_records, guidance_notes, project_context}
- [x] 1. 2 Implement `_load_team_members(project_id, db)` helper — queries project_assignments JOIN users to get team member name list for pre-fill
- [x] 1. 3 Register "a17-7-independence-declaration" in RENDERER_DISPATCH `__init__.py`
- [x] 1. 4 Add "a17-7-independence-declaration" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1. 5 Update `wp_code_overrides.json` — map A17-7 and A17-7A to "a17-7-independence-declaration" (keep skip)
- [x] 1. 6 Write hypothesis PBT: `backend/tests/test_a177_render_pbt.py` — Property 4 (response schema completeness 8 keys), Property 5 (variant determination from wp_code)
- [x] 1. 7 Write unit tests: `backend/tests/test_a177_independence_declaration.py` — render strategy (team variant, committee variant, empty responses, team pre-fill)

## 2. 前端：composable

- [x] 2. 1 Create `audit-platform/frontend/src/components/workpaper/composables/useA177IndependenceDeclaration.ts` — reactive state for all 5 sections, variant-aware item_id prefix, 2s debounce save, team sign table CRUD (add/remove/update), threat record CRUD (3 types), flush pending saves
- [x] 2. 2 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/composables/__tests__/useA177IndependenceDeclaration.spec.ts` — Property 1 (item_id prefix isolation by variant), Property 2 (team pre-fill count), Property 3 (threat add/remove consistency)
- [x] 2. 3 Write vitest unit tests for useA177IndependenceDeclaration: debounce timing, team CRUD operations, threat CRUD, variant switching prefix, JSON serialization

## 3. 前端：主组件 GtA177IndependenceDeclaration.vue

- [x] 3. 1 Create `audit-platform/frontend/src/components/workpaper/GtA177IndependenceDeclaration.vue` (~400 lines) — el-segmented mode switch, variant prop, 5 section card layout, GtOnlyOfficeSheet for online mode
- [x] 3. 2 Implement Section 1 (声明正文+期间承诺): auto-fill company/year + fixed text + 2 el-date-picker ranges (business period, report period)
- [x] 3. 3 Implement Section 2 (团队签字表): el-table with dynamic rows (序号/姓名/签字checkbox/日期), add button, row delete icon, pre-fill from assignments
- [x] 3. 4 Implement Section 3 (合伙人声明+签字): Y/N el-radio-group + conditional textarea + 2-row fixed sign table (合伙人/负责经理)
- [x] 3. 5 Implement Section 4 (附件威胁记录): el-collapse containing 3 sub-tables (经济利益/贷款担保/商业关系), each with dynamic add/delete rows
- [x] 3. 6 Implement Section 5 (编制指导): el-collapse with 5 read-only guidance note panels
- [x] 3. 7 Write fast-check PBT: `audit-platform/frontend/src/components/workpaper/__tests__/GtA177IndependenceDeclaration.spec.ts` — Property 1 (variant title rendering), Property 3 (threat table row count after operations)
- [x] 3. 8 Write vitest unit tests: 5 sections render, variant prop changes title, team table CRUD UI, date pickers, threat collapse, guidance collapse, mode switch

## 4. 前端：注册

- [x] 4. 1 Register GtA177IndependenceDeclaration in `htmlRendererRegistry.ts` with key "a17-7-independence-declaration"

## 5. 契约测试 + E2E

- [x] 5. 1 Update `htmlRendererRegistry.spec.ts` expected list to include "a17-7-independence-declaration"
- [ ] 5. 2 Write Playwright E2E: load A17-7 → verify team pre-fill → add member row → fill period dates → set partner Y → expand threats → add economic row → save → reload → verify all data persisted → switch to A17-7A → verify different title and prefix
