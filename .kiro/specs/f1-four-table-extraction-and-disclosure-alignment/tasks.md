# Implementation Plan: F1 四表库取数链路根治 + 披露/附注结构收尾

## Overview

主线 A（取数，Wave 1→2→3）与主线 B（披露，Wave 4）互不依赖，可并行。
Wave 5 汇总勾稽面板（弱依赖 A 的 `impairment_prefill`，缺则规则 `skipped`），
Wave 6 公式预设 + 端到端实测 + 收口。

不造轮子：`app/services/four_table/`（`report_line_accounts` / `leaf_aggregation`）
由 K1 spec Wave 1 建成、D1 已委托，F1 是第三个消费者 —— 本 spec **不改共享件**，
只新增 F1 侧的纯函数（性质归类）。

## Task Dependency Graph

分 6 波。Wave 1 纯函数 + render 接入（后端，无 UI 依赖）；Wave 2 前端消费（溯源面板 /
带入按钮 / 预填回退）；Wave 3 后端守卫（characterization + 纯函数单测）；
Wave 4 披露结构（列字面 / 二选一 / 金额控件，独立于 A）；Wave 5 勾稽引擎与面板；
Wave 6 公式预设 + 实测 + 收口。

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "后端取数：共享件接入 + 性质/减值预填",
      "tasks": ["1.1", "1.2", "1.3", "1.4"],
      "depends_on": []
    },
    {
      "wave": 2,
      "name": "前端消费：溯源面板 / 带入按钮 / 预填回退",
      "tasks": ["2.1", "2.2", "2.3", "2.4"],
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "后端守卫：纯函数单测 + characterization",
      "tasks": ["3.1", "3.2"],
      "depends_on": [1]
    },
    {
      "wave": 4,
      "name": "披露结构：列字面三向对齐 / 上市③二选一 / 金额控件",
      "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6"],
      "depends_on": []
    },
    {
      "wave": 5,
      "name": "勾稽引擎 + 面板",
      "tasks": ["5.1", "5.2", "5.3"],
      "depends_on": [1, 4]
    },
    {
      "wave": 6,
      "name": "公式管理预设 + 端到端实测 + 收口",
      "tasks": ["6.1", "6.2", "6.3", "6.4"],
      "depends_on": [2, 3, 5]
    }
  ]
}
```

## Tasks

- [ ] 1.1 `_f1_prepayment.py` 新增纯函数区：`classify_f1_nature(account_name) -> rowKey`
  （判定顺序：工程 → 设备/长期资产/购置 → 服务/待摊/费用/保险/租金 → 货款/材料/商品/采购
  → 其他；工程优先于设备，因实证 `1123.02.03 长期资产款_工程款` 两词皆含）、
  `build_nature_prefill(leaves, prefixes)`、
  `build_impairment_prefill(leaves, prefixes, name_filter)`（无命中返 `None`）。
  三者均不碰 DB，供 Wave 3 单测。
  - Requirements: 3.1, 3.2, 3.3, 1.5, 4.1
  - Properties: 2, 3

- [ ] 1.2 `_f1_prepayment.py` 删除 `_is_leaf` 与硬编码 `1123` 前缀，改为
  `four_table.resolve_report_line_accounts(F1_REPORT_LINE_SPEC)` +
  `to_leaf_rows/select_leaves/aggregate_leaves`；`_F1_CROSS_CYCLE_PREFIXES` 只留
  `("1401","2202")` 且同样走叶子口径；备抵侧聚合取 `abs()`；`_fetch_f1_1123_audited`
  改用解析出的 `gross_standard`。
  - Requirements: 1.1, 1.2, 1.3, 1.6, 2.1, 2.2, 2.4, 2.5
  - Properties: 1, 3, 4

- [ ] 1.3 `render()` 输出新增 `adjudication_prefill.nature`（空则整键省略）与
  `impairment_prefill`；`project_context.tb_source_codes` 由 `list[str]` 升级为
  `ReportLineAccounts.as_dict()` 结构（已确认前端 0 消费，无破坏性）。
  - Requirements: 1.7, 3.1, 3.7, 4.1, 4.3
  - Properties: 4

- [ ] 1.4 `_f1_prepayment.py` 顶部 docstring 补「科目映射链路三层」实证说明（原始码/标准码/
  报表映射 + `BS-008` 四准则同形且不减备抵 + 实证 9 项目无 `1231-04` 映射 → 必叠名称过滤），
  作为后续 F2~F4 推广的口径依据。
  - Requirements: 1.3, 1.4

- [ ] 2.1 新建 `composables/f1FourTableSource.ts`：`normalizeF1TbSource(raw)`
  （兼容旧 `string[]` 与新 dict，缺字段给安全默认）+ `describeResolvedFrom(v)`
  （`report_config`→「报表映射」绿 / `fallback`→「兜底科目」橙）。
  - Requirements: 1.7, 4.3

- [ ] 2.2 新建 `f1/F1FourTableSourcePanel.vue`：紧凑单行 bar（报表行 + 来源 tag）+
  折叠明细（公式原文 / 标准码 / 原始码 / 是否叠名称过滤），挂在 F1-1 审定表顶部与
  两个披露 Tab 顶部 —— 消费 `tb_source_codes`，杜绝 dead output。
  - Requirements: 1.7, 4.3

- [ ] 2.3 `useF1Adjudication.ts` 新增 `naturePrefill` 选项与 `pullNatureFromTB()`；
  `buildRow` 的 seed 链改「手工 > F1-2 明细 > 四表库预填」；
  `F1TabAdjudication.vue` 工具条加「从四表库带入未审数」（`:loading` + `:disabled="isReadonly"`，
  无数据时 `ElMessage.info`）；`GtF1Prepayment.vue` 补 `f1NaturePrefill` / `f1ImpairmentPrefill`
  / `f1TbSource` computed 并 provide + 透传。
  - Requirements: 3.4, 3.5, 3.6, 3.7
  - Properties: 5

- [ ] 2.4 `useF1DisclosureListed.ts` 的 `impairmentProvision` / `impairmentPrior` 加
  `impairmentPrefill` 只读回退（有持久化值时不套用）；`useF1DisclosureSoe.ts` 暴露
  `fourTableImpairment`（只读，供 Wave 5 勾稽右值）。新增
  `composables/__tests__/useF1AdjudicationPrefill.spec.ts`（手工优先 / 幂等 / 不清零）。
  - Requirements: 4.1, 4.2
  - Properties: 5

- [ ] 3.1 新建 `backend/tests/test_f1_four_table_extraction.py`：`classify_f1_nature`
  参数化（含 6 个实证真实科目名 + 工程优先于设备的反例）、`build_nature_prefill` 五桶和
  == 叶子合计（hypothesis PBT，`max_examples=5`）、点号边界（`1123.1` vs `1123.10`）、
  备抵名称过滤断言**不含** `1231.02` 金额、空数据返回 `None`/`{}`。
  - Requirements: 1.4, 1.5, 2.2, 3.1, 3.2, 3.7
  - Properties: 1, 2, 3

- [ ] 3.2 新建 `backend/tests/test_f1_render_characterization.py`：三种依赖缺失下
  `project_context` 既有字段与改动前逐值相等；`tb_source_codes` 新形态逐键钉死；
  无 `1123` 数据时不出现 `adjudication_prefill` 键。
  - Requirements: 1.6, 2.5, 3.7
  - Properties: 4

- [ ] 4.1 `f1DisclosureSyncPayload.ts` 导出列字面常量（`F1_AGING_LABEL_COL='账  龄'` /
  `F1_LISTED_AGING_GROUPS={end:'期末数',prior:'上年年末数'}` / `F1_SOE_AGING_GROUPS` /
  `F1_LISTED_AMOUNT_LABEL='金  额'` / `F1_SOE_AMOUNT_LABEL='金 额'` / 两个 pct 常量），
  `F1_LISTED_COLUMNS` / `F1_SOE_COLUMNS` 改引常量；**数据 key 逐字不变**。
  - Requirements: 6.1, 6.2, 6.3
  - Properties: 6

- [ ] 4.2 `fix_note_prepayment_structure.py`：`_aging_patch()` 参数化 `amount_label` /
  `label_col`，listed 改 `("期末数","上年年末数","金  额","比例%")`、
  soe 改 `("期末数","期初数","金 额","比例（%）")`；`ALIGNED_BY` 改集合判定（追加本 spec 名）；
  跑 `--dry-run` 复核后落盘，`--check` 归零。
  - Requirements: 6.1, 6.2, 11.1
  - Properties: 6

- [ ] 4.3 `useF1DisclosureListed.ts` 新增 `top5Mode`（持久化 `F1-note-listed-top5-mode`，
  默认 `'separate'`）+ `setTop5Mode()`；`getSyncSnapshot()` 带出；
  `buildF1ListedSubTableData` 按 mode 分支（`summary` → 不推③表 + `_removed_table_keys`
  含③表名 + 推 `listed-top5-summary`；`separate` → 推③表 + 不推汇总句）。
  - Requirements: 7.1, 7.2, 7.3, 7.4
  - Properties: 7

- [ ] 4.4 `F1TabDisclosureListed.vue`：③区块加 `el-radio-group`（汇总披露格式 / 分别披露格式）
  并按 mode `v-if` 切换展示；4 处 `el-input-number` → `WpAmountInput`；
  列头 `label` 改引 4.1 的常量。
  - Requirements: 7.1, 9.1, 9.2, 6.4
  - Properties: 7, 12

- [ ] 4.5 `F1TabDisclosureSoe.vue`：4 处 `el-input-number` → `WpAmountInput`；
  列头 `label` 改引常量（含逐段坏账准备列头取源模板 `坏账准备`）。
  - Requirements: 9.1, 9.2, 6.4
  - Properties: 12

- [ ] 4.6 守卫三件：① 扩展 `backend/tests/services/test_note_prepayment_structure.py`
  加 **openpyxl 直读源 xlsx** 三向比对（`A8`/`B8`/`D8`/`B9`/`B10` 逐字含空格 ↔ 模板 columns
  ↔ `f1DisclosureSyncPayload.ts` 源码正则）+ 反向自检；② 扩展
  `f1DisclosureColumns.spec.ts` / `f1NoteSubtableContract.spec.ts`（新字面 + key 不变 +
  Tab 源码禁出现 `label="期末余额"` 字面）；③ 新增
  `composables/__tests__/f1Top5Mode.spec.ts`（Property 7）与
  `f1AmountInputMigration.spec.ts`（读 SFC 源码，`stripComments()` + 自检，
  `el-input-number` 计数 0 且比例/账龄字段未套 `WpAmountInput`）。
  - Requirements: 6.1, 6.2, 6.3, 6.4, 7.2, 7.3, 9.1, 9.2, 11.2, 11.3
  - Properties: 6, 7, 12

- [ ] 5.1 新建 `composables/f1DisclosureConsistency.ts`：纯函数
  `buildF1ConsistencyChecks(variant, input) → F1CheckResult[]`，规则集逐条对齐
  F7-1~F7-14（listed 跳过 F7-13 并显式标 `skipped`；国企附加「逐段减值准备合计 =
  四表库 `1231-04` 期末」，`fourTableImpairment == null` 时 `skipped`）；
  相等类容差 0.01 元、比例类 0.01 个百分点；F7-11 的「1 年以上各段」按传入账龄段集合
  自动适配（3年段/5年段/自定义）。
  - Requirements: 8.2, 8.3, 8.4, 4.2
  - Properties: 8

- [ ] 5.2 新建 `f1/F1DisclosureConsistencyPanel.vue`（紧凑单行 bar + 折叠明细表 +
  规则 tooltip + `GtIndexChip` 追溯），两个披露 Tab 挂载并传入
  报表数（`project_context.prepaid_tb_amount`）/ ①②③表数据 / 账龄段 / 四表库减值准备。
  - Requirements: 8.1
  - Properties: 8

- [ ] 5.3 新增 `composables/__tests__/f1DisclosureConsistency.spec.ts`：
  两变体 `id` 集合完备性（与 `note_check_preset_formulas.json` 该节可判定规则集比对，
  含反向自检防空转）、缺数据 → `skipped` 不 `error`、容差边界、
  账龄段 3/5/自定义下 F7-11 段集自适配（PBT）。
  - Requirements: 8.1, 8.2, 8.3, 8.4, 10.1, 10.5
  - Properties: 8, 9

- [ ] 6.1 `prefill_formula_mapping.json`：F1-1 块补 6 条
  （`TB('1231-04','期初余额')` / `TB('1231-04','期末余额')` / `TB('1123','本期借方')` /
  `TB('1123','本期贷方')` / `WP('F1','明细表F1-2','期末审定余额合计')` /
  `WP('F1','长期挂款检查表F1-5','审定余额合计')`）；新增 F1-2 块
  （`TB('1123','期初余额'/'期末余额')` + `AUX('1123','客户','XX单位','期末余额')`，
  **不得含 `WP(`**）与 F1-4 块（`TB('1401','期末余额')` / `TB('2202','期末余额')` /
  `TB('1401','本期借方')`）。
  - Requirements: 5.1, 5.2, 5.3, 5.4

- [ ] 6.2 新建 `backend/tests/test_f1_prefill_presets.py`：F1 条目归 `workpaper:F1`、
  `formula_type` 属受支持集合、F1-2 块无 `WP(`、6 条新增条目逐条在册；
  跑既有 `backend/tests/formula_management/` 全量证明零回归。
  - Requirements: 5.5
  - Properties: 11

- [ ] 6.3 端到端实测（chrome-devtools + postgres 只读）：
  ① 项目 `2aa00f57`（国企，1123 期末 1,301,918.43 = `1123.01` 2,430.64 + `1123.03` 1,299,487.79）
  打开 F1-1 → 溯源面板显示 `BS-008` / `TB('1123','期末余额')` / 兜底备抵 tag，
  「按性质分类」预填 货款 2,430.64 + 服务费 1,299,487.79（或经 F1-2 明细聚合优先）；
  点「从四表库带入未审数」→ 持久化且再点一次结果不变；
  ② 国企披露 Tab 录入 → 5s 内自动同步 → §八、7 `last_sync_at` 前移、3 子表、
  `_sub_table_columns` 的 group 为 `期末数`/`期初数`、标签列 `账  龄`；勾稽 bar 有结论；
  ③ 上市 Tab 切「汇总披露格式」→ 载荷不含③表且 `_removed_table_keys` 含③表名（DB 实证
  §五、7 子表数变化）；切回复原；
  ④ 金额格录 1234567.5 → 显示 `1,234,567.50`；`el-input-number` 计数 0。
  实测数据全部复原。
  - Requirements: 11.5, 11.6
  - Properties: 1, 5, 6, 7, 12

- [ ] 6.4 收口：`fix_note_prepayment_structure.py --check` 零欠账；后端 F1 + four_table +
  note_prepayment 全量绿；前端 F1 相关全量绿；`governance-checks.yml` 新增 job
  `note-f1-four-table`（跑 `--check` + 后端 F1 守卫）；更新 `.kiro/specs/INDEX.md`
  与 `#dev-history`；把「F2~F4 沿用本范式」与「科目映射链路三层」写入 `#conventions`。
  - Requirements: 11.1, 11.2, 11.3, 11.4

## Notes

**实证基线（改动前，供回归比对）**

| 项 | 现状 | 目标 | 来源 |
|----|------|------|------|
| F1-1 按性质分类未审数（无 F1-2 明细时） | 全 0（无 prefill） | 从 `1123` 叶子按名归类 | `tb_balance` 子科目名 |
| 减值准备（两版披露） | 100% 手工 | 四表库有则预填（实证 9 项目无 `1231-04` → 空，正确） | `account_chart 1231-04` + `account_mapping` |
| `tb_source_codes` | `list[str]`，前端 0 消费 | 结构化 dict + 溯源面板 | grep 命中 0 |
| listed 按账龄表父组名 | `期末余额` / `上年年末余额` | `期末数` / `上年年末数` | 源 xlsx `B8`/`D8` |
| 标签列 / 金额列字面 | `账龄` / `金额` | `账  龄` / `金  额`(listed) `金 额`(soe) | 源 xlsx `A8`/`B9`/`B10` |
| 上市③前五名 | 汇总句与明细表同时推送 | 二选一 + `_removed_table_keys` | 源 xlsx `A23`/`A24`/`A26` |
| 披露 Tab 金额控件 | 8 处 `el-input-number`（千分符从未生效） | `WpAmountInput` | 平台双证 |
| 勾稽面板 | 无（F7-1~F7-14 未落地） | 引擎 + 面板 | `note_check_preset_formulas.json` |
| F1 公式预设 | 1 块 5 条 | 3 块 ~14 条 | 对比 F2 18 条 / N1 含 `WP()` |

**踩坑预警**

- `_aligned_by` 现为单值断言 → 改 `ALIGNED_BY` 前先把 `--check` 改成集合判定，否则 CI 必红。
- `read_file` 对并发会话在改的文件返回陈旧版本 → 判落盘真相用
  `python -c "open(p,encoding='utf-8').read()"`。
- PowerShell `>` 重定向腌坏 UTF-8 中文 → 诊断脚本用 `--out` 自己写盘；
  临时文件用**每次不同的文件名**（`read_file` 按路径缓存）。
- `note_template_*.json` 与 `prefill_formula_mapping.json` 是多 spec 共改真源 →
  只走幂等脚本，测试红了先重跑脚本再判断。
- 源模板空格字面（`账  龄` 双空格 / listed `金  额` 双空格 / soe `金 额` 单空格）
  **必须逐字保留**，守卫用 `repr()` 断言防编辑器 trim。
- 上市②/国企②表清空到无行时**仍要推**（模板正式表 + 底稿有录入区块），
  与 K7 政府补助那类「有录入区块的条件表」语义不同 —— F1 两表非条件表，不进
  `_removed_table_keys`。
- 读 SFC 源码的守卫必须先 `stripComments()` 且加反向自检（否则注释里的反例被数成真实调用）。

**范围外**：改 `BS-008` 公式加备抵项 / `report_row_code` 全库陈旧 / F2~F4 同类修复 /
按账龄表改回源 xlsx 国企 7 列三级表头（详见 design §Overview 表）。
