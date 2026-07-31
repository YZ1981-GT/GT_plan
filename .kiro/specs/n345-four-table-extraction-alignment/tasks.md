# Implementation Plan: N3/N4/N5 四表取数对齐

## Overview

五个 wave：①修 P0（N5 `get_active_filter` 签名错致取数恒 0、N4 审定表空 if 块）；
②抽共享 `deferred_tax_shared` 并让三循环接 `report_config` 科目映射 + 输出 `tb_source_codes`；
③前端接现成件 `useLmnTbReconcile` + 补「从四表库带入」按钮 + N3 预填按分类落行；
④公式预设纠错（`1812`→`2901`、损益类改发生额、删/降级 `利润总额`/`法定税率`/`6403.01`）；
⑤守卫收口（含「四表键不得 dead output」平台守卫）+ 活体实测。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "P0 修复（取数完全失效）",
      "tasks": ["1.1", "1.2", "1.3"],
      "parallel": false
    },
    {
      "wave": 2,
      "name": "共享模块 + 科目映射接入",
      "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5"],
      "parallel": false
    },
    {
      "wave": 3,
      "name": "前端 TB 核对与四表带入",
      "tasks": ["3.1", "3.2", "3.3", "3.4"],
      "parallel": false
    },
    {
      "wave": 4,
      "name": "公式预设纠错",
      "tasks": ["4.1", "4.2", "4.3", "4.4"],
      "parallel": false
    },
    {
      "wave": 5,
      "name": "守卫收口与活体实测",
      "tasks": ["5.1", "5.2", "5.3", "5.4"],
      "parallel": false
    }
  ]
}
```

Wave 2 依赖 Wave 1（同一批文件）。Wave 3 依赖 Wave 2（消费新键）。Wave 4 独立。Wave 5 收口。

## Tasks

- [ ] 1. P0 修复
- [ ] 1.1 修 N5 两处 `get_active_filter` 签名错误
  - `_n5_income_tax_expense.py`：`_fetch_tb_data` 与 `_build_adjudication_prefill` 改为
    `await get_active_filter(ctx.db, Table.__table__, ctx.project_id, ctx.year or 0)`
  - 删除多余的手写 `Table.project_id == str(ctx.project_id)`（统一入口已含）
  - _Requirements: 1.1, 1.2, 1.5_

- [ ] 1.2 修 N4 审定表 seed 空 if 块
  - `N4TabAdjudication.vue` 的 `onMounted` 空分支实装：无持久化行且 `tbData.unadjustedNet ≠ 0`
    时 seed 到合计/其他行，并在界面标注「总额级，需按税种分配」
  - 只填空不覆盖
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 1.3 P0 守卫（真实签名调用）
  - 新增 `backend/tests/test_n5_four_table_extraction.py`：以真实签名调用 `_fetch_tb_data`
    与 `_build_adjudication_prefill`，断言 `period_amount = Σ借 − Σ贷`、有子科目时预填非 None
  - 新增前端断言：N4 seed 分支非空 if 块
  - _Requirements: 1.3, 1.4, 1.6, 2.4, 9.2_

- [ ] 2. 共享模块 + 科目映射接入
- [ ] 2.1 抽 `backend/app/services/deferred_tax_shared.py`
  - `LIABILITY_SLOTS` / `classify_liability_subaccount` / `code_predicate` / `leaf_rows` / `aggregate_by_slot`
  - N1 侧改为薄壳委托（保留模块内同名属性，`test_n1_account_mapping.py` 按属性取用）
  - 新增 `backend/tests/test_deferred_tax_shared.py`（含与 N1 行为等价 characterization）
  - _Requirements: 4.4_

- [ ] 2.2 N3 接映射 + 叶子聚合 + 语义分类预填
  - `_LIABILITY_ROW_CODE = 'BS-067'`；`_resolve_account_codes`（fail-open）
  - `_fetch_tb_data` 科目级优先 → 叶子聚合（替代 `.limit(1)`）；`abs()` 归一
  - 新增 `_build_adjudication_prefill`（复用共享模块五语义槽）
  - render 输出 `adjudication_prefill` + `tb_source_codes`
  - _Requirements: 3.1, 3.4, 3.5, 4.1, 4.2, 4.3, 4.5_

- [ ] 2.3 N4 接映射
  - `_N4_ROW_CODE = 'IS-003'`；`_fetch_tb_period_amount` 接收 codes（`tb_ledger` 发生额口径不变）
  - render 输出 `tb_source_codes`（`basis: 'period'`）
  - _Requirements: 3.2, 3.4, 3.5_

- [ ] 2.4 N5 接映射 + 当期/递延叶子拆分
  - `_N5_ROW_CODE = 'IS-023'`；拆分改用共享 `leaf_rows` 排除父级防双算
  - render 输出 `tb_source_codes`（`basis: 'period'`）
  - _Requirements: 3.3, 3.4, 3.5, 5.1, 5.2, 5.4_

- [ ] 2.5 清理 N3 披露 inert 残留
  - 后端 `N3_SHEETS` 删 `附注披露信息` 条目
  - 宿主 `GtN3DeferredTaxLiabilities.vue` 的 `currentSheet` 与 `isHtmlSheet` 删「附注」/「披露」分支
  - 守卫断言（Property 13）
  - _Requirements: 7.1, 7.2, 7.3_

- [ ] 3. 前端 TB 核对与四表带入
- [ ] 3.1 三个审定表接 `useLmnTbReconcile`
  - N3 余额类（不传 `isIncome`）；N4 / N5 传 `{ isIncome: true }`
  - TB 全 0 时不渲染核对行
  - _Requirements: 6.1, 6.2, 6.3, 6.6_

- [ ] 3.2 三个审定表加「从四表库带入未审数」按钮
  - 只填空不覆盖；提示带入行数
  - _Requirements: 6.4, 6.5_

- [ ] 3.3 N3 预填按分类落行
  - 前端 `n3LiabilitySlotLabel` 单一真源（与 N1 `N1_LIABILITY_SLOT_LABEL` 同源口径）
  - `useN3Adjudication` 改按语义槽映射到 `DEFAULT_CATEGORIES`，替代「全塞其他行」
  - _Requirements: 4.3_

- [ ] 3.4 取数溯源展示（消除 dead output）
  - 三个审定表消费 `tb_source_codes`，展示科目集 + 报表行 + 口径（发生额 / 期末余额）
  - N3 的 `formula_direction` / `n3_metadata` / `trial_balance`：接入或移除
  - _Requirements: 3.6, 4.6_

- [ ] 4. 公式预设纠错
- [ ] 4.1 `1812` → `2901`
  - N3「明细表N3-2」块与 N5「N5-8递延所得税费用核对表」块
  - _Requirements: 8.1_

- [ ] 4.2 N3 审定表块科目与命名纠正
  - `account_codes: ['6801']` → `['2901']`；`wp_name` 改递延所得税负债审定表
  - _Requirements: 8.2_

- [ ] 4.3 N4 / N5 损益类改本期发生额 + 删/降级错误 cell
  - `期末余额` → `本期发生额`（对齐 `IS-003` / `IS-023`）
  - N5-4 `利润总额`：删 `TB('6001',...)` → `PLACEHOLDER` + 描述写明 `IS-022` 是 `ROW()` 派生行
  - N5-4 `法定税率`：删 `WP(...审定数)` → `PLACEHOLDER`
  - N4「城建税_期末余额」：删（活体 `6403.01` 实为印花税，子科目编码客户间冲突）
  - 补 N5 `6801.01 当期` / `6801.02 递延` 发生额预设
  - _Requirements: 8.3, 8.4, 8.5, 8.6, 8.7_

- [ ] 4.4 预设纯净性守卫
  - 新增 `backend/tests/formula_management/test_n345_preset_purity.py`（Property 8/9/10）
  - _Requirements: 8.8, 8.9, 9.3_

- [ ] 5. 守卫收口与活体实测
- [ ] 5.1 平台守卫：四表键不得 dead output
  - 新增 `__tests__/fourTableOutputConsumption.spec.ts`：扫 render 策略源码取四表键名 →
    断言前端源码有消费点；带豁免清单（须写理由）+ 反向自检
  - 断言 `useLmnTbReconcile` 引用点 ≥ 3
  - _Requirements: 9.1, 9.4_

- [ ] 5.2 全量测试
  - 后端 N3/N4/N5 + 共享模块 + 预设；前端 N3/N4/N5 相关 + 平台守卫
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [ ] 5.3 CI job 挂载
  - `governance-checks.yml` 新增 job 覆盖新守卫
  - _Requirements: 9.1_

- [ ] 5.4 活体实测
  - 先查活体 `tb_ledger` 是否有 `6403` / `6801` 发生额，据此选项目
  - 真实 DB 直跑三个 render + 浏览器验审定表 TB 核对与带入按钮
  - 验证后复原测试数据
  - _Requirements: 9.5_

## Notes

- **不在范围内**：N3 披露（源模板无该 sheet，与 N1 共节）；N4 / N5 披露结构
  （已由归档 spec `n-cycle-tax-disclosure-alignment` 对齐）；N2 应交税费。
- **并发风险**：`prefill_formula_mapping.json` 被多个在飞 spec 同时改 → 一律 `str_replace`
  增量修改，禁整文件覆盖。
- **`inventory.json` 不重生成**：预存在漂移（232 页 vs 运行时 255 页），本 spec 若不新增
  `page_key` 就不动它；守卫用 `convert_prefill_presets()` 运行态输出。
- **平台级待办（本 spec 不做）**：`page_key = workpaper:{wp_code}` 忽略 sheet 导致
  `上年审定数` 在 25+ 循环内撞键；N3 / N4 / N5 内部的该撞键会被 Property 10 拦住并要求改名。
- **后端 sheet 名漂移（暂不动）**：`N4_SHEETS` 写「附注披露信息（国有企业）」、
  `N5_SHEETS` 写「附注披露信息（上市）」，与前端 `X_DISCLOSURE_SHEET_NAME` 及
  `workpaper_sheet_classification` 三处各不相同 —— 属披露侧，归 `disclosureSheetNameRegistry`
  体系，另立。
