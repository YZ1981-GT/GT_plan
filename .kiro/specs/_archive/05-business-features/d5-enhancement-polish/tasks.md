# Tasks: D5 应收款项融资底稿增强打磨

## Overview

7 项 presentation-layer 增强，按优先级执行。不改后端/不加依赖/不改 composable 对外接口。

## Tasks

- [x] 1. D5-2 明细表列设置 ⚙ popover
  - [x] 1.1 创建 `composables/useD5DetailColumnPrefs.ts`
    - 定义 COLUMN_GROUPS 分组（核心/期初/本期变动/重分类与调整/OCI减值）
    - DEFAULT_HIDDEN: ['priorAje', 'priorRje', 'ociImpairment', 'endOciImpairment']
    - localStorage key `d5-detail-column-prefs` 读写
    - 导出 isColVisible(key) / toggleCol(key) / resetDefaults() / columnGroups ref
    - _Requirements: 1_

  - [x] 1.2 在 D5TabDetail.vue 接入列设置
    - toolbar-right 加 ⚙ el-popover 按钮（分组 checkbox + 重置默认）
    - 每个 el-table-column 加 `v-if="isColVisible('fieldKey')"` 控制显隐
    - 核心列（类别/明细项目/期末审定/备注/操作）不可隐藏（alwaysShow）
    - _Requirements: 1_

- [x] 2. D5TabDetail 补审计结论字段
  - [x] 2.1 在 D5TabDetail.vue opinion-card 中补"审计结论"区段
    - 新增 `auditConclusion` ref + watch 绑定 `D5-2-note-conclusion` item_id
    - 带 🤖AI辅助按钮（section='detail-conclusion'）+ 💬复核按钮
    - textarea :autosize="{ minRows: 3, maxRows: 7 }"
    - _Requirements: 2_

- [x] 3. D5-2 ↔ D1-6 / D2-13 勾稽校验提示
  - [x] 3.1 在 D5TabDetail.vue 实现勾稽校验提示
    - 从 crossSheet.categoryAggregation 取应收票据/应收账款期末审定合计
    - 从 allResponses 读 `D1-6-sold-total` / `D2-13-sold-total`（D1/D2 可能未录入则显示"暂无数据"）
    - tab-toolbar 下方 el-alert 展示对比结果（一致=绿色/差异=黄色/无数据=蓝色info）
    - _Requirements: 3_

- [x] 4. D5-4 公允价值到期预警统计卡片
  - [x] 4.1 在 D5TabFairValue.vue 加统计卡片区
    - computed 从 rows 分三桶：expired(≤0天) / nearExpiry(1-30天) / normal(>30天)
    - 每桶统计笔数 + 面值合计
    - flex 容器 3 个 el-statistic（已逾期红/即将到期橙/正常绿），放工具栏与表格之间
    - 无数据行时不显示
    - _Requirements: 4_

- [x] 5. D5-4 公允价值方法论琥珀块
  - [x] 5.1 在 D5TabFairValue.vue 审计目标下方加琥珀块
    - `<details class="amber-context">` 可折叠
    - 内容：CAS22 FVOCI分类条件 / 贴现法估值公式依据 / 公允价值层次判定标准
    - 样式：`border-left: 3px solid #e6a23c; background: #fdf6ec;`
    - _Requirements: 5_

- [x] 6. 附注披露补金融资产风险敞口节
  - [x] 6.1 在 D5TabDisclosure.vue 上市公司版 Section 3 改为风险敞口结构化
    - el-table 3行（应收票据/应收账款/合计）× 3列（账面金额从D5-1取/信用风险最大敞口/前五名集中度占比）
    - 集中度为 el-input-number（%），手动填写
    - 保留原"说明"textarea 作为补充文本
    - 数据存 `D5-note-listed-exposure-notes` / `D5-note-listed-exposure-data` item_id
    - _Requirements: 6_

- [x] 7. D5-4 利率合理性对比参考
  - [x] 7.1 在 D5TabFairValue.vue 审计说明区上方加利率参考 details
    - `<details class="guidance-details">` 蓝色主题可折叠
    - 2×3 grid：央行LPR(1Y) / SHIBOR(3M) / 同业贴现率 / 城商行贴现率 / 国股银票贴现率 / 被审计单位采用率
    - 各项 el-input-number :precision="4" :step="0.001"，手动填写参考值
    - 数据存 `D5-4-rate-references` item_id（JSON），debouncedSave
    - _Requirements: 7_
