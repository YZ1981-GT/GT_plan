# Tasks

## 1. 后端：渲染策略

- [ ] 1.1 Create `backend/app/routers/wp_render_strategies/_a182_regulatory_communication.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a182-%'), returns {recipient(2 fields), matters(4 items×4 keys), issuance(3 fields), project_context(3 fields)}
- [ ] 1.2 Register "a18-2-regulatory-communication" in RENDERER_DISPATCH `__init__.py`
- [ ] 1.3 Add "a18-2-regulatory-communication" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [ ] 1.4 Update `wp_code_overrides.json` — ensure A18-2 maps to "a18-2-regulatory-communication" (keep skip)
- [ ] 1.5 Write hypothesis PBT: `backend/tests/test_a182_render_pbt.py` — Property 3 (response structure: recipient 2 keys + matters 4 items each 4 keys + issuance 3 keys + project_context 3 keys)
- [ ] 1.6 Write unit test: `backend/tests/test_a182_regulatory_communication.py` — render strategy (normal/empty/partial applicability)

## 2. 前端：composable

- [ ] 2.1 Create `useA182RegulatoryCommunication.ts` — reactive recipient/matters(4)/issuance, 2s debounce save (item_id: `a182-*`), flush, applicability state management, auto-fill from projectContext
- [ ] 2.2 Write fast-check PBT: `useA182RegulatoryCommunication.spec.ts` — Property 1 (item_id format `a182-{section}-{field}`), Property 2 (applicability→textarea联动), Property 5 (适用性幂等)
- [ ] 2.3 Write vitest unit tests: matter applicability toggle, textarea visibility, recipient select/custom, dual-sign fields, debounce save, flush

## 3. 前端：主组件 GtA182RegulatoryCommunication.vue

- [ ] 3.1 Create `GtA182RegulatoryCommunication.vue` (~300 lines) — el-segmented, 区块1(收件人: el-select 3 options + conditional custom input), 区块2(引言: el-collapse 只读2段+auto-fill), 区块3(4事项v-for: title+radio-group Y/N/NA+conditional textarea min 4 rows), 区块4(签发: firm read-only+CPA1+CPA2+date-picker), 区块5(提示: el-collapse 2 tables), AI按钮disabled, GtOnlyOfficeSheet
- [ ] 3.2 Write fast-check PBT: `GtA182RegulatoryCommunication.spec.ts` — Property 2 (Y→textarea visible, N/NA→hidden), Property 4 (dual-sign independence)
- [ ] 3.3 Write vitest unit tests: 5 区块渲染、适用性三态切换、textarea显隐、双签独立、select+custom切换、折叠展开、模式切换

## 4. 前端：注册

- [ ] 4.1 Register GtA182RegulatoryCommunication in `htmlRendererRegistry.ts` with key "a18-2-regulatory-communication"

## 5. 契约测试 + E2E

- [ ] 5.1 Update `htmlRendererRegistry.spec.ts` expected list to include "a18-2-regulatory-communication"
- [ ] 5.2 Write Playwright E2E: load A18-2 → select authority → set matter1 applicability=Y → fill content → set matter2=NA → verify hidden → dual-sign → save → reload → verify persistence
