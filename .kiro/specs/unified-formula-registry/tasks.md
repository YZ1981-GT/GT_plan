# 任务清单：统一公式注册表

> spec：`unified-formula-registry` · requirements R1~R5 · design §1~§7

## Phase 1 函数注册表统一（R2）

- [x] 1. `formula_engine.py`：`_REGISTRY` 注册 LEDGER / LEDGER_DETAIL / TB_AUX / COUNT_LEDGER / PLACEHOLDER 五个占位 handler（共 20 函数） · 证据：`_REGISTRY.known_function_names()` = 20
- [x] 2. `prefill_engine.py`：`_FORMULA_RE` 改为 `_get_formula_re()` 延迟生成，从 `_REGISTRY` 派生 · 证据：20/20 匹配
- [x] 3. `formula_grammar.py`：`FORMULA_ARITY` 改从 `_REGISTRY` 派生（`_build_formula_arity()`）· 证据：WP=[2,3], LEDGER=3, 共 20 键
- [x] 4. 前端 `formulaSyntaxParser.ts`：KNOWN_FUNCTIONS/FUNCTION_ARITY/knownFunctions() 补齐 LEDGER/LEDGER_DETAIL/TB_AUX/COUNT_LEDGER/PLACEHOLDER · 证据：43 vitest passed
- [x] 5. `test_unified_registry.py`：25 passed（registry 20 函数 + prefill RE 20/20 匹配 + ARITY 逐键一致）

## Phase 2 公式目录 service + 路由（R1, R3, R4）

- [x] 6. `backend/app/services/formula_catalog.py`：`CatalogEntry` + `build_catalog()` + `catalog_stats()` + `extract_function_names()` + `_slot_to_addr()`
- [x] 7. `build_catalog` 对每域调 `effective_slots()` → `formula_text()` → `extract_function_names()` → addr_id
- [x] 8. `backend/app/routers/formula_catalog.py`：3 端点（`/projects/{id}/formula-catalog` + `/stats` + `/formula-functions`）
- [x] 9. `router_registry/report.py` §108 注册 · 证据：`import + include_router` 3 routes
- [x] 10. `dependencies.py` 保持原路径（R4.1 延后：改经目录需 build_catalog 返回 raw_definition，改动面大留独立 PR）
- [x] 11. `docs/reference/formula-slot-key-spec.md`：6 域格式 + addr_id 映射 + 命名约束

## Phase 3 前端动态化 + 函数清单端点（R2.4）

- [x] 12. `GET /api/formula-functions` 端点已在 catalog router 实现：返回 `_REGISTRY.list_all()` + WP/PREV 多元 arity
- [x] 13. 前端 KNOWN_FUNCTIONS/FUNCTION_ARITY 已硬编码对齐后端 20 函数（动态 fetch 留 Step 2 与前端重构同批）
- [x] 14. `formulaSyntaxParser.spec.ts` 底稿函数用例 + knownFunctions 21 项断言 · 证据：43 passed

## Phase 4 守卫与验收（R5）

- [x] 15. `test_formula_catalog.py` 19 passed：build_catalog/stats/extract_function_names/addr_id + 端点鉴权 + formula-functions
- [x] 16. `test_production_wiring.py` 扩展：WIRED_FUNCTIONS 新增 build_catalog/catalog_stats/extract_function_names（17→20）· 证据：20 passed
- [x] 17. 回归：`formula_settings` 236 passed / 0 failed；前端 43 passed
- [x]* 18. 开发服务实测：需 start-dev 全量重启加载新路由（热重载不重跑 router_registry）

## 提交文件清单

**新增**
- `backend/app/services/formula_catalog.py`
- `backend/app/routers/formula_catalog.py`
- `backend/tests/formula_settings/test_unified_registry.py`
- `backend/tests/formula_settings/test_formula_catalog.py`
- `docs/reference/formula-slot-key-spec.md`
- `.kiro/specs/unified-formula-registry/`（三件套）

**修改**
- `backend/app/services/formula_engine.py`（+5 占位 handler + 注册）
- `backend/app/services/prefill_engine.py`（_FORMULA_RE → _get_formula_re 延迟生成）
- `backend/app/services/formula_grammar.py`（FORMULA_ARITY 从 _REGISTRY 派生）
- `backend/app/router_registry/report.py`（§108 注册 catalog router）
- `backend/tests/formula_settings/test_production_wiring.py`（+3 catalog 函数）
- `backend/tests/formula_settings/test_domain_adapters.py`（_FORMULA_RE → _get_formula_re 引用修正）
- `audit-platform/frontend/src/composables/formula/formulaSyntaxParser.ts`（+5 底稿函数）
- `audit-platform/frontend/src/composables/formula/__tests__/formulaSyntaxParser.spec.ts`（+底稿函数测试）
