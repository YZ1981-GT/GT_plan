# Spec B (R10) — Linkage & Tokens · Tasks

**版本**：v1.0
**起草日期**：2026-05-16
**关联**：`requirements.md` v1.0 + `design.md` v1.0
**总工时**：22 个工作日（3 周 + Sprint 0 半天）

---

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-16 | tasks 初稿，4 Sprint × 22 任务 |

---

## 任务总览

| Sprint | 工时 | 范围 |
|--------|------|------|
| Sprint 0 | 0.5 天 | 启动条件核验 + gt-tokens.css 补完 + stylelint 装机 |
| Sprint 1 | 1 周 | 字号 token 化 4 批 + stylelint 转 error |
| Sprint 2 | 1 周 | 颜色 token 化 4 批 + 背景 token 化 4 批 |
| Sprint 3 | 1 周 | GtEditableTable 拆分 + 右键穿透补完 + CI baseline |
| Sprint 4 (UAT) | 0.5 天 | 上线前全量 UAT 跑 10 项验收 |

---

## Sprint 0 — 启动条件核验（0.5 天）

- [ ] 0.1 grep 实测 9 项 baseline
  - 输出 console 报告（11 个变量）：N_font_size_px / N_color_hex / N_bg_hex / N_el_table_naked / N_gt_editable_table_users / N_gt_extend_users / N_misstatements_ctx / N_adjustments_ctx / N_stylelint_installed
  - 写入 `.github/workflows/baselines.json` 初始值
  - **依赖**：requirements §1 量化快照；不能凭 v3 文档引用

- [ ] 0.2 gt-tokens.css 颜色变量补完
  - 添加灰度 9 阶 + 5 语义色（如已有则跳过）
  - 文件：`audit-platform/frontend/src/styles/gt-tokens.css`

- [ ] 0.3 gt-tokens.css 背景变量新增 6 级
  - `--gt-bg-default/subtle/info/warning/success/danger`

- [ ] 0.4 stylelint 装机（warning 级别）
  - `npm install --save-dev stylelint stylelint-config-standard-vue`
  - 新建 `.stylelintrc.json`（severity=warning）
  - 新建 `npm run stylelint` script

- [ ] 0.5 CI 加 stylelint job（不阻断 PR）
  - `.github/workflows/ci.yml` 新增 `frontend-stylelint` job

---

## Sprint 1 — 字号 token 化 4 批（1 周）

### 1.1 批 1 编辑器 5 视图（1.5 天）

- [ ] 1.1.1 WorkpaperEditor.vue 字号 token 化
  - 验收：grep `font-size:\s*\d+px` 在该文件 = 0
  - 截图对比保留

- [ ] 1.1.2 WorkpaperList.vue 字号 token 化
- [ ] 1.1.3 WorkpaperWorkbench.vue 字号 token 化
- [ ] 1.1.4 DisclosureEditor.vue 字号 token 化
- [ ] 1.1.5 AuditReportEditor.vue 字号 token 化

- [ ] 1.1.6 设计师/合伙人截图对比 5 视图
  - UAT-1 通过

- [ ] 1.1.7 PR 合并 → CI 自动检查 baseline -N

### 1.2 批 2 表格类 6 视图（1.5 天）

- [ ] 1.2.1 TrialBalance.vue 字号 token 化
- [ ] 1.2.2 ReportView.vue 字号 token 化
- [ ] 1.2.3 Adjustments.vue 字号 token 化
- [ ] 1.2.4 Misstatements.vue 字号 token 化
- [ ] 1.2.5 Materiality.vue 字号 token 化
- [ ] 1.2.6 LedgerPenetration.vue 字号 token 化

- [ ] 1.2.7 设计师截图对比 6 视图
  - UAT-2 通过

### 1.3 批 3 Dashboard 系列 6 视图（1 天）

- [ ] 1.3.1 ProjectDashboard.vue 字号 token 化
- [ ] 1.3.2 ManagerDashboard.vue 字号 token 化
- [ ] 1.3.3 PartnerDashboard.vue 字号 token 化
- [ ] 1.3.4 QCDashboard.vue 字号 token 化
- [ ] 1.3.5 EqcrMetrics.vue 字号 token 化
- [ ] 1.3.6 Dashboard.vue 字号 token 化

- [ ] 1.3.7 项目经理/合伙人截图对比 6 视图
  - UAT-3 通过

### 1.4 批 4 剩余视图（1 天）

- [ ] 1.4.1 grep 列出剩余 ~30 视图清单
- [ ] 1.4.2 批量替换 + 抽样人工审查 ≥ 10 视图
- [ ] 1.4.3 verify 全量 `font-size:\s*\d+px` 在 vue 文件中 = 0
- [ ] 1.4.4 baselines.json 更新 `font-size-px-vue-files: 0`

### 1.5 stylelint 转 error（半天）

- [ ] 1.5.1 `.stylelintrc.json` font-size 规则改 `error`
- [ ] 1.5.2 CI `frontend-stylelint` job 改阻断 PR
- [ ] 1.5.3 测试故意提交 `font-size: 14px` 验证 PR 被拒
  - UAT-10 通过（部分）

---

## Sprint 2 — 颜色 + 背景 token 化（1 周）

### 2.1 颜色批 1-4（3 天）

- [ ] 2.1.1 颜色批 1 编辑器 5 视图
- [ ] 2.1.2 颜色批 2 表格类 6 视图
- [ ] 2.1.3 颜色批 3 Dashboard 6 视图
- [ ] 2.1.4 颜色批 4 剩余视图
- [ ] 2.1.5 verify `color:\s*#[0-9a-fA-F]{3,6}` 全量 < 50
- [ ] 2.1.6 baselines.json 更新 `color-hex-vue-files: <实测值>`
- [ ] 2.1.7 设计师视觉验收
  - UAT-4 通过

### 2.2 背景批 1-4（2 天）

- [ ] 2.2.1 背景批 1 编辑器 5 视图
- [ ] 2.2.2 背景批 2 表格类 6 视图
- [ ] 2.2.3 背景批 3 Dashboard 6 视图
- [ ] 2.2.4 背景批 4 剩余视图
- [ ] 2.2.5 verify `background(-color)?:\s*#[0-9a-fA-F]{3,6}` 全量 < 30
- [ ] 2.2.6 baselines.json 更新 `background-hex-vue-files: <实测值>`
- [ ] 2.2.7 设计师视觉验收
  - UAT-5 通过

### 2.3 stylelint 颜色/背景规则启用 error（半天）

- [ ] 2.3.1 `.stylelintrc.json` color/background 规则改 `error`
- [ ] 2.3.2 CI 阻断 PR 测试

---

## Sprint 3 — 组件拆分 + 右键穿透 + CI baseline（1 周）

### 3.1 GtEditableTable 拆分（2 天）

- [ ] 3.1.1 新建 `GtTableExtended.vue`（约 200 行）
  - 列表型，基于 el-table + 紫色表头 + 字号 class + 千分位 + 空状态 + 复制粘贴右键菜单
  - 文件：`audit-platform/frontend/src/components/common/GtTableExtended.vue`

- [ ] 3.1.2 新建 `GtFormTable.vue`（约 250 行）
  - 编辑型，行内编辑 + dirty 标记 + 校验 + 撤销

- [ ] 3.1.3 改 `GtEditableTable.vue` 为兼容 wrapper
  - 根据 `mode` prop 路由
  - `console.warn` 提示迁移路径

- [ ] 3.1.4 单测 `GtTableExtended.spec.ts` 5 用例
  - 列渲染 / 千分位 / 空状态 / 复制粘贴 / 紫色表头 class

- [ ] 3.1.5 单测 `GtFormTable.spec.ts` 5 用例
  - 行内编辑 / dirty 标记 / 校验 / 撤销 / 兼容 wrapper

- [ ] 3.1.6 现有 3 使用方零回归测试
  - Adjustments.vue 粘贴/撤销/dirty
  - InternalTradeSheet.vue 行为
  - InternalCashFlowSheet.vue 行为
  - UAT-6 通过

- [ ] 3.1.7 文档化 `docs/COMPONENT_USAGE_GUIDE.md`
  - 决策树 + 3 个使用示例

### 3.2 右键穿透补完（2 天）

- [ ] 3.2.1 后端 grep 实测 `related-workpapers` 端点
  - 如缺则建 helper `find_workpapers_by_account_codes`
  - 文件：`backend/app/services/workpaper_query.py`

- [ ] 3.2.2 后端 misstatements 端点（按需新建）
  - `GET /api/projects/{pid}/misstatements/{id}/related-workpapers`
  - 文件：`backend/app/routers/misstatements.py`

- [ ] 3.2.3 后端 adjustments 端点（按需新建）
  - `GET /api/projects/{pid}/adjustments/{group_id}/related-workpapers`
  - 文件：`backend/app/routers/adjustments.py`

- [ ] 3.2.4 集成测试
  - `backend/tests/test_misstatements_related_workpapers.py` 3 用例
  - `backend/tests/test_adjustments_related_workpapers.py` 3 用例

- [ ] 3.2.5 前端 Misstatements.vue 右键菜单接入
  - 引入 CellContextMenu + usePenetrate
  - "📝 查看关联底稿" 菜单项
  - UAT-7 通过

- [ ] 3.2.6 前端 Adjustments.vue 右键菜单接入
  - line_items 行右键
  - UAT-8 通过

### 3.3 CI baseline 4 道卡点完整启用（半天）

- [ ] 3.3.1 CI step `Display token guard` 4 道全开
  - font-size: 0
  - color: < 50
  - background: < 30
  - el-table 裸用: ≤ Sprint 0 实测值

- [ ] 3.3.2 测试 PR 添加裸 `<el-table>` 验证 CI fail
  - UAT-9 通过

### 3.4 视觉回归 + 全量 vue-tsc（半天）

- [ ] 3.4.1 全量 `npx vue-tsc --noEmit` 0 错误
- [ ] 3.4.2 全量 getDiagnostics 0 错误
- [ ] 3.4.3 设计师抽样 30 个核心视图截图对比
- [ ] 3.4.4 GtEditableTable wrapper 60 天观察期开始（监控 console.warn 频率）

---

## Sprint 4 — UAT（0.5 天）

### UAT 验收清单

| # | 验收项 | Tester | Date | Status |
|---|--------|--------|------|--------|
| 1 | 编辑器 5 视图字号 token 化无视觉差异 | 设计师/合伙人 | — | ○ pending |
| 2 | 表格类 6 视图字号 token 化无视觉差异 | 设计师 | — | ○ pending |
| 3 | Dashboard 系列 6 视图字号 token 化无视觉差异 | 项目经理 | — | ○ pending |
| 4 | 颜色 token 化全量验收 | 设计师 | — | ○ pending |
| 5 | 背景 token 化全量验收 | 设计师 | — | ○ pending |
| 6 | GtEditableTable 拆分后 Adjustments 行为零回归 | 审计助理 | — | ○ pending |
| 7 | Misstatements 右键 "查看关联底稿" 跳转正确 | 审计助理 | — | ○ pending |
| 8 | Adjustments 右键 "查看关联底稿" 跳转正确 | 审计助理 | — | ○ pending |
| 9 | CI baseline 4 道卡点全绿 | DevOps | — | ○ pending |
| 10 | stylelint 转 error 后 PR 不能合入新硬编码 | 代码审查者 | — | ○ pending |

**上线门槛**：≥ 8 项 ✓ pass（关键项 6/7/8/9 必须 pass）

---

## 已知缺口与技术债

| ID | 缺口 | 优先级 | 触发条件 | 后续 spec |
|----|------|-------|---------|-----------|
| TD-1 | GtEditableTable wrapper 60 天后未删除 | P2 | 60 天后无 console.warn | Spec D 评估删除时间 |
| TD-2 | 透明度场景 `rgba(...)` 未 token 化 | P3 | CSS color-mix() 兼容性达 95% | Spec D（暗色模式） |
| TD-3 | 字号迁移期间允许 `// stylelint-disable-next-line` 临时豁免 | P2 | Sprint 1 末尾扫描清零 | 本 Sprint 1 末尾扫尾 |

---

## 测试策略

### 单测（vitest）
- `GtTableExtended.spec.ts` 5 用例
- `GtFormTable.spec.ts` 5 用例

### 集成测试（pytest）
- `test_misstatements_related_workpapers.py` 3 用例
- `test_adjustments_related_workpapers.py` 3 用例

### CI baseline 测试
- 每 PR 自动跑 4 道 grep + stylelint

### 视觉回归（人工）
- 设计师 ≥ 30 视图截图对比

---

## 关联文档

- `requirements.md` —— 需求源
- `design.md` —— 架构决策
- `.github/workflows/ci.yml` —— CI 配置
- `.github/workflows/baselines.json` —— baseline 真源
- `audit-platform/frontend/src/styles/gt-tokens.css` —— token 真源
