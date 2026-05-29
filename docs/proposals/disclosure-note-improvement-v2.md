# 附注模块改进建议（v2.0）

> **✅ 已实施**（2026-05-27 完成 44/47，剩 F-1 真 UAT / F-2 dev-history 沉淀 / F-3 收口在跑中）
> commits：`6b6731c` Sprint 0 / `65fc11a` Sprint 1 / `3c5067c` Sprint 1.5 / `e1477b2`+`1729c38f` Sprint 2 / `58cff337` Sprint 3 / `736cf1d4`+`551835b6` Sprint 4
> spec 三件套：`.kiro/specs/disclosure-note-full-revamp/`
> 验收：pytest 430/430 全绿（53 新增）

> 编写：2026-05-26 | 范围：财务报表附注的数据绑定、生成、Word 导出全链路 | 适用：国企版（SOE）/ 上市版（Listed）双轨模板
>
> 版本说明：v1.0（2026-05-25）的改进方向正确，但字段级实现细节存在 16 处与代码事实不符。v2.0 全部基于 `grepSearch` 代码核验和 `附注模版/*.md` 致同实测规范重写，不再保留"勘误式补丁"格式。

---

## 一、现状盘点（基于代码 grep 实测）

### 1.1 模板规模

| 维度 | 国企版 | 上市版 |
|------|------:|------:|
| 总章节数 | 173 | 187 |
| 纯文字章节（content_type=text） | 46 | 48 |
| 文字+表格混合（content_type=mixed） | 127 | 139 |
| 含 1 张表格 | 73 | 85 |
| 含多张表格（最多 12 张/章节，如应收票据） | 54 | 54 |
| 仅合并报表（scope=consolidated_only） | 27 | 27 |

### 1.2 章节真实结构（注意：不是 v1 假设的简单 row+account_codes）

```json
{
  "section_number": "八、22",
  "section_title": "固定资产",
  "account_name": "固定资产",
  "content_type": "mixed",
  "scope": "both",
  "sort_order": 821,
  "tables": [
    {
      "name": "项  目",
      "headers": ["项目", "期末账面价值", "期初账面价值"],
      "rows": [
        {"label": "固定资产"},
        {"label": "固定资产清理"},
        {"label": "合计", "is_total": true}
      ]
    },
    { "name": "项  目", "headers": [...], "rows": [...] }
  ],
  "text_sections": ["应收票据分类", "坏账准备计提情况", "..."],
  "check_presets": ["LLM审核","二级明细","交叉","余额","其中项","完整性","宽表","纵向","跨科目"],
  "wide_table_presets": []
}
```

**核心事实**（每条都对应代码改造点）：

1. **row 字段只有 `label` 和可选 `is_total`**——**没有** `account_codes`，模板里没有任何数据绑定信息
2. 表格用 `tables` 数组承载（应收票据 12 张 / 固定资产 5 张），不是单个 `table_template`
3. `headers` 含大量空字符串占位（如 `["票据种类","期末数","期初数","","","",""]`，实际只 3 列有效）
4. 部分 row 是分组标题（label 与 headers[0] 同字面），不是数据行
5. `text_sections` / `check_presets` / `wide_table_presets` 已配置但引擎完全没消费
6. `section_number` 编号格式不统一（`"四、固定资产"` 与 `"八、22"` 混用）

### 1.3 关键代码位置

| 模块 | 文件 | 真实角色 |
|------|------|---------|
| 数据模型 | `backend/app/models/report_models.py::DisclosureNote` | UNIQUE(project_id, year, note_section) WHERE is_deleted=false |
| 模板数据 | `backend/data/note_template_{soe,listed}.json` | JSON 驱动 173/187 章节 |
| 数据绑定（缺失） | — | v2 新建 `backend/data/note_template_bindings.json` |
| 生成引擎 | `backend/app/services/disclosure_engine.py` | `generate_notes` / `_build_table_data` / `_preload_data_for_notes` |
| Word 导出 | `backend/app/services/note_word_exporter.py` | **只读 `note.table_data.headers/rows`，无视 `_tables` 数组**（P0 bug） |
| AI 辅助 | `backend/app/routers/note_ai.py` | 政策生成/续写/改写（vLLM） |
| 校验引擎 | `backend/app/services/note_validation_engine.py` | 合计行校验、期末=期初+变动 |
| 模板裁剪 | `note_trim_service.py` + `NoteTrimScheme` | 已建表+CRUD，**无自动化逻辑** |
| 报表科目映射 | `backend/data/soe_listed_mapping_preset.json` | 已被 `report_mapping_service.py:189` 用作**报表项映射**，**不是**附注章节映射 |
| 致同模板规范 | `附注模版/{上市,国企}报表附注.md` | 开头"使用说明"是排版规范单一真源 |
| 前端编辑 | `audit-platform/frontend/src/views/DisclosureEditor.vue` | TipTap + el-table，已支持 `_tables` 多表 Tab |

### 1.4 当前生成引擎的真实数据流

```
generate_notes(project_id, year, template_type)
  ├─ _preload_data_for_notes
  │    ├─ wp_cache: WorkingPaper.parsed_data.{audited_amount, unadjusted_amount}
  │    ├─ wp_fine_cache: WorkingPaper.parsed_data.fine_summary（精细化提取的明细行）
  │    ├─ wp_account_cache: wp_account_mapping.json 88 条 wp_code↔account_name
  │    ├─ tb_cache: TrialBalance.{audited_amount, unadjusted_amount, opening_balance}
  │    └─ prior_notes_cache: 上年同期 DisclosureNote.text_content
  └─ for each template:
       ├─ text_content: 上年附注 → LLM 生成 → text_sections 拍扁拼接
       ├─ table_data:
       │    ├─ tables 数组非空 → 对每张表调 _build_table_data，存到 _tables 数组
       │    │   （前端 DisclosureEditor.vue:1014 已优先读 _tables 多表 Tab；
       │    │    **只有 Word 导出器没读 _tables**，是后端单点 P0 bug）
       │    └─ 否则走单 table_template 老路径
       └─ Upsert DisclosureNote
```

**核心痛点**：`_build_table_data` 完全靠 `wp_by_account[row.label]` 字符串匹配 `wp_account_mapping.json` 反查数据，**没有任何列绑定层**。53 个变动表的"本期增加/减少"列完全无法自动取数。

### 1.5 用户自定义编辑 + 公式 + 三式联动基础设施已就位（v2 第三次复盘修订）

> ⚠️ **本节修订**（2026-05-26）：v2 早期版本仅识别"前端 row.cells 与后端 row.values 双结构 round-trip 丢字段"。**grep 实测发现远不止于此**，前后端已有完整的"自定义编辑 + 公式管理 + 三式联动"基础设施已运行，v2 后续设计必须**渐进兼容**而非另起炉灶。

#### 用户自定义编辑入口已就绪

`DisclosureEditor.vue:47-50, 277-281` 工具栏已挂载 4 个用户自定义按钮：

| 按钮 | 调用组件 | 功能 |
|---|---|---|
| 📐 表样编辑 | `StructureEditor.vue`（85% 屏占比 fullscreen） | 行列增删 + 单元格编辑 + 公式绑定 + Excel 双向同步 |
| ⚙️ 公式管理 | `FormulaManagerDialog.vue`（节点级全局公式管理器） | TB/ROW/PRIOR 等 DSL 规则的 CRUD |
| 一键清除公式 | `POST /api/disclosure-notes/.../clear-formulas` | 把所有 auto 单元格切换为 manual（用户全部接管） |
| 恢复自动提数 | `POST /api/disclosure-notes/.../restore-auto` | 把所有 manual 切回 auto，触发底稿重新提取 |

#### 三套公式系统并存（含技术债）

| 系统 | 位置 | 角色 | 状态 |
|---|---|---|---|
| `FormulaManagerDialog` | `components/formula/FormulaManagerDialog.vue` | 全局节点级公式管理 | 已实装 |
| `StructureEditor` 双 Tab | `components/formula/StructureEditor.vue:166` | 当前表公式 + 结构编辑 | 已实装 |
| `ConsolNoteTab` 内置 | `components/consolidation/ConsolNoteTab.vue:424` | 合并附注专用 dialog | **重复实现，技术债**，Sprint 1.5 收敛到 FormulaManagerDialog |

#### 公式 DSL 已运行（不要重新发明）

`note_formula_generator.execute_note_formulas` 已支持的 DSL 函数（grep 自 `ConsolNoteTab.vue:1212` + `note_formula_generator.py`）：

```
=TB("货币资金", "期末余额")            # 试算表余额取数
=TB("应收账款", "本期借方")           # 序时账发生额
=ROW(R3, "C2") - ROW(R3, "C3")         # 表内行列引用
=PRIOR("货币资金", "期末")             # 上年附注期末值（推测，需查 generator 确认）
```

Sprint 1.5 任务是**沉淀文档化**这套 DSL，不是重新发明。

#### 三式联动架构已落地

```
DisclosureNote.table_data  ⇄  structure.json  ⇄  Excel xlsx  ⇄  HTML 报告
        ↑                          ↑                ↑                ↑
   主表 JSONB              wp_structure_bridge   excel_html.py:218 三式输出
```

- `wp_structure_bridge.py`：Excel ↔ structure.json 双向同步
- `excel_html.py:218`：HTML 报告导入 → structure → DisclosureNote 单一真源更新
- `triple_format_adapter.update_note_from_structure()`：保 4 份数据一致

#### 持久化结构真相（与 v2 早期假设不符）

**真实运行结构**（`note_wp_mapping_service.py:175` + `note_formula_generator.py:278` + `triple_format_adapter.py:152`）：

```python
row = {
    "label": "银行存款",
    "values": [12345.67, 11000.00],            # ← 数值数组，前端核心字段
    "_cell_modes": {"0": "auto", "1": "manual"}, # ← 行级 dict，key 是列 index 字符串
    "is_total": False,
    "formula_type": "opening_plus_changes"      # ← 行级公式类型（前端 1095 行）
}
```

**v2 必须遵守的兼容铁律**（详见 §5.1.1）：
1. **不**把 `values` 改造为 `cells = [{value, mode}]` 单元格对象数组
2. **不**把 `_cell_modes` 收敛进 `cells[i].mode`
3. **新字段一律 sidecar 形式存在**（`row_type` / `_cell_meta` 等），老代码读到未知字段忽略
4. v2 真正新增的价值是 `_cell_meta[i].manual_value`（用户手工值原始备份，给"恢复自动提数"反查用）+ `_cell_meta[i].semantic` + `_cell_meta[i].binding_id`

---

## 二、核心问题诊断

### 问题 1：数据绑定层完全缺失（数据层根因）

模板 row 只有 `label` + 可选 `is_total`，**没有任何数据绑定信息**。引擎靠 `wp_by_account[row.label]` 字符串匹配 `wp_account_mapping.json` 反查数据，但同一个科目在不同表格里取值规则不同：

- 货币资金附注 → 期末/期初余额（`TrialBalance.audited_amount` / `opening_balance`）
- 固定资产变动表"本期增加" → 本期借方发生额（`TbLedger.debit_amount` sum）
- 应收账款账龄表 → 按账龄分桶取辅助序时账（`TbAuxLedger.voucher_date` 反推天数）
- 单元字段映射规约：
  - `closing_balance` → `audited_amount`（试算表"审定数"作为期末余额）
  - `opening_balance` → `opening_balance`
  - `current_year_amount` → 不要用 `audited_amount - opening_balance` 推算，必须走 `ledger_sum`

**实测影响**：
- 53 个变动类章节的"本期增加/减少"列完全无法自动取数
- 多表格章节（应收票据 12 张表）只有第一张表能取数
- 表格数字准确率粗估 60-65%

---

### 问题 2：多层表头 + cells.column_index 设计冲突

真实致同附注（固定资产变动表）：

```
┌──────┬──────┬───────────────┬───────────────┬──────┐
│ 项目  │期初  │   本期增加     │   本期减少     │期末  │
│      │余额  ├──────┬────────┼──────┬────────┤余额  │
│      │      │ 购置  │在建转入│ 处置  │ 报废   │      │
└──────┴──────┴──────┴────────┴──────┴────────┴──────┘
```

当前模板只支持一维 `headers: [...]` 字符串数组，无法表达。

**关键设计权衡**：v1 提的 `cells.column_index` 设计与多层表头冲突——合并单元格跨多列时，"线性 column_index"概念失效。**正确做法是用列语义 ID**（`closing_carrying_value` / `current_year_increase_purchase` / `aging_within_1y` 等）做绑定锚点。

---

### 问题 3：Word 导出过于简陋（输出层根因）

`note_word_exporter.py` 当前实现的硬缺陷：

- ❌ **只渲染第一张表**——直接读 `note.table_data.headers/rows`，完全无视 `_tables` 数组（P0 bug，53+ 变动章节导出后只剩第一张表）
- ❌ **空 header 列未裁剪**——`["票据种类","期末数","期初数","","","",""]` 导出 7 列空表格
- ❌ 合并单元格 / 多层表头
- ❌ 致同三线表样式（顶 1 磅 + 表头下 1/2 磅 + 底 1 磅）
- ❌ 致同字体规范（仿宋_GB2312 小四 + Arial Narrow）
- ❌ 致同章节标题样式（仿宋小四加粗 + **左缩进 -2 字符**）
- ❌ 致同段落规范（首行不缩进 + 段前 0 段后 0.9 行 + 单倍行距）
- ❌ 致同空值留白（不填 `0` / `-` / `/`）
- ❌ 页眉页脚 / 目录 / 单位说明 / 横向页面

**实测影响**：当前导出的 Word 必须手工排版 4-8 小时才能交付客户。

---

### 问题 4：模板已配置元数据但引擎不消费

| 已存在配置 | 当前行为 | 期望行为 |
|---|---|---|
| `text_sections` 8 段子标题 | `"\n\n".join` 拍扁丢失"每段配一表"语义 | 存 JSON 数组，每段含 title/body/linked_table_index |
| `check_presets` 9 类规则 | 引擎完全不读 | 映射到 `note_validation_engine` 具体规则触发校验 |
| `wide_table_presets` | 未消费 | 控制宽表渲染策略 |
| 部分 row 分组标题 | 按数据行取数全空 | 标 `row_type=header_label` 跳过取数 |

不需要新设计，把已有配置接入校验/UI 就有大量价值。

---

### 问题 5：生成后修改量大（流程层根因）

- 全量生成 173 章节，但中小企业项目大部分章节用不到（金融工具、股份支付等）
- 上年附注的文字内容 90% 可复用，引擎已加载 `prior_notes_cache` 但只用于 `text_content`，table_data 不参照
- AI 续写/改写"现做现用"，未沉淀客户专属模板
- `NoteTrimService` 已有 `get_sections / save_trim / get_trim_scheme / resolve_template_type / _init_from_template`，**没有 `auto_trim` 自动化方法**

---

### 问题 6：双版本切换粗糙

- 切换 SOE ↔ Listed 时，触发 `onGenerate` 重新生成，已编辑内容**丢失**
- `soe_listed_mapping_preset.json` 已存在但**用途是报表项映射**（`report_mapping_service.py:189` 消费），**不是附注章节映射**
- 附注双版本映射需新建独立配置 `note_section_mapping_preset.json`，不要复用现有文件

---

## 三、致同 Word 排版规范（单一真源）

> 实测来源：`附注模版/上市报表附注.md` 第 1-30 行 + `附注模版/国企报表附注.md` 第 1-26 行的"使用说明"段。两份模板规范完全相同。任何 spec/code 引用 Word 排版必须以本表为准。

### 3.1 排版规范对照表

| 维度 | 致同标准（实测） | v1 凭印象写的 | python-docx 实现 |
|---|---|---|---|
| 页边距 | **上 3.2 / 下 2.54 / 左 3 / 右 3.18 cm** | 上 3 / 下 2.54 / 左 3.18 / 右 3.2（左右搞反） | `section.top_margin = Cm(3.2)` |
| 页眉/页脚边距 | 1.3 cm | 未提 | `section.header_distance = Cm(1.3)` |
| 中文字体 | **仿宋_GB2312** | 黑体（标题）/宋体（正文） | `rFonts.eastAsia="仿宋_GB2312"` |
| 中文字号 | **小四统一**，表内必要时降五号 | 标题三号、正文小四 | `Pt(12)` 统一 |
| 数字英文字体 | Arial Narrow | Arial Narrow | `rFonts.ascii/hAnsi="Arial Narrow"` |
| 章节标题区分 | **加粗 + 左缩进 -2 字符**（不靠字号） | Heading 1/2/3 不同字号 | `left_indent=Cm(-0.74)` + `bold=True` |
| 章节标题对齐 | 居左 | 居中 | `WD_ALIGN_PARAGRAPH.LEFT` |
| 正文首行缩进 | **不缩进** | 缩进 2 字符（反） | `first_line_indent=Pt(0)` |
| 正文段落间距 | **段前 0、段后 0.9 行、单倍行距** | 段前 6pt 段后 6pt 1.5 倍 | `space_after=Pt(12*0.9)` |
| 表格后段 | 段前 0.5 行、段后 0.9 行 | 未提 | 单独样式 `NoteAfterTable` |
| 表格三线 | **顶 1 磅 + 表头下 1/2 磅 + 底 1 磅** | 1.5/0.5/1.5 磅 | `sz="8"`=1磅 / `sz="4"`=1/2磅 |
| 表格内字号 | **小四与正文一致**，必要时五号 | 五号 + Arial Narrow | 表内 run 复用正文样式 |
| 表格行高 | **小四单行 0.7cm（397twip）/两行 1.1cm**；五号 0.6/1.0 | 未指定 | `trHeight hRule="exact" val="397"` |
| 表格对齐 | 垂直居中；首列左对齐，其他右对齐 | 类似 | `cell.vertical_alignment=CENTER` |
| 加粗行 | 标题行 + 合计行 | 标题行 + 合计行 | `run.bold=True` |
| **空值/零值显示** | **留白**（不填 `0` / `-` / `/`） | 显示 `-`（反） | `return ""` 而非 `return "-"` |
| 标题行重复 | **不开启**（跨页不重复表头） | 跨页重复 | 不设 `w:tblHeader` |
| 横向页面 | 长期股权投资/在建工程**可设横向**（章节级） | 全纵向（缺） | 新 section + `WD_ORIENT.LANDSCAPE` |
| 单位说明 | 表格上方"金额单位：人民币元"（居右） | 同 | 单独样式 `NoteUnit` |
| 国企版 vs 上市版 | **排版完全相同**（差异在内容） | v1 担心的版式差异不存在 | Word 模板共用一套 |

### 3.2 关键 OOXML 操作

**双字体 rPr 注入**（中文 eastAsia，数字 ascii/hAnsi）：

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def apply_gt_dual_font(run, size_pt: float = 12.0):
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts')) or OxmlElement('w:rFonts')
    rfonts.set(qn('w:ascii'), 'Arial Narrow')
    rfonts.set(qn('w:hAnsi'), 'Arial Narrow')
    rfonts.set(qn('w:eastAsia'), '仿宋_GB2312')
    rfonts.set(qn('w:cs'), 'Arial Narrow')
    rpr.append(rfonts)
    run.font.size = Pt(size_pt)
```

**章节标题左缩进 -2 字符**（致同辨识度核心）：

```python
para.paragraph_format.left_indent = Cm(-0.74)  # 12pt × 2 字符 ≈ 7.4mm
para.paragraph_format.first_line_indent = Pt(0)
para.paragraph_format.space_before = Pt(0)
para.paragraph_format.space_after = Pt(12 * 0.9)  # 段后 0.9 行
para.paragraph_format.line_spacing = 1.0
```

**致同三线表**：

```python
def apply_gt_three_line(table):
    tbl = table._tbl
    borders = OxmlElement('w:tblBorders')
    for edge, sz in [('top','8'), ('bottom','8')]:  # 1 磅
        b = OxmlElement(f'w:{edge}')
        b.set(qn('w:val'), 'single'); b.set(qn('w:sz'), sz); b.set(qn('w:color'), '000000')
        borders.append(b)
    for edge in ['left','right','insideH','insideV']:  # 内部全无
        b = OxmlElement(f'w:{edge}'); b.set(qn('w:val'), 'nil')
        borders.append(b)
    tbl.tblPr.append(borders)
    # 表头行单独加底边 1/2 磅
    for cell in table.rows[0].cells:
        tcPr = cell._tc.get_or_add_tcPr()
        tcBorders = OxmlElement('w:tcBorders')
        bottom = OxmlElement('w:bottom')
        bottom.set(qn('w:val'), 'single'); bottom.set(qn('w:sz'), '4'); bottom.set(qn('w:color'), '000000')
        tcBorders.append(bottom); tcPr.append(tcBorders)
```

**多层表头 grid 二阶段填充**（解决 §2 问题 2，cells.column_index 无法表达 rowspan/colspan）：

```python
def fill_multi_header(table, header_rows: list[list], total_cols: int):
    """多层表头填充：第一遍标记位置/MERGED 占位，第二遍填充 + cell.merge

    header_rows 结构（与 v2 §5.1 对齐）：
    [
        [
            {"text": "项目", "rowspan": 2},
            {"text": "期初余额", "rowspan": 2},
            {"text": "本期增加", "colspan": 2},
            {"text": "本期减少", "colspan": 2},
            {"text": "期末余额", "rowspan": 2},
        ],
        [None, None, {"text": "购置"}, {"text": "在建转入"}, {"text": "处置"}, {"text": "报废"}, None],
    ]
    """
    grid = [[None] * total_cols for _ in range(len(header_rows))]

    # 第一遍：标记每个位置应该放谁，被 rowspan/colspan 占用的格子标 "MERGED"
    for r, row in enumerate(header_rows):
        col = 0
        for cell_def in row:
            if cell_def is None:
                col += 1
                continue
            if isinstance(cell_def, str):
                cell_def = {"text": cell_def}
            while col < total_cols and grid[r][col] is not None:
                col += 1
            rs = cell_def.get("rowspan", 1)
            cs = cell_def.get("colspan", 1)
            grid[r][col] = cell_def
            for rr in range(r, r + rs):
                for cc in range(col, col + cs):
                    if (rr, cc) != (r, col):
                        grid[rr][cc] = "MERGED"
            col += cs

    # 第二遍：填充文本 + 合并单元格
    for r, row in enumerate(grid):
        for c, cd in enumerate(row):
            if cd is None or cd == "MERGED":
                continue
            cell = table.rows[r].cells[c]
            cell.text = ""  # 清空默认 paragraph
            run = cell.paragraphs[0].add_run(cd.get("text", ""))
            apply_gt_dual_font(run)
            run.bold = True  # 表头加粗
            rs = cd.get("rowspan", 1)
            cs = cd.get("colspan", 1)
            if rs > 1 or cs > 1:
                end_cell = table.rows[r + rs - 1].cells[c + cs - 1]
                cell.merge(end_cell)
```

**行高固定 + 关闭标题行重复**：

```python
def apply_gt_row_height(row, cm_value: float = 0.7):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement('w:cantSplit'))
    trHeight = OxmlElement('w:trHeight')
    trHeight.set(qn('w:val'), str(int(cm_value * 567)))  # 567 twip/cm
    trHeight.set(qn('w:hRule'), 'exact')
    trPr.append(trHeight)
    # 不设 w:tblHeader 即关闭跨页重复
```

**空值/零值留白**：

```python
def fmt_amount_gt(val) -> str:
    """致同规范：空值留白，0 也留白"""
    if val is None or val == "": return ""
    try: n = float(val)
    except (ValueError, TypeError): return str(val)
    if n == 0: return ""
    if n < 0: return f"({abs(n):,.2f})"
    return f"{n:,.2f}"
```

**章节级横向页面**：

```python
from docx.enum.section import WD_ORIENT, WD_SECTION

def add_landscape_section(doc):
    s = doc.add_section(WD_SECTION.NEW_PAGE)
    s.orientation = WD_ORIENT.LANDSCAPE
    s.page_width, s.page_height = s.page_height, s.page_width
    return s
```

### 3.3 模板文件由 Python 脚本生成（不手工绘制）

`scripts/build_note_export_template.py` 一次性生成 `backend/data/note_export_template.docx`，写入仓库。好处：

- 样式定义在脚本里清晰可见
- 改样式只需改脚本，不用反复打开 Word
- 单测可断言每个样式的字体名/字号/缩进/边框值

### 3.4 docx 样式命名空间规约

避免与 Word 内置样式（Heading 1/Normal/Table Grid 等）冲突，所有自定义样式统一加 **`GTNote`** 前缀（与项目前端 `Gt*` 组件命名空间相呼应，Word 样式名习惯用全大写前缀）：

| 样式类别 | 样式名 | 用途 |
|---|---|---|
| 段落 | `GTNoteHeading1` / `GTNoteHeading2` / `GTNoteHeading3` | 章节标题（小四加粗 + 左缩进 -2 字符，三级共用） |
| 段落 | `GTNoteBody` | 正文（小四 + 首行不缩进 + 段后 0.9 行） |
| 段落 | `GTNoteAfterTable` | 表格后段（段前 0.5 行 + 段后 0.9 行） |
| 段落 | `GTNoteUnit` | 金额单位说明（居右） |
| 字符 | `GTNoteNumberRun` | 数字字符样式（Arial Narrow） |
| 表格 | `GTNoteThreeLine` | 三线表（顶 1 磅 + 表头下 1/2 磅 + 底 1 磅） |
| 单元格（dev 可选） | `GTNoteFormulaCell` | 含公式的单元格背景浅绿 `#F0FFF0`（仅 dev 模式开启，正式版默认关闭） |
| 单元格（审计版可选） | `GTNoteManualCell` | 用户手工修改过的单元格灰色边框（审计追溯用） |

**关于公式/手工标记的渲染策略**：
- 默认正式版导出**不渲染** `GTNoteFormulaCell`/`GTNoteManualCell`（保持视觉与致同标准模板一致）
- 通过导出参数 `?annotate_formulas=true` 开启 dev 标注（项目经理审稿用）
- 通过导出参数 `?annotate_manual=true` 开启手工修改标注（审计追溯用，留在底稿包不进对外报告）

**CI 卡点**：`scripts/check_docx_style_names.py` 扫描 `note_export_template.docx` 的 `styles.xml`，断言所有自定义样式名以 `GTNote` 开头，没有 `Heading 1`/`Heading 2` 等 Word 内置样式被覆盖。

### 3.5 验收基准（11 项断言）

`附注模版/{上市,国企}报表附注.md` 本身就是验收基准。任意 5-10 个典型章节渲染为 docx 后比对：

1. 中文仿宋_GB2312 / 数字 Arial Narrow
2. 字号小四 12pt 统一
3. 章节标题左缩进 -2 字符
4. 正文首行不缩进
5. 段前 0、段后 0.9 行
6. 表格三线（1 + 1/2 + 1 磅）
7. 表格内行高（小四 0.7cm）
8. 空值/零值留白
9. 标题行不重复
10. 页眉左公司名、右"财务报表附注"
11. 页边距上 3.2 / 下 2.54 / 左 3 / 右 3.18

---

## 四、附注模版目录结构与可消费资源

`附注模版/` 目录已就位 8 份模版文档（共 1.1MB），是改进方案的**核心已有资源**，不是从零开始：

| 文件 | 大小 | 用途 | 改进方案如何消费 |
|------|----:|------|------------------|
| `上市报表附注.md` | 519 KB | 上市版正文模板（含表样+占位文字+提示括号） | 章节结构与排版规范的真相来源；`scripts/import_note_md_to_template.py` 解析为 JSON 模板 |
| `国企报表附注.md` | 303 KB | 国企版正文模板 | 同上 |
| `上市版科目对照模板.md` | 7.6 KB | 每个表格的**校验角色**标注（[余额]/[宽表]/[交叉]/[其中项]/[描述]） | 直接驱动 `note_validation_engine` 选择规则 |
| `国企版科目对照模板.md` | 28.7 KB | 国企版表格校验角色 | 同上 |
| `上市版宽表公式预设.md` | 6.4 KB | 宽表横向公式（期初±变动=期末，category_sum 分类合计） | 给宽表渲染器的列角色（label/opening/movement/closing/data/total）+ 符号（+/-/=） |
| `国企版宽表公式预设.md` | 10.8 KB | 同上（国企版长股投/固定资产/无形资产/在建工程/递延所得税等） | 同上 |
| `上市版校验公式预设.md` | 72.7 KB | 全量校验公式逐表逐编号（账龄衔接/其中项加总/纵向勾稽/跨科目） | `note_validation_engine` 规则定义的真相来源 |
| `国企版校验公式预设.md` | 163 KB | 同上（国企版） | 同上 |

### 4.1 模版含的关键设计已成型，**不要重新发明**

读完上市版宽表公式预设的前 80 行，发现致同自己已经把宽表设计语言定义清楚了：

**列角色**（每列在表格中的功能）：
- `label` — 项目标签列（首列，不参与计算）
- `opening` — 期初余额（公式起点）
- `movement` — 变动项（带 `+/-` 符号参与累加）
- `closing` — 期末余额（公式终点 `=`）
- `data` — 数据列（分类合计型，按列累加）
- `total` — 合计列（分类合计型的 `=` 列）
- `skip` — 不参与公式（如减值准备期初/期末单列）

**两种宽表布局**：
- **movement 型**（长股投、开发支出等）：行=被投资单位，列=变动项 → 横向公式 `期初 + 各 movement = 期末`
- **category_sum 型**（上市版固定/使用权/无形资产）：行=变动项目，列=资产类别+合计 → 横向公式 `各类别列之和 = 合计列`，纵向公式 `账面价值 = 原值 - 折旧 - 减值`

**校验角色**（每张表格在校验体系中的位置）：
- `[余额]` — 取合计行 vs 报表余额（仅纯取合计的简单表）
- `[宽表]` — 横向公式（合计行隐含余额核对）
- `[纵向]` — 多段表纵向勾稽（原值-折旧-减值=账面价值）
- `[交叉]` — 同科目多表间金额核对
- `[跨科目]` — 不同科目间金额核对
- `[其中项]` — 明细行之和=合计行
- `[二级明细]` — 报表二级子明细 vs 附注明细表
- `[完整性]` — 数据行非空校验
- `[账龄衔接]` — 期末账龄段 ≤ 期初前一段（合理性）
- `[LLM审核]` — 文本合理性，规则引擎兜不住
- `[描述]` — 纯描述性表格，不参与数值校验

**互斥规则**：`[余额]` 与 `[其中项]`/`[宽表]` 互斥。

### 4.2 模版含的硬约定（直接落到引擎实现）

读上市版校验公式预设的"前言"段，致同已经定义了**通用规则**，引擎实现必须遵守：

1. **其中项校验通用规则**：`sum(合计行以外的所有明细行) = 合计行`，按每个数值列独立校验，不硬编码具体子项名称；只一行数据（无明细可加总）则**自动跳过**
2. **账龄衔接通用规则**：引擎需自动识别表格中实际的账龄分段（3 段/5 段/其他），按顺序逐段衔接：中间段 `期末 ≤ 期初前一段`，末段（兜底）`期末 ≤ 期初同段 + 期初前一段`
3. **账龄"其中"细分**：父子关系自动识别，子项之和=父项，合计行=各父项之和（不含子项避免重复）
4. **期末/期初合并表 vs 拆分表自动适配**：同科目下两个结构相同、标题分别含"期末/期初"的表 → 拆分表模式；一张含期末+期初的宽表 → 大表模式按列分组校验
5. **组合计提多子表自动识别**：同"组合计提"标题下多个独立子表，交叉校验时合计行求和，其中项校验时各子表独立校验
6. **行名匹配规则**：先精确 → 去前缀（"其中："/"减："）→ 去空格 → 全半角统一 → 同义词适配（"库存商品"="产成品"="库存商品（产成品）"）

这 6 条规约**不是改进方案要新设计的**，是直接在引擎里实现的契约。

### 4.3 上市版与国企版的真实差异（颠覆 v1 的"另起炉灶"假设）

读上市版科目对照模板第 27-90 行：上市版主要是引用国企版结构，**只列出差异科目**（设定受益计划净资产/固定资产/使用权资产/无形资产/股本/库存股 等）。两版结构高度共享：

- **绝大多数科目**结构完全一致（货币资金/应收/存货/合同资产/...等约 50 个科目）
- **上市版差异**集中在 ~10 个科目：
  - 固定资产/使用权资产/无形资产 → category_sum 型（国企版 movement 型）
  - 股本（对应国企版"实收资本"）
  - 库存股（上市版特有）
  - 设定受益计划净资产（上市版特有）
  - 交易性金融负债（上市版宽表，国企版简单余额表）
- **校验公式预设**也是引用国企版编号（如 F1-F58 大部分共用），仅差异科目列完整公式

**含义**：双版本切换不需要"全量另存一份"，而是 **国企版作为基线 + 上市版差异覆盖层**。`note_section_mapping_preset.json` 应该是稀疏映射（只列差异），不是稠密全表。

### 4.4 校验公式预设 .md → DSL 函数的对应关系

`附注模版/{soe,listed}版校验公式预设.md` 中的公式表达（人类可读）必须翻译为 §1.5 已有的 DSL 函数（机器可执行），不要新发明语法。映射示例：

| 致同 .md 公式表达 | 翻译后的 DSL 表达式 | 对应校验角色 |
|---|---|---|
| 期末余额 = 期初余额 + 本期增加 - 本期减少 | `=ROW(R, "opening") + ROW(R, "increase") - ROW(R, "decrease")` | [宽表] 横向公式 |
| 账面价值 = 原值 - 累计折旧 - 减值准备 | `=ROW(R_orig, C) - ROW(R_dep, C) - ROW(R_imp, C)` | [纵向] 多段表勾稽 |
| 合计行 = sum(明细行) | `=SUM(ROW(detail, C))` | [其中项] 通用规则 |
| 期末"1-2 年" ≤ 期初"1 年以内" | `ROW(R_aging_1_2, "closing") <= ROW(R_aging_1, "opening")` | [账龄衔接] 不等式 |
| 附注合计行 = 报表余额 | `ROW(total, C) == TB("货币资金", "期末余额")` | [余额] 跨表核对 |

**实施位置**：Sprint 1.5 (§5 Sprint 1.5) 沉淀 DSL 时附带写"`note_validation_rules.json` → DSL 函数翻译器"（`note_formula_generator.py:translate_validation_rule`），Sprint 4 接入 `check_presets` 时直接消费翻译后的 DSL 表达式。

---

## 五、改进方案

### Sprint 0：模板治理 + Word P0 bug（前置必做，1 人天）

**0.1 模板治理脚本** `scripts/cleanup_note_templates.py`（一次性）：

- 删 `headers` 中的空字符串占位（约 800+ 处，影响 Word 导出列数）
- 统一 `section_number` 格式：含中文编号的拆为 `section_number="四、"` + `subsection_number="固定资产"`
- 给每个 row 打 `row_type`：`header_label`（label 与 headers[0] 同字面，不取数）/ `data` / `subtotal` / `total` / `dynamic_detail` / `formula`
- 输出 diff 报告，让审计师一次 review 通过

**0.2 Word 导出 P0 bug 修复**（30 分钟）`backend/app/services/note_word_exporter.py`：

```python
# 当前：只渲染第一张表（多表章节导出后 53+ 个章节只剩一张）
# 修复：优先取 _tables 数组，逐张渲染
tables_to_render = note.table_data.get("_tables") or [note.table_data]
for tbl in tables_to_render:
    if tbl.get("name"):
        doc.add_heading(tbl["name"], level=3)  # 多表章节加表名 H3
    self._render_table(doc, tbl)

# 同时裁掉空 headers + 同步裁列
headers = [h for h in tbl.get("headers", []) if h and str(h).strip()]
```

**0.3 验收**：固定资产/应收票据等多表章节导出，5 张表全部出现且无空列。

---

### Sprint 1：数据绑定层 + 列语义识别（核心改造，5-6 人天）

#### 1.1 新建 `backend/data/note_template_bindings.json`

模板继续用现有 `note_template_soe.json`（173 章节零迁移），**新建独立绑定文件**承载数据映射：

```json
{
  "version": "2026-1",
  "bindings": {
    "八、22": {
      "wp_code": "F-1",
      "tables": [
        {
          "table_index": 0,
          "table_name": "项目-账面价值",
          "header_normalize": [
            {"text": "项目", "semantic": "row_label"},
            {"text": "期末账面价值", "semantic": "closing_carrying_value"},
            {"text": "期初账面价值", "semantic": "opening_carrying_value"}
          ],
          "rows": {
            "固定资产": {
              "row_type": "data",
              "binding": {
                "closing_carrying_value": {
                  "source": "trial_balance", "field": "audited_amount",
                  "account_codes": ["1601","1602"], "agg": "sum_minus", "abs_for": ["liability"],
                  "mode": "auto"
                },
                "opening_carrying_value": {
                  "source": "trial_balance", "field": "opening_balance",
                  "account_codes": ["1601","1602"],
                  "mode": "auto"
                }
              }
            },
            "合计": {"row_type": "subtotal", "formula": "sum(detail)", "mode": "auto"}
          }
        }
      ]
    }
  }
}
```

**支持的 source 类型**：

| source | 含义 | 数据表 | 实施代价 |
|---|---|---|---|
| `trial_balance` | 期末/期初余额 | TrialBalance.audited_amount / opening_balance | 现成 |
| `ledger_sum` | 本期发生额（含 period_filter: year_range/month_range/date_range） | TbLedger.debit_amount / credit_amount | 现成 |
| `aux_balance` | 辅助核算余额 | TbAuxBalance | 现成 |
| `aux_ledger_aging` | 账龄分桶（从 TbAuxLedger.voucher_date 反推天数） | TbAuxLedger 复合查询 | 中等（无 balance_date 字段） |
| `formula` | 单元格公式（横向公式表内引用） | 表内引用 | 现成 |
| `prior_year_note` | 上年附注值（期初余额回填） | 上年 DisclosureNote | 现成（已有 prior_notes_cache） |
| `manual` | 手工录入 | — | 现成 |

注意点：
- **不要加 `direction` 字段**：TrialBalance.audited_amount 已合并借贷，资产正/负债负在 `account_category` 层面；负债类附注用 `abs_for: ["liability"]` 表示"取绝对值"
- **不要用 column_index**：多层表头跨列时线性 index 失效，统一用 **列语义 ID**

#### 1.1.1 持久化结构：渐进兼容现有 `_cell_modes` 行级 dict（关键事实修订）

> ⚠️ **本节修订**（2026-05-26）：v2 早期版本设计了 `row.cells = [{value, mode, manual_value, semantic}]` 单元格对象数组结构，但 **grep 实测发现前后端已运行的真实结构是行级 `_cell_modes` dict**（`note_wp_mapping_service.py:175`、`note_formula_generator.py:278`、`triple_format_adapter.py:152`、`DisclosureEditor.vue:1205`）。改用单元格对象数组会**强制重写 5 处前端取数函数 + 2 个后端服务 + 已部署的两个 API 端点**（`POST /clear-formulas` / `POST /restore-auto`）。本节改为**渐进兼容**：保留行级 dict 不动，新增字段以 sidecar 形式存在。

**真实持久化结构（已运行，必须兼容）**：

```python
row = {
    "label": "银行存款",
    "values": [12345.67, 11000.00],            # ← 数值数组（前端核心字段）
    "_cell_modes": {                            # ← 行级 dict，key 是列 index 字符串
        "0": "auto",                            # 自动取数
        "1": "manual",                          # 用户手工修改，保留不覆盖
        "2": "locked"                           # 用户锁定整格，连公式都不算
    },
    "is_total": False,
    "formula_type": "opening_plus_changes"      # ← 行级横向公式类型（前端 1095 行用）
}
```

**v2 在此基础上**新增 sidecar 字段（不动现有字段，老代码读到未知字段忽略即可）：

```python
row = {
    # ───────── 现有字段，前端老代码继续用，禁止破坏 ─────────
    "label": "银行存款",
    "values": [12345.67, 11000.00],
    "_cell_modes": {"0": "auto", "1": "manual"},
    "is_total": False,
    "formula_type": "opening_plus_changes",

    # ───────── v2 新增 sidecar，老代码读到未知字段忽略 ─────────
    "row_type": "data",                         # Sprint 0 模板治理产物：data/header_label/subtotal/total/dynamic_detail/formula
    "_cell_meta": {                              # 单元格级元数据（不混入 values，避免破坏前端取数函数）
        "0": {
            "manual_value": null,               # 用户手工值原始备份（恢复自动提数时反查）
            "semantic": "closing_balance",      # 列语义 ID（与 §5.1 binding 对齐）
            "binding_id": "F22-1.col1"          # 绑定到哪条规则（可选）
        },
        "1": {
            "manual_value": 11000.00,           # 用户改前是 12000.00，存这里供"恢复"
            "semantic": "opening_balance",
            "binding_id": "F22-1.col2"
        }
    }
}
```

**字段语义**（v2 新增的 sidecar 字段）：

| 字段 | 类型 | 含义 | 引擎重生成行为 |
|---|---|---|---|
| `row_type` | string | 行类型（Sprint 0 治理产出） | 不变 |
| `_cell_meta[i].manual_value` | number\|null | 用户手工值的原始备份 | 永不覆盖 |
| `_cell_meta[i].semantic` | string | 列语义 ID（与 header_normalize 对齐） | 不变 |
| `_cell_meta[i].binding_id` | string\|null | 来自 `note_template_bindings.json` 的规则编号 | 不变 |

**引擎重新生成（generate_notes / update_note_values）规则（与现有逻辑兼容）**：
- `_cell_modes[i] == "auto"`：按 binding 重新计算，写入 `values[i]`，更新 `_cell_meta[i].binding_id`
- `_cell_modes[i] == "manual"`：保留 `values[i]` 不覆盖（用户已手工修改）；如果 `_cell_meta[i].manual_value` 为空则把当前 `values[i]` 写进去做备份
- `_cell_modes[i] == "locked"`：连 `values[i]` 都不重算，连同公式跳过

**为什么必须这样设计**：
1. 前端 5 处取数函数（`getCellValue/getCellMode/recalcHorizontalFormula/isFormulaMismatch/onClearAllFormulas`）已运行，改 schema 全要重写
2. 后端 `note_wp_mapping_service.py` 的 `clear-formulas`/`restore-auto` 两端点直接操作 `_cell_modes` dict，已被 `DisclosureEditor.vue:279-280` 按钮调用
3. `triple_format_adapter.update_note_from_structure` 在 `_cell_modes` 上做 round-trip，是 Excel/HTML/JSON 三式联动的真源
4. 用户在 UI 上手工改了某个数字（如不同意自动取数），现有逻辑直接覆盖 `values[i]` 没有原值备份，**`_cell_meta[i].manual_value` 是 v2 新功能的真正价值**（支持"恢复自动提数"按钮回到原始值）

**不再做的事**（v2 早期错误设计已撤销）：
- ❌ 把 `values` 升级成 `cells = [{value, mode, manual_value}]` 单元格对象数组
- ❌ 把 `_cell_modes` 收敛进 `cells[i].mode`
- ❌ 单独的 `cells[i].semantic` 字段（改放 `_cell_meta[i].semantic`）

#### 1.1.2 数据迁移脚本（Sprint 1 上线必须配套，幂等）

`scripts/migrate_disclosure_notes_to_v2.py`：

```python
# 把历史 DisclosureNote.table_data.rows[i] 升级为含 row_type + _cell_meta 的 sidecar 结构
# 完全不动 values / _cell_modes / formula_type / is_total / label，前端零感知

def migrate_row(row: dict, headers: list, binding: dict | None) -> dict:
    # 已升级过则跳过（幂等）
    if "_cell_meta" in row and "row_type" in row:
        return row

    # 1) 推断 row_type（Sprint 0 治理已加，这里兜底）
    if "row_type" not in row:
        if row.get("is_total"):
            row["row_type"] = "total"
        elif (row.get("label") or "").strip() == (headers[0] if headers else "").strip():
            row["row_type"] = "header_label"
        else:
            row["row_type"] = "data"

    # 2) 构造 _cell_meta（sidecar，不动 values）
    values = row.get("values", [])
    cell_modes = row.get("_cell_modes") or {}
    cell_meta = row.get("_cell_meta") or {}
    for i, v in enumerate(values):
        if str(i) in cell_meta:
            continue  # 已存在不覆盖
        mode = cell_modes.get(str(i), "auto")
        cell_meta[str(i)] = {
            "manual_value": v if mode == "manual" else None,  # manual 时备份当前值
            "semantic": _guess_semantic(headers, i, binding),  # 从 binding 反查或启发式推断
            "binding_id": _guess_binding_id(row, i, binding),
        }
    row["_cell_meta"] = cell_meta
    return row
```

**验证迁移成功**：迁移后 `row` 同时含 `values` / `_cell_modes` / `_cell_meta` / `row_type` 四组字段，前端老代码读 `values + _cell_modes` 仍能跑（零回归），后端新代码可读 `_cell_meta` 拿 binding/semantic（v2 新功能）。

#### 1.2 列语义识别引擎 `backend/app/services/note_column_semantics.py`

把 header 字面标准化到 20+ 个标准语义 ID：

| header 字面（含模糊匹配） | 语义 ID | 默认取数路径 |
|---|---|---|
| 期末余额/期末数/期末账面价值 | `closing_balance` | TrialBalance.audited_amount |
| 期初余额/期初数/期初账面价值 | `opening_balance` | TrialBalance.opening_balance |
| 本期增加/本年增加/期间增加 | `current_year_increase` | TbLedger.debit_amount sum (year filter) |
| 本期减少/本年减少 | `current_year_decrease` | TbLedger.credit_amount sum |
| 1 年以内/1-2 年/2-3 年/3 年以上 | `aging_bucket_<N>` | aux_ledger_aging |
| 计提比例/坏账比例 | `provision_ratio` | formula |
| 备注/原因/说明 | `manual_text` | manual |

**核心价值**：53 个变动表 80% 列绑定可自动生成，剩余 20% 由审计师在前端 UI 补全。

#### 1.3 引擎改造 `disclosure_engine._build_table_data`

```python
async def _build_table_data(self, project_id, year, table_template, *, binding=None):
    if binding:
        return await self._build_with_binding(project_id, year, table_template, binding)
    # 兼容层：无绑定时降级当前 label 字符串匹配（保留 1-2 个迭代）
    return await self._build_legacy(project_id, year, table_template)
```

#### 1.4 模板绑定一次性生成脚本

90 张"3 列标准表"（约 60% 章节）用脚本基于 `wp_account_mapping.json` 88 条映射半自动生成（30 分钟）。50+ 变动表必须人工标列语义（一次性，1.5 人天）。

#### 1.5 校验公式预设 .md → JSON 预解析（Sprint 1 前置 0.5 人天）

`附注模版/{soe,listed}版宽表公式预设.md` 共 17.2KB + `{soe,listed}版校验公式预设.md` 共 235.7KB 是**未结构化 Markdown**，引擎不能直接消费。Sprint 1 启动前先跑一次解析脚本：

`scripts/parse_validation_preset_md.py`（一次性，输出后纳入 git）：

```python
# 解析两份 .md 文件，输出按"科目编号-表格序号-公式编号"索引的 JSON
# - backend/data/note_validation_rules.json   ← 全量校验公式
# - backend/data/note_wide_table_preset.json  ← 宽表列角色 + 符号

# JSON 示例（按 §4.1 列角色 + §4.2 引擎契约对齐）：
{
    "soe": {
        "F22-1": {  # 固定资产①固定资产情况
            "section": "八、22",
            "table_index": 0,
            "check_role": ["宽表", "交叉"],
            "wide_table_layout": "movement",  // 或 "category_sum"
            "columns": [
                {"text": "项目", "role": "label"},
                {"text": "期初余额", "role": "opening", "sign": "+"},
                {"text": "本期增加", "role": "movement", "sign": "+"},
                {"text": "本期减少", "role": "movement", "sign": "-"},
                {"text": "期末余额", "role": "closing", "sign": "="}
            ],
            "formula": "opening + sum(movement[+]) - sum(movement[-]) = closing"
        }
    }
}
```

**为什么必做**：Sprint 4 的 `check_presets` 接入需要规则定义，规则定义来源就是这两份 .md。如果到 Sprint 4 才解析，会发现公式预设里有边界 case（账龄"其中"细分、组合计提多子表等）需要回到 Sprint 1 改 binding 结构，引发返工。

**输出验证**：解析后核对——上市版宽表覆盖 ~10 个科目（固定/无形/使用权/长股投/开发支出等），国企版覆盖 ~12 个科目，与致同 .md 目录章节数一致。

---

### Sprint 1.5：公式 DSL 沉淀 + 三式联动整合（2 人天）

> 本 Sprint 在 v2 第三次复盘时新增（2026-05-26）。前后端已有完整公式生态（§1.5），Sprint 1.5 的目标是**收敛技术债 + 文档化 + 写 ADR**，不是新建。

#### 1.5.1 公式 DSL 沉淀文档化

在 `backend/app/services/note_formula_generator.py` 头部加 docstring + 新建 `docs/NOTE_FORMULA_DSL.md`，沉淀如下：

| 函数 | 语法 | 含义 | 实现入口 |
|---|---|---|---|
| `=TB("科目名","期末余额")` | TB(account, field) | 试算表余额取数 | `note_formula_generator._resolve_tb` |
| `=TB("科目名","本期借方")` | TB(account, field) | 序时账发生额（field 取借方/贷方） | 同上 |
| `=ROW(R3, "C2")` | ROW(row_id, col_id) | 表内行列引用 | `_resolve_row_ref` |
| `=PRIOR("货币资金","期末")` | PRIOR(account, field) | 上年附注期末值 | `_resolve_prior` |
| `=AGING("应收账款","1年以内")` | AGING(account, bucket) | 账龄分桶（v2 新增，对应 §5.1 `aux_ledger_aging`） | Sprint 1 新建 |
| `=SUM(...)` / `=AVG(...)` | 标准 Excel 函数 | 表内聚合 | `_resolve_aggregate` |

文档化交付物：
- `docs/NOTE_FORMULA_DSL.md`：完整 DSL 语法参考
- `note_formula_generator.py` 头部加 `__doc__` 引用
- 单测覆盖每个函数至少 3 个用例

#### 1.5.2 ConsolNoteTab 重复公式 dialog 收敛

`ConsolNoteTab.vue:424-493` 自实现的公式 dialog 与 `FormulaManagerDialog` 功能 90% 重叠，是历史合并附注开发遗留的技术债。Sprint 1.5 收敛策略：

```vue
<!-- 收敛前（ConsolNoteTab.vue 内部 dialog） -->
<el-dialog v-model="showNoteFormulaDialog" title="公式管理">
  <el-table :data="noteFormulaRules">  <!-- 自实现 -->
    ...
  </el-table>
</el-dialog>

<!-- 收敛后（统一调用全局 FormulaManagerDialog） -->
<FormulaManagerDialog
  v-model="showNoteFormulaDialog"
  :note-section-id="selectedNoteSection?.id"
  :rows="noteFormulaRows"
  :project-id="projectId"
  scope="consol_note"
/>
```

`FormulaManagerDialog` 增加 `scope: 'note' | 'consol_note' | 'report'` prop，按 scope 加载不同规则集。

#### 1.5.3 三式联动单一真源 ADR

新建 `docs/adr/ADR-007-note-triple-format-source-of-truth.md`，明确：

- **DisclosureNote.table_data 是唯一真源**（PG JSONB）
- structure.json 是镜像（Excel 编辑/HTML 渲染时生成）
- xlsx 是导出/导入交换格式
- HTML 报告是只读渲染产物
- 任何写入都必须经过 `triple_format_adapter.update_note_from_structure()` 单入口
- 公式存储位置：`row.formula_type`（行级横向公式枚举） + `note.table_data._formulas`（待 Sprint 1.5 创建的单元格级公式数组）

#### 1.5.4 公式持久化字段定义（与 §1.1.1 sidecar 一致）

`note.table_data` 顶层新增 `_formulas` 数组（不污染 row 结构）：

```python
note.table_data = {
    "headers": [...],
    "rows": [...],
    "_tables": [...],
    "_formulas": [                              # ← Sprint 1.5 新增
        {
            "row": 3, "col": 1,                 # 单元格定位（与前端 row/col 索引一致）
            "expr": '=TB("货币资金","期末余额")', # DSL 表达式
            "binding_id": "F1-1.row3.col1",     # 关联 binding（可选）
            "evaluated_at": "2026-05-26T10:00:00Z"
        }
    ]
}
```

行级横向公式仍走 `row.formula_type`（保留兼容），单元格级公式走 `_formulas` 数组。

---

### Sprint 2：Word 真致同样式（3.5 人天）

**2.1 模板生成脚本** `scripts/build_note_export_template.py`：

按 §3.1 实测规范用 Python 一次性生成 `backend/data/note_export_template.docx`：
- 7 套段落样式（NoteHeading1/2/3、NoteBody、NoteAfterTable、NoteUnit）
- 1 套字符样式（NumberRun = Arial Narrow）
- 1 套表格样式（GtThreeLine = 顶 1 磅 + 表头下 1/2 磅 + 底 1 磅）
- 默认行高 0.7cm exact + cantSplit
- 页面 上 3.2 / 下 2.54 / 左 3 / 右 3.18，页眉页脚 1.3
- 页眉左 `${公司名称}` + 右"财务报表附注"，页脚居中页码

**2.2 NoteWordExporter 重写**：
- 加载 `note_export_template.docx` 而非 `Document()`
- 多表渲染（已在 Sprint 0 修）
- 多层表头支持（rowspan/colspan，通过 grid 二阶段填充 + cell.merge）
- 章节级横向页面（绑定文件标记 `page_orientation: "landscape"` 时插入新 section）
- 双字体 rPr 注入封装函数 + 单测覆盖（11 项断言）

**2.3 验收**：用致同上市版/国企版 .md 模板的 5-10 个典型章节做视觉对比测试，11 项断言全绿。

---

### Sprint 3：智能裁剪 + 上年附注导入 + text_sections 分段（3.5 人天）

**3.1 NoteTrimService.auto_trim**（新增方法，不复用 evaluate）：

```python
async def auto_trim(self, project_id: UUID, year: int, template_type: str) -> dict:
    """启发式裁剪：所有相关科目期末余额=0 的章节标 not_applicable"""
    sections = await self._init_from_template(project_id, template_type)
    binding = self._load_binding(template_type)
    trimmed = []
    for sec in sections:
        # 检查 binding.skip_if_all_zero 列出的科目，TrialBalance 全为 0 → skip
        if await self._all_zero_in_tb(project_id, year, sec.section_number, binding):
            await self.save_trim(project_id, template_type, [{
                "id": sec.id, "status": "not_applicable",
                "skip_reason": "auto_zero_amount"
            }])
            trimmed.append(sec.section_number)
    return {"trimmed_count": len(trimmed), "sections": trimmed}
```

期望中小企业项目 30%+ 章节被自动跳过。

**3.2 上年附注 docx 导入** `POST /api/disclosure-notes/{project_id}/{year}/import-prior-year`：

- python-docx 解析上年 Word（已可用）
- 章节匹配：`section_number` 精确 → 标题 `difflib.SequenceMatcher >= 0.85`（**不**用 fuzzywuzzy，stdlib 即可）
- 表格匹配：行 label 模糊匹配，单元格值按列语义 ID 落入 binding
- 文字内容：整段保留作为本年初稿
- 不匹配的进 `unmatched` 列表前端显示

> **复用现有数据流**：`disclosure_engine._preload_data_for_notes` 已加载 `prior_notes_cache`，`DisclosureEditor.vue:1066-1071` 的 `_getPriorYearValue(_row, rowIndex)` 已实装上年逐行比对 UI。本端点仅负责"把外部 docx 解析后写入数据库的上年记录（year-1 占位 DisclosureNote）"，**不新增前端组件**——写入完成后既有的 priorYearNote 比对自动生效。
>
> 兼容点：上年 docx 解析得到的表格行可能没有 cells 结构，直接产出 `row.values=[...]` 由 §1.1.2 数据迁移脚本同步升级。

**3.3 text_sections 分段化**：

引擎里把 `text_sections` 改存 JSON 数组：
```python
note.text_content = json.dumps([
    {"index": 0, "title": "应收票据分类", "body": "...", "linked_table_index": 0},
    {"index": 1, "title": "坏账准备计提情况", "body": "...", "linked_table_index": 1},
])
```

前端按段渲染（每段独立 TipTap + AI 续写按钮），Word 导出按段插入 H4 + 配套表格。

---

### Sprint 4：双版本切换 + check_presets 接入 + 排版配置（2.5 人天）

**4.1 新建 `backend/data/note_section_mapping_preset.json`**（稀疏映射，§4.3）：

```json
{
  "version": "2026-1",
  "baseline": "soe",
  "mappings": [
    {"soe_section": "八、22", "listed_section": "五、22", "title": "固定资产",
     "data_compatible": false, "layout_change": "movement_to_category_sum"},
    {"soe_section": "八、26", "listed_section": "五、X", "title": "实收资本→股本",
     "data_compatible": true, "field_rename": {"实收资本": "股本"}}
  ]
}
```

**不复用** `soe_listed_mapping_preset.json`（那是报表项映射）。

**4.2 DisclosureEngine.switch_template_type**：

按映射迁移已编辑数据，`data_compatible: true` 直接迁，`false` 标"待人工 review"。

**4.3 check_presets 接入校验引擎**：

`disclosure_engine.generate_notes` 时把模板的 `check_presets` 数组按 `PRESET_TO_RULE` 映射存入 `note.table_data._validation_rules`：

```python
PRESET_TO_RULE = {
    "余额": "BALANCE_TIE",
    "宽表": "WIDE_TABLE_HORIZONTAL",
    "纵向": "VERTICAL_CARRY",
    "交叉": "CROSS_TABLE_TIE",
    "跨科目": "CROSS_ACCOUNT_TIE",
    "其中项": "WHEREOF_SUM",
    "二级明细": "DETAIL_LEVEL2_TIE",
    "完整性": "ROW_COMPLETENESS",
    "账龄衔接": "AGING_PROGRESSION",
    "LLM审核": "LLM_SEMANTIC_REVIEW",
    "描述": "SKIP",
}
```

按 §4.2 的 6 条引擎契约实现规则（其中项通用规则 / 账龄衔接通用规则 / 行名 5 级匹配 等）。

**4.4 NoteFormatConfig 抽出** `backend/app/services/note_format_config.py`：

`@dataclass(frozen=True)` 承载 §3.1 全部 21 项排版参数。前端通过 `GET /api/disclosure-notes/format-config` 拉取，应用到 CSS 变量；Word 导出器同样消费。

---

## 六、实施优先级与工时

| Sprint | 内容 | 工时（人天） | 关键产出 | CI 防回归卡点 |
|---|---|---:|---|---|
| **前置** | 列语义 review + 致同 PDF 视觉基准 + .md 公式预解析 | **1** | 50+ 变动表 binding 草稿 + 5-10 张致同 PDF 截图 + `note_validation_rules.json` + `note_wide_table_preset.json`（§1.5） | — |
| **Sprint 0** | 模板治理脚本 + Word P0 多表渲染修复 + 数据迁移脚本 | **1** | `cleanup_note_templates.py` + `note_word_exporter.py` 修复 + `migrate_disclosure_notes_to_v2.py` | grep `_tables` 必须出现在 `note_word_exporter.py`（防 P0 复发） |
| **Sprint 1** | 数据绑定层 + 列语义识别 + sidecar 持久化结构 + 引擎兼容层 | **5-6** | `note_template_bindings.json` + `note_column_semantics.py` + `_build_with_binding`（保留 `_cell_modes` 行级 dict） | 模板 JSON 中 `account_codes` 引用 = 0；后端单测断言 `row._cell_modes` 行级 dict 兼容 + `row._cell_meta` sidecar 写入 |
| **Sprint 1.5** | 公式 DSL 沉淀 + ConsolNoteTab 重复 dialog 收敛 + 三式联动 ADR + 单元格级公式 `_formulas` | **2** | `docs/NOTE_FORMULA_DSL.md` + ADR-007 + `FormulaManagerDialog` 加 scope prop | grep `noteFormulaRules.value` 在 `ConsolNoteTab.vue` 中应消失（收敛后）；`FormulaManagerDialog` 必须支持 `scope='consol_note'` |
| **Sprint 2** | Word 真致同样式（模板生成 + 多层表头 + 三线表 + 横向页面 + 11 项断言） | **3.5** | `build_note_export_template.py` + 重写 `NoteWordExporter` | 视觉回归 `tests/test_note_export_visual.py` 11 项断言全绿；docx 样式名 grep 必须为 `GTNote*` 前缀 |
| **Sprint 3** | 智能裁剪 `auto_trim` + 上年 docx 导入 + text_sections 分段 | **3.5** | 3 个新端点 + 复用现有 priorYearNote 比对 UI（§3.2 不新增前端组件） | `auto_trim` 单测覆盖率 ≥ 80%；上年 docx 导入端点单测（10 章节样本） |
| **Sprint 4** | 双版本切换稀疏映射 + check_presets 接入 + NoteFormatConfig | **2.5** | `note_section_mapping_preset.json` + `PRESET_TO_RULE` + `note_format_config.py` | `PRESET_TO_RULE` 必须覆盖 `check_presets` 全部 11 个枚举（§4.1） |
| **合计** | | **18.5-19.5** | | 6 项 CI 卡点纳入 `.github/workflows/ci.yml` |

工时上调原因（v1 12-13 → v2 16.5-17.5 → v2 终版 18.5-19.5，+5.5-6.5 人天）：
- 前置 1 人天（v1 完全没算）：列语义 review 0.5d + 致同 PDF 基准收集 0.5d，并入 §1.5 .md 公式预解析
- Sprint 0 前置治理 v1 漏掉，本版加上数据迁移脚本一起做（保 cells round-trip 不丢字段）
- Sprint 1.5（v2 终版新增 2d）：公式 DSL 沉淀 + ConsolNoteTab 收敛 + 三式联动 ADR，**避免新设计破坏已运行的 4 套用户自定义编辑入口**
- 列语义识别引擎是 v1 没考虑的，但避免了"列绑定全靠人工标"的 5+ 人天工作量
- Word 模板生成脚本化（v1 写"设计师手工绘制"是行不通的）

实施顺序建议：
- **第 0 周**：前置 1d（审计师 + 设计基准）— 解决"启动准入"
- **第一周**：Sprint 0（1d）+ Sprint 1（5-6d）— 解决"能不能用"
- **第二周**：Sprint 1.5（2d）+ Sprint 2（3.5d）— 解决"现有功能不被破坏 + 导出像不像致同"
- **第三周**：Sprint 3（3.5d）+ Sprint 4（2.5d）— 解决"自动化够不够"

---

## 七、风险与依赖

### 7.1 数据源风险
- **`ledger_sum` 取数依赖**：必须 dataset active 才能取数；`_resolve_from_ledger` 内显式调 `get_active_dataset_id`，无活跃数据集时返回 0 + warning，不抛异常
- **辅助账龄分桶字段问题**：`TbAuxBalance` 无 `balance_date`，必须从 `TbAuxLedger.voucher_date` 反推；客户未提供辅助序时账时该附注章节自动标 `not_applicable`
- **wp_account_mapping.json 88 条覆盖度**：当前只覆盖主流科目，新行业（金融/能源等）需扩展；改进期间可能暴露 30-50 条新增映射

### 7.2 模板迁移风险
- 173 章节的 binding 文件**必须**经过老审计师人工 review 一次（特别是 50+ 变动表）
- 建议先做"3 列标准表"自动迁移（约 90 个），再人工补"变动表"和"特殊表"（约 80 个）
- 迁移期间引擎兼容层保留至少 1 个迭代，旧结构走老路径，新绑定走新路径

### 7.3 Word 模板风险
- `note_export_template.docx` 由脚本生成，需要 5-10 个真实致同附注做**视觉回归基准**
- 三线表样式在不同版本 Word/WPS 渲染可能有差异，建议 `docx2pdf` 预生成 PDF 截图给客户预览
- 仿宋_GB2312 是 Windows 字体，Linux/macOS 渲染可能 fallback 为仿宋；若客户 Mac 打开会变形，需文档说明（生产环境通常 Windows 不影响）

### 7.4 显式依赖声明（v1 漏掉的）
- `python-docx>=1.2.0` 必须**显式**写入 `backend/requirements.txt`（当前是 `mineru[core]` 间接依赖，未来 mineru 升级可能移除）
- `difflib`（stdlib）即可，不引入 `fuzzywuzzy`/`rapidfuzz` 新依赖
- `docx2pdf` 仅 Sprint 2 视觉回归测试用，不进生产依赖

### 7.5 v1 提案 16 处错误（已修订汇总，不再重复）

v1 字段/方法/路径错误已在 v2 §1-§3 完整修订，主要类别：
- 5 处 ORM 字段名错（TrialBalance/TbAuxBalance 实际字段名）
- 4 处方法名错（`NoteTrimService.evaluate` 等不存在）
- 3 处依赖状态未核验（python-docx/fuzzywuzzy）
- 2 处文件用途误判（soe_listed_mapping_preset 实际用于报表项映射）
- 2 处 Word 排版凭印象写错（黑体/宋体/首行缩进/三线表磅数/零值显示）

### 7.6 前端历史代码兼容期（v2 第三次复盘新增风险）

`DisclosureEditor.vue`（~3500 行）+ `ConsolNoteTab.vue`（~1300 行）+ `StructureEditor.vue`（~900 行）三个组件总计约 **5700 行已运行代码**，含 4 套用户自定义编辑入口（§1.5）。本次改造**禁止破坏现有 round-trip**，硬约定：

1. **新增字段必须 sidecar**：`row_type` / `_cell_meta` / `_formulas` / `binding_id` 等以 sidecar 形式存在，前端老代码读到未知字段应忽略而非报错
2. **保留字段 zero-touch**：`row.values` / `row._cell_modes` / `row.formula_type` / `row.is_total` 字段语义不变，引擎读写规则不变
3. **API 契约不变**：`POST /clear-formulas` / `POST /restore-auto` / `PUT /api/disclosure-notes/{id}` 接口签名不动
4. **公式 DSL 向后兼容**：Sprint 1.5 沉淀的 DSL 函数表是已运行函数的子集，新增 `=AGING()` 等需要保证现有 `=TB()`/`=ROW()`/`=PRIOR()` 行为不变
5. **三式联动入口收敛**：所有 DisclosureNote.table_data 写入必须经过 `triple_format_adapter.update_note_from_structure()`，不能绕过
6. **至少 1 个迭代后才能考虑统一 schema**：观察生产环境 round-trip 数据无回归，再考虑下一步收敛（如把 `_cell_meta` 与 `_cell_modes` 合并）

**验收**：
- Sprint 1 上线后，前端不修改任何代码运行 1 周无回归
- 所有现有按钮（4 个用户编辑入口 + clear-formulas/restore-auto）功能不变
- `tests/test_note_round_trip_compatibility.py` 单测：构造老格式 row → 引擎处理 → 输出仍含 values + _cell_modes + formula_type 全部字段

---

## 八、开放问题（需用户决策）

1. **金额单位档位**：默认"人民币元"，是否支持"人民币万元"档位？影响金额格式化（千分位 → 万元转换）和表头说明（"金额单位"动态生成）
2. **多语言附注**：是否需要中英对照版本？影响 Word 模板设计（双语并排还是分文档）
3. **附注交叉引用**：附注内"详见附注五、3"这类引用，导出时是否自动生成超链接？
4. **AI 生成内容标记**：是否走"AI 生成 + 人工确认"双状态（已有 `wrap_ai_content` 机制可复用）？
5. **变动表"其他变动"差额平衡列**：固定资产/无形资产等变动表是否需要"其他变动"作为差额平衡列？

---

## 九、下一步

如确认本方案方向，建议：

1. **拆 spec 三件套**：`requirements.md`（27-30 个验收标准 + 11 项 Word 断言）+ `design.md`（cells/binding 数据结构 + 模板 docx + 导出器架构图 + 6 条引擎契约）+ `tasks.md`（5 Sprint 共 ~25 个任务）
2. **撰写工时**：spec 三件套 1 人天
3. **实施前依赖确认**：
   - 把 `python-docx>=1.2.0` 写入 `backend/requirements.txt`（**今天就能改**）
   - 老审计师 review 50+ 变动表的列语义（前置 0.5 人天，影响 Sprint 1 进度）
   - 提供 5-10 个真实致同附注 PDF 作为 Sprint 2 视觉回归基准（前置 0.5 人天）

### 9.1 实施前必须先解决的两个问题

**Q1：v2 §3 的 11 项 Word 排版断言由谁来跑？**

建议在 Sprint 2 开始前先用现有 `note_export_template.docx`（如果有）+ 致同 PDF 截图建立**视觉基准库**，每张图标注期望参数（字体/缩进/边框磅数）。后续 CI 可加 `tests/test_note_export_visual.py` 用 `docx2txt` + OOXML 解析做断言。

**Q2：Sprint 1 模板绑定一次性生成脚本由谁标注？**

50+ 变动表（固定资产/无形资产/长期股权投资/递延所得税等）的列语义无法纯靠规则识别（需要审计专业判断），建议：
- 列语义识别引擎先跑一遍生成"AI 建议绑定"
- 老审计师在前端 UI 上**逐章节确认**（每章 2-3 分钟，总计 1.5-2 人天）
- 确认后写入 `note_template_bindings.json`，进入 git

---

## 十、复盘方法论沉淀（v1→v2 的教训）

### 10.1 v1 失误根因（按 memory.md "代码锚定"铁律核验）

1. **凭印象写字段名**（占 8/16 错误）：TrialBalance.audited_debit / TbAuxBalance.balance_date / row.account_codes 等都是凭印象写的，没有 grep 验证
2. **未确认依赖状态**（占 3/16 错误）：fuzzywuzzy / docx2pdf / python-docx 都没有先 `pip list` 验证
3. **未读现有服务方法签名**（占 2/16 错误）：`NoteTrimService.evaluate` 是想当然的方法名
4. **未读真实模板规范**（占 3/16 错误）：Word 排版凭通用 Word 习惯写黑体/宋体/首行缩进 2 字符，没读 `附注模版/*.md` 开头的"使用说明"段

### 10.2 改进规约（沉淀到 memory.md "Spec 工作流规范"）

任何 spec/proposal 的字段/方法/依赖/排版假设必须做四层核验：

1. **模型字段层**：`grepSearch` 实际 ORM 类定义，确认字段名 + 类型
2. **服务方法层**：`grepSearch` 服务类的 `def ` 列表，避免假设方法存在
3. **依赖声明层**：`grep requirements.txt` + `pip list` 双重确认
4. **领域规范层**：`附注模版/*.md` / 致同标准等领域文档作为单一真源，避免凭通用习惯写

每写一个具体字段/方法/排版引用，先做 grep/读规范，再写文档。grep 0 行命中即假设错误。

> **本规约同步到** `.kiro/conventions.md` 的"Spec 工作流规范"章节，作为长期项目规约，不仅限于本次附注改进。`.kiro/steering/memory.md` 也记录了沉淀，但 `conventions.md` 是更长期的规约真源（memory.md 超 200 行时会迁移到 conventions/architecture/dev-history）。

### 10.3 本次复盘价值

16 处错误中 12 处直接影响代码实现，如果带到 design.md 阶段需要 1-2 天返工。**两次代码锚定核验避免了 1.5-2 人天的实施返工**。

### 10.4 致同模板 8 份文档是核心已有资源（v1 完全没识别）

`附注模版/` 1.1MB 的 8 份文档（正文模板 + 校验角色对照 + 宽表公式 + 全量校验公式）是**改进方案的基线**，v1 提案完全没识别这层资源就开始"另起炉灶"设计。v2 的核心思路转变：

- **不是"新建数据绑定层"**——是把致同已定义的列角色（label/opening/movement/closing）落到引擎
- **不是"新建校验规则"**——是把致同已定义的 11 种校验角色 + 6 条引擎契约落到 `note_validation_engine`
- **不是"双版本另起炉灶"**——是国企版基线 + ~10 个差异科目稀疏覆盖

**结论**：v2 的工作量不是"从 0 到 1 设计"，是"从致同领域规范到代码实现"。

---
