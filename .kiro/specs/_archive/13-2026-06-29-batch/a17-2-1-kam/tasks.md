# Tasks

## 1. 后端：渲染策略

- [x] 1.1 Create `backend/app/routers/wp_render_strategies/_a1721_kam.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a1721-%'), parses JSON KAM objects from remark, returns {candidates, kams, notes, applicability, project_context}
- [x] 1.2 Register "a17-2-1-kam" in RENDERER_DISPATCH `__init__.py`
- [x] 1.3 Add "a17-2-1-kam" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1.4 Update `wp_code_overrides.json` — ensure A17-2-1 maps to "a17-2-1-kam" (keep skip)
- [x] 1.5 Write hypothesis PBT: `backend/tests/test_a1721_render_pbt.py` — Property 2 (KAM JSON round-trip), Property 5 (KAM add/remove consistency)
- [x] 1.6 Write unit test: `backend/tests/test_a1721_kam.py` — render strategy (normal/empty KAM/applicability switch on/JSON failure)

## 2. 前端：composable

- [x] 2.1 Create `useA1721Kam.ts` — reactive candidates + kams(dynamic) + notes + applicability, KAM add/remove, candidate add/remove, 2s debounce save (item_id: `a1721-*`), flush, EventBus KAM_UPDATED emit
- [x] 2.2 Write fast-check PBT: `useA1721Kam.spec.ts` — Property 1 (item_id format), Property 3 (applicability switch mutual exclusion), Property 5 (KAM add/remove length)
- [x] 2.3 Write vitest unit tests: KAM add/remove, candidate table update, applicability toggle, notes auto-sync, debounce save

## 3. 前端：主组件 GtA1721Kam.vue

- [x] 3.1 Create `GtA1721Kam.vue` (~500 lines) — el-segmented, Section 一 (candidate table with dynamic rows), Section 二 (KAM cards × N with 6 textarea + GtIndexChip), Section 三 (notes per KAM), Section 四 (el-switch + reason), GtOnlyOfficeSheet
- [x] 3.2 Implement KAM candidate table (el-table 4 columns + add/remove + highlight communicate="是")
- [x] 3.3 Implement KAM detail cards (el-card × N, each with 6 textarea + index chip + delete with el-popconfirm)
- [x] 3.4 Implement applicability switch (el-switch hides sections 2/3, shows reason textarea)
- [x] 3.5 Write fast-check PBT: `GtA1721Kam.spec.ts` — Property 4 (candidate→KAM linkage)
- [x] 3.6 Write vitest unit tests: candidate table UI, KAM cards render, applicability toggle UI, notes sync, mode switch

## 4. 前端：注册

- [x] 4.1 Register GtA1721Kam in `htmlRendererRegistry.ts` with key "a17-2-1-kam"

## 5. 契约测试 + E2E

- [x] 5.1 Update `htmlRendererRegistry.spec.ts` expected list to include "a17-2-1-kam"
- [x] 5.2 Write Playwright E2E: load A17-2-1 → add candidate → mark communicate → fill KAM fields → toggle applicability → save → reload → verify
