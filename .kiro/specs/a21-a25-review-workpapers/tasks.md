# Implementation Plan

> **分期**：P0(lite) → P1(core) → P2(plus)
> **计数**：P0 6 + P1 5 + P2 3 = **14 任务**

---

## P0 / lite（6 任务）

- [ ] 0. V086 迁移：`projects` 表新增 `audit_type`(VARCHAR DEFAULT 'financial') + `is_large_soe`(BOOLEAN DEFAULT false)
- [ ] 1. 解析 A21-1 xlsx 模板 → 提取检查项 → 生成 `a21_a25_review_definitions.json`（至少 A21-1 完整 15 条）
- [ ] 2. `review_checklist_service.py`：加载定义 + review-context 接口（auto_na 条件判定）
- [ ] 3. `GtReviewChecklist.vue` 重写：角色栏 + 检查项列表(Y/N/NA) + 进度条 + auto_na 灰化
- [ ] 4. checklist_responses 保存（item_id: `{wp_code}-chk-{seq:02d}`）+ debounce 1500ms
- [ ] 5. 后端单元测试（review_checklist_service: 加载定义 + auto_na 判定 + 模板选择）

**DoD**：A21-1 打开 → 15 条检查项渲染 → 勾选→刷新不丢；auto_na 项灰化不可编辑。

---

## P1 / core（5 任务）

- [ ] 6. 扩充 definitions JSON：5 角色 × (财报+内控) = 10 模板完整检查项（从 xlsx 批量解析）
- [ ] 7. 配置驱动模板选择（`select_review_templates` 按 business_category + audit_type + is_large_soe）
- [ ] 8. 复核记录区（textarea，item_id: `{wp_code}-record`）+ 签字按钮（通过/退回）
- [ ] 9. 签字联动：POST review-sign → 写 checklist_responses `{wp_code}-sign` item + 同步 A1 程序表步骤 status
- [ ] 10. 前端 vitest + 后端 pytest（组件渲染 + 签字 API + 配置选择覆盖）

**DoD**：B 类项目打开 A24 → 提示"当前项目类别不适用" + 不渲染。签字通过→A1 对应步骤显示 ✓。

---

## P2 / plus（3 任务）

- [ ] 11. 自动预填建议（底稿完成度 > 95% → 建议勾选相关项，用户可覆盖）
- [ ] 12. Word/xlsx 导出（已勾选→√，NA→N/A，签字区填入人名+日期）
- [ ] 13. Playwright E2E：A21-1 复核流程全链路（勾选→保存→签字→A1 联动验证）

**DoD**：E2E 通过；导出 xlsx 含 √ 标记和签字。

---

## 实施优先级说明

- P0 聚焦**单角色（A21-1）跑通全链路**，验证架构可行性
- P1 **横向扩展**到 5 角色 10+ 子底稿，纯配置增量
- P2 智能辅助 + 导出 + 回归测试
