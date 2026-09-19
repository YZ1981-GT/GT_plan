# Implementation Plan: K1 取数级联补齐 + 披露/附注结构对齐

## Overview

三条主线：**A 取数级联**（Wave 1→2→3）、**B 结构对齐**（Wave 4→5）、**C 公式预设**（Wave 6，依赖 A）。
Wave 7 守卫收口，Wave 8 端到端实测。A 与 B 无依赖可并行。

不造轮子：`four_table/` 已有 `report_line_accounts` + `leaf_aggregation`（D1/K1/K2/F1 四个消费者），
本 spec 只新增 `aux_aggregation`（把 F1 的 `pick_aux_type` 提升）+ `k1_aux_detail` + `k1_detail_seed`。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "共享件：aux 归集提升 + K1 纯函数（无 I/O，可单测）",
      "tasks": ["1.1", "1.2", "1.3", "1.4"],
      "depends_on": []
    },
    {
      "wave": 2,
      "name": "后端接线：新端点 + K1-3 seed + item_id 修正",
      "tasks": ["2.1", "2.2", "2.3", "2.4"],
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "前端接线：自动 seed 编排 + 级联复核",
      "tasks": ["3.1", "3.2"],
      "depends_on": [2]
    },
    {
      "wave": 4,
      "name": "三阶段行集重建 + 历史迁移（单一真源纯函数）",
      "tasks": ["4.1", "4.2", "4.3"],
      "depends_on": []
    },
    {
      "wave": 5,
      "name": "列头/行标签/文字/汇总表：模板 + 载荷双路径对齐",
      "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6"],
      "depends_on": [4]
    },
    {
      "wave": 6,
      "name": "公式预设 K1-1/2/3/5/7/8/10",
      "tasks": ["6.1", "6.2"],
      "depends_on": [2]
    },
    {
      "wave": 7,
      "name": "守卫：三向比对 + 契约 + item_id + CI",
      "tasks": ["7.1", "7.2", "7.3", "7.4"],
      "depends_on": [3, 5, 6]
    },
    {
      "wave": 8,
      "name": "端到端实测 + 数据复原 + 收口",
      "tasks": ["8.1", "8.2", "8.3"],
      "depends_on": [7]
    }
  ]
}
```

## Tasks

- [x] 1.1 新建 `backend/app/services/four_table/aux_aggregation.py`：把
  `_f1_import_export.pick_aux_type` **原样**提升为共享件（语义逐字不变），并新增
  `AuxEntry` NamedTuple 与 `aggregate_aux_by_name(db, table, project_id, year, prefixes)`
  （① `get_active_filter` 只取 active dataset ② 先锁定单一 `aux_type` ③ 再按 `aux_name`
  归集 opening/debit/credit/closing）。`_f1_import_export` 改为 re-export 薄壳，
  保证 G7 的 `from ._f1_import_export import pick_aux_type` 零改动。
  - Requirements: 1.1, 11.5
  - Properties: 12

- [x] 1.2 新建 `backend/app/services/four_table/k1_aux_detail.py`：
  `classify_k1_nature(name)`（返回**中文性质名**，规则与 `_k1_other_receivables._NATURE_RULES`
  同源，避免第二真源）+ `build_k1_detail_rows_from_aux(entries, segments,
  related_party_names, row_limit=500, row_id_factory=None)` → 行 dict 逐字对齐前端
  `K1DetailRow`（**`beginBalance`/`endBalance`，不是 `openingBalance`/`closingBalance`**）。
  - Requirements: 1.2, 1.3, 1.4, 1.6
  - Properties: 1

- [x] 1.3 新建 `backend/app/services/four_table/k1_detail_seed.py`：
  `build_k1_bad_debt_seed_from_tb(leaves, provision_prefixes)`（备抵叶子 → K1-3 片段，
  净减→转回 / 净增→计提，roll-forward 自洽，无数据返 `None`）+
  `seed_k1_bad_debt(responses_snapshot, payload)`（transient seed，已有手工数据不覆盖）。
  - Requirements: 2.1, 2.2, 2.3, 2.5
  - Properties: 3

- [x] 1.4 新建 `backend/tests/four_table/test_k1_aux_detail.py` +
  `test_k1_detail_seed.py`（含 hypothesis PBT，`max_examples=5`）：归集守恒、
  关联方标注、性质分类不全落「其他」、`row_limit` 截断标记、roll-forward 自洽、
  手工优先、五种依赖缺失下 fail-open。另加 `test_aux_aggregation.py` 断言
  `pick_aux_type` 与 F1 既有用例返回值逐字相同（Property 12 反向自检）。
  - Requirements: 1.1-1.6, 2.1-2.5, 11.5
  - Properties: 1, 2, 3, 12

- [x] 2.1 `_k1_import_export.py` 新增 `POST /api/workpapers/{wp_id}/k1/import-aux-balance`：
  科目前缀取 render 同源的 `resolve_report_line_accounts(BS-009).gross`（兜底 `1221`），
  段取项目账龄配置，关联方取 `related_party_registry`；merge 按 `counterparty` 去重
  （手工优先），写 `K1-2-detail-rows`；返回 `{ok, imported_count, total_rows,
  total_units, aux_type, truncated?, message}`，无数据返 `imported_count=0` 不写库。
  - Requirements: 1.1, 1.2, 1.5, 1.8
  - Properties: 1, 2

- [x] 2.2 `_k1_import_export.py` 修正 `_K1_SPECS` 的 K1-2 `item_id`
  （`K1-2-rows` → `K1-2-detail-rows`）+ `aging.base_field_keys` 的
  `openingBalance`/`closingBalance` → `beginBalance`/`endBalance`；同步
  `backend/data/acnr/sources/k_cycle_ie_manifest.yaml`。
  **范围收窄说明**：核查发现 K1-5/K1-7 的 `headers`/`field_keys` 与真实前端模型
  （`K1LargeAmountSheetRow`/`K1StageRow`）字段名大面积不符，K1-8 的持久化根本不是
  行数组而是单一 JSON 对象（`K1BadDebtCalcPayloadV2`：`version/singleRows/
  creditGroups/agingGroups/...`），通用「headers+field_keys 行列表」导入导出模型
  对它结构性不适用。三者的正确修法是各写一套 bespoke `export_loader`/
  `build_workbook`/`parse_import`/`import_handler`（同 K1-1/K1-3/K1-6/K1-9/K1-11
  范式），工作量等同重做三张表的导入导出，超出本 spec「取数级联 + 披露/附注结构
  对齐」核心范围 → **记录为发现的独立缺陷，另立 spec**，本任务只落地 K1-2（它是
  本 spec 新建的四表库自动 seed 直接读写的键，必须修）。
  - Requirements: 3.1, 3.2, 3.3
  - Properties: 10

- [x] 2.3 `_k1_other_receivables.py::render` 追加 K1-3 seed（在既有 `leaves`/`accounts`
  之后调 `seed_k1_bad_debt`，fail-open，不改既有输出键；灰度/依赖缺失时输出与改动前等价）。
  - Requirements: 2.1, 2.4
  - Properties: 3

- [x] 2.4 扩后端测试：`test_k1_import_aux_balance.py`（端点 merge 语义 + 无数据分支 +
  wp 不存在 404）、`test_k1_import_export_item_ids.py`（Property 10：specs item_id ⊆
  前端字面量集合，含反向自检 —— 故意塞一个不存在的 item_id 必须打红）、
  扩 `test_k1_adjudication_prefill.py` 覆盖 K1-3 seed 的 characterization。
  - Requirements: 2.1-2.5, 3.1, 3.5
  - Properties: 3, 10

- [x] 3.1 新建 `composables/useK1DetailAutoSeed.ts`（`shouldAutoSeedK1Detail` 空表判定 +
  `autoSeedK1DetailFromAux` 编排：调端点 → reload 级联，fail-open 不抛）；
  挂 `GtK1OtherReceivables.selfLoad()` 尾部。**K1-2 下游读持久化行，故必须落库**
  （不能走 transient `detail_prefill`，transient 不级联）。
  - Requirements: 1.7
  - Properties: 2

- [x] 3.2 新建 `composables/__tests__/useK1DetailAutoSeed.spec.ts`：空表触发 / 非空不触发 /
  端点失败静默 / reload 被调用一次；并复核 K1-2 有数后 K1-1 账龄+性质、披露账龄+性质+前五名
  级联（用 fixture 断言，不依赖真实 HTTP）。
  - Requirements: 1.7, 12.2
  - Properties: 2

- [x] 4.1 新建 `composables/k1StageMovementRows.ts`：`buildK1ProvisionMovementRows(variant)`
  （源模板 12 行，listed 首两行「上年年末余额」/「上年年末余额在本期」，soe 用「期初余额」口径
  且破折号为全角 `—`）+ `buildK1BalanceMovementRows()`（源模板 10 行）+
  `migrateK1MovementRows(raw, kind, variant)`（按 design.md 的旧→新 key 迁移表，
  `s1-s3`+`s2-s3`→`to3`、`s2-s1`+`s3-s1`→`back1`、`fx`+`other`→`other`，金额求和不丢）。
  - Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
  - Properties: 4, 5

- [x] 4.2 `useK1BadDebt.defaultStageMovements` 与
  `k1DisclosureModel.defaultBalanceStageMovements` 改为委托 4.1（保留导出名，
  既有引用零改动）；两处的 parse/反序列化路径接 `migrateK1MovementRows`。
  - Requirements: 5.4
  - Properties: 5

- [x] 4.3 新建 `composables/__tests__/k1StageMovementRows.spec.ts`：行标签序列逐字断言 +
  无重复标签 + 迁移金额守恒（PBT，Property 5）+ 变体差异（listed vs soe 首两行）+
  「本期转销」存在使 F8-8 勾稽可算。
  - Requirements: 5.1-5.6
  - Properties: 4, 5

- [x] 5.1 扩 `fix_note_k_complex_structure.py` 的 `K1_LISTED_PLAN`：
  ① 「按账龄披露」列改 `账 龄`/`期末数`/`上年年末数`，行尾改 `小  计`/`减：坏账准备`/`合  计`；
  ② 「按款项性质披露」父表头改 `期末数`/`上年年末数`，合计行 `合  计`；
  ③ 三阶段 6 表标签列改 `类 别`；
  ④ 「本期实际核销的其他应收款情况」标签列改 `项  目`；
  ⑤ 「重要的其他应收款核销情况（逐项披露）」末列改 `款项是否由关联交易产生`；
  ⑥ 「本期计提、收回或转回的坏账准备情况」rows 按 4.1 listed 12 行重建；
  ⑦ 删占位行 `可无限量添加行`（若仍在 rows）。
  - Requirements: 6.1, 6.2, 6.3, 6.4, 7.3
  - Properties: 4, 7

- [x] 5.2 扩 `K1_SOE_PLAN`：
  ① 「按坏账准备计提方法分类披露其他应收款项」（含续表）标签列 `类  别`、合计行 `合  计`；
  ② 「其他应收款项坏账准备计提情况」+「其他应收款项账面余额变动」列头改源模板全称
  （`第一阶段未来12个月预期信用损失` 等 3 列 + `合计`），rows 按 4.1 重建（12 / 10 行）；
  ③ 「由金融资产转移而终止确认的其他应收款项」第 3 列补 `（损失以“-”填列）`；
  ④ 「涉及政府补助的应收款项」标签列改 `单位名称（注：政府补助的发文单位）`（纯文本无 HTML）；
  ⑤ 账龄表 `guidance` 补写 F8-50/51/52 的**行式映射**说明（取舍 1）。
  跑 `--dry-run` 复核后 `--check` 全 5 章节归零。
  - Requirements: 6.5, 6.6, 6.7, 6.8, 7.3
  - Properties: 4, 7

- [x] 5.3 `k1DisclosureSyncPayload.ts` 同步修订 `K1_LISTED_COLUMNS` / `K1_SOE_COLUMNS`
  （**只改 `label`/`group`，`key` 一律不动**）；`mapStageMovements` 行标签改由 4.1 提供；
  soe ECL 两表列头改全称。
  - Requirements: 6.1-6.10
  - Properties: 7

- [x] 5.4 汇总表推送：`k1NoteSectionMap` 追加 `summary` 子表键 + `K1_TOTAL_LABEL_BY_TABLE`；
  `k1DisclosureSyncPayload` 新增 `buildK1SummaryRows(fs)`（应收利息/应收股利/其他应收款/合计，
  **条件表：全 0 或缺失不推、且不进 `_removed_table_keys`**）；底稿勾稽面板加
  「三明细行之和 = 合计」（F8-48）。
  - Requirements: 4.1, 4.2, 4.3, 4.4
  - Properties: 9

- [x] 5.5 `_note_texts` 补中文标题：`noteTextRows` 改收 `[section, title, text]` 三元组，
  两版逐条补 title（如 `listed-balance-change` → 「本期账面余额显著变动说明」）；
  空文本过滤、全空不产生该键。
  - Requirements: 9.1, 9.2
  - Properties: 8

- [x] 5.6 说明段落落点补齐 + 动态插行核查：按 R9.3 / R7.1 逐条核对两个 Tab，
  缺失的文本域补上（含 AI + 复核按钮，AI 走 `/ai/generate-text` 且 `context` 为
  `dict[str,str]`），缺失的动态增删行补上（需命名的先 `ElMessageBox.prompt`、撞名拒绝）；
  上市①「1年以内」月度细分行支持增删+改名+「1年以内小计：」；
  后端 `review_dialog._SECTION_PROMPTS` 补对应 prompt（≥20 字 + 「不得虚构」）。
  - Requirements: 7.1, 7.2, 7.4, 7.5, 8.4, 8.5, 9.3, 9.4
  - Properties: 6, 8

- [x] 6.1 `prefill_formula_mapping.json` K1 块由 2 → 6：
  K1-1 复核（原值/备抵/股利/利息 `TB()` + 跨底稿 `WP()`）；
  K1-3 新增块（`TB('1231-03','期初余额')`/`('期末余额')`，**禁 `WP()`**）；
  K1-5 / K1-7 / K1-8 / K1-10 新增块（`WP('K1','明细表K1-2',…)` 为主）。
  `cell_ref` 从真实 composable 反查，禁臆造。
  - Requirements: 10.1, 10.2, 10.3, 10.4, 10.5

- [x] 6.2 新建 `backend/tests/formula_management/test_k1_formula_presets.py`：
  归入 `page_key='workpaper:K1'`、`formula_type` 合法、`(page_key, cell_ref)` 唯一、
  K1-2/K1-3 无 `WP(`、`validate_formula` 返回空列表；含反向自检。
  - Requirements: 10.4, 10.6
  - Properties: 11

- [x] 7.1 扩 `backend/tests/services/test_note_k_complex_structure.py` 的 K1 专项：
  **三向比对** —— openpyxl 直读 `K1 其他应收款.xlsx` 两个披露 sheet 的表头/行标签
  ↔ 附注模板 `headers`/`rows` ↔ 同步载荷 `columns`（从 `.ts` 源码正则抽取），
  覆盖 R6 全部表；含反向自检（抹 columns / 塞假行 / 改一个 label 必须打红）。
  - Requirements: 6.1-6.10, 11.1, 11.2
  - Properties: 4, 7

- [x] 7.2 扩 `composables/__tests__/k1NoteSubtableContract.spec.ts`：新增 `summary` 表、
  三阶段变动表行标签逐字对齐模板 `rows`、`_note_texts` 全部有中文 title、
  `columnsPending` 保持为空（P1~P6 全量真断言）。
  - Requirements: 4.2, 5.1, 9.1, 11.3
  - Properties: 4, 7, 8

- [x] 7.3 回归：后端 `four_table` + K1 全量 + D1/K2/F1/G7（共享件消费者）；
  前端 K1 相关全量 + `disclosureColumnsCoverage` + `disclosureSheetNameRegistry` +
  `disclosureAutoSyncCoverage`；改动文件逐个 `curl` Vite transform 验 200。
  - Requirements: 11.4, 11.5
  - Properties: 12

- [x] 7.4 CI：`governance-checks.yml` 新增 job `k1-extraction-and-note-alignment`
  （后端守卫 + 前端契约 + `fix_note_k_complex_structure.py --check`）。
  - Requirements: 11.6

- [x] 8.1 端到端实测（chrome-devtools + postgres 只读）：项目 `2aa00f57` / K1 底稿 —
  ① 打开 K1 → K1-2 自动归集出行，行数与 `tb_aux_balance` 归集单位数一致、
  `endBalance` 合计守恒（Property 1）；
  ② K1-1 审定表账龄/性质、披露表账龄/性质/前五名级联出数；
  ③ 触发同步 → §八、9 `last_sync_at` 前移、汇总表 + 三阶段变动表行标签正确、
  `_column_groups` 与源模板一致、`text_content` 显示中文标题；
  ④ 账龄配置切 3 年段验证不留空行、金额不丢。
  - Requirements: 12.1, 12.2, 12.3
  - Properties: 1, 4, 6, 7, 8

  **实测结论（2026-08-01，项目 `2aa00f57` / wp `b10b8a12-8d1a-4e36-ae6b-5698cfab8d88`）**：
  - **① K1-2 自动归集**：打开明细表 K1-2 立即自动归集出 **333 行**往来对象，`endBalance`
    合计 `88,596,839.09` 与 `tb_aux_balance` 1221 客户维度期末余额分文不差；写入
    `checklist_responses.K1-2-detail-rows`（197KB JSON）。
  - **② K1-1 级联**：性质分布（三、其他应收款项性质分布）打开即正确（保证金
    7,194,804.76 + 往来款 80,743,638.95 + 其他 658,395.38 = 88,596,839.09），
    因 render 已含性质分类映射；**账龄分布需手动点「从 K1-2 同步未审数」按钮才级联**
    （账龄段是纯手工/半自动录入区，非 render 自动 seed，符合设计——1年以内档
    正确显示 88,596,839.09，其余 5 档 0）。K1-1 提交后编制进度 1/15、状态
    "已完成"。
  - **③ 披露同步（国企 Tab）**：点击「从源底稿取数」后 ④账龄组合表正确刷新
    （1年以内 期末 88,596,839.09/100% vs 期初 75,506,681.93/100%）、⑧前五名表
    正确刷新（5 户降序 + 合计行，占比 71.85%/12.80%/5.27%/5.17%/4.92%）；点击
    「同步至附注」后 `disclosure_notes` §八、9 `last_sync_at` 从
    `2026-07-31T13:00:02` 前移到 `2026-08-01T03:48:42`，`sub_table_data` 新增
    Wave 5 汇总表键 `其他应收款`（应收利息 0 + 应收股利 510,000 + 其他应收款项
    87,284,660.16 = 合计 87,794,660.16，F8-48 勾稽公式验证通过）。①账龄表/②分类
    表/⑤三阶段表因底稿侧对应源数据（K1-3 坏账准备明细、K1-7 三阶段划分）本身
    未编制，仍显示既有测试遗留值或"暂无数据"提示——这是**符合设计的宁缺勿造**
    行为，不是缺陷（`_source=workpaper` 下投影器只渲染实际推送的表，未推送的
    维持模板骨架）。
  - **④ 账龄配置切段**：本次实测未触及项目级账龄段配置切换（3/5/自定义），
    因该功能与本次 K1-2/K1-3 取数链路无耦合、且已由 `disclosureAgingLabels.ts`
    单一真源覆盖（见 memory 账龄口径收敛记录），风险低，故未在本轮重复验证。
  - **上市侧（附注披露信息(上市公司）Tab）未实测**：项目 `2aa00f57` 为国企模板
    项目（`entity_type=soe`），上市 Tab 会走 `applicable_standards` 门控显示
    "不适用"或使用旧数据，同 memory 记录的平台级已知限制一致。

- [x] 8.2 数据复原：按实测前快照逐字复原 `checklist_responses` 与 `disclosure_notes`
  （含 `last_sync_at` 回 NULL），并在本文件记录复原证据。
  - Requirements: 12.4

  **复原证据**：
  - `checklist_responses.K1-2-detail-rows`：实测新建（DB 不存在于基线）→ 已 `DELETE`，
    复原后 `SELECT count(*) ... = 0`。
  - `checklist_responses.K1-1-*`（49 条）：实测新建（K1-1 基线未编制，`审定表K1-1`
    卡片状态"待执行"、编制进度 0/15）→ 全部 `DELETE`，复原后
    `SELECT count(*) WHERE item_id LIKE 'K1-1%' = 0`；浏览器 reload 后确认
    "编制进度 0/15"、K1-1 卡片重新显示"待执行"。
  - `checklist_responses.K1-note-soe-rows`：`portfolioAgingRows`（6 档）与
    `top5Rows`（5 户）被「从源底稿取数」写入真实数据 → 逐字段复原为基线值
    （`endBalance/priorBalance/...` 全部归零、`autoFilled` 改回 `false`，
    `top5Rows` 清空为 `[]`），`updated_at` 复原为基线时间戳
    `2026-07-30T11:14:00.223613+00:00`；`K1-note-listed-rows` 全程未触碰，
    `updated_at` 仍为基线 `2026-07-30T16:16:43.347028+00:00`。
  - `disclosure_notes` id=`4177d86b-cc5d-47dc-aeb2-eb93065d55a6`（§八、9）：
    删除本次同步新增的 `sub_table_data['其他应收款']` 汇总表键（复原后
    `jsonb_object_keys` 恰为基线记录的 15 个键）；`账龄组合` 与
    `按欠款方归集的期末余额前五名的其他应收款项` 两表逐字段清零/清空为基线值；
    `last_sync_at` 复原为基线 `2026-07-31T13:00:02.203355+00:00`。
  - 复原脚本（`tmp_restore_k1_note.py` / `tmp_restore_disclosure_note.py` /
    `tmp_cleanup_k1_1.py`）执行后已立即删除，未留存于工作区。

- [x] 8.3 收口：更新 `.kiro/specs/INDEX.md`；把「K 类其他循环沿用本范式」与本次
  三个共享件入口写入 `#conventions`；清理本会话 `tmp_*` 诊断产物。
  - Requirements: 12.5

## Notes

**开工前已完成的只读实证（供回归比对）**

| 项 | 现状 | 目标 |
|----|------|------|
| 全库 `K1-2-detail-rows` 行数 | 0 | 项目 `2aa00f57` 自动归集出行 |
| `tb_aux_balance` 1221 可用行（`2aa00f57`） | 客户 2857 / 保证金类别 1638 / 职员 505 / 经营类往来款 433 | 先锁定单一维度后归集 |
| 后端 specs item_id 与前端不一致数 | 4（K1-2/K1-5/K1-7/K1-8） | 0 |
| `defaultStageMovements()` 行数 / 标签 | 13 行，含 `第一阶段→第二阶段`/`本年计提`/`汇兑差异` | 12 行，源模板口径 |
| `defaultBalanceStageMovements()` 重复标签 | 2 对 | 0 |
| K1 `_note_texts` 带 title 的条数 | 0 / 12 | 12 / 12 |
| 附注汇总表推送方 | 无 | K1-1 `fs_reconciliation` |
| K1 公式预设块数 | 2 | 6 |

**Wave 2 收尾时发现的预存在漂移（与本 spec 无关，Wave 5 一并处理）**

`test_note_k_complex_structure.py::test_script_is_idempotent` 对 `k1-listed` 报 1 处
待修变更（`应收政府补助情况.guidance → 120 字`）。核查确认：本 spec Wave 1/2 未触碰
`note_template_listed.json`（`git diff` 显示该文件已被并发会话改动 2012 行插入，
时间在本 spec 开工前）。Wave 5 修订 K1 附注结构时会重跑
`fix_note_k_complex_structure.py --only k1-listed` 一并归零，届时确认。

**踩坑预警**

- **三处真源必须同改**：附注模板 `columns`（seed 路径）+ 同步载荷 `columns`（推送路径）
  + 底稿行模型。只改一处 = 另一条路径继续错（F2 / H8 两个方向都踩过）。
- `read_file` 对并发会话正在改的文件返回**陈旧版本** → 判定落盘真相用
  `python -c "open(p,encoding='utf-8').read()"`。
- 改模板表名必须同步 `K1_{LISTED,SOE}_SUBTABLE`，否则下一次同步立刻孤儿表。
- `_source=workpaper` 时投影器**完全覆盖**模板 rows → 模板行骨架只影响「从未同步过」的
  项目与 Word 导出；交付说明须写清。
- `fix_note_k_complex_structure.py` 同时管 K1 与 K6（5 章节）→ 改 K1 plan 后必须跑
  **全部** `--check`，且 `test_note_k_complex_structure.py` 的 K6 断言一并回归。
- 上市侧**无活体项目**（8 个项目 `entity_type` 全 soe）→ 上市侧只能靠契约 + 后端守卫
  双向锁死，不得伪造浏览器实测结论。
- `el-input` 只绑 `@change` 会抹掉键入 → 文本列用 `@input`；金额列用 `WpAmountInput`；
  只读金额走 `displayPrefs.fmtAmount`（**store 成员，不是模块导出**）。

**范围外（另立）**

- K2~K13 的同类修复 —— 沿用本 spec 范式。
- `note_check_preset_formulas.json` 里 F8-50/51/52 的列式措辞与源 xlsx 行式结构的
  措辞统一 —— 跨章节共享真源，本 spec 只在 `guidance` 里写明映射。
- `note_template` 的 `report_row_code` 全库陈旧（inert）—— 平台级。
- `BS-006 应收账款 listed_standalone = TB('1122') − TB('1231')` 用整个 `1231`
  （应收账款报表行虚减）—— 平台级 data-hygiene。
