# Implementation Plan: K2 四表取数纠偏 + K2-1 审定表动态行

## Overview

两条主线：**A 取数口径**（Wave 1→2）把 `1231 坏账准备` 换成 `BS-014` 报表映射解析的
`1901`，复用 K1 建立的 `four_table` 共享件（K2 是第三个消费者）；**B 行模型**（Wave 3）
把 K2-1 审定表从硬编码 8 行改为动态行，对齐同循环 K2-2 明细表已有范式。
Wave 4 收尾（公式预设 / sheet 名 / 实测）。

不动披露列结构与附注模板 —— 归档 spec `k2-other-current-assets-disclosure-alignment`
已完成 22/22 + 浏览器实测。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "后端取数口径纠偏（纯函数 + 单测）",
      "tasks": ["1.1", "1.2", "1.3"],
      "depends_on": []
    },
    {
      "wave": 2,
      "name": "前端消费：tb_values 口径 + 溯源面板",
      "tasks": ["2.1", "2.2"],
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "K2-1 审定表动态行改造",
      "tasks": ["3.1", "3.2", "3.3", "3.4"],
      "depends_on": []
    },
    {
      "wave": 4,
      "name": "公式预设 / sheet 名 / 实测收口",
      "tasks": ["4.1", "4.2", "4.3", "4.4"],
      "depends_on": [1, 2, 3]
    }
  ]
}
```

## Tasks

- [x] 1.1 重写 `_k2_other_current_assets.py` 取数部分：声明 `K2_ACCOUNT_SPEC`
  （`row_code='BS-014'`、`fallback_gross=('1901',)`、`fallback_provision=()`、
  `extra_standard_codes=('1131',)`），`render` 改用
  `resolve_report_line_accounts` + `select_leaves` + `aggregate_leaves`；
  删除 `_K2_ACCOUNT_PREFIXES` / `_K2_ACCOUNT_PREFIX` / 旧 `_fetch_tb_data`（死代码直接删）。
  `tb_values` 键名保持不变（前端已在读）。
  - Requirements: 1.1, 1.2, 1.3, 1.4, 1.6
  - Properties: 1, 2, 3, 4

- [x] 1.2 `_build_adjudication_prefill` 改纯函数（入参 leaves + accounts）：按原值侧
  **叶子科目名**建动态行候选 `[{name, code, opening_balance, closing_balance}]`；
  **宁缺勿造** —— 无可识别科目返回 `[]`，不塞兜底行；`_build_tb_values` 同样改纯函数，
  `trial_balance` 求和按最长前缀归属。
  - Requirements: 1.4, 1.5, 2.6
  - Properties: 3, 8

- [x] 1.3 新建 `backend/tests/four_table/test_k2_account_scope.py`：
  科目集不含 `1231*`（含反向自检：断言旧口径确实会命中坏账准备）、`1131` 只在 `extra`、
  叶子口径与点号边界、`trial_balance` 最长前缀、fail-open 六种组合、
  `tb_source_codes` 形态、`provision` 为空是合法态。
  - Requirements: 5.1, 5.3
  - Properties: 1, 2, 3, 4

- [x] 2.1 把 K1 的 `K1FourTableSourcePanel.vue` 提升为共用
  `workpaper/shared/WpFourTableSourcePanel.vue`（props: `sourceCodes` + `hints`），
  K1 侧改薄壳委托（零回归由 K1 的 111 例守卫证明），K2 侧复用。
  - Requirements: 1.7
  - Properties: 11

- [x] 2.2 `GtK2OtherCurrentAssets.vue` 透传 `tbSourceCodes`；`K2TabAdjudication.vue`
  顶部挂溯源面板；`tbData` 口径注释更新（不再是 1231）。
  - Requirements: 1.7
  - Properties: 1

- [x] 3.1 新建**平台级共享件** `composables/shared/dynamicAdjudicationRows.ts`
  （零 Vue 依赖纯函数，循环差异全由入参 `DynamicRowsSpec` 声明，模块内不含任何
  循环专属常量）：`serializeRows` / `deserializeRows` / `nextRowId` /
  `normalizeLabel` / `findDuplicateLabel` / `migrateLegacyFixedRows` /
  `seedRowsFromPrefill` / `rowFieldItemId` / `collectRowItemIds` / `dropRow`。
  同时建 K2 薄壳 `composables/k2AdjudicationRows.ts` 只放 K2 的 spec 声明。
  - Requirements: 2.1, 2.4, 2.5, 2.6
  - Properties: 5, 6, 8

- [x] 3.2 改造 `useK2Adjudication.ts`：行集由 `K2-1-rows` 动态清单驱动；
  新增 `addRow`（`ElMessageBox.prompt` 命名 + 撞名拒绝）/ `renameRow` / `removeRow`
  （清理 `K2-1-{rowId}-*` 全部键）/ `pullFromDetail`（从 K2-2 按行名聚合）；
  `seedFromPrefill` 去掉模糊包含匹配与 `other` 兜底；合计行覆盖全部动态行。
  - Requirements: 2.1, 2.2, 2.3, 2.6, 2.7, 2.8
  - Properties: 5, 7, 8, 9

- [x] 3.3 `K2TabAdjudication.vue`：行名可编辑（`el-input` `@input` 回写）、
  「新增项目行」/「删除」/「从 K2-2 带入」/「从四表库带入」按钮
  （`:disabled="isReadonly"` + `:loading`）、外来行警示 tag + tooltip、
  金额列走 `WpAmountInput`（若尚未）。
  - Requirements: 2.2, 2.3, 2.5, 2.7
  - Properties: 5, 7

- [x] 3.4 新建 `composables/__tests__/k2AdjudicationRows.spec.ts` +
  `k2FourTableWiring.spec.ts`：动态行往返 PBT、迁移不丢数、删除清理干净、
  宁缺勿造、合计覆盖、溯源透传、**反向自检**（源码不得残留硬编码 8 行枚举）。
  - Requirements: 5.2, 5.3
  - Properties: 5, 6, 7, 8, 9

- [x] 4.1 修 `prefill_formula_mapping.json` 的 K2 块：`wp_name` →「其他流动资产审定表」、
  `account_codes` → `['1901']`、公式 `6601` → `1901`、补
  `WP('K2','明细表K2-2','审定数期末数')`；K2-2 块保持无 `WP()`。
  - Requirements: 3.1, 3.2, 3.3, 3.4
  - Properties: 10

- [x] 4.2 后端 `K2_SHEETS` 披露 sheet 名 `（国有企业）` → `（国企）`；
  新建 `backend/tests/four_table/test_k2_formula_presets.py` +
  sheet 名三处一致守卫（openpyxl 直读源 xlsx ↔ 后端 ↔ 前端常量）。
  - Requirements: 3.5, 4.1, 4.2, 5.4
  - Properties: 10, 11

- [x] 4.3 端到端实测（chrome-devtools + postgres 只读，项目 `0ec33ac9` / wp `919e3387`、
  `2aa00f57` / wp `d5f0d168`）：`render-config` 的 `account_codes` 不再是 `["1231"]`、
  `adjudication_prefill` 不再出现「坏账准备_*」、`tb_values` 不再等于 28,464,225.16；
  动态行增删改名落库并刷新后保持；实测数据复原。
  - Requirements: 6.1, 6.2, 6.3
  - Properties: 1, 5, 7

- [x] 4.4 收口：后端 four_table + K2 全量绿；前端 K2 相关全量绿；
  更新 `.kiro/specs/INDEX.md` 与 memory；把「K3~K13 沿用本范式」写入约定。
  - Requirements: 5.1, 5.2

## Notes

**实证基线（改动前）**

| 项 | 现状（错） | 目标 |
|---|---|---|
| `account_codes` | `["1231"]`（坏账准备） | `BS-014` 解析结果（`1901`） |
| `0ec33ac9` K2 `tb_values.other_current_audited` | 28,464,225.16 | 按 `1901` 口径（本库为 0） |
| `0ec33ac9` K2 `adjudication_prefill` | 坏账准备_应收账款 26,401,719.77 / 应收票据 1,162,288.03 / 其他应收款 900,217.36 | `[]`（宁缺勿造） |
| K2-1 行模型 | 硬编码 8 行，含 `预付款项`/`合同资产`/`押金保证金` | 动态行（可增删改名） |
| K2 公式预设 | `wp_name='销售费用审定表'`、`TB('6601',…)` | 其他流动资产、`TB('1901',…)` |
| 后端披露 sheet 名 | `附注披露信息（国有企业）` | `附注披露信息（国企）` |

**实测结论（2026-07-31）**

| 验证项 | 结果 |
|---|---|
| 真实 DB 直跑 `render()`（3 个项目 `0ec33ac9` / `2aa00f57` / `c8621493`） | `account_codes=['1901']`、`resolved_from=report_config`、公式 `TB('1901','期末余额')`、`provision=[]`、`extra={'1131':['1131']}`、`signed_codes=[['1901',1]]` |
| 旧口径 vs 新口径（同一份 `tb_balance` 叶子） | `0ec33ac9`：旧 `1231` 期末 **28,464,225.16** → 新口径 **0.00**；`2aa00f57`：旧 **-1,718,193.78** → 新 **0**；`c8621493`：0 → 0 |
| 预填「宁缺勿造」 | 三个项目均 **0 行**，坏账准备行 **0 条**（`1901` 全库为 0 = K2 真实口径本无数据） |
| 浏览器实测（wp `d5f0d168` 审定表K2-1） | 按钮齐备（新增项目行 / 从四表库带入未审数 / 从 K2-2 明细带入 / 带入调整）；`el-input-number` 计数 **0**（全量 `WpAmountInput`）；TB 核对区与回写按钮均显示科目 **1901** |
| 动态行增删改名 | 改名落库；`ElMessageBox.prompt` 含源模板 7 个示例；撞名（含空白差异「预缴 企业所得税」）被拒不建行；删除确认提示「将同时清除该行 2 项已录数据」，删除后 `K2-1-rows` 少一行且该行 `K2-1-{rowId}-*` 键被清空、其它行键不受影响 |
| 金额千分符 | 录 `1234567.5` → 显示 `1,234,567.50`；合计 `828,552.65 = 1,234,567.50 + (-406,014.85)` 覆盖全部动态行 |
| Vite transform | 19 个改动文件全部 200 |

**遗留（环境问题，非代码）**

- 活体 **HTTP** `render-config` 仍返回旧 `account_codes=['1231']`：占用 9980 的 uvicorn worker
  未随 `--reload` 重载（本机长期存在多进程占端口现象），且该 worker 在 WMI 中查不到命令行、
  无法定向重启。**同一个 `render()` 已用真实 DB 直跑验证通过**（上表第 1~3 行），
  下次后端重启后即生效；届时溯源面板 `.wp-four-table-source` 也会出现（当前 `tb_source_codes`
  未下发故面板按设计隐藏）。
- 实测数据已复原：wp `d5f0d168` 的 5 个 `K2-1-*` 键全部置空串
  （该 wp 实测前无任何 `K2-1-*` 记录；空串与缺键等价 —— `deserializeRows('')→[]`、`readNum→0`）。

**口径纠正（2026-07-31 用户裁决，已落地）**

首版把历史 8 行里的 `预付款项` / `合同资产` / `押金保证金` 判成「属于别的报表行」，
在 UI 打「口径存疑」红 tag。**用户明确：这三行是 K2 自己的二级子明细，不是别的循环的科目。**
→ 已撤回该判定：删掉 `K2_LEGACY_FOREIGN_WARNINGS`、共享件的 `LegacyFixedRow.foreignWarning`
与 `foreignRowWarning()`（死代码不留）、UI 的红 tag 与 `.foreign-row` 样式，
requirements R2.5 改为「8 行一视同仁按二级子明细迁移，不做归属判定」。
守卫改为**正向锁死**：`K2_LEGACY_ROWS` 每项只许有 `key`/`label` 两字段，
且 `k2AdjudicationRows.ts` 源码不得再出现 `foreignWarning` / `口径存疑`。

**刷新取数增强（R2.9，同批落地）**

`seedRowsFromPrefill` 增 `createdRowIds`/`touchedRowIds` + `findRowForPrefill`
（**科目码优先于行名** —— 改名后不重复插行，并回填 `accountCode`）；
`seedFromPrefill({overwrite})` + `previewSeedFromPrefill()`：
四表库重新入库后点「从四表库带入/刷新未审数」→ 新子科目自动插行、
已有四表行金额有变化时弹确认（可选「仅补空值」），**手工/历史行的录入永不被覆盖**。

**范围外**

- `report_config` 的 `BS-014 listed_standalone` 引用 `TB('1131')`（应收股利已被 `BS-009`
  引用）与 `BS-017` 同名空公式行 —— 平台级 data-hygiene，另立。
- K2 披露列结构 / 附注模板 —— 归档 spec 已完成。
- K3~K13 同类问题 —— 沿用本范式另立。
