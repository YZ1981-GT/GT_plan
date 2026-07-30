# N1 递延所得税资产披露表与附注对齐 — 任务

## 1. 源模板精读与结论固化

- [ ] 1.1 逐 sheet 读 `backend/wp_templates/N/N1 递延所得税资产.xlsx` 两张披露 sheet（含合并单元格），结论写入 design.md §1
- [ ] 1.2 三层现状比对（底稿组件 / `n1NoteSectionMap.ts` / `note_template_*.json`），缺陷清单写入 requirements.md
- [ ] 1.3 确认 N1 sheet 分发安全（无 wp_code 后缀抢占、`国企`/`国有企业` 两种写法）

## 2. 附注模板 JSON 修订（后端）

- [ ] 2.1 新建 `backend/scripts/fix/fix_note_deferred_tax_structure.py`：`build_listed_tables()` / `build_soe_tables()` / `apply(--dry-run|--check)` / `_aligned_by`
- [ ] 2.2 listed 五、30 表 1 恢复 5 列 + `_column_groups` + 删 `header_label` 假数据行
- [ ] 2.3 soe 八、31 表 1 恢复 5 列 + `_column_groups`（子列序：资产/负债在前）+ 删假数据行
- [ ] 2.4 soe 八、31 表 2 3 列 → 5 列 + 行骨架补齐（资产段 7 项 + 小计 + 负债段 4 项 + 小计）
- [ ] 2.5 soe 八、31 新增表「递延所得税资产和递延所得税负债互抵明细」（2 列）
- [ ] 2.6 两版全部表补 `columns`（`flat` / `group` 明确表态）
- [ ] 2.7 两版全部表补 `guidance`（只取源模板红字/括注/勾稽口径）
- [ ] 2.8 `text_sections` 修订：表标题统一 `#### ` 前缀 + 补齐实质披露文本
- [ ] 2.9 新建 `backend/tests/test_note_deferred_tax_structure.py`：表数/列数/`_column_groups`/表态/guidance/text_sections/幂等
- [ ] 2.10 CI `governance-checks.yml` 加 job `note-deferred-tax-structure`（跑 `--check`）

## 3. 同步映射重写（前端 composable）

- [ ] 3.1 `n1NoteSectionMap.ts`：表 1 两级 5 列 `columns`（按 variant 定子列序）
- [ ] 3.2 `netOffsetColumns('soe')` 3 列 → 5 列；新增 `offsetDetailColumns()`
- [ ] 3.3 `N1_SUB_TABLE_KEYS.soe` 补第 5 个键（互抵明细）
- [ ] 3.4 `buildN1SyncPayload` 覆盖 5 表；行型判定先去空白；结构行 `header_label` / 小计合计 `is_total`
- [ ] 3.5 `N1_TABLE_NAMESPACE` + `seedSyncedTablesFromNote` + `buildRemovedTableKeys` 接入
- [ ] 3.6 `_note_texts` 补 R30 说明段

## 4. 勾稽引擎

- [ ] 4.1 新建 `composables/n1DisclosureConsistency.ts`（`eqCheck` 容差 0.01 / null → skip）
- [ ] 4.2 规则：段内小计、表（3）合计、表（4）合计、跨表「可抵扣亏损 = 亏损到期合计」（双列）、国企表（2）双段小计
- [ ] 4.3 新建 `n1/shared/N1DisclosureConsistencyPanel.vue`（紧凑 bar + 折叠明细 + 规则 tooltip + `GtIndexChip`）
- [ ] 4.4 单测 + PBT（`n1DisclosureConsistency.spec.ts`）

## 5. 底稿披露表重建（上市）

- [ ] 5.1 新建共用表组件 `n1/shared/N1DisclosureGroupTable.vue`（两级表头 + 分段 + 小计 + 动态增删行）
- [ ] 5.2 `N1TabDisclosureListed.vue` 表（1）：两级 5 列、资产/负债双段、`小 计` 公式行、动态增行
- [ ] 5.3 表（2）以抵销后净额列示（5 列 2 行）—— 新增
- [ ] 5.4 表（3）3 列 + `合  计` 公式行
- [ ] 5.5 表（4）4 列（年份/期末/上年年末/备注）+ `合  计` + 年度行增删
- [ ] 5.6 R30 说明可编辑正文（缺省取源模板文案）+ R31/R32/R43/R53 只读提示
- [ ] 5.7 删除自造 section（余额变动表 / 与 N3 对应关系），审计过程内容不搬进披露表
- [ ] 5.8 金额只读走 `fmtAmount`、可编辑走 `WpAmountInput`；AI 辅助按表就近放；`GtReviewTrigger`
- [ ] 5.9 接勾稽面板 + `useDisclosureAutoSync`

## 6. 底稿披露表重建（国企）

- [ ] 6.1 前置口径说明（R7）置顶方法论上下文
- [ ] 6.2 表（1）两级 5 列（子列序：资产/负债在前）+ 负债段第 4 项 `租赁形成`
- [ ] 6.3 表（2）互抵后 5 列 + 双段明细 + 双 `小 计`
- [ ] 6.4 表（3）互抵明细 2 列 + 动态增行
- [ ] 6.5 表（4）3 列 + `合  计`
- [ ] 6.6 表（5）4 列 + `合  计` + 年度行增删
- [ ] 6.7 R30/R31/R73 只读提示；删除 6 个自造 section
- [ ] 6.8 接勾稽面板 + `useDisclosureAutoSync` + AI/复核

## 7. 契约与守卫

- [ ] 7.1 新建 `__tests__/n1NoteSubtableContract.spec.ts`：接 `runDisclosureSubtableContract` + 双向键集 + 全表 guidance + headers 无空串
- [ ] 7.2 `columns` 顺序断言（表 1 子列序与 variant 匹配）
- [ ] 7.3 登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`
- [ ] 7.4 `disclosureSheetNameRegistry.spec.ts` 校验 `N1_DISCLOSURE_SHEET_NAME` 与 registry 逐字一致
- [ ] 7.5 `disclosureAutoSyncCoverage.spec.ts` 确认两 Tab 仍在册

## 8. 验证

- [ ] 8.1 后端 pytest（`test_note_deferred_tax_structure.py` + N1 既有测试零回归）
- [ ] 8.2 前端 vitest（N1 相关全量 + 契约 + 勾稽）
- [ ] 8.3 `get_diagnostics` 逐文件（vue-tsc 全项目在本机 OOM）
- [ ] 8.4 Vite transform 200 校验（`curl.exe` 两个 .vue）
- [ ] 8.5 Playwright/chrome-devtools 实测两 Tab：两级表头文案、勾稽 bar、编辑触发自动同步
- [ ] 8.6 postgres 只读比对 `disclosure_notes`：键数 / `_sub_table_columns` / `_last_sync_at`
- [ ] 8.7 交付说明写清「模板改动只对新建项目生效」
- [ ] 8.8* 清理临时文件（`tmp_*`）
