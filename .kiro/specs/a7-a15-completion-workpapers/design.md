# A7–A15 完成阶段底稿 — 设计文档

## 前置依赖

> **权威定义**：[completion-phase-infra](../completion-phase-infra/requirements.md)。  
> 联动矩阵：[linkage.md](../completion-phase-infra/linkage.md)。

实施顺序见 [linkage.md §全局实施顺序](../completion-phase-infra/linkage.md#全局实施顺序)。A13 / A14 见 [子 spec](../a13-misstatement-workpaper/requirements.md)。

---

## 架构总览

红框 **26 物理文件**按 6 种模式处理：

| 模式 | 底稿 | componentType | 格式 |
|------|------|---------------|------|
| 程序表 | A7–A15（9×） | a-program-console | xlsx→HTML（不解析 live xlsx） |
| 弹窗 | A8-1/2, A9-1/2, A10-1, A11-1, A12-1 | WpPopupDocxEditor | 信函型 docx |
| 核对表 | A11-2/3, A14-1, A15-1 | checklist-table | xlsx→HTML |
| 表单 | A10-2, A13-2~5, A14-2~5, A11-WP-1 | d-form-table / d-form-confirmation | xlsx→HTML |
| 专用 | A13-1, A7-2, A14-6 | misstatement-summary / c-note-table / e-control-test | 结构化 HTML |
| 套件 | A11, A13, A15, **A14-3** | a11-bundle / misstatement-workpaper / a15-bundle / **a14-3-workbook** | 多 sheet 路由 |

```
红框 26 物理文件
  ├─ 9× 程序表 xlsx ──→ GtAProgramConsole（HTML，已有）
  ├─ 7× docx ──→ WpPopupDocxEditor（弹窗）
  └─ 子 xlsx / 套娃 sheet ──→ checklist / d-form / 专用

A13 单文件套件：
  GtMisstatementWorkpaper（新建）
    Tab 程序表 | Tab A13-1 汇总 | Tab A13-2~5 表单

A11 双轨：
  A11-1 docx → 弹窗
  A11-WP-1 sheet / A11-2 sheet → HTML（别名路由）
```

### 适用性判定（统一口径）

```python
# 唯一入口：ProcedureTableService._check_applicable
# 数据源：procedure_table_templates.json 步骤级 applicable_categories
# 项目分类：business_category → get_category_prefix() → "A"|"B"|"C"
# A10 I/J/K 列 = 综合性问题/组织架构/循环问题（适用标签，非 ref_index）
# A13 seq2.x L 列 = 上市公司；A15 seq13/14 = 非上市/上市
```

弹窗 chip 灰显：`applicable=false` → `GtIndexChip` disabled + 不触发弹窗。

**弹窗三态**（与 A17 一致）：

1. `applicable=false` → chip 灰显，不弹窗
2. `applicable=true` 且无 OnlyOffice 实例 → 弹窗内 prefilled-download
3. 已有实例 → 弹窗内在线编辑（当前 7 个 docx lite 均走态 2）

---

## Sheet / Tab 路由契约

套娃文件统一用 `navigate(wp_code, query)`；**底稿目录 F 列解析优先级**：

1. **精确 wp_code**（独立物理文件，如 `A15-1`）→ 直接打开该 wp
2. **bundle 内 sheet alias**（F 与 docx 子码同名但实物不同，如 `A11-1`）→ 查 alias 表，**不**走 INLINE_POPUP
3. **程序表 chip ref_index** → INLINE_POPUP（docx）或 navigate（xlsx 子底稿）

```typescript
// A11 bundle
navigate('A11', { sheet: 'program' })      // 程序表（默认）
navigate('A11', { sheet: 'A11-WP-1' })       // xlsx 审定表（≠ docx A11-1）
navigate('A11', { sheet: 'A11-2' })          // 问卷 checklist
navigate('A11', { sheet: 'A11-3' })          // 内控问卷（整合审计）

// A13 bundle
navigate('A13', { tab: 'program' })        // 程序表
navigate('A13', { tab: 'summary' })        // A13-1 汇总
navigate('A13', { tab: 'A13-2' })          // … A13-5 d-form

// A15 bundle
navigate('A15', { sheet: 'program' })        // 程序表（默认）
navigate('A15', { sheet: 'guidance' })       // 决策图，只读，不持久化
navigate('A15-1')                            // 独立文件 checklist
```

| F 列索引 | 用户入口 | 路由 |
|----------|----------|------|
| A11-1 | 底稿目录 | `{ wp: 'A11', sheet: 'A11-WP-1' }` |
| A11-1 | A11 程序表 chip | `INLINE_POPUP` → docx 问询函 |
| A11-2 | chip / 目录 | `{ wp: 'A11', sheet: 'A11-2' }` 或独立 checklist |

---

## audit-xlsx 产出物（✅ 已完成）

`backend/data/a7_a15_xlsx_audit.json` — 每个物理文件一条：

**xlsx 条目**：

```json
{
  "wp_code": "A15-1",
  "filename": "A15-1 持续经营调查表.xlsx",
  "format": "xlsx",
  "sheets": [{
    "name": "持续经营调查问卷A15-1",
    "header_row": 6,
    "data_rows": 42,
    "columns": [{"col": "A", "label": "序号"}, {"col": "B", "label": "疑虑事项"}],
    "merged_ranges": ["B7:C7"],
    "notes": ""
  }]
}
```

**docx 条目**（脚本 `backend/scripts/audit_docx_scan.py`）：

```json
{
  "wp_code": "A8-1",
  "format": "docx",
  "runtime": "wp-popup-docx",
  "placeholders": { "bracket_fields": [], "xx_date_entity": [] },
  "paragraph_count": 34,
  "table_count": 1,
  "comment_table": true
}
```

**程序表 diff 规则**（`audit_a7_a15_xlsx.py`）：

| 规则 | 范围 | 说明 |
|------|------|------|
| ● → 6.1 | **仅 A8** | xlsx 符号子项展开 |
| （n）→ 10.n | A11 | 问卷编号归一化 |
| ref 空值 | 全局 | xlsx H/K 列常空；**JSON ref_index 为准** |
| 内联 seq5 | A8 | 5.1–5.3 JSON 扩展（UI 用） |

**不阻塞 lite**；**阻塞 core parser 标绿**（列映射须来自 audit JSON）。

**维护建议**（文档约定，后续实现）：

- 从 audit JSON **半自动生成** checklist parser 列配置片段，避免手写漂移
- CI 跑 `audit_a7_a15_xlsx.py --diff-only`：xlsx 模板变更时 procedure_table 须同步更新

---

## 组件设计

### GtAProgramConsole（A7–A15 程序表）

- 权威源：`procedure_table_templates.json`（**A7–A15 已全部对齐** xlsx）
- 列布局变体见 requirements §程序表列布局变体
- chip 点击 → `ref_index` 路由（navigate / INLINE_POPUP / 灰显）

### WpPopupDocxEditor（7 个 docx）

**文字颜色语义**（与 A17/A18 一致）：

| 颜色 | 含义 | export 行为 |
|------|------|-------------|
| 红 | 填写项（公司名/年度/日期） | 替换为项目数据 |
| 蓝 + 【】 | 编制提示 | **删除** |
| 黑 | 标准措辞 | 保留 |
| 注释表 | 编制说明 | **删除** |

| wp_code | 结构要点 | chip 来源 |
|---------|----------|-----------|
| A8-1 | 6 条声明 + 注释表；seq2 **条件适用** | A8 seq2 |
| A8-2 | 5 章 + 封面表 + 文件清单；Word 自由编辑 | A8 seq3 |
| A9-1/2 | 3 节沟通函 + 回签 | A9 seq2/4 |
| A10-1 | 1151 超大信函；142 段 + 10 表 | A10 seq7, 4.8 |
| A11-1 | 1332 问询函；38 段 + 1 表 | A11 seq1 |
| A12-1 | 确认函 + 复函合一；23 段 + 5 表 | A12 seq1 |

**A8-2 guidance**：`procedure_table_templates.json` → A8.`reference_note`（**静态 JSON 20 项**），不运行时解析 xlsx。

**A10-1 特殊 UX**：弹窗 guidance 区提供**按节锚点**目录（非 A17-1 章节 HTML）；正文仍在 Word 编辑。

**数据模型**：弹窗 docx **无** checklist_responses；prefilled-download → OnlyOffice 编辑。

**checkCompletion（plus）**：export 前检测红/蓝占位残留（XX、201X、未替换【】）；注释表已删。

### checklist-table（PRE-4）

新建 `backend/app/services/checklist_xlsx_parser.py`：

- 输入：`wp_templates/A/` 对应 xlsx + audit JSON 列映射
- 输出：与 `GtChecklistTable` 兼容的 `{ sections, toc, stats }`
- 缓存：mtime 缓存（同 docx parser）

| wp_code | sheet | 项数 | 列 |
|---------|-------|------|-----|
| A11-2 | 期后事项调查问卷 | 13 | 序号/调查内容/适用情况/简要说明 |
| A11-3 | 期后内控事项调查问卷 | 10 | 序号/内控调查内容/适用情况/简要说明 |
| A14-1 | A14-1控制缺陷汇总表 | 动态行 | R5+R6 双行表头；认定 6 列矩阵 |
| A15-1 | 持续经营调查问卷 | 11+6+4 | 序号/疑虑事项/是否存在/说明 |

**数据模型**：`checklist_responses` — 完整 item_id 注册表见 [persistence.md](../completion-phase-infra/persistence.md)。

A14-1 认定矩阵 **定案**：remark JSON（禁止与 A15 固定问卷共用 parser 分支）。

### d-form-table / d-form-confirmation

**共享抽象**：见 [persistence.md §d-form](../completion-phase-infra/persistence.md) 与 [infra §结构化函件最小共享](../completion-phase-infra/persistence.md#结构化函件最小共享-a17-1--a18-2)。

| wp_code | 要点 | 分期 |
|---------|------|------|
| A10-2 | 模板1 参与人+议题；模板2 5 列风险表 | core |
| A13-2 | 18 行错报明细 | core |
| A13-3 | 错报合计矩阵 + 重要性评价 | core |
| A13-4 | 错误/舞弊缺陷表 | core |
| A13-5 | 与管理层/治理层沟通记录 | core |
| A14-2 | 企业层面 Step1–4（⚠️ 首 sheet 误标 A14-4） | core |
| A14-3 | **a14-3-workbook**（见下） | core |
| A14-4 | 业务流程 Step1–7 | core |
| A14-5 | T3 汇总评价 | plus |
| A11-WP-1 | 审定表：类别/期后事项/审计过程及结论/索引/备注 | core |

#### A14-3 workbook（定案：非单一 d-form-table）

物理文件 6 sheet（含示例 skip）。runtime = **`a14-3-workbook`** Tab 容器，与 A13 对称：

```typescript
tabs: [
  { id: 'defect-list', label: 'IT缺陷汇总表', component: 'd-form-table' },
  { id: 'eval-step1', label: '步骤一', component: 'd-form-table' },
  // … Step2–6 + 沟通纪要（以 audit JSON sheet 名为准）
]
```

`_WP_CODE_OVERRIDE["A14-3"] = "a14-3-workbook"`（**不再**使用单一 `d-form-table` 打开全文件）。

### GtMisstatementWorkpaper（A13 Tab 套件，core）

```typescript
// wp_code=A13 → misstatement-workpaper
tabs: [
  { id: 'program', label: '程序表', component: 'GtAProgramConsole' },
  { id: 'summary', label: 'A13-1 汇总', component: 'MisstatementSummaryView' },
  { id: 'A13-2', ... }, // d-form-table
  // A13-3 ~ A13-5
]
```

A13-1 列（audit）：序号/内容及说明/索引号/调整内容 + R6 借方科目·金额·贷方·性质。

### 专用组件

| 组件 | wp_code | 说明 |
|------|---------|------|
| MisstatementSummaryView | A13-1 | 三大错报块 + 底部合计；`auto_data_source: misstatement_summary` |
| GtCNoteTable | A7-2 | 多 section 附注披露；section-aware parser |
| GtEControlTest | A14-6 | T4 非财报告 Step1–7 |
| guidance-reference | A15 决策图 sheet | 仅 guidance，不持久化 |

### A11 路由分流（core 必做）

实现须符合上文 **§Sheet / Tab 路由契约**；chip 与底稿目录 F 列不得共用同一路由。

---

## 模块详设（audit 结论摘要）

### A7 关联交易

| 子码 | runtime | 深读 |
|------|---------|------|
| A7 | a-program-console | 4 步；H=索引；seq1→A7-1, seq6→A7-2 |
| A7-1 | univer → HTML | 项目/母公司/子公司/合计矩阵 |
| A7-2 | c-note-table | 母公司/关联关系/多段披露子表 |

### A8 其他信息

| 子码 | runtime | 深读 |
|------|---------|------|
| A8 | a-program-console | **K=索引号**（列偏移）；10 步 + ●/5.x |
| A8-1 | wp-popup-docx | 6 条声明 + 注释表 |
| A8-2 | wp-popup-docx | 5 章 + 封面表 + 文件清单；guidance 引用 `reference_note` 20 项 |

### A9 内控建议

| 子码 | runtime | 深读 |
|------|---------|------|
| A9 | a-program-console | **4 步**；H=索引；seq1→A14, seq2/4→A9-1/2 |
| A9-1/2 | wp-popup-docx | 3 节沟通函 + 回签；文件名无空格 |

### A10 治理层沟通

| 子码 | runtime | 深读 |
|------|---------|------|
| A10 | a-program-console | **11 步**；H=索引；I/J/K 适用标签 |
| A10-1 | wp-popup-docx | 1151 信函；142 段 + 10 表 |
| A10-2 | d-form-confirmation | 2 sheet：参与人 / 事项·风险表 |

### A11 期后事项（6 sheet bundle）

| sheet | runtime | 说明 |
|-------|---------|------|
| 审计程序A11 | a-program-console | 23 步 + 35 子项 |
| 期后事项审定表A11-1 | d-form-table (`A11-WP-1`) | 与 docx A11-1 **不同路由** |
| 期后事项调查问卷A11-2 | checklist-table | 13 项 |
| 期后内控事项调查问卷A11-3 | checklist-table | 10 项（整合审计） |

### A12 律师回复

| 子码 | runtime | 深读 |
|------|---------|------|
| A12 | a-program-console | **4 步**（非 2 步泛化） |
| A12-1 | wp-popup-docx | 确认函 + 复函合一 |

### A13 错报（8 sheet bundle）

程序表：**5 步 + 13 子项**（含 3.3.1–3.3.6 三级嵌套）；**K 列**索引号。

| sheet | runtime |
|-------|---------|
| A13-1 | misstatement-summary |
| A13-2~5 | d-form-table |

### A14 缺陷族（7 文件）

| 子码 | runtime | 分期 |
|------|---------|------|
| A14 程序表 | a-program-console | lite；**6 步** |
| A14-1 | checklist-table | core |
| A14-2 | d-form-table | core |
| A14-3 | **a14-3-workbook** | core |
| A14-4 | d-form-table | core |
| A14-5 | d-form-table | plus |
| A14-6 | e-control-test | plus |

**禁止**将 A14-2~6 一律标为 univer。

### A15 持续经营（3 sheet）

| 子码 | runtime | 深读 |
|------|---------|------|
| A15 | a15-bundle | **14 步** + 决策图 guidance |
| A15-1 | checklist-table | 财务(11)+经营(6)+其他(4) + 调查结论 |

---

## ref_index（procedure_table_templates.json）

| 程序表 | seq | ref_index |
|--------|-----|-----------|
| A7 | seq1, seq6 | A7-1, A7-2 |
| A8 | seq2, seq3 | A8-1, A8-2 |
| A9 | seq1, seq2, seq4 | A14, A9-1, A9-2 |
| A10 | seq6, seq7, seq4.8 | A10-2, A10-1 |
| A11 | seq1, seq2 | A11-1 (docx), A11-2 |
| A12 | seq1 | A12-1 |
| A13 | seq3, seq3.1, seq4, seq5 | A13-1; A13-3,A13-5; A13-4 |
| A14 | seq1, seq2, seq3, seq4, seq6 | CX; A14-2,3,4; A14-5; A14-1; A14-6 |
| A15 | seq1, seq4 | A15-1 |

---

## 技术方案

### 后端

| 文件 | 分期 | 职责 |
|------|------|------|
| `a7_a15_xlsx_audit.json` | ✅ audit | 26 文件列映射 |
| `procedure_table_templates.json` | ✅ audit | A7–A15 程序表步骤 + ref_index |
| `checklist_xlsx_parser.py` | core（PRE-4） | A11-2/3, A14-1, A15-1 解析 |
| `docx_template_filler.py` | plus（PRE-2） | A8–A12 docx export-word |
| `misstatement_summary_service.py` | lite | A13-1 auto_data（已有） |

### 前端

| 组件 / 注册 | 分期 | 说明 |
|-------------|------|------|
| `GtAProgramConsole` | lite | 已有 |
| `WpPopupDocxEditor` | lite | 7 docx |
| `GtMisstatementWorkpaper.vue` | core | A13 Tab 容器 |
| `GtChecklistTable` | core | A11-2/3, A14-1, A15-1 |
| `GtA14_3Workbook.vue` | core | A14-3 多 sheet Tab |
| d-form 系列 | core/plus | A10-2, A13-2~5, A14-2/4/5 |
| `GtCNoteTable` | core | A7-2 |
| `GtEControlTest` | plus | A14-6 |
| htmlRendererRegistry 扩展 | lite/core | 见 _WP_CODE_OVERRIDE（含 `a14-3-workbook`） |

### _WP_CODE_OVERRIDE（目标态）

```python
# 程序表（已有默认 a-program-console，通常不需 override）
"A13": "misstatement-workpaper",
"A11": "a11-bundle",
"A15": "a15-bundle",

# 核对表
"A11-2": "checklist-table",
"A11-3": "checklist-table",
"A14-1": "checklist-table",
"A15-1": "checklist-table",

# 表单
"A10-2": "d-form-confirmation",
"A13-2": "d-form-table",
"A13-3": "d-form-table",
"A13-4": "d-form-table",
"A13-5": "d-form-table",
"A14-2": "d-form-table",
"A14-3": "a14-3-workbook",
"A14-4": "d-form-table",
"A14-5": "d-form-table",

# 专用
"A13-1": "misstatement-summary",
"A7-2": "c-note-table",
"A14-6": "e-control-test",

# A11 xlsx 审定表 → sheet 级路由 A11-WP-1，非 wp_code override
```

---

## issue_tickets（A14 plus）

见 [completion-phase-infra §issue_tickets](../completion-phase-infra/requirements.md#issue_tickets-取数映射舞弊违规)。

---

## 不做

- 程序表改回 xlsx/Univer 编辑
- A11-1 docx 与 xlsx 审定表共用同一路由
- audit-xlsx 未完成即标 core parser 绿
- 伪造 E2E 标绿
- A8-2 / A10-1 做成 A17-1 式 structured HTML（保持 Word 自由编辑）
