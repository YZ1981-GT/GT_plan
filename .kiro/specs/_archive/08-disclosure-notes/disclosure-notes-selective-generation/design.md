# Design Document

## Overview

本设计在「交付件管理中心」(`DeliverableCenter.vue`) 的「生成附注」入口与后端交付渲染接口之间插入一个**附注选择对话框**，让审计师在生成交付 docx 前按附注模块实时树形勾选要生成的章节，并提供「一键预设生成」（默认只勾有数据的科目章节）。

核心判断：**导出能力已完备，本功能只做三件事**——

1. 后端 `DisclosureEngine.get_notes_tree` 为每个章节节点**新增 `has_data` 字段**（唯一后端缺口），判定口径与 `NoteWordExporter._has_content` 同源（抽共享 helper 防漂移）。
2. 前端新建 `DisclosureNotesSelectionDialog.vue`，拉实时树 → `el-tree` `show-checkbox` 分组展示 → 收集最终勾选集。
3. `DeliverableCenter.vue` 的 `goGenerateNotes` 从「直接调渲染接口」改为「打开对话框」，确认回调携 `selected_sections` 调用**已支持该参数**的 `renderDisclosureNotes`。

**不触碰**：导出逻辑、`template_type` 解析（后端从 `Project.template_type` 权威决定）、`skip_empty` 语义、章节前缀（「三、」/「四、」由后端按变体返回）。

## Architecture

### 数据流

```
用户点击「生成附注」(DeliverableGroupList → @generate-notes)
        │
        ▼
DeliverableCenter.goGenerateNotes()
        │  guardGenerate('notes') 权限门控（不变）
        ▼
打开 DisclosureNotesSelectionDialog（visible=true, projectId, year）
        │
        ▼
onMounted/onOpen → GET /api/disclosure-notes/{pid}/{year}   （附注树服务，节点含 has_data）
        │
        ├─ 加载中：显示 loading，禁用「确认生成」
        ├─ 404：提示「附注数据不存在，请先生成附注」，禁用「确认生成」
        ├─ 其他错误/超时：显示失败 + 「重试」
        ▼
按顶层中文序号分组构建 el-tree（show-checkbox），has_data=false 节点置灰但不禁用
        │
        ├─ 「一键预设生成」→ setCheckedKeys(has_data=true 的叶子)
        ├─ 手动勾选/取消 → 实时更新勾选计数（预设不锁定，可叠加二次修正）
        ▼
「确认生成」（空选禁用）→ emit('confirm', { selectedSections })
        │
        ▼
DeliverableCenter → renderDisclosureNotes(pid, { year, selected_sections })
        │  （不传 template_type；后端从 Project.template_type 权威解析）
        ▼
后端 render_disclosure_notes → NoteWordExporter.export(sections=selected_sections, ...)
        │
        ▼
仅生成勾选章节 → 关闭对话框 → loadList()/下载（现有成功流程）
```

### has_data 判定收敛（防漂移）

`has_data` 与 Word 导出 `_has_content` 必须**同口径**，否则出现「树上标有数据但导出空 / 树上标无数据但导出有内容」的不一致。

**关键事实（核对 `_effective_table_data` 源码）**：`NoteWordExporter._effective_table_data(note)` **只依赖 `note.table_data`**，对**任意** note 都调 `project_sub_tables(note.table_data)`（`project_sub_tables` 内部按 `_source ∈ {workpaper, workpaper_html}` 自行 no-op，非 workpaper 来源恒等返回），**不按 `content_type` 分支**，也不使用 `NoteWordExporter` 的其他实例状态（无 `self.db`）。故投影是 `note.table_data` 的**纯变换**。

**决策：抽取模块级共享 helper，投影内聚为纯函数（单一真源）**：

- 新建 `backend/app/services/note_content_utils.py`，含两个纯函数：
  - `effective_table_data(table_data: dict | None) -> dict | None`：把 `_effective_table_data` 的投影逻辑逐字节搬入（`project_sub_tables(table_data)` 非空 → `{**table_data, "_tables": projected}`；否则原样返回；投影异常 → `logger.warning` 后回退原 `table_data`）。**不按 content_type 分支**。
  - `note_has_data(note: DisclosureNote) -> bool`：`is_empty(not_applicable)` → 提前短路 `False`；`text_content` 非空 → `True`；否则内部 `effective_table_data(note.table_data)` 后遍历 `_tables`/单表降级，任一单元格 `value`/`manual_value` 非空、非 0、非「0」、非「-」→ `True`。
- `NoteWordExporter._effective_table_data(note)` 改为委托 `effective_table_data(note.table_data)`（行为逐字节等价）；`_has_content(note)` 改为委托 `note_has_data(note)`。
- `DisclosureEngine.get_notes_tree` 每节点调 `note_has_data(n)`，**无独立投影、无 content_type 分支**——与导出器走同一 helper，确保口径一致。

投影异常时 `effective_table_data` fail-open 回退原 `table_data`（与 `_effective_table_data` 现有降级一致）；`note_has_data` 整体不抛（单 note 判定失败由调用方 fail-open 记 `False`，见 Error Handling）。

## Components and Interfaces

### 后端

**`backend/app/services/note_content_utils.py`（新建）**

```python
def effective_table_data(table_data: dict | None) -> dict | None:
    """把 sub_table_data+_sub_table_columns 投影为 _tables[]（纯 note.table_data 变换）。
    与 NoteWordExporter._effective_table_data 逐字节等价（单一真源），投影异常 fail-open 回退原值。
    """

def note_has_data(note: DisclosureNote) -> bool:
    """章节是否含数据。与 NoteWordExporter._has_content 同口径（单一真源）。
    - is_empty(not_applicable) → False（提前短路）
    - text_content 非空 → True
    - effective_table_data(note.table_data) 的 _tables/单表任一单元格值非空/非0/非'0'/非'-' → True
    """
```

**`backend/app/services/note_word_exporter.py`（改）**

- `_effective_table_data(self, note)` → 委托 `effective_table_data(note.table_data)`；对外行为不变。
- `_has_content(self, note)` → 委托 `note_has_data(note)`；对外行为不变。

**`backend/app/services/disclosure_engine.py`（改）**

- `get_notes_tree(project_id, year)` 每个节点 dict 追加 `"has_data": note_has_data(n)`；现有字段（`id/note_section/section_title/account_name/content_type/status/sort_order`）保持不变、顺序不变、`has_data` 为附加末位字段。
- **无独立投影、无 content_type 分支**——直接调共享 `note_has_data(n)`，与导出器走同一投影与判定，杜绝两条口径分叉。

**接口契约（`GET /api/disclosure-notes/{project_id}/{year}`，`disclosure_notes.py::get_notes_tree`）**

- 响应节点新增 `has_data: bool`；其余字段与现状一致。路由层无需改（直接透传 `DisclosureEngine.get_notes_tree` 结果）。
- 权限：沿用现有项目级访问控制，不放宽。

**交付渲染接口（`render_disclosure_notes`，不改）**

- 已接受 `body.selected_sections`，已从 `Project.template_type` 权威解析变体，已透传 `NoteWordExporter.export(sections=selected_sections)`。本功能零改动。

### 前端

**`audit-platform/frontend/src/components/deliverable/DisclosureNotesSelectionDialog.vue`（新建）**

- Props：`visible: boolean`、`projectId: string`、`year: number`。
- Emits：`update:visible`、`confirm: { selectedSections: string[] }`。
- 内部状态：`treeNodes`（原始扁平树）、`grouped`（按顶层中文序号分组的 `el-tree` data）、`checkedKeys`、`loading`、`loadError: 'none' | 'not_found' | 'failed'`。
- 行为：
  - 打开时（`watch(visible)` / `@open`）调 `GET disclosureNotes.tree(pid, year)`；成功 → 分组构树；404 → `loadError='not_found'`；其他 → `loadError='failed'`。
  - 分组：按 `note_section` 首段中文序号（一/二/三/四/五…）分组为父节点；叶子节点显示 `note_section + section_title`，`has_data=false` 加灰色样式 + 「无数据」tag（不 `disabled`）。
  - 「一键预设生成」：`treeRef.setCheckedKeys(has_data=true 的叶子 key)`。
  - 「确认生成」：`getCheckedKeys(leafOnly=true)` 作 `selectedSections`；空 → 禁用 + 提示「请至少选择一个章节」。
  - `loadError !== 'none'` 或 `selectedSections` 空 → 「确认生成」禁用。
  - 「重试」：`loadError='failed'` 时重新拉树。
- UI：Element Plus，全中文，字号 13px；树用 `node-key="note_section"`、`show-checkbox`、`default-expand-all` 或按分组展开。

**`audit-platform/frontend/src/views/DeliverableCenter.vue`（改）**

- `goGenerateNotes()`：从「直接 `renderDisclosureNotes`」改为「打开对话框」：设置 `notesDialogVisible=true`（`guardGenerate('notes')` 门控保留在打开前）。
- 新增 `onNotesSelectionConfirm({ selectedSections })`：执行原生成流程——`generating=true` → `renderDisclosureNotes(projectId, { year, selected_sections: selectedSections })` → 成功提示/`platform_persist_failed` 警告 → `downloadFile(...)` → `loadList()` → 关闭对话框 → `finally generating=false`。
- 模板挂载 `<DisclosureNotesSelectionDialog v-model:visible :project-id :year @confirm="onNotesSelectionConfirm" />`。

**`audit-platform/frontend/src/services/deliverableApi.ts`（不改）**

- `renderDisclosureNotes(projectId, { year, selected_sections })` 已支持 `selected_sections`。

**附注树类型（前端）**

- 树节点类型补 `has_data?: boolean`（消费方按需读取）。

## Data Models

### 附注树节点（后端响应，`get_notes_tree` 单节点）

| 字段 | 类型 | 变更 | 说明 |
|------|------|------|------|
| `id` | string | 不变 | 章节 note 主键 |
| `note_section` | string | 不变 | 章节编号（如「五、1」「三、7」），前端 `node-key` 与 `selected_sections` 元素 |
| `section_title` | string | 不变 | 章节标题 |
| `account_name` | string\|null | 不变 | 科目名 |
| `content_type` | string\|null | 不变 | 内容类型（含 `workpaper`） |
| `status` | string | 不变 | `not_applicable`/`draft`/… |
| `sort_order` | int | 不变 | 排序 |
| **`has_data`** | **bool** | **新增** | 是否含数据；与 `_has_content` 同口径；`not_applicable` → `false` |

### 前端对话框内部模型

- `TreeLeaf { note_section, section_title, has_data }`；分组父节点 `{ key: '__group__一', label: '一、…', children: TreeLeaf[] }`（父节点 key 加前缀避免与真实 `note_section` 冲突，`getCheckedKeys(leafOnly=true)` 仅返回叶子 key，天然排除分组父节点）。
- **node-key 唯一性**：`el-tree` 的 `node-key` 用叶子 `note_section`；`note_section` 在同一项目/年度附注树中即业务唯一键（导出 `sections` 也按它筛选），故直接作 key。若极端出现重复 `note_section`（脏数据），仅产生 `el-tree` key 重复告警、不影响勾选正确性（重复章节导出仍去重一次）。
- 提交给后端的 `selected_sections`：叶子 `note_section` 字符串数组。

### 生成请求（不变）

`renderDisclosureNotes` body：`{ year: number, selected_sections: string[] }`（不含 `template_type`）。

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

本功能的正确性核心是两组纯逻辑：后端 `has_data` 判定（须与导出器 skip 判定同源）、前端选择集派生（一键预设 = has_data 集、叶子投影、预设叠加、生成守卫）。以下属性经属性反思合并两版冗余后得出（如「现有字段保持」与「has_data 附加」合并为节点契约、「空选禁用」与「加载失败不提交」合并为生成守卫、5.1/5.2/5.3 合并为叶子投影叠加）。

### Property 1: 节点契约——has_data 附加且保留既有字段

*For any* 项目附注集合，`get_notes_tree` 返回的每个节点都应含布尔字段 `has_data`，且保留全部既有字段（`id`、`note_section`、`section_title`、`account_name`、`content_type`、`status`、`sort_order`）值与语义不变，`has_data` 为附加末位字段。

**Validates: Requirements 2.1, 2.3**

### Property 2: has_data 与导出器 skip 判定等价（同源）

*For any* 章节内容（任意 `text_content`，含空白/None；任意 `table_data`，含空/0/"-"/非空单元格、多表 `_tables` 与单表结构），`note_has_data(node)` 的结果应等于 `not should_skip_empty_section(node)`，即与导出器 `_has_content` 采用同一空单元格扫描口径，无判定漂移。

**Validates: Requirements 2.2**

### Property 3: not_applicable / is_empty 章节 has_data 恒为 false

*For any* `is_empty == true`（`status == not_applicable`）的章节节点，无论其 `table_data` 是否残留非空单元格，`has_data` 应为 `false`（提前短路）。

**Validates: Requirements 2.4**

### Property 4: 一键预设勾选集等于 has_data 叶子集

*For any* 附注树节点集合，点击「一键预设生成」后被勾选的叶子章节集合应恰好等于 `has_data == true` 的叶子章节 `note_section` 集合，`has_data == false` 的章节不在预设勾选集中。

**Validates: Requirements 3.1, 3.2**

### Property 5: 勾选分组父节点纳入其下全部叶子章节

*For any* 分组树与任一分组父节点，勾选该父节点后，其下全部叶子章节的 `note_section` 都应出现在最终勾选集（叶子投影结果）中。

**Validates: Requirements 4.2**

### Property 6: 空章节可被手动勾选纳入最终集

*For any* `has_data == false` 的空章节叶子，其被置灰但可手动勾选；用户手动勾选后其 `note_section` 应被纳入最终勾选集 `selected_sections`（置灰不阻止纳入）。

**Validates: Requirements 3.3, 4.3**

### Property 7: 叶子投影与预设叠加——提交集为当前勾选叶子投影

*For any* 初始预设勾选集与其后一序列用户勾选/取消操作，最终（及确认提交的）`selected_sections` 应等于当前 `el-tree` 已勾选叶子的 `note_section` 投影（只含叶子、不含分组父节点），即反映预设之上的全部用户增删，而非回退到预设的原始集合。

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 8: 导出仅生成 selected_sections 中的章节

*For any* 附注全集与其任一子集 `selected_sections`，交付渲染接口以当前最终勾选集调用，导出产出的章节集合应为 `selected_sections` 的子集（导出器按 `sections=` 筛选，不生成未勾选章节）。

**Validates: Requirements 6.1, 6.3**

### Property 9: 生成守卫——空选集或树未成功加载时渲染接口永不被调用

*For any* 导致 `selected_sections` 为空的路径，或附注树处于加载失败态（`not_found` / `failed`）时，「确认生成」始终禁用；即使强制触发提交也不应调用交付渲染接口 `renderDisclosureNotes`（不以空集或未定义集提交）。

**Validates: Requirements 7.1, 7.2, 8.1, 8.3**

### Property 10: 前端不硬编码变体前缀——原样渲染后端任意 note_section

*For any* 后端返回的节点集合（含混合「三、」「四、」等任意前缀），对话框应原样渲染其 `note_section` 进树，不在前端按变体或前缀做过滤/改写/推断。

**Validates: Requirements 9.1, 9.2**

### Property 11: 前端不传 template_type——变体由后端解析

*For any* 生成请求，请求 body 不含 `template_type`；变体由后端从 `Project.template_type` 权威决定。

**Validates: Requirements 6.2, 9.3**

## Error Handling

| 场景 | 处理 | 需求 |
|------|------|------|
| 树服务 404（附注不存在） | 对话框显示「附注数据不存在，请先生成附注」，确认按钮禁用；不触发渲染 | 8.1, 8.3 |
| 树服务其他错误 / 超时 | 显示加载失败提示 + 「重试」按钮；重试重新调 `getDisclosureNotesTree`；失败态下不触发渲染 | 8.2, 8.3 |
| sub_table_data 投影异常（后端） | 共享 helper 对单个 note 判定失败时 `project_sub_tables` try/except 降级为不投影（按原始 `table_data` 判定），fail-open 记 `has_data=false` 并 `logger.warning`，不阻断整棵树返回（宁可标无数据可手动补勾，不使树 500） | 2.2（降级） |
| 空选集提交 | 确认按钮 `disabled`；`onConfirm` 二次校验空集 → `ElMessage.warning('请至少选择一个章节')` + return，不 emit、不调接口 | 7.1, 7.2 |
| 渲染接口失败 | 沿用现有 `goGenerateNotes` 的 `catch` → `ElMessage.error('生成附注失败')`，`generating=false`；弹窗保持打开供重试 | 6.4（现有流程） |
| 平台留存失败 `platform_persist_failed` | 沿用现有 `ElMessage.warning('平台留存失败，请从版本链重新下载')` | 现有 |
| 无导出权限 | 入口按现有 `guardGenerate` / 权限门控完全隐藏，服务端 `DeliverableAction.export` 兜底 403 | 10.1, 10.2 |
| 无项目访问权限调树服务 | `require_project_access("readonly")` 拒绝（现有守卫，不放宽） | 10.3 |

## Testing Strategy

**双测试路径**：单元/示例测试覆盖具体交互与错误分支，属性测试覆盖跨输入的普遍规律。

### 属性测试（Property-Based Tests）

- **后端**：Python `hypothesis`（现有 `conftest.py` 已注册 `fast` profile，`max_examples` 默认 5、可用 `HYPOTHESIS_MAX_EXAMPLES` 覆盖；正式验收按 100+ 迭代运行）。
  - P1（节点契约）、P2（has_data ≡ not should_skip_empty_section，**核心**）、P3（is_empty → false）：生成随机 `text_content`（空白/None/非空）+ `table_data`（含空/0/"-"/非空单元格、`_tables` 多表与单表、`is_empty` 组合），断言等价与字段契约。
  - P8（导出筛选子集）：生成 notes 全集 + 随机 `selected_sections` 子集，验证 `NoteWordExporter.export(sections=...)` 产出章节 ⊆ `selected_sections`（复用现有导出器，不重写）。
- **前端**：`fast-check` + `vitest`。
  - P4（预设 = has_data 叶子集）、P5（父勾联动全叶子）、P6（空章节可纳入）、P7（叶子投影 + 预设叠加）、P9（生成守卫）、P10（原样渲染无前缀过滤）：对纯选择函数（`computePresetKeys`、叶子投影 `deriveSelectedSections`、分组建树 `buildGroupedTree`）生成随机节点集与操作序列做模型对照。
  - P11（不传 template_type）：断言生成请求 body 不含 `template_type`。
- **配置**：每个属性测试 ≥100 迭代；每个测试注释引用设计属性，标签格式 **Feature: disclosure-notes-selective-generation, Property {number}: {property_text}**。
- **可测性设计**：前端把 `computePresetKeys` / `deriveSelectedSections` / `buildGroupedTree` 抽为纯函数（不依赖 `el-tree` 实例），便于属性测试；组件层用示例测试覆盖 `el-tree` 集成。

### 单元 / 示例测试

- **后端**：
  - `test_note_content_utils.py`：`note_has_data` 各分支（`text_content` 非空/`table_data` 有值/全空/全 0/全「-」/`_tables` 多表/`not_applicable` 短路）。
  - `test_get_notes_tree_has_data.py`：`get_notes_tree` 每节点含 `has_data`，值与 `NoteWordExporter._has_content` 对同一 note 一致；现有字段保持。
- **前端组件**（`DisclosureNotesSelectionDialog.vue` + `DeliverableCenter.vue`）：
  - 1.1 点击打开弹窗而非直接渲染；1.2 以 (pid, year) 调树 API；1.3/1.4 分组分层 + `show-checkbox` 渲染 + 标记；1.5 加载态禁用确认。
  - 3.2 空章节置灰；3.3 置灰非禁用可补勾；3.4 勾选数量展示；4.1 勾选/取消实时更新。
  - 6.1 确认以 `{ year, selected_sections }` 调用；6.2 调用体无 `template_type`；6.4 成功后关闭弹窗 + 刷新列表 + 下载。
  - 7.1 空集禁用确认；8.1 404 提示；8.2 失败提示 + 重试。
  - 10.1 无导出权限入口隐藏（回归）。

### 集成测试（Integration，非 PBT）

- 9.1 / 9.3：listed / soe 项目各一，`get_notes_tree` 返回前缀符合项目变体；确认生成时导出用项目 `template_type` + 仅含所选章节（1–3 例）。
- 10.2 / 10.3：无 `DeliverableAction.export` 权限调渲染接口断言 403；无项目访问权限调树服务断言拒绝（现有守卫回归）。

## Notes

- 本功能不改 `template_type` 解析、不改 `skip_empty` 语义、不重写导出。`has_data` 是唯一后端数据契约新增。
- `has_data` 与 `_has_content` 收敛为单一 helper 是防漂移关键（避免树标记与导出结果不一致）。
- 前端对话框不复用 `DocStructureTree.vue`（静态文档结构），而是消费附注实时树服务响应，确保「所见即实时附注」。
