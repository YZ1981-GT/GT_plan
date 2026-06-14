# 需求文档：出品物溯源与回填（deliverable-lineage-and-writeback）

## 简介

本功能打通审计全链路的**双向数据流**：让**附注出品物（附注 Word）**能够正向追溯其数据来源，并将出品物中人工撰写的文字说明安全地反向回填到上游附注模块。

> **范围界定（MVP）**：本期**仅覆盖附注出品物（disclosure_notes → 附注 docx）**。报告正文 Word（OPT 段落，无 section_code）与财务报表 Excel（单元格 `{{row:}}` 占位，非段落锚点）的溯源/回填**不在本期范围**，列为「未来扩展」（见附录 D）。原因：①附注已有 `##SECTION:section_code##` 块结构 + `section_code_index.json`，段落锚点天然可挂；②报表是 xlsx 单元格模型、报告正文是 OPT 段落模型，锚点机制完全不同，需独立设计。

数据链路（正向）：

```
调整分录 adjustments
    → recalc → 审定表 trial_balance (audited_amount)
    → 映射  → 财务报表 financial_report (row_code)
    → 取数  → 附注表格 disclosure_notes (table_data + text_content)
    → 生成  → 附注出品物 Word (deliverable)
    ↑━━━━━━━━━━━━━ 反向回填（仅文字说明）━━━━━━━━━━━━━┛
```

> **核心定位：扩展接入已有体系，而非重建。** 经 codegraph 实证（见本目录 `../audit-report-template-integration/LINEAGE-全链路溯源回填-现状分析.md`），约 80% 的溯源/联动/Stale/回填基础设施已经存在并在生产运行。本功能**唯一的真实空白是"出品物层尚未接入溯源体系"**。所有需求均以"接入/适配/扩展已有服务"为前提，**严禁新建第二套溯源总线、Stale 传播引擎或事件总线**（服务逻辑层勿重建）。
>
> **数据模型例外**：出品物层的章节级状态与源数据章节快照哈希在现有 schema 中无承载位置，**允许且需要新建数据结构**（新表 `deliverable_section_state` 或等价方案）。"勿重建"约束指**服务/引擎逻辑**，**不**禁止新增承载状态的表/列。
>
> **澄清 is_stale 真相（codegraph 实证，纠正早期误判）**：上游 `disclosure_notes.is_stale` **本就是章节级行存储**——`disclosure_notes` 每个 `note_section` 占单独一行（唯一约束 `project+year+note_section`），`is_stale` 是行级（即章节级）字段，存储粒度并不缺。真正的问题是 `event_handlers` 的更新逻辑粗暴：上游变更时按 `UPDATE ... WHERE project_id AND year` **一律全标**整年所有章节，丢失了"具体哪章变"的精度。**出品物层才真正没有任何章节状态承载**——因此新表 `deliverable_section_state` 的必要性在于"**出品物章节状态**"这一全新维度（出品物从未接入任何 stale/快照体系），而非"上游缺章节粒度"。
>
> **身份模型（codegraph 实证）**：程序中**没有 `deliverable_id` 概念**。出品物的真实模型 = `WordExportTask`（主键 `id` 即 `task_id`，承载一份导出任务）+ `WordExportTaskVersion`（`word_export_task_id` + `version_no` 组成版本链）。附注出品物 = 一个 `doc_type='disclosure_notes'` 的 `WordExportTask` 承载整份附注 docx。故本功能全程以 `word_export_task_id` 作为出品物标识，章节状态绑定在 **task 级**（跨版本稳定），重新生成新版本后既有章节 stale 状态延续到 task 维度，而非随 version 重置。

本功能覆盖三档优先级（用户已确认 MVP + 回填全做）：

- **P0**：出品物章节溯源面板（`deliverable` source_type 适配器接入 `LinkageFacadeService` + confirm 写段落锚点）+ 跨层跳转
- **P1**：出品物 Stale 感知（源数据 hash 快照 + 源变标记）+ 单章节增量刷新（不全量重生成）
- **P2**：OnlyOffice 文字回填 `disclosure_notes.text_content`（**用户显式按钮触发**，非自动保存触发）+ 回填合规护栏（仅文字 / 禁金额倒灌 / 冲突检测 / 留痕）

---

## 实施前置依赖（必须先满足）

> 本章节为硬约束。在以下前置条件全部满足前，**本功能不得开始编码实施**。

| 前置项 | 来源 spec / 任务 | 说明 | 当前状态 |
|--------|------------------|------|----------|
| **附注模板整理完成** | `audit-report-template-integration` task 0.6（含 0.6.2 附注四份 `##SECTION:` 全量打标） | 出品物段落锚点依赖附注模板的 `##SECTION:section_code##` 块结构与 `section_code_index.json`；模板未整理则锚点无处可挂 | 0.6.2 附注打标已完成；0.6.1 报告正文 17 份人工整理**未完成** |
| **附注 template 模式真正可用** | `audit-report-template-integration` task 10.2（`NoteWordExporter._export_template_mode`）+ 10.4（`render_disclosure_notes` 灰度切换 `mode=template`） | 段落锚点写入与单章节增量刷新都建立在 template 模式的章节块定位能力之上 | 机制已由合成 docx 测试证实正确，但 `USE_TEMPLATE_FILL_SERVICE` 仍默认 `false`（灰度未切，GT 模板缺 `{{section}}/{{table}}/{{seq}}` 填充占位符 + 残留【】指引，需先完成模板占位插入 + 人工 spot check task 18） |

1. THE 本功能 SHALL NOT 在 `audit-report-template-integration` 的 task 0.6（模板整理）完成前开始编码。
2. THE 本功能 SHALL NOT 在 `audit-report-template-integration` 的 task 10.2（附注 template 模式实现）与 task 10.4（灰度切换）真正可用前开始编码。
3. WHERE 附注 template 模式仍处于 `programmatic` 默认（`USE_TEMPLATE_FILL_SERVICE=false`），THE 出品物段落锚点写入需求（需求 2）SHALL 标注为"阻塞中"，待灰度开启后实施。

---

## 现有基础设施复用清单（Codegraph 实证，勿重建）

> 以下组件均已存在并在生产运行。本功能 SHALL 复用，SHALL NOT 重建。来源见现状分析文档第二节。

### 溯源 / 联动服务层（已存在）

| 组件 | 文件 | 已有能力 | 本功能如何复用 |
|------|------|----------|----------------|
| **LinkageFacadeService** | `linkage_facade_service.py` | 统一穿透入口 `trace(source_type, source_id)`，支持 `tb`/`workpaper`/`note`/`report` 四类源，返回 `LinkageContract` + conflict/stale 状态 | **扩展**：新增 `source_type='deliverable'` 适配器（需求 1） |
| **wp_trace_service** | `wp_trace_service.py` | `trace_upstream` / `trace_downstream` 双向溯源 | 出品物溯源面板上游展开复用 |
| **LinkageService** | 已有 | `get_workpapers_for_tb_row` / `get_adjustments_for_tb_row` | 溯源链路末端取数 |
| **WpNoteLinkageService** | 已有 | 底稿↔附注数据联动 `fetch_note_data` | 附注→底稿链路复用 |
| **ReportTraceService** | 已有 | 报表行穿透 | 报表层溯源复用 |
| **TraceEventService** | `trace_event_service.py` | 留痕 + `replay(trace_id, level)` L1/L2/L3 回放（含 before/after snapshot + content_hash） | **复用**：回填留痕（需求 9）|
| **DeliverableSnapshotService** | 已有 | doc 级 `tb_hash`（整张试算表 MD5）快照，绑 `WordExportTask.source_snapshot_refs`；**不覆盖 `text_content`、不区分章节** | **复用为廉价闸门**：stale 检测先用 doc 级 `tb_hash` 判"整份是否变"，变了才逐章节细化（需求 4）|
| **LinkageContract.route** | 已有 | 跨模块跳转路由字段 | **复用**：跨层跳转（需求 3）|

### 事件总线 + Stale 传播（已存在）

| 组件 | 文件 | 已有能力 | 本功能如何复用 |
|------|------|----------|----------------|
| **EventBus** | `event_bus.py` | debounce 事件总线 + Redis Stream 持久化 + SSE 推送前端 | **复用**：出品物 Stale 事件订阅/推送（需求 4）|
| **StalePropagationEngine** | `stale_propagation_engine.py` | 统一 stale 传播 `on_change(uri, project_id, year)`，URI 格式 `NOTE:code::` / `WP:code:sheet:` | **扩展**：新增 `DELIVERABLE:` URI 前缀（需求 4）；章节级状态落新表 Deliverable_Section_State（按 `word_export_task_id` 粒度）|
| **event_handlers** | `event_handlers.py` | 已订阅：调整分录变更→报表/附注 `is_stale`；`REPORTS_UPDATED`→附注增量更新；账套 rollback→下游 `is_stale`；`NOTE_SECTION_SAVED`→标引用底稿 | **接线**：新增 handler 在上游变更时标 deliverable stale（需求 4）|

### 反向回填先例（已存在，证明模式可行）

| 已有回填链路 | 文件 | 说明 |
|--------------|------|------|
| H9→H8 租赁两表反向回填 | `event_handlers.py` | ADR-H5 |
| I6↔I2 研发费用↔开发支出 | `event_handlers.py` | ADR-I4 |
| 底稿审计说明→工作簿回写 | `wp_explanation_service.py` | `_write_back_to_workbook` |
| structure.json→Excel 回写 | `wp_structure_bridge.py` | 三式联动 |

> 这些先例证明"反向回填"在本系统已是成熟模式。本功能的回填（需求 8）SHALL 参照同类实现，复用 TraceEventService 留痕。

### 前端溯源 UI（已存在）

| 组件 | 文件 | 已有能力 | 本功能如何复用 |
|------|------|----------|----------------|
| **CellTraceDialog** | `notes/CellTraceDialog.vue` | 附注单元格溯源弹窗（trial_balance/ledger/aux_balance 三 tab）| 出品物溯源面板布局参照/复用 |
| **GtTraceabilityDialog** | `workpaper/GtTraceabilityDialog.vue` | 底稿溯源 | 跨层跳转目标 |
| **TraceSourcePopover** | `common/TraceSourcePopover.vue` | TB 科目/报表行溯源气泡 | 复用 |
| **DrillDownNavigator** | `extension/DrillDownNavigator.vue` | 穿透导航 | 复用 |
| **ReportTracePanel** | `views/ReportTracePanel.vue` | 报表溯源面板 | 出品物溯源面板布局参照 |
| **useReportTrace / useLinkageTraceDrawer** | composables | 溯源抽屉状态 | 复用 |

### DisclosureNote 模型（已有关键字段）

- `is_stale`（过期标记，**本就是章节级行存储**——每个 `note_section` 占单独一行，`is_stale` 是行级字段；存储粒度并不缺，缺的是 handler 更新逻辑——现有 handler 按 `WHERE project+year` 一律全标，丢失"哪章变"精度。本功能出品物层的章节状态须新建 Deliverable_Section_State，不复用此字段——因为出品物层**从未有任何章节状态承载**，与上游 `is_stale` 是两个维度）
- `text_content`（文字内容，**回填目标**）
- `table_data`（表格数据，**回填禁区**）
- `note_section`（= `section_code` 主键，每章节一行，唯一约束 `project+year+note_section`）

---

## 术语表

- **Deliverable（出品物）**：写入 `storage/deliverables/{project_id}/{task_id}/` 的最终成品文件（附注 docx、报告正文 docx、财务报表 xlsx），由 `DeliverableService` 管理版本链。**真实模型** = `WordExportTask`（主键 `id` 即 `task_id`）+ `WordExportTaskVersion`（`word_export_task_id` + `version_no` 版本链）；程序中**无 `deliverable_id` 概念**，本功能全程以 `word_export_task_id` 为出品物标识
- **Word_Export_Task_Id（出品物标识）**：`WordExportTask.id`（= `task_id`），承载一份导出任务（附注出品物即一个 `doc_type='disclosure_notes'` 的 task）；其下挂多个 `WordExportTaskVersion`（`version_no` 递增）
- **DeliverableSnapshotService**：现有快照服务，对出品物计算 doc 级 `tb_hash`（整张试算表 MD5）并绑定 `WordExportTask.source_snapshot_refs`；**不覆盖 `text_content`、不区分章节**——本功能复用为"整份是否变"的廉价闸门
- **LinkageFacadeService**：现有统一溯源穿透入口；`trace(source_type, source_id)` 返回 `LinkageContract`
- **LinkageContract**：溯源契约对象，含数据来源、编辑状态、跨模块跳转 `route` 字段
- **Source_Type（源类型）**：`LinkageFacadeService` 支持的源类别。现有 `tb`/`workpaper`/`note`/`report`；本功能新增 `deliverable`
- **Section_Code（章节编码）**：附注章节主键，等于种子 `section_number`（国企如 `八、1`、上市如 `五、1`），等于 `disclosure_notes.note_section`
- **Section_Anchor（段落锚点）**：写入出品物 docx 的隐藏定位标记（隐藏书签 `w:bookmarkStart name="sec_八_1"` 或自定义 docProperty），建立 docx 段落 ↔ `section_code` 的映射；锚点形式在设计阶段经 POC 实测后确定
- **Lineage_Panel（溯源面板）**：出品物编辑界面左侧的引用面板，展示当前章节的数据来源 + 编辑状态 + 跨层跳转入口
- **Stale（过期）**：上游数据已变更，导致出品物内容不再与最新数据一致的状态。注意：上游 `disclosure_notes.is_stale` **本就是章节级行存储**（每 `note_section` 一行），但现有 handler 按 `project+year` 一律全标；本功能要解决的是**出品物层从未有章节状态承载**这一全新维度，故引入新存储（见 Deliverable_Section_State）
- **Deliverable_Section_State（出品物章节状态）**：新建数据结构，按 `(word_export_task_id, section_code)` 粒度存储章节级 stale 标记 + Source_Snapshot_Hash + 最近回填基线，承载出品物层此前完全缺失的"出品物章节状态"维度。**绑 task 级**（跨版本稳定）——重新生成新版本后既有章节状态延续到 task 维度，非 version 级
- **Source_Snapshot_Hash（源数据快照哈希）**：出品物某版本生成时，其每个章节所依赖的上游数据（`text_content` + `table_data` + 相关 `audited_amount`）的内容哈希；用于检测源变。是在现有 doc 级 `tb_hash`（DeliverableSnapshotService）口径上**扩展到章节 + 文字粒度**（`tb_hash` 不含 `text_content`），与 `tb_hash` 分层配合而非平行新建快照体系
- **Incremental_Refresh（单章节增量刷新）**：仅重新生成出品物中某一章节，而非全量重生成整份文档
- **Writeback（回填）**：将出品物中人工编辑的文字说明反向写回 `disclosure_notes.text_content`
- **Text_Content（文字说明）**：附注章节中人工撰写的叙述性文字（`disclosure_notes.text_content`），是**唯一允许回填的叶子内容**
- **OnlyOffice_Callback**：OnlyOffice 文档编辑保存后向后端发出的回调（仅提供"文件已保存"信号 + 下载 URL，**不提供段落级 diff**）
- **TraceEventService**：现有留痕服务，`replay(trace_id, level)` 支持 L1/L2/L3 回放（含 before/after snapshot + content_hash）
- **Writeback_Conflict（回填冲突）**：回填发生时，目标 `text_content` 在出品物生成之后又被上游（附注编辑器）独立修改过的状态

---

## 范围与优先级

| 优先级 | 范围 | 关键依赖 |
|--------|------|----------|
| **P0** | 出品物章节溯源面板（`deliverable` source_type 适配器 + confirm 写段落锚点）| confirm 写锚点（需求 2）|
| **P0** | 溯源面板跨层跳转（复用 `LinkageContract.route`，前端接入）| P0 溯源面板 |
| **P1** | 出品物章节级 Stale 感知（先用 doc 级 `tb_hash` 廉价闸门判整份变没变，再用新表 Deliverable_Section_State 存章节级 hash + 源变标记）| StalePropagationEngine 语义复用 + DeliverableSnapshotService 复用 + 新状态表 |
| **P1** | 单/批量章节增量刷新（不全量重生成）| 附注 template 模式（前置依赖 task 10.2）|
| **P2** | OnlyOffice 文字回填 `disclosure_notes.text_content`（显式按钮触发）| 段落锚点（需求 2）+ docx diff |
| **P2** | 回填合规护栏（仅文字 / 禁金额 / 冲突检测 / 留痕）| P2 回填管道 |

---

## 需求

### 需求 1：deliverable 接入 LinkageFacade（P0 基础）

**用户故事：** 作为审计项目经理，我希望出品物成为溯源体系的一类数据源，以便像底稿/报表/附注一样穿透追溯其数据来源。

#### 验收标准

1. THE `LinkageFacadeService` SHALL 新增 `source_type='deliverable'` 分支，扩展现有 `trace(source_type, source_id)` 入口，不新建并行溯源服务。
2. WHEN 调用 `trace(source_type='deliverable', source_id)` 时，THE `LinkageFacadeService` SHALL 将 `source_id`（出品物 + `section_code`）映射到对应的 `disclosure_notes` 记录，并返回包含数据来源与编辑状态的 `LinkageContract`。
3. THE deliverable 适配器 SHALL 沿用现有 `LinkageContract` 数据结构，包含 `route` 字段以支持跨层跳转（需求 3），不新增并行契约类型。
4. WHEN 出品物章节对应的 `section_code` 在 `disclosure_notes` 中不存在时，THE `LinkageFacadeService` SHALL 返回明确的"无匹配来源"结果，并记录该 `section_code` 供排查。
5. THE deliverable 溯源 SHALL 复用现有 `wp_trace_service.trace_upstream`，使出品物章节可继续向上游（附注→报表→审定表→调整分录）展开溯源链。
6. THE deliverable 适配器 SHALL 仅作为读取入口，SHALL NOT 在溯源过程中修改任何 `disclosure_notes` 数据。

### 需求 2：出品物段落锚点（P0 基础，依赖前置 task 10.2/10.4）

**用户故事：** 作为审计项目经理，我希望生成的出品物 Word 中每个章节都带有稳定的定位标记，以便溯源面板和回填管道能准确定位到对应的 `section_code`。

#### 验收标准

1. WHEN confirm（确认生成）出品物时，THE 系统 SHALL 为每个保留的章节写入 Section_Anchor，建立 docx 段落 ↔ `section_code` 的映射，而非清除 `##SECTION:` 标记后不留锚点。
2. THE Section_Anchor 形式（隐藏书签 vs 自定义 docProperty）SHALL 在设计阶段经 POC 实测确定，POC SHALL 验证 OnlyOffice 与 python-docx 双方均能读取并据此定位段落。
3. WHILE 用户在 OnlyOffice 中编辑出品物时，THE Section_Anchor SHALL 保持隐藏，不影响出品物的可见正文与对外格式。
4. THE 现有 `remove_section_markers`（清除 `##SECTION:` 可见标记）SHALL 保留对可见标记的清理行为，同时改为在清理前写入隐藏 Section_Anchor，保证成品既无可见标记又有隐藏锚点。
5. WHEN 一个章节被裁剪删除（不导出）时，THE 系统 SHALL NOT 为该章节写入 Section_Anchor。
6. THE Section_Anchor 命名 SHALL 由 `section_code` 唯一派生（如 `八、1` → `sec_八_1`），保证同一 `section_code` 在锚点名与 `disclosure_notes.note_section` 之间可双向映射。
7. WHERE 附注 template 模式（前置依赖 task 10.2）尚未灰度开启，THE 段落锚点写入 SHALL 标注为"阻塞中"，待 `USE_TEMPLATE_FILL_SERVICE=true` 后实施。

### 需求 3：溯源面板与跨层跳转（P0）

**用户故事：** 作为审计项目经理，我希望点击出品物中的某个章节时，左侧引用面板显示该章节的数据来源和编辑状态，并能一键跳转到上游模块（附注编辑器/报表/审定表/调整分录）。

#### 验收标准

1. WHEN 用户在出品物编辑界面选中或点击某章节时，THE Lineage_Panel SHALL 通过 Section_Anchor 解析出 `section_code`，调用 `LinkageFacadeService.trace(source_type='deliverable', ...)` 并展示返回的数据来源清单。
2. THE Lineage_Panel SHALL 展示每个来源的：来源类型（附注/报表/审定表/调整分录）、来源标识、当前编辑状态（含 stale 标记）。
3. WHEN 用户点击某个上游来源的跳转入口时，THE 系统 SHALL 使用 `LinkageContract.route` 字段导航到对应上游模块，不新建跳转路由逻辑。
4. THE Lineage_Panel SHALL 复用现有溯源 UI 组件（参照 `CellTraceDialog` / `ReportTracePanel` / `useLinkageTraceDrawer`），SHALL NOT 新建并行溯源面板体系。
5. IF 某章节无可解析的 Section_Anchor（如旧版本出品物在锚点功能上线前生成），THEN THE Lineage_Panel SHALL 显示"该出品物版本不支持溯源，请重新生成"的提示，而非报错。
6. THE Lineage_Panel 中所有用户可见文本 SHALL 为中文（技术术语如 SQL/UUID/API 保留英文）。

### 需求 4：出品物 Stale 感知（P1）

**用户故事：** 作为审计项目经理，我希望当上游数据（调整分录/审定表/报表/附注）变更后，出品物侧能标记为"已过期"，提醒我需要刷新。

#### 验收标准

1. WHEN confirm 生成出品物某版本时，THE 系统 SHALL 复用 `DeliverableSnapshotService` 记录 doc 级 `tb_hash`（整张试算表 MD5，作为"整份是否变"的廉价闸门），并为每个章节计算并存储章节级 Source_Snapshot_Hash（在 `tb_hash` 口径上细化到 `section_code`，覆盖该章节依赖的 `text_content`、`table_data` 及相关 `audited_amount`）。
2. WHEN 检测出品物是否过期时，THE 系统 SHALL **分层检测**：先比对 doc 级 `tb_hash` 判断整份是否变化（复用 `DeliverableSnapshotService`，廉价闸门）；仅当 `tb_hash` 变化时，THE 系统 SHALL 再逐章节计算章节级 hash 以定位具体哪些章节变更，SHALL NOT 在 `tb_hash` 未变时逐章节计算。
3. THE `StalePropagationEngine` SHALL 扩展支持 `DELIVERABLE:` URI 前缀（如 `DELIVERABLE:{word_export_task_id}:{section_code}:`），复用现有 `on_change(uri, project_id, year)` 传播机制，不新建并行传播引擎。
4. WHEN 上游 `disclosure_notes`、`financial_report` 或 `adjustments` 发生变更并触发现有级联事件时，THE event_handlers SHALL 新增订阅逻辑，将受影响出品物章节标记为 stale。
5. THE 出品物章节级 stale 标记 SHALL 存储于新建的 `Deliverable_Section_State`（按 `word_export_task_id + section_code` 粒度，绑 task 级跨版本稳定），SHALL NOT 误用 `disclosure_notes.is_stale`；其原因不是"上游缺章节粒度"（上游 `is_stale` 本就是章节级行存储），而是**出品物层此前完全没有任何章节状态承载**，此为全新维度；stale 的**语义与传播机制**复用现有体系，但**承载存储**为新结构。
6. WHEN 出品物某章节被标记 stale 时，THE Lineage_Panel SHALL 在该章节显示"源数据已变更"提示。
7. WHEN 用户触发"一键刷新"时，THE 系统 SHALL 重新生成出品物（走 confirm 流程，version_no +1），刷新后 SHALL 清除相应 stale 标记并更新 doc 级 `tb_hash` 与章节级 Source_Snapshot_Hash。
8. THE 出品物 stale 状态变更 SHALL 通过现有 `EventBus` + SSE 推送前端，SHALL NOT 新建并行推送通道。
9. WHEN stale 由**本出品物自身回填**（需求 7）触发的 `NOTE_SECTION_SAVED` 引起时，THE 系统 SHALL NOT 将**该回填来源出品物**自身标记为 stale（区分"自己回填导致的上游变更"与"他人独立修改"），避免回填后立即出现"已过期"的体验循环。

### 需求 5：单章节增量刷新（P1，依赖前置 task 10.2）

**用户故事：** 作为审计项目经理，我希望只刷新出品物中过期的单个章节，而不是全量重新生成整份文档，以便保留我在其他章节已做的人工编辑。

#### 验收标准

1. WHEN 用户对某个 stale 章节触发"刷新本章节"时，THE 系统 SHALL 仅重新生成该章节内容，复用附注 template 模式的章节块定位能力（`scan_section_blocks` / `delete_section_block`），SHALL NOT 全量重生成整份文档。
2. THE 单章节增量刷新 SHALL 通过 Section_Anchor 定位目标章节块，用最新 `disclosure_notes` 内容替换该块。
3. WHEN 增量刷新某章节后，THE 系统 SHALL 仅更新该章节的 Source_Snapshot_Hash 与 stale 标记，不影响其他章节的状态。
4. THE 单章节增量刷新 SHALL 创建新的出品物版本（version_no +1），保留旧版本可回溯，复用现有 `DeliverableService` 版本链。
5. IF 增量刷新会覆盖用户在该章节已做的人工编辑，THEN THE 系统 SHALL 在执行前提示"刷新将覆盖本章节当前编辑内容"，需用户确认。
6. WHERE 附注 template 模式（前置依赖 task 10.2）尚未灰度开启，THE 单章节增量刷新 SHALL 标注为"阻塞中"，待灰度开启后实施。
7. WHEN 用户触发"刷新所有过期章节"时，THE 系统 SHALL 批量增量刷新当前出品物中所有 stale 章节（逐章节复用 5.1 能力），保留未过期且已人工编辑的章节不动，并对会覆盖人工编辑的章节按 5.5 统一提示确认。

### 需求 6：回填合规约束（P2，审计数据链可信度底线）

> 本需求为**审计合规底线**，是回填功能的强约束。任何回填实现 SHALL 100% 满足以下约束，违反即破坏审计数据链可信度。

**用户故事：** 作为审计质控（EQCR），我要求回填严格限定在人工撰写的文字说明范围内，任何金额或表格数字都不得从出品物倒灌，以保证审定数据始终源自调整分录→审定表→报表→附注的正向数据链。

#### 验收标准

1. THE 回填 SHALL 仅允许写回 `disclosure_notes.text_content`（人工撰写的文字说明叶子内容）。
2. THE 回填 SHALL NOT 写回 `disclosure_notes.table_data` 或任何金额/表格数字字段（**金额禁止从出品物倒灌**）。
3. IF 检测到出品物中的表格数字相对生成时发生变更，THEN THE 系统 SHALL 拒绝回填该变更，并提示"金额变更须通过调整分录（AJE/RJE）修正，不可从出品物回填"。
4. THE 章节标题 SHALL NOT 被回填覆盖（标题由 `section_code` + `{{seq:}}` 生成，回填会破坏编号）；WHERE 检测到标题文字变更，THE 系统 SHALL 忽略该变更并记录。
5. THE 回填管道 SHALL 在写回前对每个变更项做字段分类（文字说明 / 表格数字 / 标题），仅放行文字说明类变更。
6. WHEN 用户尝试回填被禁止的内容（金额/表格/标题）时，THE 系统 SHALL 给出明确的中文拒绝说明，指引用户走正确的上游修改路径（调整分录）。
7. THE 回填合规约束 SHALL 有自动化测试覆盖，验证金额/表格/标题变更被拒绝、仅文字变更被放行。

### 需求 7：OnlyOffice 文字回填管道（P2）

**用户故事：** 作为审计项目经理，我希望在 OnlyOffice 中编辑出品物章节的文字说明后，**通过点击"回填到附注模块"按钮**主动将这些文字回写到附注模块，避免在两处重复维护，同时避免自动保存频繁触发回写。

#### 验收标准

1. THE 回填 SHALL 由用户在出品物界面**显式点击"回填到附注模块"按钮**触发，SHALL NOT 在 OnlyOffice 每次自动保存（含编辑中途保存）时自动触发回填。
2. WHEN OnlyOffice 文档保存时，THE 系统 SHALL 继续走现有 `onlyoffice_callback_service` 仅完成文件存储/版本，SHALL NOT 因保存而自动回填。
3. WHEN 用户点击回填按钮时，THE 系统 SHALL 下载最新已保存的 docx，通过 Section_Anchor 定位每个章节块并提取其文字内容，与 DB 中 `disclosure_notes.text_content` 比对，仅识别变更的章节。
4. THE 回填 SHALL 处理 OnlyOffice 不提供段落级 diff 的限制，通过"下载 docx → 按 Section_Anchor 分块 → 文本比对"自行计算章节级 diff。
5. THE 回填 SHALL 经过需求 6 的合规护栏分类后，仅将文字说明变更写回 `disclosure_notes.text_content`。
6. WHEN 回填成功写回某章节 `text_content` 时，THE 系统 SHALL 触发现有 `NOTE_SECTION_SAVED` 等级联事件，使下游正常感知变更；同时按需求 4.9 标记该变更来源以避免自标 stale。
7. THE 回填 SHALL 复用 `TraceEventService` 记录留痕（before/after snapshot + content_hash），SHALL NOT 新建并行留痕机制。
8. IF 回填过程中 docx 下载或解析失败，THEN THE 系统 SHALL 中止本次回填、保留 `disclosure_notes` 原值不变，并记录失败原因。
9. IF 某章节的 Section_Anchor 在 OnlyOffice 编辑中被用户误删或破坏（无法定位），THEN THE 系统 SHALL 跳过该章节回填并在结果中明确列出"无法定位、未回填"的章节，不影响其他章节正常回填。

### 需求 8：回填冲突检测（P2）

**用户故事：** 作为审计项目经理，我希望当出品物中编辑的章节在上游附注也被同时修改过时，系统能检测到冲突而不是盲目覆盖，以免丢失他人的修改。

#### 验收标准

1. WHEN 执行回填时，THE 系统 SHALL 检测目标 `disclosure_notes.text_content` 在出品物生成之后是否被上游独立修改过（基于 Source_Snapshot_Hash 与当前 DB 内容比对）。
2. IF 检测到 Writeback_Conflict（上游也已变更），THEN THE 系统 SHALL 暂停自动回填该章节，并向用户呈现冲突三方内容：出品物侧编辑值、上游当前值、生成时基线值。
3. WHEN 存在 Writeback_Conflict 时，THE 系统 SHALL 由用户显式选择保留哪一方，SHALL NOT 默认静默覆盖。
4. THE 冲突检测 SHALL 复用 `LinkageFacadeService` 已有的 conflict/stale 状态能力，SHALL NOT 新建并行冲突判定逻辑。
5. THE 冲突的检测、用户裁决与最终写回 SHALL 通过 `TraceEventService` 完整留痕。
6. WHEN 用户裁决并完成写回后，THE 系统 SHALL 更新该章节 Source_Snapshot_Hash 以反映最新基线。

### 需求 9：回填留痕（P2，复用 TraceEventService）

**用户故事：** 作为审计质控（EQCR），我要求每一次回填操作都有完整可回放的留痕，以满足审计轨迹要求。

#### 验收标准

1. THE 每次回填操作 SHALL 通过 `TraceEventService` 记录一条留痕事件，复用现有 L1/L2/L3 回放能力，SHALL NOT 新建并行留痕表/服务。
2. THE 回填留痕 SHALL 包含：操作人、时间、出品物标识与版本、目标 `section_code`、before/after `text_content` snapshot 及 content_hash。
3. WHEN 回填因合规护栏（需求 6）拒绝某项变更时，THE 系统 SHALL 同样留痕被拒绝的变更及拒绝原因。
4. THE 回填留痕 SHALL 可通过 `TraceEventService.replay(trace_id, level)` 回放，与现有溯源留痕使用同一回放入口。

### 需求 10：非功能需求

**用户故事：** 作为系统运维，我希望溯源与回填功能稳定、可留痕、受权限控制，不影响主链路性能。

#### 验收标准

1. THE 出品物溯源面板单章节 `trace` 查询 SHALL 在 2 秒内返回；超时 SHALL 返回明确错误而非无限等待。
2. WHEN 回填或全量刷新涉及大型出品物（章节数 > 100）时，THE 操作 SHALL 通过现有 `export_jobs_v2` 异步执行并返回 job_id + 进度，SHALL NOT 阻塞主 API。
3. THE 回填写回 `disclosure_notes` SHALL 受现有项目权限控制（至少 `project:write` 或等同附注编辑权限）；无权限用户 SHALL 仅能查看溯源面板（`project:read`），不能触发回填。
4. THE 所有回填与刷新操作 SHALL 写入应用审计日志（`app_audit_log`）及 `TraceEventService` 留痕。
5. THE Source_Snapshot_Hash 计算 SHALL 使用稳定的内容哈希算法，对相同输入产生相同哈希（确定性），以保证 stale 检测无误报。
6. THE 出品物溯源/回填功能 SHALL NOT 修改现有 `tb`/`workpaper`/`note`/`report` 四类源的溯源行为，保证向后兼容。

### 需求 11：终态出品物禁止回填/刷新（P2，合规边界）

> 本需求为**审计合规边界**。签字/确认/归档后的附注出品物是审计定稿，不应再被自动改写。如需修改须走正式的撤回/解锁流程。

**用户故事：** 作为审计质控（EQCR），我要求当附注出品物已进入签字/确认/归档终态后，系统禁止任何回填与刷新，以保证审计定稿不被自动改写，维持审计轨迹的不可篡改性。

#### 验收标准

1. WHEN 出品物处于 `signed`、`confirmed` 或 `archived` 终态时，THE 系统 SHALL 禁止回填（需求 7）与单/批量章节刷新（需求 5），并返回明确的中文拒绝说明（如"该出品物已签字/确认/归档，不可回填或刷新；如需修改请走撤回/解锁流程"）。
2. THE 终态禁止逻辑 SHALL 与现有 `DeliverableService.create_version` 的归档锁行为一致（`archived` 态禁止新建版本），复用同一终态判定，SHALL NOT 新建并行状态机。
3. WHEN 用户对终态出品物触发"一键刷新"或"刷新本章节"时，THE 系统 SHALL 在执行前拦截并提示终态约束，SHALL NOT 创建新版本。
4. WHILE 出品物处于终态时，THE Lineage_Panel SHALL 仍允许查看溯源（只读），SHALL 禁用回填与刷新入口。

---

## 附录 A：服务职责对照（实施后目标态）

| 服务 / 组件 | 现状 | 本功能改动 |
|-------------|------|------------|
| `LinkageFacadeService` | 支持 tb/workpaper/note/report | **扩展** `deliverable` source_type 适配器 |
| `StalePropagationEngine` | URI `NOTE:` / `WP:` | **扩展** `DELIVERABLE:` URI 前缀（`word_export_task_id` 粒度）|
| `event_handlers` | 上游变更级联 note/report stale | **新增** handler 标 deliverable stale |
| `TemplateFillService` / `NoteWordExporter` | confirm 清除 `##SECTION:` 可见标记 | **扩展** confirm 时写隐藏 Section_Anchor |
| `onlyoffice_callback_service` | 保存回调 | **接入** 回填触发（下载 docx → 分块 diff）|
| `DeliverableSnapshotService` | doc 级 `tb_hash` 快照绑 `WordExportTask.source_snapshot_refs` | **复用为廉价闸门**：分层 stale 检测先判 doc 级 `tb_hash`（需求 4）|
| `TraceEventService` | L1/L2/L3 回放留痕 | **复用** 回填/冲突留痕 |
| `DeliverableService` | 版本链/存储/OnlyOffice/哈希 | **复用**（不变），承载刷新版本递增 |
| **Deliverable_Section_State（新建）** | 无 | **新建**：章节级 stale + 章节级 Source_Snapshot_Hash + 回填基线（`word_export_task_id + section_code` 粒度，绑 task 级）；**表结构设计成可扩展到报表/报告正文**（字段不绑死附注 doc_type），本期只接附注 |
| 前端溯源 UI（CellTraceDialog 等）| 附注/报表/底稿溯源 | **复用/参照** 出品物 Lineage_Panel |

## 附录 B：回填边界速查（合规底线）

| 出品物中改动的内容 | 能否回填 | 原因 |
|--------------------|----------|------|
| 章节说明文字（`text_content`）| ✅ 可回填 | 文字是人工撰写的叶子内容，附注模块是其归属 |
| 表格数字（`table_data`）| ❌ 严禁回填 | 数字来自审定数→报表，改数字必须走调整分录（AJE/RJE）|
| 章节标题 | ⚠️ 忽略（不回填）| 标题由 `section_code` + `{{seq:}}` 生成，回填会破坏编号 |

**核心原则**：回填只允许"文字说明"这种叶子内容，计算派生数据（金额）严禁反向倒灌——否则破坏审计数据链可信度。

## 附录 C：优先级与依赖

| 优先级 | 内容 | 关键依赖 |
|--------|------|----------|
| P0 | 需求 1（deliverable source_type）+ 需求 2（段落锚点）+ 需求 3（溯源面板+跳转）| 前置 task 10.2/10.4 灰度开启 |
| P1 | 需求 4（章节级 Stale 感知，doc 级 `tb_hash` 闸门 + 新表 Deliverable_Section_State）+ 需求 5（单/批量章节增量刷新）| StalePropagationEngine 语义复用 + DeliverableSnapshotService 复用 + 新建状态表；需求 5 依赖 template 模式 |
| P2 | 需求 6（合规护栏）+ 需求 7（OnlyOffice 显式按钮回填）+ 需求 8（冲突检测）+ 需求 9（留痕）+ 需求 11（终态禁止回填/刷新）| 段落锚点（需求 2）|

## 附录 D：未来扩展（不在本期 MVP 范围）

| 扩展项 | 为何本期不做 | 未来设计要点 |
|--------|--------------|--------------|
| **报告正文 Word 溯源/回填** | 报告正文是 OPT 段落模型，无 `section_code`；其"源"是 OPT 勾选 + 占位符数据，与附注章节模型不同 | 需为 OPT 段落设计独立锚点 + OPT 选择变更纳入"源变"判定 |
| **财务报表 Excel 溯源/回填** | 报表是 xlsx 单元格 `{{row:CODE}}` 模型，非段落锚点；已有 cell_mapping 可作正向溯源基础，但回填涉及单元格级 diff | 复用 cell_mapping 做正向溯源（单元格→row_code→TB）；回填同样受"金额禁倒灌"约束（报表数字几乎全是派生，回填空间极小） |
| **报表/报告正文章节级 stale** | 同上锚点模型差异 | 待附注链路验证成熟后再推广 Deliverable_Section_State 模型 |

> 本期完成附注链路并验证"段落锚点 + 章节级 stale + 显式回填"三件套可行后，报表/报告正文可在同一架构下增量扩展。
>
> **前瞻性口子（一劳永逸）**：新表 `deliverable_section_state` 的字段设计**不绑死附注 doc_type**，以 `word_export_task_id + section_code` 为通用主键。本期只接 `doc_type='disclosure_notes'`，未来报表/报告正文出品物可复用**同一张表 + 同一套溯源/回填/stale 机制**，无需另起炉灶。
