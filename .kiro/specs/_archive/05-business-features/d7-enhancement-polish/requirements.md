# Requirements: D7 合同负债底稿增强打磨

## Introduction

D7 模块（d7-contract-liabilities）10 tab / 16 composable 已全量完成。本轮对齐 D5/D6 已做改进，按优先级实现 7 项增强。不改后端 / 不加依赖 / composable 仅 additive。

## Requirements

### Requirement 1: D7 主入口 saveImmediate 触发版本快照

**EARS:** WHEN 子组件调用 saveImmediate 成功保存单条 item 后, THE system SHALL 调用 scheduleAutoSnapshot 触发版本链快照（对齐 D6 已修复范式）。

### Requirement 2: D7-2 明细表列设置 ⚙ popover

**EARS:** WHEN D7-2 明细表显示多列横向滚动时, THE system SHALL 提供列设置 popover（⚙ 图标按钮），允许用户按组/单列 checkbox 显隐列，偏好存 localStorage `d7-detail-column-prefs`，提供重置默认按钮。

### Requirement 3: D7-4 分析性复核与 TB 发生额自动勾稽

**EARS:** WHEN D7-4 分析性复核加载数据后, THE system SHALL 在表格上方展示勾稽校验提示（el-alert），比较 D7-4 借方合计 vs TB 2205 借方发生额、贷方合计 vs TB 2205 贷方发生额，差异≠0 时黄色警告。

### Requirement 4: D7-3 调整分录补审计目标 el-alert

**EARS:** WHEN D7-3 调整分录 tab 渲染时, THE system SHALL 在编制提示下方展示审计目标 el-alert。

### Requirement 5: D7-7 凭证检查补结论模板 select

**EARS:** WHEN 审计师完成 D7-7 凭证检查后, THE opinion-card 中审计结论区 SHALL 提供结论模板 el-select（5 个预设结论），选后填入 conclusion textarea 并可编辑。

### Requirement 6: D7-5 长期挂账 ↔ D7-2 勾稽校验

**EARS:** WHEN D7-5 长期挂账检查加载数据后, THE system SHALL 在工具栏下方展示勾稽提示，比较 D7-5 期末余额合计 vs D7-2 中账龄>1年的合计，差异时黄色警告。

### Requirement 7: D7-6 关联方补公允价值结构化判断

**EARS:** WHEN 审计师检查 D7-6 关联方交易时, THE 每行 SHALL 包含"是否公允"下拉 + "判断依据"输入列，底部提供"关联方交易公允性总结"textarea + AI辅助。
