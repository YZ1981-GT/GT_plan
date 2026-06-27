# Tasks

## 1. 后端：渲染策略

- [x] 1.1 Create `backend/app/routers/wp_render_strategies/_a176_closing_meeting.py` with `async def render(ctx: RenderContext) -> dict | None` — loads checklist_responses (item_id LIKE 'a176-%'), returns {meta_info(6 fields), fields(5), project_context}
- [x] 1.2 Register "a17-6-closing-meeting" in RENDERER_DISPATCH `__init__.py`
- [x] 1.3 Add "a17-6-closing-meeting" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1.4 Update `wp_code_overrides.json` — ensure A17-6 maps to "a17-6-closing-meeting" (keep skip)
- [x] 1.5 Write hypothesis PBT: `backend/tests/test_a176_render_pbt.py` — Property 3 (response structure completeness: meta_info 6 keys + fields 5 keys)
- [x] 1.6 Write unit test: `backend/tests/test_a176_closing_meeting.py` — render strategy (normal/empty)

## 2. 前端：composable

- [x] 2.1 Create `useA176ClosingMeeting.ts` — reactive metaInfo(6) + fields(5), 2s debounce save (item_id: `a176-*`), flush
- [x] 2.2 Write fast-check PBT: `useA176ClosingMeeting.spec.ts` — Property 1 (item_id format), Property 2 (auto-fill verification)
- [x] 2.3 Write vitest unit tests: field update, meta auto-fill, debounce save, flush

## 3. 前端：主组件 GtA176ClosingMeeting.vue

- [x] 3.1 Create `GtA176ClosingMeeting.vue` (~200 lines) — el-segmented, meta area (6 fields: client auto, period auto, preparer auto, reviewer input, date picker, index read-only), meeting time (datetime picker), attendees (input), minutes (textarea min 8 rows), conclusion (textarea min 3 rows), attachments (input), GtOnlyOfficeSheet
- [x] 3.2 Write fast-check PBT: `GtA176ClosingMeeting.spec.ts` — Property 2 (auto-fill fields present)
- [x] 3.3 Write vitest unit tests: 6 fields render, datetime picker, textarea sizing, meta auto-fill, mode switch

## 4. 前端：注册

- [x] 4.1 Register GtA176ClosingMeeting in `htmlRendererRegistry.ts` with key "a17-6-closing-meeting"

## 5. 契约测试 + E2E

- [x] 5.1 Update `htmlRendererRegistry.spec.ts` expected list to include "a17-6-closing-meeting"
- [x] 5.2 Write Playwright E2E: load A17-6 → verify meta auto-fill → set meeting time → fill minutes → save → reload → verify
