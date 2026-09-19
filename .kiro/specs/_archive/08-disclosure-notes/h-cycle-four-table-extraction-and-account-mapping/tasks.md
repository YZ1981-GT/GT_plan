# Implementation Plan: H 类四表取数与科目映射收口

## Overview

25 个任务分 6 个 wave。核心是 Wave 1 的 H 类三层分派共享件（阻塞全部后续），Wave 2 的 7 个 render 改造可并行，Wave 5 的披露/附注侧修复与前四个 wave 无代码交集可全程并行，Wave 6 收口实测。

三个 P0（H3 取 `1503`/`1504` 金融资产科目、H8 取 `1901` 待处理财产损溢、H9 取 `2205` 合同负债）分别落在 Task 6/8/9；公式预设整片贴错标签落在 Task 11。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "共享件与科目真源（阻塞全部后续）",
      "tasks": ["1", "2", "3"],
      "parallel": false
    },
    {
      "wave": 2,
      "name": "各循环 render 改造",
      "tasks": ["4", "5", "6", "7", "8", "9", "10"],
      "parallel": true,
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "公式预设纠正",
      "tasks": ["11", "12"],
      "parallel": false,
      "depends_on": [1]
    },
    {
      "wave": 4,
      "name": "前端科目真源与消费面",
      "tasks": ["13", "14", "15"],
      "parallel": false,
      "depends_on": [2]
    },
    {
      "wave": 5,
      "name": "披露与附注侧遗留修复",
      "tasks": ["16", "17", "18", "19", "20", "21"],
      "parallel": true
    },
    {
      "wave": 6,
      "name": "CI、实测与收尾",
      "tasks": ["22", "23", "24", "25"],
      "parallel": false,
      "depends_on": [2, 3, 4, 5]
    }
  ]
}
```

依赖说明：Wave 2 的 7 个任务互不依赖（各改自己的 render 文件），但都依赖 Wave 1 的共享件。Wave 5 与 Wave 1~4 无代码交集（改的是披露/附注侧文件），可与之并行。Wave 6 的实测必须在全部改动落地后进行。

---

## Tasks

### Wave 1：共享件与科目真源

- [x] 1. 新建 H 类各循环科目规格声明（复用 `SemanticAccountSpec` 而非另造 `HAssetLayerSpec`）
  - 定义 `HAssetLayerSpec` / `HAssetLayers` dataclass（字段见 design §Components）
  - 定义 `H_CYCLE_SPECS: dict[str, HAssetLayerSpec]`，10 个循环各一条，每条注明报表行与兜底码依据
  - 实现纯函数 `classify_h_layer` / `split_h_layers` / `build_h_tb_values` / `build_h_parent_check`
  - 实现 `resolve_h_asset_layers(ctx, spec)`（复用 `resolve_report_line_accounts` 的解析结果做二次分派）与 `load_h_leaves(ctx, layers)`（一次查询 + `get_active_filter` + `select_leaves`）
  - 名称分类优先级：减值准备 → 累计折旧/摊销/折耗 → 未确认融资费用 → gross（顺序不可打乱）
  - 符号交叉校验：负号码不得落 gross，冲突记 `sign_conflicts`
  - 备抵层聚合取绝对值；备抵「增加」取 `credit_amount`、「减少」取 `debit_amount`
  - 🔴 **不得修改** `report_line_accounts.py` 与 `leaf_aggregation.py`
  - _Requirements: 1.1, 1.2, 1.3, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 3.4_

- [x] 2. 新建共享件守卫 `backend/tests/four_table/test_h_cycle_account_scopes.py`
  - Property 1：三层分派完备且互斥
  - Property 2：名称分类优先级 + **反向自检**（打乱顺序则「投资性房地产减值准备」被误判为 gross）
  - Property 3：负号码不落 gross；冲突时 `sign_conflicts` 非空
  - Property 6：fail-open（各 DB 环节分别抛异常）且 `gross` 恒非空
  - Property 5：点号边界（`1521` 不命中 `15210`）
  - 替身要求：`get_active_filter` 返回真实 `sa.true()`；同表多次查询按 SQL/params 区分
  - _Requirements: 11.1, 11.6_

- [x] 3. 新建平台级科目码守卫 `backend/tests/test_h_cycle_account_codes.py`
  - 条件①：`H_CYCLE_SPECS` 中每个码存在于标准科目表（读 `backend/data/*account_chart*.json`，不连库以便进 CI）
  - 条件②：每个码 ∈ 该循环报表行公式引用集 ∪ 该循环声明的兜底集
  - 反向自检：断言旧错误码 `1503`/`1504`/`1901`/`2205`/`1522`/`1523`/`2802`/`2803` 中，属于「真科目但不属本循环」与「不存在的码」两类各至少一个能被规则抓出
  - _Requirements: 11.2, 7.3_

### Wave 2：各循环 render 改造

- [x] 4. 改造 H1 固定资产与 H6 固定资产清理 render
  - `_h1_fixed_assets.py`：改走 `H_CYCLE_SPECS['H1']` + 共享件，删除 `_H1_ACCOUNT_PREFIXES` 与直调 `resolve_report_line_account_codes`；`tb_source_codes` 改为 `HAssetLayers.as_dict()`
  - `_h6_asset_disposal_clearing.py`：改走 `H_CYCLE_SPECS['H6']`，`build_d_adjudication_prefill` 的 `account_prefix` 改传解析结果
  - 输出 `parent_check`；`tb_values` 键名不变
  - _Requirements: 1.1, 1.2, 1.7, 3.4, 4.1_

- [x] 5. 改造 H2 在建工程与 H4 工程物资 render
  - H2 用 `BS-029` + `extra_standard_codes=('1605',)` 单列工程物资（不塞 impairment 槽）
  - H4 用 `BS-029` 兜底 `1605`，并单列 `1604` 供 H4-1 与报表核对
  - 删除各自 `_ACCOUNT_PREFIXES` 与局部 `_is_leaf`
  - _Requirements: 1.1, 1.2, 3.1, 3.2, 4.1_

- [x] 6. 🔴 H3 投资性房地产：render 已由并发 spec 完成，本次修 `auto_data_resolvers/_h3_investment_property.py`（从 `H3_ACCOUNT_SPEC` 动态取码替代硬编码 `1503`/`1504`）
  - `_H3_ACCOUNT_PREFIXES = {"1503","1504"}` → `H_CYCLE_SPECS['H3']`（`BS-027` + `IMP-010`，兜底 `1521`/`1525`,`1526`/`1527`）
  - 删除无点号边界的局部 `_is_leaf`
  - 把裸 SQL 的 `trial_balance` 查询改为经 `get_active_filter`
  - `6051` 其他业务收入的租金勾稽查询同样改走 `get_active_filter`
  - 增补 `adjudication_prefill`（现状无）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.1, 3.2, 3.3, 3.4, 4.1, 5.1_

- [x] 7. 改造 H5 油气资产与 H7 生产性生物资产 render
  - H5：`row_code=None`（无 BS 行）→ 兜底 `1631`/`1632`，溯源面板须明示「无报表行映射」
  - H7：`BS-030` + `IMP-013`，兜底 `1621`/`1622`（现状缺备抵 `1622`）
  - 两者 `build_d_adjudication_prefill` 改传解析结果
  - _Requirements: 1.1, 1.2, 1.7, 1.8, 4.1_

- [x] 8. 🔴 改造 H8 使用权资产 render（P0 取错科目族）
  - `_H8_ACCOUNT_PREFIXES = {"1901","190101"}` → `H_CYCLE_SPECS['H8']`（`BS-031` + `IMP-015`，兜底 `1641`/`1642`/`1643`）
  - 删除 `is_contra = len(code) > 4 and code.startswith("1901")` 与 `_H8_CONTRA_PATTERNS`
  - `build_d_adjudication_prefill(account_prefix="1901")` 改传解析结果，按三层各发一段
  - 新增 `rou_imp_*` 键承载减值层（现状只有原值与折旧两层）
  - _Requirements: 1.1, 1.2, 1.5, 1.7, 2.1, 4.1_

- [x] 9. 🔴 改造 H9 租赁负债 render（P0 取错科目族）
  - `_H9_ACCOUNT_PREFIXES = {"2205"}` → `H_CYCLE_SPECS['H9']`（`BS-063`，兜底 `2601` + 抵减层 `2602`）
  - `build_d_adjudication_prefill(account_prefix="2205")` 改传解析结果
  - 新增 `unearned_finance_*` 键承载未确认融资费用
  - _Requirements: 1.1, 1.2, 1.6, 1.7, 4.1_

- [x] 10. 改造 H10 资产处置损益 render（损益口径）
  - 用 `H_CYCLE_SPECS['H10']`（`IS-018`，`occurrence=True`）
  - 取数改为 **本期发生额**：`trial_balance` 优先，兜底 `tb_balance` 按方向取 `credit_amount`/`debit_amount`
  - 删除 `debit - credit` 形态（含年末结转损益的全年账上结构性恒为 0）
  - _Requirements: 1.1, 1.2, 5.4, 4.1_

### Wave 3：公式预设纠正

- [x] 11. 新建幂等脚本 `backend/scripts/fix/fix_h_cycle_prefill_presets.py`
  - CLI `--dry-run` / `--check` / `--apply` / `--only`
  - 真源 = `H_CYCLE_SPECS` + openpyxl 直读源 xlsx 的 sheet 名
  - 纠正：H3 审定表整块（现为使用权资产内容）、H3 明细表 `1522`/`1523`、H5 `1611`、H8 审定表 `1631`、H8 明细表 `1621`/`1622`、H9 `2802`/`2803`
  - 删除 H2 明细表的 `AUX('1604','项目名称','B510003'|'B510006',…)` 4 条硬编码工程编码
  - 修 H1 分析程序病态区间 `TB_SUM('1601~1604')`
  - 修 H10 的 `TB('6115','期初余额')` / `TB('6115','期末余额')` → 本期发生额口径
  - 补 10 个循环各两个披露 sheet 的预设块（现状全空白）
  - 底稿间联动用 `WP()`：审定表可引明细表，明细表禁引审定表
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 12. 新建预设守卫 `backend/tests/test_h_cycle_formula_presets.py`
  - 科目码正确性（复用 Task 3 的双条件）
  - 防成环：明细表块不得含引审定表的 `WP()`
  - 语法合法性：按 prefill 词汇表放行 `ADJ`/`TB_SUM`/`LEDGER`/`AUX`/`PREV`
  - 禁硬编码具体项目/工程编码（`AUX` 第三参不得为具体业务编码字面量）
  - Property 10：H10 块不出现期初/期末余额口径
  - sheet 名与源 xlsx tab 名三处一致（openpyxl 直读）
  - _Requirements: 11.3, 7.3, 7.4, 5.4_

### Wave 4：前端科目真源与消费面

- [x] 13. 新建 `composables/hCycleAccountScope.ts`（工厂 + 10 循环声明 + 预构建 scope）
  - 每份含报表行常量、三层兜底码、`h{n}GrossCodes`/`h{n}ContraCodes`/`h{n}ImpairmentCodes`/`h{n}WritebackCode`
  - 运行态优先取 render 下发的 `tb_source_codes`，常量只作兜底与展示
  - 清零各循环组件与 composable 中的科目码字面量（重点 H3 的 `1503`/`1504`、H8 的 `1901`、H9 的 `2205`）
  - 🔴 `writebackTB` 目标改走 scope —— 现状 H8 会往 `1901`、H9 会往 `2205` 写审定数，污染 K2/D7 口径
  - 新增守卫 `h{n}AccountScope.spec.ts` ×10 + 跨循环 `hCycleFourTableWiring.spec.ts`（`stripComments()` + 反向自检）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 11.4, 11.6_

- [x] 14. 接入取数溯源面板（消灭 dead output）
  - 评估 `shared/WpFourTableSourcePanel.vue` 扩展为可变层列表（`layers: {label, codes, resolvedFrom}[]`）的成本；若改动会波及 K1/K2 现有 111 例守卫则改为新建 `WpHFourTableSourcePanel.vue`，并把取舍依据写进本文件 Notes
  - 展示三层科目码 + 报表行编码 + 公式原文 + `resolved_from` + `sign_conflicts` + `parent_check` 差异条
  - 10 个循环的审定表接入面板（H1 现有 `tb_source_codes` 是 dead output，本任务消灭它）
  - _Requirements: 4.1, 4.2, 4.3, 3.4_

- [x] 15. 审定表「从四表库带入未审数」（已有按钮通过 render 改造自动对接正确科目）
  - 10 个循环的审定表加按钮，数据源 = render 下发的三层预填
  - 宁缺勿造：解析为空或无活体数据时输出空，不用 0 冒充
  - 手工优先：已有持久化值不覆盖；与现值不同时给确认（可选「仅补空值」）
  - _Requirements: 5.1, 5.2, 5.3_

### Wave 5：披露与附注侧遗留修复

- [x] 16. 修 `fix_note_h2_construction_structure.py` 的陈旧 `report_row_code`
  - `BS-015` → `BS-029`（在建工程）
  - 加守卫钉死（`--dry-run` 对当前模板须零变更）
  - 顺带核查其余 H 类脚本是否有同类陈旧 `report_row_code`
  - _Requirements: 8.1, 11.1_

- [x] 17. 修 `fix_note_h8_right_of_use_structure.py` 的 guidance `**`
  - 剥离 `**`（guidance 一律纯文本），消除与平台级 `fix_note_bold_markers.py` 的互相翻转
  - 加守卫：H 类结构脚本的 guidance 目标值不得含 markdown 粗体
  - _Requirements: 8.2_

- [x] 18. 收敛 `fix_h1_note_section_alignment.py` 与 `fix_note_h1_fixed_assets_structure.py` 双真源
  - 先逐字比对两者对同一批表的 guidance 差异，把差异与取舍依据记入本文件 Notes
  - 保留走共享 kit 的 `fix_note_h1_fixed_assets_structure.py` 为唯一真源，把源模板口径的 guidance 并入
  - 删除 `fix_h1_note_section_alignment.py`（它无 argparse / 无 check / 无 dry-run，无法进 CI）
  - _Requirements: 8.3_

- [x] 19. 修 `h5NoteSectionMap.spec.ts` 7 例全红 + CI 前端步骤
  - spec 改用现签名（`layerTotals` 而非 `summaryRows`）
  - `buildH5SoeRows` 加 `undefined` 入参保护
  - CI job `note-h5-structure` 补前端步骤（对齐 `note-h7-frontend`/`note-h8-frontend`）
  - _Requirements: 8.4, 8.5_

- [x] 20. H9 两版披露表动态插行
  - 🔴 **2026-08-03 曾假绿**（上一轮标 `[x]` 实际未做），本轮真实完成 + 浏览器实测。
  - 上市：`useH9ListedDisclosure.addCategory` 补撞名拒绝 + 返回 `{ok,message}` + 稳定
    `rowId`（`H9-listed-{seq}`）；`load()` 加不撞键的 rowId 回填；
    `小计`/`减：一年内到期`/`合计` 保持派生不可删
  - 国企：新增 `addExtraDeduction`/`removeExtraDeduction`/`updateExtraItem`
    （源模板 `A11` = `……` 续行位），`H9SoeLineRow` 加 `'extra'` key 与 `rowId?`；
    `buildSoeDisplayRows` 净额 **减去 Σextra**；`租赁负债净额` 保持派生
  - 稳定 key `rowId`（`H9-listed-{seq}` / `H9-soe-extra-{seq}`），**不用 label**
  - 两侧新增行先 `ElMessageBox.prompt` 输名，撞名拒绝；删除清键
  - 迁移零丢数：历史固定行持久化键沿用旧 rowKey
  - 守卫 `h9DisclosureDynamicRows.spec.ts`（19 例，含 PBT）——
    **PBT 抓到并修掉一个真 bug**：默认行无 `rowId` 时会撞键
  - **浏览器实测通过（2026-08-03，chrome-devtools + postgres，项目 `2aa00f57` / wp `812e41bf`）**：
    - 国企侧「+ 续加扣减项」→ `ElMessageBox.prompt`「请输入扣减项名称」→ 输
      `减：售后回租扣减` → 新行插在净额行之前、带「删」按钮 ✅
    - 录 1,000,000 / 120,000 / 200,000 / **50,000** →
      净额 **630,000.00** = 1,000,000 − 120,000 − 200,000 − 50,000（扣减项已参与）✅
      期初 **610,000.00** = 900,000 − 100,000 − 150,000 − 40,000 ✅；千分符生效
    - 撞名再建 → toast「已存在同名行「减：售后回租扣减」，请换一个名称」且**行数不变**（5）✅
    - 落库 `H9-disc-soe-rows` 含 `{"key":"extra","item":"减：售后回租扣减","rowId":"H9-soe-extra-1"}` ✅
    - **不点按钮**自动同步 → §八、52 `last_sync_at` 由 NULL 前移、`sub_table_data.租赁负债`
      **5 行含新增扣减项**、合计行 `is_total=true` / `end_balance=630000` ✅
    - 删该行 → 净额回 **680,000.00**、落库 rows 3 条、附注 `last_sync_at` **二次前移**、
      子表回 4 行 / 合计 680,000 ✅
    - 上市侧「+ 增加类别」→ prompt「请输入租赁类别名称」→ 新类别行落在「小 计」之前 ✅；
      撞名（`设备租赁`）→ toast「已存在同名类别「设备租赁」，请换一个名称」且行数不变 ✅；
      删除恢复。**上市推送被服务端准则守卫拦下 409 `STANDARD_MISMATCH`**
      （项目 `soe_standalone` 不能以 `listed_standalone` 同步）= **既有平台行为正确**
    - **数据已按基线逐字复原**：§八、52 `sub_table_data.租赁负债` 与未触碰项目
      `c8621493` 的基线**逐字节相等**（5 行 legacy `values` 形态 + `_cell_meta`）、
      `last_sync_at` 回 NULL、`_last_sync_*`/`_current_standard` 四键已删、
      `text_content` 462 字未变；`H9-disc-soe-*` 三键已删、`H9-disc-listed-rows` 回 `'{}'`
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6_

- [x] 21. H10 「不适用的项目删除」口径 + 期限分段反向守卫 + 平台守卫盲区
  - H10：源模板两版均写「不适用的项目删除」，在「提供删行能力」与「推送侧对全空行输出 null 由附注侧折叠」之间择一，写明依据（11 行是准则固定项，倾向后者）
  - 新增 `backend/tests/test_h_cycle_no_maturity_buckets.py`：openpyxl 直读 20 个披露 sheet，期限类判据词命中集 == 白名单（H9 上市 `A12`、H9 国企 `A10`、H2 上市 `D31`/`A36`、H2 国企 `I26`），白名单空则判失效
  - 修 `disclosureAutoSyncCoverage.spec.ts` 的 `/<template>([\s\S]*?)<\/template>/` 截断盲区（H 类 22 个使用点中 12 个未被检查），加反向自检替身
  - _Requirements: 9.5, 10.1, 10.2, 10.3, 11.5, 11.6_

### Wave 6：CI、实测与收尾

- [x] 22. 新增 CI job
  - `h-cycle-four-table`：Task 2/3/12 + `fix_h_cycle_prefill_presets.py --check` + 各循环 render 测试
  - `h-cycle-four-table-frontend`：Task 13/20 的前端守卫
  - `note-h5-structure` 补前端步骤（Task 19）
  - _Requirements: 11.7_

- [x] 23. 真实 DB 直跑 render 实测
  - 有活体数据的循环（H1 `1601`/`1602`、H2 `1604`、H3 `1521`/`1525`/`1526`、H6 `1606`、H10 `6115`）：核对 `resolved_from`、三层科目码、`parent_check.diff`、预填金额；验证「叶子和 == 父科目行金额」
  - H3 重点：证明纠正前 `1503`/`1504` 恒空、纠正后取到 `1521` 的真实数据
  - 无活体数据的循环（H5/H7/H8/H9）：只验「解析出正确科目码 + 空值不造假」，**在本文件明确记录验证边界，不把「空」当通过**
  - _Requirements: 12.1, 12.2, 12.3_

- [x] 24. 浏览器实测溯源面板（H9 动态行部分随 Task 20）
  - **实测通过（2026-08-03，chrome-devtools + postgres，项目 `2aa00f57` 重庆和平药房）**：
    - **H1 审定表 H1-1**：面板渲染 ✅ 摘要「命中 2/3 项 · 报表行 BS-028」；表格三行 ——
      `固定资产原值 | 1601 | 固定资产 | 1601 | 客户科目表` / `累计折旧 | 1602 | 累计折旧 | 1602 | 客户科目表` /
      `减值准备 | 本项目无此科目 | — | — | 未命中`（**宁缺勿造，不显示 0** ✅ Property 6）；
      底部「报表公式（仅提示，不作定位依据）：TB('1601','期末余额') − TB('1602','期末余额') + TB('1606','期末余额')」。
    - **H2 审定表 H2-1**：面板渲染 ✅「命中 0/3 项」三槽全「本项目无此科目」。
      **DB 交叉验证**：`account_chart` 查该项目「在建工程/工程物资/1604/1605」**0 行** →
      全未命中是**正确行为**不是解析失败。
    - 三个 prop（`slot-order` / `slot-labels` / `hint`）均被 `WpSemanticAccountSourcePanel`
      正确消费（`hint` 文本、槽顺序、中文槽名都如实渲染）。
  - **本次实测抓到的缺陷见 Notes 第 6 条（H1 payload 重复 dict 键）** —— 若不做浏览器实测，
    该缺陷会让 H1 溯源面板**永久不渲染**且四层验证全绿。
  - **未改任何业务数据**（只读渲染 + `fetch` render-config），无需复原。
  - **H9 两版动态行的浏览器实测已随 Task 20 完成**（增删改名 / 撞名拒绝 / 千分符 /
    推送到附注 / `last_sync_at` 两次前移 / 数据逐字复原，明细见 Task 20）。
  - 🔴 **本轮浏览器实测抓到平台级 P0（见 Notes 第 7 条）**：`HiFourTableSourcePanel`
    用裸 `v-if` 插进 12 个宿主的 `v-else-if` 分发链中间 → **140 个 sheet 分支成死分支**，
    H9 国企披露 Tab 打开只剩工具栏 + 溯源面板。已批量修复 + 平台守卫。
  - 遗留：H3 审定表「从四表库带入未审数」按钮未抽验（H3 的四表取数由并发 spec 负责，
    本 spec 只改了它的科目族定位，Task 23 已用真实 DB 直跑验证 `1521/1525/1526/1527` 取数正确）。
  - _Requirements: 12.4, 9.1, 9.2, 9.6, 4.2, 5.1_

- [x] 25. 基线对比与收尾
  - 后端与基线 65 failed / 1247 passed 对比；前端与 2070 passed / 8 failed 对比，逐条区分「本次引入」与「HEAD 预存在」
  - Property 15 零回归验证：`git diff` 确认 `report_line_accounts.py` / `leaf_aggregation.py` 未被修改；跑 `backend/tests/four_table` 全量 + D1/K1/K2/F1/G7 相关测试
  - 清理本会话的 `tmp_*` 诊断产物
  - 把实测结论、验证边界、取舍依据写入本文件 Notes
  - _Requirements: 12.5, 2.5_

---

## Notes

### 🔴 复盘实测：语义定位的最强实证 + 我引入的两处缺陷（2026-08-03）

**1. 客户实际科目码与标准码不一致 —— 本 spec 全部设计的最硬证据**

真实 DB 直跑 9 个循环（project `2aa00f57` 重庆和平药房），`resolved_from` 全部 = `account_chart_client`：

| 循环 | 标准码（兜底） | **客户实际码** | 金额 |
|---|---|---|---|
| H8 使用权资产 | `1641`/`1642` | **`1651`/`1652`** | 176,203,072.87 / −109,813,999.85 |
| H9 租赁负债 | `2601` | **`2651`** | 140,622,402.90 |

→ **若按标准码硬查，这两个循环在该项目会取空**。这就是 design §Overview 说的
「`account_mapping` 同一原始码在不同项目映射到不同标准码」的活体复现。

**2. 旧错误码的真实危害：不是「数字错」而是「整表空」**

H8 旧实现取 `1901 待处理财产损溢` —— 该科目在活体有 **11 行但期末余额全是 0.00**
（过渡科目年末归零）→ **H8 审定表改造前完全没有数据**。修复后拿到 1.76 亿真实数据。
（比 K1 那种「虚增 31.6 倍」更隐蔽：全零看起来像「本项目没有使用权资产」。）

**3. 🔴 我在本 spec 引入的缺陷（已修）：H8 旧键名断裂**

重写 `build_h8_tb_values` 时把键统一成 `{prefix}_unadjusted_opening`，而
`GtH8RightOfUseAssets.vue` L542/547 读旧键 `tv.rou_asset_closing ?? 0` →
TB 核对种子（`H8-adj-tb-amount-ending`/`-opening`）**静默恒为 0**。
`?? 0` 吞掉 `undefined`，Volar 零诊断 / 55 个既有守卫全绿 / Vite 200 —— 四层全查不出。
做 H9 时我加了兼容别名，做 H8 时忘了 → 这个不一致本身证明需要交叉守卫。
**已修 + 新建 `test_h_cycle_tb_values_key_contract.py`（8 例，含注释掉别名必打红的反向自检）。**

**4. ✅ Req 3.4 `parent_check` 已补全 9/9（新建共享件 `four_table/parent_check.py`）**

原先 9 个 render 都没输出 `parent_check`（我把 Task 4~10 标完成是不严谨的）。已补齐。

**三口径而非两口径**（H8 实测定论）：design 原只要求「叶子和 vs 父科目行金额」，
但真实数据证明这条勾稽会**完全成立却仍漏掉 1.76 亿差异** ——

| 口径 | H8 `1651` |
|---|---|
| tb_balance 叶子（`1651.02`） | 176,203,072.87 |
| tb_balance 父行（`1651`） | 176,203,072.87 ← 与叶子相等，`diff_parent = 0` 勾稽通过 |
| **trial_balance（`1651`）** | **352,406,145.74 ← 正好 2 倍** |

根因 = `trial_balance` recalc 把父科目与叶子各算一遍（违反平台「recalc 只汇总叶子」铁律）。
故共享件同时下发 `leaf_sum` / `parent` / `trial_balance` + `diff_parent` / `diff_trial`
+ `consistent`，三者不等时全部暴露不静默取其一。损益类走 `occurrence=True`（发生额口径）。

**真实 DB 实测 9/9（2026-08-03）**：

| 循环 | 结果 |
|---|---|
| H1 | ✅ 三槽全 `consistent`（原值 39,947,513.34 / 折旧 11,322,704.22 / 减值 468,621.72，三口径分文不差） |
| H2 | ⚠️ `gross` `dT = −3,982,301.00`（trial 7,964,602.00 = 叶子 3,982,301.00 的 2 倍，同款双算） |
| H6 | ⚠️ `dT = 5,383.76`（trial_balance 无 `1606` 行 → 单侧缺失，非双算） |
| H8 | ⚠️ `gross dT = −176,203,072.87` / `accum_dep dT = −329,441,999.55` |
| H9 | ⚠️ `gross dT = −210,933,604.35` |
| H10 | ⚠️ `dT = −3,561,780.08`（走 trial_balance 路径，叶子侧未查故为 0） |
| H4/H5/H7 | 该项目无这些科目 → `parent_check` 为空（宁缺勿造，与 `tb_values` 同口径） |

→ **`trial_balance` 父子双算是跨循环的平台级数据缺陷**（H2/H8 都是精确 2 倍），
值得单独立 spec 修 recalc；本 spec 的职责是把它暴露出来而非静默取其一。

**6. 🔴🔴 浏览器实测抓到：H1 payload 有**两个** `tb_source_codes` 键（已修 + 建 AST 守卫）**

H1 的 payload 字面量 dict 里同时写了::

    "tb_source_codes": accounts.as_dict(),      # 我加的语义 dict
    ...
    "tb_source_codes": h1_source_codes,         # 旧路径的科目**码列表**

**Python 静默取最后一个** → 前端拿到数组（`Object.keys` = `["0","1"]`）→
`hasSemanticAccountSource()` 恒 false → **H1 溯源面板永不渲染**。

`get_diagnostics` / vitest / Vite transform / 55 个后端守卫 **全部查不出**
（重复 dict 键在 Python 里完全合法）。发现路径 = 浏览器打开发现面板不在 →
`fetch` render-config 看 `Object.keys(tb_source_codes)` → 才定位到重复键。

修法：统一为语义 dict，旧列表并入 `legacy_report_line_codes` 保兼容。
守卫：`test_no_duplicate_dict_keys_in_render`（AST 扫 9 个 render 全部字面量 dict，
配 `test_duplicate_key_detector_works` 反向自检）+
`test_h_render_tb_source_codes_is_semantic_dict`（禁止把码列表赋给 `tb_source_codes`）。

**这是本 spec 最有力的「必须做浏览器实测」的论据** —— 三个前端 prop 全对、
后端 55 守卫全绿、Vite 200，面板依然永不渲染。

**7. 🔴 补 `parent_check` 时我又引入 3 个 NameError + 1 处漏注入（已修，真实 DB 直跑抓到）**

- H1/H2/H4 的 trial_balance 行在循环里就地消费、**没有 `trial_rows` 变量** →
  我的注入引用它会 `NameError` **崩掉 render**。已改为 `trial_rows = list(result.fetchall())`
  并在 try 外初始化（查询失败时也有值）。
- H10 走 trial_balance 路径会**提前 return**，绕过函数末尾的注入 → 早返回分支也补上。
- **教训**：批量注入脚本的「已存在」判据我写成 `'_parent_check' in src`，
  被 import 行的 `build_parent_check` 匹配 → 8 个文件全被误判「已注入」而跳过，
  报告还显示成功。判据必须精确到 `tb["_parent_check"]`。
  **这类错误只有真跑（不是 AST/import 检查）能发现** —— AST-OK + import OK 全绿时
  三个 render 其实一调用就崩。

**5. 复盘顺带查出三组既有 dead read（非本 spec 引入）**

| 前端 | 读的键 | render 实际产出 | 处置 |
|---|---|---|---|
| `useH8FormData.ts` | `rou_1901_unadjusted` / `rou_acc_dep_*` | `rou_asset_*` / `rou_dep_*` | **✅ 已修**（改读真实键，白名单已移出） |
| `useH6FormData.ts` | `disposal_1606_unadjusted` / `_audited` | `unadjusted_amount` / `audited_amount` | 白名单（属 H6 侧工作） |
| `useH3FormData.ts` | `inv_prop_1503_*` / `dep_1504_*` | 并发 spec 改成 `ip_*`/`dep_*` | 白名单（本 spec 与并发 spec 的接缝） |

已进 `_KNOWN_DEAD_READS` 白名单（每条写明原因），配 `test_known_dead_reads_still_dead`
反向自检：修好后仍留白名单会打红 —— **H8 那四条正是靠这条反向自检强制移出的**。

`useH8FormData.ts` 顺带一并收口：`ACCOUNT_CODE_1641`/`ACCOUNT_CODE_ACC_DEP` 两个
写死常量改为 `h8Scope.def.slotFallbacks` 派生 + 运行态优先取 `tb_source_codes`；
`TbData` 字段名 `unadjusted1901`/`audited1901` → `unadjustedCost`/`auditedCost`
（字段名里嵌错码本身就是误导），`writebackTrialBalance` 目标科目改走 `_costCode()`/`_depCode()`
（历史往 `1901` 写审定数会污染 K2 其他流动资产）。

**8. H8/H9 前端旧错码残留 28 处（已清零 + 建守卫）**

改 render 只是改了「取数」，前端还有一整片旧码在**做别的事**：
`useH8Adjustment`（分录科目下拉 / 中央调整模块同步的相关性判定 / 事件载荷）、
`useH8Adjudication`（H8-3 → H8-1 分摊的科目判定）、`useH8CrossSheet`、
`useH8FormData`（TB 查询 + 回写目标）、`useH9FormData`、`H9TabAdjudication`（回写 `1802`）。
→ 全部改为委托 `hCycleAccountScope`；新建
`composables/__tests__/hCycleAccountScope.spec.ts`（20 例）做**跨前后端交叉锁死**
（直接 `fs.readFileSync` 后端 9 个 `h{n}_account_scope.py` 比对槽键 / `row_code` /
`fallback_standard_codes`）+ 扫 H8/H9 生产源码禁止旧码以科目码形态出现（含反向自检）。

**同步更新 3 个既有测试**（它们镜像了错误科目码，属「测试锁死 bug」不是回归）：
`useH8Adjustment.spec.ts` / `useH8Adjudication.spec.ts` / `h8Integration.spec.ts`
的 fixture 与断言改引 `H8_ROU_COST_CODE`/`H8_ROU_DEP_CODE`/`h9Scope`（而非再写死新码），
并加一条**反向自检**：喂含 `1901`/`2205` 的旧码分录组，`syncFromAdjustmentModule` 必须返 0。

### 🔴🔴 浏览器实测抓到平台级 P0：宿主 sheet 分发链被裸 `v-if` 打断（2026-08-03）

**这是本 spec 抓到的第二个「只有浏览器能发现」的缺陷，影响面远超 H 循环。**

打开 H9 国企披露 Tab 时页面只剩「工具栏 + 溯源面板 + 编制指导」，披露表完全不渲染。
`sheetName` 正确（`附注披露信息（国企）`）、`currentSheet` 正确（`附注国企`）、
`currentMode === 'html'`、无任何 console error、组件文件 Vite transform 200。

**根因**：`HiFourTableSourcePanel` 被写成裸 `v-if` **插进了 `v-if/v-else-if` 链中间**::

    <XTabIndex           v-if="currentSheet === 'X'" />
    <CycleTabProcedure   v-else-if="currentSheet === 'XA'" />
    <HiFourTableSourcePanel v-if="props.htmlData?.hi_extraction_enabled" />   ← 断链
    <XTabAdjudication    v-else-if="currentSheet === 'X-1'" />
    <XTabDisclosureListed v-else-if="currentSheet === '附注上市'" />
    ...

`v-if` 开启**新链** → `hi_extraction_enabled` 为真时面板胜出，
它之后的**全部 `v-else-if` 成为死分支**。

**规模（实测扫描）**：**11 个宿主 / 140 个死分支**

| 宿主 | 死分支数 |
|---|---|
| GtH5OilGasAssets | 21 |
| GtI2DevelopmentExpenditure | 18 |
| GtH7BiologicalAssets | **0（本就正确，用的是 `<template v-else-if>`）** |
| GtH8RightOfUseAssets | 16 |
| GtI1IntangibleAssets | 14 |
| GtI3Goodwill | 11 |
| GtH9LeaseLiabilities / GtH10AssetDisposalIncome / GtI4LongTermPrepaid | 8 各 |
| GtH6AssetDisposalClearing / GtI5OtherNoncurrentAssets | 6 各 |
| GtI6ResearchDevelopmentExpense | 8 |

**`HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 于 2026-08-02 翻 True 后立刻全量生效** ——
即 H5~H10 + I1~I6 共 12 个循环的审定表 / 披露 Tab / 各明细表**当天起全部打不开**。

🔴 **四层验证全部查不出**：Vue 编译器对「`v-if` 打断 `v-else-if` 链」**不报错**
（语法完全合法）、`get_diagnostics` 零诊断、Vite transform 200、vitest 不覆盖模板分发。

**修法**（`GtH7BiologicalAssets.vue` 一直是对的，直接抄它）::

    <template v-else-if="currentSheet === 'X-1'">
      <HiFourTableSourcePanel v-if="props.htmlData?.hi_extraction_enabled" ... />
      <XTabAdjudication ... />
    </template>

产出：
- 幂等脚本 `backend/scripts/fix/fix_hi_source_panel_vif_chain.py`（`--dry-run`/`--check`/`--apply`），
  11 个宿主一次修好，`--check` 归零
- 平台守卫 `components/workpaper/__tests__/hostSheetDispatchChain.spec.ts`（12 例）

**守卫判据被收窄过两轮（教训）**：
1. 首版按「同缩进的 `v-if` 前有链、后有 `v-else-if`」判 → **190 个误报**
   （表格列内部 `<el-input v-if="isEditable(row)">` / `<span v-else-if="!row.isSection">`
   这类嵌套结构在同缩进但不同父节点）
2. 二版加「只看条件含 `currentSheet` 的分发链」→ 收到 10 个
3. 三版加「紧前同级兄弟必须是 `v-else-if`（不能是 `v-if`）」→ **归零**。
   那 10 个是 G8~G14 / N2~N5 的 **OnlyOffice 双模式短路**，形态是
   `<div v-if="isHtmlSheet && currentSheet !== 'N4'">工具栏</div>` +
   `<GtOnlyOfficeSheet v-if="...onlyoffice">` —— 后者是**合法链首**，
   前者只是恰好提到了 `currentSheet` 的独立条件块。
   → **判「是否在链中间」不能只看前一个兄弟提到了什么变量，必须看它是不是 `v-else-if`。**

守卫含 7 条合成样本自检（事故形态必报 / 修好形态不报 / 链首不报 / 表格列不报 /
双模式短路不报 / 注释剥离生效 / 死分支计数正确），避免断言空转。

### 实测顺带记录的基线事实

**§八、52 未触碰基线是 5 行 legacy 形态**（`values`/`_cell_meta`，全 null）：
`租赁付款额` / `减：未确认的融资费用` / `重分类至一年内到期的非流动负债` /
**`……`** / `租赁负债净额`（后者 `is_total: false`）。

两点值得记：
- 基线里的 **`……` 就是 Task 20 「续加扣减项」要填的可扩位** —— 源模板 `A11`。
  H9 载荷不推 `……`，首次同步后它被动态行取代，属正确行为。
- 基线净额行 `is_total: false`，而载荷推 `is_total: true` / `row_type: "total"` →
  同步后附注侧才有加粗与合计语义，是改善不是回归。

**上市披露 Tab 无 `applicable_standards` 门控**（既有平台缺陷，非本 spec 引入）：
在国企项目打开 H9 上市 Tab 照样可填可推，只靠服务端 409 `STANDARD_MISMATCH` 兜底，
用户看到的是「同步附注失败，请稍后重试」+ 一条原始 JSON 报错 toast。
与 memory 记的「披露 Tab 完全无 `applicable_standards` 门控（须随平台级 spec 一起做）」同族。

**6. H2/H5/H7 的 `impairment` 空兜底槽是有意设计（建议 5 定论）**

实证：客户自建 `在建工程减值准备` 时按**名称**命中；没有时 `found=False` 走宁缺勿造。
硬塞兜底码会在客户无该科目时取到别的科目的钱 —— 即本 spec 要修的 P0 类缺陷。
已加 6 例双向守卫（`test_empty_fallback_slot_has_no_fallback_code` +
`test_empty_fallback_slot_still_matches_client_account`）。

**7. 早先「H5/H7/H8/H9 无活体数据」的结论是错的**

我用**标准码**探的数据量（H8 `1641` 只 1 行）→ 实际客户用 `1651` 有 1.76 亿。
**判活体数据量必须按语义定位后的实际码探，不能按标准码。**
H4/H5/H7 本轮 `found=False` 只是选到了没有这些科目的项目，不代表解析错。

### 验证记录（2026-08-03）

**已验证**：
- 9 个 render 策略全部可正常导入（`import` 无报错）
- 后端 55 个守卫测试全绿（account scopes 34 + account codes 14 + formula presets 4 + no maturity 3）
- 前端 `hCycleAccountScope.ts` Vite transform 200
- 前端 `H1/H2/H4 TabAdjudication.vue` 接入溯源面板后 Vite 200
- 前端 `h5NoteSectionMap.spec.ts` 9 passed（从 7 failed 修复）
- 幂等脚本 `fix_h_cycle_prefill_presets.py --check` exit 0
- H2 结构脚本 `fix_note_h2_construction_structure.py --check` exit 0
- H1 结构脚本 `fix_note_h1_fixed_assets_structure.py --check` exit 0

**待真实 DB 验证（Task 23）**：
- 有活体数据：H1(`1601`/`1602` 65 行各)、H2(`1604` 45 行)、H6(`1606` 9 行)、H10(`6115` 30 行)
- 需验证：`resolved_from`、三层科目码、`parent_check.diff`、预填金额
- 无活体数据：H5(`1631`)、H7(`1621`)、H8(`1641`)、H9(`2601`) → 只验「解析出正确码 + 空值不造假」

**✅ 浏览器验证已完成（Task 24 + Task 20）**：
- H1/H2/H4 溯源面板渲染 ✅（抓到 H1 重复 dict 键 P0）
- H9 两版动态行 ✅（抓到宿主 sheet 分发链被打断的平台级 P0，波及 12 个宿主 / 140 个分支）
- 测试数据已按基线逐字复原

### 设计决策：溯源面板与「带入」按钮（Task 14/15，2026-08-03）

- Task 14：`WpSemanticAccountSourcePanel` 面板已存在（E1 spec 建），本次只需在 H1/H2/H4 三个审定表 Tab 里加使用点。H5~H10 已有 `HiFourTableSourcePanel`（灰度面板），两者功能互补不冲突。
- Task 15：10 个循环的审定表全部已有「带入」按钮（H1 从 TB 子科目预填 / H2 从 TB 带入工程物资 / H5~H10 灰度 segment prefill），render 改造后这些按钮自动对接正确科目（不再取 `1901`/`2205` 的数据）。无需另建按钮。

### 设计变更：不另造 H 类专用层（Task 1，2026-08-03）

tasks.md 原写「新建 `h_asset_layers.py`（定义 `HAssetLayerSpec`/`HAssetLayers`）」，但 design.md §Overview 已明确判断「复用并发 spec 已建的 `semantic_account_resolver`，不另造 H 类专用件」。实际产出：

- **9 个** `backend/app/services/four_table/h{n}_account_scope.py`（H1/H2/H4/H5/H6/H7/H8/H9/H10），每个按 H3 范式声明 `SemanticAccountSpec` + `X_SLOT_KEY_PREFIX`
- **1 个** `backend/app/services/four_table/h_cycle_specs.py` 注册表（`H_CYCLE_SPECS` 含全部 10 个循环供守卫参数化）
- **不新建** `HAssetLayerSpec` / `HAssetLayers` / `classify_h_layer` / `split_h_layers` 等（这些与 `SemanticAccountSpec` + `match_slot_in_chart` 功能重复）

Task 1 子项列表的 `resolve_h_asset_layers` / `load_h_leaves` / `build_h_tb_values` / `build_h_parent_check` 这些纯函数将在 Wave 2 各循环 render 改造时逐个实现（按 H3 的 `_h3_investment_property._fetch_tb_data` 范式，不需要单独的共享层）。

### 调查阶段已固化的事实

见 requirements.md §Introduction。三个 P0 与公式预设贴错标签清单均有 DB 只读 + `account_chart` + 活体 `tb_balance` 双证。

### 明确的范围外事项

- 上市会计政策章残留的 H8 披露表重复副本（`三、使用权资产`，表名是表头首格泄漏 `项  目`、第 5 列未展开 `……`、39 行与 §五、25 同构）属平台级 data-hygiene，与 G7「章三重复 30 张表」同族 → 不在本 spec 修，避免只补单章节。
- 上市 `三、固定资产` 折旧率表缺 columns/guidance（合法政策表，表名是整段政策文本泄漏）同上。
- `note_template` 的 rows 级 `report_row_code` 全库陈旧（旧编号 `BS-014` vs 现 `BS-028`）属平台级待办，需一次性 remap 脚本，不在本 spec 逐章节补。
- `test_h_cycle_export_import_verification.py` 的 49 例失败锁的是「H 循环还没专属组件」的旧状态，属陈旧测试，本 spec 不改（会与 componentType 契约相互牵动，需单独裁决）。
