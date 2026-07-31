# Implementation Plan: N 循环税务类披露表与附注对齐（N2 / N4 / N5）

## Overview

先把 N1 已验证的三个共用件提升为平台共用，再按「附注模板修订 → 同步映射 → 编制模型 →
Tab 重建 → 契约 → 实测」逐循环推进。N2 与 N5 各有一个必修的列压扁缺陷，N5 还有表名重名
（会丢表），N4 国企要落成「本版不适用」而非造表。

> 标记以**代码 / 实测**为准，不凭印象。`[x]`=完成 / `[ ]`=未做 / `[~]`=部分 / `*`=可选

## Task Dependency Graph

```
1 源模板精读（已完成，结论在 design.md §Data Models）
└─► 2 共用件提升（N1 shared → workpaper/shared/disclosure，N1 侧 re-export）
     ├─► 3 附注模板 JSON 幂等修订（含 N5 表名去重 + 两处列恢复）
     │    ├─► 4 N2 同步映射 + 编制模型 + 两 Tab 重建
     │    ├─► 5 N4 上市 Tab 重建 + 国企「不适用」页
     │    └─► 6 N5 同步映射 + 编制模型 + 两 Tab 重建（含孤儿键上报）
     └─► 7 勾稽引擎（通用 eqCheck 提取 + 三循环规则）
          └─► 8 契约与守卫
               └─► 9 验证（后端 / 前端 / 实测）
                    └─► 10 收尾（交付说明 + commit）
```

关键串行约束：`3` 必须先于 `4/5/6`（契约测试要读模板 JSON 的 `headers`/`name`）；
`2` 必须最先（否则三循环各拷一份表组件）；`8.4`（`MISSING_SYNC_PATH` 变短）必须在
`4/5/6` 全部接线后才能通过。

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.3"] },
    { "wave": 2, "tasks": ["2.1", "2.2", "2.3"] },
    { "wave": 3, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8"] },
    { "wave": 4, "tasks": ["7.1", "7.2", "7.3"] },
    { "wave": 5, "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5"] },
    { "wave": 6, "tasks": ["5.1", "5.2", "5.3"] },
    { "wave": 7, "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5"] },
    { "wave": 8, "tasks": ["8.1", "8.2", "8.3", "8.4", "8.5"] },
    { "wave": 9, "tasks": ["9.1", "9.2", "9.3", "9.4", "9.5"] },
    { "wave": 10, "tasks": ["10.1", "10.2"] }
  ]
}
```

## Tasks

## 1. 源模板精读与缺口固化

- [x] 1.1 逐 sheet 读 `backend/wp_templates/N/{N2,N4,N5}*.xlsx` 的披露 sheet（含合并单元格），结论写入 design.md §Data Models
- [x] 1.2 比对三层现状（6 个组件 / 模板 JSON / variant_matrix），缺口表写入 requirements.md
- [x] 1.3 实证两个附带缺陷：N5 国企 xlsx tab 名缺右括号；N5 上市章节被 md 重建错挂到 chapter-03

## 2. 共用件提升（N1 → 平台）

- [x] 2.1 `n1/shared/N1DisclosureSegmentTable.vue` → `shared/disclosure/WpDisclosureSegmentTable.vue`（新增 `column.readonly` 公式列能力）；`composables/n1DisclosureSegmentTypes.ts` → `composables/shared/disclosureSegmentTypes.ts`；N1 侧留 re-export
- [x] 2.2 `n1/shared/N1DisclosureConsistencyPanel.vue` → `shared/disclosure/WpDisclosureConsistencyPanel.vue`（props 泛化为 `results/projectId/defaultExpanded`）
- [x] 2.3 N1 全量测试作回归门（`n1*` 前端 185 + 后端 66 仍绿）
- [x] 2.4 **附带**：AI 文本生成端点契约提升为 `composables/shared/wpAiText.ts`（`useN1AiText` 改 re-export）—— N2/N4/N5 首版误用了不存在的 `/ai-generate` + `existing_content`，已统一到 `/ai/generate-text` + `existingContent`

## 3. 附注模板 JSON 幂等修订

- [x] 3.1 新建 `backend/scripts/fix/fix_note_n_cycle_tax_structure.py`（`--dry-run`/`--check`/`_aligned_by`）
- [x] 3.2 八、41 应交税费：3 列 → **5 列**（期初余额 / 本期应交 / 本期已交 / 期末余额）
- [x] 3.3 三、所得税费用：两表同名 `项  目` → `所得税费用明细` / `所得税费用与利润总额的关系`
- [x] 3.4 八、78 所得税费用：第 2 表名 → `会计利润与所得税费用调整过程`；列 2 → **3 列**（补回 `上期发生额`）
- [x] 3.5 五、41 / 五、63 结构已对齐，仅补 `columns(flat)` + `guidance`
- [x] 3.6 全部涉及表补 `columns(flat)` + `guidance`（只取源模板红字/括注/注/勾稽口径）
- [x] 3.7 `text_sections` 表标题统一 `#### ` 前缀 + 补齐实质披露文本；**N4 国企不新建章节**
- [x] 3.8 `backend/tests/services/test_note_n_cycle_tax_structure.py`（列数/表名唯一/表态/guidance/text_sections/幂等/纯函数）+ CI job `note-n-cycle-tax-structure`

## 4. N2 应交税费

- [x] 4.1 `composables/n2NoteSectionMap.ts`：章节 五、41 / 八、41；sheet 名常量；子表名；**两版列定义分别构造**（上市 3 列双期 / 国企 5 列变动）
- [x] 4.2 `composables/useN2DisclosureTables.ts`：行骨架（上市 5 税种 / 国企 10 税种）+ `合计` 公式 + 国企 `期末余额` 行内公式 + 动态增删行 + 持久化键
- [x] 4.3 `N2TabDisclosureListed.vue` 重建：3 列表 + R24~R26 说明 + R27 提示（用附注模板的「未交增值税」而非源模板错字）
- [x] 4.4 `N2TabDisclosureSoe.vue` 重建：5 列变动表（期末列为公式列）+ R24 提示
- [x] 4.5 两版删自造 section（税种变动说明 / 欠缴税款说明 / 应缴国有资本收益说明）；接 autoSync + 手动同步 + 反向跳转 + AI + 复核
- [x] 4.6 **附带修实测缺陷**：`GtN2TaxesPayable.vue` 分发用繁体「國企」（国企 Tab 从未渲染过）→ 抽 `composables/n2SheetRouting.ts`；宿主漏传 `projectId`（同步永久静默失败）→ 已补

## 5. N4 税金及附加

- [x] 5.1 `composables/n4NoteSectionMap.ts`：章节 五、63；`buildN4SyncPayload('soe', …)` 恒返回 `null`
- [x] 5.2 `N4TabDisclosureListed.vue` 重建：3 列表 + `合计` + R18 说明；删自造变动额/变动率/变动原因三列
- [x] 5.3 `N4TabDisclosureSoe.vue` 改为「本版不适用」说明页（引源模板 `附注披露信息：无` + 指向上市版），不显示同步按钮
- [x] 5.4 **附带**：`composables/n4SheetRouting.ts`（披露判定前置）+ 宿主补传 `projectId`

## 6. N5 所得税费用

- [x] 6.1 `composables/n5NoteSectionMap.ts`：listed 用模板现存 `三、所得税费用`、soe `八、78`；🔴 `sheet_name.soe = '附注披露信息（国企'`（逐字，缺右括号）；子表名用去重后的名字
- [x] 6.2 `composables/useN5DisclosureTables.ts`：表（1）3~4 行 + 表（2）行骨架（上市 13 行 / 国企 10 行）+ 合计公式 + 动态增行；**表（2）末行求和排除首行「利润总额」**（源模板注 1「第二行至倒数第二行」）
- [x] 6.3 `N5TabDisclosureListed.vue` 重建：两表 + 标题括注 + R27~R29 注
- [x] 6.4 `N5TabDisclosureSoe.vue` 重建：两表 + 表（2）标题括注（国资委格式未要求披露，建议披露）+ R30~R32 注
  - 两版列结构与交互完全相同 → 实现收在 `n5/shared/N5DisclosureBody.vue`，两 Tab 为薄壳（显式声明全部 prop + `v-bind="$props"`，供覆盖率守卫做委托解析）
- [x] 6.5 `N5_TABLE_NAMESPACE` + `legacyObsolete`（旧键 `项  目`）+ `_removed_table_keys` 上报 + 同步成功后 `markSynced`
- [x] 6.6 **附带**：`composables/n5SheetRouting.ts` + 宿主补传 `projectId`

## 6.5 N3 递延所得税负债（复核 N 类完整性时发现）

- [x] 6.5.1 双证确认 N3 **无披露 sheet**：源模板 `N3 递延所得税负债.xlsx` 只有
      底稿目录 / N3A / N3-1 / N3-2 / N3-3 / GT_Custom；`workpaper_sheet_classification`
      里 `wp_code='N3'` 的附注 sheet **0 条**。递延所得税负债披露与 N1 **共节**
      （五、30 / 八、31，N1 表(1)「未经抵销的递延所得税资产和递延所得税负债」已含负债段）
- [x] 6.5.2 删除自造且不可达的 `n3/core/N3TabDisclosure.vue`（三个自拟小节：概述 /
      应纳税暂时性差异明细 / 余额变动表 —— 与 N1 spec 已推翻的那批自造表同源；
      宿主判定 `currentSheet === '附注'` 永不命中 = 死代码 + 潜在污染源）
      + 清宿主 import/分发块 + 清 `components.d.ts` 自动生成条目；
      落库确认 `checklist_responses` 里 `N3-disclosure-%` **0 行**（无用户数据可丢）
- [x] 6.5.3 反向守卫 `CYCLES_WITHOUT_DISCLOSURE`（`disclosureAutoSyncCoverage.spec.ts`）：
      源模板无披露 sheet 的循环不得有披露 Tab 组件，每条须写源模板依据 + 反向自检防空转；
      `MISSING_SYNC_PATH` 42 → 41。N3 相关既有测试 117 例零回归

## 7. 勾稽引擎

- [x] 7.1 从 `n1DisclosureConsistency.ts` 提取通用 `eqCheck` / `segmentSumCheck` / `summarizeChecks` / 类型到 `composables/shared/disclosureConsistency.ts`，N1 侧 re-export
- [x] 7.2 新建 `composables/nCycleTaxConsistency.ts`：N2 合计、N2 国企逐行期末恒等式、N4 合计、N5 表（1）合计、N5 表（2）末行 = 明细之和、N5 跨表相等
- [x] 7.3 `nCycleTaxConsistency.spec.ts`（单测 + PBT：恒等式、跨表、null→skip、纯函数）

## 8. 契约与守卫

- [x] 8.1 `n2NoteSubtableContract.spec.ts` / `n4…` / `n5…`：接 `runDisclosureSubtableContract` + 双向键集 + **同章节表名唯一** + 全表 guidance
- [x] 8.2 登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`（新增 5 个零参 builder）
- [x] 8.3 `disclosureSheetNameRegistry.spec.ts` 覆盖三循环（含 N5 国企缺括号）—— glob 自动纳入，重跑 `gen_note_wp_sync_registry.py --write` 后逐字一致
- [x] 8.4 `disclosureAutoSyncCoverage.spec.ts` 的 `MISSING_SYNC_PATH` 移除 5 个 Tab（47 → 42；N4 国企按「不适用」豁免并写理由）
- [x] 8.5 反向断言：N2 两版列定义键集不等（防两版共用一份列定义复发）
- [x] 8.6 **新增平台守卫**：宿主必须给披露 Tab 传 `projectId`（漏传 = 同步永久静默失败）——
      扫全部 `.vue` 的 `<XTabDisclosure*>` 使用点，现存 126 处全部合规
- [x] 8.7 `nCycleSheetRouting.spec.ts`：N4/N5 sheet 分发（披露判定前置 / 国企多写法 / N5 缺括号）+ 反向自检替身
- [x] 8.8 CI job `note-n-cycle-tax-frontend`（12 个前端守卫 spec）

## 9. 验证

- [x] 9.1 后端 pytest（结构守卫 + e2e + N1 零回归）：147 passed
- [x] 9.2 前端 vitest（三循环载荷 + 契约 + 勾稽 + 平台守卫）：N 循环 229 + 平台守卫 48 全绿；`src/components/workpaper` 全量对比基线无新增失败
- [x] 9.3 `get_diagnostics` 逐文件全绿 + Vite transform 21 个文件全 200（vue-tsc 全项目本机需 32 GB，收口时单独跑）
- [x] 9.4 chrome-devtools 实测 5 个 Tab + postgres 只读比对落库（详见下）
- [x] 9.5 进程内 ASGI e2e 验 `get_note_detail` 表数 / 列 / guidance（`test_note_n_cycle_tax_detail_e2e.py`）

### 9.4 实测记录（项目 `2aa00f57` / 2026-07-30）

| Tab | 实测结果 |
|---|---|
| N2 上市 | 列头 `税 项 / 期末余额 / 上年年末余额`；5 税种 + 合计；录 250000/180000 → 合计正确；同步新建 五、41（`source_template=listed`，columns 3 列带 `flat`） |
| N2 国企 | 列头 5 列；录 100000/80000/30000 → **公式列 期末余额 = 150,000.00**；合计四列正确；勾稽由「待补数 14」变「一致 5」；同步落 八、41（11 行，`_last_sync_sheet=附注披露信息（国企）`） |
| N4 上市 | 列头 3 列；8 税费项 + 合计；录 12000/8000 → 合计 20,000.00；同步新建 五、63 |
| N4 国企 | 「本版不适用」说明页：0 张表、**无同步按钮**、5 条源模板依据（含 `附注披露信息：无`） |
| N5 上市 | 两卡片标题带源模板括注；表(1) 合计 560,000.00；**表(2) 末行「所得税费用」= 560,000.00（排除首行 利润总额 2,000,000）**；勾稽跨表一致；同步新建 三、所得税费用，两表名互异，末行不带 `is_total` |
| N5 国企 | sheet 名 `附注披露信息（国企`（缺右括号）能命中并挂载；两表；同步落 八、78，`_last_sync_sheet` 逐字缺括号，表名 `所得税费用` / `会计利润与所得税费用调整过程` |

实测顺带挖出并修掉 **N2/N4/N5 三个宿主都漏传 `projectId`** → 同步（含自动同步）永久静默失败
（控制台只有 `Missing required prop` 警告，vitest 与 `get_diagnostics` 都查不出）。已加平台守卫 8.6。

实测数据已全部复原：删除新建的 五、41 / 五、63 / 三、所得税费用；八、41 / 八、78 回到生成时快照
（移除 `sub_table_data`/`_sub_table_columns`/`_source`/`_last_sync_sheet`，`last_sync_at` 置 NULL）；
清掉 12 条 `N{2,4,5}-disclosure-*` checklist_responses。

## 10. 收尾

- [x] 10.1 交付说明：模板改动只对新建项目生效；N5 表名去重对既有项目靠 `_removed_table_keys` 自愈
- [ ] 10.2 commit

## Notes

### 跨 spec 依赖（本 spec 不做）

- **`三、所得税费用` 章节归属错误**：md 重建把 8 个利润表项目注释章节（公允价值变动收益 /
  信用减值损失 / 资产减值损失 / 资产处置收益 / 营业外收入 / 营业外支出 / 所得税费用 /
  现金流量表项目注释）挂到 `chapter-03 重要会计政策及会计估计`，应在 `chapter-05 项目注释`。
  修它会改动章节号（`五、63` 之后全部顺移）并影响既有项目的 `note_section` 定位键 →
  须单独立 spec 并配存量迁移脚本。本 spec 用模板现存章节号保证链路通。
- **`disclosure_notes.source_template` 记项目模板而非章节变体**（N1 spec 已在读端用
  `resolve_template_type` 旁路，生成侧未改）。实测再次印证：国企模板项目里同步上市披露表
  会新建 `source_template=listed` 的章节，与既有 soe 章节并存。
- **`applicable_standards` 前端全链缺失** → 披露 Tab 变体门恒开（本 spec 5 个 Tab 同样无门控）。

### 交付说明（必读）

1. 模板 JSON 改动只对**新建项目 / 重新生成附注**生效；既有项目须由底稿「同步到附注」整表覆盖。
2. **N4 国企版按源模板不披露税金及附加** —— Tab 显示「本版不适用」不是缺功能。
3. **N5 国企披露 sheet 名逐字为 `附注披露信息（国企`（缺右括号）**，源模板 tab 名如此，
   同步 `sheet_name` 必须与之逐字一致，不要"修正"。
4. N2 两版列结构本质不同（上市 3 列双期 / 国企 5 列变动），禁止共用列定义。
5. **N5 表（2）末行是公式行**，= 第二行至倒数第二行之和（**不含首行「利润总额」**，源模板注 1），
   不可手工录入；两版分别落成「所得税费用」勾稽落点行与「合计」行。
