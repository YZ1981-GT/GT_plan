# Implementation Plan: D1 取数链路补齐与披露/附注口径修复

## Overview

六个 wave：①后端科目映射解析层（报表映射 → 标准码 → 原始码）；②前端共享锚点模型
（消灭跨表锚点漂移）+ 审定表坏账/动态票据种类补齐；③披露表接共享模型 + 口径修复；
④D1-3 辅助余额表取数；⑤公式管理预设与报表↔附注映射；⑥守卫收口 + 浏览器实测。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "后端科目映射解析层与 seed 泛化",
      "tasks": ["1.1", "1.2", "1.3", "1.4"],
      "depends_on": []
    },
    {
      "wave": 2,
      "name": "前端共享锚点模型 + 审定表取数补齐",
      "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5"],
      "depends_on": []
    },
    {
      "wave": 3,
      "name": "披露表接共享模型 + 源模板口径修复",
      "tasks": ["3.1", "3.2", "3.3", "3.4"],
      "depends_on": [2]
    },
    {
      "wave": 4,
      "name": "D1-3 辅助余额表客户维度取数",
      "tasks": ["4.1", "4.2", "4.3"],
      "depends_on": [1]
    },
    {
      "wave": 5,
      "name": "公式管理预设与报表↔附注映射",
      "tasks": ["5.1", "5.2", "5.3"],
      "depends_on": [1]
    },
    {
      "wave": 6,
      "name": "守卫收口与浏览器实测",
      "tasks": ["6.1", "6.2", "6.3"],
      "depends_on": [1, 2, 3, 4, 5]
    }
  ]
}
```

Wave 1 与 Wave 2 无相互依赖（后端/前端各自独立），可并行推进。Wave 3 硬依赖 Wave 2 的
共享模型。Wave 4 依赖 Wave 1 的科目解析。Wave 5 依赖 Wave 1（sheet 名/维度实证）。
Wave 6 收口。

## Tasks

- [x] 1. 后端科目映射解析层与 seed 泛化
- [x] 1.1 新建 `backend/app/services/d_cycle_extraction/d1_account_resolver.py`
  - `D1_REPORT_ROW_CODE='BS-005'` / `D1_FALLBACK_CODES=['1121','1231-01']`（DB 实证）
  - 纯函数 `split_gross_provision(codes, chart_rows)`（备抵判定：`direction=='credit'` 或名含「坏账准备」/「减值准备」）
  - 纯函数 `normalize_standard_prefix('1231-01') → '1231'`
  - `async resolve_d1_account_codes(ctx) -> D1AccountCodes`：报表映射 → 拆分 → `account_mapping` 反解原始码，全程 fail-open 标注 `resolved_from`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - _Properties: 1, 2, 3_

- [x] 1.2 泛化 `d1_detail_seed.py`
  - `_fetch_leaves(ctx, prefixes: list[str], *, name_contains=None)`：单前缀 → 前缀集（`or_`）
  - `seed_d1_detail_rows(ctx, snapshot, codes=None)`：`codes` 为 None 时自解析；坏账侧仅 `resolved_from=='fallback'` 时叠加名称过滤
  - _Requirements: 1.1, 1.3, 1.4_
  - _Properties: 1, 3_

- [x] 1.3 接入 `_d1_notes_receivable.py::render`
  - 灰度分支内解析 codes 并传给 seed
  - `html_data['tb_source_codes']`（additive）
  - `trial_balance` 查询改用 `gross_standard`；新增 `project_context['tb_provision_amount']`
  - _Requirements: 1.6, 1.7_
  - _Properties: 1, 10_

- [x] 1.4 后端守卫 `backend/tests/d_cycle_extraction/test_d1_account_resolver.py`
  - Property 1/2/3 全覆盖 + 反向自检（构造 credit 科目必须被判成 provision）
  - 扩展 `test_d1_render_prefill_integration.py`：灰度关逐字节等价（Property 10）、`tb_source_codes` 结构
  - _Requirements: 8.3_
  - _Properties: 1, 2, 3, 10_

- [x] 2. 前端共享锚点模型 + 审定表取数补齐
- [x] 2.1 新建 `composables/d1AdjudicationModel.ts`（零依赖 leaf 纯函数）
  - `d1AdjAnchor` / `d1CategorySlug` / `readD1Categories` / `readD1BadDebtByNoteType` / `readD1AdjudicationTotals`
  - 审定数现算 = 未审 + 账项调整 + 重分类调整；净值 = 原值 − 坏账
  - _Requirements: 3.1, 3.2, 3.4_
  - _Properties: 4, 5, 6_

- [x] 2.2 `useD1BadDebt.ts` 新增「按票据种类小计」区块
  - 持久化键 `D1-bd-notetype-rows`，行名逐字「银行承兑汇票小计」「商业承兑汇票小计」+ 动态票据种类
  - 与 D1-4 合计行的勾稽提示（源模板 R22 vs R23+R24）；**不做按原值比例分摊**
  - _Requirements: 2.1, 2.3_

- [x] 2.3 `useD1Adjudication.ts` 三区块改由共享模型驱动
  - 行集由 `readD1Categories` 派生（银承/商承固定在前 + 动态追加）
  - 坏账区块接 `readD1BadDebtByNoteType` override（未命中保持可编辑且 `isFromCrossSheet=false`）
  - 新增 `crossCheckRows`（D1-2 合计 vs 原值小计 / D1-4 合计 vs 坏账小计）
  - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6_
  - _Properties: 5, 6, 7_

- [x] 2.4 锚点登记表扩展
  - `d_cycle_anchor_registry.json` D1 模式锚点接纳动态 slug；新增 `D1-bd-notetype-rows`
  - _Requirements: 2.5_
  - _Properties: 4_

- [x] 2.5 前端守卫
  - `composables/__tests__/d1AdjudicationModel.spec.ts`（Property 4/5/6/7 + 与 registry 正则交叉校验）
  - `composables/__tests__/d1AnchorSingleSource.spec.ts`：扫 D1 全部 composable/vue 源码，禁止模块外构造 `D1-adj-*` 字面量（含 `stripComments` 与反向自检）
  - _Requirements: 8.1, 8.2_
  - _Properties: 4_

- [x] 3. 披露表接共享模型 + 源模板口径修复
- [x] 3.1 `useD1Disclosure.ts` 删除 `CROSS_SHEET_KEYS`
  - `crossSheetData` / `categorySummaryRows` / `canEditCategorySummary` 改由 `readD1AdjudicationTotals` 驱动，支持动态票据种类
  - _Requirements: 3.1, 3.2, 3.3_
  - _Properties: 4, 5_

- [x] 3.2 `useD1InventoryCount.ts` / `useD1RelatedPartyCheck.ts` / `useD1CrossSheet.ts` 改用共享模型
  - 删除 `D1-adj-notes-receivable-current-audited`（无写入方）
  - _Requirements: 3.4_
  - _Properties: 4_

- [x] 3.3 源模板口径修复
  - `d1NoteSectionMap.ts`：国企组合表 `loss_rate` → `pct()`；`mergePortfolio` / `individualTable` 合计行损失率改派生
  - `useD1FormulaEngine.ts`：新增 `calcDisclosureBadDebtEnd`（其他为减项），`calcBadDebtEndBalance` 不动
  - `useD1Disclosure.updateCell('movement'|'movementDetail')` 改用新函数
  - `D1TabDisclosure.vue`：`buildD1SyncPayload` 的 `applicableStandards` 接 `useHostApplicableStandards`
  - 账龄口径不一致的只读提示（不自动删数据）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_
  - _Properties: 8, 9_

- [x] 3.4 前端守卫
  - 修正 `useD1Disclosure.pbt.spec.ts` / `useD1DisclosureDerived.spec.ts`：fixture 锚点改取共享常量（Requirement 8.2）
  - 新增 `d1DisclosureRateUnit.spec.ts`（Property 8）与 `d1MovementSign.spec.ts`（Property 9）
  - _Requirements: 8.2, 8.3_
  - _Properties: 8, 9_

- [x] 4. D1-3 辅助余额表客户维度取数
- [x] 4.1 后端端点 `POST /api/workpapers/{wp_id}/d1/import-aux-balance`
  - `aux_type='客户'` + `codes.gross` 原始码 + `get_active_filter`，按客户名合并、票据种类以「/」连接
  - 无维度/无匹配 → `imported_count=0`，不抛错
  - _Requirements: 4.1, 4.2, 4.3, 4.5_
  - _Properties: 11_

- [x] 4.2 前端 `useD1DetailCustomer.ts` + `D1TabDetailCustomer.vue` 接入
  - 「从辅助余额表导入」按钮；按客户名合并，不覆盖关联方标记/期后兑付/备注
  - 归集合计与 tb 原值期末合计勾稽提示
  - _Requirements: 4.4, 4.5_
  - _Properties: 11_

- [x] 4.3 守卫 `backend/tests/d_cycle_extraction/test_d1_aux_import.py`（Property 11 + 合并语义）
  - _Requirements: 8.3_
  - _Properties: 11_

- [x] 5. 公式管理预设与报表↔附注映射
- [x] 5.1 修订 `prefill_formula_mapping.json` 的 D1 段
  - sheet 名纠正（`原值明细表（按客户）D1-3` / `坏账准备明细表D1-4`）
  - `TB_AUX('1121','票据类型',…)` → `TB_AUX('1121','客户','期末余额')` 并归到 D1-3
  - 补 D1-2（`TB('1121',…)`）/ D1-4（`TB('1231-01',…)`）/ D1-1（两条 `WP()`）
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Properties: 12_

- [x] 5.2 更新 `presets.py::_TIER_B_PROVENANCE['D1']`
  - D1-2/D1-4 溯源改为「报表映射 BS-005 → 标准码 → account_mapping → tb_balance 叶子」
  - 新增 D1-3 ← `tb_aux_balance` 客户维度条目
  - _Requirements: 5.3_

- [x] 5.3 `report_note_linkage.json` 补 BS-005 → 五、4 / 八、4
  - 依据 F4-1 / F4-2 人工核实；同步加入 `test_report_note_linkage_diagnose._VERIFIED_SEED_ROW_CODES`
  - 守卫 `backend/tests/test_d1_prefill_presets.py`（Property 12）
  - _Requirements: 7.3, 5.5_
  - _Properties: 12_

- [ ] 6. 守卫收口与浏览器实测
- [ ] 6.1 附注结构复核（源模板 14/12 表逐表）
  - 以源模板 sheet + F4 预设为裁决者产出差异清单（无差异亦记录）
  - 有欠账则 `fix_note_d1_notes_receivable_structure.py` 增量修复 + `--check` 归零
  - _Requirements: 7.1, 7.2, 7.4_

- [ ] 6.2 全量回归
  - 后端 `backend/tests/d_cycle_extraction/` + D1 相关；前端 D1 相关全绿（既有基线除外）
  - CI job `d1-extraction-chain`
  - _Requirements: 8.3_

- [ ] 6.3 浏览器实测（chrome-devtools + postgres 只读）
  - 真实项目 `0ec33ac9…`/2025：D1-2/D1-4 有数 → D1-1 原值+坏账+净值有数 → 披露①分类表有数 → 推送后附注 五、4·八、4 落库正确（列头/两级表头/比率百分数）
  - 测试数据用后复原
  - _Requirements: 8.4_
  - _Properties: 5, 6, 8_

## Notes

### 前置依赖：灰度开关

`settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 默认 `False`（D2~D7 公用，翻默认属平台级）。
Wave 1 的取数在运行态需该开关为 True 才生效；Wave 2/3 的**跨表链路修复不受该开关约束**
（读的是 checklist_responses，手工录入同样受益）。Wave 6.3 实测前需确认开关策略。

### 明确不做（宁缺勿造边界）

- **坏账准备按票据种类分摊**：`tb_balance` 1231.01 只有总额，按原值比例分摊无审计依据，
  仅提供手工录入 + 与 D1-4 合计的勾稽提示。
- **`tb_aux_balance` 1231.01 的「计提方式」/「减值方式」维度**：实证数据自相矛盾
  （`本期计提额` 值等于期初余额、`opening_balance` 全 NULL、closing 有正负混杂），不作取数源。
- **`report_config` listed 侧 BS-005 公式缺减坏账**（`TB('1121','期末余额')` 未减 `1231-01`，
  与 `soe_standalone` 不一致）：属平台级报表配置数据缺陷，本 spec 只报告不改（影响全部项目报表）。
- **`note_template` 全库 `report_row_code` 陈旧**：平台级 data-hygiene 待办，不在本 spec。
