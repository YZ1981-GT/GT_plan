# K1 其他应收款披露表与附注对齐增强 — 任务

## Sprint 1 — 数据模型与映射

- [x] 1.1 `k1DisclosureModel.ts`：账龄 `sub` / `subtotal1y` 行类型 + `buildAgingDisclosureRows(opts.withinOneYearBreakdown)` + `calcWithinOneYearTieOut`
- [x] 1.2 listed payload 增 `priorStage1/2/3Rows`、`stage2NoneEnd/Prior`、`continuedInvolvementRows`（`migrateContinuedInvolvement` 兼容旧标量）
- [x] 1.3 soe payload 增 `K1ReversalDisclosureRow.cumulativeProvision`、新类型 `K1OtherPortfolioRow`（`migrateOtherPortfolioRows` 兼容旧 `endBalancePct` 口径）、`continuedInvolvementRows`
- [x] 1.4 新增勾稽函数：`calcWithinOneYearTieOut`(T3) / `calcPriorProvisionTieOut`(T4') / `calcMovementTieOut`(T5·T6·T7) / `calcIndividualSplitTieOut`(T9) / `calcPortfolioSplitTieOut`(T10) / `calcTop5ProportionCheck`(T12) / `stageBlocksProvisionTotal`
- [x] 1.5 `k1NoteSectionMap.ts`：`K1_LISTED_SUBTABLE` 增 priorStage1/2/3；`K1_SOE_SUBTABLE` 修正 reversal / balanceMovement / transfer 表名 + 增 portfolioAging / continuedInvolvement；SECTION_GUIDES 补 8 个新区块
- [x] 1.6 `mapK9ReversalRow`：K1-9 `accumProvision` → `cumulativeProvision`；soe 账龄表关闭月度细分

## Sprint 2 — 附注模板 JSON 修订

- [x] 2.1 listed §五、8「按款项性质披露」→ 7 列全限定列名 + `_column_groups`，删冗余 `header_label` 行
- [x] 2.2 listed 期末/上年年末第一、二阶段补「其他应收款单位1/2」行（6 张三阶段表结构一致）
- [x] 2.3 listed §五、8 全 18 张表补 `guidance`
- [x] 2.4 soe §八、9 6 张表补二级表头（按账龄 / 计提方法 / 续： / 单项计提 / 账龄组合 / 余额百分比法）
- [x] 2.5 soe §八、9 新增 4 张表：账面余额变动 / 转移终止确认 / 继续涉入 / 政府补助（15 → 19 张）
- [x] 2.6 soe §八、9 `text_sections` 12 → 27 条（15号文引用 / 阶段依据 / 转回注 / 核销 / 政府补助注 / 继续涉入说明）
- [x] 2.7 soe §八、9 全 19 张表补 `guidance`
- [x] 2.8 幂等修订脚本 `backend/scripts/fix/fix_k1_note_section_alignment.py`（可重复运行）
- [x] 2.9 生成期透传：`disclosure_engine._carry_seed_table_guidance`（seed 显式 guidance 优先于段落游标推断，仅 K1 声明 → 其余章节零影响）
- [x] 2.10 `test_note_template_row_type.py` + `test_note_ci18_ci19.py` + `test_per_table_guidance.py` 全绿

## Sprint 3 — 同步载荷

- [x] 3.1 listed：priorStage1/2/3 子表 + 列头；`stage2None*` 开启时对应子表清空并推送标准语句；`_note_texts` 增 balance-change / ecl-basis / writeoff-note / transfer-note / stage2-none-end / stage2-none-prior
- [x] 3.2 soe：portfolioAging 与 portfolioOther 分表；aging 改「账面余额 + 坏账准备」双列口径（合计行补坏账总额）；reversal 补累计已计提列并合并原因·方式；transfer 去「转移方式」；continuedInvolvement 独立表（资产区/小计/负债区/小计）
- [x] 3.3 新增 `k1NoteSubtableContract.spec.ts`（32 项）：子表名 ↔ note_template 契约、`_column_groups` 齐备、headers 无空串、全表 guidance、4 张新表存在、**标签列头 = 附注 headers[0]**

## Sprint 4 — 底稿 UI·上市

- [x] 4.1 复用既有 `composables/wpAmountInput`（平台通行做法：`el-input-number` + `:formatter`/`:parser`），不新建组件
- [x] 4.2 账龄表 sub 行缩进 + 标签可编辑 + `1年以内小计：` 只读 + T3 校验告警
- [x] 4.3 ③ 段方法论上下文块（琥珀色左边线，15号文（四）5 + 二/三阶段划分依据）+ 期末三阶段 + 第二阶段「不存在」开关
- [x] 4.4 上年年末三阶段 3 张表（`el-collapse` 默认折叠，标题显示合计）+ 第二阶段开关 + T4' 校验
- [x] 4.5 两个说明 textarea + AI 辅助（`disclosure-balance-change` / `disclosure-ecl-basis`）
- [x] 4.6 ④ 变动表两级表头（阶段 + 二级释义）+ T5/T6/T7 合并告警
- [x] 4.7 ⑤ 核销 15号文引用 + 说明 textarea + AI；关联交易列改下拉点选
- [x] 4.8 ⑦ 资金集中管理 2 条解释15号提示块
- [x] 4.9 ⑧ 政府补助「重大业务咨询程序」提示 + 附注去向 tag + 可增删行
- [x] 4.10 ⑨ 转移终止确认表（新建，含转移方式下拉 + 合计 + 附注去向 tag）
- [x] 4.11 ⑩ 继续涉入表（资产区/资产小计/负债区/负债小计 + 说明 + AI）
- [x] 4.12 全表可编辑金额列千分符；比率列保持 `:precision=2` 不套金额格式；只读金额走 `displayPrefs.fmtAmount`
- [x] 4.13 编制提示重写为源模板 10 段对照（含 ⑧⑨⑩ 附注去向说明）
- [x] 4.14 抽出 `K1StageEclTable.vue`（6 处三阶段表复用）
- [x] 4.15 ② 段新增性质行改 `ElMessageBox.prompt` 先命名

## Sprint 5 — 底稿 UI·国企

- [x] 5.1 ④ 段新增「其他组合」表（动态行 + `ElMessageBox.prompt` 命名 + 合计行 + 坏账由计提比例派生）
- [x] 5.2 ② 计提方法表改两级表头（账面余额金额·比例% / 坏账准备金额·ECL率% / 账面价值），期末＋期初双表
- [x] 5.3 ④ 账龄组合补「期初比例(%)」并改两级表头（期末数 / 期初数）
- [x] 5.4 ⑥ 转回表补 `转回或收回前累计已计提坏账准备金额` 列 + 改可编辑 + 合计 + 源模板注
- [x] 5.5 前五名 / 核销 / 政府补助 改可编辑（含增删行，保留「K1-2」自动标签）
- [x] 5.6 ⑨ 转移表去「转移方式」列 + 改可编辑 + 「损失以「-」填列」列头 tooltip
- [x] 5.7 ⑩ 继续涉入改多行（资产/负债区 + 小计 + 说明 + AI）
- [x] 5.8 ⑤b 账面余额三阶段补【正数】/【负数】方向 tooltip + 方向异常单元格标红
- [x] 5.9 两个说明 textarea + AI 辅助
- [x] 5.10 全表金额列千分符 + T1/T8/T9/T10/T11/T12 告警区
- [x] 5.11 前五名占比分母改「账龄表小计」（原为前五名合计，口径错误）
- [x] 5.12 编制提示重写为源模板 8 段对照（含与上市版差异说明）

## Sprint 6 — 验证

- [x] 6.1 扩 `k1DisclosureListed.spec.ts` 6 → 13 项（账龄细分 / 上年年末三阶段 / stage2None / 继续涉入迁移 / T3）
- [x] 6.2 扩 `k1DisclosureSoe.spec.ts` 8 → 12 项（其他组合派生+T10 / 旧口径迁移 / accumProvision / 账龄无细分 / 新列头）
- [x] 6.3 前端 vitest：K1 披露 4 文件 64 项 + K1 全量 5 文件 173 项全绿
- [x] 6.4 后端 pytest：K1 契约 + 附注模板契约 + seed 元数据 + per-table guidance 共 77 项全绿
- [x] 6.5 Volar 诊断全部改动文件 0 问题；Vite transform 全部改动文件 200（SFC 结构权威校验）
- [x] 6.6 Playwright 实测：上市/国企两张披露表全区块渲染、0 console error；附注 §八、9 经 API 实测 19 表 / 6 两级表头 / 19 guidance / 27 文字段落
- [x] 6.7 死字段清零：`otherPortfolioRows` / `transferRows` / `continuedInvolvement*` 均已有 UI + 同步落点
- [x]* 6.8 `vue-tsc --noEmit` 全项目类型检查 —— **已跑通**（2026-07-30）
  - **可用配方**：`NODE_OPTIONS=--max-old-space-size=32768 npx vue-tsc --noEmit -p tsconfig.json`
    （约 5~6 分钟）。此前判定「本机 OOM」是**堆上限不足**而非机器内存不足（本机 189 GB /
    空闲 120 GB）：8 GB 与 12 GB 都 `FATAL ERROR: Ineffective mark-compacts near heap limit`，
    32 GB 跑完。⚠️ 12 GB 那次曾"看起来成功"，实为**在语法错误处提前 bail**、根本没进入类型检查阶段。
  - **基线**：3380 errors / 881 files（大量预存在，主要是 `el-input-number` 的
    `@change="(v: number) => …"` 与 `(cur, prev) => any` 签名不符，TS2322 占 1779 条）。
    本 spec 的 K1 文件残留属该基线，非本次引入。
  - 🔴 **本次靠它揪出并修掉 3 类问题（Volar 逐文件诊断 + vitest 全都查不出）**：
    1. **2 个文件语法级损坏、Vite transform 实为 500**：`I4TabPolicyCheck.vue:282` 的
       `{{ idx + 1 }.` 少一个大括号；`N1TabCalcTable.vue:812` 多一个 `}`。两者修复后均 200。
    2. **共享契约 helper 的类型不兼容波及 8 个循环**（D1/G4/G5/G6/G8/G9/G12/N1 共 16 条
       TS2322/TS2345）：`_disclosureSubtableContract.helper.ts` 的 `ContractColumnDef`
       带了 `[k: string]: unknown` 索引签名 → 带索引签名的类型不能从无索引签名的
       `interface ColumnDef` 赋值。删掉索引签名后 16 条清零（3396 → 3380），300 项契约测试仍全绿。
    3. **11 个宿主引用了不存在的 `runtime.applicableStandards`**（死 fallback）：
       `WorkpaperRuntimeContext` 里没有这个字段 —— 这正是「`applicableStandards` 前端全链缺失、
       变体门恒开」的类型层证据。清单：GtG4/G5/G6/G8/G9/G11/G12/G13/G14/H10/I2。
       **未改**（属跨前后端 schema 变更，须单独立 spec；11 处一致的既有模式，不在本 spec 范围内动）。

## 遗留说明

- **既有项目的附注 §八、9 仍显示 15 张表**：`disclosure_notes.table_data._tables` 是生成时快照，
  新增的 4 张表与 `_column_groups` / `guidance` 需重新生成附注后生效（新建项目直接生效）。
  「🔄 恢复模板结构」只重置当前单表，不新增表。
- 上市披露表的政府补助 / 转移 / 继续涉入三块**不推送** §五、8（附注真源分别在
  「计入其他应收款的政府补助」与 §七 金融工具章节），UI 已标注去向。
- 源模板 listed ④ 另有「本期转销」行，K1-3 三阶段矩阵当前不区分转销与核销；
  编制提示已说明，如需区分应在 K1-3 增设该行。
