# Implementation Plan: ACNR Consumer Wiring

## Overview

将 4 个优先级消费者接入 ACNR 统一解析体系，按优先级分组（P1→P4）逐步交付。核心原则：strangler-fig 模式（旧路径保留 fallback）、addr_id 唯一标识、容错不中断。语言：Python（后端）+ TypeScript/Vue（前端）。

## Tasks

- [x] 1. Priority 1 — Formula Engine + EventBus Invalidation Chain
  - [x] 1.1 Enhance CrossSheetResolver to call ACNR full_resolve
    - 修改 `backend/app/services/custom_query/cross_sheet_resolver.py`
    - 在 BFS 循环中对每个跨 sheet 引用先调 `full_resolve(formula_ref, project_id)`
    - 命中（found=true）时使用 `ResolveResult.addr_id` 作为 node URI
    - 未命中时 fallback 到 snapshot 提取，标记 `resolve_missed=True`
    - 新增 `_sync_resolve` 包装器处理 async→sync 转换
    - 异常时 `logger.warning` + 继续 BFS 不中断
    - `RefChainNode` 新增 `resolve_missed: bool = False` 字段
    - 构造函数接收 `project_id` 参数传递给 full_resolve
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x]* 1.2 Write property tests for CrossSheetResolver ACNR integration (P1–P3)
    - **Property 1: ACNR Resolve Fallback Preserves Response Contract**
    - **Property 2: addr_id Used on ACNR Hit**
    - **Property 3: Snapshot Fallback on ACNR Miss**
    - 使用 Hypothesis 生成随机 ResolveResult 组合（found=true/false/exception）
    - 验证无论 full_resolve 结果如何，resolve() 始终返回有效 RefChainResponse
    - **Validates: Requirements 1.2, 1.3, 1.5, 1.6**

  - [x] 1.3 Enhance ACNR events.invalidate with FormulaReverseIndex clear
    - 修改 `backend/app/services/acnr/events.py`
    - 在 L2 overlay clear 之后、legacy delegate 之前插入 `invalidate_reverse_index()` 调用
    - 执行顺序：L3 RuntimeIndex → L2 Overlay → FormulaReverseIndex → Legacy V1
    - 每步独立 try/except，异常 `logger.warning` 不 re-raise
    - 无论 extra_sheets 参数如何，始终执行完整 reverse_index 失效
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x]* 1.4 Write property test for invalidation chain completeness (P14)
    - **Property 14: Invalidation Chain Completeness**
    - 使用 Hypothesis 注入随机异常组合（任意 step 可能 raise）
    - 验证所有 4 步始终被调用，不因前序异常跳过后续步
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [x]* 1.5 Write unit tests for CrossSheetResolver and EventBus integration
    - 测试 project_id 正确传递给 full_resolve（Req 1.4）
    - 测试 invalidation 执行顺序（mock 各 step 记录调用序）
    - 测试 extra_sheets 不影响 reverse_index 失效行为
    - _Requirements: 1.4, 2.1–2.4_

- [x] 2. Checkpoint — Priority 1 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Priority 2 — LinkageGraphBuilder + StalePropagationEngine + stale_impact Endpoint
  - [x] 3.1 Implement `_normalize_wp_uri_to_addr_id` pure function
    - 在 `backend/app/services/linkage_graph_builder.py` 中新增 module-level 纯函数
    - 正则匹配 `WP:{wp_code}:{sheet_display}:{cell}` 格式
    - 提取 sheet_code（从 sheet_display 中匹配 `[A-Z]\d+(-\d+)?[A-Z]?` 模式）
    - 非 WP 域 URI 原样返回（REPORT:, TB:, NOTE:, MAPPING:, ADJ:）
    - 输出格式 `{wp_code}/{sheet_code}/{cell}`
    - _Requirements: 3.1, 3.10_

  - [x]* 3.2 Write property tests for URI normalization (P4–P5)
    - **Property 4: WP URI Normalization Round-Trip Consistency**
    - **Property 5: Non-WP Domain URI Passthrough**
    - 使用 Hypothesis 生成随机 WP URI（合法 wp_code + sheet_display + cell）
    - 验证 WP 域输出含 3 段 `/` 分隔；非 WP 域输入 = 输出
    - **Validates: Requirements 3.1, 3.5, 3.6, 3.8, 3.9, 3.10**

  - [x] 3.3 Integrate normalization into LinkageGraphBuilder._from_* methods
    - 修改 `_from_prefill_mapping`：WP 域 URI 调 `_normalize_wp_uri_to_addr_id`
    - 修改 `_from_cross_wp_references`：source/target URI 归一化
    - 修改 `_from_l3_dependencies`：intra-wp 依赖 URI 归一化
    - 修改 `_from_docx_placeholders`：WP 域 placeholder URI 归一化
    - 保留 REPORT/TB/NOTE/MAPPING 域原 URI 不变
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.11_

  - [x]* 3.4 Write property test for graph build invariant (P10)
    - **Property 10: Graph Build Invariant — WP Nodes Use addr_id**
    - Mock 各数据源，验证 build() 输出中所有 `module=="WP"` 节点 id 含 `/` 无 `WP:` 前缀
    - **Validates: Requirements 3.11**

  - [x] 3.5 Implement StalePropagationEngine addr_id compatibility
    - 修改 `backend/app/services/stale_propagation_engine.py`
    - 新增 `_detect_and_normalize(source_uri)` 格式检测函数
    - `WP:` 前缀 + 多冒号 → legacy → 调 `_normalize_wp_uri_to_addr_id`
    - `/` 分隔无 `WP:` 前缀 → addr_id → 直接使用
    - 新增 `_addr_id_index: dict[str, str]` 字段
    - 新增 `_build_addr_id_index()` 在 graph load 后构建 O(1) 查找索引
    - `reload_graph()` 时重建 index
    - `on_change()` 入口调 `_detect_and_normalize` 后再 BFS
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x]* 3.6 Write property test for format detection (P6)
    - **Property 6: Format Detection Correctness**
    - 使用 Hypothesis 生成两种格式 URI 混合输入
    - 验证 legacy 格式被归一化、addr_id 格式直通不变
    - **Validates: Requirements 4.1, 4.2, 4.3**

  - [x] 3.7 Implement GET /api/linkage-bus/impact-by-addr endpoint
    - 修改 `backend/app/routers/linkage_bus.py`
    - 新增 `GET /impact-by-addr` 端点
    - 接收 `addr_id`（required）、`max_depth`（default 3）、`project_id`（required）
    - addr_id 空/缺失 → HTTP 400 `"addr_id is required"`
    - engine degraded → HTTP 503
    - 正常调用 `stale_engine.on_change(addr_id)` 返回 BFS 结果
    - 响应含 `addr_id`, `total_affected`, `affected` list（每项含 addr_id/depth/via_ref/match_type）
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x]* 3.8 Write property test for stale_impact response schema (P11)
    - **Property 11: stale_impact Response Schema Completeness**
    - 使用 Hypothesis 生成随机合法 addr_id 输入
    - 验证 200 响应 schema 含所有必需字段、类型正确
    - **Validates: Requirements 5.4**

  - [x]* 3.9 Write unit tests for stale_impact boundary conditions
    - 测试 addr_id 为空串 → 400
    - 测试 engine degraded → 503
    - 测试正常 addr_id → 200 含正确 schema
    - _Requirements: 5.5, 5.6_

- [x] 4. Checkpoint — Priority 2 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Priority 3 — Bulk ZIP Manifest Consumer Switch + Topo Sort
  - [x] 5.1 Create wp_bulk_tab_export service with manifest integration
    - 新建 `backend/app/services/wp_bulk_tab_export.py`
    - 实现 `list_export_sheets(db, project_id, cycle)` 异步函数
    - 调用 `manifest.list_import_export(db, project_id, cycle)` 获取清单
    - 过滤 `wp_id=None` 条目（log warning + skip）
    - 使用 manifest entry 的 `api_prefix` + `item_id` 构造数据端点
    - 使用 `sheet_code` 作为 ZIP tab 名称
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 5.2 Implement `_topological_sort` with Kahn's algorithm
    - 在同文件中实现拓扑排序纯函数
    - 基于 `depends_on_sheets` 构建有向图
    - Kahn's algorithm 逐层弹出零入度节点
    - 同级无依赖关系时以 `import_order` 为 tiebreaker
    - 环检测：排序结果数 < 输入数 → `logger.error` + fallback import_order 排序
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x]* 5.3 Write property tests for topological sort (P7–P9)
    - **Property 7: Topological Sort Respects Dependencies**
    - **Property 8: Topological Sort Stability via import_order**
    - **Property 9: Circular Dependency Fallback**
    - 使用 Hypothesis 生成随机 DAG、有环图、平级 entry 组合
    - 验证 DAG 输出满足依赖序、无依赖对按 import_order、环时 fallback
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

  - [x] 5.4 Implement bulk import service with topo sort ordering
    - 在 `wp_bulk_tab_export.py` 中新增 `list_import_sheets(db, project_id, cycle)` 函数
    - 同样调用 manifest + topo sort 获取导入顺序
    - 使用 `api_prefix` + `item_id` 路由数据到正确存储端点
    - 导出也应用 topo sort 确保 ZIP 中 sheet 顺序满足依赖
    - _Requirements: 6.5, 6.6, 7.5_

  - [x]* 5.5 Write property test for bulk export tab naming (P12)
    - **Property 12: Bulk Export Tab Names Match sheet_code**
    - 使用 Hypothesis 生成随机 manifest entries（含/不含 wp_id）
    - 验证 wp_id≠None 的 entry 对应 tab 名 == sheet_code
    - **Validates: Requirements 6.4**

  - [x]* 5.6 Write unit tests for bulk export/import service
    - 测试 wp_id=None 条目跳过 + warning 日志
    - 测试 topo sort 输出顺序正确
    - 测试 api_prefix/item_id 构造端点正确
    - _Requirements: 6.1–6.6, 7.1–7.5_

- [x] 6. Checkpoint — Priority 3 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Priority 4 — CustomQueryFieldPicker Migration
  - [x] 7.1 Create CustomQueryFieldPicker Vue component
    - 新建 `audit-platform/frontend/src/components/custom-query/CustomQueryFieldPicker.vue`
    - 调用 `useAcnr().buildAddressTree(cycle)` 获取层级树
    - el-tree lazy 加载：展开 sheet 节点时调 `loadCellNodes(sheetEntry)`
    - 树节点 label = `AcnrTreeNode.label`，存值 = `AcnrTreeNode.addrId`
    - 选中 cell 节点时 emit `select` 事件（含 addrId + formulaRef）
    - 支持 cycle prop 过滤 + showCycleFilter 循环下拉
    - 监听 `template-applied` 事件 → clearCache + reload
    - loading 态显示 spinner、空态显示 el-empty 占位
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [x]* 7.2 Write unit tests for CustomQueryFieldPicker
    - 测试 buildAddressTree 被调用时传入正确 cycle
    - 测试 template-applied 事件触发 clearCache + reload
    - 测试 loading=true 时展示 spinner
    - 测试空数组时展示 el-empty
    - 测试 cell 节点 click emit 正确 payload（addrId + formulaRef）
    - _Requirements: 8.1–8.8_

- [x] 8. Checkpoint — Priority 1–4 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Priority 5 — Formula Validation Consumers → ACNR full_resolve
  - [x] 9.1 Create shared ACNR-backed validation helper + wire WpFormulaService.save
    - 新建 `backend/app/services/acnr/formula_validation.py`，实现 `validate_refs_via_acnr(db, project_id, year, expression, template_type) -> list[dict]`
    - 拆分 expression 中 WP 域引用 vs 非 WP 域引用（TB/ROW/REPORT/NOTE/AUX）
    - WP 域逐引用调 `full_resolve(formula_ref=..., project_id=..., db=db)`；`found=false` → issue `{ref, reason:"not_found"}`
    - `full_resolve` 抛异常 → 整体回退 `address_registry.validate_formula_refs`（fail-open）+ `logger.warning`
    - 非 WP 域引用仍走 legacy 校验并合并 issues
    - 修改 `wp_formula_service.WpFormulaService.save` 调新 helper 替换直接的 `address_registry.validate_formula_refs`，保持 `(None, issues)` 契约
    - _Requirements: 9.1, 9.3, 9.4_

  - [x] 9.2 Wire report_config + wp_user_formulas to shared helper
    - `routers/report_config.py`（~line 115）与 `routers/wp_user_formulas.py`（~line 221）的 `validate_formula_refs` 调用改用 9.1 的共享 helper
    - 三处共享同一校验语义
    - _Requirements: 9.2_

  - [x]* 9.3 Write property test for fail-open validation (P15)
    - **Property 15: Formula Validation Fail-Open on Infra Error**
    - Hypothesis 生成随机 expression + mock `full_resolve` 抛异常
    - 验证结果与 legacy `validate_formula_refs` 一致，不产生虚假 `not_found`
    - **Validates: Requirements 9.3**

  - [x]* 9.4 Write unit tests for validation helper
    - 测试 WP 域 `found=false` → issue；非 WP 域走 legacy；混合表达式拆分正确
    - 测试三个调用点行为一致
    - _Requirements: 9.1, 9.2, 9.4_

- [x] 10. Checkpoint — Priority 5 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Priority 6 — Invalidation Path Unification
  - [x] 11.1 Add acnr.events.invalidate_domain + route touch_wp_registry through canonical invalidate
    - 在 `backend/app/services/acnr/events.py` 新增 `invalidate_domain(project_id, *, domain, wp_id=None)` 薄封装（domain=="wp" → `invalidate(...)`；其他域委托 legacy）
    - 修改 `wp_parsed_data_service.touch_wp_registry` → 调 `acnr.events.invalidate(project_id, trigger="touch_wp_registry")` 替换直接的 `address_registry.invalidate_async(domain="wp")`
    - 不 re-publish WORKPAPER_SAVED 事件（in-process 直调，避免 handler 重复 fan-out）
    - 异常仅 `logger.warning`，不 raise（保持"失败不阻断主流程"）
    - 确认 canonical `invalidate()` 最后一步仍委托 `address_registry.invalidate_async(domain="wp")`（无回归）
    - _Requirements: 2.5, 2.6, 10.1, 10.2, 10.3, 10.4_

  - [x] 11.2 Route event_handlers TB/REPORT/NOTE invalidation through invalidate_domain
    - 修改 `event_handlers.py` `_invalidate_addr_tb/report/note` 改调 `acnr.events.invalidate_domain(pid, domain="tb"|"report"|"note")`
    - 行为与现状一致（最终委托 legacy），异常仅 warning + continue
    - _Requirements: 11.1, 11.2, 11.3_

  - [x]* 11.3 Write property test for invalidation path convergence (P16)
    - **Property 16: Invalidation Path Convergence**
    - mock 各失效 step，验证 WORKPAPER_SAVED 路径与 touch_wp_registry 路径清理的缓存层集合一致且都含 reverse_index clear
    - 验证 touch_wp_registry 不 re-publish 事件（无重复 fan-out）
    - **Validates: Requirements 2.5, 2.6, 10.1, 10.2, 10.4**

  - [x]* 11.4 Write unit tests for invalidation unification
    - 测试 invalidate_domain 各 domain 委托正确；touch_wp_registry 异常不 raise
    - _Requirements: 10.3, 11.3_

- [x] 12. Checkpoint — Priority 6 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Priority 7 — Custom WP Cell Index → ACNR L3 Runtime
  - [x] 13.1 Register custom WP cells into ACNR L3 runtime (additive)
    - 修改 `address_registry._build_custom_wp_cell_entries`：在产 legacy AddressEntry 后追加调 `acnr.runtime.register_custom`
    - addr_id 用 custom_flat `{wp_code}/{wp_code}/{cell}`；formula_ref `WP('{wp_code}','{wp_code}','{cell}')`
    - project-scoped 注册；单 wp 失败仅 warning + continue
    - 保留 legacy AddressEntry 产出（strangler-fig，不删旧路径）
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [x]* 13.2 Write property test for custom_flat round-trip (P17)
    - **Property 17: Custom Cell addr_id custom_flat Round-Trip**
    - Hypothesis 生成随机 `(wp_code, cell)`，验证 addr_id == `{wp_code}/{wp_code}/{cell}` 且 formula_ref 可被 grammar_v1 custom_flat 解析回同一 addr_id
    - 验证 legacy AddressEntry 仍产出（追加而非替换）
    - **Validates: Requirements 12.1, 12.2**

  - [x]* 13.3 Write unit tests for runtime registration
    - 测试注册进 runtime + `full_resolve` 可命中；单 wp 失败 continue；invalidate 清理 project-scoped runtime
    - _Requirements: 12.3, 12.4_

- [x] 14. Checkpoint — Priority 7 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Priority 8 — Frontend Index Navigation → ACNR resolveIndex
  - [x] 15.1 Add ACNR pre-resolution to useWorkpaperNavigation
    - 修改 `frontend/composables/useWorkpaperNavigation.ts`：`navigateToWorkpaper` 增加 `useAcnr().resolveIndex('wp:'+wpCode)` 前置，命中 jump_route → 直接跳转
    - `found=false`/异常 → 静默回退现有 `index-resolve` API + `resolveRoute`（无回归）
    - A16-1~7 虚拟码与未知码处理不变
    - _Requirements: 13.1, 13.2, 13.4_

  - [x] 15.2 Converge utils/parseIndexRef.ts to ACNR grammar
    - `frontend/utils/parseIndexRef.ts` 内部委托 `services/acnr/resolveUri.ts::parseIndexRef`，或标注为 display-only 并保留
    - 新增契约测试断言两解析器在 11 命名空间上分类等价
    - _Requirements: 13.3_

  - [x]* 15.3 Write unit tests for navigation + parser parity (P18)
    - **Property 18: Frontend Index Parser Parity**
    - 测试 ACNR 命中跳转 jump_route；miss 回退 registry；11 命名空间解析器 parity
    - **Validates: Requirements 13.3**
    - _Requirements: 13.1, 13.2, 13.4_

- [x] 16. Checkpoint — Priority 8 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Checkpoint — Priority 1–8 验证
  - Ensure all tests pass (backend pytest + frontend vitest), no regression on legacy paths, ask the user if questions arise.

- [x] 18. Priority 9 — Formula Pickers + Store → ACNR
  - [x] 18.1 Converge useAddressRegistry store to ACNR (facade, contract-preserving)
    - 修改 `frontend/stores/addressRegistry.ts`：`resolve` 先调 `/api/acnr/resolve` 回退 legacy；`validate` 走 ACNR-backed 回退 legacy(fail-open)；`search` wp 域走 `useAcnr().listSheets/listCells` 映射 AddressEntry，其余域保留 legacy
    - 公共 return 面不变（addresses/*Addresses/refresh/search/resolve/validate/jump/invalidate）
    - `template-applied`/`formula-changed` 复用 debounced refresh + clearCache ACNR 派生缓存
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

  - [x] 18.2 FormulaRefPicker + CellSelector consume ACNR + add WP tab
    - `FormulaRefPicker.vue`：report/tb/note 数据源经收敛后的 store（无需改调用点）；新增 WP tab，数据源 `useAcnr().listSheets`→`loadCellNodes`，选中 emit `WP('parent','sheet','cell')`
    - `CellSelector.vue`：同源 ACNR，空则回退 legacy
    - WP formula_ref 用 grammar_v1 3 参；custom_flat 用 `WP('wp_code','wp_code','cell')`
    - _Requirements: 14.1, 14.2, 14.4, 14.5_

  - [x] 18.3 FormulaEditDialog WP browse from ACNR listCells
    - `utils/wpFormulaPicker.ts` 新增 `mapAcnrCellsToPickerRows(cells)`（`_ref=cell.formula_ref`）
    - `FormulaEditDialog.vue` WP 源浏览改用 ACNR listCells，`pickerRowsSubsetOfRegistry` 语义变 subset-of-ACNR
    - _Requirements: 14.3, 14.5_

  - [x]* 18.4 Write property + unit tests (P19, P21)
    - **Property 19: WP Picker Emits grammar_v1 Formula** — 生成随机 cell，验证 emit formula_ref 可被 parseUri/full_resolve round-trip
    - **Property 21: Store Facade Contract Invariance** — ACNR vs legacy 返回 shape 一致
    - 单测：WP tab 空回退 legacy；三 picker 取数一致
    - **Validates: Requirements 14.2, 14.3, 14.5, 16.1, 16.2, 16.4**

- [x] 19. Checkpoint — Priority 9 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 20. Priority 10 — Formula Management Dialog Load/Edit/Persist Fix
  - [x] 20.1 Backend NoteFormula list/get + upsert endpoint + service
    - `routers/disclosure_notes.py` 新增 `GET /{pid}/{year}/{note_section}/formulas`（已保存优先，否则 generator 预览）+ `PUT .../formulas`（upsert 用户编辑集）
    - 新增 `NoteFormulaService`（`list_by_section`/`save_many`），只 flush 不 commit，router 统一 commit；如需存储加迁移 V1xx
    - 保留 apply-formulas/clear-formulas 语义不变
    - _Requirements: 15.6_

  - [x] 20.2 NoteFormulaDialog load + persist + apply-persisted-set
    - onOpen（watch visible）调 `GET .../formulas` 填充 `formulas`（替换空 ref）
    - 行 `完成` 调 `PUT` 持久化；`addFormula` 推空可编辑行（去掉硬编码 SUM 占位）
    - `onApply` 执行持久化集；新增「重新生成」显式按钮触发 preset 重生成
    - 保存前经 ACNR 校验（Req 9），悬空引用 ElMessage 提示不入库
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x]* 20.3 Write property + unit tests (P20)
    - **Property 20: Formula Dialog Edit Persistence Round-Trip** — save→reload 恒等
    - 单测：onOpen 加载非空；编辑持久化跨重开；apply 执行持久集不重生成；悬空引用拦截
    - **Validates: Requirements 15.1, 15.2, 15.4**

- [x] 21. Checkpoint — Priority 10 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 22. Priority 11 — Note Tree Position → ACNR NOTE Index
  - [x] 22.1 Add indexRef to note tree + ACNR resolveIndex jump
    - `useNoteTree.ts` `TreeNode` 增加可选 `indexRef?: string`（`note:{note_section}`），additive 不改结构/分组/拖拽
    - 节点索引 chip/跳转经 `useAcnr().resolveIndex('note:'+section)` 取 jump_route，unresolved 回退现有 note 导航
    - NOTE 域走 full_resolve V1 delegation，无需预登记 catalog
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

  - [x]* 22.2 Write property + unit tests (P22)
    - **Property 22: Note Index Additive Non-Regression** — 加 indexRef 不改 id/label/children/排序/分组
    - 单测：resolveIndex 命中跳转；未命中回退
    - **Validates: Requirements 17.1, 17.3**

- [x] 23. Checkpoint — Priority 11 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 24. Checkpoint — Priority 1–11 验证
  - Ensure all tests pass (backend pytest + frontend vitest), no regression on legacy paths, ask the user if questions arise.

- [x] 25. Priority 12 — Bundle Directory Tabs → ACNR Catalog Index
  - [x] 25.1 Create useAcnrCatalogIndex(cycle) helper
    - 新建 `frontend/components/workpaper/composables/useAcnrCatalogIndex.ts`
    - 调 `useAcnr().listSheets(cycle)` → `Map<sheet_code,{sheet_name,addr_id,order}>`
    - catalog 空/失败 → 返回空 map（调用方回退硬编码）
    - _Requirements: 18.1, 18.7_

  - [x] 25.2 Migrate D2TabIndex + D4TabIndex to catalog-sourced names (pilots)
    - `D2TabIndex.vue`/`D4TabIndex.vue`：`indexRows` 的 name/code/order 从 `useAcnrCatalogIndex` 取；tabName/applicable/完成检测保留本地按 sheet_code keyed config
    - 跨底稿跳转行用 `GtIndexChip`；纯 bundle 内 sheet 切换保留 `jumpToSection`
    - catalog 不可用回退现有硬编码 rows（无空白目录）
    - per-project applicability(ipoGroupVisible/hasExportBusiness)+isSheetComplete 保持本地
    - _Requirements: 18.2, 18.3, 18.5, 18.6, 18.7_

  - [x] 25.3 Contract test: TabIndex codes ⊆ ACNR catalog
    - `test_tabindex_codes_in_acnr_catalog`：收集 D2/D4 TabIndex sheet_code 集合，断言全部存在于 ACNR catalog
    - _Requirements: 18.4_

  - [x]* 25.4 Write property + unit tests (P23)
    - **Property 23: TabIndex Code ⊆ ACNR Catalog** — 迁移后 TabIndex sheet_code ⊆ catalog；catalog 空回退全量硬编码
    - 单测：名称从 catalog 取；tabName/applicable 本地；降级回退
    - **Validates: Requirements 18.1, 18.4, 18.7**

- [x] 26. Checkpoint — Priority 12 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 27. Checkpoint — Priority 1–12 验证
  - Ensure all tests pass (backend pytest + frontend vitest), no regression on legacy paths, ask the user if questions arise.

- [x] 28. Priority 13 — Consolidation Module Address/Name References → ACNR
  - [x] 28.1 Create useConsolSubjectSource helper + migrate EliminationSheet subjectTree (pilot)
    - 新建 `frontend/components/consolidation/composables/useConsolSubjectSource.ts`：从 ACNR-backed store `tbAddresses`(Req 16)/TB 域取标准科目名，产出与现 subjectTree 同构树（disabled 父节点 + 叶子科目名）
    - `EliminationSheet.vue` 用 helper 替换硬编码 subjectTree；registry 空回退硬编码
    - buildAutoEntries + Excel 导入导出逻辑不变
    - _Requirements: 19.1, 19.5, 19.7_

  - [x] 28.2 Migrate useReportCrossCheck to ACNR REPORT-domain resolution
    - `useReportCrossCheck.loadCrossCheckData/computeCrossCheckResults`：经 ACNR REPORT 域/store reportAddresses 取 canonical row_code→row_name，用 row_code 精确取值替代中文名模糊匹配
    - 7 条勾稽等式逻辑不变；miss 回退现有模糊匹配
    - _Requirements: 19.2, 19.5, 19.7_

  - [x] 28.3 Wire EliminationSheet formula/nav to ACNR + contract test
    - `open-formula` 走 Req 14 ACNR picker；`goto-sheet` 跨底稿跳转经 GtIndexChip/ACNR resolve
    - 契约测试 `test_crosscheck_codes_in_report_registry`：cross-check 用的 BS-*/IS-* 存在于 report-config 地址注册表
    - _Requirements: 19.3, 19.6_

  - [x]* 28.4 Migrate remaining consolidation worksheets to shared helper (incremental)
    - InternalTradeSheet/InternalArApSheet/CapitalReserveSheet/NetAssetSheet 等复用 useConsolSubjectSource 替换各自硬编码科目引用
    - _Requirements: 19.4_

  - [x]* 28.5 Write property + unit tests (P24)
    - **Property 24: Consolidation Name Source Fidelity + Fallback** — registry 可用时名称/码 ⊆ registry；不可用回退全量硬编码；计算结果与迁移前一致
    - 单测：subjectTree 从 store 取；cross-check row_code 精确取值；降级回退
    - **Validates: Requirements 19.1, 19.2, 19.5, 19.7**

- [x] 29. Checkpoint — Priority 13 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 30. Checkpoint — Priority 1–13 验证
  - Ensure all tests pass (backend pytest + frontend vitest), no regression on legacy paths, ask the user if questions arise.

- [x] 31. Priority 14 — Consolidated Report / Notes / Worksheet Address References → ACNR
  - [x] 31.1 合并报表: report/account references → ACNR REPORT/TB (chip + drill)
    - 合并报表视图的报表行/account 引用渲染改用 GtIndexChip（REPORT/TB 域）或经 Req 16 store reportAddresses/tbAddresses 取 canonical 地址
    - `reports.consolBreakdown(accountCode)` drill 的 account_code 经 ACNR TB 域解析取 jump_route
    - 报表数值/生成/balance-check 逻辑不变；miss 回退纯文本
    - _Requirements: 20.1, 20.2, 20.7, 20.9_

  - [x] 31.2 合并附注: note section references → ACNR NOTE resolveIndex
    - 合并附注 note section 引用经 `useAcnr().resolveIndex('note:'+sectionId)` 解析/跳转（NOTE 域 V1 delegation）
    - reaggregate 溯源以 NOTE addr 标识源单体附注 section；reaggregate 计算不变；miss 回退现有 note 导航
    - _Requirements: 20.3, 20.4, 20.7, 20.9_

  - [x] 31.3 合并工作底稿: unify all worksheet open-formula/goto-sheet → ACNR (parent wiring)
    - `ConsolWorksheetTabs` 父级统一把子 worksheet 的 `open-formula` 接到 Req 14 ACNR formula picker（一处接线惠及全部 ~15 worksheet）
    - `goto-sheet` 经 GtIndexChip/ACNR resolve；`worksheet.drillTrialBalance` account_code 作 ACNR TB 地址
    - miss 回退现有公式弹窗/导航行为
    - _Requirements: 20.5, 20.6, 20.7_

  - [x] 31.4 Contract tests: consol report codes + note sections in registry
    - `test_consol_report_codes_in_registry` / `test_consol_note_sections_in_registry`：合并报表 account_code、合并附注 section 集合在 ACNR REPORT/NOTE 覆盖内（V1 动态域豁免）
    - _Requirements: 20.8_

  - [x]* 31.5 Write property + unit tests (P25)
    - **Property 25: Consolidation Address Resolution Additive + Numbers Unchanged** — 可解析时得 addr/jump_route；不可解析回退；计算输出与迁移前一致
    - 单测：报表行 chip 跳转；附注 section resolveIndex；worksheet open-formula 接 ACNR picker；降级回退
    - **Validates: Requirements 20.1, 20.3, 20.5, 20.7, 20.9**

- [x] 32. Checkpoint — Priority 14 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 33. Checkpoint — Priority 1–14 验证
  - Ensure all tests pass (backend pytest + frontend vitest), no regression on legacy paths, ask the user if questions arise.

- [x] 34. Priority 15 — Full-Sweep Closure (公式生态收口 + 后端产出方 + 覆盖 Ledger)
  - [x] 34.1 Migrate FormulaManagerDialog + FormulaBar to ACNR source (complete formula ecosystem)
    - `FormulaManagerDialog.vue`/`FormulaBar.vue` 的地址候选源改走 Req 16 store facade / useAcnr；构造 grammar_v1-valid formula_ref（含 2 参语义列 `WP(code,审定数)` / 3 参 cell / custom_flat 三形态）
    - 与 FormulaRefPicker/FormulaEditDialog/NoteFormulaDialog/CellSelector 六组件同模式
    - _Requirements: 14.5, 14.6_

  - [x] 34.2 Contract test: all formula-construction refs parse under grammar_v1
    - 断言 6 个前端公式构造组件 + query_builder.py 产出的 formula_ref 全部 `parseUri`/`_formula_ref_to_addr_id` 非 null
    - _Requirements: 14.7, 21.3_

  - [x] 34.3 Backend producers alignment: formula_engine + wp_structure_bridge + query_builder
    - `formula_engine.py` WP 域解析先试 full_resolve/runtime，miss 回退 extract_custom_cells（fail-open）
    - `wp_structure_bridge.py` build_uri 追加 register_custom 进 L3 runtime（保留 legacy 产出）
    - `query_builder.py` ref 语法 grammar_v1 契约（并入 34.2）
    - _Requirements: 21.1, 21.2, 21.3_

  - [x] 34.4 Coverage Ledger drift guard test
    - 依 design Coverage Ledger 建 CI 契约测试：新增 `address_registry.` 直接消费者若不在豁免白名单且无 Ledger 条目 → CI 失败
    - _Requirements: 22.1, 22.2, 22.3_

  - [x]* 34.5 Write property tests (P26, P27)
    - **Property 26: Formula-Ref Grammar Closure** — 所有构造点 formula_ref 可被 grammar_v1 解析
    - **Property 27: Legacy-Consumer Drift Guard** — 新 legacy 消费者无 Ledger 条目则 CI 失败
    - **Validates: Requirements 14.6, 14.7, 21.3, 22.2**

- [x] 35. Checkpoint — Priority 15 验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 36. Grand Final Checkpoint — P1–P15 全量验证
  - Ensure all tests pass (backend pytest + frontend vitest), no regression on legacy paths, Coverage Ledger 全绿, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation per priority group
- Property tests validate universal correctness properties (P1–P14)
- Unit tests validate specific examples and edge cases
- Python 后端使用 Hypothesis（max_examples=100+）, 前端使用 vitest
- 优先级分组独立可验证：P1(formula+events) → P2(graph+stale) → P3(bulk) → P4(picker)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "1.4", "1.5"] },
    { "id": 2, "tasks": ["3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.5"] },
    { "id": 4, "tasks": ["3.4", "3.6"] },
    { "id": 5, "tasks": ["3.7"] },
    { "id": 6, "tasks": ["3.8", "3.9"] },
    { "id": 7, "tasks": ["5.1", "5.2"] },
    { "id": 8, "tasks": ["5.3", "5.4"] },
    { "id": 9, "tasks": ["5.5", "5.6"] },
    { "id": 10, "tasks": ["7.1"] },
    { "id": 11, "tasks": ["7.2"] },
    { "id": 12, "tasks": ["9.1"] },
    { "id": 13, "tasks": ["9.2", "9.3", "9.4"] },
    { "id": 14, "tasks": ["11.1"] },
    { "id": 15, "tasks": ["11.2", "11.3", "11.4"] },
    { "id": 16, "tasks": ["13.1"] },
    { "id": 17, "tasks": ["13.2", "13.3"] },
    { "id": 18, "tasks": ["15.1", "15.2"] },
    { "id": 19, "tasks": ["15.3"] },
    { "id": 20, "tasks": ["18.1"] },
    { "id": 21, "tasks": ["18.2", "18.3"] },
    { "id": 22, "tasks": ["18.4"] },
    { "id": 23, "tasks": ["20.1"] },
    { "id": 24, "tasks": ["20.2", "20.3"] },
    { "id": 25, "tasks": ["22.1", "22.2"] },
    { "id": 26, "tasks": ["25.1"] },
    { "id": 27, "tasks": ["25.2", "25.3"] },
    { "id": 28, "tasks": ["25.4"] },
    { "id": 29, "tasks": ["28.1", "28.2"] },
    { "id": 30, "tasks": ["28.3", "28.4"] },
    { "id": 31, "tasks": ["28.5"] },
    { "id": 32, "tasks": ["31.1", "31.2", "31.3"] },
    { "id": 33, "tasks": ["31.4", "31.5"] },
    { "id": 34, "tasks": ["34.1", "34.3"] },
    { "id": 35, "tasks": ["34.2", "34.4", "34.5"] }
  ]
}
```

## Retrospective Expansion Notes (P5–P8)

- P5–P8 来自「ACNR 开发完成后代码库复盘」，补齐 P1–P4 之外仍依赖旧 address_registry / 前端自解析的消费点。
- **P6（task 11.1）修复 P1 的死代码风险**：`touch_wp_registry` 原直调 `address_registry.invalidate_async` 绕过 `acnr.events.invalidate`，导致 task 1.3 的 reverse_index 清理在该热路径不触发。P6 让两条失效路径收敛到 canonical invalidate。
- design §1 已补 sync→async 桥接与 WP() 参数形态两处风险修复（影响 P1 task 1.1 可行性）。
- 优先级建议：P6（失效链收敛，修 P1 死代码）> P5（校验收敛）> P7（自定义 cell 入 L3）> P8（前端索引收敛）。P6 依赖 P1 的 events.invalidate 增强先落地。

## Retrospective Expansion Notes (P9–P11 · 公式/附注/索引 UI 面)

- 第二轮复盘覆盖用户点名的 5 个面：
  - **附注树形结构位置和索引** → P11(Req 17)：`useNoteTree.TreeNode` 加 `note:{section}` 索引，走 ACNR resolveIndex。
  - **公式管理模块索引** → P9(Req 14+16)：`FormulaRefPicker`/`CellSelector`/`FormulaEditDialog` 取数换 ACNR，新增 WP tab；`useAddressRegistry` store facade 收敛。
  - **高级查询树形索引** → 已由 **P4(task 7.1 CustomQueryFieldPicker)** 覆盖（greenfield useAcnr.buildAddressTree）。
  - **底稿模块索引** → 已由 **P8(useWorkpaperNavigation)** + GtIndexChip(已迁 ACNR) 覆盖。
  - **公式管理弹窗显示编辑问题** → P10(Req 15)：`NoteFormulaDialog.formulas` 空 ref 从不加载、编辑不持久化；后端仅 apply/clear 无 list/save → 新增 GET/PUT formulas + NoteFormulaService，弹窗 onOpen 加载 + 编辑持久化 + apply 执行持久集。
- 依赖：P9 的 picker(18.2/18.3) 依赖 store 收敛(18.1)先落地；P10 前端(20.2) 依赖后端端点(20.1)。
- 优先级建议（叠加第一轮 P6>P5>P7>P8 之后）：**P10(修弹窗真 bug，用户可感)> P9(公式索引统一)> P11(附注索引)**。

## Retrospective Expansion Notes (P12 · Bundle 目录索引 Tab)

- 第三轮复盘（截图页 = WorkpaperList + 逐一排查 wp_code/索引消费点）结论：
  - **GtIndexChip** 已完全迁 ACNR（resolve/resolveInstance/jump_route）——标杆。
  - **WorkpaperList（截图页）** 按 wp_id 直跳，wp_code 仅展示 → 不需 ACNR；wp_code 列 chip 化为可选(Req 13.7)。
  - **legacy navigateToWorkpaper 的 6 调用点**(SourceRefChip/WorkpaperTraceView/MyTodoCard/ReviewOpinionList/DocAiChatPanel/WorkpaperHtmlTable) → 由 **P8(Req 13.5)** 迁 composable 一并修复。
  - **Bundle 目录 Tab**(D2TabIndex 16行/D4TabIndex 42行/每循环一个) 硬编码 sheet_code→名称+假 `→` span+jumpToSection → **P12(Req 18)**：名称从 ACNR catalog 取(真源)，routing/applicable/完成检测保留本地，跨底稿跳转用 GtIndexChip，契约测试防漂移，catalog 空回退硬编码。
- 依赖：P12 的 D2/D4 迁移(25.2) 依赖 helper(25.1)。
- 全景更新：**P1–P12 共 12 组**。综合优先级 **P6 > P10 > P5 > P9 > P7 > P8 > P11 > P12**（P12 为一致性/防漂移，非阻断）。

## Retrospective Expansion Notes (P13 · 合并模块)

- 第四轮复盘（合并模块地址坐标名称引用）结论：
  - **EliminationSheet.subjectTree** 硬编码五级科目名 → P13 用 `useConsolSubjectSource` 从 ACNR-backed store tbAddresses/TB 域取真源，回退硬编码。
  - **useReportCrossCheck** 硬编码 BS-*/IS-* + 中文名模糊匹配 → 经 ACNR REPORT 域/reportAddresses 取 canonical row_code 精确取值，勾稽逻辑不变，miss 回退。
  - **EliminationSheet open-formula/goto-sheet** → 接 Req 14 ACNR picker + GtIndexChip。
  - **其余 ~15 合并 worksheet** 硬编码科目引用 → 复用同一 helper（增量 optional 28.4）。
  - 契约测试防 report code 漂移；buildAutoEntries + Excel 导入导出逻辑不动（只换坐标名称来源）。
- 依赖：28.1/28.2 依赖 Req 16 store 收敛（P9）先落地更佳；28.3 依赖 Req 14（P9）。
- 全景更新：**P1–P13 共 13 组**。综合优先级 **P6 > P10 > P5 > P9 > P7 > P8 > P11 > P12 > P13**（P13 一致性/防漂移，依赖 P9 的 store/ picker 收敛）。

## Retrospective Expansion Notes (P14 · 合并报表/附注/工作底稿)

- 第四轮复盘补全（用户强调不要忽视合并模块，覆盖三块）：
  - **合并报表**：consolBreakdown(accountCode)/balance-check 报表行/account 地址 → ACNR REPORT/TB 域 + GtIndexChip drill；数值/生成逻辑不变。
  - **合并附注**：notes.reaggregate/consolBreakdown(sectionId) note section → ACNR NOTE 域 resolveIndex；reaggregate 溯源以 NOTE addr 标识；计算不变。
  - **合并工作底稿**：~15 worksheet 的 open-formula/goto-sheet 由 `ConsolWorksheetTabs` 父级**统一接线**到 Req 14 ACNR picker（一处惠及全部），drill account_code 作 ACNR TB 地址。
  - 契约测试防 report code/note section 漂移（V1 动态域豁免）；降级回退现有行为；计算输出恒等（P25）。
- 与 Req 19 关系：Req 20.5 是 19.3 的推广（父级统一接线覆盖全部 worksheet）；Req 19=科目树+勾稽数据名源，Req 20=报表/附注/worksheet formula-nav-drill 地址。
- 依赖：P14 依赖 Req 14(P9) formula picker + Req 16(P9) store + Req 17(P11) note index 先落地。
- 全景更新：**P1–P14 共 14 组**。综合优先级 **P6 > P10 > P5 > P9 > P7 > P8 > P11 > P12 > P13 > P14**（P13/P14 合并模块一致性，依赖 P9/P11 收敛）。

## Full-Sweep Closure Notes (P15)

- 第五轮全库穷举扫描（`address_registry.` 导入 / `useAddressRegistry`+`navigateToWorkpaper` 消费 / `WP()TB()REPORT()NOTE()` 构造 / `auto_data_resolvers`）后收口：
  - **公式构造生态收全 6 组件**：新增 FormulaManagerDialog + FormulaBar（Req 14.6）；承认 2 参语义列 `WP(code,审定数)` 形态（Req 14.5）。
  - **导航调用点 7 个**：补 WpPopupDocxEditor（Req 13.5）。
  - **后端产出方 3 处**：formula_engine 解析 / wp_structure_bridge 产出 / query_builder ref 语法（Req 21）。
  - **豁免明确**：legacy router(fallback)/ACNR core delegation/auto_data 数据 resolver 记入 Coverage Ledger 豁免。
  - **无死角保证**：design 增 Coverage Ledger（全消费点→P 映射）+ CI drift guard（Req 22，新 legacy 消费者无 Ledger 条目即 CI 失败）。
- 全景更新：**P1–P15 共 15 组**。综合优先级 **P6 > P10 > P5 > P9 > P7 > P8 > P11 > P12 > P13 > P14 > P15**（P15 收口/防漂移，依赖 P9 公式生态收敛）。
- **Coverage Ledger（design.md）是"无死角"可核查真源**：全库扫描无未映射消费点。