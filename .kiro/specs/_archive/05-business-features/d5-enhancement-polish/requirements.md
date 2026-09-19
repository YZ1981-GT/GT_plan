# Requirements: D5 应收款项融资底稿增强打磨

## Introduction

D5 模块（d5-receivables-financing）已全量完成（24 tasks all [x]），架构清晰、persistence 无 bug。本轮为**内容丰富度打磨**，按优先级实现 7 项改进，不改架构/不改后端契约/不加新依赖。

## Requirements

### Requirement 1: D5-2 明细表列设置 ⚙ popover

**EARS:** WHEN D5-2 明细表显示 17 列横向滚动时, THE system SHALL 提供列设置 popover（⚙ 图标按钮），允许用户按组/单列 checkbox 显隐列，偏好存 localStorage `d5-detail-column-prefs`，提供重置默认按钮，默认隐藏低频列（期初AJE/RJE、OCI减值、期末OCI减值）。

### Requirement 2: D5TabDetail 补审计结论字段

**EARS:** WHEN 审计师在 D5-2 明细表编制审计意见时, THE opinion-card SHALL 包含"审计说明"和"审计结论"双区段（各带 🤖AI辅助 + 💬复核按钮），结论区绑定 `D5-2-note-conclusion` item_id，使用 debouncedSave 持久化。

### Requirement 3: D5-2 ↔ D1-6 / D2-13 勾稽校验提示

**EARS:** WHEN D5-2 明细表数据加载完成后, THE system SHALL 在工具栏下方显示勾稽校验行（el-alert type=success/warning），比较 D5-2 中"应收票据"合计 vs D1-6 出售模式票据合计、D5-2 中"应收账款"合计 vs D2-13 出售模式账款合计，差异≠0 时黄色警告。

### Requirement 4: D5-4 公允价值到期预警统计卡片

**EARS:** WHEN D5-4 公允价值测算表有数据行时, THE system SHALL 在表格上方展示统计卡片区（flex 布局 3 个 el-statistic），分别统计"已逾期"（剩余天数≤0）、"30天内到期"（0<天数≤30）、"正常"（天数>30）的笔数和金额。

### Requirement 5: D5-4 公允价值方法论琥珀块

**EARS:** WHEN 审计师查看 D5-4 公允价值测算区域时, THE system SHALL 在审计目标 alert 下方展示一个方法论上下文块（琥珀色左边线+浅黄背景 details 可折叠），内容覆盖 CAS22 FVOCI 分类条件、贴现法估值依据、公允价值层次判定标准（第二/三层次）。

### Requirement 6: 附注披露补金融资产风险敞口节（上市公司版）

**EARS:** WHEN 上市公司版附注显示且用户查看 Section 3（说明）时, THE system SHALL 将第 3 节改为"金融资产风险敞口"结构化表格（信用风险最大敞口=账面金额、集中度前五名占比），保留原说明 textarea 作为补充文本。

### Requirement 7: D5-4 利率合理性对比参考

**EARS:** WHEN 审计师评价贴现利率合理性时, THE D5-4 审计说明区域 SHALL 在 textarea 上方提供一个可折叠的"利率参考"区（details 蓝色主题），内嵌 2×3 grid 展示参考利率来源（央行LPR / 同业贴现率 / SHIBOR / 被审计单位采用率），各项为只读 el-input 可手动填写参考值。
