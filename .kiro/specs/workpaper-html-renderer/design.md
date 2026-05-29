# 底稿 HTML 渲染器（通用组件）— 设计文档

> 起草日期：2026-05-25
> 对应需求：`.kiro/specs/workpaper-html-renderer/requirements.md`（1928 行）
> 渲染范围：1788 单体真底稿（已剔除 450 合并 + 347 假底稿 + 7 合并 pending），单体范围 100% 自动归类
> 状态：✅ 代码实现完成 | ⚠️ render_schema 覆盖率 55%（修复见 workpaper-editor-slimdown Sprint 1）
> 关联模块：复用 ProcedureTrimming / chain_orchestrator / cross-ref:updated / report_line_mapping / disclosure_notes / workpaper_attachment / LibreOffice + python-docx + openpyxl

---

## 一、概览（Overview）

### 1.1 设计目标

把 1788 单体真底稿（A/B/C/D/E 共 1346 sheet）从 Univer Sheets 切换为**纯 HTML 通用组件**渲染，保留 F/G 数据测算 558 sheet 走 Univer。导出 xlsx 走**致同模板填值还原**链路（方案 C），保证字符级 1:1 还原版式。

**EARS 决策**：
- WHEN 用户打开 wp_code 对应底稿 THEN 系统 SHALL 按 9 类（A~I）路由分发到对应 HTML/Univer 组件，零 fallback
- WHEN 用户保存 HTML 数据 THEN 系统 SHALL 写入 `working_paper.parsed_data` JSONB（沿用已有结构 + 扩展 schema_version 字段）
- WHEN 用户点击「导出 xlsx」 THEN 系统 SHALL 加载致同模板 xlsx + openpyxl 按 schema 填值 + 保留原公式与合并区
- WHEN 致同发布新版模板 THEN 系统 SHALL 通过 `workpaper_template_version` 表多版本共存，老项目沿用旧版
- WHEN 跨底稿引用源数据更新 THEN 系统 SHALL 触发 `cross-ref:updated` 事件，订阅方刷新引用值

### 1.2 关键设计决策（与方案 C 对齐）

| # | 决策 | 理由 |
|---|------|------|
| D1 | 数据存 JSONB（沿用 `parsed_data`），不新建宽表 | 模板 schema 多变，宽表难维护；JSONB 已支撑 univer_snapshot |
| D2 | 模板 xlsx 占位符 schema 用 YAML 描述（fixed_cells / dynamic_table / formulas / merged_cells / static_text） | 人类可读 + 易编辑 + 致同模板修订时可 diff |
| D3 | 公式列保留原模板公式（不写值） | 用户重新打开 xlsx 时公式自动重算，HTML 显示值 ≡ xlsx 公式重算值 |
| D4 | 9 类组件用 `componentType` 路由，禁止 Univer 兜底 | 保证每个 sheet 必有归类，pending=0 是工程铁律 |
| D5 | 项目实例继承 + 覆盖（`project_workpaper_sheet_override`） | 用户自定义底稿不污染模板归类 |
| D6 | 跨底稿索引用 11 命名空间 + 4 层级跳转语义（`<GtIndexChip>` 组件） | 从 Layer 1 cell → Layer 4 module 一套规则 |
| D7 | 联动机制基于现有 `cross-ref:updated` eventBus + `useStaleImpact`，不新增基础设施 | 复用现有 D 循环已验证的机制 |
| D8 | 附注双源统一为 **底稿 → 模块单向同步**（推荐 6.2 选项 A） | 底稿是编辑入口，disclosure_notes 是汇总输出 |

### 1.3 不在范围

- 不动 F/G 类 Univer 渲染（558 sheet 保留）
- 不动 A3 合并 / A6 集团审计模块（独立模块负责 450 sheet）
- 不替换 disclosure_notes 模块（保留作为汇总输出层）
- 不动 chain_orchestrator 主流程（仅扩展状态写回）
- 不做新 PDF 链路（继续走 LibreOffice）
- 跨年度数据延续 UI（仅落表结构 P0+P1，UI 后置独立 spec）


---

## 二、整体架构（Architecture）

### 2.1 三层架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       前端：HTML 通用组件层                                │
│                                                                           │
│  ┌────────────────┐                                                       │
│  │ GtWpRenderer   │ (顶层路由组件，按 componentType 分发)                  │
│  └───────┬────────┘                                                       │
│          │                                                                 │
│   ┌──────┼─────────┬────────────┬─────────────┬─────────────┐            │
│   ▼      ▼         ▼            ▼             ▼             ▼            │
│ GtAProgram  GtBIndex  GtCNoteTable  GtDForm   GtEControl   <UniverHost>   │
│ Console     (B 目录)   (C 嵌套表)    (D 表单)   Test         (F/G 保留)    │
│ (A 中控台)            5 子模式              (含 stepper)                  │
│                                                                           │
│  辅助：GtIndexChip / GtTraceabilityDialog / GtAttachmentChip               │
│                                                                           │
│  Composables：useWpRenderer / useWpClassification / useEditorActions      │
│              + 既有 useStaleImpact / useCycleDialogs / useSheetNavFacade  │
└─────────────────────────────────────────┬─────────────────────────────────┘
                                          │ HTTP + SSE
┌─────────────────────────────────────────▼─────────────────────────────────┐
│                       后端：FastAPI 服务层                                  │
│                                                                           │
│  /api/workpapers/{id}/render-config   ← 前端拉 schema                      │
│  /api/workpapers/{id}/save            ← HTML 数据保存                      │
│  /api/workpapers/{id}/export-xlsx     ← openpyxl 模板填值                  │
│  /api/wp-classifications              ← 9 类归属查询                       │
│  /api/wp-template-versions            ← 多版本管理                         │
│  /api/wp-index-resolve                ← <GtIndexChip> 解析校验             │
│                                                                           │
│  既有端点（不动）：                                                        │
│  /api/custom-query/wp-sheet-preview / wp-id-by-code  ← 跨 sheet 取值       │
│  /api/projects/{pid}/workpapers/cross-ref           ← 跨底稿引用           │
│  /api/projects/{pid}/stale-impact                   ← 失效传播             │
│                                                                           │
│  Services：                                                               │
│  - wp_render_schema_service     (schema 加载 + 项目级覆盖)                 │
│  - wp_xlsx_export_service       (openpyxl 填值 + 公式保留 + 字符级 diff)    │
│  - wp_template_version_service  (多版本 + auto_map/user_confirm)           │
│  - wp_classification_service    (扩展现有，加 scope/is_real_workpaper)     │
└─────────────────────────────────────────┬─────────────────────────────────┘
                                          │
┌─────────────────────────────────────────▼─────────────────────────────────┐
│                       存储层：PostgreSQL + 文件系统                          │
│                                                                           │
│  PG：                                                                     │
│  - working_paper.parsed_data JSONB        ← 已有，扩展 schema_version       │
│  - workpaper_sheet_classification         ← 已有，扩展 6 字段               │
│  - workpaper_template_version             ← 新表（P0+P1）                  │
│  - project_workpaper_sheet_override       ← 新表（项目级覆盖）              │
│  - workpaper_sheet_version_mapping        ← 新表（跨版本映射，P1）          │
│  - cross_wp_references / wp_index         ← 既有                           │
│                                                                           │
│  文件：                                                                   │
│  - backend/wp_templates/{cycle}/*.xlsx    ← 致同模板（349 xlsx）           │
│  - backend/data/wp_render_schema/         ← 新增 YAML schema               │
│  - storage/projects/{pid}/workpapers/     ← 项目实例 xlsx 落地             │
└───────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流（Read / Write 双路径）

**读路径（用户打开底稿）**：

```
用户打开 wp_id
  → GET /api/workpapers/{id}/render-config
  → 服务端：
       1. 查 wp_index 取 wp_code
       2. 查 workpaper_sheet_classification 获 9 类归属（按 template_version_id）
       3. 查 project_workpaper_sheet_override 取项目级覆盖（如有）
       4. 加载 wp_render_schema/{wp_code}.yaml
       5. 读 working_paper.parsed_data['html_data'] (项目数据)
  → 返回 { componentType, schema, htmlData, sheets[], crossRefs[] }
  → 前端：GtWpRenderer 路由到对应组件渲染
```

**写路径（用户保存）**：

```
用户编辑 → debounce 1.5s
  → POST /api/workpapers/{id}/save
       body: { sheet_name, html_data: {...}, schema_version }
  → 服务端：
       1. JSON Schema 校验（按 wp_render_schema/*.yaml 中定义的字段类型）
       2. merge 到 working_paper.parsed_data['html_data'][sheet_name]
       3. 调 cross_ref_service.detect_changes 计算影响范围
       4. 发 SSE cross_ref.updated（如有跨底稿引用变化）
  → 前端：useStaleImpact 触发 affected 列表 + 黄色横幅提示
  → 订阅方（其他底稿编辑器）onCrossRefUpdated → 刷新引用值
```

**导出路径（用户点导出 xlsx）**：

```
POST /api/workpapers/{id}/export-xlsx
  → wp_xlsx_export_service：
       1. 加载致同模板 backend/wp_templates/{cycle}/{wp_code}.xlsx (read-only mode)
       2. 复制为 BytesIO 工作簿（保留 styles / formulas / merged_cells）
       3. 按 wp_render_schema/{wp_code}.yaml 遍历每个 sheet：
          - fixed_cells: 写入 schema 默认值（项目元数据 + 索引号）
          - dynamic_table: html_data[sheet][rows] 按 columns 映射写入
          - formulas: 跳过（保留原公式）
          - static_text: 跳过（保留原文字）
          - merged_cells: 跳过（openpyxl 加载时已含 merged_ranges）
       4. ws.calculate_dimension() 兜底
       5. 字符级 diff 校验（pytest 测试链路）
  → 返回 attachment xlsx
```


---

## 三、组件与接口（Components and Interfaces）

### 3.1 前端组件层次

```
GtWpRenderer.vue                          ← 顶层路由组件（按 componentType 分发）
├── GtAProgramConsole.vue                 ← A 程序表中控台（261 sheet）
├── GtBIndex.vue                          ← B 底稿目录（148 sheet）
├── GtCNoteTable.vue                      ← C 附注披露嵌套表（166 sheet）
├── GtDForm.vue                           ← D 类表单顶层（449 sheet）
│   ├── GtDFormTable.vue                  ←   D 子模式 1：表格型检查（如 L5-6 关联方）
│   ├── GtDFormParagraph.vue              ←   D 子模式 2：段落型政策（如 D2-8 坏账政策）
│   ├── GtDFormQA.vue                     ←   D 子模式 3：是否问答型（如 D2-13 业务模式）
│   ├── GtDFormConfirmation.vue           ←   D 子模式 4：函证/盘点/访谈（含专属子组件）
│   └── GtDFormReview.vue                 ←   D 子模式 5：复核记录（含电子签）
├── GtEControlTest.vue                    ← E 控制测试（322 sheet，含 stepper）
├── GtHStaticDoc.vue                      ← H 辅助说明（104 sheet，只读 markdown）
├── <UniverHost />（既有）                 ← F/G 类保留 Univer 渲染（558 sheet）
└── <SkippedSheetPlaceholder />           ← I 占位（243 sheet 跳过 + 提示）

辅助组件：
├── GtIndexChip.vue                       ← 索引号点击跳转（4 层级语义）
├── GtTraceabilityDialog.vue              ← 报表/附注溯源弹窗
├── GtAttachmentChip.vue                  ← 附件/函证 N 个证据 chip
└── GtFormulaPopover.vue                  ← 公式溯源 popover

Composables：
├── useWpRenderer()                       ← 顶层数据加载 + componentType 派生
├── useWpClassification()                 ← 9 类归属 + scope 路由判定
├── useWpRenderSchema()                   ← schema 加载 + 校验 + 项目级覆盖
└── （既有）useStaleImpact / useCycleDialogs / useSheetNavFacade / useEditorActions
```

### 3.2 GtWpRenderer（顶层路由组件）

```typescript
interface Props {
  wpId: string                            // 底稿 ID
  initialSheet?: string                   // 进入时聚焦的 sheet（可选）
  initialCell?: string                    // 进入时聚焦的 cell（可选）
  readonly?: boolean                      // 只读模式（如归档后）
}

interface Emits {
  (e: 'sheet-change', sheetName: string): void
  (e: 'cell-focus', payload: { sheet: string; cell: string }): void
  (e: 'save-success', payload: SavePayload): void
  (e: 'cross-ref-update', payload: CrossRefPayload): void
}

// 核心逻辑
const { renderConfig, loading, error } = useWpRenderer(wpId)
const componentType = computed(() => renderConfig.value?.componentType)
// componentType ∈ {a-program-console, b-index, c-note-table,
//                  d-form-table, d-form-paragraph, d-form-qa,
//                  d-form-confirmation, d-form-review,
//                  e-control-test, h-static-doc, univer, skip}
```

**EARS**：
- WHEN renderConfig.componentType = 'univer' THEN GtWpRenderer SHALL 渲染 `<UniverHost>` 而不是 HTML 组件
- WHEN renderConfig.componentType = 'skip' THEN GtWpRenderer SHALL 显示"此 sheet 不参与渲染"提示
- IF wp_id 不存在 THEN useWpRenderer SHALL 进入 error 状态触发 GtError overlay（参见 useWpDetailGuard 模式）

### 3.3 GtAProgramConsole（A 类中控台）

```typescript
interface Props {
  wpId: string
  sheetName: string                       // 如 '应收账款实质性程序表D2A'
  schema: AProgramSchema                  // 来自 wp_render_schema YAML
  htmlData: AProgramHtmlData              // 项目级数据
  readonly?: boolean
}

interface AProgramSchema {
  fixed_cells: Record<string, string>     // { 'A1': '致同会计师事务所', 'H3': '${index_no}' }
  programs: ProgramItemSchema[]           // 程序清单 schema
  assertions: ('存在' | '完整性' | '权利义务' | '准确性' | '列报')[]
}

interface AProgramHtmlData {
  programs: ProgramRow[]                  // 用户填写的程序行
  trim_decisions: TrimDecision[]          // 裁剪决策（写回 ProcedureInstance）
  signatures?: Signature[]                // 编制人/复核人电子签
}

interface Emits {
  (e: 'program-trim', payload: { programId: string; reason: string }): void
  (e: 'program-status-change', payload: { programId: string; status: string }): void
  (e: 'jump-to-workpaper', wpCode: string): void   // I 列底稿索引点击
  (e: 'save', data: AProgramHtmlData): void
}
```

**核心交互**：
- 程序行展开显示完整描述 + 历史决策
- 状态切换（执行/裁剪/已完成）+ 必填理由
- 关联底稿索引号渲染为 `<GtIndexChip>` 可点击
- 类别筛选（常规★/IPO/备选/舞弊应对）
- 批量裁剪（多选 + 填理由 → 写回 ProcedureInstance.status='not_applicable'）
- 进度条（17/20 完成 / 2 已裁 / 1 进行中）

### 3.4 GtBIndex（B 类底稿目录）

```typescript
interface Props { wpId: string; sheetName: string; schema: BIndexSchema; htmlData: BIndexHtmlData }
interface BIndexSchema {
  preparation_info_fields: ('entity_name' | 'period_end' | 'preparer' | 'reviewer' | ...)[]
  navigation_table: { columns: ['seq', 'content', 'index_ref', 'no_print'] }
}
interface BIndexHtmlData {
  preparation_info: Record<string, string>
  navigation_rows: Array<{ seq: number; content: string; index_ref: string; no_print: boolean }>
}
interface Emits {
  (e: 'jump-to-section', indexRef: string): void
  (e: 'review-status-change', status: string): void
  (e: 'save', data: BIndexHtmlData): void
}
```

**核心交互**：
- 编制信息从 project meta + user profile 自动填充（首次加载）
- 索引导航行可点跳转（同底稿 sheet 切换 / 跨底稿 router.push）
- "无需打印"批量切换（导出时保留原合并区，但 cell 写入空字符串 + 加批注"已标记不打印"）

### 3.5 GtCNoteTable（C 类附注嵌套表）

```typescript
interface Props { wpId: string; sheetName: string; schema: CNoteTableSchema; htmlData: CNoteTableHtmlData }
interface CNoteTableSchema {
  applicable_standard: 'soe_standalone' | 'listed_standalone' | 'soe_consolidated' | 'listed_consolidated'
  sub_tables: SubTableSchema[]            // 4-7 张子表
  inheritance_rules: InheritanceRule[]    // 子表合计 → 主表对应行
}
interface SubTableSchema {
  id: string                              // 'aging_period_end' / 'single_provision' 等
  title: string
  type: 'static_rows' | 'dynamic_rows'    // 动态行支持增删
  columns: ColumnDef[]
  applicable_to_sub_class?: ('listed' | 'soe')[]   // 上市/国企版本切换
}
interface CNoteTableHtmlData {
  sub_table_data: Record<string, RowData[]>
  hidden_subtables: string[]              // "不适用"软标记
}
interface Emits {
  (e: 'subtable-toggle', subTableId: string): void
  (e: 'standard-switch', standard: string): void
  (e: 'sync-to-disclosure-notes', payload: SyncPayload): void   // 单向同步
  (e: 'save', data: CNoteTableHtmlData): void
}
```

**EARS**：
- WHEN 用户切换 standard（上市↔国企）THEN GtCNoteTable SHALL 保留共有字段值，差异字段 ElMessageBox 提示
- WHEN 子表合计变化 THEN GtCNoteTable SHALL 实时更新主表对应行 + 触发 inheritance_rules 校验

### 3.6 GtDForm（D 类 5 子模式）

D 类 449 sheet 按子模式路由到 5 个组件：

| 子模式 | 组件 | 适用 sheet 数 | 关键交互 |
|--------|------|--------------|---------|
| 表格型 | GtDFormTable | ~250 | 行项目矩阵 + 关联方/项目动态增删 + 字典下拉 |
| 段落型 | GtDFormParagraph | ~19 | markdown 富文本 + 占位符提示 + 引用文档链接 |
| 是否问答 | GtDFormQA | ~9 | radio 选项 + 自动判定（业务模式 → 报表项目分类） |
| 函证/盘点/访谈 | GtDFormConfirmation | ~109 | 专属子组件（询证函生成 / 盘点队伍 / 访谈记录） |
| 复核记录 | GtDFormReview | ~27 | 电子签 + 时间戳 + 复核状态机 |

**统一 Props/Emits**：

```typescript
interface DFormProps {
  wpId: string; sheetName: string
  schema: DFormSchema    // 含 form_type 字段决定子模式
  htmlData: DFormData
  readonly?: boolean
}
interface DFormEmits {
  (e: 'field-change', payload: FieldChangePayload): void
  (e: 'jump-to-reference', refCode: string): void   // 引用文档 / 关联底稿
  (e: 'save', data: DFormData): void
  (e: 'sign', payload: SignaturePayload): void      // 仅 review 子模式
}
```

### 3.7 GtEControlTest（E 类控制测试）

```typescript
interface Props { wpId: string; sheetName: string; schema: EControlTestSchema; htmlData: EControlTestData }
interface EControlTestSchema {
  test_type: 'summary' | 'single' | 'evaluation_step'   // 三种结构
  steps?: StepDef[]                                      // evaluation_step 的 6 步骤
  hints?: HintBlock[]                                    // 风险说明 / 样本规模区间
}
interface EControlTestEmits {
  (e: 'step-advance', step: number): void
  (e: 'conclusion-change', conclusion: string): void
  (e: 'trigger-procedure-trimming-suggestion', payload: SuggestionPayload): void
  (e: 'save', data: EControlTestData): void
}
```

**核心交互**：
- evaluation_step 子模式用 el-steps stepper 渲染 6 步骤
- 4 个互斥结论用 radio（控制有效 / 扩大测试有效 / 仍有偏差 / 系统性偏差）
- 控制有效结论 → emit 'trigger-procedure-trimming-suggestion' → 写入 ProcedureTrimming 建议
- 风险说明长段折叠展开

### 3.8 GtIndexChip（跨底稿索引跳转）

```typescript
interface Props {
  value: string                           // '[D2-1]' / 'Note:五-1-1' / 'TB:1122' 等
  validate?: boolean                      // 默认 true，自动调 wp_index 校验存在性
  contextProjectId?: string               // 跨项目场景禁止跳转
}

interface Emits {
  (e: 'click', resolved: ResolvedIndexRef): void
}

interface ResolvedIndexRef {
  ns: 'wp' | 'sheet' | 'cell' | 'Note' | 'TB' | 'Adj' | 'Att' | 'EQCR'
  layer: 1 | 2 | 3 | 4                    // 跳转层级
  target: string
  exists: boolean                         // 校验后状态
  routeTarget?: RouteLocationRaw          // 已构造的路由对象
}
```

**11 命名空间路由（详见 §3.10）**：
- 严格模式 `<ns>:<target>`：`Note:` / `TB:` / `Adj:` / `Att:` / `EQCR:` / `wp:` / `sheet:` / `cell:` / `Calc:` / `Sample:` / `Confirm:`
- 宽松模式 `[A-S]\d+(-\d+)*[A-Z]?`（识别文本中的底稿编码）

**9 种边缘 case 处理**（与需求 §3.11.10 一致）：

| Case | 处理 |
|------|------|
| 中文索引号 | `Note:五-1-1` / `Note:五、(1)货币资金` 都匹配 |
| 带空格 | trim 后匹配 |
| 大小写 | 归一化为大写后匹配 |
| 多目标 | hover 弹菜单选择 |
| 不存在 | 灰显 + tooltip "底稿不存在或被裁剪" |
| 被裁剪 | 灰显 + tooltip "已裁剪：理由" |
| 跨项目 | 禁止跳转 |
| GT_Custom | 不可跳转（白名单跳过） |
| 空 sheet | 跳转但提示"sheet 为空" |

### 3.9 GtTraceabilityDialog（报表/附注溯源）

```typescript
interface Props {
  source: 'report' | 'disclosure' | 'workpaper'
  identifier: string                      // row_code / section_id / cell_ref
  projectId: string
}

// 内部分两路调用：
// 1. 反向溯源：GET /api/workpapers/trace?source=report&row_code=BS-007
//    返回 { upstream: [{ wp_code, sheet, cell, value }, ...] }
// 2. 正向影响：GET /api/workpapers/trace?source=workpaper&wp_code=D2&cell=K15
//    返回 { downstream: [{ target: 'report', row_code: 'BS-007' }, ...] }
```


### 3.10 11 命名空间路由表

| 命名空间 | 用途 | 路由 | 例子 |
|---------|------|------|------|
| `wp:` | 主底稿编辑器 | `/projects/:pid/workpapers/:wpId/edit` | `wp:D2` |
| `sheet:` | 同底稿 sheet 切换 | `?sheet=<name>` | `sheet:D2-1` |
| `cell:` | sheet + cell 高亮 | `?sheet=...&cell=...` | `cell:D2-1!B23` |
| `Note:` | 附注模块 | `/projects/:pid/disclosure-notes?section=...` | `Note:五-1-1` |
| `TB:` | 试算表 | `/projects/:pid/trial-balance?account=...` | `TB:1122` |
| `Adj:` | 调整分录 | `/projects/:pid/adjustments?id=...` | `Adj:AJE-001` |
| `Att:` | 附件预览 | `/projects/:pid/attachments?id=...` | `Att:UUID` |
| `EQCR:` | EQCR 工作台 | `/eqcr-workbench?id=...` | `EQCR:RID` |
| `Calc:` | 计算 dialog | 触发对应 dialog | `Calc:depreciation` |
| `Sample:` | 抽样工具 | `/projects/:pid/sampling?id=...` | `Sample:F2-VAL` |
| `Confirm:` | 函证管理 | `/projects/:pid/confirmation?id=...` | `Confirm:D0-001` |

### 3.11 联动机制实现

```
┌─────────────────── Layer 1: sheet 内 ───────────────────┐
│  HTML 计算函数库（基础四则 + 行/列合计 + 比率）            │
│  GtFormulaPopover 实时显示"此值由 X+Y 计算"                │
│  实时校验：subtable 合计 ↔ 主表行（C 类核心）              │
└──────────────────────────────────────────────────────────┘

┌─────────────────── Layer 2: sheet 间 ───────────────────┐
│  schema 中 source: 'wp_code:sheet:cell' 引用              │
│  onMounted → query_workpaper API 拉值                     │
│  保存时 → cross_ref_service.detect_changes 检测            │
└──────────────────────────────────────────────────────────┘

┌─────────────────── Layer 3: 底稿间 ─────────────────────┐
│  cross_wp_references.json 400 条引用规则（既有）          │
│  保存触发 cross_ref_service.notify → SSE cross_ref.updated │
│  订阅方（其他底稿编辑器）onCrossRefUpdated → 刷新引用值    │
│  既有 useStaleImpact composable 处理 stale 传播           │
└──────────────────────────────────────────────────────────┘

┌─────────────────── Layer 4: 模块间 ─────────────────────┐
│  报表：report_line_mapping (4 套维度) → report_snapshot   │
│  附注：底稿 → disclosure_notes 单向同步（推荐方案 6.2-A） │
│  审计报告：python-docx 引用底稿 cell                      │
│  EQCR：双向引用（底稿 ↔ EQCR Workbench）                  │
│  归档：LibreOffice 转 PDF + 电子签                        │
│  Dashboard：wp_file_status 进度卡                         │
│  委派矩阵：A 程序级负责人分配                              │
│  电子证据：workpaper_attachment + 函证                    │
└──────────────────────────────────────────────────────────┘
```

**复用既有事件总线**（不新增）：

```typescript
// audit-platform/frontend/src/utils/eventBus.ts 既有事件
eventBus.emit('cross-ref:updated', {
  projectId: string
  targetWpCode: string
  changedSheets: string[]
})
eventBus.emit('sse:sync-event', { event_type: 'cross_ref.updated', ... })
```

**新增 useWpRenderer composable**（核心数据加载）：

```typescript
export function useWpRenderer(wpId: Ref<string>) {
  const renderConfig = ref<RenderConfig | null>(null)
  const loading = ref(true)
  const error = ref<Error | null>(null)
  const componentType = computed(() => renderConfig.value?.componentType ?? 'skip')

  async function load() {
    loading.value = true
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/render-config`)
      renderConfig.value = res
    } catch (e) {
      error.value = e as Error
    } finally {
      loading.value = false
    }
  }

  // SSE 订阅：跨底稿引用变化时刷新
  function onCrossRefUpdated(payload: CrossRefUpdatedPayload) {
    if (payload.targetWpCode === renderConfig.value?.wpCode) {
      load()  // 重新拉取最新引用值
    }
  }

  onMounted(() => {
    load()
    eventBus.on('cross-ref:updated', onCrossRefUpdated)
  })
  onUnmounted(() => {
    eventBus.off('cross-ref:updated', onCrossRefUpdated)
  })

  return { renderConfig, loading, error, componentType, reload: load }
}
```

**新增 useWpClassification composable**（9 类归属判定 + scope 路由）：

```typescript
export function useWpClassification(wpCode: Ref<string>, projectId: Ref<string>) {
  const classification = ref<ClassificationResult | null>(null)

  async function load() {
    const res = await api.get('/api/wp-classifications', {
      params: { wp_code: wpCode.value, project_id: projectId.value }
    })
    classification.value = res
  }

  const componentType = computed(() => {
    const c = classification.value
    if (!c) return 'skip'
    // scope 路由：合并/母公司专属 → 委派给独立模块
    if (c.scope === 'consolidated') return 'delegate-consolidation'
    if (c.scope === 'parent_only') return 'delegate-parent-view'
    // 9 类映射
    return c.classMapping  // a-program-console / b-index / c-note-table / d-form-* / e-control-test / univer / h-static-doc / skip
  })

  const isRealWorkpaper = computed(() => classification.value?.is_real_workpaper ?? true)
  const excludeFromArchive = computed(() => classification.value?.exclude_from_archive ?? false)

  return { classification, componentType, isRealWorkpaper, excludeFromArchive, load }
}
```


---

## 四、数据模型（Data Models）

### 4.1 ER 图

```
┌─────────────────────────────────┐
│ workpaper_template_version (新)  │
│ id PK / version / release_date  │
│ is_current / parent_version_id  │
└────────┬────────────────────────┘
         │ 1:N
         ▼
┌────────────────────────────────────────────┐
│ workpaper_sheet_classification (扩展)        │
│ template_version_id FK / wp_code / sheet     │
│ class (A-/B-/C-/D-/E-/F-/G-/H-/I-)            │
│ is_real_workpaper / exclude_from_archive     │
│ exclude_from_progress / is_static_doc        │
│ scope (standalone/consolidated/parent_only)  │
│ delegated_module                              │
└────────┬─────────────────────────────────────┘
         │ N:1（项目级覆盖）
         ▼
┌─────────────────────────────────────────────┐
│ project_workpaper_sheet_override (新)        │
│ project_id / wp_code / sheet_name            │
│ class_override / scope_override              │
│ schema_override JSONB                         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────┐
│ workpaper_sheet_version_mapping (新) │ ← P1 跨版本迁移
│ from_version_id / to_version_id     │
│ from_wp_code / from_sheet_name      │
│ to_wp_code / to_sheet_name          │
│ field_mapping JSONB                  │
│ migration_strategy                   │
└─────────────────────────────────────┘

projects.template_version_id (新增列, 项目绑定模板版本)
working_paper.parsed_data['html_data'] (扩展 JSONB 字段)
working_paper.parsed_data['schema_version'] (扩展 JSONB 字段)
working_paper.parsed_data['univer_snapshot'] (既有，F/G 类继续用)
```

### 4.2 SQL DDL

```sql
-- ① 模板版本表（P0+P1）
CREATE TABLE workpaper_template_version (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version VARCHAR(20) NOT NULL UNIQUE,
  release_date DATE NOT NULL,
  source VARCHAR(50) NOT NULL DEFAULT '致同总所',
  is_current BOOLEAN NOT NULL DEFAULT FALSE,
  parent_version_id UUID REFERENCES workpaper_template_version(id) ON DELETE SET NULL,
  changelog TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT chk_only_one_current CHECK ((is_current = FALSE) OR (is_current = TRUE))
);
CREATE UNIQUE INDEX uq_workpaper_template_version_current
  ON workpaper_template_version (is_current) WHERE is_current = TRUE;

-- ② projects 表加列（项目绑定版本）
ALTER TABLE projects
  ADD COLUMN template_version_id UUID REFERENCES workpaper_template_version(id);
CREATE INDEX idx_projects_template_version_id ON projects(template_version_id);

-- ③ workpaper_sheet_classification 扩展（保留既有 wp_code/sheet_name/class_code）
ALTER TABLE workpaper_sheet_classification
  ADD COLUMN class VARCHAR(20),                        -- A-/B-/C-/D-/E-/F-/G-/H-/I- 子类（取代 class_code 别名）
  ADD COLUMN is_real_workpaper BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN exclude_from_archive BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN exclude_from_progress BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN is_static_doc BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN scope VARCHAR(20) NOT NULL DEFAULT 'standalone'
    CHECK (scope IN ('standalone', 'consolidated', 'parent_only', 'both')),
  ADD COLUMN delegated_module VARCHAR(50),
  ADD COLUMN template_version_id UUID REFERENCES workpaper_template_version(id),
  ADD COLUMN render_schema_path VARCHAR(255);          -- backend/data/wp_render_schema/{wp_code}.yaml

-- 索引：组件路由 + 项目过滤高频访问
CREATE INDEX idx_wpsc_class_scope ON workpaper_sheet_classification (class, scope);
CREATE INDEX idx_wpsc_template_version_real ON workpaper_sheet_classification
  (template_version_id, is_real_workpaper) WHERE is_real_workpaper = TRUE;
CREATE INDEX idx_wpsc_wp_code_version ON workpaper_sheet_classification
  (wp_code, template_version_id);

-- ④ 项目级覆盖表（自定义底稿/特殊归类）
CREATE TABLE project_workpaper_sheet_override (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  wp_code VARCHAR(50) NOT NULL,
  sheet_name VARCHAR(255) NOT NULL,
  class_override VARCHAR(20),
  scope_override VARCHAR(20),
  schema_override JSONB,                                -- 项目级 schema 覆盖（仅自定义底稿用）
  reason TEXT,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (project_id, wp_code, sheet_name)
);
CREATE INDEX idx_pwpso_project_wp ON project_workpaper_sheet_override (project_id, wp_code);

-- ⑤ 跨版本 sheet 映射表（P1）
CREATE TABLE workpaper_sheet_version_mapping (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_version_id UUID NOT NULL REFERENCES workpaper_template_version(id),
  to_version_id UUID NOT NULL REFERENCES workpaper_template_version(id),
  from_wp_code VARCHAR(50) NOT NULL,
  from_sheet_name VARCHAR(255) NOT NULL,
  to_wp_code VARCHAR(50),                              -- NULL = 删除
  to_sheet_name VARCHAR(255),
  field_mapping JSONB,                                 -- {"old_cell": "new_cell"}
  migration_strategy VARCHAR(50) NOT NULL
    CHECK (migration_strategy IN ('auto_map', 'user_confirm', 'fresh_start')),
  notes TEXT,
  UNIQUE (from_version_id, to_version_id, from_wp_code, from_sheet_name)
);

-- ⑥ working_paper.parsed_data JSONB 结构约定（无 schema 变化，扩展字段）
-- {
--   "univer_snapshot": {...},              ← F/G 类继续用（既有）
--   "html_data": {                          ← 新增（A/B/C/D/E 类用）
--     "<sheet_name>": {
--       "preparation_info": {...},
--       "rows": [...],
--       "sub_table_data": {...}
--     }
--   },
--   "schema_version": "v2025-R5",           ← 新增（数据迁移依据）
--   "changed_sheets_last_save": [...],     ← 既有（增量保存）
--   "last_modified_by": "uuid",             ← 既有
--   "last_modified_at": "ISO8601"           ← 既有
-- }
```

### 4.3 数据迁移策略（推荐 6.3 选项 A：渐进式）

```
阶段 1（P0，本 spec implementation 第 1 周）：
  - 新建项目自动绑定 template_version_id = current 版
  - 老项目 template_version_id = NULL（继续按原 Univer 渲染）
  - workpaper_sheet_classification 落 6 字段（已经实测 100% 单体归类）

阶段 2（P0+P1，第 2-4 周）：
  - HTML 组件 5 类（A → B → E → D → C）按优先级实施
  - 老项目可手动点"切换 HTML 渲染"（per-project 开关）
  - working_paper.parsed_data['html_data'] 为空时自动从 univer_snapshot 反向解析（P1）

阶段 3（P2 后置独立 spec）：
  - 模板版本上传 + auto_map/user_confirm/fresh_start 迁移
  - 跨年度数据延续 carry forward
```


---

## 五、API 端点设计

### 5.1 新增端点

#### 5.1.1 GET /api/workpapers/{wp_id}/render-config

获取底稿渲染 schema + 项目数据 + 跨底稿引用。

**Query**：`sheet_name?: string`（可选，仅返回单 sheet 数据）

**Response**：
```json
{
  "wp_id": "uuid",
  "wp_code": "D2",
  "project_id": "uuid",
  "scope": "standalone",
  "is_real_workpaper": true,
  "template_version": "v2025-R5",
  "sheets": [
    {
      "sheet_name": "应收账款实质性程序表D2A",
      "componentType": "a-program-console",
      "schema": { /* 来自 wp_render_schema/{wp_code}.yaml */ },
      "html_data": { /* 来自 working_paper.parsed_data['html_data'][sheet] */ },
      "cross_refs": [{"wp_code": "D2-1", "cell": "K15"}]
    }
  ]
}
```

**EARS**：
- IF wp_id 不存在 OR 用户无权限 THEN 返回 404 / 403
- IF scope = 'consolidated' OR 'parent_only' THEN 返回 redirect 提示，前端跳合并模块
- WHEN 项目 template_version_id IS NULL THEN 默认按 current version 返回 schema

#### 5.1.2 POST /api/workpapers/{wp_id}/save

保存 HTML 数据到 `parsed_data['html_data']`。

**Body**：
```json
{
  "sheet_name": "应收账款实质性程序表D2A",
  "html_data": { "rows": [...], "preparation_info": {...} },
  "schema_version": "v2025-R5",
  "changed_cells": ["B17", "I20"]
}
```

**Response**：
```json
{
  "saved_at": "ISO8601",
  "stale_impact": [
    {"target_wp_code": "A1", "target_sheet": "BS", "target_row": "BS-007"}
  ]
}
```

**EARS**：
- WHEN 保存成功 AND 存在 cross_wp_references 引用此 cell THEN 系统 SHALL 发布 SSE `cross_ref.updated`
- WHEN schema_version 与服务端 current 不一致 THEN 返回 409 + 提示用户升级
- IF html_data 校验失败（JSON Schema） THEN 返回 422 + 字段级错误

#### 5.1.3 POST /api/workpapers/{wp_id}/export-xlsx

导出 xlsx（致同模板填值）。

**Query**：`download?: boolean = true`（false 时仅返回 JSON 不附下载头）

**Response**：`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

**EARS**：
- WHEN 模板 xlsx 不存在 THEN 返回 500 + 提示"模板缺失"
- WHEN 用户数据不完整（必填字段为空） THEN 返回 422 + 字段清单
- 6000 并发场景：openpyxl 写入走 `asyncio.run_in_executor` + 队列限流

#### 5.1.4 GET /api/wp-classifications

查询 9 类归属（前端组件路由依据）。

**Query**：`wp_code?: string` / `project_id?: string` / `template_version_id?: string`

**Response**：返回符合条件的 classification 列表（含 scope / is_real_workpaper / class / delegated_module）

#### 5.1.5 GET /api/wp-template-versions

多版本管理（P0 仅查询当前版，P1 加上传/切换）。

**Endpoints**：
- `GET /api/wp-template-versions` 列出所有版本
- `GET /api/wp-template-versions/current` 获取 current
- `POST /api/wp-template-versions/upload` (P1 admin only) 上传新版

#### 5.1.6 GET /api/wp-index-resolve

`<GtIndexChip>` 解析校验。

**Query**：`ref: string` / `project_id: string`

**Response**：
```json
{
  "resolved": true,
  "ns": "wp",
  "layer": 3,
  "target": "D2-1",
  "exists": true,
  "is_trimmed": false,
  "preview": {"preparer": "张三", "status": "draft", "last_modified": "..."}
}
```

#### 5.1.7 GET /api/workpapers/trace

报表/附注溯源（GtTraceabilityDialog 用）。

**Query**：`source: 'report' | 'disclosure' | 'workpaper'` / `identifier: string` / `direction: 'upstream' | 'downstream'`

**Response**：返回上游单元格列表 / 下游引用列表

### 5.2 既有端点（复用 / 不动）

| 端点 | 用途 | 边界 |
|------|------|------|
| `/api/custom-query/wp-sheet-preview` | 跨 sheet 取值 | 复用，HTML 类引用 F/G 类时调用 |
| `/api/custom-query/wp-id-by-code` | wp_code → wp_id | 复用，GtIndexChip 跳转用 |
| `/api/projects/{pid}/workpapers/cross-ref` | 跨底稿引用 | 不动 |
| `/api/projects/{pid}/stale-impact` | 失效传播 | 不动 |
| `/api/projects/{pid}/procedure-trimming` | 项目级裁剪 | 不动，A 类中控台写回 ProcedureInstance |
| `/api/projects/{pid}/disclosure-notes` | 附注汇总 | 不动，C 类写时单向同步 |
| `/api/workpapers/{id}/univer-save` | Univer 保存 | 不动，F/G 类继续用 |


---

## 六、方案 C 技术细节（致同模板填值导出）

### 6.1 模板 xlsx 占位符 schema 格式（YAML）

每个 wp_code 对应一份 YAML schema，存于 `backend/data/wp_render_schema/{wp_code}.yaml`：

```yaml
# backend/data/wp_render_schema/D2A.yaml
wp_code: D2A
template_path: backend/wp_templates/D/D2 应收账款.xlsx
template_version: v2025-R5
applicable_standards: [soe_standalone, listed_standalone]    # scope 路由
sheets:
  应收账款实质性程序表D2A:
    component_type: a-program-console
    fixed_cells:                                              # 固定头部（自动填充）
      A1: '致同会计师事务所'
      H3: '${index_no}'                                       # 来自 wp_index.index_no
      H4: '${page_no}'
      A5: '${entity_name}'                                    # 来自 project.client_name
      A6: '${period_end}'                                     # 来自 project.period_end
    dynamic_table:                                            # 用户填写区
      start_row: 17
      end_row: dynamic                                         # 用户决定行数
      header_row: 16
      columns:
        A: { field: program_no, type: number }
        B: { field: program_desc, type: text, max_length: 1000 }
        C: { field: program_category, type: enum,
             enum: ['常规★', 'IPO 加项', '备选程序', '舞弊应对'] }
        D: { field: assertion.existence, type: boolean, render: 'checkmark' }
        E: { field: assertion.completeness, type: boolean, render: 'checkmark' }
        F: { field: assertion.rights, type: boolean, render: 'checkmark' }
        G: { field: assertion.accuracy, type: boolean, render: 'checkmark' }
        H: { field: assertion.presentation, type: boolean, render: 'checkmark' }
        I: { field: linked_workpapers, type: text, render: 'index_chip' }
        J: { field: trim_reason, type: text, conditional: status='not_applicable' }
    static_text:                                               # 不可改区
      rows: [5-13, 14-16]                                     # 表头 + 5 项认定标题
      footer_rows_after_dynamic: 3                             # 尾部签字行
    formulas:                                                  # 保留模板公式
      preserve: true
      cells: [K10:K30]                                         # 显式标注（防 schema 升级误删）
    merged_cells:
      preserve: true                                           # 完整保留 merged_ranges
    cross_refs:                                                # 跨底稿引用（既有 cross_wp_references.json 衍生）
      - source: D2-1
        cell: K15
        target_field: linked_value
```

### 6.2 openpyxl 写入策略（4 路径）

```python
# backend/app/services/wp_xlsx_export_service.py

def export_wp_xlsx(wp_id: UUID, db: AsyncSession) -> BytesIO:
    """
    导出 xlsx 主流程（4 路径写入策略）：
      1. fixed_cells: 写 schema 默认值（覆盖用户改动）
      2. dynamic_table: 写 html_data[sheet][rows] 按 columns 映射
      3. formulas: 跳过（保留原公式 → 用户打开 xlsx 自动重算）
      4. static_text + merged_cells: openpyxl 加载时已含，跳过
    """
    wp = await db.get(WorkPaper, wp_id)
    schema = load_render_schema(wp.wp_code, wp.project.template_version_id)

    # 加载致同模板（保留 styles + formulas + merged_cells）
    template_path = schema['template_path']
    wb = openpyxl.load_workbook(template_path, data_only=False, keep_vba=False)

    html_data = wp.parsed_data.get('html_data', {})

    for sheet_name, sheet_schema in schema['sheets'].items():
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        sheet_data = html_data.get(sheet_name, {})

        # 路径 1: fixed_cells
        for cell_ref, value_template in sheet_schema.get('fixed_cells', {}).items():
            ws[cell_ref] = render_template_var(value_template, wp.project, wp)

        # 路径 2: dynamic_table
        if 'dynamic_table' in sheet_schema:
            write_dynamic_table(
                ws,
                sheet_schema['dynamic_table'],
                sheet_data.get('rows', []),
            )

        # 路径 3 + 4: formulas / static_text / merged_cells 跳过

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def write_dynamic_table(ws, table_schema, rows):
    """写入动态表格区域（保留公式列）"""
    start_row = table_schema['start_row']
    columns = table_schema['columns']

    for i, row_data in enumerate(rows):
        excel_row = start_row + i
        for col_letter, col_def in columns.items():
            cell = ws[f'{col_letter}{excel_row}']
            # 公式列跳过（保留原 formulas: preserve）
            if cell.value and isinstance(cell.value, str) and cell.value.startswith('='):
                continue
            field_path = col_def['field']
            value = get_nested(row_data, field_path)
            # 类型转换
            if col_def.get('render') == 'checkmark':
                cell.value = '√' if value else ''
            elif col_def.get('type') == 'enum':
                cell.value = value
            elif col_def.get('type') == 'number':
                cell.value = float(value) if value else None
            else:
                cell.value = value
```

### 6.3 字符级 diff 测试方案

```python
# backend/tests/exports/test_xlsx_diff.py

@pytest.mark.parametrize('wp_code,sample_sheet', [
    ('D2A', '应收账款实质性程序表D2A'),
    ('D2', '底稿目录'),
    ('D2', '附注披露信息'),
    ('C12', '控制测试汇总表'),
    # ... 9 个循环各 1 个底稿样本
])
def test_export_xlsx_char_level_diff(wp_code, sample_sheet, sample_html_data, tmp_path):
    """
    导出 xlsx 与"用户在原模板手填"的 xlsx 字符级 diff = 0（除用户填写位置）
    """
    # 1. 导出 HTML 渲染版本
    exported_xlsx = export_wp_xlsx_for_test(wp_code, sample_html_data)

    # 2. 加载致同原模板，按 sample_html_data 手填同样数据（fixture）
    expected_xlsx = manually_fill_template(wp_code, sample_html_data)

    # 3. 字符级 diff（不含格式，仅 cell 值 + merged_cells + formula）
    diff = compare_xlsx_cells(exported_xlsx, expected_xlsx)
    assert diff.value_diffs == [], f'Cell value diffs: {diff.value_diffs}'
    assert diff.formula_diffs == [], f'Formula diffs: {diff.formula_diffs}'
    assert diff.merged_diffs == [], f'Merged range diffs: {diff.merged_diffs}'
```

**diff 工具实现**：
```python
def compare_xlsx_cells(a: BytesIO, b: BytesIO) -> XlsxDiff:
    wb_a = openpyxl.load_workbook(a, data_only=False)
    wb_b = openpyxl.load_workbook(b, data_only=False)
    diffs = XlsxDiff()
    for sheet_name in set(wb_a.sheetnames) & set(wb_b.sheetnames):
        ws_a, ws_b = wb_a[sheet_name], wb_b[sheet_name]
        # cell 值 + 公式
        for row in ws_a.iter_rows():
            for cell_a in row:
                cell_b = ws_b.cell(cell_a.row, cell_a.column)
                if cell_a.value != cell_b.value:
                    diffs.value_diffs.append((sheet_name, cell_a.coordinate, cell_a.value, cell_b.value))
        # merged_cells
        if set(map(str, ws_a.merged_cells.ranges)) != set(map(str, ws_b.merged_cells.ranges)):
            diffs.merged_diffs.append(sheet_name)
    return diffs
```

### 6.4 复合写入策略（4 类 cell）

| Cell 类型 | 写入策略 | 示例 |
|----------|---------|------|
| **fixed_cells** | 强制写 schema 默认值（覆盖用户改动） | A1='致同会计师事务所' / H3=index_no |
| **dynamic_table** | 按 schema field 映射写入 | B17 = rows[0].program_desc |
| **formula_cells** | 跳过（保留公式字符串） | K10='=H10+I10+J10'（用户打开重算）|
| **note_cells** | 原样保留（"勿删勿改"区 + 财政部引用） | 静态长文本说明 |


---

## 七、正确性属性（Correctness Properties）

> *A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### 7.1 Property Reflection（消除冗余）

经审查，初版 16 条候选属性可合并优化：

- **R1.1 + R1.2 合并** → 9 类全覆盖归类自动派生 componentType 路由，两者是同一规则的两面（归类 → 组件）
- **R3.1 + R3.2 合并** → cross-ref 事件触发与 affected 列表是同一传播链路的两端
- **R5.1 + R5.2 合并** → 11 命名空间解析与 4 层跳转语义同属 parseIndexRef 输出
- **R4.1 + R4.2 合并** → 真假底稿标记与完成率口径是 is_real_workpaper 派生关系
- **R6.1 + R6.2 合并** → 项目级覆盖与 scope 路由都是 render-config 合并函数的输入

经合并后保留 **9 条核心属性**：

### 7.2 Property 1：9 类全覆盖归类 → componentType 路由

*For any* (sheet_name, sheet_features) 组合，`classify_sheet()` SHALL 返回 9 类之一（A-/B-/C-/D-/E-/F-/G-/H-/I-）且 `render_config_service.derive_component_type()` SHALL 把每个类映射到 componentType 白名单 {a-program-console, b-index, c-note-table, d-form-table, d-form-paragraph, d-form-qa, d-form-confirmation, d-form-review, e-control-test, h-static-doc, univer, skip} 中的一个，绝不返回 undefined / null / 'fallback'。

**Validates: Requirements 1.2（9 类全覆盖）+ 3.0.1（100% 自动归类）+ 3.9（决策树禁止 Univer 兜底）**

### 7.3 Property 2：方案 C 字符级还原（导出 xlsx ≡ 致同模板手填）

*For any* (wp_code, html_data) 合法组合，`export_wp_xlsx(wp_code, html_data)` 输出的 xlsx 与"在原致同模板上手填同样数据"的 xlsx 在 cell value、formula 字符串、merged_cells 集合三个维度上字符级 diff 为空集（除用户填写位置标记差异）。

**Validates: Requirements 4.3.1.a-g（方案 C 还原 7 项约束）+ 5.3（字符级 diff 测试要求）**

### 7.4 Property 3：公式与合并单元格保留不变量

*For any* 模板 xlsx 加载后的 (formula_cells, merged_ranges) 集合，导出 xlsx 重新加载后的对应集合 SHALL 与之恒等（即 export 是公式与合并区的恒等映射）。

**Validates: Requirements 4.3.1.b（公式保留）+ 4.3.1.c（合并单元格保留）**

### 7.5 Property 4：跨底稿引用传播

*For any* (source_wp_code, source_cell, value_change) 修改，IF 该 cell 在 `cross_wp_references` 中存在引用记录 THEN 系统 SHALL 发布 SSE `cross_ref.updated` 且 `stale-impact` API 返回的 affected 列表 SHALL 包含所有 (target_wp_code) 满足 `(source=source_wp_code.cell, target=target_wp_code)` 在引用表中的记录。

**Validates: Requirements 3.11.4 ★★★ 强联动 + 3.11.5 联动 4 层架构 + 3.11.6 报表附注溯源链路**

### 7.6 Property 5：真假底稿与完成率派生

*For any* sheet（含 sheet_name + classification 字段），`is_real_workpaper` 由 sheet_name 关键词与 class 决定性映射（即同样输入永远产出同样标记），且项目完成率公式 `progress = COUNT(real AND completed) / COUNT(real)` 严格不含 `is_real_workpaper=FALSE` 的 sheet。

**Validates: Requirements 3.0.2（真假底稿铁律）+ 完成率口径不含假底稿**

### 7.7 Property 6：跨底稿索引解析与跳转语义

*For any* 文本 ref（合法或非法），`parseIndexRef(ref)` SHALL 对合法输入返回结构化对象 {ns, layer, target}，对非法输入返回 null；且 layer 字段由 ns 决定性派生（cell→1, sheet→2, wp→3, Note/TB/Adj/Att/EQCR/Calc/Sample/Confirm→4），9 种边缘 case（中文/空格/大小写/多目标/不存在/被裁剪/跨项目/GT_Custom/空 sheet）都有确定行为。

**Validates: Requirements 3.11.8（跨底稿索引号 4 级语义）+ 3.11.9（11 命名空间路由表）+ 3.11.10（9 边缘 case）**

### 7.8 Property 7：项目实例覆盖与 scope 路由

*For any* (project_id, wp_code, sheet_name) 三元组，render-config 返回的 componentType SHALL 按 `(project_workpaper_sheet_override.class_override IS NOT NULL ? override : workpaper_sheet_classification.class)` 顺序合并；且 IF `scope='consolidated'` THEN componentType='delegate-consolidation'，IF `scope='parent_only'` THEN componentType='delegate-parent-view'，IF `scope IN ('standalone', 'both')` THEN 走本 spec 9 类路由。

**Validates: Requirements 3.0.3（项目实例层级 L5）+ 3.0.5（合并/母公司剔除 scope 字段路由规则）**

### 7.9 Property 8：附注双源单向同步

*For any* C 类 sheet 保存事件，系统 SHALL 触发 `disclosure_notes` 模块对应 section 的 push 更新；且对 `disclosure_notes` 模块的编辑事件 SHALL 不反向写回 C 类 sheet（同步方向严格单向）。

**Validates: Requirements 3.11.5 §4.2（附注双源问题）+ 6.2 待决策点 1 选项 A 推荐**

### 7.10 Property 9：行业特定 sheet 可见性派生

*For any* (project.industry_type, sheet_industry_tag) 组合，sheet 可见性 SHALL 由 `visibility = (sheet_industry_tag IS NULL) OR (sheet_industry_tag = project.industry_type)` 决定性派生（H5 油气仅在 industry_type='oil_gas' 时可见 / H7 生物资产仅在 'agriculture' / M7 专项储备仅在 'soe' template_type）。

**Validates: Requirements 6.5 待决策点 4 选项 A（按 industry_type 自动启用）**


---

## 八、错误处理（Error Handling）

### 8.1 错误分类与统一响应

| 错误类型 | HTTP 码 | 前端处理 |
|---------|--------|---------|
| 底稿不存在 | 404 | useWpDetailGuard → GtError overlay "底稿不存在" + 返回列表按钮 |
| 无项目权限 | 403 | overlay "无权访问" + 联系管理员 |
| schema 缺失（wp_code 没对应 YAML） | 500 | overlay "模板配置缺失：${wp_code}" + 上报运维 |
| 数据校验失败（保存时） | 422 | 字段级红边框 + ElMessage 列出所有错误 |
| 版本冲突（schema_version 不一致） | 409 | confirmVersionConflict 弹窗：升级 / 强制保存 / 取消 |
| 模板 xlsx 文件缺失（导出时） | 500 | "致同模板缺失：${path}" + 不重试 |
| 必填字段为空（导出时） | 422 | 列出所有空字段 + 跳转到第一个空字段 |
| openpyxl 写入失败 | 500 | 重试 1 次 + 失败上报 |
| LibreOffice 服务降级 | 503 | 静默降级（参考既有 useStaleImpact 503 处理） |
| pending 归类（理论不应发生） | 500 | 上报告警，绝不 fallback Univer |

### 8.2 关键边界处理

#### 8.2.1 setup ref 顺序铁律（避免 Cannot access X before initialization）

GtWpRenderer / 各子组件 `<script setup>` 中：
- 业务 ref（wpDetail / loading / htmlData）必须在最顶部定义
- composable 调用 useWpRenderer / useWpClassification 之后
- computed 必须在所有依赖 ref 之后

参考 conventions 中"Vue setup const 声明顺序铁律"（commit 065c91e 真因修复教训）。

#### 8.2.2 顶层 v-if 守卫拦 init 死锁

任何依赖 template ref 挂载触发 init 的子组件（如 Univer 编辑器）SHALL 不在顶层加 `v-if="loading"` 守卫。`<UniverHost>` 内部用 `v-if="!isUniver" / overlay 模式` 避免死锁。

#### 8.2.3 useWpDetailGuard 三态接入铁律

GtWpRenderer SHALL 调用 `useWpDetailGuard(wpId)` 获取 (loading / error / ready) 三态，错误情况下用 GtError overlay 展示，**不允许 router.push 强制跳转**。

#### 8.2.4 cross-ref:updated 订阅清理

任何订阅 cross-ref:updated 的 composable 必须在 onUnmounted 时 off 监听器（避免内存泄漏）。

### 8.3 数据降级策略

| 场景 | 降级 |
|------|------|
| html_data 为空（项目首次打开） | 从 univer_snapshot 反向解析为 html_data（P1） |
| schema YAML 缺失 | 显式报错（不 fallback 到 Univer） |
| cross_wp_references 引用目标不存在 | GtIndexChip 灰显 + tooltip |
| 公式重算失败（Excel 打开后） | 用户触发，不在系统范围 |
| Stale 引擎 503 | 静默不阻断保存（既有 useStaleImpact 实现） |
| openpyxl 内存溢出（大底稿） | 走 asyncio.run_in_executor + 队列限流 |

---

## 九、测试策略（Testing Strategy）

### 9.1 双轨测试

- **单元测试**：覆盖具体例子、边界 case、错误条件
- **属性测试（PBT）**：覆盖 §7 9 条核心属性的全输入空间

### 9.2 PBT 配置

- 库选择：`hypothesis`（Python 后端，已有大量先例）+ `fast-check`（前端 vitest）
- 每个 property test 最少 100 iterations（hypothesis 默认 max_examples=100）
- 慢生成器加 `@settings(suppress_health_check=[HealthCheck.too_slow])`
- 标签格式：注释 `# Feature: workpaper-html-renderer, Property N: <title>`

### 9.3 9 条属性的测试映射

| Property | 测试位置 | 关键策略 |
|----------|---------|---------|
| P1 9 类全覆盖 | `backend/tests/properties/test_classification_coverage.py` | hypothesis 生成 sheet_name + features → 断言 class ∈ 白名单 |
| P2 字符级还原 | `backend/tests/exports/test_xlsx_diff.py` | hypothesis 生成 html_data → 对比导出 vs fixture |
| P3 公式合并不变量 | `backend/tests/exports/test_invariants.py` | 加载模板 → 导出 → 重载 → 比对集合 |
| P4 跨底稿引用传播 | `backend/tests/properties/test_cross_ref_propagation.py` | 生成 (wp, cell) 修改 → 断言 SSE + affected |
| P5 真假底稿派生 | `backend/tests/properties/test_real_workpaper.py` | hypothesis sheet_name → is_real_workpaper |
| P6 索引解析 | `audit-platform/frontend/src/utils/__tests__/parseIndexRef.test.ts` | fast-check 生成 ref 字符串 |
| P7 覆盖 + scope | `backend/tests/properties/test_render_config_merge.py` | 生成 override + base → 合并函数确定性 |
| P8 附注单向同步 | `backend/tests/integration/test_disclosure_sync.py` | C sheet 保存 → 断言 disclosure_notes 更新 |
| P9 行业可见性 | `backend/tests/properties/test_industry_visibility.py` | hypothesis (industry_type, tag) 组合 |

### 9.4 单元测试要点

- A 类组件：程序裁剪决策写回 ProcedureInstance.status='not_applicable' 测试
- B 类组件：编制信息自动填充测试（project meta 缺失时友好降级）
- C 类组件：上市 ↔ 国企版本切换时共有字段保留 / 差异字段 ElMessageBox 提示
- D 类组件：5 子模式分发测试 + 业务模式判定（D2-13）输出测试
- E 类组件：6 步骤决策树 stepper 校验测试 + 4 互斥结论测试
- 导出 xlsx：9 个循环各 1 个底稿样本（D2A / D2 目录 / D2 附注 / C12 / B 目录 / A1 / E1 / F2 / G7）
- GtIndexChip：11 命名空间 × 9 边缘 case = 99 组合测试
- 跨版本兼容：v2025-R5 数据在 v2026-R1 schema 下加载（P1 后置）

### 9.5 集成测试

- 9 类组件 + 真实 backend/wp_templates 模板 + 4 项目实测数据（已有：陕西华氏 / 和平药房 / 辽宁卫生 / 宜宾大药房）
- Playwright e2e：A 中控台批量裁剪 → 写回 ProcedureInstance → 重新打开 chain_orchestrator 跳过测试
- Playwright e2e：C 附注披露子表合计变化 → 主表行实时更新 → 导出 xlsx → 公式重算正确

### 9.6 性能基准

- HTML 渲染冷启动 ≤ 500ms（D2 18 sheet 整套）
- 导出 xlsx ≤ 5s（含模板加载 + openpyxl 写入）
- 6000 并发场景：openpyxl 走 asyncio.run_in_executor + 信号量 ≤ 10 并发

---

## 十、风险评估

### 10.1 高风险

| # | 风险 | 影响 | 缓解 |
|---|------|------|------|
| H1 | schema YAML 维护成本（每个 wp_code 一份 + 致同每年修订） | 工作量 5x | 优先 A → B → E → D → C 5 类，F/G 不动；自动化提取工具（从模板 xlsx 反向解析 schema 草稿）|
| H2 | 字符级 diff = 0 难度高（致同模板含大量隐藏样式 / 默认值） | 测试难达标 | 9 个样本起步，逐个验证，发现问题反馈给 schema |
| H3 | C 类上市/国企双版本切换数据丢失 | 用户失数据 | 共有字段自动迁移 + 差异字段 ElMessageBox 提示 + 备份到 working_paper.parsed_data['html_data_backup_${standard}'] |
| H4 | cross-ref 传播性能（400 条引用 × 6000 并发） | 可能压垮服务 | 既有 useStaleImpact 已有 503 降级 + Redis 缓存 |

### 10.2 中风险

| # | 风险 | 缓解 |
|---|------|------|
| M1 | 项目实例覆盖优先级冲突 | 单元测试覆盖合并函数确定性（Property 7） |
| M2 | 9 类组件代码量大（5 类 × 各 200-500 行） | Storybook 8.6.14 已有，组件级隔离开发 |
| M3 | scope='consolidated' 路由跳转时数据闪烁 | 提前在 useWpClassification 判定，路由前置 |
| M4 | 自定义底稿（用户上传 xlsx）归类失败 | 复用 analyze_wp_templates.py 60+ 条规则 + 落 _pending 标记通知运维 |

### 10.3 低风险

| # | 风险 | 缓解 |
|---|------|------|
| L1 | LibreOffice 服务降级 | 503 静默不阻断（既有） |
| L2 | 模板版本号冲突（同一项目误升级） | UNIQUE constraint + `is_current` 唯一约束 |
| L3 | parseIndexRef 误识别（如文本中含 D2 但不是引用） | 严格模式优先 + 宽松模式只识别独立 token |

---

## 十一、不变量清单

| # | 不变量 | 触发点 | 校验位置 |
|---|-------|--------|---------|
| I1 | 单体范围 100% 自动归类（pending = 0） | 模板上传时 | analyze_wp_templates.py + CI |
| I2 | 完成率分母不含 is_real_workpaper=FALSE | Dashboard 进度计算 | progress_service |
| I3 | 公式 cell 导出后仍为 '=...' 字符串 | export_xlsx | wp_xlsx_export_service + Property 3 |
| I4 | merged_ranges 集合在导出前后恒等 | export_xlsx | 同上 |
| I5 | scope='consolidated' 不进入本 spec 9 类组件 | 渲染路由 | useWpClassification + Property 7 |
| I6 | cross_wp_references 中 source 与 target 都属同一 project_id | 跨底稿引用 | cross_ref_service |
| I7 | schema_version 与 template_version_id 一一对应 | render-config | 数据库约束 |
| I8 | 项目级覆盖记录每条 wp_code+sheet_name 在同 project_id 内唯一 | 数据库约束 | UNIQUE (project_id, wp_code, sheet_name) |
| I9 | 任何 SSE cross_ref.updated 必有对应的 cross_wp_references 记录 | cross_ref_service.notify | 单元测试 |
| I10 | 11 命名空间 ns 与 layer 一一对应（不会混淆） | parseIndexRef | Property 6 |


---

## 十二、5 个待决策点的设计推荐

> 对应 requirements.md §6.2~6.6 的 5 个 P0 待决策点。本节给出 design 阶段的明确推荐方案。

### 12.1 待决策点 1：附注双源统一方向 → **推荐选项 A：底稿 → 模块单向同步**

**EARS**：
- WHEN 用户在 C 类 sheet 保存附注披露数据 THEN 系统 SHALL 自动 push 到 disclosure_notes 模块对应 section
- WHEN disclosure_notes 模块直接编辑（已有独立编辑器）THEN 系统 SHALL 仅更新 disclosure_notes 表，不反向写回 C 类 sheet

**实施**：
- C 类 GtCNoteTable.vue 保存触发 `POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper`
- payload: `{ wp_code, sheet_name, section_id, fields }`
- disclosure_notes 模块继续保留独立编辑器（向后兼容）但加 banner 提示"此数据由底稿同步，建议在底稿编辑"

**理由**：底稿是审计员主要工作面，编辑频率高于 disclosure_notes 模块；单向同步避免循环引用与冲突解决复杂度。

### 12.2 待决策点 2：现有数据迁移策略 → **推荐选项 A：渐进式**

**EARS**：
- WHEN 项目首次开启 HTML 渲染 THEN 系统 SHALL 从 working_paper.parsed_data['univer_snapshot'] 反向解析为 html_data（P1 实施）
- WHEN 项目尚未开启 HTML 渲染 THEN 系统 SHALL 继续按 Univer 渲染（向后兼容）
- WHEN 老项目主动切换 HTML THEN 用户在 ProjectConfig 页面点击"切换 HTML 渲染"按钮，系统在后台跑反向解析

**实施**：
- projects 表加列 `enable_html_renderer BOOLEAN DEFAULT FALSE`（仅当 template_version_id 为 v2025-R5+ 时可启用）
- 反向解析 `univer_snapshot → html_data` 工具：`backend/scripts/migrate_univer_to_html.py`
- 失败时保留 univer_snapshot + 标记 `parsed_data['migration_status']='failed'` 通知运维

**理由**：避免一刀切冲击老项目，给用户选择权；反向解析复杂度可控（schema 已知）。

### 12.3 待决策点 3：9 组重复主底稿合并 → **推荐选项 A：迁移时合并**

**EARS**：
- WHEN 项目升级到 v2026-R1 THEN 系统 SHALL 把 G1↔G7 / G5↔G8 / G6↔G9 / H3↔H8 / H9↔L4 / L8↔K3 / N3↔N5 / N4↔K5 / M5↔M9 共 9 组合并为单一主底稿
- WHEN 老项目沿用 v2025-R5 THEN 重复入口保留双源 + cross-ref 强同步（不合并，避免历史数据风险）

**实施**：
- workpaper_sheet_version_mapping 表预定义 9 组合并规则（migration_strategy='auto_map'）
- 合并后保留 wp_code 历史别名（用户搜索旧码自动跳新主底稿）
- 数据迁移脚本 `backend/scripts/merge_duplicate_wp.py`（dry-run 默认）

**理由**：合并是长期价值（避免用户混淆与维护成本），老项目沿用旧版避免数据风险。

### 12.4 待决策点 4：行业特定底稿启用 → **推荐选项 A：按 industry_type 自动**

**EARS**：
- WHEN project.industry_type IN ('oil_gas', 'agriculture', 'soe', 'finance') THEN 系统 SHALL 按 sheet_industry_tag 自动启用对应底稿
- WHEN industry_type 未设置（NULL）THEN 系统 SHALL 不启用任何行业特定底稿（默认隐藏）

**实施**：
- workpaper_sheet_classification 加列 `industry_tag VARCHAR(50)`（'oil_gas' / 'agriculture' / 'soe' / 'finance' / 'all'）
- projects 加列 `industry_type VARCHAR(50)`（首次立项必填，可后续修改）
- 渲染层 useWpClassification 计算 visibility = (industry_tag IS NULL OR industry_tag = 'all' OR industry_tag = project.industry_type)

**理由**：自动启用减轻用户配置负担；industry_type 是项目立项必填，已是单一权威源。

### 12.5 待决策点 5：跨年度数据延续 → **推荐选项 A：仅落表结构**

**EARS**：
- WHEN 本 spec implementation 第 1-4 周 THEN 系统 SHALL 仅落表结构（workpaper_template_version 表 + projects.template_version_id 列）
- WHEN P2/P3 后置独立 spec THEN 实施 UI 流程（"沿用旧版/升级数据迁移"+ 跨年度 carry forward）

**实施**：
- 本 spec 内：表结构 + 新建项目自动绑定 current 版 + 老项目 NULL（继续 Univer）
- 不做 UI：模板上传 / 数据迁移 / carry forward 全部后置

**理由**：避免本 spec 范围爆炸；表结构先落地为后续独立 spec 留接口；P0+P1 范围内可控。

---

## 十三、章节交叉引用速查表

| Design 章节 | 对应 Requirements 章节 |
|------------|----------------------|
| §1 Overview | requirements §一、§二（用户偏好与设计原则） |
| §2 Architecture | requirements §一（D2A 痛点） + §3.0（用户主流程视图） |
| §3 Components | requirements §3.2~3.7（A~I 9 类） + §3.10（按循环逐一分析） |
| §3.8 GtIndexChip + §3.9 Traceability | requirements §3.11.8~3.11.10（4 层级跳转 + 11 命名空间 + 9 边缘 case） |
| §3.11 联动机制 | requirements §3.11.0~3.11.7（4 层级架构 + 47 联动场景速查表） |
| §4 Data Models | requirements §3.0.2~3.0.5（真假底稿 + L5 实例 + 模板版本 + 合并剔除） |
| §5 API | requirements §三、§4.4 关键技术依赖 |
| §6 方案 C 技术细节 | requirements §4.3 方案 C + §4.3.1 还原 7 项约束 |
| §7 Correctness Properties | requirements 全篇 EARS 决策（合并归 9 条核心） |
| §10 风险评估 | requirements §五、§5.3 测试要求 |
| §12 5 待决策点 | requirements §6.2~6.6 |

---

## 十四、实施优先级（与 requirements §8 一致）

```
Week 1-2：P0 数据模型
  ├─ workpaper_sheet_classification 扩展 6 字段（已有数据）
  ├─ workpaper_template_version 表 + projects.template_version_id 列
  ├─ project_workpaper_sheet_override 表
  └─ /api/wp-classifications + /api/workpapers/{id}/render-config 端点

Week 3-4：A 程序表中控台（261 sheet，最高用户价值）
  ├─ wp_render_schema YAML（A 类样本：D2A / G7A / E1A）
  ├─ GtAProgramConsole.vue + 程序裁剪写回 ProcedureInstance
  ├─ GtIndexChip.vue + 11 命名空间 + 9 边缘 case
  └─ 导出 xlsx 字符级 diff = 0 测试（Property 2/3）

Week 5：B 底稿目录（148 sheet，相对简单）
  └─ GtBIndex.vue + 编制信息自动填充 + 索引导航

Week 6-7：E 控制测试（322 sheet，复杂度中）
  ├─ GtEControlTest.vue + 6 步骤 stepper
  └─ ProcedureTrimming 联动建议

Week 8-10：D 检查表（449 sheet，5 子模式）
  ├─ GtDForm 5 子组件
  └─ 函证/盘点/访谈专属子组件

Week 11-13：C 附注披露（166 sheet，最复杂）
  ├─ GtCNoteTable.vue + 上市/国企版本切换
  ├─ 附注双源单向同步（disclosure_notes push）
  └─ 子表合计 ↔ 主表行实时联动

Week 14：F/G 不动（558 sheet 保留 Univer，仅扩展 cross-ref:updated 订阅）

Week 15：H 静态展示 + I 跳过 + 最终联调
```

**关键里程碑**：
- M1（Week 4）：A 程序表 + 导出 xlsx 字符级 diff 通过（核心还原能力验证）
- M2（Week 10）：A+B+E+D 4 类完成（主流程闭环）
- M3（Week 13）：C 类完成 + 附注双源统一（业务核心）
- M4（Week 15）：全 9 类联调 + 性能基准达标（HTML < 500ms / 导出 < 5s）

---

## 十五、附录

### 15.1 复用现有模块明确边界

| 模块 | 边界 |
|------|------|
| ProcedureTrimming | **复用**（项目级裁剪，A 中控台决策写回 ProcedureInstance.status） |
| chain_orchestrator 步骤 5b/5c | **复用**（不动主流程，仅扩展状态写回） |
| cross-ref:updated eventBus | **复用**（既有 D 循环已验证，A~E 类全部接入） |
| useStaleImpact | **复用**（既有 composable，503 降级已实现） |
| useCycleDialogs / useSheetNavFacade | **复用**（11 nav 路由 + 18 弹窗，HTML 类继续用） |
| useEditorActions | **复用**（保存/取消/版本冲突弹窗等） |
| report_line_mapping | **复用**（4 套维度 × 143 条，A 类报表行溯源依赖） |
| disclosure_notes | **复用 + 扩展**（C 类底稿单向 push，模块层加 banner 提示） |
| workpaper_attachment + AttachmentTabPanel | **复用**（HTML 类右栏附件 Tab） |
| LibreOffice + python-docx + openpyxl | **复用**（导出 xlsx + PDF 归档链路不变） |
| Univer Sheets | **复用**（F/G 类 558 sheet 保留，HTML 类不引入 Univer） |
| ConsolidationHub / ConsolWorksheetTabs | **复用**（合并/母公司专属 450 sheet 委派给独立模块，本 spec 不动） |
| EQCR Workbench | **复用**（双向引用接口 P1 后置） |
| analyze_wp_templates.py | **复用**（60+ 条归类规则 + 单体 100% 归类，自定义底稿走运行时归类） |
| univer_snapshot_helper.py | **复用**（既有 slim 工具 + 增量 + 体积保护） |
| `query_workpaper` API（既有） | **复用**（HTML 类引用 F/G 类时调用） |

### 15.2 关键文件清单（本 spec 新增）

```
backend/
├── app/
│   ├── routers/
│   │   ├── wp_render_config.py            (新)
│   │   ├── wp_classification.py           (新)
│   │   └── wp_template_version.py         (新)
│   ├── services/
│   │   ├── wp_render_schema_service.py    (新)
│   │   ├── wp_xlsx_export_service.py      (新)
│   │   ├── wp_template_version_service.py (新)
│   │   └── wp_classification_service.py   (扩展既有)
│   └── models/
│       ├── workpaper_models.py            (扩展：6 字段)
│       ├── workpaper_template_version.py  (新)
│       └── project_wp_sheet_override.py   (新)
├── data/
│   └── wp_render_schema/                  (新目录，每 wp_code 一份 YAML)
│       ├── D2A.yaml
│       ├── D2.yaml
│       ├── B-template.yaml                (B 类共享模板)
│       └── ...
├── scripts/
│   ├── analyze_wp_templates.py            (既有，复用)
│   ├── generate_wp_render_schema.py       (新：模板 xlsx → schema 草稿)
│   └── migrate_univer_to_html.py          (新：P1 渐进迁移)
├── tests/
│   ├── exports/test_xlsx_diff.py          (新：Property 2)
│   ├── exports/test_invariants.py         (新：Property 3)
│   └── properties/                        (新目录，9 PBT 测试)
└── alembic/versions/
    └── add_wp_html_renderer_tables.py     (新)

audit-platform/frontend/
├── src/
│   ├── components/
│   │   ├── workpaper/
│   │   │   ├── GtWpRenderer.vue           (新)
│   │   │   ├── GtAProgramConsole.vue      (新)
│   │   │   ├── GtBIndex.vue               (新)
│   │   │   ├── GtCNoteTable.vue           (新)
│   │   │   ├── GtDForm/                   (新目录，5 子组件)
│   │   │   │   ├── GtDFormTable.vue
│   │   │   │   ├── GtDFormParagraph.vue
│   │   │   │   ├── GtDFormQA.vue
│   │   │   │   ├── GtDFormConfirmation.vue
│   │   │   │   └── GtDFormReview.vue
│   │   │   ├── GtEControlTest.vue         (新)
│   │   │   ├── GtHStaticDoc.vue           (新)
│   │   │   ├── GtIndexChip.vue            (新)
│   │   │   ├── GtTraceabilityDialog.vue   (新)
│   │   │   ├── GtAttachmentChip.vue       (新)
│   │   │   └── GtFormulaPopover.vue       (新)
│   ├── composables/
│   │   ├── useWpRenderer.ts               (新)
│   │   ├── useWpClassification.ts         (新)
│   │   └── useWpRenderSchema.ts           (新)
│   ├── utils/
│   │   └── parseIndexRef.ts               (新：11 命名空间 + 9 边缘 case)
│   └── views/
│       └── WorkpaperEditor.vue            (扩展：按 componentType 分发到 GtWpRenderer)
└── tests/
    ├── unit/parseIndexRef.test.ts         (新：Property 6)
    └── e2e/wp-html-renderer.spec.ts       (新：5 类组件 e2e)
```

### 15.3 与既有 spec / commit 的衔接

| 既有产物 | 衔接方式 |
|---------|---------|
| commit `ff7f20d`（univer_snapshot 落 JSONB） | F/G 类继续用，HTML 类扩展 `parsed_data['html_data']` |
| commit `065c91e`（WorkpaperEditor 真因修复） | 经验沉淀：setup const 顺序铁律 + Playwright 实测 |
| commit `da36de1`（report_line_mapping 4 套维度） | A 类报表行溯源直接复用 |
| spec `advanced-query-enhancements-p1p2`（212 tests） | 跨 sheet 查询 / 公式 popover / 选区记忆复用 |
| spec `procedure-trimming` | A 中控台决策写回 ProcedureInstance |
| spec `audit-chain-generation`（chain_orchestrator） | 步骤 5b/5c 已尊重裁剪，HTML 类决策同样写回 |

### 15.4 后续独立 spec（不在本 spec 范围）

- `workpaper-template-version-management`（P2：模板上传 + 自动归类 + auto_map/user_confirm/fresh_start 迁移）
- `workpaper-cross-year-continuity`（P3：跨年度数据延续 + carry forward UI）
- `workpaper-eqcr-bidirectional-link`（P1：EQCR 抽查记录 ↔ 底稿双向引用）
- `audit-report-traceability`（独立：审计报告关键句 → 底稿证据链）

---

**Design 完成 ✅**

> 800-1200 行设计文档，覆盖：整体架构 / 9 类组件 / 方案 C 还原 / 数据模型 / API / 联动 4 层 / PBT 9 属性 / 风险 / 不变量 / 5 待决策点。
> 下一步：用户审阅 → 进入 tasks 阶段。
