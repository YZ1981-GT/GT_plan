# Spec B (R10) — Linkage & Tokens · Requirements

**版本**：v1.0
**起草日期**：2026-05-16
**状态**：🟡 立项规划完成，待启动条件满足后正式实施
**关联文档**：`docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md` §7.6 / §8 / §9
**前置依赖**：v3 P0 全清 ✅ + Spec A 上线观察 ≥ 7 天稳定

---

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|---------|
| v1.0 | 2026-05-16 | 三件套初稿（基于 README 立项规划扩展） | 用户要求"分别生成各自的三件套" |
| v1.1 | 2026-05-16 | B1 baselines.json 字段命名统一 + B2 stylelint 转 error 时机分字段拆分 | 复盘核验发现命名不一致、转 error 时机不明确 |

---

## 1. 立项背景

v3 P0 + Spec A 落地后剩余的 4 个核心治理面：

1. **显示治理三条线**：字号 1565 处 / 颜色 1611 处 / 背景 712 处 inline 硬编码（v3 §1 量化快照）
2. **GtEditableTable 接入率治理**：仅 3 处使用（Adjustments + 2 个合并工作表组件），需职责瘦身
3. **报表/附注/错报右键穿透补完**：ReportView/DisclosureEditor/TrialBalance 已有，Misstatements/Adjustments 缺
4. **stylelint 卡点 + CI 基线**：3888 处硬编码迁移过程必须 grep 卡点防回退

**严格不重复 Spec A 已交付内容**：useStaleStatus 推 6 视图 / PartnerSignDecision stale 摘要 / AJE→错报转换前端入口 — 这些已在 commit `b4cda44` 完成。

---

## 2. 功能需求

### 2.1 显示治理（F1-F4 字号/颜色/背景 token 化）

#### F1 字号 token 化 4 批迁移

| 用户故事 | 作为合伙人/开发者，我希望全平台字号统一通过 `--gt-font-size-*` token 控制，未来切换暗色模式或品牌主题时只改 token 即可 |
|----------|----------------------------------------------------------------------------------------------------------|

**验收标准**：
1. 批次 1（编辑器 5 视图）合并后：`rg "font-size:\s*\d+px" audit-platform/frontend/src/views/{WorkpaperEditor,WorkpaperList,WorkpaperWorkbench,DisclosureEditor,AuditReportEditor}.vue | wc -l == 0`
2. 批次 2（表格类 6 视图）合并后：TrialBalance/ReportView/Adjustments/Misstatements/Materiality/LedgerPenetration inline `font-size:` = 0
3. 批次 3（Dashboard 6 视图）合并后：ProjectDashboard/ManagerDashboard/PartnerDashboard/QCDashboard/EqcrMetrics/Dashboard inline `font-size:` = 0
4. 批次 4（剩余视图）合并后：全量 `rg "font-size:\s*\d+px" src --include='*.vue' | wc -l == 0`
5. `gt-tokens.css` 7 级字号变量保持完整：`--gt-font-size-xs/sm/md/lg/xl/2xl/3xl`

#### F2 stylelint 卡点（CI 强制）

| 用户故事 | 作为代码审查者，我希望 CI 自动拒绝新增 inline `font-size: \d+px`，防止治理成果回退 |
|----------|---------------------------------------------------------------------------|

**验收标准**：
1. `package.json` 装机 `stylelint@16+` + `stylelint-config-standard-vue` + 自定义规则
2. CI 新增 `npm run stylelint` step（feature/round* 分支 + master 分支必跑）
3. 规则严重度按字段 + Sprint 切换：
   - Sprint 0 全量 `warning`（不阻断 PR）
   - Sprint 1 末尾：`font-size` 转 `error`
   - Sprint 2 末尾：`color` / `background` / `background-color` 转 `error`
4. 自定义规则禁止 inline `font-size: \d+px` / `color: #[0-9a-fA-F]{3,6}` / `background(-color)?: #[0-9a-fA-F]{3,6}`

#### F3 颜色 token 化 4 批

| 用户故事 | 作为开发者，我希望文字颜色统一通过 `var(--gt-color-text-*)` 控制，5 个语义色（primary/success/warning/danger/info）+ 灰度 9 阶 |

**验收标准**：
1. `gt-tokens.css` 补完 5 个语义色 + 9 阶灰度（`--gt-text-primary/regular/secondary/tertiary/placeholder/disabled` 等）
2. 4 批迁移后：`rg "color:\s*#[0-9a-fA-F]{3,6}" src --include='*.vue' | wc -l < 50`（合理保留：`color-mix()` 透明度调节场景）

#### F4 背景 token 化 4 批

| 用户故事 | 作为开发者，我希望背景色统一走 6 级背景 token：默认/微调/信息/警告/成功/危险 |

**验收标准**：
1. `gt-tokens.css` 新增 6 级：`--gt-bg-default/subtle/info/warning/success/danger`
2. 4 批迁移后：`rg "background(-color)?:\s*#[0-9a-fA-F]{3,6}" src --include='*.vue' | wc -l < 30`

---

### 2.2 GtEditableTable 职责瘦身（F5-F6）

#### F5 GtEditableTable 拆分为两个轻封装

| 用户故事 | 作为开发者，我希望根据"列表型 vs 编辑型"场景明确选择组件，不再用一个 500 行的复杂组件做所有事 |

**验收标准**：
1. 新建 `GtTableExtended.vue`（列表型，约 200 行）：基于 el-table + 紫色表头 + 字号 class + 千分位 + 空状态 + 复制粘贴右键菜单
2. 新建 `GtFormTable.vue`（编辑型，约 250 行）：行内编辑 + dirty 标记 + 校验 + 撤销
3. `GtEditableTable.vue` 改为兼容 wrapper：根据 prop `mode='display'|'edit'` 路由到上面两个；保留 60 天后再删
4. 现有 3 个使用方（Adjustments/InternalTradeSheet/InternalCashFlowSheet）行为零回归（粘贴/撤销/dirty 全部正常工作）

#### F6 文档化 + 选择树

| 用户故事 | 作为新加入开发者，我希望读 1 篇文档就能选对组件 |

**验收标准**：
1. 新建 `docs/COMPONENT_USAGE_GUIDE.md`：含 GtTableExtended vs GtFormTable 决策树（"是否需要行内编辑/粘贴/撤销" 三问）
2. 文档含 3 个使用示例（纯展示 / 行内编辑 / 多列复杂场景）

---

### 2.3 右键穿透菜单补完（F7-F9）

#### F7 Misstatements 右键菜单 "查看关联底稿"

| 用户故事 | 作为合伙人/审计助理，我希望在错报列表上右键单元格能直接跳到关联底稿，不用反查科目编码再去 WP List |

**验收标准**：
1. Misstatements.vue 接入 `CellContextMenu` 组件 + `usePenetrate` composable
2. 右键单元格弹出菜单含"📝 查看关联底稿"项
3. 点击后调 `GET /api/projects/{pid}/misstatements/{id}/related-workpapers` 端点（如不存在则 F9 补建）
4. 返回 1 张底稿 → 直接跳转；返回多张 → 弹 dialog 让用户选

#### F8 Adjustments 右键菜单 "查看关联底稿"

**验收标准**：
1. Adjustments.vue 接入 `CellContextMenu` 组件 + `usePenetrate` composable
2. 右键 line_items 行弹出菜单含"📝 查看关联底稿"项
3. 点击后按 `line_items[].standard_account_code` 反查关联底稿（复用 ReportView 的 `relatedWorkpapers` 端点逻辑）

#### F9 后端 related-workpapers 端点（按需新建）

**验收标准**：
1. Sprint 0 grep 实测：如 `backend/app/routers/misstatements.py` 已有 `/related-workpapers` 端点则跳过此任务
2. 如缺则新建 `GET /api/projects/{pid}/misstatements/{id}/related-workpapers` 返回 `{workpapers: [{id, wp_code, wp_name}]}`
3. 端点遵循 ReportView/DisclosureEditor 已有的关联底稿 SQL 模式

---

### 2.4 CI baseline 卡点（F10）

#### F10 4 道 grep 卡点

| 用户故事 | 作为代码审查者，我希望治理成果"只减不增"，CI 自动拦截硬编码回归 |

**验收标准**：
1. CI `backend-lint` job 增加 4 个 grep 步骤：
   - `font-size: \d+px` baseline = 0（Sprint 1 末尾达成后）
   - `color: #xxx` baseline = 实测值（Sprint 2 末尾，目标 < 50）
   - `background(-color)?: #xxx` baseline = 实测值（Sprint 2 末尾，目标 < 30）
   - 裸 `<el-table` baseline = 当前实测值（Sprint 0 测得后）
2. 每个 baseline 超出即 CI fail；新视图必须用 `GtTableExtended` / `GtFormTable`
3. baseline 文件持久化到 `.github/workflows/baselines.json`，每次降低后更新

---

## 3. 非功能需求

### NF1 视觉无回归
- 每批字号/颜色 PR 配截图对比（≥ 30 个视图覆盖编辑器/表格/Dashboard）
- 截图工具：手动 Chrome F12 截图（不要求 Playwright 自动化，本期不做 E2E 视觉回归）

### NF2 vue-tsc + getDiagnostics 0 错误
- 每批 PR 合并前必须跑 `npx vue-tsc --noEmit` 0 错误
- getDiagnostics 全量 0 错误

### NF3 PR 粒度控制
- 每 PR ≤ 50 视图（约 1.5 天工时），避免合并冲突
- 严禁多人并行同视图（Sprint Lead 协调任务分配）

### NF4 不影响现有功能
- Adjustments 行内编辑 / 粘贴 / 撤销 / dirty 标记全部正常
- InternalTradeSheet / InternalCashFlowSheet 合并工作表行为零回归
- 现有右键菜单（TrialBalance "查看关联底稿" / ReportView / DisclosureEditor）行为不变

### NF5 GtEditableTable 兼容 wrapper 必须 60 天观察期
- 不立即删除 GtEditableTable.vue；改为 wrapper 模式
- 60 天内监控 console.warn `[GtEditableTable] 已迁移到 GtTableExtended/GtFormTable，请按场景选择`
- 60 天后无警告则删除 wrapper 文件

---

## 4. 测试策略

### 4.1 单测覆盖
- `GtTableExtended.spec.ts` 5 用例：列渲染 / 千分位 / 空状态 / 复制粘贴 / 紫色表头 class
- `GtFormTable.spec.ts` 5 用例：行内编辑 / dirty 标记 / 校验 / 撤销 / 兼容 GtEditableTable wrapper

### 4.2 集成测试
- `test_misstatements_related_workpapers.py`（如新建端点）：3 用例（找到 1 张 / 多张 / 0 张）
- `test_adjustments_related_workpapers.py`（按需）

### 4.3 CI 卡点测试
- `font-size baseline` 测试：grep 数 == 0
- `color baseline` 测试：grep 数 < 50
- `background baseline` 测试：grep 数 < 30
- `<el-table` baseline 测试：grep 数 ≤ Sprint 0 实测值

### 4.4 视觉回归（人工）
- Sprint 1 末尾截图对比 ≥ 5 个编辑器视图
- Sprint 2 末尾截图对比 ≥ 10 个表格类视图
- Sprint 3 末尾截图对比 ≥ 30 个完整覆盖

---

## 5. UAT 验收清单（项目上线前必跑）

| # | 验收项 | Requirements | Tester | Date | Status | 备注 |
|---|--------|--------------|--------|------|--------|------|
| 1 | 编辑器 5 视图字号 token 化无视觉差异 | F1 批 1 | 设计师/合伙人 | — | ○ pending | 截图对比 |
| 2 | 表格类 6 视图字号 token 化无视觉差异 | F1 批 2 | 设计师 | — | ○ pending | |
| 3 | Dashboard 系列 6 视图字号 token 化无视觉差异 | F1 批 3 | 项目经理 | — | ○ pending | |
| 4 | 颜色 token 化全量验收 | F3 | 设计师 | — | ○ pending | 5 语义色 + 灰度 |
| 5 | 背景 token 化全量验收 | F4 | 设计师 | — | ○ pending | 6 级背景 |
| 6 | GtEditableTable 拆分后 Adjustments 行为零回归 | F5+NF4 | 审计助理 | — | ○ pending | 粘贴/撤销/dirty |
| 7 | Misstatements 右键 "查看关联底稿" 跳转正确 | F7 | 审计助理 | — | ○ pending | |
| 8 | Adjustments 右键 "查看关联底稿" 跳转正确 | F8 | 审计助理 | — | ○ pending | |
| 9 | CI baseline 4 道卡点全绿 | F10 | DevOps | — | ○ pending | |
| 10 | stylelint 转 error 后 PR 不能合入新硬编码 | F2 | 代码审查者 | — | ○ pending | |

**Status 取值**：`✓ pass` / `✗ fail` / `⚠ partial` / `○ pending`
**上线门槛**：≥ 8 项 ✓ pass（关键项 6/7/8/9 必须 pass）

---

## 6. 成功判据汇总

| 维度 | 当前快照 | 目标 |
|------|---------|------|
| inline `font-size: Npx` | 1565 | 0 |
| inline `color: #xxx` | 1611 | < 50 |
| inline `background: #xxx` | 712 | < 30 |
| GtEditableTable 接入率 | 3 处 | GtTableExtended 接入 ≥ 20 视图 |
| 裸 `<el-table` | 待 grep | baseline 持平或减少 |
| Misstatements 右键穿透 | 缺 | ✅ |
| Adjustments 右键穿透 | 缺 | ✅ |
| stylelint CI 卡点 | 无 | ✅（error 级别） |

---

## 7. 不做清单（明确排除）

| # | 事项 | 排除原因 |
|---|------|---------|
| O1 | 暗色模式 | 先把 token 打实，Spec D 评估 |
| O2 | 全局 Ctrl+K 搜索 | 用户实际诉求弱 |
| O3 | 给 GtEditableTable 加新功能 | 先做接入率治理 + 拆分，新功能 Spec D 评估 |
| O4 | 客户主数据 + 项目标签 | R11 评估，业务诉求弱 |
| O5 | Playwright 视觉回归自动化 | 本期人工截图对比足够，不引入 E2E 复杂度 |

---

## 8. 术语表

| 术语 | 定义 |
|------|------|
| token | CSS variable，统一管理样式属性（字号/颜色/背景） |
| `gt-tokens.css` | 致同设计系统 token 真源文件，位于 `audit-platform/frontend/src/styles/` |
| baseline | grep 卡点的允许阈值，CI 强制只减不增 |
| 兼容 wrapper | 旧组件保留 60 天观察期不立即删除，内部转发到新组件 |
| inline 硬编码 | Vue 文件 `<style scoped>` 块或 template `style="..."` 属性中的字面值（非 token） |

---

## 9. 关联文档

- `docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md` §1 量化快照 / §7.6 穿透 / §8 显示治理三条线 / §9 组件铺设
- `audit-platform/frontend/src/styles/gt-tokens.css` —— token 真源
- `.kiro/specs/v3-linkage-stale-propagation/` —— Spec A（已完成，本 spec 不重做其内容）
- `.kiro/specs/v3-r10-editor-resilience/` —— Spec C（并行 spec）
