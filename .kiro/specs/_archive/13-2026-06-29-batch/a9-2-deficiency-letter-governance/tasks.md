# Tasks

## 1. 后端：渲染策略注册

- [x] 1.1 Create `backend/app/routers/wp_render_strategies/_a92_deficiency_letter_governance.py` with `async def render(ctx: RenderContext) -> dict | None` — reuse A91's `_load_section_data` (with prefix="a92") and `_load_b22b_deficiencies`, remove "general" from deficiency_list, remove "response" from section_data, add variant="governance" to response
- [x] 1.2 Refactor `_a91_deficiency_letter.py` to extract `_load_section_data(ctx, prefix)` as a reusable helper (if not already parameterized) so A92 can call with prefix="a92"
- [x] 1.3 Register "a9-2-deficiency-letter-governance" in RENDERER_DISPATCH `__init__.py`
- [x] 1.4 Add "a9-2-deficiency-letter-governance" to VALID_COMPONENT_TYPES in `wp_classification_service.py`
- [x] 1.5 Update `wp_code_overrides.json` — add A9-2 mapping to "a9-2-deficiency-letter-governance"
- [x] 1.6 Write hypothesis PBT: `backend/tests/test_a92_render_pbt.py` — Property 4 (response has variant=governance, no general in deficiency_list, no response in section_data)
- [x] 1.7 Write unit test: `backend/tests/test_a92_deficiency_letter_governance.py` — render strategy returns correct governance structure, B22B absent returns warning

## 2. 前端：variant 支持

- [x] 2.1 Add `variant` prop to GtA91DeficiencyLetter.vue: type `'management' | 'governance'`, default `'management'`
- [x] 2.2 Add `itemIdPrefix` option to useA91DeficiencyLetter.ts — replace hardcoded 'a91' with configurable prefix, default 'a91'
- [x] 2.3 Implement conditional rendering: hide Section 7 (管理层回复区) when variant='governance', hide 一般缺陷 sub-group when variant='governance'
- [x] 2.4 Implement addressee text switch: "董事会\监事会\审计委员会" for governance, "总经理\财务总监\…" for management
- [x] 2.5 Implement navigation item count adjustment: 6 items for governance (exclude 管理层回复区), 7 for management
- [x] 2.6 Register "a9-2-deficiency-letter-governance" in htmlRendererRegistry with component GtA91DeficiencyLetter and extra props `{ variant: 'governance' }`
- [x] 2.7 Write fast-check PBT (追加到现有 spec): Property 1 (variant conditional rendering), Property 2 (item_id a92 prefix), Property 3 (addressee text), Property 5 (nav count)
- [x] 2.8 Write vitest unit tests: variant governance hides section 7 + general deficiency, addressee text correct, itemIdPrefix generates a92-* item_ids

## 3. 契约测试 + 回归验证

- [x] 3.1 Update `htmlRendererRegistry.spec.ts` expected componentType list to include "a9-2-deficiency-letter-governance"
- [x] 3.2 Verify `wp_code_overrides.json` A9-2 entry passes `validate_overrides` startup check
- [x] 3.3 Write Playwright E2E: load A9-2 workpaper → verify only 6 section cards (no Section 7) → verify no 一般缺陷 group → verify addressee shows 董事会 → fill data → save → verify persistence with a92- prefix
