# Requirements: D6 合同资产底稿增强打磨

## Introduction

D6 模块（d6-contract-assets）12 tab / 17 composable 已全量完成。本轮为**内容丰富度 + 跨tab勾稽自动化**打磨，按优先级实现 8 项改进，不改后端 API / 不加新依赖 / composable 仅 additive 扩展。

## Requirements

### Requirement 1: D6-2 明细表列设置 ⚙ popover

**EARS:** WHEN D6-2 明细表显示 30 列横向滚动时, THE system SHALL 提供列设置 popover（⚙ 图标按钮），允许用户按组/单列 checkbox 显隐列，偏好存 localStorage `d6-detail-column-prefs`，提供重置默认按钮。与现有 el-segmented 列组切换（基础/含账龄）互补——列组切换为粗粒度，⚙为细粒度单列级别。

### Requirement 2: D6-8 ECL ↔ D6-7 政策检查损失率交叉校验

**EARS:** WHEN D6-8 ECL 测算表加载数据后, THE system SHALL 在表格上方展示勾稽校验提示（el-alert），比较 D6-8 各账龄组合的损失率与 D6-7 政策检查中记录的被审计单位公告损失率（从 allResponses 读取 D6-7 相关 item_id），差异超过 1% 时黄色警告。

### Requirement 3: D6-6 检查表补结论模板 select

**EARS:** WHEN 审计师完成 D6-6 检查表细节测试后, THE opinion-card 中的"审计结论"区 SHALL 提供结论模板 el-select（3~5 个预设结论：样本无重大异常 / 发现差异已调整 / 检查比例不足需扩样 / 发现重大差异建议调整 / 其他），选择后填入结论 textarea 并可编辑。

### Requirement 4: D6-1 审定表 AI 辅助按钮

**EARS:** WHEN 审计师在 D6-1 审定表编制审计意见时, THE opinion-card SHALL 在"审计说明"和"审计结论"区段各提供 🤖AI辅助按钮，调用 useD6AiGenerate section='adj-change-analysis' / 'adj-conclusion'。

### Requirement 5: D6-5 关联方公允价值结构化判断

**EARS:** WHEN 审计师检查 D6-5 关联方交易时, THE 每行 SHALL 包含"是否公允"下拉（是/否/待定）和"判断依据"文本输入列，底部提供"关联方交易公允性总结"textarea + AI辅助。

### Requirement 6: D6-4 调整分录补审计目标 el-alert

**EARS:** WHEN D6-4 调整分录 tab 渲染时, THE system SHALL 在编制提示下方展示审计目标 el-alert（"验证调整分录的准确性与完整性，确认借贷平衡且调整事由充分合理"）。

### Requirement 7: D6-9 转回核销 ↔ D6-3 减值明细勾稽校验

**EARS:** WHEN D6-9 转回核销检查表加载数据后, THE system SHALL 在工具栏下方展示勾稽校验提示，比较 D6-9 转回合计 vs D6-3 减值明细转回列合计、D6-9 核销合计 vs D6-3 核销列合计，差异≠0 时黄色警告。

### Requirement 8: D6 主入口 saveImmediate 触发版本快照

**EARS:** WHEN 子组件调用 saveImmediate 成功保存单条 item 后, THE system SHALL 调用 scheduleAutoSnapshot 触发版本链快照（当前仅 saveBatch 触发快照，单条保存不触发）。
