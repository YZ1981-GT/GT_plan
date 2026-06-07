# Requirements Document

## Introduction

附注模块（disclosure notes）是致同审计平台最成熟的模块之一（49 个 note service + 22 个路由 + 66 个后端测试 + 47 个前端文件），已具备 173 章节生成、公式 DSL、Word 导出、离线分发、国企/上市互转等完整能力。本 spec 不新增功能，只集中修复代码实证勘察（2026-06-05）暴露的 3 处真实缺口：

- **缺口 1（P0，联动假性刷新）**：用户点「从底稿刷新」后，stale 红标被清除、提示「已刷新」，但附注表格里的金额仍是旧值——从未真正调用取数引擎重算。这是比指标占位更隐蔽的假性刷新（用户误以为已刷新），违反项目铁律「联动断裂是 P0」。
- **缺口 2（P1，cross_ref auto_pull 真拉值未接 query_workpaper）**：附注披露表的跨底稿引用字段目前只做 `{ref:BS-001}` 占位符→章节号文本替换，从未从底稿/报表真正拉取数值填进披露表格，跨底稿取数仍靠手填。
- **缺口 3（P1，DisclosureEditor.vue 2585 行超标瘦身）**：附注编辑器是全平台第二大 .vue（2585 行），远超仓库 1500 行卡点。需比照已落地的 `workpaper-editor-slimdown`「先测后拆」模式纯重构瘦身。

**最高约束：零功能回归。** 附注模块功能极完整，本 spec 的任何改动均不得破坏现有 173 章节生成、公式 DSL、Word 导出、离线分发、国企/上市互转、stale 联动、复核/EQCR 只读副本等任意能力。

### 勘察实证（写需求前已完成的现状确认）

| 文件 | 行数 | 实证结论 |
|------|------|----------|
| `backend/app/services/note_stale_service.py` | 254 | `refresh_stale_sections` 仅置 `is_stale=False`，注释自承认「实际数据刷新由 fill engine 负责」，但从未调用 `NoteFillEngine`。`refresh_from_workpaper` 同样只清标记不取数。 |
| `backend/app/services/note_wp_mapping_service.py` | — | 「从底稿刷新」按钮实际命中的 `refresh_from_workpapers` 在匹配到底稿后只 `# 简化：标记为已刷新` 自增计数器，不写回任何数值。 |
| `backend/app/services/note_fill_engine.py` | 272 | `NoteFillEngine` 已存在（4 种取数模式 + `fill_from_trial_balance` + 填充率统计），但 refresh 路径从未调用它。 |
| `backend/app/services/note_cross_reference_service.py` | 212 | 只有 `resolve_ref_placeholders`（占位符→章节号文本），无任何从底稿/报表拉数值的逻辑。 |
| `backend/app/services/cross_ref_service.py` | — | 已有 `detect_changes`（跨底稿引用变更检测）+ `propagate_with_manual_override_check`（manual_override 保护），可复用。 |
| `backend/app/routers/custom_query.py` | — | `_query_workpaper` / `_query_workpaper_cell_range` 已落地，是 auto_pull 真拉值的候选接入点（设计阶段确认）。 |
| `audit-platform/frontend/src/components/workpaper/GtCNoteTable.vue` | — | `autoPullRefs` computed 已筛 `auto_pull && direction==='inbound'` 的 cross_refs，jump-to-reference 跳转已接线，但显示的值是占位。 |
| `audit-platform/frontend/src/views/DisclosureEditor.vue` | 2585 | 全平台第二大 .vue，`onRefreshFromWP`/`onWorkpaperSaved`/`onManualRefresh` 均调 `refreshDisclosureFromWorkpapers`（即假性刷新端点）。 |
| `backend/scripts/check/check_file_size.py` | — | 已有 `HARD_CAPS` 防退化机制（GtDForm 三件已登记），瘦身后 DisclosureEditor.vue 须登记 hard cap。 |

## Glossary

- **附注模块（Disclosure_Note_Module）**：致同审计平台中生成、编辑、导出财务报表附注的子系统，核心入口为 `DisclosureEditor.vue` 与 `disclosure-notes` 系列路由。
- **NoteStaleService**：附注 stale 联动服务（`note_stale_service.py`），负责标记附注章节为 stale、刷新 stale 章节、查询 stale 状态。
- **NoteFillEngine**：附注数据填充引擎（`note_fill_engine.py`），提供合计/明细/分类/变动 4 种取数模式及从试算表取数能力。
- **NoteWpMappingService**：附注-底稿映射与提数服务（`note_wp_mapping_service.py`），「从底稿刷新」按钮实际命中的提数入口。
- **NoteCrossReferenceService**：附注交叉引用服务（`note_cross_reference_service.py`），负责占位符替换与报表行次→章节号映射。
- **CrossRefService**：跨底稿引用变更检测服务（`cross_ref_service.py`），提供 `detect_changes` 与 manual_override 保护。
- **stale 标记（Stale_Flag）**：附注章节的 `is_stale` 布尔字段，为 True 时前端显示红标，提示该章节上游数据已变更、需重新取数。
- **假性刷新（Phantom_Refresh）**：清除 stale 标记并提示「已刷新」，但未实际重算附注数值的反模式行为。
- **cross_ref（Cross_Reference）**：附注披露表中引用其他底稿/报表/试算表单元格的定义，schema 中含 `target_wp`、`direction`、`auto_pull` 等字段。
- **auto_pull（Auto_Pull）**：cross_ref 的一种行为标记，为 True 时表示该引用字段应在加载时自动从来源拉取当前值填充（只读联动）。
- **query_workpaper（Query_Workpaper_API）**：`custom_query.py` 中的底稿单元格查询能力（`_query_workpaper` / `_query_workpaper_cell_range`），按 wp_code/sheet/cell_range 返回底稿单元格值。
- **manual_override（Manual_Override）**：单元格被用户手工编辑后置位的保护标记，联动写入前须检查，不得覆盖用户手工值。
- **fill engine 重算（Refill）**：调用 NoteFillEngine 从试算表/底稿/报表重新取数并写回附注 table_data 的过程。
- **HARD_CAPS（Hard_Cap）**：`check_file_size.py` 中为已瘦身文件登记的显式行数上限，超限即 CI 失败，防止功能追加导致文件膨胀回弹。
- **特征测试（Characterization_Test）**：在重构前捕获现有行为快照的测试，用于守护重构「行为零变化」。
- **composable**：Vue 3 中以 `useXxx` 命名、封装可复用响应式逻辑的组合式函数。
- **零功能回归（Zero_Regression）**：本 spec 实施后，附注模块所有既有能力的可观察行为均保持不变。

## Requirements

### Requirement 1：零功能回归硬约束（最高优先级）

**User Story:** 作为审计平台的合伙人，我希望本次附注模块的修复不破坏任何现有能力，以便成熟模块的稳定性得到保障。

#### Acceptance Criteria

1. THE Disclosure_Note_Module SHALL 在本 spec 实施后保持 173 章节生成、公式 DSL 求值、Word 导出、离线分发（xlsx 4 色 + _meta_ + AES）、国企/上市模板互转、stale 联动、复核/EQCR 只读副本能力的可观察行为不变
2. THE 附注模块既有后端测试套件（66 个 note 测试）SHALL 在本 spec 实施后全部通过
3. WHEN 本 spec 修改任一附注后端 service，THE 修改 SHALL 保持 service 只 flush 不 commit、由 router 统一 commit 的事务边界约定
4. WHERE 本 spec 修改涉及前端用户可见文本，THE 文本 SHALL 使用中文，且 UI 颜色 SHALL 使用 GT 紫令牌而非 Element 默认蓝
5. IF 本 spec 的任一改动导致既有附注测试失败，THEN THE 实施 SHALL 修复改动而非修改测试断言以掩盖回归
6. THE 本 spec 新增的 PG 专属 SQL（如有）SHALL 标注 `pg_only` 标记，以便在 SQLite in-memory 测试环境下自动跳过
7. WHEN 本 spec 完成后，THE 实施 SHALL 在在线环境（后端 9980 + 前端 3030）用 Playwright 实测附注核心链路，验证无运行时回归

### Requirement 2：从底稿刷新真实重算（P0，修复假性刷新）

**User Story:** 作为审计助理，我希望点击「从底稿刷新」后附注金额真实更新为底稿最新值，以便我看到的红标消失等同于数据已真正刷新，而不是被误导。

#### Acceptance Criteria

1. WHEN 用户触发「从底稿刷新」操作，THE NoteStaleService SHALL 调用 NoteFillEngine 对受影响的附注章节重新取数并写回 table_data
2. WHEN 一个 stale 附注章节的上游底稿数值已变更，THE Refill SHALL 在刷新后将该章节自动取数单元格的值更新为底稿最新值
3. IF 某附注章节属于无法自动重算的纯文本/叙述性章节，THEN THE NoteStaleService SHALL 保留该章节为「需手动重填」状态而非清除其 stale 标记
4. WHERE 附注单元格被标记为 manual_override（手工模式），THE Refill SHALL 跳过该单元格、不覆盖用户手工值
5. WHEN Refill 成功更新某章节的自动取数单元格，THE NoteStaleService SHALL 仅对该章节清除 stale 标记
6. IF Refill 对某章节取数失败，THEN THE NoteStaleService SHALL 保留该章节的 stale 标记并在返回结果的 errors 中记录失败原因
7. THE NoteStaleService SHALL 在刷新结果中返回实际更新数值的单元格数量（cells_updated）
8. WHEN Refill 完成，THE 前端附注编辑器 SHALL 重新加载当前章节数据并向用户显示与实际重算结果一致的提示文案
9. IF 存在无法自动重算的纯文本章节，THEN THE 前端附注编辑器 SHALL 用区别于「已刷新」的文案提示用户哪些章节需手动重填
10. THE 单元测试 SHALL 验证「上游底稿数值变更后执行刷新，目标附注自动取数单元格的值确实从旧值变为新值」

### Requirement 3：cross_ref auto_pull 真实取数（P1，接 query_workpaper）

**User Story:** 作为审计助理，我希望附注披露表中标记为 auto_pull 的跨底稿引用字段能自动显示底稿/报表的当前真实值，以便我不必手工把底稿数字抄进附注披露表。

#### Acceptance Criteria

1. WHEN 附注披露表加载且其 schema 含 `auto_pull=true` 且 `direction=inbound` 的 cross_ref，THE Disclosure_Note_Module SHALL 通过 query_workpaper 从来源底稿拉取对应单元格的当前值填充该字段
2. WHERE cross_ref 来源为报表或试算表，THE Disclosure_Note_Module SHALL 从对应来源拉取当前值填充该字段
3. THE auto_pull 拉取的字段值 SHALL 为只读联动值，且 SHALL 携带可溯源的来源标识（来源底稿编码/报表行次/单元格引用）
4. IF auto_pull 取数失败，THEN THE Disclosure_Note_Module SHALL 在该字段显示占位符并标记为不可用，且 SHALL 继续渲染附注披露表其余部分而不阻断渲染
5. WHEN 来源底稿单元格值发生变更，THE CrossRefService.detect_changes SHALL 能检测到该 auto_pull 引用受影响
6. WHERE auto_pull 目标单元格被标记为 manual_override，THE Disclosure_Note_Module SHALL 跳过自动取数、保留用户手工值
7. THE auto_pull 拉取的值 SHALL 不污染附注的手工填写数据，即 auto_pull 字段与用户手填字段在持久化时可区分
8. WHEN 用户在前端点击 auto_pull 字段的来源跳转（jump-to-reference），THE 前端 SHALL 跳转到对应来源底稿
9. THE 单元测试 SHALL 验证「给定来源底稿单元格值，auto_pull 字段拉取到的值与来源值一致」
10. THE 单元测试 SHALL 验证「来源取数失败时，auto_pull 字段降级为占位+不可用标记，且附注披露表其余字段仍正常返回」

### Requirement 4：DisclosureEditor.vue 瘦身（P1，纯重构，先测后拆）

**User Story:** 作为平台维护者，我希望附注编辑器从 2585 行瘦身到仓库卡点以内，以便后续维护和审查成本下降，且重构过程行为零变化。

#### Acceptance Criteria

1. THE DisclosureEditor.vue SHALL 在瘦身后行数不超过 1500 行
2. WHEN 开始瘦身前，THE 实施 SHALL 先为 DisclosureEditor.vue 的现有行为补充特征测试，以守护重构期间行为不变
3. THE 瘦身 SHALL 通过抽取 composable（如 useNoteTree / useNoteEdit / useNotePersist / useNoteValidation）与子组件（SFC）实现，而非删除功能
4. THE 瘦身后的附注编辑器 SHALL 保持原有的章节树、章节编辑、保存、校验、从底稿刷新、模板切换、Word 导出、公式管理、导入、EQCR 只读副本等全部交互行为不变
5. WHEN 瘦身完成，THE check_file_size.py 的 HARD_CAPS SHALL 登记 DisclosureEditor.vue 的显式行数上限以防后续膨胀回弹
6. THE 瘦身前补充的特征测试与瘦身后抽出的 composable/子组件单元测试 SHALL 全部通过
7. IF 瘦身过程中发现行为差异，THEN THE 实施 SHALL 修正抽取代码使其与原行为一致，而非修改特征测试断言
8. WHEN 瘦身完成，THE vue-tsc 类型检查 SHALL 对 DisclosureEditor.vue 及抽出的文件零错误
9. THE 瘦身 SHALL 不改变 DisclosureEditor.vue 对外暴露的路由、props、事件契约
