# Architecture Decision Records

本目录记录重要的架构决策。每条决策按时间顺序编号，状态遵循：Proposed → Accepted → (Superseded by XXX)。

| ID | Title | Status | Date |
|----|-------|--------|------|
| ADR-001 | ~~保留号码不使用~~ | Deprecated | - |
| ADR-002 | ~~保留号码不使用~~ | Deprecated | - |
| ADR-003 | [复核意见↔工单联动的事务策略差异](003-review-issue-transaction-strategy.md) | Accepted | 2026-05-08 |

> **说明**：历史决策未补录 ADR，请从 ADR-004 起编号。001/002/003 三个号码中只有 003 是有效决策，001/002 为占位号码，不再承载任何决策，只保留编号以避免跨仓库交叉引用断链。

## 新增流程

1. 选择下一个可用编号（当前：ADR-004）
2. 创建文件 `NNN-short-kebab-title.md`，内容结构：
   - Status（Proposed/Accepted/Deprecated/Superseded）
   - Context（决策背景）
   - Decision（决策本身）
   - Consequences（正向/反向后果）
3. 更新本 README 的索引表
