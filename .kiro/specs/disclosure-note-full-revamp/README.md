# 附注模块全栈改进（disclosure-note-full-revamp）

> **创建日期**：2026-05-26
> **来源**：`docs/DISCLOSURE_NOTE_IMPROVEMENT_PROPOSAL.md`（v2.0，1196 行 / 67KB）
> **预计工时**：18.5-19.5 人天，6 Sprint（含前置 1d）
> **关键 commit**：v2 文档 `ccf92da`，三件套 spec 起草中

## 一句话目标

把附注模块从"只能取数填表的工具"升级为"取数 + 联动 + 溯源 + 自动运算 + 手动校验 + 自定义模板 + 致同 Word 导出"全栈财报附注生成系统，覆盖 173/187 章节（SOE/Listed），可对外交付。

## 范围

### 在范围（必做）

1. **数据绑定层**：把模板的 `account_codes` 字符串匹配升级为列语义 ID 驱动的精确取数（trial_balance / ledger_sum / aux_balance / aux_ledger_aging / formula / prior_year_note / manual 七种数据源）
2. **联动机制**：试算表/底稿/调整变更 → 附注 stale → 重算；附注修改 → Word 导出 + 报表反查
3. **溯源穿透**：附注单元格 → 公式 DSL → 试算表/序时账/底稿明细行（4 层级穿透链）
4. **自动运算 + 手动校验设置**：单元格三态 `auto/manual/locked` + 行级 formula_type；用户改值后保留 + 一键清除/恢复
5. **预设科目表格模板 + 自定义编辑**：保留 173/187 章节模板基线 + StructureEditor 编辑表样 + FormulaManagerDialog 编辑公式
6. **自定义增加科目表格**：支持新增章节、新增表格、自定义 binding；与基线模板隔离不冲突
7. **致同 Word 排版规范导出**：仿宋_GB2312 小四统一 / 章节标题 -2 字符左缩进 / 三线表 1+1/2+1 磅 / 空值留白 / 11 项视觉断言

### 不在范围（独立 spec 或后续）

- 国企 ↔ 上市双版本切换的内容迁移引擎（v2 §5.4，留独立 spec）
- AI 续写 / 改写质量提升（已接 vLLM，本 spec 不动 LLM 链路）
- 上年附注 docx 自动解析导入（v2 §5.3，本 spec 留小入口，全功能留独立 spec）
- 合并版（consolidated）多家加总附注的精确联动（v2 §4.3 + `note-account-mapping-seed/TD-D`）

## 三件套结构

```
.kiro/specs/disclosure-note-full-revamp/
├── README.md          (本文件，总览 + 范围 + 关键决策)
├── requirements.md    (~30 个验收标准，5 大需求簇)
├── design.md          (架构图 + 6 Sprint 拆解 + OOXML 操作 + DSL 规约)
└── tasks.md           (6 Sprint × ~35 任务，每个 task 含 [x] 完成态)
```

## 关键设计决策（已锁定）

### D1：渐进兼容现有 `_cell_modes` 行级 dict（不重写）

前后端已运行的 schema 是 `row.values=[number]` + `row._cell_modes={"0":"auto","1":"manual"}` 行级 dict + `row.formula_type` 行级公式类型。**新字段以 sidecar 形式追加**：
- `row.row_type`：data/header_label/subtotal/total/dynamic_detail/formula
- `row._cell_meta[i]`：{manual_value 备份, semantic 列语义 ID, binding_id 绑定规则编号}

理由：避免破坏 `DisclosureEditor.vue:1052-1063` 的 5 个取数函数 + `note_wp_mapping_service.clear-formulas/restore-auto` 两端点 + `triple_format_adapter.update_note_from_structure` 三式联动入口。

### D2：模板与绑定分离

- `note_template_{soe,listed}.json`（173/187 章节）：保持不动，只做 row_type 治理
- `note_template_bindings.json`（新建）：承载 wp_code / table_index / 列语义 / source / mode 的数据绑定层
- 用户自定义模板：`custom_note_template_{project_id}.json`（项目级），与基线 union

### D3：公式 DSL 沉淀（不重新发明）

`note_formula_generator.execute_note_formulas` 已支持 `=TB("货币资金","期末余额")` / `=ROW(R3,"C2")` / `=PRIOR("货币资金","期末")` 等函数。Sprint 1.5 沉淀文档化 + 补 `=AGING("应收账款","1年以内")` 一个新函数。

### D4：致同 Word 模板由 Python 脚本生成

`scripts/build_note_export_template.py` 一次性生成 `backend/data/note_export_template.docx`（不手工绘制）。样式名加 `GTNote*` 前缀避免与 Word 内置冲突。

### D5：联动走 EventBus + linkage_graph_builder

附注作为 NOTE 模块节点已在 `linkage_graph_builder._from_note_account_mapping` 实装（`note-account-mapping-seed` spec 280 条种子），本 spec 不动 graph，只补 stale 标记 + EventBus 订阅。

## 与现有 spec 的关系

| 现有 spec | 关系 |
|---|---|
| `note-account-mapping-seed` | **前置依赖已完成**，本 spec 复用 280 条业务名称种子 |
| `enterprise-linkage` | **前置依赖已完成**，复用 EventBus + linkage_graph_builder |
| `e2e-business-flow` | 本 spec 是 e2e 链路最后一段（附注章节生成）的深化 |
| `template-library-coordination` | 共享模板版本管理基础设施 |
| `audit-chain-generation` | 公式 DSL 沿用其设计 |

## CI 防回归卡点（6 项）

| Sprint | 卡点 |
|---|---|
| S0 | grep `_tables` 必须出现在 `note_word_exporter.py`（防 P0 多表渲染复发） |
| S1 | 模板 JSON `account_codes` 引用 = 0；后端单测断言 `row._cell_modes in {auto, manual, locked}` |
| S1.5 | `noteFormulaRules.value` 在 `ConsolNoteTab.vue` 应消失（重复 dialog 收敛后） |
| S2 | 视觉回归 `tests/test_note_export_visual.py` 11 项断言全绿；docx 样式名 grep 必须 `GTNote*` 前缀 |
| S3 | `auto_trim` 单测覆盖率 ≥ 80%；上年 docx 导入端点单测（10 章节样本） |
| S4 | `PRESET_TO_RULE` 必须覆盖 `check_presets` 全部 11 个枚举 |

## 验收清单（高级别）

- [ ] 173 章节（SOE）+ 187 章节（Listed）数字准确率 ≥ 95%（53 个变动表"本期增加/减少"列**全部**自动取数）
- [ ] 附注单元格右键 → 溯源穿透到试算表/序时账/底稿明细行
- [ ] 试算表改动 → 附注 NOTE 节点 stale → 用户点"重算"刷新（不自动覆盖手工值）
- [ ] 用户在 StructureEditor 中新增章节/新增表格/新增列 → 不影响其他基线章节
- [ ] 用户改某单元格 → 下次"重新生成"保留 manual_value，"恢复自动提数"按钮一键清除
- [ ] Word 导出 docx 与致同标准模板视觉一致（11 项断言）
- [ ] 全部 18.5-19.5 人天工时拆到 6 Sprint，每个 Sprint 完成时 CI 卡点通过

## 依赖与风险

### 依赖
- 致同 8 份模板（`附注模版/*.md` 1.1MB）作为单一真源（已就位）
- python-docx 1.2.0 显式声明到 `requirements.txt`（v2 §7.4）
- LibreOffice 本地安装（仿宋_GB2312/楷体_GB2312/宋体/Arial Narrow 字体）

### 风险
- 50+ 变动表绑定文件需老审计师人工 review 1.5 人天（前置必做）
- 前后端共 ~5700 行已运行代码（DisclosureEditor 3500 + ConsolNoteTab 1300 + StructureEditor 900）round-trip 兼容期至少 1 个迭代
- 真实致同附注 PDF 视觉基准库（5-10 张截图）需老审计师提供（前置 0.5 人天）

## 时间线（建议）

```
第 0 周：前置 1d（审计师列语义 review + 致同 PDF 基准 + .md 公式预解析）
第一周：Sprint 0（1d）+ Sprint 1（5-6d）        — 解决"能不能用"
第二周：Sprint 1.5（2d）+ Sprint 2（3.5d）       — 解决"现有功能不破坏 + 导出像致同"
第三周：Sprint 3（3.5d）+ Sprint 4（2.5d）       — 解决"自动化够不够"
```
