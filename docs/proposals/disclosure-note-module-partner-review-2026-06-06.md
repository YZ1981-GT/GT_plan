# 附注模块专项复盘与下一轮优化建议（2026-06-06）

> 视角：大型会计师事务所项目合伙人 / 平台建设负责人  
> 范围：财务报表附注模块的章节切分、表格语义、公式联动、格式编辑、底稿取数关联、前后端体验与后续维护  
> 关系：本文件不替代 `disclosure-note-improvement-v2.md` 与 `.kiro/specs/disclosure-note-linkage-and-slimdown/`，而是在其基础上提出下一轮更偏“附注产品化、审计可用性、长期维护”的建议。

---

## 0. 总体判断

附注模块是当前平台中业务复杂度最高、也最接近“事务所级能力”的模块之一。它已经具备很多成熟基础：章节树、国企/上市模板、附注生成、表格编辑、公式管理、从底稿刷新、Word 导出、离线分发、版本树、集团基线、锁定、AI 辅助等能力都已铺开。

但从事务所真实使用角度看，附注模块仍存在一个核心问题：**功能点很多，但附注的“语义模型”还没有完全收口**。也就是说，系统已经能展示章节、表格、公式和数据，但还需要进一步明确：

1. 一个附注章节到底由哪些“可治理的结构单元”组成？
2. 标题行、说明行、表格数据行、合计行、分组行如何区分？
3. 每个单元格的值来自底稿、试算表、报表、上年附注、人工输入还是 AI？
4. 公式是表内公式、跨表公式、跨附注公式，还是底稿取数公式？
5. 前端编辑样式、Word 导出样式、离线 Excel 样式是否真正同源？
6. 上游底稿变化后，哪些附注章节、哪些表格、哪些单元格受影响？

当前已有的 `disclosure-note-linkage-and-slimdown` spec 已经针对“假性刷新、auto_pull、DisclosureEditor 瘦身”提出了具体修复，这是必要的 P0/P1。但从更长期看，附注模块下一步应从“能生成、能编辑”升级为“结构化、可追溯、可校验、可复用、可审计”的专业模块。

---

## 1. 当前基础能力

### 1.1 后端能力已较丰富

代码中已经形成 50+ 个 `note_*` 服务，例如：

- `disclosure_engine.py`：附注生成与刷新主引擎
- `note_formula_generator.py`：附注公式 DSL 执行
- `note_source_resolvers.py` / `note_wp_data_resolver.py`：附注取数解析
- `note_cell_merge.py`：auto/manual/locked 单元格合并保护
- `note_column_semantics.py`：列语义
- `note_format_config.py` / `note_word_dynamic_styles.py`：格式与 Word 样式
- `note_validation_engine.py`：校验
- `note_section_numbering_service.py`：章节编号
- `note_template_service.py` / `note_custom_template_service.py`：模板
- `note_offline_export_service.py` / `note_offline_import_service.py`：离线分发
- `note_auto_pull_service.py`：跨底稿 auto_pull
- `note_stale_service.py`：stale 联动
- `note_wp_mapping_service.py`：附注与底稿映射

这说明附注模块不是空白，而是已经有很强的工程基础。

### 1.2 前端编辑器功能很全

`DisclosureEditor.vue` 已集成：

- 章节树 / 平铺列表
- 刷新、生成、校验
- 新增自定义章节
- 表样编辑 `StructureEditor`
- 公式管理 `FormulaManagerDialog`
- 版本、上年、锁定、批注、时光机
- AI 续写/改写/知识库
- stale 提示、冲突提示、EQCR 只读视图

问题不在“没有功能”，而在功能都集中在一个大型编辑器里，用户在复杂场景下容易失去方向，开发维护也容易牵一发动全身。

### 1.3 已有重要架构决策是正确的

几个已有 ADR/文档方向值得继续坚持：

- `DisclosureNote.table_data` 作为唯一真源，`structure.json / xlsx / HTML` 都是镜像或中间形态。
- `_cell_modes` / `_cell_meta` 作为 sidecar 保留 auto/manual/locked、binding、manual_value。
- 公式 DSL 已有文档，不应另起炉灶。
- 三式联动应走统一入口，不能让 xlsx / HTML 直接变成真源。

这些都是附注模块后续优化的地基。

---

## 2. 当前主要问题

## 2.1 附注章节切分仍偏“显示树”，未完全成为“业务结构树”

当前章节树能展示 `note_section` 和 `section_title`，也支持章节编号、锁定、stale、校验错误等状态。但从审计实际看，附注章节不只是目录节点，还需要表达更细的业务结构：

- 主章节
- 子章节
- 段落说明
- 表格组
- 单张表
- 表内分组
- 标题行
- 数据行
- 合计行
- 说明脚注
- 不适用章节
- 单体/合并适用范围

目前 `note_section` 仍承担了太多含义：编号、章节 ID、展示文本、排序锚点、跳转锚点、权限锁定锚点。长期看，这会造成几个问题：

1. 国企版/上市版模板切换时，章节编号和语义章节难以稳定对应。
2. 自定义章节插入后，编号、排序、锁定、版本树容易互相影响。
3. 合并附注与单体附注共享章节时，范围 `scope` 与章节树关系不够直观。
4. 附注导出时，标题层级和 Word 样式难以稳定映射。

### 建议

建立“附注章节结构树”模型，至少区分：

| 字段 | 用途 |
|---|---|
| `section_id` | 稳定语义 ID，不随展示编号变化 |
| `display_number` | 渲染编号，如“五、3” |
| `title` | 章节标题 |
| `level` | 层级 |
| `parent_section_id` | 父节点 |
| `scope` | standalone / consolidated / both |
| `content_blocks` | 段落、表格、脚注等块 |
| `sort_index` | 排序 |
| `is_custom` | 是否自定义 |
| `applicable_standard` | soe / listed / both |

注意：这不一定要求马上改数据库主模型，可以先在模板和前端层提供结构化 view model，但长期应减少对 `note_section` 字符串的过度依赖。

---

## 2.2 标题行、分组行、数据行、合计行缺少统一 row_type

附注表格不同于普通数据表。很多表里第一列既可能是行标题，也可能是分组标题，还可能是可取数科目名称。例如：

- “项 目” 是表头，不是数据行。
- “一、账面原值” 是分组行。
- “1.期初余额” 是数据行。
- “合计” 是合计行。
- “其中：房屋及建筑物” 是子项行。
- “本期增加金额” 下还可能有购置、在建转入、企业合并增加等多层列。

当前部分结构依赖 `row.label` 和 `is_total`，这对简单表可用，但不足以支撑复杂附注。

### 建议

在 `table_data.rows[]` 中统一引入 sidecar 字段 `row_type`，兼容现有结构：

```json
{
  "label": "一、账面原值",
  "values": [],
  "row_type": "group_header",
  "_cell_modes": {},
  "_cell_meta": {}
}
```

建议枚举：

| row_type | 含义 |
|---|---|
| `data` | 普通数据行 |
| `group_header` | 表内分组标题 |
| `subtotal` | 小计行 |
| `total` | 合计行 |
| `section_note` | 表内说明行 |
| `blank` | 空行 |
| `custom` | 用户自定义行 |

同时应避免继续只靠 `is_total` 判断汇总逻辑。`is_total` 可以保留兼容，但新逻辑应以 `row_type` 为主。

---

## 2.3 表格列语义仍不够强，复杂表头难以承载公式和取数

当前附注模板大量是多层表头、合并表头、动态列。若只用 `headers: string[]`，系统难以表达：

- 期初余额 / 本期增加 / 本期减少 / 期末余额
- 本期增加下的购置、在建转入、企业合并增加
- 本期减少下的处置、报废、转出
- 原值、累计折旧、减值准备、账面价值之间的关系

公式管理如果绑定到“第几列”，后续用户增删列、模板升级、国企/上市转换时就容易错位。

### 建议

引入 `columns[]` 语义层，与 `headers[]` 兼容：

```json
{
  "columns": [
    {
      "col_id": "opening_balance",
      "label": "期初余额",
      "level": 1,
      "source": "trial_balance",
      "period": "opening"
    },
    {
      "col_id": "increase_purchase",
      "label": "购置",
      "parent_col_id": "current_year_increase",
      "source": "ledger",
      "direction": "debit"
    }
  ]
}
```

公式和取数应绑定 `col_id`，而不是绑定列下标。

这样可以解决三个问题：

1. 多层表头可以稳定表达。
2. 表格增删列不会破坏公式。
3. Word 导出、Excel 离线、前端预览可以共享同一列语义。

---

## 2.4 表格中的公式管理已有基础，但需要进一步统一和产品化

目前公式相关能力较多：

- `FormulaManagerDialog`
- `StructureEditor`
- `note_formula_generator`
- `note_formula_engine`
- `_formulas`
- `formula_type`
- `_cell_modes`
- `_cell_meta`

这说明公式能力已经存在。但从用户使用角度看，还需要进一步回答：

1. 这个单元格是否有公式？
2. 公式来自模板、系统生成、用户自定义，还是 AI 建议？
3. 公式用了哪些底稿、试算表、报表、上年附注？
4. 公式是否执行失败？
5. 公式执行失败后，用户应如何处理？
6. 手工覆盖后，原公式是否保留？
7. 恢复自动取数时，恢复到哪个公式版本？

### 建议

把公式管理升级为“单元格公式治理面板”，而不仅是公式 CRUD。

每个公式单元格应有：

| 字段 | 说明 |
|---|---|
| `formula_id` | 公式 ID |
| `cell_ref` | 表格/行/列定位 |
| `formula_expr` | DSL 表达式 |
| `formula_source` | template / user / ai / system |
| `dependencies` | 依赖的 TB/WP/REPORT/NOTE/PRIOR |
| `last_result` | 最近执行结果 |
| `last_error` | 最近错误 |
| `last_evaluated_at` | 最近执行时间 |
| `is_overridden` | 是否被手工覆盖 |
| `previous_auto_value` | 覆盖前自动值 |

前端建议在表格单元格上提供统一标识：

- `fx`：有公式
- `M`：manual
- `L`：locked
- `!`：公式错误
- `S`：stale

用户点击单元格时，右侧面板展示公式、来源、依赖、错误、历史和恢复自动按钮。

---

## 2.5 格式编辑与内容编辑需要分层

审计附注的格式要求很强，包括：

- 章节标题层级
- 左缩进
- 字体字号
- 三线表
- 表头加粗
- 金额列对齐
- 合并单元格
- 脚注
- 空行
- Word 导出样式

当前前端有 `StructureEditor`，后端有 `note_format_config`、`note_word_dynamic_styles`、`note_word_exporter` 等基础。但风险在于用户编辑“表格内容”时可能顺手改变“格式结构”，导致导出样式不稳定。

### 建议

把附注编辑拆成三层：

| 层 | 用户可见能力 | 存储建议 |
|---|---|---|
| 内容层 | 文本、金额、说明、手工输入 | `table_data.rows[].values` / `text_content` |
| 结构层 | 增删行列、表格、章节、合并单元格 | `table_data._tables[].structure` |
| 样式层 | 字体、边框、缩进、三线表、金额单位 | `format_profile` / style tokens |

普通审计助理默认只开放内容层。结构层和样式层建议给经理或模板管理员使用，避免项目组随意改坏模板。

---

## 2.6 附注与底稿数据关联应从“标签匹配”升级为“绑定注册表”

历史上附注取数存在用 `row.label` 匹配底稿或科目名称的模式，这在简单表里能工作，但长期不可靠：

- 同名行在不同表中含义不同。
- “合计”“其中”“期末余额”等文字不是科目。
- 国企版/上市版同一语义章节可能标题不同。
- 自定义章节无法稳定匹配。
- 行标签修改会破坏取数。

### 建议

建立附注绑定注册表 `note_binding_registry`，按语义绑定，而非文字绑定：

```json
{
  "section_id": "fixed_assets",
  "table_id": "movement_original_cost",
  "row_id": "buildings",
  "col_id": "increase_purchase",
  "binding": {
    "source": "workpaper",
    "wp_code": "H1",
    "sheet": "固定资产明细",
    "field": "purchase_amount",
    "aggregation": "sum",
    "filters": {
      "asset_category": "buildings"
    }
  }
}
```

绑定注册表应支持来源：

- `trial_balance`
- `ledger`
- `workpaper`
- `report`
- `prior_note`
- `manual`
- `formula`
- `ai_draft`

并且每个绑定应能返回：

- 当前值
- 来源路径
- 取数口径
- 最近刷新时间
- 是否 stale
- 是否被 manual 覆盖

---

## 2.7 自定义章节需要更强的治理

目前已有新增自定义附注章节能力。但事务所实际使用中，自定义章节有风险：

1. 用户新增章节后，编号如何与标准模板一起排序？
2. 自定义章节是否参与 Word 导出？
3. 是否参与校验？
4. 是否参与版本链和归档？
5. 是否能被集团模板下发或锁定？
6. 是否能被 EQCR/QC 识别？

### 建议

自定义章节要进入标准治理：

| 能力 | 建议 |
---|---|
| 编号 | 由章节树服务统一生成，不允许用户手填最终编号 |
| 权限 | 普通助理可提议，经理/合伙人批准后生效 |
| 版本 | 每次结构变更进入版本树 |
| 导出 | 默认参与导出，但可显式排除 |
| 校验 | 至少校验标题、内容非空、金额格式 |
| 来源 | 标记 custom/manual/system |
| 归档 | 进入交付件和归档清单 |

---

## 2.8 附注校验应从“表内校验”升级为“签发前附注质量清单”

现在已有 `note_validation_engine`，但合伙人和经理需要看到更高层的附注质量结论。

建议建立附注质量清单：

| 检查项 | 说明 |
|---|---|
| 完整性 | 必填章节是否存在 |
| 适用性 | 不适用章节是否已说明 |
| 金额一致性 | 与报表、底稿、试算表是否一致 |
| 公式正确性 | 是否有公式错误 |
| stale 状态 | 是否有未刷新章节 |
| manual 覆盖 | 是否有重要手工覆盖 |
| AI 内容 | 是否有未确认 AI 内容 |
| Word 样式 | 是否满足致同样式 |
| 交叉引用 | 章节引用是否可跳转 |
| 导出可用性 | Word/PDF 是否可成功生成 |

该清单应在：

- 附注编辑器
- 项目经理工作台
- 合伙人签发页
- EQCR 工作台

都能看到，但展示粒度不同。

---

## 2.9 前端用户体验建议

### 2.9.1 章节树要更像“附注导航”，而不是普通目录

建议章节树显示：

- 编号
- 标题
- stale 标记
- 锁定标记
- 校验失败标记
- 是否不适用
- 是否自定义
- 是否含 AI 未确认
- 是否含手工覆盖

并支持过滤：

- 仅看 stale
- 仅看校验失败
- 仅看自定义章节
- 仅看含手工覆盖
- 仅看合并附注

### 2.9.2 表格编辑应默认保护结构

普通助理进入表格时，默认只编辑内容。结构编辑入口应更明确：

- 内容编辑：直接在表格中改数、改文字。
- 结构编辑：进入 `StructureEditor`，需要更高权限。
- 公式编辑：进入公式面板，保留变更记录。
- 样式编辑：模板管理员入口，不建议普通项目组开放。

### 2.9.3 单元格应有“来源说明”

每个关键金额单元格点击后应能看到：

- 当前值
- 来源类型
- 来源路径
- 公式
- 最近刷新时间
- 是否手工覆盖
- 上游是否 stale
- 相关底稿/附件/报表行跳转

这对审计助理、经理、合伙人都很重要。

---

## 3. 建议的下一轮优化路线

### P0：先补语义底座

目标：不大改界面，先让结构和数据口径清楚。

1. 引入 `row_type` sidecar，兼容 `is_total`。
2. 引入 `columns[].col_id` 列语义层，兼容 `headers[]`。
3. 补充 `table_id`，避免 `_tables` 中多个表同名。
4. 统一单元格来源面板，读取 `_cell_meta`、`_formulas`、LinkageContract。
5. 明确普通内容编辑和结构编辑权限边界。
6. 附注质量清单先覆盖 stale、formula error、manual override、AI unconfirmed。

### P1：强化联动和公式治理

目标：让附注真正成为底稿和报表的下游可信输出。

1. 建立 `note_binding_registry`。
2. 公式管理绑定 `section_id/table_id/row_id/col_id`，不再依赖列下标。
3. 公式依赖图展示：TB/WP/REPORT/NOTE/PRIOR。
4. 公式执行错误统一进入质量清单。
5. 底稿变化后，精准定位影响的章节、表格和单元格。
6. 支持公式版本、恢复自动值、手工覆盖差异对比。

### P2：模板治理和导出一致性

目标：把附注模板变成事务所级资产。

1. 自定义章节审批流。
2. 结构层/样式层权限治理。
3. 国企版/上市版章节语义映射。
4. 集团模板下发与项目自定义差异对比。
5. Word、Excel、前端预览三式样式一致性测试。
6. 模板优化回流主模板机制。

---

## 4. 补充专题：前端呈现与关键章节专项建议

本节是在进一步查看当前附注前后端实现后，对前端呈现方式和关键章节处理给出的更具体建议。当前 `DisclosureEditor` 已经拆出 `useNoteTree`、`useNoteDetail`、`useNoteRefresh`、`useNotePersist`、`useNoteTemplate` 等 composable，后端也已经具备 `note_auto_pull_service`、`note_formula_generator`、`note_source_resolvers`、`note_validation_engine` 等基础。因此下一步重点不应是再堆新入口，而是把“附注怎么看、怎么核、怎么快速定位差异”产品化。

### 4.1 会计政策章节：从富文本滚动编辑升级为条款差异审阅

会计政策部分通常文字体量大、标题多、与上年或模板高度相似，仅少量条款需要调整。若继续用普通富文本模式，用户需要在长文本中人工寻找差异，效率低且容易漏。

建议将会计政策拆成条款级结构：

```json
{
  "clause_id": "policy_revenue_recognition",
  "title": "收入确认",
  "level": 2,
  "template_text": "...",
  "prior_year_text": "...",
  "current_text": "...",
  "variables": ["company_name", "year", "standard"],
  "source": "template|prior_year|manual|ai_draft",
  "diff_status": "unchanged|changed|needs_review",
  "confirm_status": "pending|confirmed|rejected"
}
```

前端建议增加“政策条款审阅模式”：

- 左侧：政策条款目录，按“重要会计政策 / 会计估计 / 变更事项 / 其他”分组。
- 中间：本年条款正文。
- 右侧：模板原文 / 上年原文 / 差异摘要。
- 默认只展示“有差异 / 待确认”条款。
- 未变化条款支持一键批量确认。
- 公司名称、年度、准则、合并范围等变量高亮。
- AI 仅生成差异摘要和修改建议，不直接覆盖正文。

这类章节的核心体验应是“快速确认少量变化”，不是“从头编辑大量文字”。

### 4.2 报表科目注释与关联方章节：从章节编辑器升级为披露数据工作台

财务报表科目主要注释和关联方交易章节是附注最关键章节。它们往往不是简单文本，而是对报表项目的明细披露，包含大量小标题、分组表格、提示事项和金额校验。

前端应支持至少四个维度：

| 维度 | 示例 | 作用 |
|---|---|---|
| 单位 | 单体 / 合并 / 子公司 / 分部 | 区分披露口径 |
| 年度 | 本年 / 上年 / 对比 | 区分期间 |
| 科目及明细 | 应收账款 / 账龄 / 坏账 / 关联方 | 快速定位披露对象 |
| 金额 | 期初 / 本期增加 / 本期减少 / 期末 / 差异 | 核对披露金额 |

建议在数据披露模式顶部固定一个“四维上下文栏”：

```text
单位：合并 | 年度：2025 | 科目：应收账款 | 明细：账龄分析 | 金额口径：期末余额
```

并支持快速切换：

- 单体 / 合并切换
- 本年 / 上年 / 差异切换
- 科目下拉
- 明细表卡片切换
- 金额口径切换

这样用户不用在章节树中反复展开定位，也能更接近审计师日常按科目审阅附注的习惯。

### 4.3 关键表格的标题行和提示事项必须结构化保护

科目注释和关联方章节中有大量小标题：

- 表格标题
- 表内分组标题
- 小计/合计行
- “其中：”项目
- 表格下关注提示事项
- 脚注说明

这些内容不能被普通数据编辑误改，否则 Word 导出、复核和签发都会受影响。

建议引入更细的结构类型：

| 类型 | 说明 | 普通助理是否可改 |
|---|---|---|
| `table_title` | 表格标题 | 否 |
| `group_header` | 表内分组标题 | 否 |
| `data` | 数据行 | 是 |
| `subtotal` | 小计行 | 通常否 |
| `total` | 合计行 | 否 |
| `note_tip` | 表下关注提示事项 | 可编辑文字，保留类型 |
| `footnote` | 脚注 | 可编辑文字，保留类型 |
| `custom` | 用户自定义行 | 依权限 |

标题和提示事项应进入 `table_data` 的 sidecar 结构，而不是仅靠 label 文本识别。建议：

```json
{
  "row_id": "bad_debt_policy_tip",
  "label": "关注提示：请说明坏账准备计提方法及本年变化原因。",
  "row_type": "note_tip",
  "locked_structure": true
}
```

### 4.4 离线导出模板：从数据 dump 升级为可填报工作包

当前离线模板如果只是把复杂表格和章节倒出，对一线人员并不友好。附注离线工作包应面向“可填、可核、可回传”设计。

建议离线包包含以下 sheet：

1. `00_填报说明`
   - 颜色说明
   - 哪些格可填
   - 哪些格锁定
   - 哪些格来自底稿
   - 如何回传

2. `01_章节清单`
   - 章节编号
   - 标题
   - 是否适用
   - 是否需填写
   - 责任人
   - 状态

3. `政策条款`
   - 条款标题
   - 模板原文
   - 上年内容
   - 本年内容
   - 差异说明
   - 确认状态

4. `科目披露`
   - 固定标题行
   - 锁定公式列
   - 可填列明确标色
   - 来源底稿列只读
   - 差异列自动计算

5. `99_校验结果`
   - 报表一致性
   - 公式错误
   - 必填缺失
   - stale 提示
   - AI 未确认

颜色建议统一：

| 颜色/标记 | 含义 |
|---|---|
| 白底 | 可填写 |
| 灰底 | 锁定/系统生成 |
| 紫色角标 | 来自底稿或报表 |
| 黄色 | 需复核 |
| 红色 | 校验失败 |
| 蓝色 | 上年/模板参考 |

这样离线模板才像审计人员可直接使用的工作底稿，而不是系统内部 JSON 的表格化导出。

### 4.5 关键科目披露：必须与报表数建立平衡校验

关键科目附注应建立“披露平衡检查”，例如：

```text
报表应收账款期末数 = 附注应收账款明细合计
报表固定资产原值期末数 = 附注固定资产原值表期末合计
报表关联方应收余额 = 关联方余额披露合计
```

建议每个关键章节配置校验规则：

```json
{
  "section_id": "accounts_receivable",
  "table_id": "aging_analysis",
  "rule_id": "ar_closing_balance_tieout",
  "left": "sum(note.table.aging_analysis.closing_balance)",
  "right": "report.BS.accounts_receivable.closing_balance",
  "tolerance": "0.01",
  "severity": "blocking"
}
```

前端展示：

- 通过：绿色
- 差异：红色，显示差异金额
- 来源缺失：黄色
- 手工覆盖：紫色提示需复核

这些校验结果应进入附注质量清单，并在合伙人签发页显示。

### 4.6 国企/上市、合并/单体：建议建立模板变体矩阵

不建议维护四套彼此割裂的模板：

- 国企单体
- 国企合并
- 上市单体
- 上市合并

建议建立语义矩阵：

```text
semantic_section_id
  ├─ soe_standalone
  ├─ soe_consolidated
  ├─ listed_standalone
  └─ listed_consolidated
```

每个语义章节记录：

- 四个版本的章节编号
- 标题差异
- 表格差异
- 必填差异
- 适用范围差异
- Word 样式差异

前端在切换国企/上市或单体/合并时，应显示：

- 当前版本
- 对应版本章节
- 差异摘要
- 独有章节
- 缺失章节
- 表格结构差异

用户需要知道“这个章节在另一个版本中对应哪里”，而不是简单重生成。

### 4.7 建议新增两种前端模式

#### A. 政策文字模式

适用于会计政策、会计估计、重大政策变更：

- 条款目录
- 差异视图
- 变量高亮
- 一键确认未变条款
- AI 差异摘要
- 上年/模板对照

#### B. 数据披露模式

适用于科目注释、关联方、合并披露：

- 四维上下文栏：单位、年度、科目/明细、金额口径
- 表格卡片
- 来源/公式/校验侧栏
- 表格下关注提示事项
- 一键穿透底稿
- 差异与报表一致性提示

这两个模式可以共用 `DisclosureNote.table_data` 真源，但前端呈现和操作焦点应明显不同。

---

## 5. 建议新增一个专项 spec

已有 `disclosure-note-linkage-and-slimdown` 解决的是“刷新、auto_pull、瘦身”三个实证缺口。建议新增一个后续 spec：

`disclosure-note-semantic-structure-and-presentation`

建议三件套覆盖：

### requirements

- 章节结构树
- 会计政策条款化呈现
- 数据披露四维上下文
- row_type
- column semantics
- table_id
- formula governance
- binding registry
- cell source drawer
- note quality checklist
- role-based structure editing
- offline workbook presentation
- template variant matrix

### design

- `DisclosureNote.table_data` 兼容扩展
- sidecar 字段设计
- `row_id / col_id / table_id`
- `policy_clause_id`
- `semantic_section_id`
- formula dependency graph
- binding registry
- disclosure balance rules
- Word/Excel/HTML 样式映射
- offline workbook sheet layout
- 迁移策略

### tasks

- P0-MVP：政策条款审阅原型 + 数据披露四维上下文 + row_type + table_id/col_id + 单元格来源面板
- P0-Full：附注质量清单 + 结构编辑权限边界 + 离线模板说明页
- P1：binding registry + formula dependency graph + 披露平衡校验
- P2：模板变体矩阵 + 离线工作包优化 + 样式一致性测试

---

## 6. 最终建议

如果站在合伙人和真实项目使用角度，我认为附注模块下一轮的重点不应是继续增加按钮，而应是：

1. **把章节切分从目录树升级为结构树。**
2. **把表格从二维数组升级为语义表格。**
3. **把公式从表达式管理升级为公式治理。**
4. **把格式编辑从随手改样式升级为内容/结构/样式分层权限。**
5. **把底稿关联从文字匹配升级为绑定注册表。**
6. **把校验从表内公式校验升级为签发前附注质量清单。**

附注模块已经有足够多的基础设施，下一步最重要的是“收口语义模型”。只要 `section_id / table_id / row_id / col_id / binding_id / formula_id` 这些锚点稳定下来，附注与底稿、报表、调整分录、交付件、EQCR、QC 的联动都会变得更可靠，也更容易维护。

一句话结论：**附注模块现在不是缺功能，而是缺一个更稳定的结构语义层。下一轮应围绕章节结构、表格语义、公式治理和底稿绑定做专项升级。**
