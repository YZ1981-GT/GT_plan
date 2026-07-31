# Implementation Plan: F1 四表库取数链路根治 + 披露/附注结构收尾

## Overview

主线 A（取数，Wave 1→2→3）与主线 B（披露，Wave 4）互不依赖，可并行。
Wave 5 汇总勾稽面板（弱依赖 A 的 `impairment_prefill`，缺则规则 `skipped`），
Wave 6 公式预设 + 端到端实测 + 收口。

不造轮子：`app/services/four_table/`（`report_line_accounts` / `leaf_aggregation`）
由 K1 spec Wave 1 建成、D1 已委托，F1 是第三个消费者 —— 本 spec **不改共享件**，
只新增 F1 侧的纯函数（性质归类 / 区间解析）。

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

- [x] 1.1 `_f1_prepayment.py` 新增纯函数区：`classify_f1_nature(account_name) -> rowKey`
  （判定顺序：工程 → 设备/长期资产/购置 → 服务/待摊/费用/保险/租金 → 货款/材料/商品/采购
  → 其他；工程优先于设备，因实证 `1123.02.03 长期资产款_工程款` 两词皆含）、
  `build_nature_prefill(leaves, prefixes)`、
  `build_impairment_prefill(leaves, prefixes, name_filter)`（无命中返 `None`）。
  三者均不碰 DB，供 Wave 3 单测。**另新增 `sql_prefixes_for_specs` /
  `filter_by_code_specs`** 支持 `BS-010` 的 `1401~1499` 区间口径。
  - Requirements: 3.1, 3.2, 3.3, 1.5, 4.1
  - Properties: 2, 3

- [x] 1.2 `_f1_prepayment.py` 删除 `_is_leaf` 与硬编码 `1123` 前缀，改为
  `four_table.resolve_report_line_accounts(F1_REPORT_LINE_SPEC)` +
  `to_leaf_rows/select_leaves/aggregate_leaves`；**跨循环锚点也改走报表映射**
  （存货 `BS-010` 区间 / 应付账款 `BS-045`）；备抵侧聚合取 `abs()`；
  `_fetch_f1_1123_audited` 改用解析出的 `gross_standard`。
  - Requirements: 1.1, 1.2, 1.3, 1.6, 2.1, 2.2, 2.4, 2.5
  - Properties: 1, 3, 4

- [x] 1.3 `render()` 输出新增 `adjudication_prefill.nature`（空则整键省略）与
  `impairment_prefill`；`project_context.tb_source_codes` 由 `list[str]` 升级为
  `ReportLineAccounts.as_dict()` 结构；**另新增 `prepaid_tb_leaf_amount`**
  （科目余额表叶子合计，与 trial_balance 口径并列下发供溯源面板显示差异）
  与 `tb_cross_cycle_codes`。
  - Requirements: 1.7, 3.1, 3.7, 4.1, 4.3
  - Properties: 4

- [x] 1.4 `_f1_prepayment.py` 顶部 docstring 补「科目映射链路三层」实证说明（原始码/标准码/
  报表映射 + `BS-008` 四准则同形且不减备抵 + 实证 9 项目无 `1231-04` 映射 → 必叠名称过滤
  + `1123` 叶子科目名 → 性质桶对照表），作为后续 F2~F4 推广的口径依据。
  - Requirements: 1.3, 1.4

- [x] 2.1 新建 `composables/f1FourTableSource.ts`：`normalizeF1TbSource(raw)`
  （兼容旧 `string[]` 与新 dict，缺字段给安全默认）+ `describeResolvedFrom(v)`
  + `normalizeF1CrossCycleSources` + `tbAmountDivergence`（两口径差异检出）。
  - Requirements: 1.7, 4.3

- [x] 2.2 新建 `f1/F1FourTableSourcePanel.vue`：紧凑单行 bar（报表行 + 来源 tag +
  两口径差异 tag）+ 折叠明细（公式原文 / 标准码 / 原始码 / 是否叠名称过滤 /
  跨循环锚点 / 两口径对比），挂在 F1-1 审定表与两个披露 Tab 顶部 —— 消费
  `tb_source_codes`，杜绝 dead output。
  - Requirements: 1.7, 4.3

- [x] 2.3 `useF1Adjudication.ts` 新增 `naturePrefill` 选项与 `pullNatureFromTB()`；
  `buildRow` 的 seed 链改「手工 > F1-2 明细 > 四表库预填」（新增 `isFromFourTable` 标记）；
  `F1TabAdjudication.vue` 工具条加「从四表库带入未审数」（`:loading` + `:disabled="isReadonly"`，
  无数据时 `ElMessage.info`）；`GtF1Prepayment.vue` 补 `f1NaturePrefill` /
  `f1ImpairmentPrefill` / `f1TbSourceCodes` / `f1TbLeafAmount` / `f1TbCrossCycleCodes`
  computed 并透传；顺手把 sheet 分发的「国企」判定扩到「国有」。
  - Requirements: 3.4, 3.5, 3.6, 3.7
  - Properties: 5

- [x] 2.4 `useF1DisclosureListed.ts` 的 `impairmentProvision` / `impairmentPrior` 加
  `impairmentPrefill` 只读回退（有持久化值时不套用）；`useF1DisclosureSoe.ts` 暴露
  `fourTableImpairment`（只读，供 Wave 5 勾稽右值）。
  - Requirements: 4.1, 4.2
  - Properties: 5

- [x] 3.1 新建 `backend/tests/test_f1_four_table_extraction.py`（28 例）：`classify_f1_nature`
  参数化（含 6 个实证真实科目名 + 工程优先于设备的反例）、`build_nature_prefill` 五桶和
  == 叶子合计（hypothesis PBT，`max_examples=5`）、点号边界（`1123.1` vs `1123.10`、
  `2202` vs `22020`）、备抵名称过滤断言**不含** `1231.02` 金额 + 反向自检、
  区间解析（`1401~1499` 实证 117,808,961.20）、空数据返回 `None`/`{}`。
  - Requirements: 1.4, 1.5, 2.2, 3.1, 3.2, 3.7
  - Properties: 1, 2, 3

- [x] 3.2 render characterization（并入 3.1 文件）：依赖全空时
  `project_context` 既有字段与改动前逐值相等；`tb_source_codes` 新形态逐键钉死；
  无 `1123` 数据时不出现 `adjudication_prefill` / `impairment_prefill` 键。
  - Requirements: 1.6, 2.5, 3.7
  - Properties: 4

- [x] 4.1 `f1DisclosureSyncPayload.ts` 导出列字面常量（`F1_AGING_LABEL_COL='账  龄'` /
  `F1_LISTED_AGING_GROUPS={end:'期末数',prior:'上年年末数'}` / `F1_SOE_AGING_GROUPS` /
  `F1_LISTED_AMOUNT_LABEL='金  额'` / `F1_SOE_AMOUNT_LABEL='金 额'` / 两个 pct 常量），
  `F1_LISTED_COLUMNS` / `F1_SOE_COLUMNS` 改引常量；**数据 key 逐字不变**。
  - Requirements: 6.1, 6.2, 6.3
  - Properties: 6

- [x] 4.2 `fix_note_prepayment_structure.py`：`_aging_patch()` 参数化 `amount_label` /
  `label_col`，listed 改 `("期末数","上年年末数","金  额","比例%")`、
  soe 改 `("期末数","期初数","金 额","比例（%）")`；`ALIGNED_BY` 改集合判定；
  跑 `--dry-run` 复核后落盘，`--check` 归零。
  - Requirements: 6.1, 6.2, 11.1
  - Properties: 6

- [x] 4.3 `useF1DisclosureListed.ts` 新增 `top5Mode`（持久化 `F1-note-listed-top5-mode`，
  默认 `'separate'`）+ `setTop5Mode()`；`getSyncSnapshot()` 带出；
  `buildF1ListedSubTableData` 按 mode 分支；`buildF1SyncPayload` 只发**本次推送表**的
  列元数据（避免附注留无数据的列元数据残片）。
  - Requirements: 7.1, 7.2, 7.3, 7.4
  - Properties: 7

- [x] 4.4 `F1TabDisclosureListed.vue`：③区块加 `el-radio-group` 并按 mode `v-if` 切换展示；
  4 处 `el-input-number` → `WpAmountInput`；列头 `label` 改引 4.1 的常量；
  `fmtAmount` 委托 `displayPrefs`。
  - Requirements: 7.1, 9.1, 9.2, 6.4
  - Properties: 7, 12

- [x] 4.5 `F1TabDisclosureSoe.vue`：4 处 `el-input-number` → `WpAmountInput`；
  列头 `label` 改引常量（逐段备抵列头取源模板 `D9/G9` 字面「坏账准备」）；
  `fmtAmount` 委托 `displayPrefs`。
  - Requirements: 9.1, 9.2, 6.4
  - Properties: 12

- [x] 4.6 守卫四件：① 扩展 `backend/tests/services/test_note_prepayment_structure.py`
  加 **openpyxl 直读源 xlsx** 三向比对（`A8`/`B8`/`D8`/`B9`/`B10` 逐字含空格 ↔ 模板 columns
  ↔ `f1DisclosureSyncPayload.ts` 源码正则）+ 反向自检；② 扩展
  `f1DisclosureColumns.spec.ts` / `f1NoteSubtableContract.spec.ts`（改引常量 + key 不变 +
  两版空格数必须不同）；③ 新增 `f1Top5Mode.spec.ts`(11) 与
  `f1AmountInputMigration.spec.ts`(16，读 SFC 源码 + `stripComments()` 自检) 与
  `f1FourTableSource.spec.ts`(16)；④ 扩展 `F1DisclosureMount.spec.ts`（两面板真渲染 +
  mode 切换 + F1-1 SFC 编译冒烟）。
  - Requirements: 6.1, 6.2, 6.3, 6.4, 7.2, 7.3, 9.1, 9.2, 11.2, 11.3
  - Properties: 6, 7, 12

- [x] 5.1 新建 `composables/f1DisclosureConsistency.ts`：纯函数
  `buildF1ConsistencyChecks(variant, input) → F1CheckResult[]`，规则集逐条对齐
  F7-1~F7-14（含 F7-5 账龄衔接与 F7-10 LLM 审核的显式 `skipped`；listed 跳过 F7-13；
  国企附加「逐段减值准备合计 = 四表库 `1231-04` 期末」）；相等类容差 0.01 元、
  比例类 0.01 个百分点；F7-11 的「1 年以上」段集按账龄枚举自适配。
  - Requirements: 8.2, 8.3, 8.4, 4.2
  - Properties: 8

- [x] 5.2 新建 `f1/F1DisclosureConsistencyPanel.vue`（紧凑单行 bar + 折叠明细表 +
  规则 tooltip + `GtIndexChip` 追溯），两个披露 Tab 挂载并传入报表数 / ①②③表数据 /
  账龄段 / 四表库减值准备。
  - Requirements: 8.1
  - Properties: 8

- [x] 5.3 新增 `composables/__tests__/f1DisclosureConsistency.spec.ts`(20)：
  两变体 `id` 集合完备性（与 `note_check_preset_formulas.json` 该节交叉比对，
  **按 `section_title` 收敛** —— 实证该文件 `note_section='五、7'` 下混入 `F65-*`/`F82-*`
  陈旧条目）、缺数据 → `skipped` 不 `error`、容差边界、账龄段 3/5/自定义自适配。
  - Requirements: 8.1, 8.2, 8.3, 8.4, 10.1, 10.5
  - Properties: 8, 9

- [x] 6.1 新建幂等脚本 `backend/scripts/fix/fix_f1_prefill_presets.py`（`--dry-run`/`--check`）：
  F1-1 块补 6 条（`TB('1231-04','期初/期末余额')` / `TB('1123','本期借方/本期贷方')` /
  `WP('F1','明细表F1-2',…)` / `WP('F1','长期挂款检查表F1-5',…)`）；新增 F1-2 块
  （`TB` + `AUX('1123','客户',…)`，**不含 `WP()`**）与 F1-4 块
  （`TB_SUM('1401~1499','期末余额'/'本期借方')` / `TB('2202','期末余额')`）。
  - Requirements: 5.1, 5.2, 5.3, 5.4

- [x] 6.2 新建 `backend/tests/four_table/test_f1_formula_presets.py`(20)：F1 条目归
  `workpaper:F1`、`formula_type == 'auto_calc'`、F1-2 无 `WP(`、`cell_ref` 在
  `workpaper:F1` 内唯一、反向钉子（不得出现 `TB('1231',` / `TB('1401',`）。
  - Requirements: 5.5
  - Properties: 11

- [x] 6.3 端到端实测（chrome-devtools + postgres 只读，项目 `2aa00f57` / wp `6de6c91d`）：
  ① F1-1 溯源面板显示 `BS-008` / 原值「报表映射」/ 备抵「兜底科目」/「备抵按『预付』过滤」/
  **两口径差异 1,301,918.43**；② 点「从四表库带入未审数」→ 货款 33,666.58 / 2,430.64 +
  服务费 1,297,540.83 / 1,299,487.79，合计 = 1,301,918.43 = 科目余额表叶子合计，
  性质合计 == 账龄合计；③ 国企披露 Tab 三级表头正确（`账  龄` / `期末数`·`期初数` /
  `账面余额`·`坏账准备` / `金 额`·`比例（%）`）、`el-input-number` 计数 **0**、
  `WpAmountInput` 17 处、录 1234567.5 → `1,234,567.50`；④ 勾稽面板 17 条（通过 12 /
  异常 1 = F7-1 报表口径差异 / 跳过 4，全部有中文说明）；⑤ 自动同步 → §八、7
  `last_sync_at` 由 NULL 前移、3 子表、`_sub_table_columns` 列头字面与源 xlsx 逐字一致、
  合计 = 小计 − 减值准备 = 67,350.93；⑥ 上市 Tab 在国企项目正确显示「当前项目不适用」
  且零写入。实测数据（11 个 checklist 键）已全部复原。
  - Requirements: 11.5, 11.6
  - Properties: 1, 5, 6, 7, 12

- [x] 6.4 收口：`fix_note_prepayment_structure.py --check` +
  `fix_f1_prefill_presets.py --check` 零欠账；后端 F1 + four_table + note_prepayment
  全量绿（181）；前端 F1 相关 19 文件 185 例绿；12 个改动文件 Vite transform 200；
  `governance-checks.yml` 新增 job `note-f1-four-table` / `note-f1-four-table-frontend`；
  更新 `.kiro/specs/INDEX.md` 与 `#memory`。
  - Requirements: 11.1, 11.2, 11.3, 11.4

## Notes

**实证结果（改动前 → 改动后）**

| 项 | 改动前 | 改动后 | 来源 |
|----|--------|--------|------|
| F1-1 按性质分类未审数 | 全部落「其他」（F1-2 aux 自动归集的占位性质） | 货款 2,430.64 / 服务费 1,299,487.79（`1123` 叶子按名归类） | `tb_balance` 子科目名 |
| F1-4 存货余额 | **恒 0**（前缀 `1401` = 材料采购） | 117,808,961.20（`BS-010` = `SUM_TB('1401~1499')`） | `report_config` + `tb_balance` |
| 减值准备 | 100% 手工 | 四表库有则预填（实证 9 项目无 `1231-04` → `null`，正确） | `account_chart 1231-04` |
| `tb_source_codes` | `list[str]`，前端 **0 消费** | 结构化 dict + 溯源面板（含两口径差异检出） | grep |
| listed 按账龄表父组名 | `期末余额` / `上年年末余额` | `期末数` / `上年年末数` | 源 xlsx `B8`/`D8` |
| 标签列 / 金额列字面 | `账龄` / `金额` | `账  龄` / `金  额`(listed) `金 额`(soe) | 源 xlsx `A8`/`B9`/`B10` |
| 上市③前五名 | 汇总句与明细表**同时**推送 | 二选一 + `_removed_table_keys` | 源 xlsx `A23`/`A24`/`A26` |
| 披露 Tab 金额控件 | 8 处 `el-input-number`（千分符从未生效） | `WpAmountInput`，`el-input-number` 归零 | 平台双证 |
| 勾稽面板 | 无 | 17 条规则（F7-1~F7-14 + F1-TB4） | `note_check_preset_formulas.json` |
| F1 公式预设 | 1 块 5 条 | 3 块 17 条 | 对比 F2 18 条 / N1 含 `WP()` |

**本会话新发现的既有缺陷（已修 / 已记录）**

1. **F1-4「存货余额」恒 0** —— 前缀 `1401` 是「材料采购」不是存货合计（已修，见上表）。
2. **`trial_balance` 双计**：项目 `2aa00f57` 的 `1123` 试算数 2,603,836.86 =
   科目余额表叶子合计 1,301,918.43 的 **2 倍**（`recalc` 把 `dataset_id IS NULL` 的历史行
   一并计入）。属**平台级 data-hygiene，不在本 spec 修**；已让溯源面板并列展示两口径
   并打「两口径差异」红 tag，勾稽 F7-1 也会报异常 —— 从「静默采信一个错数」变成「显式暴露」。
3. **`note_check_preset_formulas.json` 的 `note_section` 陈旧**：`五、7` 下混入
   `F65-*`（其他收益，应为 五、65）与 `F82-*`（筹资活动…，应为 五、82）。平台级，另立；
   本 spec 的守卫按 `section_title` 收敛规避。
4. **F1 有 11 处本地 `fmtAmount`**（各写一份 `toLocaleString`，忽略用户单位/小数位偏好）。
   本 spec 收敛了范围内的 3 个 Tab，其余 8 个登记在
   `f1AmountInputMigration.spec.ts` 的 `FMT_AMOUNT_PENDING`（每项带理由，不许静默增长）。
5. **`pullNatureFromTB` 必须给「四表无数据且无手工值」的性质桶显式写 0** ——
   否则「其他」继续显示 F1-2 明细聚合的全额，合计立刻翻倍（实测 2,603,836.86 = 真值 2 倍）。

**遗留（不阻塞）**

- **上市侧无活体**：8 个在册项目 `applicable_standard_v2.entity_type` 全为 `soe`
  → 上市披露 Tab 被 `applicable_standards` 正确门控为「不适用」（已实测，零写入）。
  上市侧行为由 11 例 `f1Top5Mode` + mount spec 覆盖。
- `formula_management` 的 `test_materialized_inventory_json_consistent` 红
  （`inventory.json` 物化产物陈旧：文件 232 页 / 3939 条 vs 运行时 255 / 3999）——
  **改动前就红**（差额 23 页远大于本 spec 新增的 12 条，且页数不变），
  重新物化需 `附注模版/*宽表公式预设.md`（本仓库不存在）→ 留待平台级处理。
- `formula_management` 其余 28 个失败全是 sqlite 缺 `pg_advisory_xact_lock` /
  缺表的环境性预存在失败。
- commit（按层分批，见 `#memory`）。

**范围外**：改 `BS-008` 公式加备抵项 / `report_row_code` 全库陈旧 / `trial_balance`
recalc 双计 / F2~F4 同类修复 / 按账龄表改回源 xlsx 国企 7 列三级表头
（附注侧行形态由 F7-6/F7-7/F7-13 预设裁决，底稿侧已按源模板三级渲染）。
