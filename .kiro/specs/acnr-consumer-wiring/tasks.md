# Implementation Plan: ACNR Consumer Wiring

## Overview

将 4 个优先级消费者接入 ACNR 统一解析体系，按优先级分组（P1→P4）逐步交付。核心原则：strangler-fig 模式（旧路径保留 fallback）、addr_id 唯一标识、容错不中断。语言：Python（后端）+ TypeScript/Vue（前端）。

## Tasks

- [ ] 1. Priority 1 — Formula Engine + EventBus Invalidation Chain
  - [ ] 1.1 Enhance CrossSheetResolver to call ACNR full_resolve
    - 修改 `backend/app/services/custom_query/cross_sheet_resolver.py`
    - 在 BFS 循环中对每个跨 sheet 引用先调 `full_resolve(formula_ref, project_id)`
    - 命中（found=true）时使用 `ResolveResult.addr_id` 作为 node URI
    - 未命中时 fallback 到 snapshot 提取，标记 `resolve_missed=True`
    - 新增 `_sync_resolve` 包装器处理 async→sync 转换
    - 异常时 `logger.warning` + 继续 BFS 不中断
    - `RefChainNode` 新增 `resolve_missed: bool = False` 字段
    - 构造函数接收 `project_id` 参数传递给 full_resolve
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 1.2 Write property tests for CrossSheetResolver ACNR integration (P1–P3)
    - **Property 1: ACNR Resolve Fallback Preserves Response Contract**
    - **Property 2: addr_id Used on ACNR Hit**
    - **Property 3: Snapshot Fallback on ACNR Miss**
    - 使用 Hypothesis 生成随机 ResolveResult 组合（found=true/false/exception）
    - 验证无论 full_resolve 结果如何，resolve() 始终返回有效 RefChainResponse
    - **Validates: Requirements 1.2, 1.3, 1.5, 1.6**

  - [ ] 1.3 Enhance ACNR events.invalidate with FormulaReverseIndex clear
    - 修改 `backend/app/services/acnr/events.py`
    - 在 L2 overlay clear 之后、legacy delegate 之前插入 `invalidate_reverse_index()` 调用
    - 执行顺序：L3 RuntimeIndex → L2 Overlay → FormulaReverseIndex → Legacy V1
    - 每步独立 try/except，异常 `logger.warning` 不 re-raise
    - 无论 extra_sheets 参数如何，始终执行完整 reverse_index 失效
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 1.4 Write property test for invalidation chain completeness (P14)
    - **Property 14: Invalidation Chain Completeness**
    - 使用 Hypothesis 注入随机异常组合（任意 step 可能 raise）
    - 验证所有 4 步始终被调用，不因前序异常跳过后续步
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [ ]* 1.5 Write unit tests for CrossSheetResolver and EventBus integration
    - 测试 project_id 正确传递给 full_resolve（Req 1.4）
    - 测试 invalidation 执行顺序（mock 各 step 记录调用序）
    - 测试 extra_sheets 不影响 reverse_index 失效行为
    - _Requirements: 1.4, 2.1–2.4_

- [ ] 2. Checkpoint — Priority 1 验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Priority 2 — LinkageGraphBuilder + StalePropagationEngine + stale_impact Endpoint
  - [ ] 3.1 Implement `_normalize_wp_uri_to_addr_id` pure function
    - 在 `backend/app/services/linkage_graph_builder.py` 中新增 module-level 纯函数
    - 正则匹配 `WP:{wp_code}:{sheet_display}:{cell}` 格式
    - 提取 sheet_code（从 sheet_display 中匹配 `[A-Z]\d+(-\d+)?[A-Z]?` 模式）
    - 非 WP 域 URI 原样返回（REPORT:, TB:, NOTE:, MAPPING:, ADJ:）
    - 输出格式 `{wp_code}/{sheet_code}/{cell}`
    - _Requirements: 3.1, 3.10_

  - [ ]* 3.2 Write property tests for URI normalization (P4–P5)
    - **Property 4: WP URI Normalization Round-Trip Consistency**
    - **Property 5: Non-WP Domain URI Passthrough**
    - 使用 Hypothesis 生成随机 WP URI（合法 wp_code + sheet_display + cell）
    - 验证 WP 域输出含 3 段 `/` 分隔；非 WP 域输入 = 输出
    - **Validates: Requirements 3.1, 3.5, 3.6, 3.8, 3.9, 3.10**

  - [ ] 3.3 Integrate normalization into LinkageGraphBuilder._from_* methods
    - 修改 `_from_prefill_mapping`：WP 域 URI 调 `_normalize_wp_uri_to_addr_id`
    - 修改 `_from_cross_wp_references`：source/target URI 归一化
    - 修改 `_from_l3_dependencies`：intra-wp 依赖 URI 归一化
    - 修改 `_from_docx_placeholders`：WP 域 placeholder URI 归一化
    - 保留 REPORT/TB/NOTE/MAPPING 域原 URI 不变
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.11_

  - [ ]* 3.4 Write property test for graph build invariant (P10)
    - **Property 10: Graph Build Invariant — WP Nodes Use addr_id**
    - Mock 各数据源，验证 build() 输出中所有 `module=="WP"` 节点 id 含 `/` 无 `WP:` 前缀
    - **Validates: Requirements 3.11**

  - [ ] 3.5 Implement StalePropagationEngine addr_id compatibility
    - 修改 `backend/app/services/stale_propagation_engine.py`
    - 新增 `_detect_and_normalize(source_uri)` 格式检测函数
    - `WP:` 前缀 + 多冒号 → legacy → 调 `_normalize_wp_uri_to_addr_id`
    - `/` 分隔无 `WP:` 前缀 → addr_id → 直接使用
    - 新增 `_addr_id_index: dict[str, str]` 字段
    - 新增 `_build_addr_id_index()` 在 graph load 后构建 O(1) 查找索引
    - `reload_graph()` 时重建 index
    - `on_change()` 入口调 `_detect_and_normalize` 后再 BFS
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 3.6 Write property test for format detection (P6)
    - **Property 6: Format Detection Correctness**
    - 使用 Hypothesis 生成两种格式 URI 混合输入
    - 验证 legacy 格式被归一化、addr_id 格式直通不变
    - **Validates: Requirements 4.1, 4.2, 4.3**

  - [ ] 3.7 Implement GET /api/linkage-bus/impact-by-addr endpoint
    - 修改 `backend/app/routers/linkage_bus.py`
    - 新增 `GET /impact-by-addr` 端点
    - 接收 `addr_id`（required）、`max_depth`（default 3）、`project_id`（required）
    - addr_id 空/缺失 → HTTP 400 `"addr_id is required"`
    - engine degraded → HTTP 503
    - 正常调用 `stale_engine.on_change(addr_id)` 返回 BFS 结果
    - 响应含 `addr_id`, `total_affected`, `affected` list（每项含 addr_id/depth/via_ref/match_type）
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 3.8 Write property test for stale_impact response schema (P11)
    - **Property 11: stale_impact Response Schema Completeness**
    - 使用 Hypothesis 生成随机合法 addr_id 输入
    - 验证 200 响应 schema 含所有必需字段、类型正确
    - **Validates: Requirements 5.4**

  - [ ]* 3.9 Write unit tests for stale_impact boundary conditions
    - 测试 addr_id 为空串 → 400
    - 测试 engine degraded → 503
    - 测试正常 addr_id → 200 含正确 schema
    - _Requirements: 5.5, 5.6_

- [ ] 4. Checkpoint — Priority 2 验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Priority 3 — Bulk ZIP Manifest Consumer Switch + Topo Sort
  - [ ] 5.1 Create wp_bulk_tab_export service with manifest integration
    - 新建 `backend/app/services/wp_bulk_tab_export.py`
    - 实现 `list_export_sheets(db, project_id, cycle)` 异步函数
    - 调用 `manifest.list_import_export(db, project_id, cycle)` 获取清单
    - 过滤 `wp_id=None` 条目（log warning + skip）
    - 使用 manifest entry 的 `api_prefix` + `item_id` 构造数据端点
    - 使用 `sheet_code` 作为 ZIP tab 名称
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 5.2 Implement `_topological_sort` with Kahn's algorithm
    - 在同文件中实现拓扑排序纯函数
    - 基于 `depends_on_sheets` 构建有向图
    - Kahn's algorithm 逐层弹出零入度节点
    - 同级无依赖关系时以 `import_order` 为 tiebreaker
    - 环检测：排序结果数 < 输入数 → `logger.error` + fallback import_order 排序
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 5.3 Write property tests for topological sort (P7–P9)
    - **Property 7: Topological Sort Respects Dependencies**
    - **Property 8: Topological Sort Stability via import_order**
    - **Property 9: Circular Dependency Fallback**
    - 使用 Hypothesis 生成随机 DAG、有环图、平级 entry 组合
    - 验证 DAG 输出满足依赖序、无依赖对按 import_order、环时 fallback
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

  - [ ] 5.4 Implement bulk import service with topo sort ordering
    - 在 `wp_bulk_tab_export.py` 中新增 `list_import_sheets(db, project_id, cycle)` 函数
    - 同样调用 manifest + topo sort 获取导入顺序
    - 使用 `api_prefix` + `item_id` 路由数据到正确存储端点
    - 导出也应用 topo sort 确保 ZIP 中 sheet 顺序满足依赖
    - _Requirements: 6.5, 6.6, 7.5_

  - [ ]* 5.5 Write property test for bulk export tab naming (P12)
    - **Property 12: Bulk Export Tab Names Match sheet_code**
    - 使用 Hypothesis 生成随机 manifest entries（含/不含 wp_id）
    - 验证 wp_id≠None 的 entry 对应 tab 名 == sheet_code
    - **Validates: Requirements 6.4**

  - [ ]* 5.6 Write unit tests for bulk export/import service
    - 测试 wp_id=None 条目跳过 + warning 日志
    - 测试 topo sort 输出顺序正确
    - 测试 api_prefix/item_id 构造端点正确
    - _Requirements: 6.1–6.6, 7.1–7.5_

- [ ] 6. Checkpoint — Priority 3 验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Priority 4 — CustomQueryFieldPicker Migration
  - [ ] 7.1 Create CustomQueryFieldPicker Vue component
    - 新建 `audit-platform/frontend/src/components/custom-query/CustomQueryFieldPicker.vue`
    - 调用 `useAcnr().buildAddressTree(cycle)` 获取层级树
    - el-tree lazy 加载：展开 sheet 节点时调 `loadCellNodes(sheetEntry)`
    - 树节点 label = `AcnrTreeNode.label`，存值 = `AcnrTreeNode.addrId`
    - 选中 cell 节点时 emit `select` 事件（含 addrId + formulaRef）
    - 支持 cycle prop 过滤 + showCycleFilter 循环下拉
    - 监听 `template-applied` 事件 → clearCache + reload
    - loading 态显示 spinner、空态显示 el-empty 占位
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [ ]* 7.2 Write unit tests for CustomQueryFieldPicker
    - 测试 buildAddressTree 被调用时传入正确 cycle
    - 测试 template-applied 事件触发 clearCache + reload
    - 测试 loading=true 时展示 spinner
    - 测试空数组时展示 el-empty
    - 测试 cell 节点 click emit 正确 payload（addrId + formulaRef）
    - _Requirements: 8.1–8.8_

- [ ] 8. Final Checkpoint — 全量验证
  - Ensure all tests pass, ask the user if questions arise.

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
    { "id": 11, "tasks": ["7.2"] }
  ]
}
```
