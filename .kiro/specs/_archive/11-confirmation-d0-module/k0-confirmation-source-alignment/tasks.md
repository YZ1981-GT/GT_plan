# Implementation Plan: K0 管理循环函证源模板对齐

## Overview

4 个 wave、18 项任务。

**开工前必读**：K0 既有实现度**高于立项预估** —— 9 个 sheet 的 componentType 全部登记、后端三个策略齐备、K0-5/K0-6 借贷拆表已实现、四区块已在 `alternativeBlockManifest.ts` 登记 `sourceExtra` 依据、K0-8 的 19 条舞弊迹象已按源模板逐字锁死（后端守卫在册）。本 spec **不重做**这些，只补五类真缺口。凡本文件写「补」「改」的地方，落手前**先 grep 一次**确认还没被并发会话做掉。

**🔴 并发约束（Wave 3 的硬前置）**：

| 并发 spec | 状态（2026-08-04 扫描） | 重叠文件 |
|---|---|---|
| `f0-confirmation-linkage-and-structural-enhancement` | 28/31，`inprog=1 queued=2`，tasks.md mtime 08-03 23:35 | `GtConfirmationSummary.vue`、`f0SummaryAggregation.ts`、`f0MatrixDataSources.ts` |
| `g0-confirmation-source-alignment` | 仅 requirements.md（mtime 08-03 23:48），同族且同样计划泛化矩阵 | `confirmationColumnSpec.ts`、`cycleConfirmationMeta.ts`、`GtConfirmationSummary.vue`、`memoTemplates.ts`、`ReliabilityGrid.vue` |

**Wave 1/2 不碰共享件，可立即开工。Wave 3 开工前必须重新扫一次两个并发 spec 的 tasks.md**；若 F0 仍有 `[-]`，只做 Wave 1/2。

**🔴 2026-08-04 已核实的平台现状（本 spec 据此定调，落手前仍需复查）**：

| 共享能力 | 现状 | 对 K0 的含义 |
|---|---|---|
| 品种矩阵 | 已有**三份**（`e0SummaryMatrix` 6×6 / `f0SummaryAggregation` 4×8 / `h0SummaryMatrix` 动态×8），H0 明确范式「复用 `safeRatio`/`sumByCategory`，常量各自声明」 | Task 8 **沿用范式新建**，不重构统一内核（半径覆盖四个 spec） |
| `CYCLE_COLUMN_LABEL_OVERRIDES` | **已存在**，含 `G0`/`H0` 两 key | Task 9 只增 `K0` 键，勿重建机制 |
| `CYCLE_COLUMN_GROUP_OVERRIDES` | 不存在 | Task 9 新建 |
| `send_channel` variant 列 | **已存在**（G0/H0 用，承载渠道 `邮寄/跟函/电子函证/其他`） | Task 9 给 K0 启用，勿重建 |
| `row_summary` 结论段 | 已存在（G0/H0 的 `*_row_conclusion` 在用），注释已指明 K0/L0 归属待修正 | Task 9 把 K0 的 `row_conclusion` 移入，不新建段 |
| 抽样结构化 | `ConfirmationSampling.vue` 已按 `isG0` 门控 + 字段映射 + 文案 import 自 `g0SummaryLowerZone` | Task 10 沿用同法加 `isK0` |
| `ReliabilityGrid.vue` 12 渠道字段 | 仍 **0 命中**（08-04 13:16 改过但未接） | Task 14 仍需做 |
| `GtConfirmationSummary.vue` 门控 | 已有 `isE0`/`isF0`/`isH0`/`isG0` | Task 10 加 `isK0`，与 `H0SummaryLowerZone.vue` 对称 |

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "源模板事实固化守卫（不碰生产代码）",
      "tasks": ["1", "2", "3"],
      "blocks": [2, 3, 4]
    },
    {
      "wave": 2,
      "name": "K0 专属件 + 后端数据（不碰共享件）",
      "tasks": ["4", "5", "6", "7"],
      "blocks": [3, 4]
    },
    {
      "wave": 3,
      "name": "共享件改造（须等 F0 spec 收口）",
      "tasks": ["8", "9", "10", "11", "12", "13", "14"],
      "blocks": [4]
    },
    {
      "wave": 4,
      "name": "收口与实测",
      "tasks": ["15", "16", "17", "18"],
      "blocks": []
    }
  ]
}
```

## Tasks

### Wave 1 — 源模板事实固化守卫

- [x] 1. 建 `backend/tests/test_k0_source_template_facts.py` — sheet 与目录层
  - openpyxl 直读 `backend/wp_templates/K/K0 管理循环函证.xlsx`
  - 断言 11 张 sheet、`GT_Custom` 为 `hidden`、其余 10 张 `visible`、名称逐字
  - 断言底稿目录 `D5:F13` 共 9 行、`F` 列索引号集合 `{K0A, K0-1..K0-8}`、`D` 列序号序列 `[1,2,3,4,5,7,8,9,10]`（序号 6 缺失的源模板事实）
  - 断言 `wp_code_overrides.json` 的 K0 条目覆盖 9 个索引号且无一为 `skip`
  - 反向自检：改一个 sheet 名/一个序号即打红
  - **注意**：读模板前先比对 `backend/wp_templates/` 与参考副本的 size；跳过 `~$` 锁文件（用户可能开着 WPS）
  - _Requirements: 1.1, 1.2, 6.3, 6.4_

- [x] 2. 扩 `test_k0_source_template_facts.py` — K0-1 / K0-2 / K0-4 / K0-7 / K0-8 / K0A 结构层
  - K0-1：R5 六段 + `AB5` 独立段、R6 **28** 个叶子列逐字、数据行 `r7:r26`、`VLOOKUP` 七列的目标列号 `{2,3,4,10,16,19,22}`、`T` 列 `IF(L="是",S-F,"未回函")`
  - K0-1 下区：四块锚点 `C27/I27/S27/C38`、品种列头 `E28/F28`、8 指标 `C29:C36` 逐字、三个 SUMIF 形态、三个 `IF(ISERROR(...),0,...)`、末行 `(E35+E32)/E29` **无 ISERROR**
  - K0-1 样本选择 6 项位于 `I28/I29/I30/I31/I33/I34`（`I32` 为空、`J32` 承载提示）
  - K0-1 审计说明 5 项位于 `S28/X28/S32/X32/S36`，第 2 项界定条件 = `X29`+`X30` 两格拼接
  - K0-1 编制说明：准则 1312 第十条 6 项、注意事项 8 条、参考结论 A/B/C、`A67` 后附审计证据、`A40` 提示
  - K0-2：38 列 5 段、`AF6:AK6` 六个叶子列逐字、DV 覆盖行区**非对称**（提供信息段到 24 行 / 回函与二次发函段到 26 行）、`L7:L24` 六项取值集合
  - K0-4：9 列、`r6:r20` 15 行、`F=D-E`、`r21` 三处 SUM
  - K0-7：14 列、`G5:M5` 父表头「期末未收回原件函证可靠性验证」、七个叶子列逐字、**无「回函日期」列**
  - K0-8：19 条 + `A25 ……` + `A26` 汇总行 `H26='B50'`、两条 tooltip 举例位于 `J19/J20`
  - K0A：12 条程序、D 列分类取值集合、E 列索引号逐字（含 `K0-1/K0-2//K0-4` 双斜杠事实）
  - 归一函数只做空白/全半角处理，**不做过度归一**；含反向自检
  - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.12, 1.14, 1.15, 1.16, 1.17_

- [x] 3. 扩 `test_k0_source_template_facts.py` — K0-3 / K0-5 / K0-6 结构层 + 笔误登记
  - K0-3：两套话术锚点（`A10:A13` / `A15:A17`）、电话回访段 `A18:A19`、事后补记 `A21`、3 控制点 `A23:A25`（DV `是,否`）、签名行 `A27`；断言 `A13`/`A17` 逐字含「工号为[XX]（如有）」
  - K0-5/K0-6：`A6` 样本选取 6 项、`A11:E11` 余额表 + `E12=B12+C12-D12`、**4 张检查表**锚点（`A14`/`A25`/`A37`/`A47`）、`A57`/`A61`、编制说明 3 条
  - 断言 K0-5 段① = `银行回单{日期,付款方,金额}` + `支持性文件1{识别特征,信息1,信息2}`；K0-6 段① = `付款审批单{日期/编号,是否经过恰当审批}` + `银行回单{日期,收款方,金额}`
  - 断言两侧段①对方当事人**不相等**（K0-5「付款方」/ K0-6「收款方」）
  - 登记源模板笔误 5 条（含 `K0-5!M46` 对索引号文本列求和、三处索引号笔误、目录跳号）为常量表，供前端守卫交叉引用
  - _Requirements: 1.11, 1.13, 6.1, 7.1, 7.5, 7.6_

### Wave 2 — K0 专属件 + 后端数据

- [x] 4. 建 `confirmation/k0-confirmation/k0MatrixSpec.ts`
  - `K0_MATRIX_CATEGORIES`：2 品种，各带 `sourceRef`（`函证结果汇总表K0-1!E28`/`!F28`）、`reportRowCode`（`BS-009`/`BS-050`）、`fallbackAccountCodes`、`amountHint`、`bookAmountFrom`（`K1`/`K3`）
  - `K0_MATRIX_METRIC_LABELS`：8 项逐字取自源 `C29:C36`
  - 注释写明：`BS-009` 是**净额口径**（`soe_standalone` 含 `− TB('1231-03') + TB('1131')`）；`BS-075` 是同名 NULL 行**必须按 row_code 匹配**；兜底码只作展示，运行态走 `four_table` 语义定位
  - _Requirements: 4.1, 4.2, 4.3, 4.5_

- [x] 5. 建 `confirmation/k0-confirmation/k0LowerZoneSpec.ts`
  - `K0_SAMPLE_SELECTION` 6 项：key **复用替代程序既有抽样字段族名**（先 grep `useAlternativeK05Data` 的 `sampling` 字段名，不新造）、label 逐字源 `I28..I34`、placeholder 逐字源 `J28..J34`
  - `K0_AUDIT_NOTES` 5 项：label 逐字源 `S28/X28/S32/X32/S36`；第 2 项 `inlineHint` = `X29`+`X30` 合并句（**不得半句结尾**）；`针对未回函的替代程序` 声明 `aliasOf: 'note_alternative'`
  - `K0_REFERENCE_CONCLUSIONS` A/B/C 逐字源 `A64:B66`
  - `K0_GUIDANCE_BLOCKS`：准则 1312 第十条 6 项 / 注意事项 8 条 / `A40` 提示 / `A67` 后附审计证据
  - `K0_INDEX_TYPO_MAP` 三条（literal/intended/note）
  - _Requirements: 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 6.1, 6.2_

- [x] 6. 建 `backend/scripts/fix/fix_k0_prefill_presets.py` + `backend/tests/test_k0_formula_presets.py`
  - K0 块 `sheet`：`审定表K0-1` → `函证结果汇总表K0-1`（源 xlsx 无前者）
  - `account_codes` 补其他应付款侧；`cells` 由审定表口径两格改为矩阵账面金额两格（`E29`/`F29`），公式按 `BS-009` 净额口径与 `BS-050` 口径
  - `--dry-run` / `--check` / `--apply` 三态 + 幂等 + round-trip 自检（`json.dumps` 不能逐字复现原文即 exit 非 0）
  - 校验器**只扫语义字段**（`formula`/`formula_type`/`account_codes`/`applies_when`），不扫 `description`/`notes`
  - 守卫：7 个函证循环的块 `sheet` 值必须存在于对应源 xlsx 可见 sheet 名集合；E0 的 `审定表E0-1` 登记白名单并写明归属 spec（白名单只许变短）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 7. 建 `confirmation/k0-confirmation/__tests__/k0MatrixSpec.spec.ts` 与 `k0LowerZoneSpec.spec.ts`
  - 读后端笔误常量表与源 xlsx JSON 化结构，交叉锁死品种 `sourceRef`、8 指标标签、5 项说明 label、三条笔误映射
  - 断言 `reportRowCode` 为 `BS-009`/`BS-050`（**不是 `BS-075`**）；断言 spec 中不含按 row_name 匹配的路径
  - 断言 `K0_SAMPLE_SELECTION` 的 key 全部出现在替代程序抽样字段族中（跨文件交叉锁死，防新造第二套字段名）
  - 断言 `aliasOf` 目标存在于 `NotesData`
  - 含反向自检（把 `intended` 改成 `literal`、把 `BS-050` 改成 `BS-075` 均须打红）
  - _Requirements: 4.6, 3.8, 6.4_

### Wave 3 — 共享件改造（开工前重扫并发 spec）

- [x] 8. 建 `confirmation/k0-confirmation/k0SummaryMatrix.ts`（沿用 H0 范式，**不重构三份矩阵**）
  - `import { safeRatio, sumByCategory } from '../composables/f0SummaryAggregation'` —— 只引用不修改
  - `K0_MATRIX_METRIC_LABELS`（8 项，源 `C29:C36` 逐字去尾冒号）+ `K0_MATRIX_METRIC_ANCHORS`（`['C29'..'C36']`）+ `K0_MATRIX_EDITABLE_METRIC_INDEX = 0`
  - `buildK0SummaryMatrix({ rows, bookAmounts, manualOverrides })` → `2 × 8` 矩阵；品种为**固定 2 个**（源 `E28`/`F28`，非 H0 那种动态可扩位）
  - 文件头写清与 F0/H0 的关系及「为何不统一内核」（重构半径覆盖 E0/F0/H0/G0 四 spec）
  - 黄金快照冻结 E0/F0/H0 三份矩阵改造前输出 + 断言三文件内容哈希不变；三侧既有 spec 断言**不改一个字**必须全绿
  - 🔴 本任务是 Wave 3 的第一个共享件任务 ⇒ 开工即 R11.1 的并发闸判定点（F0 spec 实测 144/144 且已归档 ⇒ 闸门已客观解除）
  - _Requirements: 3.2, 3.3, 3.4, 11.1, 11.2, 11.3_

- [x] 9. `confirmationColumnSpec.ts` — 撤伪列 + 对齐 G0/H0 处置（**两个机制已存在，只增 K0 声明**）
  - 删 `VARIANT_COLUMN_DEFS.send_memo`（伪列）；`row_conclusion` 的 `group` 由 `send_memo` 改 `row_summary`（现有注释已指明 K0/L0 归属待修正）
  - `CYCLE_VARIANT_COLUMNS.K0/L0`：`['send_memo','row_conclusion']` → `['send_channel','row_conclusion']`（`send_channel` 已由 G0/H0 建好，勿重建）
  - `CYCLE_EXCLUDED_COLUMNS.K0`（现 `[]`）：增 `contact_person`/`contact_phone`/`currency`（源模板无，它们在 K0-2 的 `F`/`G` 列），与 G0/H0 同款；只影响渲染，不删持久化值
  - `CYCLE_COLUMN_LABEL_OVERRIDES`（**已存在**，现含 `G0`/`H0`）：增 `K0` 键 —— 13 处 label + `confirmation_method` → 「函证类型（积极式/消极式）」（源外保留列，显式登记）
  - **新增** `CYCLE_COLUMN_GROUP_OVERRIDES`（现不存在）：K0 声明 6 处（`sample_purpose`/`entity_name`/`account_type`/`amount` → `send_memo` 段；`diff_ref_index`/`remark` → `reply_amount` 段）；默认缺省 ⇒ 未声明循环逐字节不变
  - `resolveConfirmationColumns` 合并 group 后套用 group override（label override 逻辑已在，勿重写）
  - **L0 同步生效**：K0/L0 共用 variant，须交叉锁死到 L0 源模板（若 L0 源模板用词不同则各自声明 override）
  - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 10. K0-1 下区渲染 `confirmation/k0-confirmation/K0SummaryLowerZone.vue` + 接入 `GtConfirmationSummary.vue`
  - 四个 `el-collapse-item`，标题逐字源模板；矩阵表格（品种为列、8 指标为行）+ 账面金额行可手工录入（手工优先）
  - 样本选择**不在本组件内实现**：沿用 G0 范式在 `ConfirmationSampling.vue` 加 `isK0` 门控 + 字段映射表复用既有 `sampling_*` 持久化字段，文案 import 自 `k0LowerZoneSpec`（组件内不抄第二份）；`J32`/`J36` 提示随项展示并标源模板锚点
  - 审计说明 5 项，每项配 AI 辅助 + `GtReviewTrigger`；`aliasOf` 项只读引用既有 `note_alternative` 不重复录入
  - 审计结论：A/B/C 一键套用 + textarea
  - 编制说明以 `details` 折叠置底
  - `GtConfirmationSummary.vue` 加 `isK0` 门控（与既有 `isE0`/`isF0`/`isH0`/`isG0` 同层，**不得插进 `v-if`/`v-else-if` 分发链中间**）；组件命名与 `H0SummaryLowerZone.vue` 对称
  - 🔴 金额一律 `displayPrefs.fmtAmount()`（setup 顶层 `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`）；可编辑金额用 `el-input`/`WpAmountInput`，**禁 `el-input-number :formatter`**
  - 未归类提示：`account_type` 不在两品种内的行数提示「不计入函证情况」
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.10, 3.11, 3.12_

- [x] 11. 账面金额取数 `confirmation/k0-confirmation/k0MatrixDataSources.ts`
  - 从 K1 / K3 render-config 既有出口取数（**不新建通路**）；缺失返 `undefined` 而非 0
  - 🔴 `@/utils/http`（返 AxiosResponse）与 `@/services/apiProxy`（返业务数据）形态不同，选错会静默取空 —— F0 spec 已踩过，落手前确认取哪一个
  - 错误记入 `diagnostics.errors`（不被静默吞掉），UI 提供「🔄 刷新取数」
  - 手工覆盖持久化到 `k0_matrix_overrides`
  - _Requirements: 4.2, 4.3, 4.4, 4.6_

- [x] 12. `send_memo` 既有值只读呈现 + `cycleConfirmationMeta.ts` 笔误登记
  - 撤列后若某行 `send_memo` 非空，在行详情以只读提示呈现并说明「源模板无此列，请改填对应分段内的具体列」
  - `cycleConfirmationMeta` 新增可选笔误说明字段（**落地字段名是 `SheetMeta.indexTypoNote`，不是立项写的 `indexTypoMap`** —— 笔误说明挂在 per-sheet 条目上比再建一张 map 少一层间接），K0 声明三条；其余循环缺省 `undefined` ⇒ 行为不变
  - 跨表跳转与 CrossRef 文案按 `intended` 目标（`K0-4`/`K0-7`/`K0-3`），tooltip 标源模板原值
  - _Requirements: 2.2, 6.1, 6.2_

- [x] 13. K0-5/K0-6 局部对齐 + K0-2 二次发函六列
  - `blockColumnConfigsK05.block1`：`receipt_payer` label「收款方」→「**付款方**」；补 `支持性文件1{识别特征,信息1,信息2}` 三列；银行回单日期列 label 回归源模板用词
  - 源模板红字「检查的关键证据和要素根据被审计单位具体情况修改」以琥珀块置于对应区块上方（K0-5/K0-6 各 3 处）
  - 编制说明内嵌 3 条替代程序要点
  - `entityVerifyTypes.ts` additive 六字段 + `EntityVerifyDetail.vue` 在 `is_second_send` 为真时展开、为假时折叠
    - 🔴 **落地字段名是 `second_entity_address`/`second_entity_zipcode`/`second_contact_person`/`second_contact_phone`/`second_fax`/`second_info_verified`**，不是立项写的 `second_send_*`/`second_info_match` —— 与该文件既有一次发函侧命名（`entity_*`/`contact_*`/`info_verified`）保持同一构词法，改成 `send_*` 会让同一张表出现两套构词
  - K0-2 五条编制说明作只读方法论上下文就地展示
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4_

- [x] 14. K0-7 渠道列渲染 + K0-3 通用话术补齐（共享件，全循环受益）
  - 🔴 **12 个渠道字段按「明确撤回」处置，不接线**（R9.1 的两个选项之一）—— 三条并列实证：①六份 visible 源模板（D0-7/F0-7/G0-7/H0-6/K0-7/L0-6）的可靠性表列集**逐字同构且都是 14 列，没有这 12 列** ②它们的原始出处是 E0 的 `邮件传真回函核对记录F1-12`，而该 sheet 是 `hidden` 且用户已于 2026-08-02 裁决「三张隐藏底稿不需要再实现」 ③全库 `parsed_data` 命中这 12 个字段名的行数为 **0**（删除不触碰数据零丢失红线）。⇒ 接线出来的录入位在**任何**循环的源模板上都不存在 = 自造底稿列。守卫 `reliability/__tests__/reliabilityChannelFieldsWithdrawal.spec.ts` 钉死「不得复活」
  - `ReliabilityGrid.vue`：`G:M` 七列加父表头「期末未收回原件函证可靠性验证」（走 `RELIABILITY_PARENT_HEADER` 常量，禁写字面量）
  - K0 侧列标签按源模板用词（走 `RELIABILITY_COLUMN_SOURCE_LABELS` 真源，逐字对后端 r5/r6）
  - 🔴 **「回函日期」不做按循环可见性控制**（R9.3 落地时被实证推翻）—— 六个枢纽源模板**全部**无该列 ⇒ 按循环分叉说不出哪个循环该显示，正确形态是**平台级源外保留列 + 显式登记 + UI tooltip 标注**（Property 24）
  - `memoTemplates.ts`：通用两段话术补工号占位；`LATER_FOLLOW_TPL` 补「确认其确实于〔visit_date〕接待跟函人员」核实要点；`getTemplate` 两种旧签名调用形态不变；E0 五段**逐字不变**
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3_

### Wave 4 — 收口与实测

- [x] 15. 建守卫 `k0ColumnAlignment.spec.ts` / `k0SummaryMatrix.spec.ts` / `k0LowerZone.spec.ts`
  - Property 2/3/4：28 列一一映射（含 `send_channel` 承载渠道、三列已剔除、`confirmation_method` 作显式登记源外保留列）+ 伪列已撤且字段保留 + D0/E0/F0/G0/H0 黄金快照逐字节不变
  - Property 5/6/7/8：矩阵 8 指标同构 + PBT 不产 NaN/Infinity（金额生成器**显式排除 `±Infinity`**，`fc.float({noNaN:true})` 不够）+ E0/F0/H0 三份矩阵内容哈希与输出快照不变 + row_code 精确匹配
  - Property 9/10/13：下区四键与既有键无交集 + 旧 payload 兼容 + 5 项说明逐字 + 笔误三条登记 → 落 `k0LowerZoneSpec.spec.ts`（守**声明真源**）
  - Property 22/23：`fmtAmount` 单一真源（setup 顶层 inject / 禁模块级命名导入 / 禁 `toLocaleString`）+ `el-input-number` 与 `:formatter` 计数 0 + `WpAmountInput` 受控形态 → 落 `k0LowerZone.spec.ts`（守**组件实现形态**）
    - 🔴 下区拆两个守卫文件：混在一个文件里会让「改声明」与「改渲染」的红信号混淆
    - 🔴 `DisplayPrefs_Key` **引入来源**已有平台级守卫 `components/workpaper/__tests__/displayPrefsKeyImportSource.spec.ts` 全量扫 `.vue` ⇒ 本文件只做一条「该守卫仍在」的交叉锁死，**不抄第二份扫描逻辑**（同一不变式两份判据 = 改一处另一处不红）
  - _Requirements: 2.7, 3.1, 3.4, 3.5, 3.12, 4.6, 11.3_

- [x] 16. 建守卫 `k0AlternativeBlocks.spec.ts` / `k0SharedComponentBoundary.spec.ts` + CI job
  - Property 14/15/16：段①对方当事人 label 必须不同（反向自检：统一即红）+ 支持性文件三列齐备 + 索引号列不参与求和 + `SOURCE_EXTRA_MANIFEST` 与 `splitByDirection` 登记不变
  - Property 17/18/19：二次发函六列 additive（对改造前字段名集合取差集，删除项与重命名项须为空）+ 12 个渠道字段**全部有 UI 消费方**（反向自检：删任一渲染点即红）+ 通用话术含两处占位且 E0 五段逐字不变
  - Property 20/21：本 spec 新建模块**零消费方即打红**（排除自身/`__tests__`/`components.d.ts`）+ 共享件受影响循环声明表完整
  - 登记 `RELIABILITY_COLUMN_CONFIG` 零消费方为已知死配置（平台级，不在本 spec 清理）
  - 落地时另加两条 Property（design 已补声明，防悬挂引用）：**Property 24** 源外保留列显式登记 + UI 标注（`reply_date`/`identity_method`/`phone_source`/`reliability_note` 四条，reason 须有实质内容）· **Property 25** 模板引用的标识符均已定义或导入（`<script setup>` 未声明标识符不阻断编译，只在浏览器打开时整页崩）
  - CI 新增 job：`k0-source-alignment`（后端 2 个测试文件 + 幂等脚本 `--check`）+ `k0-source-alignment-frontend`（k0-confirmation 目录 + `k0ColumnAlignment` + `k0SharedComponentBoundary` + `reliability/__tests__` + `confirmationColumnSpec`）
  - _Requirements: 7.6, 8.5, 9.3, 9.5, 9.6, 10.4, 11.4, 11.6_

- [x] 17. 浏览器实测（三件套，缺一不算实测）
  - 逐个打开 K0 的 9 个 sheet 页签，确认无「页面渲染出错」（Vue 运行期错误四层验证全查不出）
  - K0-1 录 ≥2 行（两品种各一行 + 一行未回函走替代）→ 确认矩阵 8 指标出数、三个比例正确、账面金额可手填且手工优先、未归类提示按预期出现/消失
  - `postgres` 只读确认下区键落库且键名符合 Property 9
    - 🔴 **落点是 `checklist_responses` 不是 `html_data`**（立项写错）—— 下区一律 `emit('save', itemId, value)` 走 `PUT /checklist-responses`；`html_data['函证结果汇总表K0-1']` 只承载上区明细行 `rows` 与 `sampling`/`notes`/`conclusion`/`summary_config`
  - K0-2 勾「是否进行第二次发函=是」→ 六列展开可录入并落库；K0-7 切 `reply_method` → 对应渠道列组展开
  - K0-5 段①确认 label 为「付款方」且支持性文件三列在；K0-6 为「收款方」
  - 实测前抓快照，测完**逐字复原**测试数据
  - _Requirements: 3.1, 3.5, 7.1, 8.1, 9.1_

- [x] 18. 回归与收口
  - `npx vitest run confirmation` 全绿；F0/E0/G0/D0/H0/L0 的 confirmation spec **不改任何断言**全绿
  - `backend/tests/test_k0_*.py` + `test_fraud_risk_presets_source_fidelity.py` + `test_confirmation_meta_override_alignment.py` + `test_render_config_smoke.py` 全绿
  - `fix_k0_prefill_presets.py --check` 返回 0 项欠账
  - 清理本会话 `tmp_*` 诊断产物
  - 把「K0 十张 sheet 编制逻辑 + 本轮修掉的缺口 + 未做项及归属」写入本文件 Notes；memory 只留铁律级条目
  - _Requirements: 11.5, 11.6_

## Notes

### 收口实录（2026-08-08，18/18 全完成）

**接手时的第一件事是「spec 三件套在工作树里被并发会话删掉了」** —— `.kiro/specs/k0-confirmation-source-alignment/` 三个文件全部处于 ` D`（已删未暂存）状态，`file_search` 全仓零命中；`git log` 显示它们只被 `6ab66b76` 收过一次，故 `git checkout HEAD -- <dir>` 即完整恢复。**恢复出来的 tasks.md 是 7/18 的旧快照，而磁盘上的代码产物远超它** —— 这是「复选框与代码实证不一致」的又一实例，且成因是新的一种：**spec 文档被删导致进度记载整体回退**（此前记载的成因是「并发会话完成不回写」或「IDE 自动标绿」）。⇒ 判进度一律先逐项探针，别信复选框，也别因为文档不见了就以为工作没做。

**逐项探针实证：Wave 3（Task 8~14）早已完整交付，本轮只剩一个真缺口。**

| Task | 实证 |
|---|---|
| 8 | `k0SummaryMatrix.ts` 14.3 KB + `k0SummaryMatrix.spec.ts` 23.8 KB（Property 5/6/7/8） |
| 9 | `CYCLE_VARIANT_COLUMNS.K0=['send_channel','k0_row_conclusion']` / `CYCLE_EXCLUDED_COLUMNS.K0` 三列 / `CYCLE_COLUMN_LABEL_OVERRIDES` 含 `K0`（另有 G0/H0/L0）/ **`CYCLE_COLUMN_GROUP_OVERRIDES` 已新建且只有 `K0` 一个键**（其余循环缺省 ⇒ 零回归） |
| 10 | `K0SummaryLowerZone.vue` 23.2 KB；`GtConfirmationSummary.vue` 的 `isK0` 8 处 + 挂载 3 处；`ConfirmationSampling.vue` 的 `isK0` 4 处 + `K0_SAMPLE_SELECTION` 4 处 |
| 11 | `k0MatrixDataSources.ts` 17.6 KB |
| 12 | `cycleConfirmationMeta.ts` 的 `indexTypoNote` 3 处；`ConfirmationDetail.vue` 的 `send_memo` 只读留档区（`v-if="row.send_memo"`）在 L356 |
| 13 | `blockColumnConfigsK05.ts` 付款方 4 / 识别特征 3 / 支持性文件 5；`blockColumnConfigsK06.ts` 收款方 5；`k0AlternativeSourceFidelity.ts` 红字真源；`entityVerifyGuidance.ts`（K0-2 五条编制说明）；二次发函六列在 types + Detail 双侧 |
| 14 | `RELIABILITY_PARENT_HEADER` 已在 `ReliabilityGrid.vue` L183 用常量渲染；`reliabilityColumnLabels.ts` 九处源模板用词；`memoTemplates.ts` 工号 12 处 + `THIRD_PARTY_CALLBACK_TPL`（接待事实核实）；12 渠道字段按「明确撤回」处置并有专门守卫 |
| 16 | `k0ColumnAlignment.spec.ts` 17.8 KB + `k0SharedComponentBoundary.spec.ts` 25.6 KB（**都在 `confirmation/__tests__/` 而非 `k0-confirmation/__tests__/`**）；CI 两个 job 已在 `governance-checks.yml`（jobs 137） |

**本轮唯一真缺口 = Property 22/23 无守卫。** design 的 Testing Strategy 表点名 `k0LowerZone.spec.ts`，该文件不存在；Property 覆盖矩阵实扫结果是「1~21、24、25 全有引用，**22 无任何引用**、23 只被 H0 的 `entityVerifyH0Columns.spec.ts` 偶然命中（那是 H0 自己的 Property 23）」。→ 新建 `k0-confirmation/__tests__/k0LowerZone.spec.ts`（20 例），**变异检验 6/6 全 RED、md5 逐字节还原**：

| 变异 | 结果 |
|---|---|
| M1 `inject` 挪进函数体（setup 顶层失效） | RED（2 条） |
| M2 把 `fmtAmount` 当模块级命名导出引入 | RED |
| M3 自造 `toLocaleString` 格式化 | RED |
| M4 金额控件换成 `el-input-number :formatter` | RED（7 条） |
| M5 去掉 `readonly` 门控 | RED |
| M6 比例分支退化成金额格式 | RED |

> 🔴 变异脚本首版 M3/M4 报 ANCHOR-MISS（hits=0）—— **含 `\n` 的跨行锚点在 CRLF 工作树必不命中**（已记铁律，本轮又踩）。改单行锚点后立刻 RED。**ANCHOR-MISS 是脚本缺陷、既不是 RED 也不是 GREEN**，当成 GREEN 处理会漏掉真正的守卫缺陷。

**同轮修掉三处三件套自身缺陷**：

1. **悬挂引用** —— `k0SharedComponentBoundary.spec.ts` 引用了 design 里不存在的 Property 24/25 ⇒ design 补齐两条声明（24 源外保留列显式登记 + UI 标注 / 25 模板标识符均已定义），并写明 24 是对 R9.3「按循环控制 `reply_date` 可见性」的**落地修正**（六枢纽源模板全部无该列 ⇒ 按循环分叉说不出依据）。
2. **Testing Strategy 表路径漂移** —— 矩阵守卫写成 `confirmation/__tests__/x0SummaryMatrix.spec.ts`（泛化内核撤回后该文件名不再成立）、替代程序守卫写成 `confirmation/__tests__/`，实际两者都在 `k0-confirmation/__tests__/`；下区由一份拆成「声明真源」+「实现形态」两份。
3. **AC 11.1 无人引用** —— 它是 Wave 3 的并发闸（F0 未收口前不得改共享件），落到 Task 8 的 `_Requirements:`（Wave 3 第一个共享件任务即闸门判定点）。

三件套现自洽：11 需求 / 80 AC / **25 Property 无缺号无重复** / design 与 tasks 的 AC 引用**悬挂 0 条** / 未被任何一侧覆盖的 AC **0 条** / waves JSON 18 个 id ≡ 复选框 18 个 / `get_diagnostics` 零诊断。

**四处立项描述被落地实证推翻（勿按旧文字实现）**：`indexTypoMap` → 实为 `SheetMeta.indexTypoNote` · `second_send_*`/`second_info_match` → 实为 `second_entity_*`/`second_contact_*`/`second_fax`/`second_info_verified`（与一次发函侧同构词法）· 12 渠道字段「接线或撤回」→ 撤回（三条并列实证）· 下区落点 `html_data` → 实为 `checklist_responses`。

### 浏览器实测（Task 17，2026-08-08，chrome-devtools `isolatedContext` + postgres 只读）

项目 `2aa00f57`（重庆和平药房连锁有限责任公司_2025）/ wp `02c5f9b2`（**`wp_code=K0` 整册 10 sheet** —— 单 sheet 遗留 wp_code 的 `html_data` 为 null，用它测不到注入）。
基线：`parsed_data IS NULL` / `md5=d41d8cd9…` / `updated_at=2026-06-08 02:00:53.647970+00` / `checklist_responses` 0 行。

| 验证项 | 结果 |
|---|---|
| 9 个 sheet 逐个打开 | 全部无「页面渲染出错」；console **零 `[error]`**（39 条 `[warn]` 全是平台预存在的 EP/prop 类型告警，如 `year` Number vs String、`GtAProgramConsole` 缺 `schema`） |
| 下区四块渲染 | 一、函证情况（C27）/ 三、审计说明（S27）/ 四、审计结论（C38）+ 编制说明 `details` 折叠；二、样本选择由共享 `ConfirmationSampling` 承担（`renderedHere:false` 设计如实） |
| 8 指标锚点与文案 | `C29..C36` 逐格显示锚点；X29+X30 合并句完整不半句结尾；第 3 项挂「源模板索引号笔误」tag（逐字保留源模板的「（K0-6）」）；第 5 项 `aliasOf` 只读引用 + 「请在那里编辑（避免两处录入）」 |
| **账面金额自动取数** | 其他应收款 **87,794,660.16**（= K1 `adjudication_prefill.fs_reconciliation.report_total`，BS-009 净额口径）/ 其他应付款 **110,361,076.52**；取数诊断告警**真实渲染**（K3 row_code 缺口那条），不是只收集 |
| 矩阵 8 指标出数 | 录 2 行（其他应收款 100 万相符 / 其他应付款 50 万未回函+替代 20 万）→ C30 1,000,000/500,000 · C31 1.14%/0.45% · C32 1,000,000/200,000 · C33 100.00%/40.00% · C34 1.14%/0.18% · C35 −/200,000 · C36 1.14%/0.36%，逐格与源模板 SUMIF 口径相符；**C36 无 ISERROR 兜底**如实实现 |
| 三态与 null 口径 | 分母为 0 的 C33 显示 `-`（null，非 0）；分母非 0 分子为 0 的 C31/C34/C36 显示 `0.00%` |
| **Property 22/23** | 账面金额格显示 `87,794,660.16` / 手工改 90000000 → `90,000,000.00`（千分符 + 2 位小数）；比例随之 1.14% → **1.11%** ⇒ 手工优先生效 |
| **Property 2/4（完整表格视图）** | 六段分组 `发函信息(8)/发函询证纪要(4)/收到回函(7)/回函金额确认(5)/未收到回函的替代程序(4)/行级审计结论(1)` = **29 个叶子列 = 源模板 28 列 + 显式登记的「函证类型（积极式/消极式）」**；「账户/交易」（非「科目」）、「调节索引（K0-4）」（源模板笔误 K1-12 按意图修正）、无联系人/联系电话/币种三列、无 `send_memo` 伪列 —— 全部生效 |
| 落库（Property 9） | `checklist_responses` 恰 3 键：`K0-1-lower-audit-note-1` / `K0-1-lower-conclusion` / **`K0-1-matrix-其他应收款-book_amount`**（后者逐字等于 `prefill_formula_mapping.json` 的 `cell_ref`，前后端双向锁死在浏览器端得到证实）；`parsed_data.html_data['函证结果汇总表K0-1']` = `rows`(2) + `_format:confirmation-v1` + `summary_config.account_types` 两品种 |
| 硬刷新读回 | 矩阵 8 指标由落库数据重算一致、手工覆盖 `90,000,000.00` 读回、审计说明与结论读回、两行明细读回 |
| K0-2 | 二次发函六列（地址/邮编/联系人/联系电话/传真/信息核查一致）受 `二次发函` 开关门控；**五条编制说明全部渲染**（`说明1：`~`说明5：` + 锚点 A28/A34/A36/A38/A40 + 「记录工号（若有）」），默认折叠在 `details` 里 |
| K0-7 | 父表头「期末未收回原件函证可靠性验证」**跨 11 列**渲染；九处源模板用词 label 全部生效（被函证者身份确认 / 邮箱可靠性验证 / 是否致电被函证者确认 / 发函及回函传真信息及验证 / 对函证信息可靠性的考虑 / 是否由审计项目组直接接收 / 是否寄回原件） |
| K0-6 段① | `付款审批单{日期/编号, 是否经过恰当审批}` + `银行回单{日期, **收款方**, 金额}`；「付款方」计数 0 ⇒ Property 14 的方向正确；红字「关键证据和要素…」琥珀块已渲染 |
| 「账户/交易」下拉 | 已含 `其他应收款`/`其他应付款`（立项记的「三处下拉都无 K 类科目」已被后端 4 新枚举 + 21 追加取值修好） |

**数据已逐字复原并经独立工具交叉核实**：复原脚本报 `deleted=3 updated=1` 后另起事务复查，再用 postgres MCP 第三方核对 —— `parsed_is_null=true` / `md5=d41d8cd98f00b204e9800998ecf8427e` / `updated_at=2026-06-08 02:00:53.647970+00` / `cr_rows=0` / 全库 `parsed_data` 命中「K0实测」**0 行**，与基线逐项相等。

> 复原时踩到一条：**asyncpg 的 timestamptz 参数必须传 `datetime` 对象，传字符串会 `DataError`**，`CAST(:ts AS timestamptz)` 救不了（参数在绑定期就已按 timestamptz 编码）。因为写在 `engine.begin()` 里，首次失败整体回滚、未产生半写状态。

### 回归

| 范围 | 结果 |
|---|---|
| `backend/tests/test_k0_*.py` | **209 passed** |
| 后端本 spec + 邻域（`test_fraud_risk_presets_source_fidelity` / `test_confirmation_meta_override_alignment`） | 223 passed / **1 failed 预存在** |
| `fix_k0_prefill_presets.py --check` | `[OK] K0 预设已达目标状态，0 项欠账`（exit 0） |
| 前端 `src/components/workpaper/confirmation` 全量 | **1975 passed / 0 failed**（改造前 1955；新增 20 例全通过、**新增失败 0**） |
| F0/E0/G0/D0/H0/L0 的 confirmation spec | **未改任何断言**，全绿 |

**唯一失败 `test_confirmation_meta_override_alignment::test_non_null_codes_have_override`（`G0.diffCode=G0-5` 在 override 无映射）是预存在的 G0 侧不一致**，判据不是「看着像别人的」：把 `wp_code_overrides.json` 与 `cycleConfirmationMeta.ts` 的**工作树版与 `git show HEAD:` 版逐项对比**，两侧都是 `meta G0.diffCode='G0-5'` 而 override 的 G0* 键集都是 `G0/G0-1/G0-2/G0-3/G0-3S/G0-4/G0-6/G0-7/G0-8/G0A`（**都没有 `G0-5`**）⇒ 与本轮零因果，归 G0 循环侧。

### 本轮新查出、未修、需登记归属的问题

| 项 | 实证 | 归属与不修的理由 |
|---|---|---|
| **保存后切走再切回，函证汇总回到 render-config 初始载荷（空态）** | 同一次页面加载内：录 2 行 → 保存成功（DB 已落库）→ 切 K0-6/K0-5 → 回 K0-1 显示 onboarding 空态；**硬刷新后恢复正常**（切 K0-2/K0-6 再回来行数稳定 2 行）⇒ 不是数据丢失，是宿主保存后不刷新 `htmlData` prop | 平台级（七枢纽共享 `GtConfirmationSummary`）。**该组件源码明文写着「本组件未 inject `reloadWorkpaperData`，写了会运行时 ReferenceError 而 `get_diagnostics` 查不出」** ⇒ 补刷新通路要动共享宿主、波及 7 个循环，超 R11.4 边界。**但它是一条潜在数据丢失路径**（用户看到空态重新录入再保存 = 整表覆盖掉已存的行），建议单独立 spec 并优先于其它函证增强 |
| **列表视图的详情面板不套用列剔除与 label 覆盖** | `ConfirmationDetail.vue` 仍显示「联系人/联系电话/币种」（K0 已在 `CYCLE_EXCLUDED_COLUMNS` 剔除）且用「函证方式」而非「函证类型（积极式/消极式）」—— 因为 label/exclusion 由 `resolveConfirmationColumns` 施加，只有 `ConfirmationFullGrid` 消费它；详情面板有自己一套固定字段与 label | 平台级（七枢纽共享）。**详情面板是主要录入路径**，故这不只是显示问题：审计师在这里看到源模板没有的三列。Requirement 2 的验收对象是「列集」，落地已达标；要让两个视图口径一致须让详情面板也走 `resolveConfirmationColumns` = 改共享件 + 影响 7 循环，另立 spec |
| K0-6 的「从 D0-1 带入」按钮文案 | 七循环替代程序主控件共用 `AlternativeD05Master`，标签在所有循环都写 D0-1 | memory 已登记的平台文案项，非本 spec |

### 🔴 进度校正（2026-08-07 逐项探针实测：**14/18**，此前复选框记 7/18 = 五项假红）

按 memory 铁律「复选框与 memory 记的数字都不可信，接手必须逐项探针」实测，Task 8~14 的产物
**全部已在磁盘**且完整。Wave 3 的并发阻塞早已解除（F0 实测 144/144、G0 已归档）。

| Task | 旧复选框 | 实测 | 证据 |
|---|---|---|---|
| 8 矩阵 | `[x]` | ✅ | `k0SummaryMatrix.ts` 14.3 KB |
| 9 列集 | `[x]` | ✅ | `CYCLE_COLUMN_LABEL_OVERRIDES.K0`(15 条) + `CYCLE_COLUMN_GROUP_OVERRIDES.K0`(7 条) + `send_memo` def 已删 + `k0_row_conclusion` 在 `row_summary` |
| 10 下区 | `[x]` | ✅ | `K0SummaryLowerZone.vue` 23.2 KB + `GtConfirmationSummary` 挂载（`isK0` 8 处） |
| 11 取数 | `[x]` | ✅ | `k0MatrixDataSources.ts` 17.6 KB |
| **12** | `[ ]` | **✅ 假红** | `ConfirmationDetail.vue` 的 `v-if="row.send_memo"` 只读留档区 + `k0SheetRegistry.ts` 三条笔误 + `indexTypoNote` 机制 |
| **13** | `[ ]` | **✅ 假红** | K0-5 `receipt_payer`=「付款方」+ 支持性文件三列 + `entityVerifyTypes` 六字段 + `entityVerifyGuidance.ts` |
| **14** | `[ ]` | **部分→本轮补完** | 12 渠道字段已按「明确撤回」处置（`reliabilityChannelFieldsWithdrawal.spec.ts` 在册）+ 父表头已接；本轮补列标签真源与源外列登记 |

**🔴 两处 tasks.md 原描述与磁盘不符（勿按旧描述改）**：

1. **二次发函六字段的真实名是 `second_entity_*` 不是 `second_send_*`** ——
   实测 `entityVerifyTypes.ts` 为 `second_entity_address` / `second_entity_zipcode` /
   `second_contact_person` / `second_contact_phone` / `second_fax` / `second_info_verified`
   （由 h0 spec 建），`EntityVerifyDetail.vue` 已逐个接线。按 Task 13 写的 `second_send_address`
   去 grep 会得「零命中 ⇒ 未做」的错误结论。
2. **Task 14 的「12 个渠道字段补 UI 录入位置」已被改判为「明确撤回」** ——
   守卫文件名是 `reliability/__tests__/reliabilityChannelFieldsWithdrawal.spec.ts`
   （不是 tasks 原计划的 `k0ReliabilityChannelFields.spec.ts`），三条并列实证：
   六份源模板可靠性表逐字同构 14 列且都无这些列 / 原始出处是 E0 的 hidden sheet
   （用户已裁决 A-否）/ 全库 0 存量。R9.1 的「或明确撤回」分支即此。

### 🔴 Task 14 本轮补完部分（2026-08-07）

**新建 `reliability/reliabilityColumnLabels.ts`** —— X0-7 列标签真源 + 源外列登记。

**推翻 R9.3 的立项描述（openpyxl 直读七枢纽实证）**：R9.3 原文要求「按循环控制
『回函日期』列可见性，保持 D0/F0/G0/H0/L0 行为不变」，而实测**六个可见的可靠性 sheet
表头逐字完全相同、一个都没有该列**（`D0-7`/`F0-7`/`G0-7`/`H0-6`/`K0-7`/`L0-6` 均 14 列、
`G5:M5` 合并父表头、r5/r6 叶子列逐字一致；E0 无可靠性 sheet）⇒「按循环分叉」只会产出
「K0 藏起来、另五个继续显示源模板没有的列」这种自相矛盾的结果。
⇒ 改为**平台级源外保留列 + 显式登记依据**（同 `confirmation_method` 在 X0-1 的处置）：
`SOURCE_EXTRA_RELIABILITY_COLUMNS` 登记 4 列（`reply_date`/`identity_method`/
`phone_source`/`reliability_note`），每条写明审计依据，列头挂问号 tooltip 呈现理由。

**R9.4 同理不按循环分叉** —— 六枢纽源模板用词逐字相同，故
`RELIABILITY_COLUMN_SOURCE_LABELS` 是平台唯一一份映射（9 条「平台简称 → 源模板全称」，
如「身份已确认」→「被函证者身份确认」、「信息可靠性」→「回函可靠性结论」）；
`（注N）` 后缀不进 label（注 1/2/3 全文已由 `FIELD_TOOLTIPS_D07` 承载为列头 tooltip，
两处都写会重复）。每条带 `legacyLabel` 供守卫断言「确实改了」，防映射退化成空操作。

**K0-2 编制说明零展示已补** —— `ENTITY_VERIFY_GUIDANCE`（5 条，真源已在
`entityVerifyGuidance.ts`）此前**只有守卫消费、UI 零展示**；本轮在 `EntityVerifyDetail.vue`
末尾加折叠区（默认收起）+ 锚点 tooltip 溯源。

**验证**：`get_diagnostics` 零诊断 + Vite transform 5 个文件全 200 +
`vitest run confirmation reliability entityVerify` **655 files / 2359 passed / 0 failed**（零回归）。

### 交付实录（2026-08-04，Wave 1 + Wave 2 完成 7/18；Wave 3 当时被并发约束挡住）

**Wave 3 未开工的判据（每次接手都要重扫）**：F0 spec 仍 `done=28 / inprog=1 / queued=2`
（tasks.md mtime 08-03 23:35 静置），按 Requirement 11.5 只能推进 Wave 1/2；G0 spec 13/23、
mtime 08-04 13:08 仍在动。**Wave 3 的 7 个任务（8~14）全部碰共享件，不得在此状态下开工。**

**产出**

| 文件 | 规模 | 覆盖 |
|---|---|---|
| `backend/tests/test_k0_source_template_facts.py` | **185 例** | Property 1 + R1.1~1.17 全部源侧结构断言 + 5 条笔误登记 + 6 组反向自检 |
| `backend/tests/test_k0_formula_presets.py` | **21 例** | Property 11（七枢纽 sheet 名存在性 + 白名单）/ 12（幂等 + round-trip + 只扫语义字段） |
| `backend/scripts/fix/fix_k0_prefill_presets.py` | 三态幂等 | **已 `--apply`**（3 项变更），二次 apply 与 `--check` 均 0 欠账 |
| `confirmation/k0-confirmation/k0MatrixSpec.ts` | 2 品种 × 8 指标声明 | R4.1/4.2/4.3/4.5 |
| `confirmation/k0-confirmation/k0LowerZoneSpec.ts` | 四块文字真源 | R3.1/3.6~3.12/6.1/6.2 |
| `__tests__/k0MatrixSpec.spec.ts` + `k0LowerZoneSpec.spec.ts` | **67 例** | Property 8/9/10/13 + 交叉锁死 + helper 自检 |

**变异检验（守卫有效性的唯一证明）**：后端 6 处 + 前端 10 处变异**全部打红**
（脚本已删；改一字即红的清单：sheet 名 / 目录序号补 6 / `账户/交易`→`科目` / 末行补 ISERROR /
K0-6 对方当事人统一成「付款方」/ 笔误 intended 退回 literal / `BS-050`→`BS-075` / 品种名 /
指标标签 / 覆盖键改用中文 label / 审计说明序号 `N.`→`N、` / aliasOf 指向不存在字段 /
样本字段新造名 / 第 3 项 hint 与标题拼接 / 注意事项锚点改到 A 列）。

**回归**：`test_k0_*` 206 passed。`test_k_prefill_extension` + `formula_management`
**26 failed 全部预存在** —— 判据不是「看着像别人的」，而是把 `prefill_formula_mapping.json`
临时换成 `git show HEAD:` 版跑同一组，两侧失败集合**逐条相同**（新增 0 / 消失 0）。
前端 `vitest run confirmation` **1802 例 / 1795 passed**，7 failed 全在
`GtG0Confirmation.integration.spec.ts`（该文件 ` M`，属并发 G0 会话在改 `blockColumnConfigsG06.ts`）。

**Wave 2 产物当前零生产消费方**（只被自己的 `__tests__` 引用）—— 这是**预期状态**，
Wave 3 的 Task 10/11 才接线。Property 20（零消费方即打红）的守卫在 Task 16，届时才生效。
下个会话看到「新模块没人用」不要当缺陷回退。

### 落手时推翻/补正的立项描述（勿按旧描述实现）

1. **公式预设 `cell_ref` 不写裸单元格地址** —— Requirement 5.2 写「对应源模板 `E29`/`F29` 两格」，
   落地形态是 G0 已确立的**手工覆盖键** `K0-1-matrix-{品种}-book_amount`（`E29`/`F29` 作
   `sourceRef` 写进 description）。理由见 G0 块自己的说明：**`cell_ref` 同时是手工覆盖键**，
   写裸地址或审定表口径的键都落不到矩阵上。守卫 `k0MatrixSpec.spec.ts` 断言该键与
   `prefill_formula_mapping.json` 的 `cell_ref` 逐字一致（前后端双向锁死）。
2. **样本选择第 1 项的字段名是 `test_population` 不是 `test_scope`** —— Task 5 写「复用
   `useAlternativeK05Data` 的 sampling 字段名」，但 K0-1 的持久化目标是
   `SamplingData`（`ConfirmationPayload.sampling`）而非替代程序族的 `SamplingConfig`；
   `SamplingData` 上「二、样本选择第一项」的槽是 G0 spec 已建好的 additive 字段
   `test_population`。**给 `SamplingData` 再加一个 `test_scope` 就是「新造第二套字段名」**
   （正是该约束要防的事）→ 沿用 `test_population`，并在每项上声明 `legacyFamilyField`
   记录替代程序族的对位字段，守卫断言「6 个 key 全在 `SamplingData` 里 + 5 个与
   `SamplingConfig` 同名 + 唯一例外 `test_population` 显式登记且 `SamplingData` 里不得出现
   `test_scope`」。
3. **`_plan` 不把 `description` 纳入语义比对** —— 首版整块 `cells != TARGET_CELLS` 比对会让
   「手工补一句说明」被判成欠账，与 R5.4 相悖。改为 `_cells_semantic()`
   （`cell_ref`/`formula`/`formula_type`/`applies_when`）+ 单独校验 description 非空。
4. **`--apply` 后 K0 不在 `KNOWN_BAD_SHEET_NAMES` 白名单里**，但 **D0 有三条**（不是一条）：
   `审定表D0-1` / `分析程序D0-3`（D0-3 真名是「跟函函证过程控制D0-3」）/
   `函证汇总表D0-2`（D0-2 真名是「核实被函证单位信息D0-2」）。白名单结构因此是
   `(cycle, sheet) → reason` 而非 `cycle → sheet`。

### 本轮新查出、**未修**、需登记归属的问题

| 项 | 实证 | 归属 |
|---|---|---|
| **`K_CYCLE_SPECS['K3']` 的 row_code 错位** | 声明 `row_code_listed="BS-053"` / `row_code_soe="BS-075"`，而 `report_config` 实测 BS-053 = **其他流动负债**（K4 的行，formula 现为 NULL）、BS-075 在 soe 侧 row_name 是其他应付款但 formula 为 NULL（**listed 侧 row_name 竟是「股本」**）。有公式的其他应付款行是 **BS-050** = `TB('2241')+TB('2231')`。K3 现靠 `fallback_standard="2241"` 取数「碰巧对」，但①溯源展示的报表行是错的 ②**漏掉 `2231`**（应付利息已按财会[2018]15 号并入其他应付款列报）。守卫 `k0MatrixSpec.spec.ts` 已把该分歧显式钉住，**K3 修好即打红**提醒收敛 | K 循环侧 / `report-config-account-code-integrity`（row_code 对账那批；2026-08-03 那轮修了 16 处，**K 循环没查**） |
| **`BS-075` 在两套准则下 row_name 不同** | listed_* = 「股本」/ soe_* = 「其他应付款」（同一 row_code！）→ 「按 row_name 匹配」不只是会撞同名行，还会在切准则时拿到**完全不同的科目** | 平台级事实，已写进 `k0MatrixSpec.ts` 与预设 description 留证 |
| **L0 源模板程序表 tab 名是 `函证程序表F0A`** | openpyxl 实测；G0 的舞弊表 tab 名同款写成 `函证程序舞弊风险评价表F0-8`（memory 已记 G0 那处） | L0 循环侧（尚无 spec） |
| **K0-1 `O32` 的数据验证指向 `#REF!`** | 源模板坏引用，守卫已登记为事实，不实现 | K0 源模板缺陷，登记不改 |

### 源模板编制逻辑链（做任何 K0 改动前的地图）

```
底稿目录（被审计单位/截止日/编制人复核人 → 全表表头 =底稿目录!Ax）
   │
   ├─ 函证程序表K0A（12 条程序 + 程序分类 常规★/备选/舞弊应对·IPO 类 + 底稿索引号）
   │
   ├─ 核实被函证单位信息K0-2（38 列 5 段：发函前核实 → 回函核对 → 一次发函结果 → 二次发函信息 → 二次发函结果）
   │        │ VLOOKUP 七列（2/3/4/10/16/19/22）
   │        ▼
   ├─ 函证结果汇总表K0-1（上区 28 列 6 段 20 行；下区 一、函证情况矩阵 2×8 / 二、样本选择 6 / 三、审计说明 5 / 四、审计结论）
   │        │  T=IF(L="是",S-F,"未回函")
   │        ├──► K0-4 函证差异调节表（源写「调节索引（K1-12）」= 笔误）
   │        ├──► K0-5/K0-6 替代程序（未回函项）
   │        ├──► K0-7 回函可靠性（源写「（K0-6）」= 笔误）
   │        └──► 矩阵 SUMIF(账户/交易, 品种, 金额|可确认金额|替代后可确认金额)
   │
   ├─ 跟函函证过程控制K0-3（备忘录：即时确认 / 留函待寄回 / 电话回访核实接待事实 / 3 控制点 / 手书签名；含工号）
   │
   └─ 函证程序舞弊风险评价表K0-8（19 条迹象 + 可扩行 → 汇总去向 B50）
```

### 已核实无需改动（勿重复上报）

| 项 | 实证 |
|---|---|
| K0-8 19 条舞弊迹象 | `fraudRiskPresets.ts` 已是平台唯一真源且按源模板逐字重写，后端 `test_fraud_risk_presets_source_fidelity.py` 以 xlsx 为裁决者，六表 md5 全等 |
| K0-5/K0-6 段③借贷拆表 | 两个组件均已实现（借方表 + 贷方表 + 待归位提示 + `addDirectionRow`），`splitByDirection` 已在 manifest 登记 |
| K0-5/K0-6 block4 往来对账 | 源模板无该区块，已在 `SOURCE_EXTRA_MANIFEST` 登记依据 |
| K0-5/K0-6 样本选取区与余额表 | 组件已有 `sampling.test_scope` 与 `balanceSummary`（含 `E12=B12+C12-D12` 派生） |
| 9 个 sheet 的 componentType | `wp_code_overrides.json` 全部登记（`K0A`→`a-program-console`，`K0-1..K0-8`→`confirmation-*`），无 `skip` |
| 后端 render / AI / 导入导出 | `_k0_confirmation.py` / `_k0_confirmation_ai.py` / `_k0_confirmation_import_export.py` 三个策略齐备 |
| `ConfirmationMaster.vue` 列硬编码 | 有意设计（列表视图=核心列概览，完整宽表在 `ConfirmationFullGrid` 且它确实消费 `resolveConfirmationColumns`），注释已说明 |
| `wp_render_schema/generated/K0.yaml` | 运行时**从不加载**（`_SCHEMA_DIR` 不含 `generated/`），与 E0 同款平台事实，非 K0 缺陷 |

### 已发现但归属别的 spec（本 spec 只登记不实施）

| 项 | 归属 | 实证 |
|---|---|---|
| `RELIABILITY_COLUMN_CONFIG`（14 列常量）零消费方 | 平台级（六循环共享） | `ReliabilityGrid.vue` 对该常量 0 命中，自行渲染列 |
| E0 公式预设 `sheet="审定表E0-1"` 不存在于源 xlsx | `e0-confirmation-completion` 遗留 | 与 K0 同款笔误，Task 6 的守卫会打红，登记白名单 |
| `ReliabilityRow` 12 个渠道字段死字段 | `e0-confirmation-completion` R7 声明「照做」但只加了类型 | 全前端仅 `reliabilityTypes.ts` 一处出现；本 spec Task 14 顺带修好（共享受益） |
| `E0SummaryLowerZone.vue` 仅被 `components.d.ts` 引用、`useE0BookAmounts.ts` 零消费方 | `e0-confirmation-completion` 遗留 | 与 E1 spec 抓到的「8 个组件写好从未渲染」同款 |
