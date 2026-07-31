# Implementation Plan: N1 递延所得税资产披露表与附注对齐

## Overview

按「源模板精读 → 附注模板修订 → 同步映射 → 勾稽引擎 → 两个披露 Tab 重建 → 契约守卫 → 实测」
七段推进。后端模板修订先行（前端契约测试要读模板 JSON），勾稽引擎与共用表组件先于两个 Tab。

> 标记以**代码 / 实测**为准，不凭印象。`[x]`=完成 / `[ ]`=未做 / `[~]`=部分 / `*`=可选

## Task Dependency Graph

```
1 源模板精读
├─► 2 附注模板 JSON 修订（幂等脚本 + 测试 + CI）
│    └─► 3 同步映射重写（columns 需与模板 headers 逐字一致）
│         ├─► 4 勾稽引擎（读同步模型的段/合计口径）
│         │    └─► 5.1 共用分段两级表头表组件
│         │         ├─► 5 上市披露 Tab 重建
│         │         └─► 6 国企披露 Tab 重建
│         └─► 7 契约与守卫（同时依赖 2 与 3）
└─────────────────────────► 8 验证（依赖 2~7 全部）
                              └─► 9 实测中发现的真缺陷修复
                                   └─► 10 遗留
```

关键串行约束：`2` 必须先于 `3`（否则 P5「标签列头对齐 headers[0]」无从校验）；
`3` 必须先于 `4`（勾稽入参取自同步模型字段）；`8.5/8.6` 必须在 `5`+`6` 都完成后做
（两个 Tab 共用同一附注章节，单侧实测无法证明子列序不串味）。

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.3"] },
    { "wave": 2, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10"] },
    { "wave": 3, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7"] },
    { "wave": 4, "tasks": ["4.1", "4.2", "4.3", "4.4", "5.1"] },
    { "wave": 5, "tasks": ["5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8", "5.9", "6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7", "6.8"] },
    { "wave": 6, "tasks": ["7.1", "7.2", "7.3", "7.4", "7.5"] },
    { "wave": 7, "tasks": ["8.1", "8.2", "8.3", "8.4", "8.5", "8.6", "8.7", "8.8"] },
    { "wave": 8, "tasks": ["9.1", "9.2", "9.3"] },
    { "wave": 9, "tasks": ["10.1", "10.2", "10.3", "10.4"] }
  ]
}
```

## Tasks

## 1. 源模板精读与结论固化

- [x] 1.1 逐 sheet 读 `backend/wp_templates/N/N1 递延所得税资产.xlsx` 两张披露 sheet（含合并单元格），结论写入 design.md §1
- [x] 1.2 三层现状比对（底稿组件 / `n1NoteSectionMap.ts` / `note_template_*.json`），缺陷清单写入 requirements.md
- [x] 1.3 确认 N1 sheet 分发安全 —— `workpaper_sheet_classification` 实测 sheet 名为 `附注披露信息（上市公司）`/`附注披露信息（国企）`（无 wp_code 后缀），`GtN1DeferredTaxAssets.currentSheet` 的 `N1-[1-5]` 正则不会抢占，且「国企」「国有企业」两种写法都认

## 2. 附注模板 JSON 修订（后端）

- [x] 2.1 新建 `backend/scripts/fix/fix_note_deferred_tax_structure.py`（`--dry-run` / `--check` / `_aligned_by`）
- [x] 2.2 listed 五、30 表 1 恢复 5 列 + `_column_groups` + 删 `header_label` 假数据行
- [x] 2.3 soe 八、31 表 1 恢复 5 列 + `_column_groups`（子列序：资产/负债在前）+ 删假数据行
- [x] 2.4 soe 八、31 表 2 3 列 → 5 列 + 行骨架补齐（资产段 + 小计 + 负债段 + 小计，与表 1 同构）
- [x] 2.5 soe 八、31 新增表「递延所得税资产和递延所得税负债互抵明细」（2 列，源模板（2）B）
- [x] 2.6 两版全部表补 `columns`（`flat` / `group` 明确表态）
- [x] 2.7 两版全部表补 `guidance`（只取源模板红字/括注/勾稽口径）
- [x] 2.8 `text_sections` 修订：表标题统一 `#### ` 前缀 + 补齐实质披露文本（listed 10 段 / soe 9 段）
- [x] 2.9 `backend/tests/services/test_note_deferred_tax_structure.py` —— 34 测试全绿（表数/列数/`_column_groups`/表态/guidance/text_sections/无假数据行/幂等/纯函数）
- [x] 2.10 CI `governance-checks.yml` 新增 job `note-deferred-tax-structure`（`--check` + 契约测试；yaml 解析通过，34 job）

## 3. 同步映射重写（前端 composable）

- [x] 3.1 `n1NoteSectionMap.ts` 表 1 两级 5 列 `columns`，子列序单一真源 `n1UnoffsetSubOrder(variant)`
- [x] 3.2 `netOffsetColumns('soe')` 3 列 → 5 列；新增 `offsetDetailColumns()`
- [x] 3.3 `N1_SUB_TABLE_KEYS.soe` 补第 5 键 `offsetDetail`
- [x] 3.4 `buildN1SyncPayload` 覆盖 5 表；`normalizeN1RowLabel`/`isN1TotalLabel` 先去空白；分组标题行全列 `null`、小计合计 `is_total`
- [x] 3.5 `N1_TABLE_NAMESPACE` 导出 + 同步**成功后**才 `markSynced`（`dataTableNames` + `serializeSyncedTableNames`）
- [x] 3.6 `_note_texts` 新增 `rollback`（R30 一年后预期转回说明），排序在 `conclusion` 之前
- [x] 3.7 变体入参 builder 改名 `n1ColumnsFor`（铁律：`build*Columns` 会被守卫用空入参 sweep）

## 4. 勾稽引擎

- [x] 4.1 新建 `composables/n1DisclosureConsistency.ts`（`eqCheck` 容差 0.01 元 / 任一侧 null → skip）
- [x] 4.2 规则：表 1 双段小计、表 2 双段小计（仅国企）、未确认合计、亏损到期合计、跨表「亏损到期合计 = 未确认可抵扣亏损」（期末 + 上期各一条）
- [x] 4.3 新建 `n1/shared/N1DisclosureConsistencyPanel.vue`（紧凑 bar + 折叠明细 + 规则 tooltip + `GtIndexChip`）
- [x] 4.4 `n1DisclosureConsistency.spec.ts` —— 22 测试（含 4 条 PBT，numRuns=20）

## 5. 底稿披露表重建（上市）

- [x] 5.1 新建 `n1/shared/N1DisclosureSegmentTable.vue`（两级表头 + 分段 + `span-method` 整行合并 + 小计公式行 + 动态增删行）；类型下沉 `composables/n1DisclosureSegmentTypes.ts`（`<script setup>` 不允许 `export interface`）
- [x] 5.2 表（1）两级 5 列、资产/负债双段、`小计` 公式行、动态增行
- [x] 5.3 表（2）以抵销后净额列示（5 列 2 行）—— 新增
- [x] 5.4 表（3）3 列 + `合计` 公式行
- [x] 5.5 表（4）4 列 + `合计` + 年度行增删（默认审计年度后 5 年）
- [x] 5.6 R30 说明可编辑正文 + R31/R32/R43/R53 只读提示（含中文引号的文案只放 script 常量，不进模板属性）
- [x] 5.7 删除自造 section（「余额变动表」「与 N3 对应关系」）；账面价值/计税基础/确认依据等审计过程列留在 N1-2 / N1-4
- [x] 5.8 只读金额走 `displayPrefs.fmtAmount`、可编辑走 `WpAmountInput`；每表 AI 辅助 + `GtReviewTrigger`
- [x] 5.9 接勾稽面板 + `useDisclosureAutoSync`

## 6. 底稿披露表重建（国企）

- [x] 6.1 前置口径说明（源模板 R7 原文）置顶方法论上下文
- [x] 6.2 表（1）两级 5 列（子列序与上市相反）+ 负债段第 4 项 `租赁形成`
- [x] 6.3 表（2）互抵后 5 列 + 双段明细 + 双 `小计`
- [x] 6.4 表（3）互抵明细 2 列 + 动态增行
- [x] 6.5 表（4）3 列 + `合计`
- [x] 6.6 表（5）4 列 + `合计` + 年度行增删
- [x] 6.7 R30/R31/R73 只读提示；删除 6 个自造 section
- [x] 6.8 接勾稽面板 + `useDisclosureAutoSync` + AI/复核

## 7. 契约与守卫

- [x] 7.1 `n1NoteSubtableContract.spec.ts` —— 共享 helper 5 条 Property + N1 专属 P6~P10（双向键集 / 全表 guidance / headers 无空串 + 分组不越界 / 子列序两版相反 / 同步 columns ↔ 模板 columns 同形）；37 测试
- [x] 7.2 `columns` 键序断言（表 1 子列序与 variant 匹配）—— 在 7.1 P9 与 `n1NoteSectionMap.spec.ts` Property 12
- [x] 7.3 登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`（`buildN1ListedColumns` / `buildN1SoeColumns`）—— 15 测试全绿
- [x] 7.4 `disclosureSheetNameRegistry.spec.ts` 6/6 绿（`N1_DISCLOSURE_SHEET_NAME` 与 registry 逐字一致）
- [x] 7.5 `disclosureAutoSyncCoverage.spec.ts` 24/24 绿（两 Tab 仍在册）

## 8. 验证

- [x] 8.1 后端 pytest：`test_note_deferred_tax_structure`(34) + `test_note_table_guidance`(18) + `test_note_deferred_tax_read_projection`(14) = **66 全绿**
- [x] 8.2 前端 vitest：N1 四文件 111 全绿；`src/components/workpaper` 全量 1304 passed，稳定红 10 个文件全在未触碰区（b23×3 / j2 / G0 / h8 / l4 / useF3 / useF5 / useH4DualMode），另 3 个（`disclosureColumnsCoverage` / `useD7AgingLifecycle` / `g7AuxExtraction.pbt`）孤立跑全绿 = 并行 flaky
- [x] 8.3 `get_diagnostics` 逐文件（新增/改动 15 个文件全 clean；vue-tsc 全项目在本机 OOM 故不跑）
- [x] 8.4 Vite transform 200 校验（8 个新增/改动前端文件全 200）
- [x] 8.5 chrome-devtools 实测两 Tab（项目 `2aa00f57` / wp `c48c1ad8`）：
  - 上市 4 表、国企 5 表，表 1 真两级表头（`期末余额[x2]` / `上年年末余额[x2]`、国企 `年初余额[x2]`），**两版子列序确认相反**
  - 分组标题行整行合并、负债段国企第 4 项为 `租赁形成`
  - 公式行正确：资产段小计 200,000.00 / 表 3 合计 700,000.00 / 表 4 合计 500,000.00 / 国企表 2 双段小计 60,000.00
  - 勾稽面板：上市 4 条一致 + 4 条待补数；国企 5 条一致 + 5 条待补数（含跨表 500,000 = 500,000）
  - 编辑触发 `useDisclosureAutoSync` 自动同步成功
- [x] 8.6 postgres 只读比对 `disclosure_notes`：基线 sub_keys 全 0 → 同步后 五、30 = 4 键 / 八、31 = 5 键；`_sub_table_columns` 带 `group` 两级元数据（两版子列序相反）；`is_total` 到位；未取到值保持 `null`；`_source=workpaper`、`_last_sync_sheet` 为源 sheet 全角括号名、`_last_sync_at` 随每次编辑更新
- [x] 8.7 交付说明写清「模板 JSON 改动只对新建项目 / 重新生成附注生效；既有项目须由底稿『同步到附注』整表覆盖」（见 design.md §2 与本文件末尾）
- [x] 8.8* 清理临时文件

## 9. 实测中发现并修掉的真缺陷（非计划内）

- [x] 9.1 **`el-input` 只绑 `@change` 会抹掉用户键入**：EP 的 `handleInput` 在 `await nextTick()` 后调 `setNativeInputValue()` 把 DOM 值重置回 `modelValue`；不回写 `modelValue` 时用户敲的字消失、`change` 拿到空串。实测证据：国企互抵明细行名落库 `label: ""`。已把 `N1DisclosureSegmentTable` 的行名列与文本列改为 `@input` 回写，复测落库 `label: "同一纳税主体互抵"`
- [x] 9.2 **附注 TAB 编制提示对已同步项目永久为空**：`guidance` 只在 seed 路径经 `_carry_seed_table_guidance` 生效，`_source=workpaper` 的读时投影完全不带它。新增 `backend/app/services/note_table_guidance.py`（读时按 `(source_template, section_number, 表名)` 回填，不写库、表名对不上就跳过、已有非空不覆盖）并接进 `get_note_detail`
- [x] 9.3 **`n1-linkage-fixes.spec.ts` 5 条长期红**（与披露无关的既有缺口）：测试桩 `makeFormDataStub` 缺 `getField`/`setField`；`useN1LossCheck` 入参名是 `auditYear` 而桩写 `currentYear`；亏损表 fixture 仍是 N1-5 重建前的 legacy 行形状（应为 `N1_LOSS_ROWS_KEY_V2` + 新字段）。三处修掉后该文件 18/18 绿

## 10. 遗留收口

- [x] 10.1 **`guidance` 回填端到端验证（改用进程内 ASGI，比 live server 更硬）**：本机 uvicorn 虽带 `--reload --reload-dir app` 但实测 `.py` 改动**不热加载**（9980 上同时跑 `.venv` 与系统 python 两个 uvicorn），端点持续返回旧代码；重启共享 dev 后端会打断并发会话。改用 `httpx.ASGITransport` 直连 `app.main:app`（跑当前磁盘代码）—— 新建 `backend/tests/e2e/test_note_deferred_tax_detail_e2e.py`，**11 测试全绿**：`GET /api/disclosure-notes/{pid}/{year}/{section}` 返回 listed 4 表 / soe 5 表、表 1 两级表头且两版子列序相反、其余表 `_column_groups == []`、**全部表 `guidance` 非空**、soe 互抵明细表在位
- [x] 10.2 **附注端渲染以 API 契约验证替代肉眼复验**（附注编辑页被「打印预览」遮罩接管 + 共享 Chrome 被并发会话反复导航走 + token 过期需重登）：附注 TAB 的表数 / 表名 / `headers` / `_column_groups` / `guidance` 全部来自 `get_note_detail` 的 `table_data._tables`，已由 10.1 的 11 条 e2e 逐项锁死；两级表头的**前端渲染路径**（`DisclosureEditor.activeTableColumns` 嵌套 `el-table-column`）是平台共享机制，F2 / K6 已有浏览器实测在册，本 spec 不重复验证
- [x] 10.3 **修掉 `source_template` 与章节号变体错配**：新增 `note_table_guidance.resolve_template_type(template_type, section_number)` —— 记录的模板含该章节号则原样返回（绝大多数情况零行为变化）；记录的模板**没有**而另一份**恰好有**则纠正；两个都有 / 都没有则不猜。这使错记为 `soe` 的上市章节 `五、30` 也能填上 guidance（此前恒空）。守卫 5 测试（纠正 / 推断 / 歧义不猜 / 端到端）
- [ ] 10.4 commit（工作树含其它并发 spec 改动；本 spec 后端部分已被并发会话提交进 `f5debfa4` / `4678ec3b`）
- [ ] 10.5* 平台级跟进（**不属本 spec**）：`disclosure_notes.source_template` 记的是**项目模板**而非章节变体，根治须改生成侧口径。本 spec 只在读端用 `resolve_template_type` 旁路，不改数据；与 memory 已记的 `applicable_standards` 前端全链缺失同源，建议单独立 spec

---

## Notes

### 交付说明（必读）

1. **模板 JSON 改动只对新建项目 / 重新生成附注生效**。`note_template_{listed,soe}.json` 是 seed 骨架；既有项目的附注 TAB 数与行不会自动变化，须由底稿披露页点「同步到附注」（或任意编辑触发自动同步）整表覆盖。本次实测的 `2aa00f57` 即通过同步从 0 表变为 4/5 表。
2. **`_source=workpaper` 时底稿推送是唯一权威**：投影器只渲染推来的 `sub_table_data`，模板 seed 的示例行一旦同步就被完全覆盖。
3. **国企与上市表 1 的子列序相反**，单一真源是 `n1UnoffsetSubOrder(variant)`（前端）与 `_unoffset_sub_order(variant)`（幂等脚本）。新增消费方必须引用，不要写死字面量。
4. 审计过程数据（账面价值 / 计税基础 / 适用税率 / 确认依据 / 余额变动）在 N1-2 明细表与 N1-4 测算表，**不在披露表**——披露表只承载交付物内容。
