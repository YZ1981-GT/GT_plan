# Requirements Document

## Introduction

ACNR（地址坐标名称注册中心）核心基础设施已完成（catalog、resolver、manifest、events、前端 SDK），但平台中多个现存消费者仍依赖旧 address_registry / 硬编码路径。本需求描述将 4 个优先级消费者接入 ACNR 统一解析体系的 wiring 工作：

1. **公式引擎 resolve 目标迁移** — cross_sheet_resolver → ACNR full_resolve
2. **EventBus 失效链补全** — on_workpaper_saved → invalidate_reverse_index
3. **LinkageGraphBuilder 全 addr_id 归一化** — 10 数据源 URI → addr_id
4. **StalePropagationEngine addr_id 兼容** — 接受新旧两种格式
5. **stale_impact(addr_id) API 端点** — 按 addr_id 查询下游影响
6. **Bulk ZIP manifest 消费者切换** — wp_bulk_tab_export → manifest.list_import_export
7. **Bulk ZIP 拓扑排序** — depends_on_sheets 决定导入顺序
8. **CustomQueryFieldPicker 迁移** — 硬编码选址树 → useAcnr.buildAddressTree

## Glossary

- **ACNR**: Address Coordinate & Naming Registry，地址坐标名称注册中心
- **addr_id**: ACNR 稳定主键，格式 `{wp_code}/{sheet_code}/{coordinate_key}`
- **full_resolve**: ACNR resolver 统一解析决策树入口（`backend/app/services/acnr/resolver.py`）
- **ResolveResult**: full_resolve 返回的标准化契约 dataclass
- **CrossSheetResolver**: 跨 sheet 公式追溯器（`backend/app/services/custom_query/cross_sheet_resolver.py`）
- **LinkageGraphBuilder**: 统一依赖图构建器（`backend/app/services/linkage_graph_builder.py`）
- **StalePropagationEngine**: 过时传播引擎，BFS 下游影响分析（`backend/app/services/stale_propagation_engine.py`）
- **EventBus**: 进程内事件总线（publish 走 handlers + SSE，broadcast_raw 纯 SSE）
- **WORKPAPER_SAVED**: 底稿保存事件类型
- **FormulaReverseIndex**: 公式反向索引服务（`backend/app/services/formula_reverse_index.py`）
- **manifest.list_import_export**: ACNR manifest 层 bulk I/E 清单生成方法
- **depends_on_sheets**: catalog import_export 段中声明的 sheet 间依赖列表
- **useAcnr**: 前端 ACNR composable（`audit-platform/frontend/src/services/acnr/useAcnr.ts`）
- **buildAddressTree**: useAcnr 提供的公式选址树构建方法
- **CustomQueryFieldPicker**: 高级查询字段选择器组件（待创建/迁移）
- **URI**: 统一资源标识符，格式 `{domain}://{source}/{path}#{cell}`
- **catalog**: ACNR L1 静态目录 JSON（sheets + cells）

## Requirements

### Requirement 1: Formula Engine Resolve Target Migration

**User Story:** As a formula engine consumer, I want cross-sheet references to be resolved through ACNR full_resolve, so that all formula resolution uses a single canonical resolver with consistent addr_id output.

#### Acceptance Criteria

1.1 WHEN CrossSheetResolver encounters a cross-sheet reference formula, THE CrossSheetResolver SHALL call ACNR full_resolve with formula_ref parameter to obtain the target addr_id.

1.2 WHEN full_resolve returns found=true, THE CrossSheetResolver SHALL use the ResolveResult.addr_id as the canonical node identifier in the reference chain.

1.3 WHEN full_resolve returns found=false, THE CrossSheetResolver SHALL fall back to the existing snapshot-based extraction and mark the node with a `resolve_missed=true` flag.

1.4 THE CrossSheetResolver SHALL pass project_id to full_resolve when available in the resolve call context, enabling L2 overlay and wp_id attachment.

1.5 THE CrossSheetResolver SHALL preserve backward compatibility by returning the same RefChainResponse structure to all existing callers.

1.6 WHEN full_resolve raises an exception, THE CrossSheetResolver SHALL log the error at warning level and continue with snapshot-based fallback without interrupting the BFS traversal.

### Requirement 2: EventBus Invalidation Chain Completion

**User Story:** As a platform maintainer, I want the WORKPAPER_SAVED event to also invalidate the formula reverse index, so that stale cached reverse edges are cleared when any workpaper is saved.

#### Acceptance Criteria

2.1 WHEN the WORKPAPER_SAVED event fires, THE ACNR events.invalidate function SHALL also call invalidate_reverse_index to clear the cached FormulaReverseIndex singleton.

2.2 WHEN invalidate_reverse_index raises an exception, THE ACNR events.invalidate function SHALL log the error at warning level and continue without re-raising.

2.3 THE invalidation chain execution order SHALL be: L3 RuntimeIndex clear → L2 overlay clear → FormulaReverseIndex clear → legacy address_registry delegate.

2.4 WHEN a WORKPAPER_SAVED event with extra.sheets is received, THE invalidation function SHALL still perform full reverse_index invalidation regardless of incremental mode.

### Requirement 3: LinkageGraphBuilder Full addr_id Normalization

**User Story:** As a dependency graph consumer, I want all graph nodes to use ACNR addr_id as identifiers, so that the unified dependency graph is consistent with the ACNR addressing scheme and stale propagation can match nodes by addr_id.

#### Acceptance Criteria

3.1 THE LinkageGraphBuilder SHALL normalize all node URIs to ACNR addr_id format (`{wp_code}/{sheet_code}/{coordinate_key}`) for WP-domain nodes.

3.2 WHEN building nodes from prefill_formula_mapping.json, THE LinkageGraphBuilder SHALL convert `WP:{wp_code}:{sheet}:{cell_ref}` URIs to addr_id by calling a normalize function that maps to `{wp_code}/{sheet_code}/{cell_ref}`.

3.3 WHEN building nodes from cross_wp_references.json, THE LinkageGraphBuilder SHALL normalize source and target URIs to addr_id format.

3.4 WHEN building nodes from l3_dependencies.json, THE LinkageGraphBuilder SHALL normalize intra-workpaper dependency URIs to addr_id format.

3.5 WHEN building nodes from report_config DB, THE LinkageGraphBuilder SHALL retain the existing URI format for REPORT-domain and TB-domain nodes (non-WP domains are outside ACNR catalog scope).

3.6 WHEN building nodes from note_account_mapping DB, THE LinkageGraphBuilder SHALL retain NOTE-domain URI format for note nodes.

3.7 WHEN building nodes from docx_placeholder_registry.json, THE LinkageGraphBuilder SHALL normalize WP-domain placeholder URIs to addr_id format.

3.8 WHEN building nodes from account_mapping DB, THE LinkageGraphBuilder SHALL retain MAPPING-domain and TB-domain URI formats.

3.9 WHEN building nodes from note_referenced_accounts (binding-derived), THE LinkageGraphBuilder SHALL retain NOTE-domain and TB-domain URI formats.

3.10 THE LinkageGraphBuilder SHALL expose a `_normalize_wp_uri_to_addr_id(uri: str) -> str` helper that maps `WP:{wp_code}:{sheet}:{cell}` to `{wp_code}/{sheet_code}/{cell}`, with sheet_code derived by stripping display-name prefixes.

3.11 THE unified_dependency_graph.json output SHALL contain addr_id-keyed nodes for all WP-domain entries after normalization, while non-WP domain nodes retain their original URI format.

### Requirement 4: StalePropagationEngine addr_id Compatibility

**User Story:** As a stale propagation consumer, I want the engine to accept both legacy URI format and ACNR addr_id format, so that existing callers are not broken during the transition while new callers can use addr_id directly.

#### Acceptance Criteria

4.1 WHEN StalePropagationEngine.on_change receives a source_uri in legacy `WP:{wp_code}:{sheet}:{cell}` format, THE StalePropagationEngine SHALL normalize the URI to addr_id format before performing BFS.

4.2 WHEN StalePropagationEngine.on_change receives a source_uri in addr_id format (`{wp_code}/{sheet_code}/{cell}`), THE StalePropagationEngine SHALL accept and use the addr_id directly for BFS.

4.3 THE StalePropagationEngine SHALL detect the format by checking if the input contains a colon (`:`) prefix pattern (legacy) versus slash (`/`) separators (addr_id).

4.4 WHEN the unified_dependency_graph is loaded, THE StalePropagationEngine SHALL index nodes by addr_id for O(1) lookup during BFS traversal.

4.5 THE StalePropagationEngine.reload_graph method SHALL rebuild the addr_id index whenever the graph is reloaded.

### Requirement 5: stale_impact(addr_id) API Endpoint

**User Story:** As a frontend developer, I want to query stale impact by addr_id, so that the linkage bus can be called with the same identifiers used throughout ACNR without format conversion.

#### Acceptance Criteria

5.1 THE Linkage Bus router SHALL expose a `GET /api/linkage-bus/impact-by-addr` endpoint accepting an `addr_id` query parameter.

5.2 WHEN the addr_id parameter is provided, THE endpoint SHALL call StalePropagationEngine with the addr_id directly (bypassing legacy URI construction).

5.3 THE endpoint SHALL accept optional `max_depth` (default 3) and `project_id` query parameters.

5.4 THE endpoint response SHALL include `addr_id`, `total_affected`, and `affected` list with each entry containing `addr_id`, `depth`, `via_ref`, and `match_type`.

5.5 IF the addr_id is empty or missing, THEN THE endpoint SHALL return HTTP 400 with detail message "addr_id is required".

5.6 WHILE the StalePropagationEngine is in degraded mode, THE endpoint SHALL return HTTP 503 with detail message indicating degraded mode.

### Requirement 6: Bulk ZIP Manifest Consumer Switch

**User Story:** As a bulk export service, I want to obtain the I/E sheet list from ACNR manifest.list_import_export instead of hardcoded wp_bulk_tab_export logic, so that sheet discovery is centralized in the catalog and new sheets are automatically included.

#### Acceptance Criteria

6.1 WHEN bulk ZIP export is triggered, THE bulk export service SHALL call manifest.list_import_export(db, project_id, cycle) to obtain the list of exportable sheets.

6.2 THE bulk export service SHALL use the manifest entry's `api_prefix` and `item_id` to construct the correct data retrieval endpoint for each sheet.

6.3 WHEN manifest.list_import_export returns an entry with wp_id=None (resolve_instance miss), THE bulk export service SHALL skip that sheet and log a warning with the sheet_code.

6.4 THE bulk export service SHALL use the manifest entry's `sheet_code` as the tab name in the generated ZIP archive.

6.5 WHEN bulk ZIP import is triggered, THE bulk import service SHALL call manifest.list_import_export(db, project_id, cycle) to obtain the list of importable sheets and their routing information.

6.6 THE bulk import service SHALL use the manifest entry's `api_prefix` and `item_id` to route imported data to the correct storage endpoint.

### Requirement 7: Bulk ZIP Topological Sort by depends_on_sheets

**User Story:** As a bulk import consumer, I want sheets to be imported in dependency order, so that sheets depending on data from other sheets are imported after their dependencies are ready.

#### Acceptance Criteria

7.1 WHEN bulk import receives the manifest list, THE bulk import service SHALL perform a topological sort on entries using their `depends_on_sheets` field.

7.2 THE topological sort SHALL place entries with no dependencies (empty depends_on_sheets) before entries that depend on them.

7.3 IF a circular dependency is detected in depends_on_sheets, THEN THE bulk import service SHALL log an error and fall back to import_order numeric sort.

7.4 WHEN two entries have no dependency relationship between them, THE topological sort SHALL use `import_order` as the tiebreaker to maintain stable ordering.

7.5 THE bulk export service SHALL also apply topological sort to determine sheet export order, ensuring that when the ZIP is reimported, dependencies are satisfied.

### Requirement 8: CustomQueryFieldPicker Migration to useAcnr

**User Story:** As a custom query user, I want the field picker to display the ACNR address tree, so that available fields are always in sync with the catalog and I can select any registered cell coordinate.

#### Acceptance Criteria

8.1 THE CustomQueryFieldPicker component SHALL call useAcnr().buildAddressTree(cycle) to obtain the hierarchical field tree.

8.2 WHEN a user expands a sheet node, THE CustomQueryFieldPicker SHALL call useAcnr().loadCellNodes(sheetEntry) to lazily load cell-level children.

8.3 THE CustomQueryFieldPicker SHALL display tree nodes with label from `AcnrTreeNode.label` and store `AcnrTreeNode.addrId` as the selected field value.

8.4 WHEN a cell node is selected, THE CustomQueryFieldPicker SHALL emit the addr_id and formula_ref to the parent custom query form.

8.5 THE CustomQueryFieldPicker SHALL support filtering the tree by cycle code via a prop or internal filter dropdown.

8.6 WHEN the ACNR catalog is updated (signaled by `template-applied` event), THE CustomQueryFieldPicker SHALL clear the useAcnr cache and reload the tree.

8.7 WHILE the useAcnr composable is loading data, THE CustomQueryFieldPicker SHALL display a loading spinner in the tree area.

8.8 IF listSheets or loadCellNodes returns an empty array, THEN THE CustomQueryFieldPicker SHALL display a placeholder message indicating no fields are available for the selected cycle.
