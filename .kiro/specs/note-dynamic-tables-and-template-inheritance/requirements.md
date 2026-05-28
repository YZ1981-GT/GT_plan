# 附注模块全维度增强 — 需求文档

> 版本：v0.6（草稿，2026-05-28 第六轮重组）
> 编写：2026-05-28
> 范围：单体附注修复（主线）+ 合并附注完整开发（联动） + **国企↔上市丝滑切换** **14 维全栈增强**
> 前置：disclosure-note-full-revamp（已完成 46/47）
> 原则：**能不写死就不写死**，全部支持动态调整
>
> **v0.6 关键变更**：
> 1. **重心调整** — 用户原话「主要是修复单体附注模块，合并附注模块内容是连带完成」「支持国企版和上市版的丝滑切换」
> 2. **Phase 化重组** — Phase 1（单体修复主线）/ Phase 2（合并连带）/ Phase 3（高级特性 + 收尾）
> 3. **新增 D14：国企↔上市丝滑切换**（同项目年内切换 + 集团内多模板共存 + 互转无丢失）
> 4. **130 验收 / 36 人天 / 16 Sprint**（v0.5 126 / 34 / 15）

## 一、问题陈述

致同附注模板（国企版 173 章节 / 上市版 187 章节）当前实现存在 **14 个核心维度** 缺陷：

| 维度 | 缺陷 | 用户优先级 | Phase |
|------|------|-----------|-------|
| **D1 行动态** | rows 数量固定，无法按业务数据 explode | P0 | 1 |
| **D2 列动态** | headers 固定，无法新增/删除/调宽列 | P0 | 1 |
| **D3 数据源（wp_data）** | 现有 binding 实测 0 条 wp_data | P0 | 1 |
| **D4 多源混合** | 单元格无法同时绑多源 | P0 | 1 |
| **D5 空内容剔除** | auto_trim 只裁章节，不裁空表/空段 | P0 | 1 |
| **D6 集团模板继承** | Sprint 3 仅项目级，无跨项目基线 | P0 | 1 |
| **D7 文字段落动态** | 写死字符串，无法按企业类型/规模适配 | P0 | 1 |
| **D8 合并附注完整开发** ⭐⭐⭐ | **当前只有 7 合并专用章节，缺少从子公司汇总的 173 共有章节** | **P0** | **2** |
| **D9 协作锁** | 已建表但未集成 | P1 | 1 |
| **D10 AI 辅助** | 与动态/wp_data 不打通 | P1 | 3 |
| **D11 跨年版本** | 仅 inherit，无版本树 | P1 | 3 |
| **D12 合并↔单体映射** ⭐⭐ | **D8 的核心服务，必须先于 D8** | **P0** | **2** |
| **D13 标题序号动态层级** ⭐⭐ | section_number 写死，裁剪不重排 | **P0** | **1** |
| **D14 国企↔上市丝滑切换** ⭐⭐⭐ | **集团下子公司模板可能不同，互转易丢数据** | **P0** | **1** |

## 一、问题陈述

致同附注模板（国企版 173 章节 / 上市版 187 章节）当前实现存在 **13 个核心维度** 缺陷：

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
| **D12 合并↔单体映射** ⭐ | **合并附注模板没有与单体附注科目对应表，集团合并时无法自动从子公司单体附注提数** | **P0** |
| **D13 标题序号动态层级** ⭐ | **`section_number` 是字符串写死（"一、1" / "四、记账本位币"），裁剪后无法自动重排序号；多级层级（一/(一)/1./(1)/①）无法动态调整** | **P0** |

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

### D8 合并附注完整开发（v0.5 升级 ⭐⭐⭐）

#### 现状盘点（grep 实测）

| 模块 | 文件 | 状态 |
|------|------|------|
| 后端 service | `consol_disclosure_service.py` | ✅ 7 章节生成，**但完全不消费子公司单体附注** |
| 后端 schema | `ConsolDisclosureSection` | ✅ 字段简单（section_code/title/content/rows） |
| 前端组件 | `ConsolNoteTab.vue` (1466 行) | ✅ UI 框架完整 + aggregation 弹窗（aggTarget.source=report\|note）|
| 前端集成 | `ConsolidationIndex.vue` Tab 6 | ✅ 已挂载 |
| API | `P_cn.list / consolNoteSections` | ✅ 列表/详情端点 |
| 子公司汇总 | — | ❌ **完全缺失** |
| 章节序号 | sort_order=100+idx | ❌ 写死，与单体冲突 |
| 单体↔合并映射 | — | ❌ **完全缺失** |

#### 核心问题（用户原话："合并附注还没有开发好"）

1. **「合并附注」≠「合并专用 7 章节」**：用户期望的合并附注 = 单体附注 173 章节 ∪ 合并专用 7 章节，且单体章节的数据来自子公司汇总（抵销内部）
2. **当前合并附注章节列表只有 7 项**：用户在 `ConsolNoteTab.vue` 看到的章节树缺少财务报表主要项目注释（货币资金/应收账款/...）
3. **用户在合并附注里手填数字**：因为系统不会自动从子公司单体附注汇总
4. **合并范围变化时合并附注不联动**：删除子公司，合并附注应自动调整范围说明 + 「重要子公司」表

#### v0.5 完整设计（含 D12 映射作为前提）

##### 8.1 合并附注 = 完整章节集

```
合并附注 = (
    单体附注 173 章节（数据来自子公司汇总，章节编号按 scope=consolidated 重排）
    ∪ 合并专用 7 章节（合并范围/重要子公司/范围变动/商誉/MI/内部抵消/外币）
    ∪ 用户自定义章节（如分部信息）
)
```

##### 8.2 全章节生成管线（新）

```
ConsolDisclosureServiceV2.generate_full_consol_notes(parent_project_id, year):
  1. 加载 parent project 的子公司树（consol_tree_service.build_tree）
  2. 对每个共有章节（150+）:
     a. 找 binding（来自 P-5 标注：source=consol_aggregation）
     b. 加载所有子公司单体附注的对应章节
     c. 调用 ConsolNoteAggregationService.aggregate_section
     d. 应用抵销规则（internal_ar / internal_revenue 等）
     e. 写入 parent project 的 disclosure_notes 表（scope=consolidated）
  3. 生成 7 个合并专用章节（保留现有 ConsolDisclosureService 逻辑）
  4. 调用 NoteSectionNumberingService.render_all(scope='consolidated') 重排序号
  5. 文字段落 Jinja 渲染（合并版变量：subsidiary_count / consolidated_revenue / ...）
  6. 保存 + 标记 lineage（合并附注 ← 来自哪些子公司单体）
```

##### 8.3 子公司项目→合并项目数据流

```
子公司项目 A (df5b8403...) — 单体附注 173 章节
子公司项目 B (2aa00f57...) — 单体附注 173 章节
子公司项目 C (...)         — 单体附注 173 章节
              ↓
              ↓ 通过 parent_project_id 链
              ↓
合并项目 (consol_level=2)
  → 合并附注 173 + 7 = 180 章节
  → 货币资金 = A.货币资金 + B.货币资金 + C.货币资金 - 内部抵消
  → 应收账款前5名 = top_n(A前5 ∪ B前5 ∪ C前5, 抵消内部往来后)
  → 子公司清单 = [A, B, C]（自动）
```

##### 8.4 合并附注前端 UI（升级 ConsolNoteTab）

新增功能：

- **章节树显示完整 180 章节**（不只是 7）
- 每个章节显示「来自 N 家子公司」标识
- 单元格点击 → 溯源对话框「A 公司贡献 100 万 + B 公司贡献 50 万 - 内部往来 20 万 = 130 万」
- 「重新汇总」按钮 + 进度条 SSE
- 「单体↔合并切换」按钮（仅显示合并 vs 显示单体的预览模式）
- 合并范围变化 → 红点提示「3 个章节需重新汇总」

##### 8.5 多层合并

```
孙公司 → 子合并 → 总合并

孙公司 X (consol_level=1) — 单体附注
   ↓
子合并 P (consol_level=2) — 合并附注 = 孙公司汇总 + 子合并 7 章节
   ↓
总合并 G (consol_level=3) — 合并附注 = 子合并附注汇总 + 总合并 7 章节
```

每层 lineage 链记录在 `template_lineage` 字段，可追溯。

##### 8.6 与现有 7 章节的关系

| 合并专用章节 | 升级后 |
|-------------|-------|
| 合并范围说明 | 子公司清单实时拉取（已有） |
| 重要子公司 | 自动从 consolidation_subsidiaries 取持股比例（已有，加 wp_data 绑定）|
| 范围变动 | 加跨年对比（合并范围 diff）|
| 商誉 | 绑 H 循环商誉子表（wp_h08）|
| 少数股东权益 | 绑 M 循环 MI 子表 |
| 内部交易抵消 | **抵销前/抵销后双列**（新）|
| 外币折算 | 绑外币 wp_data |

#### 用户需求（D8 v0.5）

- **U31** 合并附注章节树显示完整 180 章节（不只 7）
- **U32** 每个共有章节显示「来自 N 家子公司」+ 各贡献金额溯源
- **U33** 「重新汇总」一键触发 + 进度条
- **U34** 子公司单体附注更新 → 合并对应章节自动 stale
- **U35** 合并范围变化 → 范围说明 + 重要子公司表自动重算
- **U36** 多层合并 lineage 链可视化（孙→子→总）
- **U37** 合并附注与单体附注共用模板 + binding（不另起一套）

### D14 国企↔上市丝滑切换（v0.6 新增 ⭐⭐⭐）

#### 现状盘点（grep 实测）

| 模块 | 状态 |
|------|------|
| 后端 `note_conversion_service.py` | ✅ preview + execute 已存在 |
| 后端 `note_conversion_router.py` | ✅ 路由已注册 |
| 前端切换 UI | ⚠ ConsolidationIndex 有「准则切换器」但未集成单体附注 |
| 切换前预览影响章节数 | ❌ 当前未实现 |
| 互转 round-trip 数据保留 | ❌ 未验证 |
| 集团内子公司不同模板共存 | ❌ 完全缺失 |
| 跨模板合并汇总 | ❌ 完全缺失 |
| 模板差异清单 | ❌ 没有结构化数据 |

#### 用户场景

##### 场景 1：业主中途切换准则

国企转制上市/上市转下市/集团重组时，单一项目的附注准则需要切换。当前流程：
- 切换 → 重新生成全 173/187 章节 → **用户编辑全丢失**

##### 场景 2：集团内子公司不同模板

> 集团 G（合并项目，consol_level=2）
>   ├─ 子公司 A（国企版，103 章节有数据）
>   ├─ 子公司 B（上市版，125 章节有数据）
>   └─ 子公司 C（国企版）
>
> 合并附注按 G 的模板（国企版）汇总：
>   - A 的章节直接复制（同 SOE）
>   - B 的章节需要映射（Listed → SOE 章节对照）
>   - 合并版有但 SOE 没有的字段 → 标 not_applicable

##### 场景 3：合并版与单体版差异

合并附注通常是上市版（监管要求），但子公司可能国企版。当前**无机制处理这种跨准则汇总**。

#### 模板差异清单（量化）

国企版 173 章节 vs 上市版 187 章节：

| 类型 | 数量 | 处理方式 |
|------|------|---------|
| 共有章节（章节标题 + 表样完全一致） | ~150 | 直接复用 |
| 共有但格式略不同（多 1-2 列 / 行不同） | ~10 | 字段级映射 |
| 仅 SOE 有 | ~13 | Listed→SOE 时数据归档 |
| 仅 Listed 有 | ~14 | SOE→Listed 时新建空章节 |

具体差异（需 P-7 审计师确认）：

```
仅 Listed 有：
  - 设定受益计划净资产
  - 库存股
  - 优先股
  - 永续债
  - 上市公司股东大会信息
  - 关联方交易披露的"上市公司特别要求"段落
  ...

仅 SOE 有：
  - 国资委特别披露要求
  - 上缴国库利润
  - 国有资本经营预算
  ...

格式略不同（~10 章节）：
  - 固定资产（SOE: movement 型 / Listed: category_sum 型）
  - 使用权资产（同上）
  - 无形资产（同上）
  - 实收资本/股本（SOE: 实收资本 / Listed: 股本）
  ...
```

#### 设计目标

##### 14.1 互转无丢失（PBT 验证）

```python
def conversion_round_trip_invariant(notes_soe):
    """SOE → Listed → SOE 数据无丢失（用户编辑保留）."""
    listed = convert(notes_soe, target='listed')
    back_to_soe = convert(listed, target='soe')

    for section in notes_soe:
        if section.has_user_edits():
            assert section in back_to_soe
            assert section.user_edited_cells == back_to_soe[section.id].user_edited_cells
```

##### 14.2 切换预览（用户决策点）

切换前 UI 显示：

```
即将切换：国企版 → 上市版

影响章节：
  ✓ 共有章节 150 个 — 数据保留
  ⚠ SOE 独有 13 个 — 数据将归档（不可见但保留 30 天）
  + Listed 新增 14 个 — 创建空章节
  ⚠ 格式略不同 10 个 — 列结构调整，部分字段值可能丢失：
      - 固定资产（您手工编辑过的"减值准备"列将归档到独立栏）
      - ...

用户编辑保留：N 个章节，M 个 cells

[查看详细 diff]  [取消]  [继续切换]
```

##### 14.3 跨模板合并汇总

合并项目模板 = 国企版时：
- 子公司 SOE → 直接汇总
- 子公司 Listed → 走 `consol_aggregation` 配 `template_translate=listed_to_soe`

#### 用户需求（D14）

- **U38** 单体附注顶部「准则」切换器（与 ConsolidationIndex 已有切换器一致风格）
- **U39** 切换前预览：影响章节数 + 用户编辑保留情况
- **U40** 切换后归档不可见章节（30 天保留期，可恢复）
- **U41** 集团内子公司模板独立管理（partner 锁定合并版准则）
- **U42** 跨模板合并汇总（SOE 子公司 + Listed 合并 等组合）
- **U43** 合并 cell provenance 标识子公司模板（「来自 SOE 子 A 100 + Listed 子 B 50」）
- **U44** 模板差异清单可视化（P-7 数据驱动）

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

### D12 合并↔单体附注映射（v0.4 新增 ⭐）

#### 核心场景

集团合并附注（parent project，consol_level≥2）的「八、4 应收账款」需要从所有子公司单体附注的「八、3 应收账款」自动汇总（抵销内部往来后），目前**无映射关系导致只能手填**。

#### 三大映射维度

##### 12.1 章节级映射（section ↔ section）

合并模板与单体模板**章节集差异**：

| 类型 | 数量 | 说明 |
|------|------|------|
| **共有章节** | ~150 | 合并和单体都有（如货币资金/应收账款/固定资产） |
| **仅合并** | ~20 | 合并范围/重要子公司/范围变动/商誉/少数股东权益/内部交易抵消/外币折算/分部信息等 |
| **仅单体** | ~10 | 母公司报表项目（仅对外报送母公司单体报表时） |
| **格式略不同** | ~30 | 共有但合并版多列（如固定资产合并多"少数股东权益部分"） |

##### 12.2 科目级映射（合并 cell ↔ 子公司单体 cell）

```json
// 合并附注「八、4 应收账款 - 按欠款单位列示前五名」cell binding：
{
  "primary": {
    "source": "consol_aggregation",
    "child_section": "八、3",                    // 单体附注的对应章节
    "aggregation_method": "sum_after_elimination", // 抵销后求和
    "child_filter": {                            // 哪些子公司参与汇总
      "scope": "all" | "exclude_inactive" | ["subsidiary_id_1", ...]
    },
    "elimination_rules": [                       // 内部往来抵销规则
      {"type": "internal_ar", "wp_code": "consol_internal_ar"}
    ]
  }
}
```

##### 12.3 表格行级映射（前 N 名汇总规则）

合并附注「前 5 名客户」≠ 各子公司前 5 名简单叠加，**需重新排序**：

```python
# 算法（伪代码）
def consolidate_top_n(child_notes: list, top_n: int = 5):
    """汇总各子公司动态行 → 抵销内部 → 重新排序取前 N."""
    all_rows = []
    for child in child_notes:
        for row in child.dynamic_rows:
            # 1. 标记内部往来（按客户名匹配集团内子公司）
            if row.label in group_internal_companies:
                row.is_internal = True
            all_rows.append(row)
    # 2. 抵销内部
    external = [r for r in all_rows if not r.is_internal]
    # 3. 按 label 合并同名（不同子公司可能与同一外部客户有往来）
    grouped = group_by_label_fuzzy(external)
    # 4. 按金额重排序
    grouped.sort(key=lambda r: r.amount, reverse=True)
    return grouped[:top_n]
```

#### 用户需求

- **U18** 合并模板编辑器看到「此章节从子公司哪个章节汇总」标识
- **U19** 子公司单体附注更新 → 合并附注对应章节自动 stale 标记
- **U20** 合并 cell 溯源对话框显示「来自 N 家子公司」+ 各子公司贡献金额
- **U21** 「重新汇总」按钮 → 触发跨子公司重新提数 + 抵销 + 排序
- **U22** 多层合并（孙公司 → 子合并 → 总合并）的链式映射可视化

### D13 标题序号动态层级（v0.4 新增 ⭐）

#### 致同标准多级编号体系

```
一、公司基本情况                    ← 一级（中文数字）
二、财务报表编制基础
...
四、重要会计政策、会计估计           ← 一级
  （一）会计期间                   ← 二级（带括号中文数字）
  （二）记账本位币
  （三）记账基础和计价原则
五、税项                          ← 一级
  （一）主要税种及税率              ← 二级
    1. 增值税                    ← 三级（阿拉伯数字）
    2. 企业所得税
八、财务报表主要项目注释            ← 一级
  （一）货币资金                   ← 二级
    1. 期末余额构成                ← 三级
      (1) 库存现金                ← 四级（带括号阿拉伯数字）
      (2) 银行存款
        ① 国内存款                ← 五级（带圈数字）
        ② 境外存款
```

#### 当前问题

1. **写死字符串**：`section_number = "一、1"` `"四、记账本位币"` `"八、22"` 是手工编的字符串，与位置无关
2. **裁剪后断号**：删了「(三) 记账基础」后，「(四)」不会自动变 「(三)」
3. **层级不固定**：用户加自定义子章节后，子章节用什么层级？
4. **跳级**：「八、22」直接跳到 22 而无 (一)~(三十几)（实际是子项目分组）
5. **单体↔合并切换**：单体附注 9 大章节，合并附注 14 大章节（多 5 个），原 4/5/6/7 章节顺延变 5/6/7/8/9，所有内部引用「见五、（一）」全部失效

#### 设计目标

##### 13.1 章节序号 = 「位置自动派生」（不写死）

```json
// 模板 JSON 改为不写死序号，存层级 + 排序：
{
  "section_id": "company_basic_info",       // 稳定 ID
  "section_title": "公司基本情况",
  "level": 1,                               // 层级（1-5）
  "parent_section_id": null,                // 顶层
  "sort_index": 1,                          // 同层级内排序
  "auto_numbering": true,                   // 自动编号 vs 用户固定

  // 渲染时动态生成（不存）
  "_rendered_number": "一、",                // 由 SectionNumberingService 计算
  "_full_path": "一、",                      // 完整层级路径
}
```

##### 13.2 多级编号格式注册器

```python
# backend/app/services/note_section_numbering.py
LEVEL_FORMATS = {
    1: lambda i: f"{cn_number(i)}、",         # 一、二、三、...
    2: lambda i: f"（{cn_number(i)}）",         # （一）（二）（三）
    3: lambda i: f"{i}.",                     # 1. 2. 3.
    4: lambda i: f"({i})",                    # (1) (2) (3)
    5: lambda i: f"{circled_number(i)}",      # ① ② ③
    6: lambda i: f"  {chr(0x4E00 + i - 1)}.", # 子级（罕见）
}
```

##### 13.3 裁剪后自动重排

```
裁剪前：
  四、(一) 会计期间          [保留]
  四、(二) 记账本位币        [保留]
  四、(三) 记账基础          [删除] ← 用户裁剪
  四、(四) 企业合并          [保留]
  四、(五) 合并财务报表编制   [保留]

裁剪后（不重排，保留断号）：
  四、(一) 会计期间
  四、(二) 记账本位币
  四、(四) 企业合并          ← 跳号 (三)
  四、(五) 合并财务报表编制

裁剪后（自动重排）：
  四、(一) 会计期间
  四、(二) 记账本位币
  四、(三) 企业合并          ← 重排
  四、(四) 合并财务报表编制
```

**用户可选**：每个章节有 `lock_number: bool` 字段，true 时序号锁定（如某章节用户一定要叫"四、(五)"），false 时自动重排。

##### 13.4 表格也有标题序号

```
八、(三) 应收账款           ← 章节标题
  1. 应收账款分类           ← 表格 1 标题
  2. 按账龄披露的应收账款    ← 表格 2 标题
  3. 按欠款单位列示前五名    ← 表格 3 标题
```

表格标题也参与层级编号。模板需新增 `table.title_level: int`。

##### 13.5 单体↔合并切换序号联动

```python
# 同一份附注数据，单体/合并切换时序号自动重排
def render_section_numbers(notes, scope: str):
    """按 scope 过滤章节后重新编号."""
    visible = [n for n in notes if n.scope in (scope, 'both')]
    # 按 (level, parent_section_id, sort_index) 树形遍历
    return _renumber_tree(visible)
```

##### 13.6 内部引用自动跟随

附注内文常有「具体见五、（一）2.」这种交叉引用。当章节序号变化时，引用应自动更新：

```jinja
本期增加情况详见 {{ ref("section_id_revenue_breakdown") }}
                 ↓ 渲染时替换为
本期增加情况详见 五、(三) 2.
```

#### 用户需求

- **U23** 模板编辑器自动显示当前序号（实时）
- **U24** 「锁定序号」开关 + 「自动重排」开关
- **U25** 单体↔合并切换序号自动重算（无需手工改）
- **U26** 删除/新增章节后内部引用自动更新
- **U27** 章节拖拽排序（同层级内）→ 序号自动重算
- **U28** 表格标题也参与编号（如「应收账款」下「1. 分类 / 2. 账龄」）
- **U29** 序号格式可定制（中文/阿拉伯/带圈）— partner 权限
- **U30** Word 导出 TOC 使用最新序号

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

### H. 合并↔单体映射（v0.4 新增 ⭐ 12 项）

- H.1 模板新增 `consol_section_mapping` 字段（合并章节 → 单体章节 ID 映射）
- H.2 模板新增 `is_consol_only` / `is_standalone_only` 标记
- H.3 binding 新增 `source: "consol_aggregation"` source 类型
- H.4 `consol_aggregation` source_config 含 child_section + aggregation_method + child_filter + elimination_rules
- H.5 `aggregation_method` 枚举：`simple_sum / sum_after_elimination / top_n_after_elimination / weighted_avg / first_n_concat`
- H.6 多层合并 lineage 链（孙合并 → 子合并 → 总合并的章节映射跟随）
- H.7 子公司单体附注更新 → 合并附注对应章节自动 stale（事件驱动）
- H.8 「重新汇总」按钮触发 + 进度条
- H.9 合并 cell 溯源对话框（「来自 N 家子公司」+ 各子公司贡献）
- H.10 内部往来抵销规则注册器（按 wp_code 配置规则）
- H.11 模糊合并同名（不同子公司与同一外部客户）label 算法
- H.12 国企/上市合并版与单体版互转保留映射

### I. 标题序号动态层级（v0.4 新增 ⭐ 15 项）

- I.1 模板字段从 `section_number` 字符串改为 `section_id` 稳定 ID + `level` + `parent_section_id` + `sort_index`
- I.2 `auto_numbering: bool` + `lock_number: bool` 双开关
- I.3 `note_section_numbering.py` 服务新建（5 级格式注册器）
- I.4 中文数字 / 阿拉伯 / 带圈数字 filter
- I.5 `render_section_numbers(notes, scope)` 按 scope 过滤后重排
- I.6 裁剪/新增后自动重算 `_rendered_number`
- I.7 表格也参与编号（`table.title_level`）
- I.8 内部引用 `{{ ref('section_id_xxx') }}` 自动替换
- I.9 拖拽排序 → 序号实时刷新
- I.10 单体↔合并切换序号联动
- I.11 序号格式 partner 可定制
- I.12 Word TOC 使用最新序号
- I.13 用户「锁定」单章节序号（不参与重排）
- I.14 历史模板平滑迁移（旧 `section_number` 字符串 → 新 `section_id`）
- I.15 章节序号唯一性校验（CI 卡点）

### J. 国企↔上市丝滑切换（v0.6 新增 ⭐⭐⭐ 11 项）

- J.1 `note_conversion_service` 改用 D13 section_id（不依赖 section_number 字符串）
- J.2 互转 round-trip 数据无丢失（PBT 验证 / CI-20）
- J.3 切换预览：影响章节数 + 用户编辑保留 + 字段级 diff
- J.4 SOE 独有章节归档（30 天保留期，可恢复）
- J.5 Listed 独有章节自动创建空章节
- J.6 格式略不同章节字段映射（约 10 章节，固定资产 movement↔category_sum 等）
- J.7 集团内子公司 template_type 独立存储
- J.8 合并项目模板由 partner 锁定（不跟随子公司）
- J.9 跨模板合并汇总（SOE 子 + Listed 合并等组合）
- J.10 合并 cell provenance 标识子公司模板
- J.11 模板差异清单 `note_soe_listed_diff.json`（P-7 审计师确认）

### F. 兼容与回退（3 项）

- F.1 旧模板按固定模式
- F.2 各维度 feature flag
- F.3 一键回退（清 _dynamic_regions / lineage）

## 四、范围与不做事项

### 必做（v1）

- D1 / D2 / D3 / D4 / D5 / D6 / D7 / D8 / D9 / D10 / D11 / **D12** / **D13** 全部 13 维核心
- 173 章节中 60+ 动态表 binding
- 30+ wp_data binding（H/G/J/L/D/K/M）
- 20+ 段落 Jinja 模板
- **150+ 章节合并↔单体映射**（含 30+ 格式略不同的章节）
- **全部 173 章节 section_id 化**（旧字符串 section_number 迁移）
- 1 个集团基线 demo（首汽租车 → 重庆和平药房）
- 1 个合并项目 demo（合并附注从 N 个子公司单体附注汇总）

### 不做（v1）

- AI 全自动撰写整章节（v2）
- 集团基线 fork & merge（v2）
- 多版本图形化合并工具（v2）
- 跨章节联动（A 加客户 B 同步 — v2）
- 多语言序号（英文/俄文等 — v2）

## 五、性能预算

- 60+ 动态表生成 < 12s
- wp_data 提取 < 200ms / 章节
- 集团基线 apply 60 章节 < 3s
- 上年 diff 全量 < 2s
- AI 建议单章节 < 5s
- **合并附注汇总 N=10 家子公司 < 5s**
- **章节序号重排 173 章节 < 100ms**（纯计算）

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
- ⚠ **P-5**：审计师标注 150+ 章节合并↔单体映射 + 抵销规则（**1.5 人天**，v0.4 新增）
- ⚠ **P-6**：审计师确认 173 章节层级编号方案（5 级标准 / 哪些自动 / 哪些锁定）（**0.5 人天**，v0.4 新增）

## 七、与已完成/进行中 spec 的关系

| 已完成 / 进行中 | 本 spec 扩展 |
|----------------|------------|
| auto_trim 章节级 | 加表格级 + 段落级 |
| 自定义模板（项目级） | 加集团基线（跨项目）+ lineage |
| 空 header 列裁剪 | 加空数据/全空表替换 |
| binding 7 source（设计） | wp_data + multi-source 真接入 + **consol_aggregation 新源（D12）** |
| ADR-010 版本化 | 覆盖动态 + Jinja 段落 + 序号重排 |
| ConsolDisclosureService 7 章节 | 与 173 章节深度融合 + 多层级 lineage + **章节级映射 D12** |
| NoteSectionLockService | 集成动态编辑入口 |
| note_ai.py 5 端点 | 动态行建议 + 段落生成 + 一致性校核 |
| note_prior_year_import_service | 章节级版本图 |
| `section_number` 字符串字段（173 章节） | **section_id + level + auto_numbering 重构（D13）** |
