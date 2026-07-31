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

- [x] 1. P0 修复
- [x] 1.1 修 N5 两处 `get_active_filter` 签名错误
  - `_n5_income_tax_expense.py`：`_fetch_tb_data` 与 `_build_adjudication_prefill` 改为
    `await get_active_filter(ctx.db, Table.__table__, ctx.project_id, ctx.year or 0)`
  - 删除多余的手写 `Table.project_id == str(ctx.project_id)`（统一入口已含）
  - _Requirements: 1.1, 1.2, 1.5_

- [x] 1.2 修 N4 审定表 seed 空 if 块
  - `N4TabAdjudication.vue` 的 `onMounted` 空分支实装：无持久化行且 `tbData.unadjustedNet ≠ 0`
    时 seed 到合计/其他行，并在界面标注「总额级，需按税种分配」
  - 只填空不覆盖
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 1.3 P0 守卫（真实签名调用）
  - 新增 `backend/tests/test_n5_four_table_extraction.py`：以真实签名调用 `_fetch_tb_data`
    与 `_build_adjudication_prefill`，断言 `period_amount` 取本期发生额、有子科目时预填非 None
  - 新增前端断言：N4 seed 分支非空 if 块
  - _Requirements: 1.3, 1.4, 1.6, 2.4, 9.2_

- [x] 2. 共享模块 + 科目映射接入
- [x] 2.1 抽 `backend/app/services/deferred_tax_shared.py`
  - `LIABILITY_SLOTS` / `classify_liability_subaccount` / `code_predicate` / `leaf_rows` /
    `aggregate_by_slot` / `parse_num`
  - N1 侧保留同名模块属性（`test_n1_account_mapping.py` 按属性取用），行为零回归
  - _Requirements: 4.4_

- [x] 2.2 N3 接映射 + 叶子聚合 + 语义分类预填
  - `_LIABILITY_ROW_CODE = 'BS-067'`；`_resolve_account_codes`（fail-open）
  - `_fetch_tb_data` 科目级优先 → 叶子聚合（替代 `.limit(1)`）；`abs()` 归一
  - 新增 `_build_adjudication_prefill`（复用共享模块五语义槽）
  - render 输出 `adjudication_prefill` + `tb_source_codes`
  - _Requirements: 3.1, 3.4, 3.5, 4.1, 4.2, 4.3, 4.5_

- [x] 2.3 N4 接映射
  - `_N4_ROW_CODE = 'IS-003'`；`_fetch_period_amount` 接收 codes
  - `_classify_n4_subaccount`：10 个税种按**名称**归类（`6403` 子科目编码语义客户间冲突）
  - render 输出 `adjudication_prefill` + `tb_source_codes`（`basis: 'period'`）
  - _Requirements: 3.2, 3.4, 3.5_

- [x] 2.4 N5 接映射 + 当期/递延叶子拆分
  - `_N5_ROW_CODE = 'IS-023'`；拆分改用叶子排除父级防双算
  - render 输出 `tb_source_codes`（`basis: 'period'`）
  - _Requirements: 3.3, 3.4, 3.5, 5.1, 5.2, 5.4_

- [x] 2.5 清理 N3 披露 inert 残留
  - 后端 `N3_SHEETS` 删 `附注披露信息` 条目
  - 宿主 `GtN3DeferredTaxLiabilities.vue` 的 `currentSheet` 与 `isHtmlSheet` 删「附注」/「披露」分支
  - 守卫断言（Property 13）
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 3. 前端 TB 核对与四表带入
- [x] 3.1 三个审定表接 `useLmnTbReconcile`
  - N3 余额类（不传 `isIncome`）；N4 / N5 传 `{ isIncome: true }`
  - TB 全 0 时不渲染核对行
  - _Requirements: 6.1, 6.2, 6.3, 6.6_

- [x] 3.2 三个审定表加「从四表库带入未审数」按钮
  - 只填空不覆盖；提示带入行数
  - _Requirements: 6.4, 6.5_

- [x] 3.3 N3 预填按分类落行
  - `useN3Adjudication` 新增 `N3_SLOT_TO_CATEGORY` + `adjudicationPrefill` 入参，
    按语义槽映射到 `DEFAULT_CATEGORIES`，替代「全塞其他行」
  - _Requirements: 4.3_

- [x] 3.4 取数溯源展示（消除 dead output）
  - 三个审定表消费 `tb_source_codes`，展示科目集 + 报表行 + 口径（发生额 / 期末余额）
  - N3 的 `trial_balance` 经 `useN3FormData.renderMeta` 接入（原 `selfLoad` 把响应整个丢弃）
  - _Requirements: 3.6, 4.6_

- [x] 4. 公式预设纠错
- [x] 4.1 `1812` → `2901`
  - N3「明细表N3-2」块与 N5「N5-8递延所得税费用核对表」块
  - _Requirements: 8.1_

- [x] 4.2 N3 审定表块科目与命名纠正
  - `account_codes: ['6801']` → `['2901']`；`wp_name` 改递延所得税负债审定表
  - _Requirements: 8.2_

- [x] 4.3 N4 / N5 损益类改本期发生额 + 删/降级错误 cell
  - `期末余额` → `本期发生额`（对齐 `IS-003` / `IS-023`）
  - N5-4 `利润总额`：删 `TB('6001',...)` → `PLACEHOLDER` + 描述写明 `IS-022` 是 `ROW()` 派生行
  - N5-4 `法定税率`：删 `WP(...审定数)` → `PLACEHOLDER`
  - N4「城建税_期末余额」：删（活体 `6403.01` 实为印花税，子科目编码客户间冲突）
  - 补 N5 `6801.01 当期` / `6801.02 递延` 发生额预设
  - 幂等脚本 `backend/scripts/fix/fix_n345_prefill_presets.py`（9 处修订，`--check` 绿）
  - _Requirements: 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 4.4 预设纯净性守卫
  - 新增 `backend/tests/formula_management/test_n345_preset_purity.py`（Property 8/9/10）
  - _Requirements: 8.8, 8.9, 9.3_

- [x] 5. 守卫收口与活体实测
- [x] 5.1 平台守卫：四表键不得 dead output
  - 新增 `__tests__/fourTableOutputConsumption.spec.ts`：扫 render 策略源码取四表键名 →
    断言前端源码有消费点；带豁免清单（须写理由）+ 反向自检
  - 断言 `useLmnTbReconcile` 引用点 ≥ 3 且 N3/N4/N5 三个审定表各自在册
  - 追加 N5 专属两组断言（见 5.5）
  - _Requirements: 9.1, 9.4_

- [x] 5.2 全量测试
  - 后端 190 绿（N3/N4/N5 取数 + 预设纯净 + N1 回归）
  - 前端定向 45 绿（N1 披露预填/分支 + N4 引擎 + 平台四表守卫 17）
  - 前端 N 类 sheet 分发/附注契约/N3·N5 单测契约 PBT 全绿
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 5.3 CI job 挂载
  - `governance-checks.yml` 新增 `n345-four-table-extraction` / `four-table-output-consumption`
  - _Requirements: 9.1_

- [x] 5.4 活体实测
  - 见下「实测记录」
  - _Requirements: 9.5_

- [x] 5.5 实测挖出的两个 N5 静默缺陷（补做）
  - `GtN5IncomeTaxExpense.vue`：`onMounted` 的 `props.htmlData` 分支漏提取四表键 →
    抽 `_absorbFourTableKeys()` 两条路径共用；顺带删重复 `provide('scheduleAutoSnapshot')`
  - `N5TabAdjudication.vue`：`handleCellChange` 改为**两行一并落库**；`applyTbSeed` 加
    「四表全 0 直接返回」守卫 + 区分「已自动预填」与「手工优先不覆盖」两种提示
  - 守卫：`fourTableOutputConsumption.spec.ts` 追加 7 条断言（含 `stripComments` 反向自检
    与 `functionBody` 花括号配对自检）
  - _Requirements: 6.4, 6.5, 9.1_

## 实测记录

### 后端取数（真实 DB）

| 循环 | 项目 | 报表行 → 科目 | 结果 |
|------|------|---------------|------|
| N3 | `2aa00f57` / `a7fc75e5` | `BS-067` → `['2901']` | 期末 233,512.19 / 200,530.32（两种符号约定被同一段 `abs()` 归一），五语义槽合计 == TB 期末 |
| N4 | `a7fc75e5` | `IS-003` → `['6403']` | 11,258,989.55（与 `trial_balance` 一致；**改造前恒 0**） |
| N5 | `a7fc75e5` | `IS-023` → `['6801']` | 21,151,383.26（当期 24,891,157.62 / 递延 −3,739,774.36，勾稽成立） |
| N5 | `f064f5e4` / 2024 | `IS-023` → `['6801']` | `trial_balance` 无 6801 → 兜底 `tb_balance.debit_amount` 叶子：`6801.02` = −329,846.13，父级 `6801` 已排除防双算，`source: tb_balance` |

### 浏览器实测（chrome-devtools + postgres 只读）

- **N3 审定表**（`2aa00f57`）：TB 核对条显示「科目 2901（报表行 BS-067 · 期末余额）」；
  233,512.19 现落在**「使用权资产」**行（改造前全堆在「其他」行）。
- **N4 审定表**（`2aa00f57`）：按税种带入生效 —— 城建税 1,022,169.44 / 教育费附加 438,072.64 /
  地方教育附加 292,048.39 / 房产税 529,613.28 / 土地使用税 33,411.91 / 车船税 1,500 /
  印花税 137,266.86，合计 2,454,082.52。TB 核对报差异 −2,454,082.52，因试算表为
  4,908,165.04 恰好 2 倍 → **该项目已知的双数据集双算问题被核对行正确暴露**（非本 spec 缺陷）。
- **N5 审定表**（`f064f5e4` / 2024 / wp `9c968253`）：
  - 修复前「从四表库带入未审数」按钮与 TB 核对条**完全不渲染**（宿主 provide 断链）；
    修复后按钮可点、核对条显示「试算平衡表数 −329,846.13 · 审定合计 −329,846.13 ·
    科目 6801（报表行 IS-023 · 本期发生额）」，递延行自动预填 −329,846.13、合计行正确派生。
  - 点带入 → 提示「四表取数已自动预填到本表，无需重复带入」（零值不再落库）。
  - 手工改当期行 RJE = 5,000 → **两行都落库**（`N5-1-current-row` + `N5-1-deferred-row`，
    递延行带四表值）；刷新后（后端预填门已关闭）递延 −329,846.13 **仍在**，
    核对条正确转为差异态（审定合计 −324,846.13）。
  - 测试数据已完整复原（`checklist_responses` 该 wp 回到 0 行，与实测前一致）。

### 实测顺带修掉的预存在缺陷

- `useN4CrossSheet.ts` 用 `getResponseNum` 但既未 import 也未定义 → **N4 整页渲染崩**
  （界面报「页面渲染出错 getResponseNum is not defined」），已补本地定义。
- `useN4FormData.selfLoad` 只取顶层 `html_data`（恒 `undefined`），改为扫 `sheets[].html_data`。

### 两个重大口径实证

1. **损益类「Σ借 − Σ贷」在全年账上结构性恒为 0**：序时账必含年末「结转损益」分录
   （活体 `6801.01` 凭证 0409 计提借 110,445.40 / 凭证 0410 结转损益贷 110,445.40），
   9 个项目的 `6403` / `6801` 借贷两侧金额全部相等。权威口径 = `trial_balance`
   （`TB()` 的 `_handle_tb` 读 `ctx.tb_data` ← `trial_balance`），兜底
   `tb_balance.debit_amount`（**仅借方**，负借方语义即"贷方性质"，直取可保留符号）。
2. **「28 个测试全绿」不等于取数能跑**：N5 两处 `get_active_filter(ctx.project_id)` 单参调用
   → `TypeError` 被 `except Exception` 吞成 warning → 取数恒 0 / 预填恒 None，
   而既有测试只测导入可用性与 `_parse_num`，**从不真实调用取数函数**。

### 数据可见性注意

`get_active_filter` 在项目有 active dataset 时强制 `dataset_id == active_id` →
**`dataset_id` 为 NULL 的历史导入行被排除**。项目 `2aa00f57` 的 `6801` 两行 dataset_id 为
NULL，故其 N5 取数为 0 且 `source: 'none'` —— 这是**正确的平台行为**，不是取数缺陷；
选活体项目时须先确认目标科目落在 active 数据集内。

## Notes

- **不在范围内**：N3 披露（源模板无该 sheet，与 N1 共节）；N4 / N5 披露结构
  （已由归档 spec `n-cycle-tax-disclosure-alignment` 对齐）；N2 应交税费。
- **并发风险**：`prefill_formula_mapping.json` 被多个在飞 spec 同时改 → 一律 `str_replace`
  增量修改，禁整文件覆盖。
- **`inventory.json` 不重生成**：预存在漂移（232 页 vs 运行时 255 页），本 spec 未新增
  `page_key` 故不动它；守卫用 `convert_prefill_presets()` 运行态输出。
- **平台级待办（本 spec 不做）**：`page_key = workpaper:{wp_code}` 忽略 sheet 导致
  `上年审定数` 在 25+ 循环内撞键。
- **后端 sheet 名漂移（暂不动）**：`N4_SHEETS` 写「附注披露信息（国有企业）」、
  `N5_SHEETS` 写「附注披露信息（上市）」，与前端 `X_DISCLOSURE_SHEET_NAME` 及
  `workpaper_sheet_classification` 三处各不相同 —— 属披露侧，归 `disclosureSheetNameRegistry`
  体系，另立。
- **N5 审定表是全平台异类**：把两行存成两个 checklist item（N3 / N4 整表存一个
  `adjudication-rows`），故独有「预填门关闭后另一行丢值」窗口。新增循环若沿用逐行存法，
  必须同样做到「任一行变更时整组一并落库」。
