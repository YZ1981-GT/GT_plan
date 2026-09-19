# Tasks: D7 合同负债底稿增强打磨

## Overview

7 项增强对齐 D5/D6 标准，按优先级执行。

## Tasks

- [x] 1. D7 主入口 saveImmediate 触发快照
  - [x] 1.1 在 GtD7ContractLiabilities.vue 包装 saveImmediate
    - 新建 saveImmediateWithSnapshot wrapper（await saveImmediate + scheduleAutoSnapshot）
    - 所有子组件 :save-immediate prop 改为 saveImmediateWithSnapshot（8处）
    - _Requirements: 1_

- [x] 2. D7-2 明细表列设置 ⚙ popover
  - [x] 2.1 创建 `composables/useD7DetailColumnPrefs.ts`
    - 套 D5/D6 范式，6分组，DEFAULT_HIDDEN，localStorage 'd7-detail-column-prefs'
    - _Requirements: 2_

  - [x] 2.2 在 D7TabDetail.vue 接入列设置
    - toolbar-right 加 ⚙ el-popover
    - 非核心列加 v-if="isColVisible('key')"
    - _Requirements: 2_

- [x] 3. D7-4 分析性复核 TB 勾稽
  - [x] 3.1 在 D7TabAnalysis.vue 加勾稽校验
    - 从 allResponses 读 TB 2205 借方/贷方发生额
    - computed 比对表内 debitTotal/creditTotal vs TB 值
    - 差异时 warning el-alert，一致时 success，无 TB 数据时 info
    - _Requirements: 3_

- [x] 4. D7-3 调整分录补审计目标
  - [x] 4.1 在 D7TabAdjustment.vue 编制提示下方加审计目标 el-alert
    - _Requirements: 4_

- [x] 5. D7-7 凭证检查结论模板
  - [x] 5.1 在 D7TabVoucherCheck.vue 补结论模板 el-select
    - 5 个预设结论，选后填入 conclusion textarea
    - _Requirements: 5_

- [x] 6. D7-5 长期挂账 ↔ D7-2 勾稽
  - [x] 6.1 在 D7TabLongTerm.vue 加勾稽校验
    - 从 allResponses 读 D7-2-rows 筛选账龄>1年合计
    - 与 D7-5 自身 rows 期末余额合计比对
    - 差异时 warning，D7-2 无数据时 info
    - _Requirements: 6_

- [x] 7. D7-6 关联方公允判断
  - [x] 7.1 在 D7TabRelatedParty.vue 补公允判断列和总结区
    - el-table 加"是否公允"列 + "判断依据"列
    - 底部加"关联方交易公允性总结"textarea + AI辅助
    - _Requirements: 7_
