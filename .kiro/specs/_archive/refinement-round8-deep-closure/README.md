# Round 8：深度闭环与一致性收敛

## 主题

基于 GLOBAL_REFINEMENT_PROPOSAL_v2.md，聚焦：
1. 业务闭环断点修复（四表穿透 4 个断点）
2. 弹窗/消息/Toast 三层规范统一
3. 5 角色核心功能深化（签字决策面板 / QcHub / ShadowCompareRow / WorkpaperSidePanel / ManagerDashboard）
4. 数值处理 / 年度上下文 / 权限铺设 / 容灾

## Sprint 划分

- **Sprint 1（P0，1 周）**：快速修复 6 项 + 基础设施
- **Sprint 2（P1，3 周）**：核心角色功能 14 项

## 依赖

- v1 路线图 P0/P1 已完成（R7 Sprint 1-3）
- statusMaps 已删、navItems 已 computed、GtPageHeader 12 视图已接入
- 后端 2830 tests / 0 errors，vue-tsc 0 errors

## 验证方式

- vue-tsc --noEmit 0 errors
- python -m pytest backend/tests/ 0 collection errors
- 5 角色 UAT 穿刺清单（见 v2 §10）
- CI lint 基线只减不增
