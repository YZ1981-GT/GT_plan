# 附注模块全维度增强 — 需求文档

> 版本：v0.3（草稿，2026-05-28 三轮扩展）
> 编写：2026-05-28
> 范围：动态表格 + 模板继承 + 合并附注衔接 + 文字段落动态 + 协作锁 + AI 辅助 + 跨年版本 + 多公司基线 11 维全栈增强
> 前置：disclosure-note-full-revamp（已完成 46/47）
> 原则：**能不写死就不写死**，全部支持动态调整

## 一、问题陈述

致同附注模板（国企版 173 章节 / 上市版 187 章节）当前实现存在 **11 个核心维度** 缺陷：

| 维度 | 缺陷 | 用户优先级 |
|------|------|---------|
| **D1 行动态** | rows 数量固定，无法按业务数据 explode | P0 |
| **D2 列动态** | headers 固定，无法新增/删除/调宽列 | P0 |
| **D3 数据源（wp_data）** | 现有 binding 实测 0 条 wp_data，依赖 trial_balance | P0 |
| **D4 多源混合** | 单元格无法同时绑多源（TB + WP + 手工 fallback） | P0 |
| **D5 空内容剔除** | auto_trim 只裁章节，不裁空表/空段 | P0 |
| **D6 集团模板继承** | Sprint 3 仅项目级，无跨项目基线机制 | P0 |
| **D7 文字段落动态** | 会计政策段落是写死字符串，无法按企业类型/规模/法人/币种自动适配 | P0 |
| **D8 合并附注衔接** | `ConsolDisclosureService` 已有 7 章节但与单体附注 173 章节融合粗糙（仅按 sort_order 插入） | P0 |
| **D9 协作锁** | `note_section_lock` 已建表但未与本 spec 动态 UI 集成 | P1 |
| **D10 AI 辅助** | `note_ai.py` 政策生成/续写/改写存在但与动态行/列 / wp_data 不打通 | P1 |
| **D11 跨年版本** | `note_prior_year_import_service` 仅 inherit，无章节级 diff/合并/版本树 | P1 |

## 二、用户需求（按维度展开）

### D1 行动态（要支持的三种模式）

#### 模式 A：固定行
货币资金、资产负债表项目分类（行号固定）

#### 模式 B：动态行（行数与内容均动态）
应收账款前 N 名 / 子公司明细 / 借款明细 / 关联方清单 / 存货分类 / 预计负债事项

#### 模式 C：固定+动态混合
应付职工薪酬（6 类骨架 + 类内动态子项）/ 应交税费（大类固定 + 子项动态）/ 固定资产（7 大类 + "其他"动态）

### D2 列动态（要支持）

- 「+ 添加列」用户定义新列（label / value_type / 是否参与合计）
- 「拖动调宽列」存到 `_columns_meta.width`
- 「合并表头」二级表头（例：上年/本年下分子列 期初/期末）
- 「冻结列」固定首列滚动时不移动

### D3 数据源（5 种全支持，能不写死就不写死）

| source | 用法 | 现状 |
|--------|------|------|
| `trial_balance` | 试算表科目余额 | ✅ 4101 cells |
| `aux_balance` | 辅助账（按 aux_type 自动 explode） | ✅ 已支持但未广泛标注 |
| `aux_ledger_aging` | 辅助序时账反推账龄 | ✅ 已支持 |
| `wp_data` | 底稿 parsed_data | ❌ **0 条** ← 本 spec 核心 |
| `formula` | DSL 引用其他 cell | ✅ 部分支持 |
| `prior_year_note` | 上年附注 | ✅ 已支持 |
| `manual` | 用户手填 | ✅ 已支持 |

### D4 多源混合（新增）

单 cell 可绑「主源 + fallback 链」，按优先级取数：

```json
{
  "primary": {"source": "wp_data", "wp_code": "h08", ...},
  "fallback": [
    {"source": "trial_balance", "account_codes": ["1601"], "field": "audited_amount"},
    {"source": "manual", "default_value": 0}
  ],
  "show_provenance": true  // 单元格右上角显示数据源 chip（WP/TB/手工）
}
```

### D5 空内容三级剔除

| 级别 | 触发 | 行为 |
|------|------|------|
| 章节级（已有） | TB 科目全为 0 | 章节 is_deleted=true，不输出 |
| **表格级（新）** | 单表 rows 数值全为 0/null/'-' | 替换为段落「本期无此项业务」 |
| **段落级（新）** | text_content 空 + 全部表格 is_empty | 章节标题不输出 + TOC 不显示 |

### D6 集团模板继承

详见原 v0.2 设计：`group_note_template_baseline` 表 + `template_lineage` 字段 + apply/diff/sync API。

### D7 文字段落动态（v0.3 新增维度）

会计政策段落不能是写死字符串，必须按以下变量动态填充：

| 变量 | 来源 | 影响段落 |
|------|------|---------|
| `company_type` | wizard_state | "本公司是经...登记成立的有限责任公司" |
| `industry_code` | client master | 行业特定政策（如金融业适用 IFRS 9） |
| `currency` | wizard_state | 记账本位币段落 |
| `consol_level` | project | 单体 vs 合并版本切换 |
| `is_listed` | client master | 上市公司 vs 国企特定段落 |
| `subsidiary_count` | consolidation_models | 合并范围说明（动态拼接子公司清单） |
| `prior_year_data` | prior_notes_cache | "本年度变动情况：..."（自动对比上年） |

设计：政策段落用 **Jinja-like 模板**：

```text
本公司是经{{ registration_authority }}登记注册的{{ company_type | default("有限责任公司") }}，
{% if is_listed %}于{{ list_date }}在{{ list_exchange }}上市，{% endif %}
注册资本为人民币{{ registered_capital | format_amount }}元，
经营范围：{{ business_scope }}。
{% if subsidiary_count > 0 %}
本公司及子公司（以下统称"本集团"）主要从事{{ business_industry }}业务。
{% endif %}
```

### D8 合并附注衔接（v0.3 新增维度）

#### 现状问题

- `ConsolDisclosureService` 提供 7 章节（合并范围/重要子公司/范围变动/商誉/少数股东权益/内部交易抵消/外币折算）
- 与 173 章节融合方式 = 简单按 `sort_order=100+idx` 插入末尾，**章节序号断层**
- 抵销分录 → 子公司单体 TB 与合并 TB 双源差异未在附注披露
- 商誉减值表（H 循环商誉子表）→ 合并附注「商誉」章节未联动

#### 目标设计

| 联动点 | 设计 |
|--------|------|
| **合并范围列表** 实时同步 | 子公司表（consolidation_subsidiaries）变化 → 合并附注「合并范围」章节自动重算 |
| **抵销前后对比披露** | 内部往来抵销前 / 抵销后金额双列展示 |
| **商誉减值与 H 联动** | 合并附注商誉章节 binding 直接绑 wp_h08 商誉子表 |
| **少数股东权益变动** | 与合并工作底稿少数股东权益子表 binding |
| **多层级合并** | parent → 子合并 → 孙合并的多层 lineage（子合并附注的「合并范围」自动汇总到 parent） |

#### 「集团合并附注」与「单体附注」分离 + 衔接

```
单体项目 N 个（df5b8403... / 2aa00f57... 等）
  → 每个项目生成单体附注（173 章节 SOE）
  ↓
合并项目 1 个（parent project，consol_level=2）
  → 合并附注 = 单体附注 ∪ 合并专用 7 章节
  → 抵销/商誉/MI 等单体没有的章节
  → 「合并范围」自动列出纳入子公司
```

### D9 协作锁集成（v0.3 新增维度）

- 现有 `note_section_lock` 表 + `NoteSectionLockService`
- **本 spec 集成**：动态行/列编辑器、集团基线 apply、auto_trim v2 都必须先获锁
- 锁可视化：前端章节列表显示「张三正在编辑」标记
- 锁过期自动释放（5 分钟无心跳）

### D10 AI 辅助（v0.3 新增维度）

- `note_ai.py` 现有：政策生成 / 续写 / 改写 / 完整性检查 / 表达检查
- **本 spec 扩展**：
  - AI 自动建议哪些行该是动态行（基于 TB 辅助账多 aux_code 检测）
  - AI 自动从底稿摘要生成段落（如「重要会计判断」从 H 减值评估底稿摘要）
  - AI 校核 wp_data 取数与 TB 的一致性

### D11 跨年版本（v0.3 新增维度）

- 现有 `note_prior_year_import_service.inherit_from_prior_year` 仅复制
- **本 spec 扩展**：
  - 章节级 version tree（v2024 → v2025，每章节独立分支）
  - 「与上年差异」可视化（章节侧栏显示「7 处变动 / 23 处保留」）
  - 跨年合并范围变化高亮（新增子公司 / 处置子公司）

## 三、验收标准（共 92 项，按 11 维度）

### A. 数据模型层（15 项）

- A.1 `row.row_type` 加 `dynamic_anchor / dynamic_data / dynamic_marker_end`
- A.2 `row.is_dynamic` + `row.region_name`
- A.3 `column.is_dynamic` + `column.column_id` + `column.width` + `column.is_frozen`
- A.4 `_columns_meta` sidecar（含合并表头 `header_path: list[str]`）
- A.5 `_dynamic_regions` sidecar（含 axis=row/column）
- A.6 binding 多源 `primary + fallback` 链
- A.7 binding 7 source 全支持（trial_balance/aux_balance/aux_ledger_aging/wp_data/formula/prior_year_note/manual）
- A.8 wp_data binding 详细字段（wp_code/sheet/extract/row_filter/label_col/value_cols）
- A.9 `note.is_empty` 计算字段（rows 全空 + text 空）
- A.10 `note.template_lineage` jsonb（多层级合并支持）
- A.11 `note.is_local_override` bool
- A.12 `note.text_template_vars` jsonb（D7 段落变量绑定）
- A.13 新建 `group_note_template_baseline` 表
- A.14 新建 `note_section_version_tree` 表（章节版本图）
- A.15 现有 173 章节向后兼容

### B. 后端引擎（25 项）

- B.1 `_expand_dynamic_regions` 行展开
- B.2 `_expand_dynamic_columns` 列展开（含合并表头处理）
- B.3 `aux_balance` 行 explode
- B.4 **`wp_data` 数据源 _extract_wp_table / _extract_wp_cell / _extract_wp_column_sum**
- B.5 多源 fallback 链解析（primary 失败 → fallback 1 → fallback 2 → ...）
- B.6 数据源溯源记录（每 cell 实际从哪个 source 取的）
- B.7 动态行 label 自动填充
- B.8 合计公式自动适配
- B.9 `update_note_values` 兼容动态行/列增删
- B.10 `note_cell_merge` 行+列三态合并
- B.11 `is_empty` 计算
- B.12 `auto_trim_v2` 三级裁剪（章节+表格+段落）
- B.13 集团基线 Service（save / apply / diff / sync）
- B.14 lineage 多层级（parent → 子合并 → 孙合并）
- B.15 PRIOR 跨年动态匹配
- B.16 自定义模板存储扩展（动态行/列）
- B.17 ADR-010 版本化覆盖
- B.18 **D7 文字段落 Jinja 渲染** `_render_text_paragraph(template, vars)`
- B.19 **D8 合并附注章节序号自动适配**（不再写死 sort_order=100+idx）
- B.20 **D8 子公司清单实时拉取**（每次生成附注重新查 consolidation_subsidiaries）
- B.21 **D8 抵销前后双列**（new column "抵销前" / "抵销后" 自动展开）
- B.22 **D9 协作锁集成**（动态行/列/基线 apply 调用 NoteSectionLockService）
- B.23 **D10 AI 自动建议动态行**（service.suggest_dynamic_rows）
- B.24 **D11 章节级版本图** Service（fork / merge / diff）
- B.25 **D11 跨年合并范围变化高亮**

### C. 前端编辑器（22 项）

- C.1 行动态视觉（浅黄底色 + ★）
- C.2 列动态视觉（浅紫底色 + +）
- C.3 「+ 添加明细行」按钮
- C.4 「+ 添加列」按钮
- C.5 列拖动调宽
- C.6 合并表头多级渲染
- C.7 冻结列实现
- C.8 删除右键 + 公式栏多源选项
- C.9 数据源溯源 chip（WP/TB/手工 颜色区分）
- C.10 排序 / 自动重新填充
- C.11 「📦 应用集团基线」对话框 + diff 预览
- C.12 「💾 保存为集团基线」按钮
- C.13 「🔄 同步基线」+ lineage 显示
- C.14 章节级 local override 标记
- C.15 **D7 文字段落变量编辑器**（修改 vars 实时预览段落变化）
- C.16 **D8 合并附注独立 tab**（合并项目下专属，单体不显示）
- C.17 **D8 抵销前后双列折叠展开**
- C.18 **D9 协作锁可视化** 「张三正在编辑」标识
- C.19 **D9 锁冲突弹窗** + 等待/抢占选择
- C.20 **D10 AI 建议侧栏**（AI 建议本章节哪些行该动态化）
- C.21 **D11 上年对比侧栏**（章节级 diff + 合并范围变化）
- C.22 **D11 章节版本树可视化**（git-like 分支图）

### D. Word 导出（12 项）

- D.1 GTNoteDynamicRow 样式
- D.2 GTNoteDynamicCol 样式
- D.3 合并表头 docx 渲染
- D.4 「（不适用的项目请删除）」灰色提示
- D.5 **空表替换段落「本期无此项业务」**
- D.6 **空章节跳过 + TOC 不显示**
- D.7 19 项视觉断言扩展为 27 项
- D.8 集团基线 lineage 备注栏
- D.9 **D7 段落 Jinja 渲染** Word 输出
- D.10 **D8 合并附注独立章节集 + 与单体融合**
- D.11 **D8 抵销前后双列 Word 表格**
- D.12 多公司基线对比 PDF 工具

### E. 集团模板继承（10 项）

- E.1 「保存为集团基线」（partner 权限）
- E.2 基线版本号 v{major}.{minor}
- E.3 child apply baseline → 文字+表样+lineage 复制
- E.4 child local override 标记
- E.5 基线升级通知
- E.6 文字段落 vars 由 child 自动填充（D7 联动）
- E.7 集团/单体模板互转保留 lineage
- E.8 多 child 批量同步基线
- E.9 基线 fork & merge（v2 backlog）
- E.10 child 反哺基线建议（child 改动可建议合并回基线）

### F. 合并附注衔接（5 项，v0.3 新增）

- F.1 ConsolDisclosureService 与 disclosure-note-full-revamp 融合（不再 sort_order=100 写死）
- F.2 子公司清单实时同步
- F.3 抵销前后双列
- F.4 商誉/MI/外币 章节绑 H/G/M 循环底稿（wp_data）
- F.5 多层级合并 lineage 链（孙合并 → 子合并 → 总合并）

### G. 协作 / AI / 跨年（10 项，v0.3 新增）

- G.1 协作锁集成 4 入口（行/列/基线/auto_trim）
- G.2 锁可视化 + 抢占
- G.3 AI 建议动态行
- G.4 AI 段落生成（从底稿摘要）
- G.5 AI wp_data 一致性校核
- G.6 章节级版本树
- G.7 上年差异可视化
- G.8 跨年合并范围变化高亮
- G.9 章节 fork（A 章节用 v2024，B 章节用 v2025）
- G.10 多版本 merge 冲突解决

### F. 兼容与回退（3 项）

- F.1 旧模板按固定模式
- F.2 各维度 feature flag
- F.3 一键回退（清 _dynamic_regions / lineage）

## 四、范围与不做事项

### 必做（v1）

- D1 / D2 / D3 / D4 / D5 / D6 / D7 / D8 / D9 / D10 / D11 全部 11 维核心
- 173 章节中 60+ 动态表 binding
- 30+ wp_data binding（H/G/J/L/D/K/M）
- 20+ 段落 Jinja 模板
- 1 个集团基线 demo（首汽租车 → 重庆和平药房）

### 不做（v1）

- AI 全自动撰写整章节（v2）
- 集团基线 fork & merge（v2）
- 多版本图形化合并工具（v2）
- 跨章节联动（A 加客户 B 同步 — v2）

## 五、性能预算

- 60+ 动态表生成 < 12s
- wp_data 提取 < 200ms / 章节
- 集团基线 apply 60 章节 < 3s
- 上年 diff 全量 < 2s
- AI 建议单章节 < 5s

## 六、依赖与前置

- ✅ disclosure-note-full-revamp 46/47
- ✅ ConsolDisclosureService 7 章节
- ✅ note_section_lock 表
- ✅ note_ai.py 5 端点
- ✅ note_prior_year_import_service
- ⚠ **P-1**：审计师标注 60+ 章节动态区域（1 人天）
- ⚠ **P-2**：审计师标注 30+ 章节 wp_data 绑定（1 人天）
- ⚠ **P-3**：审计师标注 20+ 段落 Jinja 模板（0.5 人天）
- ⚠ **P-4**：致同 PDF 视觉基线（0.5 人天）

## 七、与已完成/进行中 spec 的关系

| 已完成 / 进行中 | 本 spec 扩展 |
|----------------|------------|
| auto_trim 章节级 | 加表格级 + 段落级 |
| 自定义模板（项目级） | 加集团基线（跨项目）+ lineage |
| 空 header 列裁剪 | 加空数据/全空表替换 |
| binding 7 source（设计） | wp_data + multi-source 真接入 |
| ADR-010 版本化 | 覆盖动态 + Jinja 段落 |
| ConsolDisclosureService 7 章节 | 与 173 章节深度融合 + 多层级 lineage |
| NoteSectionLockService | 集成动态编辑入口 |
| note_ai.py 5 端点 | 动态行建议 + 段落生成 + 一致性校核 |
| note_prior_year_import_service | 章节级版本图 |
