# 附注模块与致同 Word 模板差距分析（四方对比）

> 分析日期：2026-06-08  
> 脚本：`backend/scripts/analyze_note_templates.py`、`analyze_note_gap_deep.py`  
> 输出：`backend/scripts/_note_gap_deep.txt`

## 执行摘要

附注模块**尚未与四套致同 Word 模板对齐**，但已建立**唯一对齐层** `note_section_catalog.py`（2026-06-08），禁止三套体系各说各话。

### 统一铁律（强制）

```
唯一主键 section_code = note_template_{soe|listed}.json → section_number
唯一变体键 variant_key = {template_type}_{report_scope} → disclosure_notes/{variant_key}.docx
DB disclosure_notes.note_section = normalize_section_code(section_code)
bindings 查表 = section_code（国企历史五、N → 归一为八、N）
Word Heading 文本（「货币资金」）≠ 主键，仅通过 section_code_index / ##SECTION: 映射
```

| 组件 | 必须走 catalog |
|------|----------------|
| `DisclosureEngine._load_templates` | `filter_template_sections` + `normalize_section_code` |
| `NoteTrimService._load_template_sections` | 同上 |
| `NoteSectionNumberingService` | `section_applies_to_scope`（识别 `consolidated_only`） |
| `NoteWordExporter._detect_level` | `detect_heading_level` |
| 模板填充（Phase 2） | `word_template_relpath(variant_key)` |

| 维度 | 迁移前（咋搞成这样的） | 现已修复 / 目标 |
|------|------------------------|-----------------|
| 导出源 | 程序化 `note_export_template.docx` | Phase 2 → 致同 docx 模板填充 |
| 章节主键 | JSON / bindings / 公式各用不同编号 | **catalog 归一** |
| 单体/合并 | 全量 JSON 187/204 节都生成 | **按 report_scope 过滤** consolidated_only |
| 标题层级 | `八、1` 误判一级标题 | **detect_heading_level** |
| scope 字段 | JSON 写 `consolidated_only` 程序不认 | **section_applies_to_scope** |

### 历史原因（为啥会「三套各说各话」）

1. **附注编辑器**先按 JSON 种子程序化搭建（`section_number` = `八、1`），bindings/公式沿用了更早的 `五、1` 习惯未统一清理。  
2. **Word 模板**后入库，是致同 Heading 样式文档，从未打 `##SECTION:`，标题行也不带 `八、1` 字样。  
3. **NoteWordExporter** 另起炉灶用空白 GTNote 壳排版，`_detect_level` 按西方 `5.1` 规则写，与中文编号无关。  
4. **`consolidated_only`** 在 JSON 里标了 27+22 节，但生成/裁剪/编号**从未读取**该字段。

这不是「设计如此」，是**三条线并行开发未收口**；现已用 catalog 收口，Word 打标仍在 Phase 0。

---

## 一、四套 Word 模板实测

| 文件 | 段落 | 表格 | Heading1 | 与 JSON 标题匹配* |
|------|------|------|----------|-------------------|
| `soe_standalone.docx` | 1331 | 246 | 11 | 154/187 |
| `soe_consolidated.docx` | 1390 | 264 | 14 | 184/187 |
| `listed_standalone.docx` | ~4200+ | 431 | 多 | 179/204 |
| `listed_consolidated.docx` | ~4200+ | 435 | 多 | 200/204 |

\*按 JSON `section_title` 在 Word 全文搜索，非严格块对齐。

### 1.1 Word 文档结构（与 JSON 不同）

**JSON 种子**用扁平 `section_number`：

```
一 → 一、1 公司基本情况
四 → 四、会计期间 / 四、企业合并 …
八 → 八、1 货币资金 / 八、2 应收票据 …
```

**Word 模板**用 **Heading 样式层级**，大章**常无**「一、」前缀：

| Word 样式 | 示例 | 对应 JSON 概念 |
|-----------|------|----------------|
| Heading 1 | 财务报表编制基础、税项、**财务报表主要项目注释** | 合成大章 `二` `六` `八` |
| Heading 2 | 本期纳入合并报表范围的子公司基本情况（仅合并版） | `七、…` consolidated_only |
| Heading 3 | 货币资金、应收账款、合并财务报表编制方法 | `八、1` 或 `四、子节` |
| Heading 4 | 金融工具的确认和终止确认、账面原值 | 表内子标题 / 政策子段 |
| Normal | 政策正文、**【提示】**、（说明…） | `text_sections` / 待删除 |

**关键**：Word 中「货币资金」是 **Heading 3**（国企）或 **Heading 2**（上市），**不出现** `八、1` / `五、1` 字样；编号由程序 `{{seq:八}}` 生成。

### 1.2 单体 vs 合并 Word 差异

| 对比 | 独有段落数 | 结论 |
|------|-----------|------|
| soe_standalone vs soe_consolidated | 单体 2 / 合并 56 | 合并版多「纳入合并范围子公司」「反向购买」等 Heading2 块 |
| listed_standalone vs listed_consolidated | 单体 1 / 合并 9 | 合并版多「公司财务报表主要项目注释」引用合并附注五 |

**问题**：两套 Word 文件 **~95% 相同**；单体版仍含大量合并政策正文（如「合并财务报表编制方法」），须 Phase 0 用 `##OPT:consolidated_only##` 或 `##SECTION:` + 生成时按 `report_scope` 裁剪。

### 1.3 原始范例残留（Phase 0 必删）

四套模板均含：

- 文首「**使用说明**」（国企明显；上市含大量【提示】）
- `【…】` / `（…删除）` / `（注：…）` 编制指引
- 范例年度 `2025`、占位公司 `XX`

上市版段落量约为国企 3–5 倍（政策全文展开更细）。

---

## 二、JSON 种子 vs Word vs 程序

### 2.1 章节清单

| 来源 | SOE | 上市 |
|------|-----|------|
| JSON sections | 187 | 204 |
| JSON `consolidated_only` | **27** | **22** |
| JSON `standalone_only` | 0 | 0 |
| bindings 键 | 152（69⊂SOE，86⊂Listed） | |

`consolidated_only` 示例（SOE）：

- `四、企业合并`、`四、合并财务报表编制方法`
- `七、本期纳入合并报表范围的子公司基本情况`
- `七、重要非全资子公司情况` …

上市 `consolidated_only` 另含 **`十六、应收票据` / `十六、应收账款`**（母公司报表注释）。

### 2.2 编号体系冲突（历史债）

| 概念 | 国企 SOE | 上市 Listed |
|------|----------|-------------|
| 货币资金 `section_number` | **`八、1`** | **`五、1`** |
| 财务报表项目大章 | **八** | **五** |
| 旧映射/公式/测试 | 仍用 **`五、1`** | `五、1` 一致 |

`note_template_variant_matrix.json` 已正确映射 `semantic_section_id` → 四版本 `number`，但 **未接入** `DisclosureEngine` / `NoteWordExporter`。

### 2.3 程序路径缺口

| 组件 | 问题 |
|------|------|
| `DisclosureEngine._load_templates` | 加载全量 JSON，**不**按 `report_scope` 过滤 `consolidated_only` |
| `NoteWordExporter.export` | 无 `report_scope`；用 `note_export_template.docx`；**非**致同 docx |
| `_detect_level` | `八、1`.split(".")→1 段→**误判为一级标题**（已修，见下） |
| `get_section_numbers` | 接受 `scope` 参数但**未使用** |
| `note_template_variant_matrix.json` | 仅语义导出辅助，主路径未读 |
| `should_skip_empty_section` | 未覆盖 `is_empty=True` |

---

## 三、四方差异对照表（结构级）

| 语义章节 | SOE 单体 JSON | SOE 合并 JSON | 上市 单体 JSON | Word 国企 | Word 上市 |
|----------|--------------|--------------|---------------|----------|----------|
| 货币资金 | 八、1 | 八、1 | 五、1 | Heading3「货币资金」 | Heading2「货币资金」 |
| 合并政策 | —（consol_only 在第四章） | 四、合并财务报表编制 | 三、控制的判断标准… | Heading3 合并财务报表编制方法 | Heading2 合并… |
| 合并范围变化 | — | 七、*（12 节） | 三、在子公司中的权益 等 | 仅 consolidated docx 有 Heading2 子公司表 | 附注七 在其他主体中的权益 |
| 母公司报表注释 | — | — | 十六、*（consol_only） | 无独立章名 | consolidated 有「公司财务报表主要项目注释」 |

---

## 四、处理策略（分阶段）

### Phase 0-A：模板整理（阻塞）

对 **4 份 docx** 分别执行（不可交叉复制）：

1. **删** 使用说明、【】、（删除）范例
2. **打标** `##SECTION:{section_code}##` — `section_code` 取自**对应 JSON** `section_number`（国企 `八、1`，上市 `五、1`）
3. **合并专属块** 包 `##OPT:consolidated_only##` 或独立 `##SECTION:` + `scope=consolidated_only` 写入 `section_code_index.json`
4. **标题行** 用 `{{seq:八}} 货币资金`，不写死「八、1」
5. 运行 `build_section_code_index.py`：Word 块偏移 ↔ JSON ↔ `legacy_aliases`（`五、1`↔`八、1`）

**POC 顺序**（每变体 3 节 + 1 合并节）：

| 变体 | 文字节 | 表格节 | 合并专属节 |
|------|--------|--------|-----------|
| soe_standalone | 一、1 | 八、1 | — |
| soe_consolidated | 一、1 | 八、1 | 七、本期纳入合并报表… |
| listed_standalone | 一、1 | 五、1 | — |
| listed_consolidated | 一、1 | 五、1 | 十六、应收账款（或首节） |

### Phase 0-B：JSON/绑定校准

1. 核对 27+22 个 `consolidated_only` 节在 Word 中是否有对应块；缺的补 SECTION 或标为「仅程序化」
2. `note_template_bindings.json`：为国企键统一以 `八、N` 为准，`五、N` 收入 `legacy_aliases`
3. 扩充 `note_template_variant_matrix.json` 覆盖全部账户节（现仅 ~5 条样例）

### Phase 0.9：程序预修复（模板模式之前）

| 任务 | 状态 |
|------|------|
| `note_section_catalog.py` | ✅ 已实现 |
| `DisclosureEngine` / `NoteTrimService` scope 过滤 + `normalize_section_code` | ✅ 已实现 |
| `NoteSectionNumberingService` + `consolidated_only` | ✅ 已实现 |
| `get_binding_for_section` → `resolve_binding_key` | ✅ 已实现 |
| `detect_heading_level` / `_detect_level` | ✅ 已实现 |
| `get_section_numbers` + `compute_section_numbers` 提取 | ✅ tasks 0.9.2 / 9.1–9.2 |
| `NoteWordExporter.report_scope` + 四路由传参 | ✅ tasks 0.9.3（`deliverable` / `note_export` / `disclosure_notes` / `export_package`） |
| `TemplateManifestLoader` + `build_variant_key` | ✅ tasks 0.9.4 / Phase 1 task 2.1–2.2（lifespan 校验待 2.3） |
| `variant_matrix` 扩充接入 | ✅ POC 三账户（tasks 0.9.5） |
| 四变体 `##SECTION:` POC 打标 | ✅ tasks 0.0.2a–d（11 节入 `section_code_index.json`） |

### Phase 2：模板模式

`NoteWordExporter(mode='template')` 读 manifest 对应 docx → 按 `section_code_index` 填充（见 `template-preparation.md` §二）。

---

## 五、验收标准（附注专项）

- [ ] 四套 docx 无使用说明/【】；每 JSON `section_number`（按 scope 过滤后）有且仅有一个 `##SECTION:`
- [ ] `soe_standalone` 导出**不含**第七章合并范围；`soe_consolidated` **含**
- [ ] `listed_consolidated` 含第十六章母公司注释；`listed_standalone` **不含**
- [ ] 货币资金：国企 DB `note_section=八、1` 填入 Word 正确块；`legacy_aliases` 可匹配旧 `五、1`
- [ ] 程序化导出与模板导出编号一致（`compute_section_numbers`）
- [ ] `analyze_note_gap_deep.py` 标题匹配率：SOE ≥180/187，Listed ≥195/204（按 scope）

---

## 六、相关文件

| 文件 | 角色 |
|------|------|
| `disclosure_notes/*.docx` | 致同原始模板（待整理） |
| `note_template_soe.json` / `note_template_listed.json` | 章节清单权威 |
| `note_template_bindings.json` | 表格取数 |
| `note_template_variant_matrix.json` | 四版本语义映射（待扩充并接入） |
| `note_word_exporter.py` | 当前程序化导出 |
| `disclosure_engine.py` | 附注初始化/树 |


---

## 七、财务报表占位符已知限制（Task 12.1，2026-06-08）

> 脚本：`backend/scripts/prepare_financial_templates.py`（全量泛化）+ `export_cell_mapping_from_xlsx.py`（全量扫描）
> 产物：4 变体 xlsx 内联 `{{row:CODE:current/prior}}` + `cell_mapping.json`（v1，4 变体）

`{{row:CODE:current|prior}}` 占位符方案基于「项目 × 期末/期初（本期/上期）两列」的一维报表模型。
以下两类结构**无法**用该方案表达，已**结构性跳过**（不发明新占位语义）：

### 1. 合并报表「母公司（公司）」列未映射

合并/上市报表的资产负债表、利润表、现金流量表均为四列布局：

| 列 | 含义 | 映射 |
|----|------|------|
| C | 期末/本期 — **合并** | `current` ✅ |
| D | 期末/本期 — 公司（母公司） | **未映射** ❌ |
| E | 期初/上期 — **合并** | `prior` ✅ |
| F | 期初/上期 — 公司（母公司） | **未映射** ❌ |

原因：现有 `current` / `prior` 数据模型仅有「合并」口径两期值，无「母公司」单列字段。
按任务约束**不发明新占位 scheme**；母公司列保留模板原样（空白），待后续若引入母公司口径
数据模型再扩展（可新增 `current_parent` / `prior_parent` 后缀）。

影响变体：`soe_consolidated` / `listed_standalone` / `listed_consolidated`（listed 模板本身即合并及公司双列）。

### 2. 所有者权益变动表 / 资产减值准备情况表（2D 矩阵）

这两张表为二维矩阵布局（行=项目，列=权益组成/增减明细），无「期末/期初」列对：

- 所有者权益变动表：列 = 实收资本 / 其他权益工具 / 资本公积 / 库存股 …（本年金额块）
- 资产减值准备情况表：列 = 年初账面余额 / 本期计提 / 合并增加 / 转回 / 期末 …

`equity_statement` 与 `asset_impairment`（impairment_provision，仅国企变体有）整体跳过占位注入，
保留模板内置 `=SUM` 公式与人工填列。后续如需自动填充，须设计「行×列」二维 cell 映射（非本任务范围）。

### 注入口径汇总（每变体）

| report_type | 注入 | 列探测 |
|-------------|------|--------|
| balance_sheet（主表+续表，同一 report_type 跨两 sheet 按行名匹配） | ✅ | 期末余额/期初余额 |
| income_statement | ✅ | 本期金额/上期金额 |
| cash_flow_statement | ✅ | 本期金额/上期金额 |
| equity_statement | ❌ 2D 矩阵 | — |
| asset_impairment / impairment_provision（仅国企） | ❌ 2D 矩阵 | — |

数据列一律按**表头文字探测**（非硬编码列号）；合计行（`is_total_row`）与公式格（`=`/`data_type=='f'`）跳过；
附注列（col2）与提示性文本列（如数字人民币提示语，col7）从不写入。
