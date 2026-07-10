# Implementation Plan

## Overview

本任务清单交付三部分：**A. D3-7 预收账款检查表全闭环**（行级附件+OCR+AI+确认+回写、抽凭弹窗联动、异常与跨底稿钩子）；**B. 抽凭引擎方法学增强**（科学样本量、MUS 完整方法学、错报推断与总体结论、总体完整性校验、重要性联动、重抽治理）；**C. 四表库凭证库联动**（抽凭按科目单/多回写、截止性测试基准日±N天一键取数回写、两类回写后 AI 复核弹窗→确认填入审计说明）。实现以扩展既有 `useSamplingAlgorithms`/`useVoucherSampling`/`GtVoucherSamplingEngine` 与 `useD3VoucherCheck`/`D3TabVoucherCheck` 为主，新增字段均为可选以保证向后兼容。可选/后续项（备忘导出、属性抽样、跨循环横向推广）单列。

## Task Dependency Graph

- **Wave 1（纯函数方法学基座，可并行）**：Task 1, 2, 3
- **Wave 2（引擎编排 + 引擎 UI 扩展）**：Task 4, 5（依赖 1~3）
- **Wave 3（D3-7 全闭环 + 截止联动 + 回写后 AI 复核）**：Task 6, 7, 8, 10, 11（依赖 4, 5）
- **Wave 4（后端契约扩展）**：Task 9（可与 Wave 2/3 并行，前端先以现有响应兜底）
- **Wave 5（实测与验收）**：Task 12（依赖全部）
- **Wave 6（可选/后续）**：Task 13, 14

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "3"], "dependsOn": [] },
    { "wave": 2, "tasks": ["4", "5"], "dependsOn": [1] },
    { "wave": 3, "tasks": ["6", "7", "8", "10", "11"], "dependsOn": [2] },
    { "wave": 4, "tasks": ["9"], "dependsOn": [] },
    { "wave": 5, "tasks": ["12"], "dependsOn": [3, 4] },
    { "wave": 6, "tasks": ["13", "14"], "dependsOn": [5] }
  ]
}
```

## Tasks

- [ ] 1. 抽样方法学纯函数（useSamplingAlgorithms 扩展）
  - 在 `composables/useSamplingAlgorithms.ts` 新增：`reliabilityFactor`、`computeMusInterval`、`computeSampleSize`、`markHighValueItems`；扩展 `SamplingConfig`(confidenceLevel/tolerableMisstatement/expectedMisstatement/suggestedSampleSize/resampleReason) 与 `SampledVoucher`(isHighValue/actualMisstatement)
  - 内置 CAS 1314 泊松可信赖度系数常量表（95%→3.0 / 90%→2.3 等 + tainting 增量因子）；金额用 Decimal 字符串运算
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 17.1, 17.2, 17.3, 17.4, 20.1_

- [ ] 2. 错报推断与总体结论纯函数
  - 新增 `projectMisstatement`(MUS 污染率×间隔 + 高值层已知错报 / 经典比率估计)、`computeUpperMisstatementLimit`(基本准备+增量准备)、`deriveSamplingConclusion`(UML vs tolerable)、`reconcilePopulation`
  - 扩展 `validateSamplingConfig`：统计法 confidence/tolerable 必填、expected<tolerable
  - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 19.1, 19.2, 19.3, 20.2, 20.3_

- [ ] 3. 纯函数属性测试（PBT）
  - 新建 `composables/__tests__/useSamplingMethodology.pbt.spec.ts`，覆盖设计文档 Property 1~12（含既有 applyFillMode/computeVersionDiff 回归、截止窗口 filterByCutoffWindow/markCutoffCrossPeriod），hypothesis/fast-check max_examples≈5
  - _Requirements: 15.1, 17.2, 18.2, 18.4, 18.5, 19.2, 20.2, 25.1, 25.5_

- [ ] 4. 引擎编排 composable 扩展（useVoucherSampling）
  - 承接新参数（置信度/可容忍/预期错报）与建议样本量留痕；`loadTolerableMisstatement(projectId)` 从重要性/B15 取数（失败允许手填）
  - 错报推断状态（actualMisstatement 录入 → projectMisstatement → UML → conclusion）；重抽原因必填；seed 展示；历史不覆盖
  - cutoff-fill/voucher-history 载荷扩展（前端侧字段），后端未就绪时兼容兜底
  - _Requirements: 15.3, 15.4, 16.1, 16.2, 16.3, 18.1, 22.1, 22.2, 22.3_

- [ ] 5. 抽凭引擎 UI 扩展（GtVoucherSamplingEngine + 子对话框）
  - `SamplingConfigDialog`：新增置信度/可容忍错报/预期错报录入 + 建议样本量展示与覆盖 + 参数校验提示
  - 引擎主体：MUS 抽样间隔展示 + 高值必选标识列；总体完整性校验区（总体↔账面差异告警）；错报推断区（录入实际错报→UML→结论建议，人工确认）
  - `SamplingHistoryDrawer`：回显 seed / 重抽原因 / 间隔 / 结论
  - _Requirements: 17.1, 17.4, 18.5, 18.6, 18.7, 19.1, 19.3, 20.1, 22.2_

- [ ] 6. D3-7 行级附件 + OCR 闭环（useD3VoucherCheck 扩展）
  - 新增 `OCR_FIELD_MAP`/`mapOcrToVoucherFields`/`handleRowOcr`（复用 `/d4/contract-ocr` 范式 → ElMessageBox 确认 → merge 保留已填值 → 低置信度标注）
  - `D3TabVoucherCheck.vue` 两区块每行加 📎 附件列（图片/PDF，只读禁用，类型校验）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [ ] 7. D3-7 抽凭弹窗联动 + AI 辅助
  - `D3TabVoucherCheck.vue` 以 dialog-mode 接入 `GtVoucherSamplingEngine`（account-code=2203, phase）；`onSampleFilled` → `fillFromSampling`（append/replace/merge 复用 applyFillMode 语义）→ 行 `source='抽凭'`
  - 检查结论区 🤖 AI（voucher-conclusion，建议→确认→写入，不可用提示）；VoucherCheckRow 增 source/actualMisstatement 字段
  - ref 解包用 toRef；只读禁用抽样回填；抽样按当前底稿绑定科目(2203)检索四表库凭证库，选定单/多条一次性回写并标注来源=抽凭
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 10.1, 10.2, 10.3, 10.4, 12.1, 12.2, 12.3, 24.1, 24.2, 24.3, 24.4, 24.5_

- [ ] 8. D3-7 异常标记与跨底稿联动 + 覆盖率反馈
  - 异常类型点选（跨期疑点/金额异常/无原始凭证/对方科目异常/重复入账，沿用已做的 filterable select）；跨期疑点保留 → D4 可追溯标识；异常汇总至 A13 可追溯标识
  - 覆盖率/异常率反馈在检查表汇总区展示
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 11.1, 11.2, 11.3, 11.4_

- [ ] 9. 后端 sampling 端点契约扩展
  - `voucher-extract` 响应加 `items[].high_value`、`stats.book_amount`；`cutoff-fill` 请求加方法学字段（confidence/tolerable/expected/interval/resample_reason）；`voucher-history` 回显 seed/间隔/重抽原因/结论
  - 迁移/契约测试保持向后兼容（新增字段可选）；不新增路由
  - _Requirements: 17.2, 19.2, 22.1, 22.2, 22.3_

- [ ] 10. 截止性测试凭证联动（useCutoffAutoSampling 扩展）
  - 扩展 `composables/useCutoffAutoSampling.ts`：基准日 ±N 天窗口 `filterByCutoffWindow`、跨期判定 `markCutoffCrossPeriod`（纯函数）；截止底稿工具栏"一键取数"（cutoffDate + daysBefore/daysAfter + 科目/方向/金额）→ 检索四表库凭证库 → 回写截止底稿，跨期行标注跨期疑点；只读禁用
  - _Requirements: 25.1, 25.2, 25.3, 25.4, 25.5, 25.6_

- [ ] 11. 回写后 AI 复核弹窗（检查表 + 截止共用）
  - 新建 `voucher-sampling/PostFillAiReviewDialog.vue`：回写完成弹出"是否发起 AI 复核"→ `POST /ai/generate-text`(section=voucher-review/cutoff-review, context=回写凭证)→ 展示意见 → 确认填入审计说明 / 取消不写入；AI 不可用提示不阻断；确认前不定稿
  - D3-7 抽凭回写后 + 截止一键取数回写后分别触发；后端 section 白名单加 voucher-review/cutoff-review
  - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8_

- [ ] 12. 集成验证与 Playwright 实测
  - D3 vitest 全绿（含新 PBT Property 1~12）；`get_diagnostics` 零错误
  - Playwright 实测 D3-7：打开抽凭弹窗→配置方法学参数→抽样(含高值必选/间隔)→勾选→回填(来源=抽凭)→行级📎OCR确认→录入错报→查看结论建议→回写后 AI 复核弹窗→确认填入审计说明→保存；截止性测试：设基准日±N天→一键取数→回写(跨期标注)→AI复核弹窗；0 console error + postgres 落库校验
  - _Requirements: 1.1, 2.4, 4.2, 7.6, 18.5, 19.1, 25.4, 26.5_

- [ ] 13. 抽样计划与结论备忘导出（可选）
  - `Sampling_Memo` 导出（方法/参数/样本量依据/覆盖率/错报推断/结论）
  - _Requirements: 21.1, 21.2_

- [ ] 14. 属性抽样扩展 + 横向推广（可选/后续）
  - `computeAttributeSampleSize`/`evaluateDeviationRate`（控制测试，不破坏金额法）
  - 按 D3-7 样板对齐其他循环检查表（D2-7/G4-13/G5-12/G6/G7-18/G8-6/G9-6/G10-7/G12-6/G2/G3/F2），复用同一引擎，按科目编码接入
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 14.1, 14.2, 14.3, 23.1, 23.2, 23.3_

## Notes

- **复用优先**：新增能力以纯函数 + 可选配置字段 + 端点字段扩展加入，既有五方法/覆盖率/CAS1314/版本diff/历史/撤销/回填三模式/字段留痕/随机种子全部保留。
- **立场铁律**：OCR/AI/抽样结论一律"建议→人工确认→写入"；点选优先；跨循环共享同一引擎；D3-7 子 tab 用 `toRef` 处理 ref 解包。
- **边界**：必做 = Task 1~12（含四表库凭证库联动、截止性测试凭证联动、回写后 AI 复核弹窗）；可选/后续 = Task 13~14（备忘导出、属性抽样、跨循环推广）。不重复 `ui-pattern-unification` 的通用工具栏迁移与全局 collapse→dialog。
- **金额运算**：统一 Decimal 字符串，避免浮点误差。
