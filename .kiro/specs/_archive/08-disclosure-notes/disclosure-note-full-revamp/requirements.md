# 附注模块全栈改进 — 需求文档

> **版本**：v1.1（2026-05-26 修订：DSL 函数清单与代码事实对齐 + is_stale 字段已存在 + NoteTrimService 已有方法清单）
> **来源**：`docs/DISCLOSURE_NOTE_IMPROVEMENT_PROPOSAL.md` v2.0
> **覆盖**：5 大需求簇 / 59 验收标准 / 173 SOE + 187 Listed 章节

## 角色定义

- **审计助理（auditor）**：日常生成附注、改数字、加备注、导出 Word 给项目经理
- **项目经理（manager）**：复核数字准确性、调整章节裁剪、跨年比对
- **质控（qc）**：复核报告交付前的格式与勾稽
- **合伙人（partner）**：签字时刻最终核对，关心不能再改的 final 状态
- **管理员（admin）**：维护模板基线、绑定规则、Word 样式

---

## R1 数据绑定层（解决"取数公式不精确"）

### R1.1 列语义 ID 驱动取数（替代 label 字符串匹配）

**用户故事**：作为 auditor，我希望固定资产章节的"本期增加"列能自动从序时账取借方发生额，不需要手工填。

**当前痛点**：模板 row 只有 `label` + 可选 `is_total`，引擎靠 `wp_by_account[label]` 字符串匹配 88 条 wp_account_mapping 反查，53 个变动表的"本期增加/减少"列**完全无法**自动取数。

**验收标准**：

1. 新建 `backend/data/note_template_bindings.json`，覆盖 173 SOE + 187 Listed 全部章节，最少含 60% 标准 3 列表的自动绑定 + 50+ 变动表的人工标注绑定
2. 列语义 ID 至少覆盖 20 个标准语义：`closing_balance` / `opening_balance` / `current_year_increase` / `current_year_decrease` / `current_year_provision` / `aging_bucket_within_1y / _1_2y / _2_3y / _3_5y / _over_5y` / `category_subtotal` / `provision_ratio` / `manual_text` / `formula_result` / `prior_year_value` / 等
3. 引擎 `disclosure_engine._build_table_data` 优先读 binding，无绑定时降级到当前 label 匹配（兼容层至少保留 1 个迭代）
4. **53 个变动表的"本期增加/减少"列自动取数命中率 ≥ 95%**（从当前 0% 提升）
5. **整体表格数字准确率 ≥ 95%**（人工抽样 20 个真实项目附注，从当前 60-65% 提升）

### R1.2 七种数据源支持（source 类型）

**用户故事**：作为 auditor，我希望应收账款附注按账龄分桶能自动从辅助序时账反推，固定资产期末从试算表取，本期发生从序时账取，不同列不同来源。

**验收标准**：

6. binding `source` 字段支持七种类型：`trial_balance`（TrialBalance.audited_amount/opening_balance）/ `ledger_sum`（TbLedger.debit_amount/credit_amount + period_filter）/ `aux_balance`（TbAuxBalance）/ `aux_ledger_aging`（TbAuxLedger.voucher_date 反推天数 + bucket_days 配置）/ `formula`（DSL 表达式）/ `prior_year_note`（上年 DisclosureNote 反查）/ `manual`（用户手填）
7. `aux_ledger_aging` 数据源在客户**未提供**辅助序时账时，对应章节自动标 `not_applicable`（不抛错）
8. `period_filter` 支持三种模式：`year_range`（YYYY-MM-DD ~ YYYY-MM-DD） / `month_range`（accounting_period 1-12） / `date_range`（任意日期段，可用 `${current_year}-01-01` 变量）
9. `prior_year_note` 数据源使用现有 `_preload_data_for_notes.prior_notes_cache` 不重复查询；上年无数据时静默返回 None（不阻塞生成）

### R1.3 单元格三态持久化（auto / manual / locked）

**用户故事**：作为 auditor，我手工调整了某个数字（不同意自动取数），下次"重新生成"时这个手工值必须保留，不能被覆盖。

**当前痛点**：`row.values` 直接覆盖，没有 `manual_value` 备份，"恢复自动提数"按钮无法回到原始 auto 值。

**验收标准**：

10. `DisclosureNote.table_data.row` 新增三个 sidecar 字段（不动现有 values/_cell_modes/formula_type/is_total/label）：
    - `row.row_type`：`data` / `header_label` / `subtotal` / `total` / `dynamic_detail` / `formula`
    - `row._cell_meta[i] = {manual_value: number|null, semantic: string, binding_id: string|null}`
    - 老前端代码读到未知字段必须忽略而非报错
11. 引擎重生成（`generate_notes` / `update_note_values`）规则：
    - `_cell_modes[i] == "auto"` → 按 binding 重算 `values[i]` 写入 + 更新 `_cell_meta[i].binding_id`
    - `_cell_modes[i] == "manual"` → **保留** `values[i]`，且若 `_cell_meta[i].manual_value` 为空则把当前 `values[i]` 备份进去
    - `_cell_modes[i] == "locked"` → 连 `values[i]` 都不重算，公式跳过
12. 数据迁移脚本 `scripts/migrate_disclosure_notes_to_v2.py`（一次性 + 幂等）：把所有历史 DisclosureNote.table_data.row 升级为含 `row_type + _cell_meta`；前端老代码读 `values + _cell_modes` 仍能跑零回归
13. CI 单测断言 `row._cell_modes[i] in {"auto", "manual", "locked"}` + `row._cell_meta[i].manual_value` 类型为 number|null

---

## R2 联动机制（解决"附注是孤岛"）

### R2.1 试算表/底稿/调整 → 附注 stale 标记

**用户故事**：作为 manager，试算表导入了新的账套或者助理调整了底稿，我希望附注章节自动标记为"待重算"，看到红点提醒，不要悄悄被新数字覆盖。

**当前现状**（grep 实测）：
- `DisclosureNote.is_stale` 字段**已存在**（commit "F46 / Sprint 7.22: 账套 rollback 后由 event_handlers 标 True"）
- `event_handlers.py::_mark_downstream_stale_on_rollback` 已订阅 `LEDGER_DATASET_ROLLED_BACK` 事件
- 当前痛点：仅 rollback 触发 stale，**其他 3 类上游事件无任何通知**

**验收标准**：

14. `EventBus` 在现有 `LEDGER_DATASET_ROLLED_BACK` handler 基础上**新增 3 类事件订阅**，触发对应 `DisclosureNote.is_stale=true`：
    - `LEDGER_DATASET_ACTIVATED`（账套激活）→ 全部该 project+year 的章节（🆕 新增订阅）
    - `WORKPAPER_REVIEWED`（底稿复核通过 status→review_passed/archived）→ 该底稿关联章节（走 linkage_graph，🆕 新增订阅）
    - `ADJUSTMENT_APPROVED`（调整审批通过）→ 全部该 project+year 章节（🆕 新增订阅）
    - `LEDGER_DATASET_ROLLED_BACK`（账套回滚）→ 已有 `_mark_downstream_stale_on_rollback`，**本 spec 不动**
15. 前端 `DisclosureEditor.vue` 章节列表显示 `🔴` 红点 + tooltip "上游已变更，建议重算"；右键菜单"重算此章节"
16. **重算 != 覆盖手工值**：触发 `update_note_values` 时仍走 R1.3 三态规则，`manual/locked` 单元格不动
17. 用户可一键忽略 stale 标记（`POST /disclosure-notes/{id}/dismiss-stale`），UI 隐藏红点直到下次新事件

### R2.2 附注 → Word 导出 + 报表反查

**用户故事**：作为 partner，我签字前要看附注章节是否引用了今年新增的科目（比如新增了"使用权资产"），希望反查能定位到来源底稿。

**验收标准**：

18. 附注章节渲染时计算"引用清单"：每个 binding.account_codes 写入 `note.referenced_accounts`（数组），与现有 `note-account-mapping-seed` 的 280 条种子互补
19. `linkage_graph_builder` 从 `referenced_accounts` 自动生成 NOTE→TB→WP 双向边（NOTE 模块节点 ≥ 200，从当前 115 提升）
20. 报表 ReportView 添加"附注引用我"侧栏：rowCode → 反查所有引用此报表项的 note_section（双向溯源）

---

## R3 溯源穿透（解决"数字从哪来不可见"）

### R3.1 单元格 → 公式 DSL → 数据源 4 层穿透

**用户故事**：作为 qc 复核员，我点附注里"货币资金 期末余额 1,234.56"右键，希望能看到：① 这个值来自哪条 binding；② 公式是什么；③ 命中了哪些科目；④ 命中底稿明细行 / 序时账记录 / 试算表行。

**当前痛点**：引擎只产数字不存来源，复核全靠肉眼对账。

**验收标准**：

21. `DisclosureNote.table_data.row._cell_meta[i].binding_id` 字段存对应 binding 编号（如 `F22-1.row3.col1`）
22. 新增端点 `GET /api/disclosure-notes/{note_id}/cells/{row_idx}/{col_idx}/trace` 返回完整溯源链：
    ```json
    {
      "binding": {"source": "trial_balance", "field": "audited_amount", "account_codes": ["1601", "1602"], "agg": "sum"},
      "formula_resolved": "=SUM(TB('1601','期末'), TB('1602','期末'))",
      "computed_value": 1234.56,
      "evidence": {
        "trial_balance_rows": [{"account_code": "1601", "audited_amount": 800.00}, {"account_code": "1602", "audited_amount": 434.56}],
        "ledger_sample": [],
        "aux_balance_sample": []
      },
      "computed_at": "2026-05-26T14:00:00Z"
    }
    ```
23. 前端右键菜单"溯源"打开 `CellTraceDialog.vue` 三栏布局：左 = binding 元数据，中 = 公式展开过程，右 = 命中数据行（点击行可跳转到 TrialBalance 页面）
24. 穿透链支持 4 层级跳转：附注 → 公式 → 试算表 → 底稿（点击试算表行 `account_code` 跳到底稿明细）

### R3.2 公式 DSL 文档化（TB / WP / REPORT / cell / SUM + PRIOR / AGING）

**用户故事**：作为 admin，新增章节时我要写公式，需要完整 DSL 语法手册。

**当前现状**（grep `note_formula_generator.py` 实测）：
- 入口函数：`generate_formulas_for_table(table_template, check_presets, ...)`（**不是**早期 spec 误写的 `execute_note_formulas`）
- 已有 5 个 DSL 函数：`TB / WP / REPORT / cell / SUM`
- 不存在 `=ROW(R3,"C2")` 函数（v2 文档曾误写，实际是 `cell(row, col)`）
- 不存在 `=PRIOR()` 函数（v2 文档曾误写，本 spec 新建）
- 不存在 `=AGING()` 函数（本 spec 新建）

**验收标准**：

25. 新建 `docs/NOTE_FORMULA_DSL.md` 完整 DSL 语法参考，至少覆盖 7 个函数：
    - **已有 5 个**（仅文档化，不改实现）：
      - `TB("科目名", "期末余额")` / `TB("应收账款", "期初")`：试算表取数
      - `WP("D-1", "main", "B5")`：底稿单元格取数（wp_mapping 优先）
      - `REPORT("BS-1", "期末")`：报表行码兜底取数
      - `cell(row, col)`：表内单元格引用（用于横向公式）
      - `SUM(start:end, col)`：纵向求和
    - **🆕 本 spec 新建 2 个**：
      - `PRIOR("货币资金", "期末")`：上年附注期末值（复用 `_preload_data_for_notes.prior_notes_cache`）
      - `AGING("应收账款", "1年以内")`：账龄分桶（从 TbAuxLedger 反推 voucher_date）
26. `note_formula_generator.py` 头部 `__doc__` 引用 NOTE_FORMULA_DSL.md
27. 每个 DSL 函数至少 3 个单测用例（覆盖正常 / 缺数据降级 / 边界）
28. CI 卡点：grep `noteFormulaRules.value` 在 `ConsolNoteTab.vue` 应消失（公式管理 dialog 收敛到 `FormulaManagerDialog` 后）

---

## R4 自定义编辑（解决"模板硬编码改不了"）

### R4.1 StructureEditor 编辑表样（已存在，本 spec 完善）

**用户故事**：作为 auditor，本年项目新增了"递延收益"章节，模板没有，我希望直接在 UI 里加一个新表格，定义列、绑定数据源，不用等开发改代码。

**当前现状**：`StructureEditor.vue` 已实装（85% 屏占比 fullscreen dialog），但只支持改现有表的行列，不能新增章节/新增表格。

**验收标准**：

29. **新增章节** UI：DisclosureEditor 工具栏"➕ 新增章节"按钮，弹出对话框输入：section_number / section_title / account_name / scope (both/standalone_only/consolidated_only) / sort_order
    - 新章节存到 `custom_note_template_{project_id}.json` （项目级覆盖）
    - 与基线模板 union 后传递给 generate_notes
30. **新增表格** UI：StructureEditor 内"➕ 加表"按钮，输入：table_name / headers / rows[]（label/is_total）
31. **新增列 + 绑定** UI：StructureEditor 选中表格 → "➕ 加列" → 输入 header 文字 → 选择列语义 ID（下拉框含 R1.1 的 20 个标准语义 + "manual"） → 自动生成 binding 草稿
32. **删除自定义条目** UI：右键"删除此章节/表格/列"二次确认 + 进回收站（30 天保留）

### R4.2 FormulaManagerDialog 编辑公式（已存在，本 spec 完善）

**用户故事**：作为 admin，预设的 binding 不满足我的需求，希望直接在 UI 里写自定义公式。

**当前现状**：`FormulaManagerDialog.vue` + `StructureEditor.vue:166` 双 Tab 已实装，但 ConsolNoteTab.vue:424 有重复实现（技术债）。

**验收标准**：

33. **三套公式 dialog 收敛到 FormulaManagerDialog**：
    - 删除 `ConsolNoteTab.vue:424` 的内置 dialog
    - `FormulaManagerDialog` 加 `scope: 'note' | 'consol_note' | 'report'` prop
    - `StructureEditor.vue:166` 双 Tab 保留（"已有公式列表" + "表格结构"），dialog 内复用 FormulaManagerDialog 组件
34. **DSL 公式编辑器** UI：
    - 函数名下拉（=TB / =ROW / =PRIOR / =AGING / =SUM 等）
    - 参数输入框含 autocomplete（科目名从 wp_account_mapping 自动补全）
    - 实时预览公式展开结果（类似 Excel 函数编辑栏）
35. **公式 round-trip 不丢字段**：保存 → 重新打开 → 完整恢复（含 source / period_filter / agg / abs_for / mode 全字段）

### R4.3 自定义模板与基线隔离（不冲突）

**用户故事**：作为 auditor，我新增的"递延收益"章节，下次升级基线模板时不要被覆盖；同事改了基线，我的自定义不能丢。

**验收标准**：

36. `custom_note_template_{project_id}.json` 存项目级 sections 数组，与 `note_template_{soe,listed}.json` union 时遵守：
    - `section_number` 冲突 → 用户自定义优先（覆盖基线该章节）
    - 新增章节按 `sort_order` 插入
    - 项目模板更新基线时，**不**触碰 custom_note_template
37. 项目级模板支持版本（version + updated_at），可回滚到任意历史版本
38. 项目导出（含模板备份）→ 项目导入（含模板恢复）→ 自定义内容完整还原

---

## R5 Word 导出致同样式（解决"输出不像致同"）

### R5.1 多表渲染 P0 修复（Sprint 0）

**用户故事**：作为 auditor，应收票据章节有 12 张表，固定资产有 5 张，导出 Word 后必须 5/12 张全部出现。

**当前痛点**：`note_word_exporter.py` 只读 `table_data.headers/rows`，**无视 `_tables` 数组** → 53+ 多表章节导出后只剩第一张表。

**验收标准**：

39. `note_word_exporter.py` 优先取 `note.table_data._tables` 数组逐张渲染，多表章节加 H3 表名标题
40. **空 header 列裁剪**：`["票据种类","期末数","期初数","","","",""]` → 渲染前过滤为 3 列
41. CI 卡点：grep `_tables` 必须出现在 `note_word_exporter.py`

### R5.2 致同排版规范单一真源（Sprint 2）

**用户故事**：作为 partner，导出的 Word 必须和致同 2025 标准模板视觉一致，否则会被客户质疑专业性。

**实测来源**：`附注模版/上市报表附注.md` + `附注模版/国企报表附注.md` 开头"使用说明"段（两版规范完全相同）

**验收标准**：

42. 21 项排版规范（详见 `docs/DISCLOSURE_NOTE_IMPROVEMENT_PROPOSAL.md` v2 §3.1）必须严格遵守：
    - 页边距 上 3.2 / 下 2.54 / 左 3 / 右 3.18 cm，页眉页脚 1.3 cm
    - 中文字体仿宋_GB2312 小四（不是黑体/宋体），数字 Arial Narrow
    - 章节标题加粗 + **左缩进 -2 字符**（`Cm(-0.74)` 精算），不靠字号区分层级
    - 正文首行**不缩进**，段前 0、段后 0.9 行、单倍行距
    - 三线表 顶 1 磅 + 表头下 1/2 磅 + 底 1 磅（python-docx `sz="8"` / `sz="4"`）
    - 行高固定值 0.7cm（397 twip）+ cantSplit 防跨页
    - **空值/零值留白**（不填 `0` / `-` / `/`）
    - **不开启**标题行重复（`w:tblHeader` 不设）
    - 长期股权投资/在建工程等可设页面横向（章节级配置）
43. `scripts/build_note_export_template.py` 一次性生成 `backend/data/note_export_template.docx`（**Python 脚本生成不手工绘制**）
44. docx 自定义样式名统一加 `GTNote*` 前缀（`GTNoteHeading1` / `GTNoteBody` / `GTNoteThreeLine` 等），CI 卡点 grep 验证
45. **多层表头支持**（rowspan/colspan）：固定资产变动表的"本期增加→购置/在建转入"二级表头通过 `fill_multi_header` grid 二阶段填充实现
46. **公式/手工标记可选渲染**：`?annotate_formulas=true` 开启 `GTNoteFormulaCell` 浅绿背景，`?annotate_manual=true` 开启 `GTNoteManualCell` 灰边框；正式版默认关闭

### R5.3 11 项视觉验收断言

**用户故事**：作为 admin，我要 CI 自动验证导出的 Word 真的是致同样式，不能依赖人眼。

**验收标准**：

47. `tests/test_note_export_visual.py` 至少 11 个断言（基于 5-10 个真实致同 PDF 截图基准）：
    1. 字体名（中文仿宋_GB2312 / 数字 Arial Narrow）
    2. 字号（小四 12pt 统一）
    3. 章节标题左缩进 -2 字符（Cm(-0.74)）
    4. 正文首行不缩进（first_line_indent=Pt(0)）
    5. 段前 0、段后 0.9 行（space_after=Pt(10.8)）
    6. 表格三线（顶/底 sz="8" / 表头下 sz="4"）
    7. 表格内行高（trHeight 0.7cm exact）
    8. 空值/零值留白（fmt_amount_gt(0) == ""）
    9. 标题行不重复（无 w:tblHeader）
    10. 页眉左公司名、右"财务报表附注"
    11. 页边距上 3.2 / 下 2.54 / 左 3 / 右 3.18

---

## 非功能性需求

### NF1 性能

48. 173 章节 SOE 项目"重新生成"耗时 ≤ 30 秒（当前实测 ~25 秒，不退化）
49. Word 导出 150 章节项目耗时 ≤ 60 秒
50. CellTraceDialog 溯源端点响应 ≤ 500ms（PG + Redis 缓存）

### NF2 兼容性

51. 前端老代码（DisclosureEditor / ConsolNoteTab / StructureEditor 共 ~5700 行）零修改即可运行，新字段全部 sidecar 形式
52. 历史数据库 DisclosureNote.table_data 升级幂等（迁移脚本可重复运行）
53. 双 storage 目录（仓库根 storage/ + backend/storage/）路径硬编码不变

### NF3 可观测性

54. `linkage_graph_builder` NOTE 模块节点 ≥ 200（从当前 115 提升）
55. `EventBus` 触发的 stale 标记带 traceId，可在 Redis 中查询近 7 天事件
56. CellTraceDialog 溯源失败时日志含完整 binding_id + project_id + cell_pos

---

## 测试矩阵

### 后端测试

| 类型 | 文件 | 至少用例数 |
|------|------|-----------|
| 单测 | `test_disclosure_engine_v2.py` | 30 |
| 单测 | `test_note_column_semantics.py` | 20 |
| 单测 | `test_note_formula_dsl.py`（5 函数 × 3 用例） | 15 |
| 单测 | `test_note_word_exporter_visual.py`（11 项断言） | 11 |
| 集成 | `test_note_stale_event_chain.py`（4 事件 × 2 路径） | 8 |
| 集成 | `test_note_cell_trace.py` | 5 |
| PBT | `test_note_persistence_property.py`（_cell_modes 三态） | 4 |

### 前端测试

| 类型 | 文件 | 至少用例数 |
|------|------|-----------|
| Vitest | `DisclosureEditor.cell-trace.spec.ts` | 5 |
| Vitest | `StructureEditor.add-section.spec.ts` | 5 |
| Vitest | `FormulaManagerDialog.scope.spec.ts` | 4 |
| Playwright | `e2e-disclosure-revamp.spec.ts`（5 流程） | 5 |

### 真实数据 UAT

57. 至少 3 个真实项目（陕西华氏 SOE / 安徽骨科 SOE / 1 个 Listed 上市样本）跑完整 173/187 章节生成 + 导出 Word
58. 老审计师人工核对 20 章节数字准确率 ≥ 95%
59. partner 视觉对比致同 PDF 11 项断言全绿

---

## 范围边界（不在本 spec）

| 不做项 | 原因 / 后续 spec |
|--------|------------------|
| 国企↔上市双版切换内容迁移 | v2 §5.4，独立 spec：`disclosure-template-bilingual-switch` |
| AI 续写质量提升 | LLM 链路改造在 phase3 UAT-3 |
| 上年 docx 全量解析导入 | v2 §5.3，独立 spec（本 spec 留小入口）|
| 合并版多家加总附注精确联动 | v2 §4.3 + `note-account-mapping-seed/TD-D` |
| 钉集成通知 | W-3，独立外部对接任务 |

