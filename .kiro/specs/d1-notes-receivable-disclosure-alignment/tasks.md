# Implementation Plan: D1 应收票据披露表 ↔ 附注模板对齐

## Overview

三层同时对齐：底稿两版披露表（上市/国企）→ 同步载荷 `columns` → 附注模板 §五、4 / §八、4。

先逐格读源模板 `backend/wp_templates/D/D1 应收票据.xlsx` 的两个披露 sheet 并用
`note_check_preset_formulas.json` 的 `F4-*` 裁决冲突；再以幂等脚本修订附注模板
（26 张表补 `columns` / `guidance` / 两级表头 / 行骨架）；然后改同步载荷列契约；
最后改两版底稿 UI（上市补出源模板 R76~R89 完全缺失的「组合计提项目」两张双期录入表）。

## Task Dependency Graph

```
1 (源模板核查/裁决)
   ├──> 2 (附注模板幂等修订) ──┐
   │                            ├──> 4 (同步载荷契约) ──┐
   └──> 3 (后端结构守卫) ───────┘                        ├──> 7 (测试与回归)
                                     ├──> 5 (composable) ┤
                                     └──> 6 (底稿 UI) ───┘
                                                              └──> 8 (浏览器实测)
```

- `1` 阻塞全部（列结构裁决结果是其余任务的输入）
- `3` 依赖 `2`（守卫锁死修订结果）
- `4` 依赖 `2`（子表名/列键/headers 需与模板逐字一致）
- `5`/`6` 依赖 `4`（snapshot 字段随载荷形状调整）
- `7` 依赖 `2`~`6`（契约测试同时读附注模板与同步载荷）
- `8` 依赖 `7`（活体验证结构对齐 + 同步落库 + 附注渲染）

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1"], "desc": "源模板逐格核查与三源冲突裁决" },
    { "wave": 1, "tasks": ["2", "3"], "desc": "附注模板幂等修订 + 后端结构守卫", "depends_on": [0] },
    { "wave": 2, "tasks": ["4"], "desc": "同步载荷列契约（group/flat 表态）", "depends_on": [1] },
    { "wave": 3, "tasks": ["5", "6"], "desc": "底稿 composable + 两版 UI", "depends_on": [2] },
    { "wave": 4, "tasks": ["7"], "desc": "契约与回归测试", "depends_on": [3] },
    { "wave": 5, "tasks": ["8"], "desc": "浏览器实测（底稿→同步→落库→附注渲染）", "depends_on": [4] }
  ]
}
```

## Tasks

- [x] 1. 源模板核查与三源冲突裁决
  - [x] 1.1 `diagnose_disclosure_sheet_vs_template.py --cycle D1` 产出小节切分与模板现状
  - [x] 1.2 openpyxl 逐格读 `附注披露信息（上市公司）`（A1:N119）/ `附注披露信息（国企）`
        （A1:P89），含合并单元格与红字提示
  - [x] 1.3 读 `note_check_preset_formulas.json` 的 `F4-1`~`F4-30`（listed/soe 双份）裁决冲突
  - [x] 1.4 裁决记录：子列名取预设（账面余额/坏账准备/账面价值）、父表头取源模板期间名；
        `F4-7` 的「+ 其他变动」不采纳（源模板 B100/G48 是减）；上市核销第 2 列取预设
        「应收票据性质」
        _Requirements: R1, R3_
- [x] 2. 附注模板修订（R1）
  - [x] 2.1 新增幂等脚本 `backend/scripts/fix/fix_note_d1_notes_receivable_structure.py`
        （`--dry-run` / `--check` / `--variant` / `_aligned_by`）
  - [x] 2.2 26 张表补 `columns` 并在 `group` / `flat` 之间明确表态
  - [x] 2.3 两级表头 9 张表派生 `_column_groups`；单级表头显式删除残留分组
  - [x] 2.4 `headers` 改为各列叶子 label（父表头由 `_column_groups` 承载）
  - [x] 2.5 26 张表补 `guidance`（仅源模板红字 / 附注括注 / 「勾稽：」前缀的 `F4-*`）
  - [x] 2.6 删占位假数据行（可无限量添加行 / 出票人类型或账龄 / ……），改空白录入行骨架
  - [x] 2.7 转应收账款表只留「商业承兑票据」；质押/背书用「票据」、主表用「汇票」
  - [x] 2.8 执行脚本写入两个 JSON（94 处变更 / 0 问题），`--check` exit 0，二次运行幂等
        _Requirements: R1.1, R1.2, R1.3, R1.4_
- [x] 3. 后端结构守卫（R4.2）
  - [x] 3.1 新增 `backend/tests/test_note_d1_structure.py`（189 测试：表名齐备唯一 /
        columns 表态 / `group` 无 `/` / `_column_groups` 自洽 / guidance ≥20 字 /
        无 `header_label` 与占位行 / 关键表父表头名 / 国企累计已计提为 amount）
  - [x] 3.2 `governance-checks.yml` 增 job `note-d1-structure`
        _Requirements: R1.4, R4.2_
- [x] 4. 同步载荷列契约（R3）
  - [x] 4.1 `summaryColumns(groupEnd, groupPrior)`：国企 期末数/期初数、上市 期末余额/上年年末余额
  - [x] 4.2 `classColumnsListed(group)` 按期间分组；`CLASS_COLUMNS_SOE` 改
        账面余额{金额,比例(%)} / 坏账准备{金额,预期信用损失率(%)} / 账面价值 独立列
  - [x] 4.3 `PORTFOLIO_COLUMNS_LISTED` group 改 期末余额/上年年末余额；
        `MOVEMENT_COLUMNS_SOE` 加 group 本期变动情况
  - [x] 4.4 单期 / 拆表双期 8 张表显式 `flat`
  - [x] 4.5 国企转回表 `cumulative_provision` 改 `amount` 并取 `cumulativeProvision`，进合计行
  - [x] 4.6 抽 `d1ColumnsFor(variant)` 为列头单一真源；导出零参
        `buildD1ListedColumns()` / `buildD1SoeColumns()` + `D1_LISTED_SUBTABLE` / `D1_SOE_SUBTABLE`
        _Requirements: R3.1, R3.2, R3.3, R3.4, R4.1_
- [x] 5. 底稿 composable（R2）
  - [x] 5.1 `defaultTransferRows` 只留「商业承兑票据」
  - [x] 5.2 质押/背书固定行名 汇票 → 票据
  - [x] 5.3 `ReversalDetailRow` 加 `cumulativeProvision`（`loadReversalRows` 含 legacy 数值迁移）
  - [x] 5.4 新增 `addPortfolioPairRow` / `renamePortfolioPair` /
        `fillPortfolioAgingBandsPair` / `removePortfolioPairRow`（双期成对对齐）
        _Requirements: R2.1, R2.3, R2.4, R2.6_
- [x] 6. 底稿披露表 UI（R2）
  - [x] 6.1 上市分类表加父表头 期末余额 / 上年年末余额；账面余额→金额、损失率(%)→预期信用损失率(%)
  - [x] 6.2 上市分类表加「计提依据」独立审计列（仅单项明细行可编辑，tooltip 标注去向）
  - [x] 6.3 上市新增「（4.3）按组合计提坏账准备」两张双期并列录入表
        （账龄段点选 + 成对生成 + `ElMessageBox.prompt` 命名后新增 + 删除 + 方法论上下文）
  - [x] 6.4 上市质押/背书/转应收表头改「种类」、金额列补「期末」前缀；转应收两版都可增删行
  - [x] 6.5 国企组合小计行名加「小计：」（`SOE_PORTFOLIO_SUBTOTAL` 常量）
  - [x] 6.6 国企转回表列名「转回或收回原因、方式」+ 累计已计提改金额输入并进合计
  - [x] 6.7 补漏：上市转回表「原确定坏账准备的依据」（原多「金额」）、
        核销逐项表末列按变体（国企「是否由关联交易产生」）
        _Requirements: R2.1, R2.2, R2.3, R2.4, R2.5, R2.6, R3.1_
- [x] 7. 契约与回归测试（R4.1）
  - [x] 7.1 新增 `d1NoteSubtableContract.spec.ts`：共享 helper 5 条 Property +
        D1 专属（group 无 `/` / 模板表名全集双向一致 / headers 逐位一致 /
        分组分段与 `_column_groups` 同口径）—— 50 测试全绿
  - [x] 7.2 更新 `d1NoteSectionMap.spec.ts`（国企主表 group、转回表数值列与合计）
  - [x] 7.3 `disclosureColumnsCoverage.spec.ts` 登记 D1 两个 builder 的 `P1_ROUTE`
  - [x] 7.4 D1 相关 23 文件 334 测试全绿；后端 189 全绿；Vite transform 200
        _Requirements: R4.1, R4.2_
- [x] 8. 浏览器实测（R4.3）
  - [x] 8.1 上市 Tab 12 表渲染核验（主表两级 / 分类表两级 + 计提依据 /
        新增组合计提两张双期表 / 种类·期末xx金额 / 转应收单行）
  - [x] 8.2 国企 Tab 12 表渲染核验（期末数·期初数 / 分类表三级 / 小计： /
        本期变动情况 / 转回表新列 / 转应收单行）
  - [x] 8.3 国企侧录入 → 「同步到附注」：已同步 28 行到「八、4 应收票据」
  - [x] 8.4 只读 SQL 验落库：`_source=workpaper`、
        `_last_sync_sheet=附注披露信息（国企）`、12 子表 + 12 组 columns，表名与分组逐字正确
  - [x] 8.5 附注端渲染核验：混合分组 `类别 | 账面余额{金额,比例(%)} |
        坏账准备{金额,预期信用损失率(%)} | 账面价值` 正确；变动表
        `类别:rs2 | 期初数:rs2 | 本期变动情况:cs4 | 期末数:rs2` 精确，列无错位
        _Requirements: R4.3_

## Notes

实测项目：「重庆医药集团宜宾医药有限公司新健康大药房临港店_2025」
（project `c8621493-70aa-46a9-8285-e0674e4e1418`，wp `cf1df7cb-3c04-4769-acbc-8aeb9735c13f`）。

交付边界：模板 JSON 修订只对 **新建项目 / 重新生成附注**（seed 路径）生效；
既有项目的 `_tables` 是生成时快照，靠底稿「同步到附注」整表覆盖（实测已验证）。

### 实测暴露的既有缺陷（非本 spec 引入，待定优先级）

- **P0-a** 国企分类表「按组合计提坏账准备」行预期信用损失率恒为 `-`：
  `D1TabDisclosure.soeClassEndRows/soeClassPriorRows` 的 `lossRate: 0` 硬编码，
  已随同步进入附注。按 `F4-12` 应 = 坏账准备 ÷ 账面余额 × 100。
- **P0-b** 比例(%) 列漂移：实测「按组合计提坏账准备」行显示 **162.50%**（应 100.00%）。
  两处叠加 —— `useD1Disclosure.updateCell('classEnd')` 用**编辑前**合计做分母且只重算
  被编辑行；`soeClassEndRows` 又把 bank.ratio + commercial.ratio 相加（分母不同期）。
  按 `F4-25` 每行比例 = 该行账面余额 ÷ 合计行账面余额 × 100。
- **P0-c** D1 的 AI 按钮全部空转（披露 5 + 审定表 2）：前端发 `section`/`context`，
  后端 `AiGenerateRequest` 要 `section_id`/`related_data`/`existing_content` → 422；
  且响应读 `res.data.text` 而后端返回 `generated_text`。正解见 `useReviewDialog.ts`。
  该端点 prompt 亦无 D1 披露口径与「不得虚构」约束。
- **P1-d** 「校对附注」误报：`pickNoteTotal` 取到「期末已质押的应收票据」合计 80000，
  与「本页期末合计 0」比较 → 提示「不一致（差异 80000）」，纯误报。应按表名定位主表。
- **P1-e** `D1TabDisclosure` 是 D1 唯一不走平台 `fmtAmount()` 的 Tab（其余 15 个都走）。
- **P1-f** `_d1_disclosure_export.py` 未覆盖「组合计提项目」明细与国企累计已计提列；
  列名仍是旧措辞（`终止确认金额`）、`预期信用损失率（%）` 全角括号与附注半角不一致。
- **P1-g** 无披露内部勾稽面板（D1 有 30 条 `F4-*` 预设，H1/N1 已有范式可复用）。
- **P1-h** 国企变动表「其中：」下无法新增明细行 → `F4-20` 勾稽永远无法满足。
- **P1-i** 无附件上传 / OCR（核销程序、质押、背书贴现需证据支撑）。
- **P2-j** 上市主表在审定表 D1-1 未加载时恒 0 且无手工兜底（国企有
  `importedTopSummaryRows` 回退）；实测主表全为 `-`。
- **P2-k** `writeOffAmount` 与变动表「本期核销」无联动校验（guidance 已写明应一致）。

## 第二阶段任务（既有缺陷修复）

```json
{
  "waves": [
    { "wave": 6, "tasks": ["9", "10"], "desc": "P0：派生列推导 + AI 契约", "depends_on": [5] },
    { "wave": 7, "tasks": ["11", "12", "13"], "desc": "P1：校对附注 / 金额格式 / 其中明细", "depends_on": [6] },
    { "wave": 8, "tasks": ["14", "15"], "desc": "P1：勾稽面板 / 附件", "depends_on": [7] },
    { "wave": 9, "tasks": ["16"], "desc": "P1：导入导出覆盖", "depends_on": [8] },
    { "wave": 10, "tasks": ["17"], "desc": "测试与 CI", "depends_on": [9] }
  ]
}
```

- [x] 9. P0：坏账分类表派生列改为读时推导（R5）
  - [x] 9.1 `useD1FormulaEngine` 新增纯函数 `deriveClassRow` / `deriveClassRows` / `ratioOf`
        （口径 F4-25 / F4-12 / F4-11）
  - [x] 9.2 `useD1Disclosure` 拆 `classEndRowsRaw` / `classPriorRowsRaw`（只持久化录入列）
        + 对外 computed 推导；`updateCell('classEnd'/'classPrior')` 不再算派生列
  - [x] 9.3 组件层 `soeClassEndRows` / `soeClassPriorRows` 抽 `buildSoeClassRows`，
        聚合行按聚合金额重算（删掉 bank.ratio + commercial.ratio 相加与 `lossRate: 0`）
  - [x] 9.4 `buildBadDebtRows` / `soeAgingRows` / 上市组合表视图与合计统一走 `ratioOf`
        _Requirements: R5.1, R5.2, R5.3, R5.4, R5.5_
- [x] 10. P0：AI 调用契约与专属 prompt（R6）
  - [x] 10.1 `D1TabDisclosure.handleAiGenerate` 改 `{section_id, related_data, existing_content}`
        + 读 `generated_text`
  - [x] 10.2 `useD1Adjudication` 抽 `aiGenerate(sectionId)`，两个按钮走同一契约
  - [x] 10.3 后端 `review_dialog` 新增 `_SECTION_PROMPTS` + `resolve_review_ai_prompt`
        （12 条 D1 专属 prompt，未登记回退通用 → 存量零回归）
  - [x] 10.4 守卫 `test_review_dialog_section_prompts.py`（40 测试）：从前端源码抽
        `section_id` 并按 `NOTE_SECTION_KEYS` 自动展开、每条 prompt ≥20 字含不得虚构、
        禁 `section:` 字段名、必须读 `generated_text`
        _Requirements: R6.1, R6.2, R6.3_
- [x] 11. P1：校对附注按表名定位（R7）
  - [x] 11.1 导出 `D1_MAIN_SUBTABLE`；`pickNoteTotal` → `pickNoteMainBookValue`
        （按表名 + `end_book_value` 列下标定位）
  - [x] 11.2 本页主表未取数时提示「本页主表未取数」，不报数据不一致
        _Requirements: R7.1, R7.2_
- [x] 12. P1：金额格式走平台单一真源（R8）
        `DisplayPrefs_Key` inject + `useDisplayPrefsStore` 兜底，`fmtAmt` 改调
        `displayPrefs.fmtAmount`，补 `.negative-amount` 样式（与 D1 其余 15 个 Tab 同款）
        _Requirements: R8.1_
- [x] 13. P1：国企变动表「其中：」明细可录（R9）
  - [x] 13.1 composable 加 `movementDetailRows` / `movementDetailTotal` /
        `hasMovementDetail` / `addMovementDetailRow` / `removeMovementDetailRow`
        + `updateCell('movementDetail')`（期末数按公式推导）
  - [x] 13.2 `soeMovementRowsForDisplay` 插入明细行；有明细时「按组合计提」行改为
        明细汇总只读；合计行按 单项 + 组合 现算（F4-19）
  - [x] 13.3 模板：4 个变动列改 `v-for` 常量表、期末数列头加公式 tooltip、
        新增/删除明细行（`ElMessageBox.prompt` 命名）
        _Requirements: R9.1, R9.2, R9.3_
- [x] 14. P1：披露内部勾稽面板（R10）
  - [x] 14.1 新建 `d1DisclosureConsistency.ts`（纯函数，覆盖 F4-3/3a/4/5/6/7/8/9/10/
        11/12/19/20/21/22/23/24，容差 0.01 元 / 1e-4 比率，两侧无数据 → skip）
  - [x] 14.2 新建 `D1DisclosureConsistencyPanel.vue`（紧凑 bar + 折叠明细 +
        规则 tooltip + `GtIndexChip` 追溯）
  - [x] 14.3 接进 `D1TabDisclosure`（入参与同步 snapshot 同源）
        _Requirements: R10.1, R10.2, R10.3_
- [x] 15. P1：关键披露项附件（R11）
        新建 `D1SheetAttachments.vue` 复用平台 `ItemAttachment`（不新建后端），
        挂在质押 / 背书贴现 / 核销三处，`sheetKey` 按 `D1-disc-{variant}-{section}` 隔离
        _Requirements: R11.1, R11.2_
- [x] 16. P1：导入导出覆盖全部录入面（R12）
  - [x] 16.1 列名归一（种类 / 期末xx金额 / 半角 `(%)` / 应收票据性质 /
        原确定坏账准备的依据）+ `SECTION_COLUMNS_OVERRIDE` 变体覆盖表 + `_cols()`
  - [x] 16.2 多层表头第 2 行改由 `_cols` 派生（`_multi_header`），防表头与列定义漂移
  - [x] 16.3 新增区块：`portfolioBank` / `portfolioCommercial`（上市双期 / 国企单期）、
        国企 `movementDetail`、国企变动主表横排 7 列、国企转回表累计已计提金额列
  - [x] 16.4 修既有缺陷：`merge_cells("A1:A2")` 清空 A2 → `_header_cells` 回退第 1 行，
        否则**导入自家导出的模板必然报「缺少列」**
  - [x] 16.5 填写说明补新增区块与「派生列由系统推导」提示
        _Requirements: R12.1, R12.2_
- [x] 17. 测试与 CI
  - [x] 17.1 `d1DisclosureConsistency.spec.ts`（23 测试，含 162.50% 与 `lossRate:0` 回归锁）
  - [x] 17.2 `test_d1_disclosure_export_columns.py`（32 测试：往返自检 + 读 `.ts` 源码比对
        列名 + 覆盖面 + 数据往返值不丢）
  - [x] 17.3 CI job `d1-disclosure-hardening`（AI prompt 守卫 + 导入导出列契约）
  - [x] 17.4 回归：后端 261 绿；前端 D1 相关 25 文件 373 绿 + 勾稽 23 绿；
        4 个新增/改动前端文件 Vite transform 200
        _Requirements: R12.3, R4.1, R4.2_
- [x] 18. P0（实测新发现）：防抖累积批次未按 item_id 去重 → 整批被拒、数据静默丢失
  - [x] 18.1 实测证据：连改商承/银承的账面余额与坏账准备共 4 次 →
        4 条 `D1-disc-soe-class-end-rows` 同批提交 → 库里**根本没有该键**
        （界面有值，`catch {}` 静默吞掉）
  - [x] 18.2 `D1TabDisclosure` 加 `dedupeByItemId`（后写覆盖先写）+ 保存失败给用户提示
  - [x] 18.3 守卫 `disclosureSaveBatchDedupe.spec.ts`（扫全部披露源码的防抖累积器形状）
  - [x] 18.4 守卫抓出同缺陷的 `D4TabDisclosureListed` / `D4TabDisclosureSoe`，一并修
        _Requirements: 平台铁律「同一批次不得重复提交相同 item_id」_
- [x] 19. 第二阶段浏览器实测
  - [x] 19.1 复刻上次导致 162.50% 的操作序列 → 比例 **100.00%**、
        预期信用损失率 **1.63%**（原 0.00%）、组合表合计行损失率 1.63%（原硬编码 0）
  - [x] 19.2 只读 SQL 验落库：`class-end-rows` 已写入（去重修复前该键完全缺失）
  - [x] 19.3 同步到附注 28 行；附注 八、4 分类表「按组合计提坏账准备」行
        `比例(%)=100`、`预期信用损失率(%)=1.625`（原 162.5 / 0）
  - [x] 19.4 校对附注不再误报：提示「本页「应收票据分类」未取数（审定表 D1-1 数据未加载）」
        （原误报「附注现存合计 80000 与本页期末合计 0 不一致」）
  - [x] 19.5 勾稽面板：通过 7 / 异常 5 / 未取数 27，5 项异常全部诊断正确
        （①合计因审定表未取数 ≠ ②分类表 3 项 + ②组合行 ≠ ④明细小计 2 项）
  - [x] 19.6 三处附件入口渲染正常（质押 / 背书贴现 / 核销）
  - [x] 19.7 「其中：」明细行交互 **已浏览器实测**（见 28.3）：`ElMessageBox.prompt` 输名 →
        明细行插在「其中：」下 → 「按组合计提」行输入框 5 → 0 转只读汇总（F4-20）→
        删除后回落可录（5）；库里 `movement-detail-rows` 回到 `[]`。
        导入导出往返由 `test_d1_disclosure_export_columns.py` 32 测试覆盖（含往返自检）；
        实时 AI 出文本依赖 vLLM 可用性属环境因素，改由
        `test_review_dialog_section_prompts.py` 守 prompt 契约
      _Requirements: R5, R6, R7, R9, R10, R11, R12_

## 第三阶段任务（复盘 P1 三项）

```json
{
  "waves": [
    { "wave": 11, "tasks": ["20", "21", "22"], "desc": "复盘 P1 三项（互不相干，可并行）", "depends_on": [10] }
  ]
}
```

- [x] 20. `text_sections` 裸表名不得当披露正文渲染
  - [x] 20.1 证据：后端 `_is_table_title_paragraph` 只认 ① `#` 开头 ② 非 `#` 时 ≤20 字且匹配
        `（N）xxx`/`N. xxx`。五、4 有 3 条、八、4 有 3 条裸表名 → 落进 `text_content`，
        附注正文与 Word 导出凭空多出「只有一个表名」的段落
  - [x] 20.2 幂等脚本加 `titleize_text_sections`（裸表名 → `#### ` 前缀）+
        `find_bare_table_name_paragraphs`（供 validate / 测试）；6 处已修，`--check` exit 0
  - [x] 20.3 守卫 4 条（无裸表名 / 表名段落用 `#### ` / titleize 幂等 /
        复刻判定与后端 `_is_table_title_paragraph` 逐样本一致）
        _Requirements: 交付物正确性（附注正文与 Word 导出）_
- [x] 21. 补 `transfer` / `badDebtMovement` 两个说明文本域
  - [x] 21.1 `NOTE_SECTION_KEYS` 5 → 7（`categorySummary` 与顶部汇总表共用 `top`）
  - [x] 21.2 UI 补三处文本域：上市/国企 transfer 段（源模板 R27 括注要求披露终止确认金额及
        相关利得损失）、国企 badDebtMovement 段（R43/R90 要求说明按组合计提原因）、
        国企主表段（共用 `top`，含编制提示）；各带 🤖 AI + 💬 复核
  - [x] 21.3 `buildAiContext` 补 transfer / badDebtMovement 两段上下文（含「其中：」明细）
  - [x] 21.4 `NOTE_TITLES` + 导出 `D1_NOTE_TEXT_ORDER`（7 段，按源模板小节顺序）
  - [x] 21.5 后端补 2 条专属 prompt；`_D1_DISCLOSURE_KEYS` 5 → 7
  - [x] 21.6 守卫 `d1NoteTextSections.spec.ts`（9 测试：从源码抽三处键集交叉校验 —— 
        sectionOrder ⊆ 文本域键集、键集 ≡ `D1_NOTE_TEXT_ORDER`、标题表无缺无余、
        每键都有 `onNoteChange` 绑定与 AI 按钮）
        _Requirements: 附注 `text_content` 完整性_
- [x] 22. 主表手工兜底（两个变体一致）
  - [x] 22.1 `categorySummaryRows` 回退分支去掉 `variant === 'soe'` 门
        （旧实现让上市侧在审定表未加载时恒 0，且导入的 topSummary 对上市不生效）
  - [x] 22.2 新增 `canEditCategorySummary`（审定表未取数时为真）+
        `updateCell('categorySummary')` 写 `top-summary-rows`（与导入同一持久化键，不造第二真源），
        账面价值按「账面余额 − 坏账准备」推导
  - [x] 22.3 UI 抽 `MAIN_TABLE_GROUPS`（父表头随变体：上市 期末余额/上年年末余额、
        国企 期末数/期初数），两版主表共用一份模板；可录时渲染 `el-input-number` +
        琥珀色提示条，取到数后自动转只读
  - [x] 22.4 守卫 9 测试（含「上市回退不再被 variant 门死」回归锁、审定表优先、
        只读时拒绝录入）
        _Requirements: 上市侧可用性_
- [x] 23. 第三阶段回归
      后端 280 绿（3 文件）；前端 35 文件 574 绿；3 个改动文件 Vite transform 200

## 第四阶段任务（复盘 P2 三项）

```json
{
  "waves": [
    { "wave": 12, "tasks": ["24", "25", "26"], "desc": "复盘 P2 三项（互不相干，可并行）", "depends_on": [11] },
    { "wave": 13, "tasks": ["27"], "desc": "第四阶段回归与 CI", "depends_on": [12] },
    { "wave": 14, "tasks": ["28"], "desc": "第四阶段浏览器实测", "depends_on": [13] }
  ]
}
```

- [x] 24. 勾稽差异一键推送 A13 错报汇总
  - [x] 24.1 `d1DisclosureConsistency.ts` 加 `D1_ACCOUNT_CODE='1121'` / `D1_ACCOUNT_NAME='应收票据'` /
        `buildD1MisstatementPayload(summary, { checkIds? })`：只推 `level==='error'` 且
        `|diff| > 容差` 的项，形态 A `{ items: [...] }`（与平台桥 `useA13MisstatementBridge` 同构）
  - [x] 24.2 `D1DisclosureConsistencyPanel.vue`：bar 上「推送 N 项差异至错报汇总」批量按钮 +
        明细表「错报」列单行推送按钮 + `canPush()`（只读态 / 非 error / 差异为 0 时禁用）
  - [x] 24.3 `eventBus.emit('a13:push-misstatement')`；`D1TabDisclosure.vue` 透传 `:is-readonly`
  - [x] 24.4 守卫：`d1DisclosureConsistency.spec.ts` 追加 10 测试
        （含用平台 `normalizeMisstatementPushPayload` 反验载荷可被 A13 侧解析）
        _Requirements: 勾稽结论回写链路（平台铁律「结论/缺陷/偏差回写」）_
- [x] 25. 可编辑金额迁 `WpAmountInput`（千分符）
  - [x] 25.1 `D1TabDisclosure.vue` 32 处 `el-input-number` → `WpAmountInput`
        （脚本批量 31 处 + 手工 1 处上市变动表 `row.value`），残留 0
  - [x] 25.2 补齐每处 `:disabled` 与 `:aria-label`（主表两处手工兜底输入原缺）
  - [x] 25.3 守卫 `d1/__tests__/d1AmountInputMigration.spec.ts`（7 测试）：无 `el-input-number` /
        已引入并使用 / 禁 `:formatter`（EP 2.13.6 无此 prop，是空操作）/ 每处都有
        change + disabled + 值绑定 / 无 `?? 0`（会把空值写成 0）/
        **反向边界：比例、预期信用损失率、账龄天数等非金额不得套用** / 比率列仍只读
        _Requirements: 平台铁律「可编辑金额千分符只能用 el-input」_
- [x] 26. 两级表头的 Word 导出结构验证
  - [x] 26.1 核实 `note_word_exporter._build_two_level_header_rows` 已支持**混合分组**
        （独立列 rowspan=2、row1 只放分组子列名不补占位）
  - [x] 26.2 `backend/tests/services/test_note_word_export_d1.py`（45 测试）：
        参数化跑 D1 全部 9 张两级表头表（row0 colspan 之和 == 总列数 / row1 长度 == 分组列数
        且无空子列名 / 独立列 rowspan=2 / 分组名 colspan 与 span 一致）+
        6 张表逐表钉死结构 + flat 表不得有 `_column_groups`
  - [x] 26.3 挂进 CI job `d1-disclosure-hardening`
        _Requirements: 交付物正确性（Word 导出）_
- [x] 27. 第四阶段回归
  - [x] 27.1 后端 325 绿（4 文件，含新增 Word 导出 45）
  - [x] 27.2 前端 D1 相关全绿；5 个改动/新增前端文件 Vite transform 200
  - [x] 27.3 顺带修 `useD1FormulaEngine.spec.ts` 的 PBT 生成器越界：
        `fc.float({ noNaN: true })` 仍会生成 ±Infinity（seed 1139061718 命中
        `calcChangeRate(-Infinity, 0)` → NaN），三处无界生成器统一收敛到金额域 `AMOUNT`；
        同时 `parseNum` 加 `Number.isFinite` 守卫（`parseFloat('Infinity')` / `'1e400'`
        能过 `isNaN` 检查，漏进公式会让整表变 NaN）+ 7 条边界断言
  - [ ] 27.4* `disclosureColumnsCoverage.spec.ts` 2 失败**不属本 spec**：
        `buildK8~K13*Columns` 与 `buildPlColumns`（`kPlDisclosureShared.ts`，未跟踪的新文件）
        为并发会话在飞改动，缺 `P1_ROUTE` 登记且列 label 为空 —— 由其所属 spec 收口
- [x] 28. 第四阶段浏览器实测（chrome-devtools MCP + postgres 只读；项目 `2aa00f57`、
      底稿 `fd3433f4`、国企披露 Tab）
  - [x] 28.1 P2-2 千分符：主表期末坏账准备录 `1234567.5` → 失焦显示 **`1,234,567.50`**；
        `el-input-number` 计数 **0**、`el-input` 30 个；账面价值推导为 `(1,234,567.50)`
        （负值括号），落库 `D1-disc-soe-top-summary-rows` 证明 Task 22 手工兜底持久化通
  - [x] 28.2 P2-1 推送 A13：录入后勾稽 bar 由「暂无可比对数据」变
        「勾稽异常 3 项 · 通过 3 · 未取数 33」并出现「推送 3 项差异至错报汇总」；
        明细表新增「错报」列（3 个「推送错报」，通过项显示「—」）；点单行推送 → toast
        「已记入未更正错报汇总 1 笔」→ **库中 `unadjusted_misstatements` 落一条**：
        `affected_account_code=1121` / `应收票据` / `1234567.50` / `factual` /
        `source_wp_code=D1`，描述含规则 `F4-9` 与索引 `D1-1/D1-4`
  - [x] 28.3 「其中：」明细行：prompt 输名 → 行插入「其中：」下 →
        「按组合计提」行 5 输入框转 0（只读汇总）→ 删除后回落 5
  - [x] 28.4 实测数据已复原：错报记录经 `DELETE /misstatements/{id}` 删除（live=0）、
        金额改回 0、明细行删除（`movement-detail-rows` = `[]`）
        _Requirements: R10.3, 平台铁律「改动后必浏览器实测」_

## 遗留（须单独立 spec）

- **披露 Tab 完全无 `applicable_standards` 门控**：`sync_from_workpaper` 的定位键只有
  `(project_id, year, note_section)`，`current_standard` 不参与匹配 → 在国企项目上编辑上市
  披露 Tab 会把数据写进 `五、4`（该编号对国企项目是另一套科目）。根因是平台级
  `applicable_standards` 前端全链缺失（`/api/projects/{id}` 不返回、`useWpRenderSchema` 写
  `undefined`、`normalizeApplicableStandards` 不认 `{entity_type, scope}`），影响
  F1/F2/F3/D1/D3/D5/G\*/I\*/K\* 等全部 gating 循环，属跨前后端 schema 变更。
