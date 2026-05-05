# Architecture Decision Records

本目录记录重要的架构决策。每条决策按时间顺序编号，状态遵循：Proposed → Accepted → (Superseded by XXX)。

| ID | Title | Status | Date |
|----|-------|--------|------|
| ADR-001 | — | 编号预留历史决策 | - |
| ADR-002 | — | 编号预留历史决策 | - |
| ADR-003 | [复核意见↔工单联动的事务策略差异](003-review-issue-transaction-strategy.md) | Accepted | 2026-05-08 |

## 新增流程

1. 选择下一个可用编号（当前：ADR-004）
2. 创建文件 `NNN-short-kebab-title.md`，内容结构：
   - Status（Proposed/Accepted/Deprecated/Superseded）
   - Context（决策背景）
   - Decision（决策本身）
   - Consequences（正向/反向后果）
3. 更新本 README 的索引表
