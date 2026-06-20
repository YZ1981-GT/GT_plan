# 模板资产整理规范（Phase 0 首要工作）

## 原则

1. **先整理模板，后写代码**。当前仓库里的模板是致同**原始范例**（ABC 公司、示例年度、填写说明），不是可机器填充的资产。
2. **新方案覆盖旧交付件中心**。报告正文不再走 `ReportBodyService` JSON 段落 + `report_body_deliverable.docx`（docxtpl）；整理后的致同 Word 模板才是唯一正文源。
3. **生成时输出干净成品**。说明/提示性材料在整理阶段处理完毕——能删则删，暂需保留的用 `##NOTE:` 标记（生成时自动剥除），**不**留给项目经理在 OnlyOffice 里手工删。

## 提示性表述：在哪一环处理？（分层策略）

**结论先说**：编制类提示应在 **Phase 0 模板整理** 删掉；仅 **业务选用类**（要不要某段）在 **生成时 preview→弹窗→confirm** 由项目经理确认；**复核/EQCR** 不再处理模板提示，只审成品内容。

```
Phase 0 模板整理          生成 preview          生成 confirm           OnlyOffice 编辑        复核/EQCR
     │                        │                      │                      │                    │
  删【】/使用说明          弹窗 OPT 勾选          自动剥 NOTE            只见干净正文          审金额/意见/签章
  范例→{{}}               展示 missing_fields     删未选 OPT 段          人工润色措辞          不碰模板提示
```

### 分层对照表

| 类型 | 示例 | 最优处理环节 | 交互形式 | 是否进入成品 |
|------|------|-------------|----------|-------------|
| **A. 编制说明** | 「使用说明」、国资委【披露要求】原文、（…删除） | **Phase 0 直接删除** | 无 | 否 |
| **B. 选用规则** | 「IPO 时增加××段」 | **Phase 0 删除**；规则写入 `matching_rules` / 业务培训 | 无 | 否 |
| **C. 业务可选段** | 强调事项段、持续经营段、KAM 段 | **生成 preview→弹窗→confirm** | `OptionalSectionDialog` 勾选 | 用户选的才保留 |
| **D. 过渡指引** | 「请填写签字合伙人」、编制备忘 | **Phase 0 优先删除**；暂留则 `##NOTE:…##` | confirm 时**自动剥除**，不弹窗 | 否（另存 guidance 副本仅供下载参考） |
| **E. 数据缺失** | `{{signing_partner}}` 无值 | **preview 返回** `missing_fields` | 弹窗/页内**警告条**，不阻断 confirm | 成品保留 `{{}}` 高亮待补 |
| **F. 合规校验** | 上市公司缺 KAM | **confirm 前校验**（复用 `validate_kam`） | **Toast/警告**，可确认后继续 | 是（带 validation_warning） |
| **G. 附注裁剪** | TB 全 0 章节、用户标「不导出」 | **附注编辑器 + auto_trim_v2**；生成时自动读 DB | **无弹窗** | 裁剪后的章节不进成品 |
| **H. 报表** | 行次无审定数 | **生成时按 mapping 填 blank/0** | 无弹窗；日志记录 | 是 |
| **I. 内容复核** | 金额勾稽、表述是否恰当 | **EQCR/项目复核**（现有复核流） | 复核意见、批注 | 是（人工改 OnlyOffice） |

### 为什么不用「复核环节」处理模板提示？

- 复核人（EQCR）应看到与监管机构相同的**干净出品物**，不应在 Word 里删【】或「使用说明」。
- 模板提示是**编模板阶段**或**生成流水线**的职责；复核只负责**已生成内容**是否正确。
- 若提示留到复核才处理，说明 Phase 0 或 confirm 剥除失败，应修模板/流水线而非加复核负担。

### 为什么不用 OnlyOffice 编辑时弹窗？

- OnlyOffice 打开的是 **confirm 之后** 的正式版（NOTE 已剥、OPT 已裁）。
- 编辑阶段弹窗只适合：**覆盖确认**（重新生成）、**缺失字段提醒**（只读 banner），不适合模板选用类决策——选用应在生成前完成。

### 报告正文推荐交互流（仅类型 C/D/E/F）

```
点击「生成报告」
  → preview API（后台：替换占位符，NOTE 仍在工作副本里）
  → 前端 OptionalSectionDialog
       ├─ 分组展示 OPT 段（默认勾选来自 placeholder_registry）
       ├─ 展示 missing_fields 警告条
       └─ [确认生成] / [取消]
  → confirm API（剥 NOTE、删未选 OPT、写正式 docx）
  → 若有 KAM 警告 → Toast，仍入库
  → 进入交付件中心 → OnlyOffice 编辑（干净版）
```

### 附注 / 报表

| 品类 | 提示处理 | 是否弹窗 |
|------|----------|----------|
| **附注** | Phase 0 删【】/使用说明；裁剪靠 DB 状态 + `auto_trim_v2` | **否**（生成前可在附注编辑器确认章节） |
| **报表** | Phase 0 删范例；无 OPT/NOTE 概念 | **否** |

### Phase 0 整理时的决策口诀

- 问「不同项目答案不一样？」→ **##OPT:** → 生成弹窗
- 问「只给项目组看、不出品？」→ **##NOTE:** 或删 → confirm 自动剥
- 问「所有项目都不要出现在成品？」→ **直接删**
- 问「是披露法规原文抄录？」→ **直接删**（法规不入附注成品）

---

## 当前资产诊断（2026-06-08）

| 类型 | 文件数 | 现状 |
|------|--------|------|
| 报告正文 | 17（15 `.doc` + 2 `.docx` 详简） | 范例公司「ABC」、范例年度、无 `{{}}` / `##OPT:` |
| 附注 | 4 `.docx` | 首段「使用说明」、大量【…】/（…删除）/ 二选一 提示，无 `{{section:}}` |
| 报表 | 4 `.xlsx` | 已有文件，坐标映射 `cell_mapping.json` 待标 |
| manifest | 1 | 14 处仍引用 `.doc`，与「仅 docx」规则矛盾 |

---

## 一、报告正文模板整理

### 1.1 要替换为占位符的内容

| 模板中的范例/空白 | 替换为 |
|-------------------|--------|
| ABC股份有限公司 / ABC公司 | `{{company_full_name}}` / `{{company_short_name}}` |
| 2025、2026 等审计年度 | `{{audit_year}}` |
| 上年年度 | `{{prior_year}}` |
| 2025年1月1日 / 12月31日 | `{{audit_period_start}}` / `{{audit_period_end}}` |
| 报告落款日期 | `{{report_date}}` |
| 致同会计师事务所（特殊普通合伙） | `{{firm_name}}` |
| 事务所地址 | `{{firm_address}}` |
| 签字合伙人姓名 | `{{signing_partner}}` |
| 注册会计师姓名 | `{{signing_cpa}}` |
| 合并/母公司 口径表述 | 保留原文结构，用 `{{report_scope_phrase}}` 或口径替换表处理 |
| 财务报表清单句 | `{{financial_statements_list}}` |
| 治理层（董事会/管理层） | `{{responsibility_organ}}` |

### 1.2 可选段落 — 用 `##OPT:` 包裹

整段包裹，供生成时弹窗确认：

```
##OPT:emphasis:强调事项段##
（强调事项正文范例或空白引导）
##/OPT:emphasis##
```

常见 `section_id`：`emphasis`、`other_matter`、`going_concern`、`key_audit_matters`、`comparative`、`other_information`

### 1.3 说明/提示性材料 — 处理方式

| 类型 | 示例 | 处理 |
|------|------|------|
| 填写指引段落 | 「审计报告格式说明…」 | **删除** |
| 行内选用提示 | 「【IPO申报…时增加…】」 | **删除** |
| 编制提醒（给项目组看） | 「请项目组注意 KAM 至少一项」 | `##NOTE:项目组提示:...##` → 生成时剥除 |
| 目录页 | 「目 录」占位 | 保留结构或删除（按致同出品要求） |
| 范例报告号 | `致同审字（2026）第110ASXXXX号` | `{{report_number}}` 或留空待填 |

### 1.4 格式要求

- 统一另存为 **`.docx`**（`.doc` 全部转换后删除或移入 `_archive/`）
- 不破坏原有样式（字体、缩进、页眉页脚）——只改文字内容或插入标记
- 每个模板整理后跑校验：无裸 `ABC`、`XXXX`、无未标记的「使用说明」

---

## 二、附注模板整理（细则）

### 2.0 Word 模板实测结构（整理前必读）

四套 `disclosure_notes/*.docx` 是致同**原始范例**，与 JSON 种子的组织方式不同：

| Word 实际结构 | JSON 种子结构 |
|---------------|---------------|
| **Heading 1** 大章，常**无**「一、」前缀（如「财务报表主要项目注释」） | 合成大章 `八` + 子节 `八、1` |
| **Heading 2/3** 账户/政策子节（如「货币资金」= Heading3 国企 / Heading2 上市） | `section_number` + `section_title` |
| **Heading 4** 表内行标题（账面原值、期初余额…） | `tables[].name` / 非独立 section |
| **Normal** 政策正文 + 大量【提示】/（说明） | `text_sections`；编制类**删除** |

**单体 vs 合并**：`soe_standalone` 与 `soe_consolidated` 约 95% 段落相同；合并版多 ~56 段（纳入合并范围子公司等 Heading2）。上市同理（合并版多母公司报表注释引用）。单体 Word **仍含**合并政策正文 → 须 `##OPT:consolidated_only##` 或生成时按 `report_scope` 裁块。

详见 [`note-template-gap-analysis.md`](./note-template-gap-analysis.md)。

### 2.0.1 附注联动检查清单（Phase 0 每变体必过）

| # | 检查项 | 通过标准 |
|---|--------|----------|
| 1 | `section_code` = JSON `section_number` | `validate_note_template.py` 零 orphan |
| 2 | `variant_key` 路径 | `catalog.word_template_relpath` 文件存在 |
| 3 | 单体 docx 无 `consolidated_only` 块 | standalone 扫描无第七章合并范围等 |
| 4 | `legacy_aliases` | 国企 `八、1` 含 `["五、1"]` |
| 5 | bindings 可查 | `get_binding_for_section("五、1")` 命中 `八、1` 数据 |
| 6 | 重新生成附注 | 单体项目 DB 无 `consolidated_only` 的 `note_section` |

### 2.1 与程序数据模型的对应关系

附注整理必须和现有附注模块对齐，不能仅按 Word 标题肉眼切块：

| 概念 | 来源 | 模板中用作 |
|------|------|-----------|
| **section_code**（主键） | `note_template_{soe\|listed}.json` → `section_number` | `##SECTION:五、1##`、`{{section:五、1}}`、`{{table:五、1}}` |
| section_id | 同上 → `section_id`（slug） | 仅写入 `section_code_index.json`，**不**写入 Word |
| note_section | DB `disclosure_notes.note_section` | 与 section_code **同字符串** |
| 表格 binding | `note_template_bindings.json[section_code]` | 决定取数语义；模板只保留样式参考 |
| 变体差异 | `note_template_variant_matrix.json` | 国企/上市 × 单体/合并 大章序号可能不同 |

**铁律**：`section_code` = 对应种子 JSON 的 `section_number`（如国企 `八、1`、上市 `五、1`），不是 Heading 文字，也不是 slug。

> **注意：国企 vs 上市大章序号不同**  
> 同一账户「货币资金」在 `note_template_soe.json` 为 **`八、1`**，在 `note_template_listed.json` 为 **`五、1`**。  
> `note_template_bindings.json` 中两套键并存；Word 打标必须以**当前模板对应种子**的 `section_number` 为准，不可照搬范例章号。  
> 历史底稿/公式/映射里残留的 `五、1`（如 `note_wp_mapping_service`）是旧编号体系，POC 阶段需在 `section_code_index.json` 记录 `legacy_aliases` 供 join 兜底。

### 2.2 四套附注 Word 模板

| 文件 | 种子 JSON | 说明 |
|------|-----------|------|
| `disclosure_notes/soe_standalone.docx` | `note_template_soe.json` | 单体；**排除** `scope=consolidated_only`（27 节） |
| `disclosure_notes/soe_consolidated.docx` | 同上 | 含合并章（第七章等） |
| `disclosure_notes/listed_standalone.docx` | `note_template_listed.json` | 单体；**排除** `consolidated_only`（22 节，含第十六章母公司注释） |
| `disclosure_notes/listed_consolidated.docx` | 同上 | 含合并 + 母公司报表注释 |

整理以 JSON 种子的 `sections[]` 为章节清单权威；每个可导出 `section_number` 在**对应变体** Word 中**有且仅有**一个 `##SECTION:…##` 块。

**合并专属块打标**（二选一，推荐 A）：

| 方案 | 做法 |
|------|------|
| A | 单体/合并各维护独立 docx；单体 docx **删除**合并章物理内容 |
| B | 同一物理块包 `##OPT:consolidated_only##`；单体项目生成时裁掉 |

上市合并版「公司财务报表主要项目注释」与 JSON `十六、*` 对齐；国企合并范围见 JSON `七、*`.

### 2.3 章节层级与 `{{seq:}}` 占位符

| level | section_code 例 | 标题行 | seq |
|-------|----------------|--------|-----|
| 1 | `一`（合成大章） | `{{seq:一}}、公司基本情况` | 一、二、三… |
| 2 | `一、1`、`五、1` | `五、{{seq:五}} 货币资金` | 组内 1、2、3… |
| 3 | 更细子节 | `（{{seq:五-1}}）…` | 组内阿拉伯数字 |

- `level=1` 且 `_synthesized=true`：通常仅大章标题，正文在子节 `一、1`
- 组内仅 1 个子节时导出可不编号；模板仍保留 `{{seq:}}`，由程序处理
- 大章下子节全部裁剪 → 删除大章标题行

### 2.4 章节点块标准范式

**纯文字（`content_type=text`）**

```
##SECTION:一、1##
一、{{seq:一}} 公司基本情况
{{section:一、1}}
##/SECTION:一、1##
```

**纯表格（`content_type=table`）**

```
##SECTION:五、1##
五、{{seq:五}} 货币资金
##STYLE_REF:table:五、1##
{{table:五、1}}
##/SECTION:五、1##
```

- 保留 1 张**样式参考表**（表头+边框）；删范例数据行
- `##STYLE_REF:table:…##`：生成时克隆样式，不输出到成品
- 多表：`{{table:五、1:0}}`、`{{table:五、1:1}}`（与 binding `table_index` 对齐）

**文字+表格混合**

```
##SECTION:五、12##
五、{{seq:五}} 应收账款
{{section:五、12}}
{{table:五、12:0}}
##/SECTION:五、12##
```

**封面（SECTION 外）**：`{{company_full_name}}` + 财务报表附注 + `（{{audit_year}}年度）`

### 2.5 必须删除的说明/提示性材料

| 类型 | 特征 | 处理 |
|------|------|------|
| 使用说明节 | 文首至第一个 Heading1 之前 | 整节删除 |
| 披露要求 | `【根据国资委…】`、`【证监会…】` | 删除 |
| 选用提示 | `【适用于…】`、`【二选一】` | 删除 |
| 编辑提示 | `（…删除）`、`（有限，删除）` | 删除 |
| 范例公司/日期 | `XX有限公司`、`XXXX年XX月` | 删范例或改 `{{}}` |
| 项目组备注 | 仅编制用说明 | `##NOTE:…##` 或删除 |

校验：`validate_note_template.py` 拒绝残留 `【`、`使用说明`、`XXXX`。

### 2.6 section_code_index.json（整理产出）

```json
{
  "template_key": "soe_standalone",
  "seed_file": "note_template_soe.json",
  "sections": [{
    "section_code": "八、1",
    "section_id": "chapter-08-monetary-funds",
    "section_title": "货币资金",
    "level": 2,
    "content_type": "table",
    "placeholders": ["{{seq:八}}", "{{table:八、1}}"],
    "binding_wp_code": null,
    "legacy_aliases": ["五、1"]
  }]
}
```

| 字段 | 说明 |
|------|------|
| `section_code` | 种子 `section_number`，Word `##SECTION:` 主键 |
| `legacy_aliases` | 历史旧编号（公式/映射/底稿中的 `五、1` 等）；生成时 join 兜底 |
| `binding_wp_code` | 来自 bindings；可为 null（国企 `八、1` 与上市 `五、1` 的 wp 映射不同） |

**POC 必做章节**（国企 `soe_standalone`）：`一、1`（文字）、`二、1`（文字）、`八、1`（表格，货币资金）。

---

## 三、财务报表模板整理（细则）

### 3.1 Sheet 清单（`soe_standalone.xlsx` 实测）

| 实际 Sheet 名 | report_type | 本期纳入 |
|--------------|-------------|----------|
| `1,2-资产负债表(表01国单` | balance_sheet | 是 |
| `3-利润表(表02国单` | income_statement | 是 |
| `4-现金流量表(表03国单` | cash_flow_statement | 是 |
| `5-所有者权益变动表(表04国单` | equity_statement | 是 |
| `6-资产减值准备情况表(表06国单` | asset_impairment | manifest 标注可选 |
| `GT_Custom` | — | 删除或 `hidden_in_export` |

manifest 或 `sheet_aliases.json` 必须把**实际 sheet 名**映射到 `report_type`（旧代码按中文子串匹配不可靠）。

### 3.2 表头区占位符

| 位置 | 典型内容 | 替换为 |
|------|----------|--------|
| 行1 | 资产负债表 | `{{report_title}}` 或保留固定标题 |
| 行2 | 2025年12月31日 | `{{period_end_date}}` |
| 行3 左 | 编制单位： | `编制单位：{{company_full_name}}` |
| 行3 右 | 金额单位：元 | `金额单位：{{currency_unit}}` |
| 行4 | 项目/附注/期末/期初 | **保留原文** |

利润表、现金流量表日期行用 `{{audit_year}}年度` 或 `{{period_end_date}}` 按模板原句式替换。

### 3.3 数据格占位符（内联 + mapping 双轨）

**内联写入金额单元格（推荐）**

```
C列: {{row:BS-002:current}}     D列: {{row:BS-002:prior}}
B列(可选): {{note_ref:BS-002}}
```

- `row_code` 对齐 `report_config_seed.json` / `financial_report.row_code`（如 `BS-002`=货币资金）
- **仅数据行**写占位符；含 `=SUM(` 的合计行**禁止**写入
- 合并单元格：占位符写在合并区域**左上角**单元格

**cell_mapping.json**（脚本从内联扫描生成或手工维护）

```json
{
  "soe_standalone": {
    "sheet_aliases": {
      "balance_sheet": "1,2-资产负债表(表01国单"
    },
    "headers": {
      "balance_sheet": { "company_name": "A3", "period_end": "A2" }
    },
    "rows": {
      "BS-002": {
        "sheet": "balance_sheet",
        "row_name": "货币资金",
        "current": "C6",
        "prior": "D6",
        "note_ref": "B6",
        "fill_empty_as": "blank"
      }
    }
  }
}
```

程序：**优先**解析 xlsx 内联 `{{row:…}}`；无内联时回退 mapping。

### 3.4 row_code 对齐步骤

1. 打开 `report_config_seed.json` 对应标准行次表
2. 从 xlsx 数据起始行（约第 6 行）逐行对照 **项目列** 与 `row_name`
3. 匹配后在期末/期初列写入 `{{row:BS-xxx:current/prior}}`
4. 合计行确认公式 → 标 `"type": "formula"`，不入 mapping
5. 四套 xlsx **独立**整理坐标，不可复制粘贴 mapping

### 3.5 禁止事项

- 不改动数字格式、合并单元格、打印设置
- 不覆盖公式格
- 删除范例公司名/年度
- 处理掉 `GT_Custom` sheet

### 3.6 报表 POC 验收

- [ ] 资产负债表 ≥20 个 `row_code` 内联占位符
- [ ] 利润表 ≥10 个；≥1 个 SUM 行未被覆盖
- [ ] 表头 `{{company_full_name}}`、`{{period_end_date}}` 已替换
- [ ] `cell_mapping.json` 可由脚本导出且与内联一致

---

## 四、整理顺序（推荐）

```
Step 1  POC 垂直切片
  ├── 1.1 报告：模板A 无保留简版.docx
  ├── 1.2 附注：soe_standalone — 一、1 / 二、1 / **八、1**（货币资金；勿用上市的五、1）
  └── 1.3 报表：soe_standalone — 资产负债表 20 行 + 表头

Step 2  报告正文 17 份 + doc→docx + manifest

Step 3  附注 4 份全量 + section_code_index.json + validate_note_template

Step 4  报表 4 份全量内联占位 + cell_mapping + sheet_aliases

Step 5  manifest 终检 + CI

─── 完成后才写 TemplateFillService / 覆盖旧 deliverable ───
```

---

## 五、POC 验收标准（Step 1）

**报告正文**

- [ ] 无 ABC/XXXX；≥1 个 `##OPT:`；通用 `{{}}` 齐全

**附注**

- [ ] 无「使用说明」/【】残留；`一、1` `二、1` `八、1` 三个 SECTION 块完整（国企种子编号）
- [ ] `八、1` 含 `##STYLE_REF:table:八、1##`；`section_code_index.json` POC 段已填（含 `legacy_aliases` 若需对接旧 `五、1` 映射）

**报表**

- [ ] 表头占位符已替换；BS ≥20 行 `{{row:BS-xxx:…}}`；公式行未覆盖

**通用**

- [ ] docx/xlsx 用 Office 打开格式与原件一致

---

## 六、与旧交付件中心的关系

| 旧组件 | 整理完成后的处置 |
|--------|------------------|
| `audit_report_templates_seed.json`（DB JSON 段落） | 停止作为生成源；可保留只读参考 |
| `ReportBodyService.load_body_template` | 废弃 |
| `report_body_deliverable.docx`（docxtpl） | 废弃 |
| `render_report_body` 单阶段 API | 由新 preview/confirm 替代 |
| `DeliverableService` 版本链/OnlyOffice | **保留** |

**结论**：覆盖的是「报告正文生成方法」，不是整个交付件中心。
