# Implementation Plan: disclosure-note-linkage-and-slimdown（附注联动修复与瘦身）

## 概述

本计划按 design.md 的「实施顺序建议」分三组顺序推进，最高优先原则是**零功能回归**（Req 1）：附注模块为 49 service + 22 路由 + 66 后端测试的成熟模块，任何改动后每组检查点都要跑附注 66 后端测试全集守护；改动导致既有测试失败时**修改代码而非修改断言**（Req 1.5）。

- **组① 缺口1 P0（最高优先，含修致命 bug）**：让「从底稿刷新」真正重算金额。复用 `DisclosureEngine` 填充链（非 NoteFillEngine），先修 `note_stale_service` 的 import/字段名致命 bug，再重写三条刷新链路写回真实数值，路由透传更丰富返回体，前端区分「已刷新 / 需手动重填」文案。
- **组② 缺口2 P1**：cross_ref auto_pull 真实取数。新建 `NoteAutoPullService` 复用 `note_source_resolvers.dispatch_resolver`（非 custom_query），失败降级不阻断渲染，前端展示拉到的值 + 来源标识。
- **组③ 缺口3 P1（纯重构瘦身）**：先补特征测试锁定行为，再按 7 composable + 2 子 SFC 清单逐个抽取（每抽一个跑特征测试），HARD_CAPS 登记 + vue-tsc 零错误。
- **收尾组**：全量单测 / 属性测试 + Playwright 在线实测（9980 + 3030）。

口径铁律贯穿全程：service 只 flush、router 统一 commit（Req 1.3）；前端原生 http 手动解 `{code,message,data}` 信封；UI 中文 + GT 紫令牌（Req 1.4）；manual 保护判据统一为 `table_data.rows[]._cell_modes[str(col)] != "auto"`。

## Tasks

### 组① 缺口1 P0：从底稿刷新真实重算（含修致命 bug）

- [x] 1. 在 DisclosureEngine 新增窄接口 refill_sections（复用既有填充链）
  - 在 `backend/app/services/disclosure_engine.py` 新增 `@dataclass CellRefillRecord`(section/row_index/col_index/old_value/new_value) 与 `@dataclass RefillReport`(sections_recomputed/text_only_sections/cells_updated/records/errors)
  - 新增 `async def refill_sections(self, project_id, year, section_codes=None, *, skip_manual=True) -> RefillReport`：复用现有 `_preload_data_for_notes` 预热 `_wp_cache/_tb_cache/_prior_notes_cache` + 逐 cell `dispatch_resolver`
  - 只处理 `content_type` 含表格的章节；纯文本/叙述章节计入 `text_only_sections`
  - 仅写 `_cell_modes[str(col)] == "auto"` 的单元格（`skip_manual=True` 时跳过 manual）；逐格比较 old vs new，变化才计 `cells_updated` 并写回 `table_data.values`
  - 写回后 `flag_modified(note, 'table_data')`；**只 flush 不 commit**
  - 取数失败的章节不抛异常，记入 `RefillReport.errors`（`{section}: {reason}`）
  - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6, 2.7, 1.3_

- [x] 2. 修复并重写 note_stale_service 的刷新方法
  - [x] 2.1 修复 note_stale_service 两处致命 bug（触类旁通 grep 全文同类）
    - 将 `from app.models.phase13_models import DisclosureNote`（该类不存在 → ImportError 被宽 `except` 静默吞）改为 `from app.models.report_models import DisclosureNote`
    - 将字段引用 `DisclosureNote.section_code` 改为真实字段 `note_section`（grep 全文件确认 `:88,148,306,97` 等所有引用点一次改全）
    - 移除把 ImportError 伪装成「刷新成功」的宽 `except Exception` 静默吞，改为真实暴露后按降级矩阵处置
    - _Requirements: 2.1_
  - [x] 2.2 重写 refresh_from_workpaper 接 DisclosureEngine 填充链
    - 用 `NoteAccountMapping`/`DEFAULT_WP_MAPPING` 求出受 `wp_code` 影响的 `note_section` 列表
    - 调 `DisclosureEngine(self.db).refill_sections(project_id, year, sections, skip_manual=True)`
    - 对 `report.sections_recomputed` 清 `is_stale`；`text_only_sections` 与取数失败章节保留 `is_stale=True`
    - `result.cells_updated = report.cells_updated`；`result.sections_refreshed = len(sections_recomputed)`；失败原因写入 `result.errors`
    - **只 flush 不 commit**
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 1.3_
  - [x] 2.3 重写 refresh_stale_sections 走真实重算
    - 查 stale 章节 → `refill_sections` → 按结果分别清/留 stale + 真实 `cells_updated`（不再恒为 0）
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.7_
  - [x]* 2.4 写 note_stale_service 单元测试（bug 修复回归 + 文本章节降级）
    - 验证修复后 import 成功、`note_section` 字段可用、刷新真正执行而非空返回
    - 验证纯文本章节被识别并保留 stale（区别于自动重算章节被清 stale）
    - 后端 hypothesis `max_examples=5`（涉随机时）；普通示例用 pytest
    - _Requirements: 2.3, 2.6_

- [x] 3. 重写 note_wp_mapping_service.refresh_from_workpapers 真实写回
  - 删除 `# 简化：标记为已刷新` 自增计数器分支
  - 改为按 `DEFAULT_WP_MAPPING` 命中的 sections 委托 `DisclosureEngine.refill_sections`
  - 返回 `{"refreshed": cells_updated, "sections_recomputed": [...], "text_only_sections": [...], "errors": [...]}`，保持响应键向后兼容（`refreshed`/`total_notes` 仍在）
  - **只 flush 不 commit**
  - _Requirements: 2.1, 2.2, 2.7, 1.3_

- [x] 4. 路由透传更丰富返回体
  - `backend/app/routers/note_wp_mapping.py` 的 `refresh_from_workpapers` 维持「调 service → `await db.commit()`」结构（router 统一 commit）
  - 透传 `cells_updated`、`text_only_sections`、`errors` 给前端
  - _Requirements: 2.7, 2.8, 1.3_

- [x] 5. 前端 useNoteRefresh 区分「已刷新 / 需手动重填」提示文案
  - 在 `DisclosureEditor.vue`（刷新链路 `onRefreshFromWP/onManualRefresh/onStaleRecalc`）收到返回后，依据 `cells_updated` / `text_only_sections` 显示差异化中文提示
  - 有更新 → 「已刷新 N 个单元格」；存在纯文本章节 → 额外「以下章节需手动重填：…」（区别于无脑「已刷新」）
  - 刷新后 `fetchDetail` 重新加载当前章节数据；提示用 GT 紫令牌（非 Element 默认蓝）
  - 原生 http 调用手动解 `{code,message,data}` 信封取 `body.data`
  - _Requirements: 2.8, 2.9, 1.4_

- [x]* 6. 编写组① 属性测试（刷新侧 P1/P2/P3/P4）
  - [x]* 6.1 Property 1：从底稿刷新后金额等价
    - **Property 1: 从底稿刷新后金额等价**
    - **Validates: Requirements 2.1, 2.2, 2.10**
    - 位置 `backend/tests/services/test_note_refill_pbt.py`；hypothesis `max_examples=5`
    - 标签注释 `# Feature: disclosure-note-linkage-and-slimdown, Property 1: 从底稿刷新后金额等价`
    - _Requirements: 2.1, 2.2, 2.10_
  - [x]* 6.2 Property 2：cells_updated 精确计数
    - **Property 2: cells_updated 精确计数**
    - **Validates: Requirements 2.7**
    - 位置 `backend/tests/services/test_note_refill_pbt.py`；hypothesis `max_examples=5`
    - 标签注释 `# Feature: disclosure-note-linkage-and-slimdown, Property 2: cells_updated 精确计数`
    - _Requirements: 2.7_
  - [x]* 6.3 Property 3：stale 清除条件正确
    - **Property 3: stale 清除条件正确**
    - **Validates: Requirements 2.3, 2.5, 2.6**
    - 位置 `backend/tests/services/test_note_refill_pbt.py`；hypothesis `max_examples=5`
    - 标签注释 `# Feature: disclosure-note-linkage-and-slimdown, Property 3: stale 清除条件正确`
    - _Requirements: 2.3, 2.5, 2.6_
  - [x]* 6.4 Property 4（刷新侧）：manual 单元格重算路径不可覆盖
    - **Property 4: manual 单元格双路径不可覆盖（刷新路径分支）**
    - **Validates: Requirements 2.4, 3.6**
    - 位置 `backend/tests/services/test_note_manual_protect_pbt.py`；hypothesis `max_examples=5`
    - 标签注释 `# Feature: disclosure-note-linkage-and-slimdown, Property 4: manual 单元格双路径不可覆盖`
    - _Requirements: 2.4_

- [x] 7. 检查点 — 组① 零回归守护
  - 运行附注后端 66 测试全集（`backend/tests/services/test_note_*.py` + 报表/导出/离线相关），须全绿
  - 运行前端 vitest 附注相关（DisclosureEditor 刷新提示）须全绿
  - 改动导致既有测试失败 → 修代码不改断言（Req 1.5）
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 1.2, 1.5_

### 组② 缺口2 P1：cross_ref auto_pull 真实取数

- [x] 8. 新建 NoteAutoPullService（复用 note_source_resolvers 取数内核）
  - [x] 8.1 创建 service 骨架与数据类
    - 新建 `backend/app/services/note_auto_pull_service.py`
    - `@dataclass AutoPullResult`(ref_id/target_wp/source_label/value/available/reason)
    - `class NoteAutoPullService.__init__(self, db)`
    - _Requirements: 3.1, 3.3_
  - [x] 8.2 实现 target_field → binding 解析
    - `_resolve_binding(cross_ref) -> dict | None`：显式 `source_cell`（如 `B7`）→ `extract:"cell", cell_ref`；否则按 `target_wp` schema/表头将 `target_field`（如「审定数(期末)」）映射列定位 → `extract:"table"` 取列匹配行，或退化 `extract:"column_sum"`
    - 映射不到 → 返回 `None`（上层降级为占位 + 不可用，不报错）
    - 产出喂给 `resolve_wp_data` 的 binding dict（`{source:"wp_data", wp_code, sheet, extract, cell_ref/value_cols}`）
    - _Requirements: 3.1, 3.2, 3.4_
  - [x] 8.3 实现 pull_for_section 主流程（复用 dispatch_resolver + 降级）
    - `async def pull_for_section(self, project_id, year, schema, *, note_table_data=None) -> list[AutoPullResult]`
    - 预热 `_wp_cache`（一次加载项目底稿 parsed_data）
    - 对 `schema.cross_refs` 中 `auto_pull==true && direction=="inbound"` 的项逐条：manual_override 检查 → `_resolve_binding` → 复用 `note_source_resolvers.dispatch_resolver` / `resolve_wp_data` 取值
    - 成功 → 填 `value` + `source_label`（如 `D1-1!审定数(期末)`）+ `available=True`；失败 → `available=False` + `reason` 占位
    - **每个 ref 外层包 try**：单条异常被捕获为 `available=False`，绝不中断整体；拉到的值**不写入 table_data**（只读联动）
    - **不复用 custom_query._query_workpaper_cell_range**（避免 router→router 耦合与 LibreOffice 重负载进热路径）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.7, 3.10_
  - [x] 8.4 实现 manual_override 跳过判据
    - `@staticmethod _is_manual_override(note_table_data, ref) -> bool`：auto_pull 目标单元格 `_cell_modes[str(col)] != "auto"` → 跳过自动取数、保留用户手工值
    - _Requirements: 3.6_

- [x] 9. 新增 auto-pull 只读端点
  - 在 `backend/app/routers/disclosure_notes.py` 新增 `GET /{project_id}/{year}/{note_section}/auto-pull`
  - 加载该章节 schema（`wp_render_schema_service`）+ 该 note 的 `table_data`
  - 调 `NoteAutoPullService(db).pull_for_section(...)`，返回 `{"refs": [asdict(r) for r in results]}`
  - 只读查询，无需 commit；确认 router 已在 `router_registry` 注册（否则前端 404）
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 10. 前端 CrossRefDef 扩展 + 数据来源卡片展示拉到的值
  - [x] 10.1 扩展 CrossRefDef 类型
    - `GtCNoteTable.types.ts` 新增 `pulled_value?: number | string | null`、`source_label?: string`、`unavailable?: boolean`、`unavailable_reason?: string`
    - _Requirements: 3.3, 3.4_
  - [x] 10.2 GtCNoteTable 数据来源卡片渲染
    - 数据来源卡片区（`:191-211`）每个 `refItem` 展示 `pulled_value`（available）或「取数不可用：{reason}」（unavailable，灰色）
    - auto_pull 值标只读样式（区别于手填）；保留 `GtIndexChip` 跳转；jump-to-reference 行为不变
    - 文本中文 + GT 紫令牌
    - _Requirements: 3.3, 3.4, 3.8, 1.4_
  - [x] 10.3 新增 fetchNoteAutoPull（手动解信封）
    - `commonApi.ts` / `apiPaths/report.ts` 新增 `fetchNoteAutoPull(projectId, year, section)` → `GET .../auto-pull`
    - 原生 http 调用**手动解 `{code,message,data}` 信封**取 `body.data`（铁律）
    - 附注表加载时触发，把结果回填到 CrossRefDef 展示
    - _Requirements: 3.1, 3.4_

- [x]* 11. 编写组② 属性测试（auto_pull 侧 P5/P6/P7/P8 + P4 auto_pull 分支）
  - [x]* 11.1 Property 5：auto_pull 取数与来源值一致
    - **Property 5: auto_pull 取数与来源值一致**
    - **Validates: Requirements 3.1, 3.2, 3.9**
    - 位置 `backend/tests/services/test_note_auto_pull_pbt.py`；hypothesis `max_examples=5`
    - 标签注释 `# Feature: disclosure-note-linkage-and-slimdown, Property 5: auto_pull 取数与来源值一致`
    - _Requirements: 3.1, 3.2, 3.9_
  - [x]* 11.2 Property 6：auto_pull 值只读且可溯源
    - **Property 6: auto_pull 值只读且可溯源**
    - **Validates: Requirements 3.3**
    - 位置 `backend/tests/services/test_note_auto_pull_pbt.py`；hypothesis `max_examples=5`
    - 标签注释 `# Feature: disclosure-note-linkage-and-slimdown, Property 6: auto_pull 值只读且可溯源`
    - _Requirements: 3.3_
  - [x]* 11.3 Property 7：取数失败降级不阻断渲染
    - **Property 7: 取数失败降级不阻断渲染**
    - **Validates: Requirements 3.4, 3.10**
    - 位置 `backend/tests/services/test_note_auto_pull_pbt.py`；hypothesis `max_examples=5`
    - 标签注释 `# Feature: disclosure-note-linkage-and-slimdown, Property 7: 取数失败降级不阻断渲染`
    - _Requirements: 3.4, 3.10_
  - [x]* 11.4 Property 8：auto_pull 不污染手填持久化
    - **Property 8: auto_pull 不污染手填持久化**
    - **Validates: Requirements 3.7**
    - 位置 `backend/tests/services/test_note_auto_pull_pbt.py`；hypothesis `max_examples=5`
    - 标签注释 `# Feature: disclosure-note-linkage-and-slimdown, Property 8: auto_pull 不污染手填持久化`
    - _Requirements: 3.7_
  - [x]* 11.5 Property 4（auto_pull 侧）：manual 单元格取数路径不可覆盖
    - **Property 4: manual 单元格双路径不可覆盖（auto_pull 路径分支）**
    - **Validates: Requirements 2.4, 3.6**
    - 位置 `backend/tests/services/test_note_manual_protect_pbt.py`；hypothesis `max_examples=5`
    - 标签注释 `# Feature: disclosure-note-linkage-and-slimdown, Property 4: manual 单元格双路径不可覆盖`
    - _Requirements: 3.6_
  - [x]* 11.6 detect_changes 检测 auto_pull 受影响单元测试
    - 验证来源底稿单元格值变更后，`CrossRefService.detect_changes` 能检测到该 auto_pull 引用受影响
    - _Requirements: 3.5_

- [x] 12. 检查点 — 组② 零回归守护
  - 运行附注后端 66 测试全集，须全绿
  - 运行前端 vitest（GtCNoteTable / 数据来源卡片）须全绿
  - 改动导致既有测试失败 → 修代码不改断言（Req 1.5）
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 1.2, 1.5_

### 组③ 缺口3 P1：DisclosureEditor.vue 瘦身（纯重构，先测后拆）

- [x] 13. 先补特征测试锁定现有行为（拆前必做）
  - [x]* 13.1 编写 DisclosureEditor.characterization.spec.ts（Property 9 特征快照）
    - **Property 9: 瘦身行为与契约不变**
    - **Validates: Requirements 4.4, 4.9**
    - 位置 `audit-platform/frontend/src/views/__tests__/DisclosureEditor.characterization.spec.ts`
    - 覆盖既有交互：章节树加载、章节编辑、保存、校验、从底稿刷新、模板切换、Word 导出、公式管理、导入、EQCR 只读副本；断言对外路由路径/query(`year`)/事件契约不变
    - 前端 fast-check `numRuns: 100`（涉随机输入时）
    - 标签注释 `// Feature: disclosure-note-linkage-and-slimdown, Property 9: 瘦身行为与契约不变`
    - _Requirements: 4.2, 4.4, 4.6, 4.9_

- [x] 14. 按 composable 清单逐个抽取（每抽一个跑特征测试）
  - [x] 14.1 抽取 useNoteTree（章节树加载/拖拽排序/节点选中）
    - 搬 `fetchTree/onTreeNodeDrop/allowTreeDrop`（`:914,1018,1952`），只搬逻辑不改语义；抽完跑特征测试维持绿
    - _Requirements: 4.3, 4.4, 4.7_
  - [x] 14.2 抽取 useNoteDetail（章节详情加载/富文本 change）
    - 搬 `fetchDetail/onRichTextChange`（`:1112,1952`）；抽完跑特征测试
    - _Requirements: 4.3, 4.4, 4.7_
  - [x] 14.3 抽取 useNotePersist（保存/自动保存脏标记）
    - 搬 `onSave` + autoSave（`:2029`）；抽完跑特征测试
    - _Requirements: 4.3, 4.4, 4.7_
  - [x] 14.4 抽取 useNoteRefresh（从底稿刷新/手动重试/stale 重算 + 提示文案）
    - 搬 `onRefreshFromWP/onManualRefresh/onStaleRecalc`（`:1620,1645,1875`），含组① 的「已刷新 / 需手动重填」差异化提示；抽完跑特征测试
    - _Requirements: 4.3, 4.4, 4.7, 2.8, 2.9_
  - [x] 14.5 抽取 useNoteTemplate（模板切换/转换规则/模板配置）
    - 搬 `handleTemplateChange/loadNoteMappingPreset/saveNoteMappingRules/onNoteTemplateApplied`（`:927,964`）；抽完跑特征测试
    - _Requirements: 4.3, 4.4, 4.7_
  - [x] 14.6 抽取 useNoteExport（Word 导出/离线导入导出触发）
    - 搬 `onExportWord`（`:1884`）；抽完跑特征测试
    - _Requirements: 4.3, 4.4, 4.7_
  - [x] 14.7 抽取 useNoteAi（AI 续写/改写/知识库选取）
    - 搬 `onAiContinueWrite/onAiRewriteOpen/onPickKnowledge/getSelectedText`（`:1178,1201`）；抽完跑特征测试
    - _Requirements: 4.3, 4.4, 4.7_
  - [x]* 14.8 为抽出的 composable 写单元测试
    - 覆盖每个 composable 关键分支与边界；前端 fast-check `numRuns: 100`（涉随机时）
    - _Requirements: 4.6_

- [x] 15. 抽取子组件（SFC）
  - [x] 15.1 抽取 NoteEditorToolbar.vue（顶部工具栏按钮区）
    - 模板切换/刷新/生成/校验/导出/EQCR（模板 `:31-50`），通过 props/emit 与父通信，父保留编排；抽完跑特征测试
    - _Requirements: 4.3, 4.4, 4.7_
  - [x] 15.2 抽取 NoteMappingDialog.vue（转换规则弹窗）
    - 搬转换规则弹窗（`:923-952`），props/emit 通信；抽完跑特征测试
    - _Requirements: 4.3, 4.4, 4.7_

- [x] 16. HARD_CAPS 登记 + 类型检查
  - [x] 16.1 登记 check_file_size.py HARD_CAPS
    - 在 `backend/scripts/check/check_file_size.py` 的 `HARD_CAPS` 新增 `"audit-platform/frontend/src/views/DisclosureEditor.vue": 1500`
    - 确认 `DisclosureEditor.vue` 瘦身后实际行数 ≤ 1500，跑 `check_file_size.py` 通过
    - _Requirements: 4.1, 4.5_
  - [x] 16.2 vue-tsc 类型检查零错误
    - 对 `DisclosureEditor.vue` 及抽出的 composable / 子 SFC 跑 `npx vue-tsc --noEmit`，零错误
    - _Requirements: 4.8_

- [x] 17. 检查点 — 组③ 零回归守护
  - 特征测试 + composable / 子 SFC 单元测试全绿；`check_file_size.py` 通过；vue-tsc 零错误
  - 运行附注后端 66 测试全集，须全绿
  - 发现行为差异 → 修正抽取代码使其与原行为一致，而非修改特征测试断言（Req 4.7）
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 1.2, 4.1, 4.6, 4.7, 4.8_

### 收尾组：全量验证 + 在线实测

- [x] 18. 全量单测与属性测试守护
  - 运行附注后端 66 测试全集 + 本 spec 新增 `test_note_refill_pbt.py` / `test_note_manual_protect_pbt.py` / `test_note_auto_pull_pbt.py`，须全绿
  - 运行前端 vitest 附注相关全集（GtCNoteTable / DisclosureEditor / 抽出的 composable / 特征测试），须全绿
  - 任一失败 → 修代码不改断言（Req 1.5）
  - _Requirements: 1.2, 1.5, 1.6_

- [x] 19. Playwright 在线实测附注核心链路（9980 + 3030）
  - 环境就绪（后端 9980 + 前端 3030）时**必做**：实测「从底稿刷新」金额真变（非假性刷新）、auto_pull 数据来源卡片展示真实拉到的值、附注核心链路（173 章节生成/编辑/保存/校验/模板切换/Word 导出/EQCR 只读）无运行时回归
  - 离线时如实标注「代码已改未实测 + 外部依赖（在线环境）」，**不假绿**（仓库铁律）
  - _Requirements: 1.7, 1.1_

## 备注

- 标 `*` 的子任务为可选（属性测试、composable 单测、Playwright 在线 E2E）：默认仍应做完；`* 19` 受在线环境外部依赖，离线时用「代码已改未实测 + 外部依赖」措辞如实标注，严禁假绿。顶层任务与检查点不可标 `*`。
- 9 条 Correctness Properties 各对应一个属性测试子任务：P1/P2/P3 → `test_note_refill_pbt.py`；P4 → `test_note_manual_protect_pbt.py`（刷新侧 6.4 + auto_pull 侧 11.5 两路径分支）；P5/P6/P7/P8 → `test_note_auto_pull_pbt.py`；P9 → `DisclosureEditor.characterization.spec.ts`。后端属性测试 hypothesis `max_examples=5`，前端 fast-check `numRuns=100`。
- **零回归优先**：每组检查点（7 / 12 / 17）+ 收尾 18 均跑附注 66 后端测试全集守护；改动致既有测试失败一律修代码不改断言（Req 1.5 / 4.7）。
- **复用不新建**：P0 复用 `DisclosureEngine` 填充链（非 `NoteFillEngine`），auto_pull 复用 `note_source_resolvers.dispatch_resolver`（非 `custom_query`）；`disclosure_engine` / `note_source_resolvers` / `note_fill_engine` 作为被调用方不改。
- **口径铁律**：service 只 flush、router 统一 commit（Req 1.3）；前端原生 http 手动解 `{code,message,data}` 信封；manual 保护判据统一 `table_data.rows[]._cell_modes[str(col)] != "auto"`；auto_pull 值不写入 `table_data`（与手填可区分）；UI 中文 + GT 紫令牌（Req 1.4）；本 spec 不新增数据库表/列，预期不引入新 PG 专属 SQL（如有须标 `pg_only`，Req 1.6）。
- **测试环境**：SQLite in-memory 默认，优先 `httpx.ASGITransport(app=app)` in-process 直调端点避免 stale uvicorn。
- 本工作流仅产出设计与规划工件。要开始执行任务，打开 tasks.md，点击任务项旁的 "Start task"。
