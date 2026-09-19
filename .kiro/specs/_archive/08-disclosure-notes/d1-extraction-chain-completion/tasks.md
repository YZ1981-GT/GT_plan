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

- [x] 6. 守卫收口与浏览器实测
- [x] 6.1 附注结构复核（源模板 14/12 表逐表）
  - 以源模板 sheet + F4 预设为裁决者产出差异清单（无差异亦记录）
  - 有欠账则 `fix_note_d1_notes_receivable_structure.py` 增量修复 + `--check` 归零
  - _Requirements: 7.1, 7.2, 7.4_
  - **差异清单见 §Notes「Wave 6.1 逐表复核结果」**：26 张表的表名/行骨架/列键/两级表头
    与源模板逐表一致（列头字面按 F4 预设裁决，已复核 F4-1/F4-2/F4-3a/F4-29）；
    查出 **4 处真实漂移**并全部修掉 —— ①上市「转应收账款」表名多一个「将」
    ②准则23号括注挂错表 ③披露页 7 条小节标题有 5 条漂移且上市主表与质押表撞「（1）」
    ④D1 脚本与平台级 `fix_note_bold_markers.py` 就 guidance 的 `**` 互相打架。

- [x] 6.2 全量回归
  - 后端 `backend/tests/d_cycle_extraction/` + D1 相关；前端 D1 相关全绿（既有基线除外）
  - CI job `d1-extraction-chain`
  - _Requirements: 8.3_
  - **后端 743 绿**（`d_cycle_extraction` 全量 + `test_note_d1_structure`(243) + AI /
    导入导出 / ECL / PBT / Word 导出）；**前端 34 文件 489 例绿**（`npx vitest run d1 D1`）。
  - 🔴 顺带修掉 Wave 5 遗留的**测试未跟上数据**：`_D1_EXPRESSION` 还钉着旧的原值口径
    `TB('1121','期末余额')`，而预设已改净额 `- TB('1231-01','期末余额')`（源模板 D1-1
    `E20=E18-E19` 比的是净值 + `report_config` BS-005 soe 公式双证）→ 3 条断言红。
    已改常量并**加口径守卫**（必须同时含两项且是减项 + description 须写明净额依据），
    防日后又被改回原值口径。
  - CI 新增两个 job：`d1-extraction-chain`（后端取数链路 + 源 xlsx 表名交叉比对）、
    `d1-extraction-chain-frontend`（锚点单一真源 + 小节标题 + 子表名契约）。
  - 🟡 既有基线（未触碰）：`b23Property7And8.pbt.spec.ts` suite error `stringOf is not a function`。
  - 🔴 踩坑：`npx vitest run -t ""` 的空名过滤会把**全部**用例判为 skipped
    （9004 skipped / 0 passed 看着像跑通了，实际零断言执行）；位置参数是**子串过滤不是 glob**，
    传 `"src/**/*d1*.spec.ts"` 会匹配 0 文件并 exit 1。正确写法：`npx vitest run d1 D1`。

- [x] 6.3 浏览器实测（chrome-devtools + postgres 只读）
  - 真实项目 `0ec33ac9…`/2025：D1-2/D1-4 有数 → D1-1 原值+坏账+净值有数 → 披露①分类表有数 → 推送后附注 五、4·八、4 落库正确（列头/两级表头/比率百分数）
  - 测试数据用后复原
  - _Requirements: 8.4_
  - _Properties: 5, 6, 8_
  - **实测结果见 §Notes「Wave 6.3 实测记录」**：链路全通，并抓出**第 5 处真实缺陷**
    （TB 核对行「Tier A 预设净额 vs render 回退原值」口径分叉 + `tb_provision_amount`
    是 dead output），已修 + 守卫 + 活体复验。

## Notes

### Wave 6.1 逐表复核结果（2026-07-31）

**裁决者**：源模板 `backend/wp_templates/D/D1 应收票据.xlsx` 两个披露 sheet（openpyxl
直读含公式与合并区）；列头字面按 `note_check_preset_formulas.json` 的 F4-* 预设。

**结论：26 张表（上市 14 / 国企 12）的表名、行骨架、列键、两级表头分组与源模板一致**，
`--check` 0 欠账。逐表要点（无差异亦记录）：

| 版本 | 表 | 源模板 | 复核结论 |
|---|---|---|---|
| 上市 | 1 应收票据 | R7–R11 两级（期末余额 / 上年年末余额） | ✅ 子列名按 F4-3a 取「账面余额/坏账准备/账面价值」，消除源模板把期间写两遍的冗余 |
| 上市 | 2 质押 / 3 背书贴现 / 4 转应收账款 | R15 / R21 / R32 | ✅ 行用「票据」（主表用「汇票」）；占位行「可无限量添加行」已删入 guidance |
| 上市 | 5–6 按坏账计提方法分类 | R37 + R50（续） | ✅ 双期拆两表；7 行（含两个「其中：」）与 R40–R49 一致 |
| 上市 | 7–8 按单项计提 | R63 + R69（续：） | ✅ 空白录入行 + 合计 |
| 上市 | 9–10 组合计提项目 | R76 / R83 | ✅ 同表并列双期 → group；行维度「出票人类型或账龄」入 guidance |
| 上市 | 11 变动表 | R94–R100 | ✅ 7 行，顺序 = B100 公式项；`[本期转销]`/`[其他]` 去方括号（源模板可选行） |
| 上市 | 12 重要转回 / 13 核销总额 / 14 核销逐项 | R101 / R107 / R110 | ✅ 14 表第 2 列取 F4-29「应收票据性质」（源模板 B111 字面「应收票据」是截断） |
| 国企 | 1 应收票据分类 | R6–R10 两级（期末数 / 期初数） | ✅ |
| 国企 | 2–3 按计提方法分类 | R13 + R19（续） | ✅ 三级表头按「顶层期间提到表名」拆表，剩两级用 group（账面余额 / 坏账准备 + 账面价值 rowspan=2 无 group） |
| 国企 | 4 按单项 / 5 按组合 | R27 / R34 | ✅ 组合表行序**商承小计在前**（源模板 A36 先商承后银承），忠实保留 |
| 国企 | 6 变动表 | R46–R52 | ✅ group=本期变动情况，期初/期末不带 group |
| 国企 | 7 重要转回 | R54 | ✅ `cumulative_provision` 是金额列（源 C59=SUM） |
| 国企 | 8–10 质押/背书/转应收账款 | R61 / R67 / R75 | ✅ |
| 国企 | 11 核销总额 / 12 核销逐项 | R81 / R84 | ✅ 国企侧列名「应收票据的性质」（与上市不同，各守其源） |

**查出并修掉的 4 处真实漂移**：

1. 🔴 **上市「转应收账款」表名多一个「将」**：模板/脚本/前端映射都写
   `期末因出票人未履约而将其转应收账款的票据`，源模板 R31 是「而**其**转应收账款」
   （国企 R74 是「而其转**为**应收账款」，两版措辞本就不同）。原因：既有守卫全是
   **自证**（拿脚本常量比模板 JSON），源模板从未参与裁决 → 漂移零成本。
   修法：脚本表名改源模板字面 + `LEGACY_TABLE_NAMES` 走 `_rule(aliases=)` 原地改名；
   前端 `D1_LISTED_SUBTABLE.transfer` 同改并新增 `D1_LEGACY_OBSOLETE_TABLES` +
   载荷 `_removed_table_keys`（**与本次推送键求差集**，防把刚推的表当孤儿删）；
   `note_template_bindings.json` 五、4 表 3 的 `table_name` 一并对齐（按 index 匹配
   故不致命，但会留漂移陷阱）。**存量**：项目 `0ec33ac9` 的 五、4 已有 14 张子表含旧键，
   下次上市同步即自愈（该项目 entity_type=soe 被 409 挡住 → 旧键只是不渲染的死数据）。
2. 🔴 **准则23号括注挂错表**：`（如根据《企业会计准则第23号——金融资产转移》终止确认的
   应收票据，列示其终止确认的金额…）` 原在**转应收账款**表 guidance 上，而源模板该括注
   紧跟在**已背书或贴现**表合计行之后（上市 R27 / 国企 R72–R73），讲的正是该表两列
   （终止确认 / 未终止确认金额）的口径，与转应收账款表无关。两版皆错，已移正。
3. 🔴 **披露页 7 条小节标题有 5 条漂移**（`D1TabDisclosure.sectionLabels`）：上市
   「（2）…且未到期」「（3）…而转为应收账款」「（4）按坏账准备计提方法分类披露」、
   国企「（5）…且在资产负债表日尚未到期」「（6）…而将其转应收账款」；且**上市主表被标成
   「（1）」与质押表撞号**（源模板主表 R6 无编号，编号自「（1）期末已质押」起）。
   已按源模板逐字改正 + 新增守卫 `d1DisclosureSectionLabels.spec.ts`（含编号不重复、
   两版措辞不得被「统一」、旧文案不复活三条）。
4. 🔴 **两个幂等脚本互相打架**：本脚本 guidance 写 `**出票人类型或账龄**`，而平台级
   `fix_note_bold_markers.py`（附注模板剥离 markdown 粗体）会把它剥掉 → 一天内被改两次
   （HEAD 有 `**`、工作树无，`test_apply_plan_is_idempotent` 因此打红）。guidance 是
   **纯文本**渲染（TAB 提示 / Word 导出都不解析 markdown），已去掉标记并加守卫
   `test_guidance_has_no_markdown_bold`。

**新增/升级守卫**（后端 `test_note_d1_structure.py` 217→243 例）：
`test_table_name_matches_source_sheet_title`（**openpyxl 直读源 xlsx** 交叉比对 17 张表名
+ 归一函数处理小节编号 /「其中：」/「如下」/ 尾冒号）、`test_source_title_crosscheck_is_not_vacuous`
（反向自检：旧名不在源模板中 = 该守卫能抓住本次回归）、`test_legacy_table_names_are_not_current_names`、
`test_derecognition_note_belongs_to_endorsed_table`、`test_guidance_has_no_markdown_bold`。

**已复核为「非欠账」的两项**（不改）：①`report_row_code` 两节皆 `None`（全库陈旧属平台级
data-hygiene，None 反而 inert）②合计行字面附注侧是「合计」而源模板底稿侧是「合  计」
（两侧口径不同，`DISCLOSURE_TOTAL_LABEL` 不可全局硬套，D3 已有先例）。

### Wave 6.3 实测记录（2026-07-31）

环境：项目 `0ec33ac9…`（重药控股安徽_2025，`template_type=listed` 但
`applicable_standard_v2.entity_type=soe` → 准则判定国企）/ wp `68c7740e…`；
两个灰度开关 `.env` 已 opt-in；chrome-devtools 驱动 + postgres 只读比对。

**① 科目映射链路（Wave 1）活体生效**：`html_data.tb_source_codes` =
`{gross:['1121'], provision:['1231.01'], gross_standard:['1121'],
provision_standard:['1231-01'], resolved_from:'report_config',
provision_resolved_from:'report_config'}` —— 坏账**原始码** `1231.01`
（点号）由 `report_config` → 标准码 `1231-01` → `account_mapping` 反解得到，
不再靠名称关键字猜。

**② 明细 seed（D1-2 / D1-4）有数**：`D1-cat-rows` 三行（银行承兑 / 商业承兑 / 信用证）+
`D1-bd-portfolio-rows`（期初 3,037,132.25 → 本期转回 1,874,844.22）。

**③ 审定表 TB 核对行**：Tier A 锚点 `D1-adj-tb-amount` = **19,046,910.15**
（= 原值 20,209,198.18 − 坏账 1,162,288.03），假差异已消除。

**④ 披露①分类表自动带数（Wave 2/3 的跨表链路）**：国企披露 Tab 主表渲染
银行承兑 12,460,611.29 / 商业承兑 7,748,586.89 / **信用证**（← 动态票据种类，
Requirement 2.4 + 3.2）/ 合计 **20,209,198.18 = tb 1121 期末**。坏账列为 `-`
（D1-4 只有「按组合计提」总额、未按票据种类拆）→ 符合「宁缺勿造」，不臆造分摊。

**⑤ 小节标题**：7 条全部按源模板渲染，3 条旧漂移文案零残留。

**⑥ 推送附注**：点「同步到附注」→ 提示「已同步 29 行」→ 库中 八、4 的
`_last_sync_at` 由 `2026-07-31T14:34:12` 前移至 `16:26:05`，12 子表、
`应收票据分类` 含信用证行、`_sub_table_columns` 的组合表首列带 `flat`。
数据未污染（幂等重同步，子表数 12→12，仅时间戳前移 = 本次实测证据本身）。

### 🔴 实测抓出的第 5 处缺陷：TB 核对行口径分叉 + dead output（已修）

Tier A 预设 `D1-adj-tb-amount` 已改净额，但 render 下发的**seed 回退标量**
`project_context.tb_amount` 仍是原值 20,209,198.18，且 `tb_provision_amount`
**前端 grep 零消费**（dead output）。后果：用户在公式管理里停用该 Tier A 公式后，
核对行回落到原值 → 重现「差异恰好等于坏账准备」的假差异（1,162,288.03）。

修法：

- 后端新增 `_net_tb_amount(project_context)`：把 `tb_amount` / `_unadjusted` /
  `_audited` 三个口径统一减去对应坏账准备，原值移入 `tb_amount_gross*` 供溯源。
  **无坏账数据时完全空操作**（净额恒等于原值）→ 灰度开/关逐字节等价不破。
- 前端 `GtD1NotesReceivable` 新增 `tbNotesReceivableProvenance` 并透传给审定表，
  `D1TabAdjudication` 在「试算平衡表核对」上方渲染琥珀色溯源条
  「取数口径：净额 · 原值 X − 坏账准备 Y = Z」→ `tb_provision_amount` 不再是 dead output。
- 守卫 3 例（净额换算 / 无坏账时空操作 / **与 Tier A 预设同口径**）。
- 🔴 顺带修掉**两个测试替身的共性缺陷**：`_FakeSession` 对 trial_balance 的
  两次查询（原值 1121 前缀内联 / 坏账 1231-01 走绑定参数）返回同一行 →
  坏账 == 原值 → 净额恒为 0，把新守卫变成噪声。已按 `params` 里是否含 `1231` 分流。

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
