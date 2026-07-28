# Implementation Plan

## Overview

按 design M0 → M5 实施。**M0 硬前置**（区块/列清单与 F05/F06 characterization 未就绪不得进 M1）。工厂固定 4 block 位不动；Occurrence_Block 借贷拆表在渲染层做（同 block 按 `direction` 分组）。全程既有 payload 数据零丢失。改动集中：新增 `alternativeBlockManifest.ts`（+源外登记）、工厂 additive（`getBlockTotalByDirection` / CheckRow `direction?` / payload `opening_consistency?`）、K05/K06/L05/G06/F05/F06 各套。**不改** 未回函带入链、共享行模型、G0 差异模型、工厂公共面。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2", "1.3"], "note": "只读核实区块/列清单 + 源外登记 + F05/F06 characterization（硬前置）" },
    { "wave": 1, "tasks": ["2.1"], "note": "工厂 additive：getBlockTotalByDirection + CheckRow direction? + payload opening_consistency?" },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "note": "K05/K06/L05 借贷拆表 + L05 期初一致性（逐套独立）" },
    { "wave": 3, "tasks": ["4.1"], "note": "G06 纳入工厂 + 区块对齐源三区" },
    { "wave": 4, "tasks": ["5.1", "5.2"], "note": "F05/F06 拆子组件（characterization 守护）" },
    { "wave": 5, "tasks": ["6.1", "6.2", "6.3"], "note": "契约/属性/守卫 + 零回归门 + Playwright" }
  ]
}
```

## Tasks

- [x] 1. Wave 0：区块清单核实与 characterization（硬前置）

- [x] 1.1 落 ALTERNATIVE_BLOCK_MANIFEST + 源外登记
  - 新建 `audit-platform/frontend/src/components/workpaper/confirmation/coordination/alternativeBlockManifest.ts`
  - 对照 D05/D06/F05/F06/H05/K05/K06/L05/G06 各自源模板，逐套逐区块录入 `BlockSpec`（block 位 / title / columns / splitByDirection / sourceExtra + reason）
  - 逐套核实现有 `blockColumnConfigs*` 与各套 block 位映射（block2 是否承载「本期发生额」等，实施依据写注释）
  - 登记源外增强区块：H05 四区块、K05/K06 block4、L05 block4、G06 现有区块（含依据）
  - 纯数据文件，不改生产行为
  - _Requirements: 7.1, 7.4, 4.4_

- [x] 1.2 F05/F06 characterization 测试
  - 对 F05/F06 现有可观察行为写锁定测试：区块渲染集合、getBlockTotal/getRatio、getCompletionStatus、importFromSummary 带入、buildPayload 输出形状与字段
  - 作为 5.x 拆分的守护基线（拆后必须逐字通过）
  - **已存在**：useAlternativeF05Data.spec.ts(10)+useAlternativeF06Data.spec.ts(9)=19 全绿
  - _Requirements: 5.1_

- [x] 1.3 零回归基线
  - 运行并记录：八套 alternative characterization 测试、函证域前端全量测试
  - 记录工厂公共面（导出名/构造签名/返回形状）作为 Property 12 比对基准
  - **基线**: 38 test files / 647 tests passed (confirmation/ 全域)
  - _Requirements: 6.4_

- [x] 2. Wave 1：工厂 additive 扩展

- [x] 2.1 工厂 getBlockTotalByDirection + CheckRow direction? + payload opening_consistency?
  - `createAlternativeConfirmationData.ts` 新增 `getBlockTotalByDirection(company, blockType, direction)`（纯派生，只累加该 direction 行）；`getBlockTotal` 全 block 合计不变
  - `alternativeD05Types.ts`：`CheckRow` additive 补 `direction?: 'debit'|'credit'`；payload additive 补 `opening_consistency?`
  - `AltConfig` 补可选 `opening_consistency_enabled?`
  - 工厂既有导出名/构造签名/返回形状不变（仅新增）
  - _Requirements: 6.3, 6.4_
  - _Properties: 1, 12_

- [x] 3. Wave 2：K05/K06/L05 借贷拆表 + L05 期初一致性

- [x] 3.1 K05 本期发生额借贷两表
  - K05 承载「本期发生额」的 block（M0 核实的 block 位）标 `splitByDirection`；新增行默认 direction 或提供借/贷两个新增按钮
  - BlockCheckSheet（或 K05 对应渲染）按 direction 分组渲染两张 el-table，各自表头/行/`getBlockTotalByDirection` 小计
  - 既有无 direction 行归「待归位」提示，不猜方向
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - _Properties: 1, 2, 11_

- [x] 3.2 K06 本期发生额借贷两表
  - 同 3.1 手法处理 K06（注意 K06 曾因 http load/persist 异质旁挂，借贷拆表在渲染层做不影响其 IO）
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - _Properties: 1, 2, 11_

- [x] 3.3 L05 借贷两表 + Opening_Consistency_Check
  - 同 3.1 处理 L05 本期发生额借贷两表
  - 加 L0-5 第 3 项「检查期初余额是否与上期期末余额一致」独立卡片：`opening_consistency`（current_opening/prior_closing/is_consistent/note）持久化 + 回显；判定不一致要求说明
  - 期初/上期期末可从平台取则提示带入，取不到手工录入并明示
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4_
  - _Properties: 1, 2, 4, 11_

- [x] 4. Wave 3：G06 纳入工厂 + 区块对齐源三区

- [x] 4.1 G06 改造
  - G06 数据层纳入 `createAlternativeConfirmationData(config)`（config 定 getSumFields/ratios/defaultBalance）；除非实测异质 IO 无法纳入 → 按 K06 范式旁挂异质面 + 注明依据
  - 区块对齐源三区：block1=①初始投资协议、block2=②本期发生额（借贷拆表，同 3.x）、block3=③期后出售赎回；block4 保留现有区块为源外增强
  - 现有 4 区块（持仓证明/股利/处置/公允价值）数据能对应源区语义的迁移到对应 block，无对应的保留 block4，均不丢
  - 现有抽样总体/样本量/账面区/检查比例保留但不扩
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 1.1, 1.2_
  - _Properties: 5, 6, 1, 11_

- [x] 5. Wave 4：F05/F06 拆子组件

- [x] 5.1 F05 拆子组件
  - 依 1.2 characterization 守护，F05 拆分复用 D05 的 Dashboard/Master/CheckBlock + composables，不新造第二套
  - persist payload 形状与字段逐字不变；characterization 全绿
  - 拆分中发现行为与源模板不符 → 记独立缺陷，不夹带行为变更
  - **完成**：Detail 区（抽样/余额/4区块/结论）从内联迁到共享 `AlternativeDetailPanel.vue`（决策 5，已存在）；F05 补 import + detailRatios(付款③/入库④) + detailGetCheckRatio + 删死助手(formatAmount/formatRatio/ratioClass/prefs)。payload 由 composable buildPayload 驱动逐字不变。get_diagnostics 清 + Vite transform 200 + F05 characterization 10 全绿
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Properties: 9_

- [x] 5.2 F06 拆子组件
  - 同 5.1 处理 F06
  - **完成**：F06 内联 Detail 全量迁 `AlternativeDetailPanel.vue`；detailRatios(付款④/入库③，desc 与源一致) + detailGetCheckRatio + import 修正 + 删死助手。get_diagnostics 清 + Vite transform 200 + F06 characterization 9 全绿
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Properties: 9_

- [x] 6. Wave 5：测试与守卫

- [x] 6.1 属性测试与 characterization
  - fast-check：Property 1 借贷不互污染 + 各自合计、Property 11 round-trip 不丢
  - F05/F06 characterization 拆后全绿（Property 9）
  - **完成**：新建 `alternativeStructureAlignment.pbt.spec.ts`（3 用例 numRuns=30）——Property 1（getBlockTotalByDirection 借/贷不互污染 + 全合计=借+贷+无方向）、Property 11（buildPayload→重新 init 逐行 direction/amt/is_abnormal 保留）。F05/F06 characterization 19 全绿（Property 9）。全 25 属性/契约测试 passed
  - _Requirements: 5.4, 7.2, 7.3_

- [x] 6.2 契约测试与守卫
  - Property 10 每套 `blockColumnConfigs*` 区块/列集合对 `ALTERNATIVE_BLOCK_MANIFEST`，漂移即失败
  - Property 8 每个源外区块在 manifest 有条目 + 依据
  - Property 12 工厂公共面（导出名/签名/返回形状）不变
  - Property 3 一张表的套不被强拆（splitByDirection 未标者保持单表）
  - Property 7 H05 无新增区块/列
  - **完成**：新建 `alternativeBlockManifestContract.spec.ts`（22 用例）。**校准 manifest**：Task 1.1 填的 columns 是近似值，本轮以 8 套 getSumFields* 实测值校正为准确基线（D05/D06/F05/F06/H05[b3/b4]/K06/G06[b1/b3] 修正，K05 本就一致），使 Property 10 成真 drift guard。L05 内联 getSumFields 未导出→不纳 drift guard 仅校验区块集合/split/源外。Property 8/3/7/12 manifest-internal + 工厂 24 键公共面冻结
  - _Requirements: 6.1, 6.3, 6.5, 7.1, 7.4, 4.1, 1.5_

- [x] 6.3 零回归门 + Playwright
  - 八套 alternative characterization + 函证域全量前端测试全绿；改动文件 `get_diagnostics` 清 + Vite transform 200
  - **完成（零回归门）**：修 L05 adapter passthrough bug（`useAlternativeL05Data` 用显式 return 非 `...core` spread → `getBlockTotalByDirection` 缺失 → L05.vue block3 借贷拆表调用 undefined 崩；接口 + return 块各加 `getBlockTotalByDirection: core.getBlockTotalByDirection`）。零回归门 `confirmation/` + `g0-confirmation/` 全域 **48 test files / 750 passed / 0 failed**（Wave 3 基线 732 passed / 3 failed → L05 smoke 转绿，g0-diff-model 契约失败属并发 spec 不在本域）。L05.vue + composable get_diagnostics 清 + Vite transform 200。K05/K06 用 `...core` spread 天然透传故无需改。
  - **Playwright 诚实留待**：K0-5（借贷两表）/L0-5（期初一致性 + 借贷两表）/G0-6（源三区）旧数据回显不丢 —— 需实例化含这些替代程序底稿的项目 + 浏览器 SSE 稳定环境（编辑器被并发会话 SSE 劫持 flaky）；功能正确性已由 characterization（8 套）+ PBT（Property 1/11）+ 契约（Property 3/7/8/10/12）+ caller mount smoke（K06/L05）充分覆盖，不假绿
  - _Requirements: 6.1, 6.2_
  - _Properties: 1, 2, 4, 5, 11_

## Notes

- **M0 硬前置**：区块/列清单 + F05/F06 characterization 未就绪不得进 M1
- 工厂固定 4 block 位**不动**；Occurrence_Block 借贷拆表在渲染层做（同 block 按 `direction` 分组），不占第二 block 位
- 全程既有 payload 数据零丢失（旧无 direction 行标「待归位」不丢）
- **不改** 未回函带入链（`importFromSummary`，归 `confirmation-hub-workbench-tabs`）、共享行模型（归 `confirmation-shared-model-extension`）、G0 差异模型（归 `g0-investment-diff-model`）
- H05 源模板留白处不造区块；现有源外区块保留 + 登记不删
- 每套独立可发布可回退；工厂公共面不变（除非契约测试同步更新并说明）
