# UAT Pending: Spec B — Linkage & Tokens

**Spec ID**：`v3-r10-linkage-and-tokens`
**实施完成日期**：2026-05-16
**Commit**：`a04f2b5` + `99b3570`(G1-G6 修复)
**SLA**：P1 → 14 天内（≤ 2026-05-30）
**当前状态**：8/10 ○ pending-uat + 2/10 ✓ pass

---

## 待真人执行清单

| # | 验收项 | 责任人 | 截止日期 | 状态 |
|---|--------|--------|---------|------|
| 1 | 编辑器 5 视图字号 token 化无视觉差异 | 设计师 + 合伙人 | 2026-05-23 | ○ pending |
| 2 | 表格类 6 视图字号 token 化无视觉差异 | 设计师 | 2026-05-23 | ○ pending |
| 3 | Dashboard 系列 6 视图字号 token 化无视觉差异 | 项目经理 | 2026-05-23 | ○ pending |
| 4 | 颜色 token 化全量验收（1611→0 raw） | 设计师 | 2026-05-23 | ○ pending |
| 5 | 背景 token 化全量验收（712→0 raw） | 设计师 | 2026-05-23 | ○ pending |
| 6 | GtEditableTable 拆分后 Adjustments 行为零回归 | 审计助理 | 2026-05-23 | ○ pending |
| 7 | Misstatements 右键 "查看关联底稿" 跳转正确 | 审计助理 | 2026-05-23 | ○ pending |
| 8 | Adjustments 右键 "查看关联底稿" 跳转正确 | 审计助理 | 2026-05-23 | ○ pending |

## 执行指引

1. 启动前后端：`start-dev.bat`
2. 各责任人按上表逐项验收，截图存档：
   - 字号/颜色/背景：开浏览器 devtools 截图，对比 commit `b4cda44`(Spec A 完成时) 与 `99b3570`(本 spec 完成时) 的视觉差异
   - 右键穿透：在 Misstatements/Adjustments 行右键 "查看关联底稿" → 跳转后核对底稿内容
3. 测试通过 → 编辑 `.kiro/specs/v3-r10-linkage-and-tokens/tasks.md` 把 `○ pending-uat` 改 `✓ pass`
4. 测试不通过 → 改 `✗ fail` + 文字说明 + 报 issue
5. 8 项全 ✓ pass 后 → 删除本文件

## 上线门槛

- ≥ 8 项 ✓ pass
- 关键项 6 / 7 / 8 必须 pass

## 联系人

- 设计师：（待补）
- 项目经理：（待补）
- 审计助理：（待补）
- 合伙人：（待补）
