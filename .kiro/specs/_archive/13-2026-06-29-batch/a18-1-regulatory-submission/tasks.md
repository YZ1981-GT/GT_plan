# Tasks

## 1. 后端：渲染策略

- [x] 1.1 Create `backend/app/routers/wp_render_strategies/_a181_regulatory_submission.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a181-%'), returns {recipient(1 field), body(2 fields), issuance(2 fields), project_context(4 fields)}
- [x] 1.2 Register "a18-1-regulatory-submission" in RENDERER_DISPATCH `__init__.py`
- [x] 1.3 Add "a18-1-regulatory-submission" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1.4 Update `wp_code_overrides.json` — ensure A18-1 maps to "a18-1-regulatory-submission" (keep skip)
- [x] 1.5 Write hypothesis PBT: `backend/tests/test_a181_render_pbt.py` — Property 3 (response structure: recipient 1 key + body 2 keys + issuance 2 keys + project_context 4 keys)
- [x] 1.6 Write unit test: `backend/tests/test_a181_regulatory_submission.py` — render strategy (normal/empty)

## 2. 前端：composable

- [x] 2.1 Create `useA181RegulatorySubmission.ts` — reactive recipient/body/issuance, 2s debounce save (item_id: `a181-*`), flush, auto-fill from projectContext
- [x] 2.2 Write fast-check PBT: `useA181RegulatorySubmission.spec.ts` — Property 1 (item_id format `a181-{section}-{field}`), Property 2 (auto-fill verification)
- [x] 2.3 Write vitest unit tests: field update, auto-fill, debounce save, flush

## 3. 前端：主组件 GtA181RegulatorySubmission.vue

- [x] 3.1 Create `GtA181RegulatorySubmission.vue` (~150 lines) — el-segmented, 区块1(收件人: 固定前缀+bureau input), 区块2(正文: 只读段落+auto-fill client/year+联系人partner/phone input+附件说明), 区块3(签发: firm read-only+partner input+date-picker), AI按钮disabled, GtOnlyOfficeSheet
- [x] 3.2 Write fast-check PBT: `GtA181RegulatorySubmission.spec.ts` — Property 4 (前缀始终显示), Property 2 (auto-fill fields)
- [x] 3.3 Write vitest unit tests: 3 区块渲染、收件人前缀、自动填充、只读段落、模式切换

## 4. 前端：注册

- [x] 4.1 Register GtA181RegulatorySubmission in `htmlRendererRegistry.ts` with key "a18-1-regulatory-submission"

## 5. 契约测试 + E2E

- [x] 5.1 Update `htmlRendererRegistry.spec.ts` expected list to include "a18-1-regulatory-submission"
- [x] 5.2 Write Playwright E2E: load A18-1 → verify auto-fill (client/year/firm) → input bureau name → fill contact → sign → save → reload → verify persistence
