# Implementation Plan: K1 四表库取数口径根治 + 披露/附注结构对齐

## Overview

两条主线可并行：**A 取数口径**（Wave 1→2→3）与 **B 披露结构**（Wave 5）互不依赖；
**C 账龄枚举**（Wave 4）独立。Wave 6 汇总公式预设与端到端实测。

主线 A 的关键是**不再造轮子**：D1 已有实证跑通的报表映射驱动科目定位
（`d1_account_resolver.py`），本 spec 把它的通用部分提升为共享模块并让 D1 委托，
K1 只是第二个消费者。主线 B 的关键是**源 xlsx 为唯一裁决者**，且守卫升级为三向比对。

## Task Dependency Graph

分 6 波。Wave 1（共享科目定位 + 叶子聚合，纯函数为主）是主线 A 的基础；Wave 2 把它接进
K1 render 并做 characterization；Wave 3 前端消费（预填按钮 / 溯源面板 / 兜底口径）；
Wave 4 账龄枚举贯通 K1-1（独立，可与 2/3 并行）；Wave 5 披露/附注结构对齐（主线 B，
独立于 A）；Wave 6 端到端实测与收口。

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "共享科目定位 + 叶子聚合（纯函数 + 单测）",
      "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"],
      "depends_on": []
    },
    {
      "wave": 2,
      "name": "接入 K1 render + 预填补齐 + characterization",
      "tasks": ["2.1", "2.2", "2.3", "2.4"],
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "前端消费：溯源面板 / 带入按钮 / 兜底口径",
      "tasks": ["3.1", "3.2", "3.3", "3.4"],
      "depends_on": [2]
    },
    {
      "wave": 4,
      "name": "账龄枚举贯通 K1-1",
      "tasks": ["4.1", "4.2", "4.3"],
      "depends_on": []
    },
    {
      "wave": 5,
      "name": "披露表 / 附注结构对齐 + 三向守卫",
      "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7"],
      "depends_on": []
    },
    {
      "wave": 6,
      "name": "公式管理预设 + 端到端实测 + 收口",
      "tasks": ["6.1", "6.2", "6.3", "6.4"],
      "depends_on": [2, 3, 4, 5]
    }
  ]
}
```

## Tasks

- [x] 1.1 新建 `backend/app/services/four_table/__init__.py` 与
  `report_line_accounts.py`：把 `d1_account_resolver` 的通用部分提升为
  `ReportLineAccountSpec` / `ReportLineAccounts` / `resolve_report_line_accounts(ctx, spec)`
  + 纯函数 `split_gross_provision` / `normalize_standard_prefix` / `minimal_prefix_set`。
  新增 `extra_gross`（K1 的 `1131`/`1132`）与 `provision_name_filter` 参数化。
  - Requirements: 1.1, 1.2, 1.5, 1.6
  - Properties: 2, 3

- [x] 1.2 `d1_account_resolver.py` 改为薄壳委托共享模块（公开名与字段语义逐字不变），
  跑 `backend/tests/d_cycle_extraction/test_d1_account_resolver.py` 证明零回归。
  - Requirements: 1.1, 1.6
  - Properties: 2, 3

- [x] 1.3 新建 `backend/app/services/four_table/leaf_aggregation.py`：`LeafRow` /
  `select_leaves(rows)` / `aggregate_leaves(leaves, prefixes, absolute=False)`。
  叶子判定与 `trial_balance_service.recalc_unadjusted` 同语义（同数据集 + `code + '.'`
  子科目存在性），但**不做方向翻转**（实测存在 `direction='debit'` 且余额为负的合法叶子，
  翻转会破坏叶子和 = 父科目额的勾稽）。
  - Requirements: 2.1, 2.2, 2.4
  - Properties: 1

- [x] 1.4 新建 `backend/tests/four_table/test_report_line_accounts.py`：拆分优先级
  （direction → 名称 → 码族）、极小前缀集、`extra_gross` 透传、宽前缀退化置
  `use_provision_name_filter`、五种依赖缺失下的 fail-open。
  - Requirements: 1.2, 1.3, 1.4, 1.5, 1.6
  - Properties: 2, 3

- [x] 1.5 新建 `backend/tests/four_table/test_leaf_aggregation.py`（含 hypothesis PBT，
  `max_examples=5`）：叶子互不为前缀、叶子和 = 父额、参差树不丢一级叶子
  （以项目 `0ec33ac9` 实测值 269,885,933.03 / 3,597,359.45 / 55,035,942.52 作 fixture）。
  - Requirements: 2.1, 2.2, 2.3
  - Properties: 1

- [x] 2.1 改 `_k1_other_receivables.py`：删除 `_K1_ACCOUNT_PREFIXES` 与
  `_aggregate_prefix_deepest`（死代码直接删），`_fetch_tb_data` 改为
  `resolve_report_line_accounts(BS-009)` + `select_leaves` + `aggregate_leaves`；
  备抵侧取 `abs()`；`account_codes` 由解析结果派生。
  - Requirements: 1.1, 1.3, 2.1, 2.4
  - Properties: 1, 2

- [x] 2.2 `_build_adjudication_prefill` 改用叶子集合归类款项性质（保证 `1221.11`/`1221.12`
  进桶）；新增 `_build_fs_reconciliation` 产出 `fs_reconciliation{interest,dividend,report_total}`，
  `report_total` 按 `BS-009` 公式各 `TB()` 前运算符加权求和。
  - Requirements: 2.3, 3.1, 3.3
  - Properties: 1, 10

- [x] 2.3 `render` 输出新增 `tb_source_codes`；`K1_SHEETS` 两个披露 sheet 名改为源 xlsx
  逐字值并引用与 `K1_DISCLOSURE_SHEET_NAME` 同源的常量（避免第二真源）。
  - Requirements: 1.7
  - Properties: 7

- [x] 2.4 扩展 `backend/tests/test_k1_adjudication_prefill.py`：坏账为 `1231.03` 口径
  （断言不含 `1231.02` 金额）、性质桶含保证金押金、FS 三行、手工优先返回空预填、
  以及「灰度/依赖缺失时与改动前等价」的 characterization。
  - Requirements: 1.3, 2.3, 3.1, 3.2, 3.3, 3.5
  - Properties: 1, 2, 3, 4, 10

- [x] 3.1 `GtK1OtherReceivables.vue`：新增 `tbSourceCodes` computed（读
  `htmlData.tb_source_codes`）；`_loadTbData` 的坏账兜底请求改用
  `tb_source_codes.provision_standard`（无则回退 `1231-03`），并对返回行集只累加
  互不为前缀的最长码（消除父子双计）。
  - Requirements: 4.1, 4.2, 4.3
  - Properties: 1

- [x] 3.2 新建 `k1/core/K1FourTableSourcePanel.vue`：紧凑单行 bar + 折叠明细，展示
  报表行 / 标准码 / 原始码 / 解析来源（`report_config` vs `fallback` 用彩色 tag 中文化），
  挂在 K1-1 审定表顶部 —— 消费 `tb_source_codes`，杜绝 dead output。
  - Requirements: 1.7
  - Properties: 2

- [x] 3.3 `K1TabAdjudication.vue` + `useK1Adjudication.ts`：新增「从四表库带入未审数」
  按钮（与既有「从 K1-2 带入」并列，`:disabled="isReadonly"` + `:loading`）；
  `applyAdjudicationPrefill` 支持 `fs_reconciliation` 三行（逐项手工优先）。
  - Requirements: 3.3, 3.4
  - Properties: 4

- [x] 3.4 前端单测 `composables/__tests__/useK1AdjudicationPrefill.spec.ts`：
  FS 三行 seed / 手工优先 / 按钮重新套用只覆盖出现类别不清零。
  - Requirements: 3.2, 3.3, 3.4
  - Properties: 4

- [x] 4.1 `k1AdjudicationModel.ts`：新增 `buildK1AgingRowDefs(segments)` 纯函数
  （data 行 + 小计），`K1_AGING_ROW_DEFS` 保留为 FIVE_YEAR 默认导出以兼容既有引用。
  - Requirements: 5.1, 5.4
  - Properties: 5

- [x] 4.2 `k1AdjudicationSync.ts`：`aggregateK12ForK11(rows, segmentKeys?)` 参数化段 key
  （默认 FIVE_YEAR keys 保持旧行为）；`agingBucketLabels(segments?)` 同款。
  - Requirements: 5.2
  - Properties: 5

- [x] 4.3 `useK1Adjudication` / `K1TabAdjudication` 透传 `useAgingConfig(projectId,'K1')`
  的 `segments`；扩展 `composables/__tests__/k1AdjudicationSync.spec.ts`：3 年段
  `over3` 不丢、自定义 2~10 段长度一致（PBT，Property 5）。
  - Requirements: 5.1, 5.2, 5.3, 5.4
  - Properties: 5

- [x] 5.1 扩展 `fix_note_k_complex_structure.py` 的 `K1_LISTED_PLAN`：
  ① 「按账龄披露」行改源模板 5 年段（补 `3至4年`/`4至5年`/`5年以上`，去 `3年以上`）；
  ② 「本期计提、收回或转回的坏账准备情况」列改两级混合分组
  （新增 `_listed_stage_movement_cols()`，标签列不打 `flat`、`合计` 不带 `group`）。
  - Requirements: 7.1, 7.2
  - Properties: 6, 9

- [x] 5.2 同脚本追加 3 张上市表（`rule(..., insert=True)`）：
  `应收政府补助情况`（5 列）/ `因金融资产转移而终止确认的其他应收款情况`（4 列）/
  `转移其他应收款且继续涉入形成的资产、负债的金额`（2 列），并追加对应 `text_sections`
  段落（正文段**不写 `#### ` 前缀**，避免被 `_is_table_title_paragraph` 当标题静默丢弃）。
  - Requirements: 7.3, 7.4
  - Properties: 7

- [x] 5.3 同脚本改 `K1_SOE_PLAN`：「按账龄披露其他应收款项」列改源模板 3 列
  （`账  龄`/`期末数`/`期初数`，`flat`）+ 行补 `小  计`/`减：坏账准备`/`合  计`；
  「账龄组合」行改 6 档。跑 `--dry-run` 复核后 `--check` 归零。
  - Requirements: 8.1, 8.3, 8.4
  - Properties: 6, 9

- [x] 5.4 `k1NoteSectionMap.ts`：`K1_LISTED_SUBTABLE` 追加 `govGrant` / `transfer` /
  `continuedInvolvement`（逐字对齐 5.2 的表名）；新增 `K1_NOTE_TOTAL_LABEL` 单一真源
  并收敛载荷里散落的 `'合  计'` / `'合计'` 字面量（按各表源模板实证取值）。
  - Requirements: 7.3, 8.2
  - Properties: 7

- [x] 5.5 `k1DisclosureSyncPayload.ts`：
  ① listed `stageMovement` 列改两级；
  ② listed 新增 3 表的列头与行映射（`govGrantRows`/`transferRows`/`continuedInvolvementRows`）；
  ③ soe `aging` 改 3 列并忠实推送 `subtotal`/`provision`/`total` 三种 kind，删除
  「合计行补坏账准备列」的迁就 hack。
  - Requirements: 7.1, 7.3, 8.1, 8.2
  - Properties: 6, 8

- [x] 5.6 `k1DisclosureModel.ts` + `useK1DisclosureListed.ts`：listed payload 补
  `govGrantRows` / `transferRows`（`continuedInvolvementRows` 已有）；底稿上市披露 Tab
  补对应录入区块（源模板红字作方法论上下文 + 动态增删行 + `WpAmountInput`）。
  - Requirements: 7.3
  - Properties: 7, 8

- [x] 5.7 守卫三件：
  ① 新建 `backend/tests/services/test_note_k1_structure.py`（openpyxl 直读源 xlsx ↔
  模板 headers ↔ 同步 columns **三向**比对四张关键表 + 反向自检）；
  ② `composables/__tests__/k1NoteSubtableContract.spec.ts` 追加 3 表并保持
  `columnsPending` 为空；
  ③ `governance-checks.yml` 新增 job `note-k1-structure`。
  - Requirements: 9.1, 9.2, 9.3, 9.4
  - Properties: 6, 7, 8, 9

- [x] 6.1 `prefill_formula_mapping.json` K1-1 块补 6 条（`TB('1231-03','期初余额')` /
  `TB('1231-03','期末余额')` / `TB('1131','期末余额')` / `TB('1132','期末余额')` /
  `WP('K1','明细表K1-2','其他应收款余额期末审定数')` /
  `WP('K1','坏账准备明细表K1-3','期末审定数额')`）；K1-2 块保持无 `WP()`。
  - Requirements: 6.1, 6.2, 6.3

- [x] 6.2 扩展 `backend/tests/formula_management/test_preset_library.py`（或新建 K1 专项）：
  断言 K1 条目归入 `workpaper:K1`、`formula_type=='auto_calc'`、K1-2 无 `WP(`。
  - Requirements: 6.4
  - Properties: 10

- [x] 6.3 端到端实测（chrome-devtools + postgres 只读）。
  - Requirements: 10.1, 10.2, 10.3
  - Properties: 1, 2, 6, 7
  - **✅ render 取数链路已活体验证**（项目 `0ec33ac9` / wp `e53abb5b`，`GET
    /api/workpapers/{wp}/render-config` 200）：
    * `tb_source_codes` = `{row_code: BS-009, gross: ['1221'], provision: ['1231.03'],
      gross_standard: ['1221'], provision_standard: ['1231-03'],
      extra: {1131:['1131'], 1132:['1132']}, signed_codes: [[1221,1],[1231-03,-1],[1131,1]],
      formula: "TB('1221','期末余额') - TB('1231-03','期末余额') + TB('1131','期末余额')",
      resolved_from: report_config, provision_resolved_from: report_config,
      provision_exact: true}` —— 报表映射链路全程走通，非兜底。
    * `tb_values.receivable_unadjusted_closing = 269,885,933.03`（= 父科目 `1221` 期末，
      叶子口径正确；**旧「最深层级」口径是 211,252,631.06**）。
    * `tb_values.bad_debt_unadjusted_closing = 900,217.36`（= `1231.03` 口径；
      **旧「整个 1231」口径是 28,464,225.16，含应收账款坏账 26,401,719.77，虚增 31.6 倍**）。
    * 本机 uvicorn `--reload` 本次生效（无需重启即取到新字段）。
  - **✅ `adjudication_prefill` 已活体验证（两个无持久化未审数的项目）**：
    * 项目 `c8621493` / wp `ff1a6f56`：原值期末 1,791,163.90；性质桶
      `intercompany 1,531,163.90 + margin 260,000 + other 0 = 1,791,163.90`
      **= 原值合计（叶子无遗漏，Property 1）**；`fs.report_total = 1,791,163.90`。
    * 项目 `2aa00f57` / wp `b10b8a12`：原值期末 **88,596,839.09**、备抵
      **1,312,178.93**、`fs.dividend 510,000`、`fs.report_total 87,794,660.16`
      = `88,596,839.09 − 1,312,178.93 + 510,000` **按 BS-009 公式符号加权正确
      （Property 10）**；性质桶 `80,743,638.95 + 7,194,804.76 + 658,395.38
      = 88,596,839.09` 分文不差。
    * postgres 只读逐行复核该项目 13 个叶子期末之和 **== 父科目 `1221` 期末
      88,596,839.09**（Property 1 真数据验证），其中含 `direction='debit'` 但余额为负的
      叶子 `1221.98.07 = -86,483.10` —— 若套用 `trial_balance_service` 的 `+ABS()`
      归一，合计会变 88,769,805.29 ≠ 父额，**印证「原值不做方向翻转」的设计决策**。
  - **✅ 披露推送 → 附注落库 + 读时投影已活体验证**（项目 `2aa00f57` §八、9）：
    `POST /disclosure-notes/sync-from-workpaper` 200 → `last_sync_at` 前移、
    `_sub_table_columns` 由旧的 5 列（label 等于 key、无 group）替换为源模板 3 列
    （`账  龄`/`期末数`/`期初数` + 标签列 `flat`）、`sub_table_data` 落 5 行含
    `subtotal`/`provision`/`total` 三种 `row_kind`；`project_sub_tables` 读时投影
    得 `_column_groups = []`（显式单级、无凭空父表头）、`values` 与 `is_total` 正确，
    勾稽 `小  计 1000 − 减：坏账准备 60 = 合  计 940` 成立。
    实测数据已复原（恢复为更早会话遗留的 123,456.78 口径，结构保持修正后形态）。
  - **认证踩坑**：页面 token 会中途过期 → `render-config` 返回 **401「无效的认证凭据」**
    （不是可见性隔离）。在页面内重新 `POST /api/auth/login`（admin/admin123）取新
    `access_token` 写回 `sessionStorage` 即恢复。

- [x] 6.4 收口：后端 K1 + four_table + d_cycle_extraction 全量绿；前端 K1 相关全量绿；
  `fix_note_k_complex_structure.py --check` 零欠账；更新 `.kiro/specs/INDEX.md` 与
  `#dev-history`；把「K 类其他循环沿用本范式」写入 `#conventions`。
  - Requirements: 9.1, 9.2

## Notes

**实证基线（改动前，供回归比对）**

| 项 | 现状（错） | 目标（对） | 来源 |
|----|-----------|-----------|------|
| K1 坏账期末（项目 `0ec33ac9`/2025） | 28,464,225.16 | 900,217.36 | `1231.03` vs 整个 `1231` |
| K1 原值期末（同项目） | 211,252,631.06 | 269,885,933.03 | 叶子口径 = 父科目 `1221` 期末 |
| 丢失的叶子 | `1221.11` 3,597,359.45 / `1221.12` 55,035,942.52 | 计入 | 只取 depth=2 所致 |
| 3 年段项目 K1-1 账龄 | `over3` 恒 0 且多 3 空行 | 4 行且金额完整 | `AGING_SEG_KEYS` 硬编码 |

**踩坑预警（本会话已实证）**

- `read_file` 对并发会话正在改的文件会返回**陈旧版本** —— 本会话读
  `report_account_mapping.py` 曾少 30 行（漏掉 `applicable_standards` 参数），
  以 `python -c "open(p,encoding='utf-8').read()"` 复核为准。
- PowerShell 下 `2>nul` 无效、`>` 重定向会腌坏 UTF-8 中文 → 诊断脚本一律用 `--out` 自己写盘。
- postgres MCP 的查询校验器会拒绝含相关子查询 / `||` 拼接的复杂 SQL → 拆成简单 SELECT
  取回原始行，聚合在本地算。
- `fix_note_k_complex_structure.py` 同时管 K1 与 K6（5 个章节）→ 改 K1 plan 后必须跑
  **全部** `--check`，且 K6 相关守卫 `test_note_k_complex_structure.py` 一并回归。
- 改模板表名必须同步 `K1_LISTED_SUBTABLE` / `K1_SOE_SUBTABLE`，否则下一次同步立刻孤儿表。
- `_source=workpaper` 时投影器**完全覆盖**模板 rows → 模板行骨架只影响「从未同步过」的
  项目与 Word 导出；交付说明须写清「新建项目/重新生成附注才可见」。

**范围外（不在本 spec 做）**

- `report_config` 里 `BS-006 应收账款 listed_standalone = TB('1122') - TB('1231')`
  用整个 `1231`（应收账款报表行虚减）—— 平台级 data-hygiene，另立。
- `note_template` 的 `report_row_code` 全库陈旧（inert）—— 平台级，另立。
- K2~K13 的同类修复 —— 沿用本 spec 范式另立。
- `trial_balance_service.recalc_unadjusted` 的 `debit → +ABS()` 方向归一会翻转
  合法负余额借方叶子（实测 `1221.98.07 = -227,132.40`）—— 平台级，本 spec 只在 K1
  侧不采用该归一并写明理由。
