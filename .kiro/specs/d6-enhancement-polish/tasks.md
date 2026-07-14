# Tasks: D6 合同资产底稿增强打磨

## Overview

8 项 presentation-layer + 勾稽自动化增强，按优先级执行。

## Tasks

- [ ] 1. D6-2 明细表列设置 ⚙ popover
  - [ ] 1.1 创建 `composables/useD6DetailColumnPrefs.ts`
    - 定义 COLUMN_GROUPS 分组（核心/期初/本期变动/期末调整/账龄/期后）
    - DEFAULT_HIDDEN: ['priorAje','priorRje','endAje','endRje','postPeriodDate']
    - localStorage key `d6-detail-column-prefs` 读写
    - 导出 isColVisible / toggleCol / resetDefaults / columnGroups
    - 套 D5 useD5DetailColumnPrefs 范式
    - _Requirements: 1_

  - [ ] 1.2 在 D6TabDetail.vue 接入列设置
    - toolbar-right 加 ⚙ el-popover 按钮（分组 checkbox + 重置默认）
    - 非 alwaysShow 列加 `v-if="isColVisible('key')"` 控制显隐
    - 与现有 el-segmented 列组切换互补不冲突
    - _Requirements: 1_

- [ ] 2. D6-8 ECL ↔ D6-7 政策检查损失率勾稽
  - [ ] 2.1 在 D6TabEclCalculation.vue 加勾稽校验
    - 从 allResponses 读 D6-7 政策评价中的损失率数据（item_id 模式 `D6-7-eval-*`）
    - computed 比对 D6-8 各组合 lossRate vs D6-7 对应值
    - 差异>1% 时 warning el-alert，一致时 success，D6-7 无数据时 info
    - 放在工具栏下方、ECL 表格上方
    - _Requirements: 2_

- [ ] 3. D6-6 检查表结论模板 select
  - [ ] 3.1 在 D6TabInspection.vue 补结论模板
    - 定义 CONCLUSION_TEMPLATES 数组（5 个预设结论）
    - opinion-card 审计结论区加 el-select（选后填入 conclusion textarea）
    - 选择后仍可手动编辑
    - _Requirements: 3_

- [ ] 4. D6-1 审定表 AI 辅助按钮
  - [ ] 4.1 在 D6TabAdjudication.vue 确认/补齐 AI 按钮
    - 检查 opinion-card 中审计说明/结论区是否有 🤖AI辅助 按钮
    - 如缺失：import useD6AiGenerate + 补按钮 section='adj-change-analysis'/'adj-conclusion'
    - 如已有：仅验证功能正确
    - _Requirements: 4_

- [ ] 5. D6-5 关联方公允价值结构化判断
  - [ ] 5.1 在 D6TabRelatedParty.vue 补公允判断列和总结区
    - el-table 加"是否公允"列（el-select: 是/否/待定）+ "判断依据"列（el-input）
    - 数据存 row.isFairValue / row.fairValueBasis（additive 字段，不影响现有序列化——已有 ...r 展开透传）
    - 底部加"关联方交易公允性总结"textarea + 🤖AI辅助按钮
    - _Requirements: 5_

- [ ] 6. D6-4 调整分录补审计目标 el-alert
  - [ ] 6.1 在 D6TabAdjustment.vue 编制提示下方加审计目标
    - `<el-alert type="info" :closable="false" title="审计目标：验证调整分录的准确性与完整性，确认借贷平衡且调整事由充分合理。" class="objective-alert" />`
    - 加 `.objective-alert { margin-bottom: 12px; }` 样式
    - _Requirements: 6_

- [ ] 7. D6-9 转回核销 ↔ D6-3 勾稽校验
  - [ ] 7.1 在 D6TabWriteoffCheck.vue 加勾稽校验
    - 从 allResponses 读 D6-3 减值明细的转回列/核销列合计（item_id 模式 `D6-3-*`，解析 rows JSON 累加对应字段）
    - computed 比对 D6-9 reversalRows 金额合计 vs D6-3 转回合计、writeoffRows 合计 vs D6-3 核销合计
    - 差异≠0 时 warning el-alert，一致时 success，D6-3 无数据时 info
    - 放在工具栏下方
    - _Requirements: 7_

- [ ] 8. D6 主入口 saveImmediate 触发快照
  - [ ] 8.1 在 GtD6ContractAssets.vue 包装 saveImmediate
    - 新建 `saveImmediateWithSnapshot` 包装函数：await saveImmediate(itemId, data) + scheduleAutoSnapshot()
    - 将所有子组件的 `:save-immediate` prop 改为 `saveImmediateWithSnapshot`
    - _Requirements: 8_
