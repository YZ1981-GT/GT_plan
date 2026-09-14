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

2.5 WHEN parsed_data is committed via `touch_wp_registry` / `touch_after_parsed_data_commit` (wp_parsed_data_service.py), THE WP-domain invalidation SHALL route through the same canonical ACNR invalidate entry as WORKPAPER_SAVED, so that the FormulaReverseIndex clear defined in 2.1 actually fires on this hot path (currently `touch_wp_registry` calls `address_registry.invalidate_async(domain="wp")` directly and bypasses the reverse-index clear).

2.6 WHEN `wp_structure` touch or any other WP parsed_data write path triggers invalidation, THE invalidation path SHALL be identical to the WORKPAPER_SAVED path (single canonical invalidate function) to avoid divergent cache states between the two paths.

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

---

## Requirements (Retrospective Expansion — P5–P8)

> 以下需求来自「ACNR 开发完成后的代码库复盘」，覆盖当前 P1–P4 之外仍依赖旧 address_registry / 自解析的消费点。分维度：取数校验（Req 9）、失效链统一（Req 10、11）、索引地址名称（Req 12、13）。均遵循 strangler-fig：旧路径保留为 fallback，ACNR 优先。

### Requirement 9: Formula Validation Consumers → ACNR full_resolve

**User Story:** As a formula-binding maintainer, I want dangling-reference validation on formula save to go through ACNR `full_resolve`, so that "reference exists?" is decided by the single canonical resolver instead of the legacy `address_registry.validate_formula_refs`.

#### Acceptance Criteria

9.1 WHEN `WpFormulaService.save` validates a formula expression before persisting, THE service SHALL resolve each referenced address through ACNR `full_resolve` and treat `found=false` as a dangling reference (reject write, return issues for HTTP 422), preserving the existing `(None, issues)` contract.

9.2 WHEN `routers/report_config.py` and `routers/wp_user_formulas.py` validate formula references, THE validation SHALL use the same ACNR-backed validation path as 9.1 (a shared helper), so the three call sites share one validation semantic.

9.3 WHEN ACNR `full_resolve` raises or is unavailable during validation, THE validation SHALL fall back to `address_registry.validate_formula_refs` and log a warning, never blocking save due to resolver infrastructure failure (fail-open on infra error, fail-closed only on a confirmed miss).

9.4 THE ACNR-backed validation SHALL only re-classify a reference as invalid when `full_resolve` returns a definitive `found=false` for a WP-domain reference; non-WP-domain references (TB/REPORT/NOTE/AUX) SHALL continue to be validated by the existing legacy path until their catalog coverage is confirmed.

### Requirement 10: WP Invalidation Path Unification

**User Story:** As a platform maintainer, I want every WP parsed_data write path to invalidate caches through a single canonical entry, so that the reverse-index clear (Req 2) is guaranteed to run regardless of which write path fired.

#### Acceptance Criteria

10.1 THE `touch_wp_registry` function (wp_parsed_data_service.py) SHALL invoke the canonical ACNR invalidate entry (the same one enhanced in Req 2) instead of calling `address_registry.invalidate_async(domain="wp")` directly.

10.2 THE canonical ACNR invalidate entry SHALL itself continue to delegate to `address_registry.invalidate_async(domain="wp")` as its final step (Req 2.3), so behavior is a superset of the current direct call (no regression).

10.3 WHEN the canonical ACNR invalidate raises, THE `touch_wp_registry` wrapper SHALL log a warning and not raise (preserve current "失败仅 warning，不阻断主流程" contract).

10.4 THE unification SHALL NOT introduce a second WORKPAPER_SAVED event publish; `touch_wp_registry` SHALL call the invalidate function directly (in-process), not re-publish an event, to avoid duplicate handler fan-out.

### Requirement 11: TB / REPORT / NOTE Domain Invalidation via ACNR

**User Story:** As a cache-consistency owner, I want TB/REPORT/NOTE domain invalidations to route through a unified ACNR invalidate entry, so that all five domains share one invalidation surface (WP already migrated).

#### Acceptance Criteria

11.1 THE `_invalidate_addr_tb` / `_invalidate_addr_report` / `_invalidate_addr_note` handlers (event_handlers.py) SHALL route through a unified ACNR invalidate entry that accepts a `domain` argument, rather than each calling `address_registry.invalidate_async(domain=...)` inline.

11.2 THE unified invalidate entry SHALL, for non-WP domains, delegate to `address_registry.invalidate_async(pid, domain=domain)` (behavior parity) while providing a single seam for future L2/L3 ACNR overlay clearing per domain.

11.3 WHEN any per-domain invalidate raises, THE handler SHALL log a warning and continue (no re-raise), matching the existing best-effort semantics.

### Requirement 12: Custom WP Cell Index → ACNR L3 Runtime

**User Story:** As an address catalog owner, I want custom-workpaper cell coordinates extracted from parsed_data to also register into the ACNR L3 runtime layer, so that user-defined cells become resolvable via `full_resolve` instead of living only in the legacy address_registry.

#### Acceptance Criteria

12.1 WHEN `extract_custom_cells` / `_build_custom_wp_cell_entries` produce custom WP cell records, THE records SHALL also be registered into the ACNR L3 runtime layer (`register_custom` / runtime entries) keyed by addr_id `{wp_code}/{wp_code}/{cell}` (custom_flat profile), in addition to the existing legacy AddressEntry output.

12.2 THE runtime registration SHALL derive `formula_ref` consistent with grammar_v1's custom_flat profile so `full_resolve` can round-trip the cell (reconciling the current legacy 2-arg `WP('wp_code','cell')` form with the ACNR grammar).

12.3 THE runtime registration SHALL be project-scoped (keyed by project_id) and SHALL be cleared by the canonical ACNR invalidate entry (Req 2 / Req 10) when the owning workpaper is saved.

12.4 WHEN runtime registration fails for a given wp_code, THE builder SHALL log a warning and continue with remaining workpapers (no full-batch failure), preserving the current per-wp skip behavior.

### Requirement 13: Frontend Index Navigation → ACNR resolveIndex

**User Story:** As a frontend developer, I want index-chip navigation to resolve through ACNR, so that index parsing uses one canonical grammar shared with the backend instead of a duplicate local parser.

#### Acceptance Criteria

13.1 WHEN `useWorkpaperNavigation.navigateToWorkpaper` resolves an index code, THE composable SHALL attempt ACNR `useAcnr().resolveIndex` / `resolveInstance` to obtain `wp_id` + `jump_route` before falling back to the existing `useWorkpaperRegistry` lookup + `index-resolve` API.

13.2 WHEN ACNR resolution returns `found=false` or errors, THE composable SHALL fall back to the current registry-based path unchanged (no regression for unmigrated codes).

13.3 THE local parser `utils/parseIndexRef.ts` SHALL converge to the ACNR grammar by either delegating to `services/acnr/resolveUri.ts` (`parseIndexRef`) or being documented as display-only, so there is a single authoritative index-namespace grammar; any retained local copy SHALL be covered by a contract test asserting parity with the ACNR parser on the 11 namespaces.

13.4 THE navigation behavior for A16-1~7 virtual sub-codes and unknown codes SHALL remain unchanged (ACNR path is additive, not a rewrite of existing edge-case handling).

13.5 THE migration of `useWorkpaperNavigation` SHALL transitively fix ALL its call sites — `SourceRefChip.vue`, `WorkpaperTraceView.vue`, `MyTodoCard.vue`, `ReviewOpinionList.vue`, `DocAiChatPanel.vue`, `WorkpaperHtmlTable.vue`, `WpPopupDocxEditor.vue` — with no per-call-site code change required; a smoke/contract check SHALL verify no residual self-parse path remains in these consumers (grep of `useWorkpaperNavigation` importers is the authoritative call-site list).

13.6 THE `WorkpaperTraceView` upstream/downstream lookup MAY continue using `useWorkpaperRegistry` (render-registry: name/upstream/downstream metadata is out of ACNR catalog scope); only its navigation (`navigateToWorkpaper`) SHALL route through the ACNR-migrated composable.

13.7 THE `WorkpaperList` 底稿分配明细 wp_code column MAY optionally render via `GtIndexChip` for cross-workpaper jump consistency, but this is not required for correctness because row navigation already resolves by `wp_id` directly.

---

## Requirements (Retrospective Expansion — P9–P11: 公式/附注/索引 UI 面)

> 第二轮复盘（附注树形结构、公式管理索引、高级查询树、底稿索引、公式管理弹窗显示编辑）。实证结论：`FormulaRefPicker`/`CellSelector` 走 legacy `useAddressRegistry` Pinia store（非 ACNR，无 WP tab）；`FormulaEditDialog` WP 源浏览映射 legacy 注册表条目；`NoteFormulaDialog.formulas` 是空 ref 从不加载、编辑不持久化（后端仅 apply/clear，无 list/save）；`useNoteTree.TreeNode` 无 addr_id/NOTE 索引。高级查询树已由 P4 覆盖、底稿索引跳转已由 P8 覆盖、GtIndexChip 已迁 ACNR。

### Requirement 14: Formula Pickers → ACNR Data Source

**User Story:** As a formula author, I want the reference/edit pickers to draw candidates from ACNR (including WP cells), so that pickable addresses always match the catalog and WP-cell references become selectable.

#### Acceptance Criteria

14.1 THE `FormulaRefPicker` SHALL source report/tb/note candidate rows from ACNR (via `useAcnr` or an ACNR-backed store, Req 16) with the legacy store as fallback, preserving the existing formula construction (`REPORT()`/`TB()`/`NOTE()`) and the `insert` emit contract.

14.2 THE `FormulaRefPicker` SHALL add a WP-domain tab whose candidates come from `useAcnr` `listSheets`/`listCells`, emitting a `WP('parent','sheet','cell')` formula_ref, so WP-cell references become pickable (currently impossible — no WP tab exists).

14.3 THE `FormulaEditDialog` WP source browse (`wpFormulaPicker.mapRegistryToPickerRows`) SHALL map from ACNR `listCells` entries (`addr_id` + `formula_ref`) instead of legacy registry WP entries, keeping the `pickerRowsSubsetOfRegistry` invariant (now subset-of-ACNR-listCells).

14.4 THE `CellSelector` SHALL source addresses from the same ACNR-backed path; WHEN ACNR returns empty, it SHALL fall back to the legacy store (no regression).

14.5 THE WP-domain `formula_ref` emitted SHALL be grammar_v1-valid in one of the three recognized WP forms: 3-arg cell `WP('parent','sheet','cell')`; 2-arg semantic-column `WP('wp_code','审定数')` (the 审定数/semantic-column form used by FormulaEditDialog/FormulaBar); or custom_flat `WP('wp_code','wp_code','cell')` (Req 12.2). The chosen form SHALL round-trip through `full_resolve`/`parseUri`.

14.6 ALL formula-construction / address-picker components SHALL source candidate addresses from ACNR (via the Req 16 store facade or `useAcnr`) and emit grammar_v1-valid `formula_ref`. The exhaustive component set is: `FormulaRefPicker.vue`, `FormulaEditDialog.vue`, `FormulaManagerDialog.vue`, `FormulaBar.vue`, `NoteFormulaDialog.vue`, `CellSelector.vue`. `FormulaManagerDialog` and `FormulaBar` (which currently build `TB()`/`ROW()`/`REPORT()`/`NOTE()`/`WP()` refs from legacy/report sources) SHALL be migrated on the same pattern.

14.7 A contract test SHALL assert that every `formula_ref` produced by the six formula-construction components parses under grammar_v1 (`parseUri`/`_formula_ref_to_addr_id` returns non-null), catching any malformed or drifted formula syntax at CI.

### Requirement 15: Formula Management Dialog Load / Edit / Persist Fix

**User Story:** As a note preparer, I want the formula management dialog to show my existing formulas and keep my edits, so that formula management is not lost on every reopen.

#### Acceptance Criteria

15.1 WHEN `NoteFormulaDialog` opens for a note section, THE dialog SHALL load the current formula set for that section (generated + any user-saved) and populate the list, instead of starting with an empty array.

15.2 WHEN a user edits a formula/description row and confirms, THE edit SHALL be persisted to the backend and SHALL survive dialog close/reopen (currently edits live only in a local `ref` and are lost).

15.3 WHEN a user adds a new formula, THE new row SHALL be an editable blank/template row (not the hardcoded non-resolvable `'SUM(上方明细行)'` placeholder) and SHALL be persisted on confirm.

15.4 WHEN the user clicks 应用自动运算, THE apply SHALL execute the current persisted/edited formula set rather than unconditionally regenerating from `check_presets` and discarding edits; regeneration from presets SHALL be an explicit, separate action (e.g. a "重新生成" button).

15.5 THE formula references entered in the dialog SHALL be validated via the ACNR-backed validation path (Req 9) before persist; dangling references SHALL be surfaced to the user and SHALL NOT be silently saved.

15.6 IF no note-formula persistence endpoint exists, THEN a backend list/get + upsert endpoint SHALL be added (list current formulas for a section; upsert user-edited formulas), analogous to `WpFormulaService.save`, reusing `service 只 flush 不 commit` + router commit conventions.

### Requirement 16: addressRegistry Store ACNR Convergence

**User Story:** As a frontend maintainer, I want the shared address store to resolve/validate through ACNR, so that all pickers converge on ACNR without each changing its call contract.

#### Acceptance Criteria

16.1 THE Pinia `useAddressRegistry` store's `resolve(uri)` SHALL call ACNR `/api/acnr/resolve` first and fall back to legacy `/api/address-registry/resolve` on miss/error.

16.2 THE store's `validate(formula)` SHALL route through the ACNR-backed validation (parity with backend Req 9); infra failure SHALL fall back to legacy (fail-open).

16.3 THE store's `search(keyword, domain)` SHALL be backed by ACNR `listSheets`/`listCells` for the WP domain, retaining legacy search for tb/report/note/aux until their catalog coverage is confirmed.

16.4 THE store's public surface (`addresses`, `tb/report/note/wp/auxAddresses`, `refresh/search/resolve/validate/jump/invalidate`) SHALL remain unchanged, so `FormulaRefPicker`/`CellSelector` need no contract change.

16.5 THE store SHALL clear ACNR-derived caches on `template-applied`/`formula-changed` events, reusing the existing debounced refresh.

### Requirement 17: Note Tree Position → ACNR NOTE Index

**User Story:** As an auditor navigating notes, I want note tree positions to be ACNR-addressable, so that note index chips jump through the same resolver as every other index.

#### Acceptance Criteria

17.1 THE note tree `TreeNode` (useNoteTree) SHALL carry an ACNR-resolvable NOTE-domain index reference (e.g. `note:{note_section}`) in addition to its display label.

17.2 WHEN a note index chip is clicked, THE resolution SHALL go through `useAcnr().resolveIndex('note:...')` to obtain `jump_route`, falling back to the existing note navigation when unresolved.

17.3 THE note tree structure / grouping / drag behavior SHALL remain unchanged; index exposure is additive metadata, not a tree rewrite.

17.4 THE non-catalog note sections SHALL still resolve through the ACNR `full_resolve` V1-delegation path for the NOTE domain, so notes need not be pre-registered in the L1 catalog.

---

## Requirements (Retrospective Expansion — P12: Bundle 目录索引 Tab → ACNR Catalog)

> 第三轮复盘（用户点名"这个页面下的底稿索引坐标名称库 + 逐一排查类似地方"）。实证结论：截图页 `WorkpaperList` 按 wp_id 直接跳转（不需 ACNR）；但 bundle 内的目录索引 Tab（`D2TabIndex` 硬编码 16 行、`D4TabIndex` 硬编码 42 行，每个循环一个）**硬编码 sheet_code→sheet_name**、用假 `→` span、经 `inject('jumpToSection')` 自跳转，既不走 ACNR catalog 名称真源也不用 GtIndexChip。GtIndexChip 已迁 ACNR 可作标杆。

### Requirement 18: Bundle Directory Tabs → ACNR Catalog Index

**User Story:** As a workpaper directory maintainer, I want each bundle's index tab to draw its sheet codes/names from the ACNR catalog, so that the index coordinate names have a single source of truth and cannot drift from the catalog.

#### Acceptance Criteria

18.1 THE bundle directory/index tabs (`D2TabIndex`, `D4TabIndex`, and analogous per-cycle `*TabIndex` components) SHALL derive each row's `sheet_code → sheet_name` (the index coordinate name) from the ACNR catalog (`useAcnr().listSheets(cycle)`) instead of hardcoded literal arrays, so index names cannot drift from the catalog.

18.2 WHERE a directory row needs routing/state metadata not held by the catalog (`tabName`/intra-bundle jump target, per-project applicability, completion detection), THE local config SHALL retain ONLY that metadata keyed by `sheet_code`, merged with catalog-sourced names/codes/order.

18.3 THE directory jump control SHALL use `GtIndexChip` for cross-workpaper jumps (ACNR resolve_instance) and MAY keep the existing `inject('jumpToSection')` for pure intra-bundle sheet switches; a bare hardcoded `→` span for cross-workpaper jumps SHALL be replaced.

18.4 A contract test SHALL assert that every `sheet_code` listed in a migrated `TabIndex` exists in the ACNR catalog (no orphan/misspelled codes), failing CI on drift.

18.5 THE per-project applicability (`ipoGroupVisible`/`hasExportBusiness`) and completion detection (`item_id`-based `isSheetComplete`) SHALL remain local logic; the catalog does not carry per-project state.

18.6 THE migration SHALL be incremental via a shared `useAcnrCatalogIndex(cycle)` helper: `D2TabIndex` + `D4TabIndex` as pilots; remaining cycle `*TabIndex` components adopt the same helper subsequently (no big-bang rewrite).

18.7 WHEN the ACNR catalog is unavailable/empty, THE `TabIndex` SHALL fall back to its current hardcoded rows (no regression / no blank directory).

---

## Requirements (Retrospective Expansion — P13: 合并模块地址坐标名称引用)

> 第四轮复盘（用户点名"合并模块下的地址坐标名称库相关代码引用"）。实证结论：`EliminationSheet` 的 `subjectTree` 是硬编码科目坐标名称树（五级科目中文名），不来自 TB/账户名称真源；`useReportCrossCheck.computeCrossCheckResults` 用硬编码 `BS-001/IS-019` 行码 + 中文名模糊匹配取报表值，未走 ACNR REPORT 域；`ConsolWorksheetTabs` 编排 ~15 个合并底稿，多处类似硬编码科目引用。`EliminationSheet` 还 `emit('open-formula'/'goto-sheet')` 未接 ACNR 公式/跳转。

### Requirement 19: Consolidation Module Address/Name References → ACNR

**User Story:** As a consolidation preparer, I want the consolidation worksheets' subject/report references to draw from the authoritative address/name registries, so that account and report coordinate names stay in sync instead of drifting from hardcoded literals.

#### Acceptance Criteria

19.1 THE `EliminationSheet` subject picker (`subjectTree`) SHALL source its account/subject coordinate names from the authoritative account-name source (ACNR TB-domain / the ACNR-backed address store's `tbAddresses`, Req 16) via a shared helper, rather than a hardcoded literal tree, so consolidation subjects stay in sync with the account name registry.

19.2 THE report cross-check (`useReportCrossCheck.computeCrossCheckResults` / `loadCrossCheckData`) SHALL resolve report line addresses (`row_code → row_name / value`) via ACNR REPORT-domain resolution (or the ACNR-backed address store's `reportAddresses`) instead of ad-hoc hardcoded `BS-*/IS-*` codes + fuzzy Chinese-name matching, improving stability against report label changes.

19.3 THE consolidation worksheet formula/navigation seams (`EliminationSheet` `open-formula` / `goto-sheet` emits, and equivalents) SHALL route through the ACNR-migrated formula picker (Req 14) and `GtIndexChip`/ACNR resolve for cross-sheet jumps.

19.4 THE other consolidation worksheets with hardcoded subject/account pickers (`InternalTradeSheet`, `InternalArApSheet`, `CapitalReserveSheet`, `NetAssetSheet`, etc.) SHALL adopt the same shared account-name helper incrementally, with `EliminationSheet` as the pilot (no big-bang rewrite).

19.5 WHEN the account/report registry is unavailable or empty, THE consolidation worksheets SHALL fall back to the current hardcoded tree/codes (no regression / no blank picker).

19.6 A contract test SHALL validate that the report cross-check `row_code` set (`BS-*/IS-*`) exists in the report-config address registry (no orphan/misspelled report codes), catching drift at CI.

19.7 THE consolidation auto-entry construction (`buildAutoEntries` from equity/income/cross rows) and Excel import/export behavior SHALL remain functionally unchanged; this requirement only replaces the SOURCE of subject/report coordinate names, not the entry/computation logic.

---

## Requirements (Retrospective Expansion — P14: 合并报表/合并附注/合并工作底稿 地址引用)

> 第四轮复盘补全（用户强调"不要忽视合并模块"，需覆盖合并报表、合并附注、合并工作底稿三块）。实证（`services/apiPaths/report.ts` consolidation 面 + worksheet 组件）：`consolidation.reports.consolBreakdown(accountCode)` / `balance-check` 用 account_code/报表行地址；`consolidation.notes.reaggregate/consolBreakdown(sectionId)` 用 note section 地址；~15 worksheet（EliminationSheet/InvestmentEquitySheet/InternalTradeSheet/…）每个都 `emit('open-formula'/'goto-sheet')`，公式/跳转 seam 未接 ACNR；worksheet drill 按 TB account_code。Req 19 仅覆盖 EliminationSheet 科目树 + 报表勾稽，本组补全其余三块。

### Requirement 20: Consolidated Report / Notes / Worksheet Address References → ACNR

**User Story:** As a consolidation reviewer, I want consolidated reports, notes, and all worksheets to address their line items / sections / cells through ACNR, so that consolidation coordinate names and jumps are consistent with the rest of the platform and traceable.

#### Acceptance Criteria

**合并报表 (Consolidated Reports)**

20.1 THE consolidated report display and its drill (`consolidation.reports.consolBreakdown(accountCode)`, `balance-check`) SHALL resolve report line / account addresses via ACNR REPORT-domain (and TB-domain for account codes) resolution — or the ACNR-backed address store (Req 16) — so consolidated report line addresses are ACNR-addressable for chip/trace/jump rather than ad-hoc `account_code` strings.

20.2 WHERE the consolidated report renders a jumpable line/account reference, THE jump SHALL route through `GtIndexChip` / ACNR resolve (REPORT/TB domain), consistent with the standard report module.

**合并附注 (Consolidated Notes)**

20.3 THE consolidated notes' section references (`consolidation.notes` list/save/reaggregate/consolBreakdown by `sectionId`) SHALL resolve note-section addresses via ACNR NOTE-domain (full_resolve V1 delegation, Req 17.4), and note index chips in the consolidated notes SHALL jump via `useAcnr().resolveIndex('note:...')` (Req 17.2).

20.4 THE reaggregate provenance (子公司单体附注 → 合并附注) SHALL reference source note sections by ACNR NOTE address so the consolidation breakdown is traceable through the same addressing scheme; the reaggregate computation logic itself SHALL remain unchanged.

**合并工作底稿 (Consolidation Worksheets)**

20.5 ALL consolidation worksheet `open-formula` seams (`EliminationSheet`, `InvestmentEquitySheet`, `InternalTradeSheet`, `InternalArApSheet`, `CapitalReserveSheet`, `NetAssetSheet`, `MinorityInterestSheet`, `ShareChangeSheet`, `InvestmentCostSheet`, `PostElimInvestSheet`, `PostElimIncomeSheet`, `InternalCashFlowSheet`, `SubsidiaryInfoSheet`, etc.) SHALL open the ACNR-migrated formula picker (Req 14); `goto-sheet` cross-sheet navigation SHALL use `GtIndexChip` / ACNR resolve.

20.6 THE worksheet drill (`worksheet.drillTrialBalance` / `drillCompanies` / `drillEliminations`) that references TB account codes SHALL surface those as ACNR TB-domain addresses for trace/jump consistency.

**共通约束**

20.7 WHEN the ACNR / report / note registry is unavailable or the address is not in catalog, THE consolidated report / notes / worksheet SHALL fall back to current behavior (no regression, no blank render).

20.8 A contract test SHALL validate the consolidated report `account_code` set and consolidated note `section` set against the ACNR REPORT/NOTE registry coverage (drift catch) where catalog coverage exists; codes outside catalog scope (dynamic V1-delegated) are exempt.

20.9 THE consolidation computation/aggregation logic (`reaggregate`, `worksheet.recalc/aggregate`, `reports.generate`, `balance-check` equations) SHALL remain functionally unchanged; this requirement only changes the SOURCE of address/coordinate names and the jump routing, not the numbers.

---

## Requirements (Full-Sweep Closure — P15: 后端产出方/解析方 + 公式构造生态收口)

> 第五轮：全库穷举扫描（`address_registry.` 导入、`useAddressRegistry`/`navigateToWorkpaper` 消费、`WP()/TB()/REPORT()/NOTE()` 构造、`auto_data_resolvers`）后的收口。前端公式构造生态已在 Req 14.6/14.7 收全（6 组件）。本组补后端仍以 legacy AddressEntry / ref 语法产出或解析的三处，并锁定"无死角"契约。

### Requirement 21: Backend Formula/Address Producers & Resolvers Alignment

**User Story:** As a backend maintainer, I want the remaining address producers/resolvers to align with ACNR, so that no server-side path silently produces legacy-only coordinates that ACNR cannot resolve.

#### Acceptance Criteria

21.1 THE `formula_engine.py` WP-cell resolution path (which imports `extract_custom_cells` for custom-workpaper cell lookup, ~line 1484) SHALL, for WP-domain references, prefer ACNR `full_resolve`/runtime lookup (Req 12) and fall back to `extract_custom_cells` only on miss, so formula evaluation and ACNR resolution share one addressing truth (fail-open to legacy on infra error).

21.2 THE `wp_structure_bridge.py` address extractor (`build_uri`/`build_jump_route`, producing `AddressEntry`-compatible entries from `structure.json`) SHALL additionally register its WP-domain coordinates into the ACNR L3 runtime (same pattern as Req 12.1), so structure-derived cells are `full_resolve`-able; legacy `AddressEntry` output retained (strangler-fig).

21.3 THE `query_builder.py` single-value `ref` syntax generator (e.g. `TB('{code}','期末')`, aligned with `address_registry.formula_ref_to_uri`) SHALL emit grammar_v1-valid refs and be covered by a contract test asserting the generated ref parses under grammar_v1 (`full_resolve`/`_formula_ref_to_addr_id` non-null), so advanced-query ref output cannot drift from the canonical grammar.

21.4 THE legacy V1 `routers/address_registry.py` endpoints (search/resolve/validate/invalidate/jump) SHALL be retained as the strangler-fig fallback surface (fronted by the ACNR-backed store, Req 16) and SHALL NOT be removed until consumer migration (P5–P14) is verified complete; their removal is explicitly out of scope for this spec.

21.5 THE ACNR core delegation points (`acnr/events.py`, `acnr/grammar.py`, `acnr/resolver.py` importing legacy `address_registry` for non-WP V1 delegation) are INTENTIONAL strangler-fig seams and SHALL NOT be treated as consumer gaps (documented exemption to prevent future false-positive "legacy usage" flags).

### Requirement 22: No-Blind-Spot Coverage Ledger

**User Story:** As the spec owner, I want a single authoritative ledger mapping every ACNR consumer point to its covering priority, so that "no blind spot" is verifiable rather than asserted.

#### Acceptance Criteria

22.1 THE design document SHALL contain a Coverage Ledger table enumerating every discovered ACNR/address consumer point (backend + frontend) mapped to its covering requirement/priority (P1–P15) or an explicit exemption reason.

22.2 A repository-wide contract/smoke test SHALL enforce that new direct `address_registry.` consumers (outside the documented exemption list: ACNR core + legacy router + retained fallbacks) are not introduced without a corresponding ledger entry, failing CI on an unlisted new legacy consumer (drift guard).

22.3 THE ledger SHALL be updated whenever a new consumer point is discovered, so the sweep remains authoritative over time.
