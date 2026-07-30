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
