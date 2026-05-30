# Requirements Document — Phase 2 角色体验提升

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-21 | 初始起草，基于《平台全局建议书》Phase 2 五项 |

## 依赖矩阵

| 依赖项 | 类型 | 状态 |
|--------|------|------|
| PartnerSignDecision.vue | 前端 | ✅ 已有 |
| QCDashboard.vue | 前端 | ✅ 已有 |
| WorkpaperList.vue | 前端 | ✅ 已有 |
| WorkpaperEditor.vue (prefill) | 前端 | ✅ 已有 |
| ReviewWorkbench.vue | 前端 | ✅ 已有 |
| consistency_gate (VR 规则引擎) | 后端 | ✅ 已有 |
| prefill_engine.py | 后端 | ✅ 已有 |
| useCellComments composable | 前端 | ✅ 已有 |
| ECharts (vue-echarts) | 前端 | ✅ 已有 |
| Phase 1 spec (版本锁) | 前置 | 🔲 需先完成 |

---

## 一、为什么做（业务痛点）

### 1.1 签字前缺乏结构化 Gate（P-1）
- **痛点**：合伙人签字决策面板仅展示基本状态，缺乏"签字前必须确认"的 checklist，容易遗漏关键事项
- **影响角色**：合伙人（签字决策）
- **技术根因**：PartnerSignDecision 无 Gate 组件，签字按钮无前置条件拦截

### 1.2 QC 缺乏风险热力图（Q-1）
- **痛点**：质控人员需逐个底稿看 VR 结果，无法快速定位高风险区域
- **影响角色**：质控人员（复核效率）
- **技术根因**：QCDashboard 无按循环×风险等级的矩阵视图，VR 结果仅在 ConsistencyDashboard 扁平展示

### 1.3 底稿批量状态变更缺失（M-3）
- **痛点**：项目经理需逐个底稿"提交复核"或"退回修改"，10+ 个底稿操作耗时
- **影响角色**：项目经理（进度管控）
- **技术根因**：WorkpaperList 无批量选择+批量操作功能

### 1.4 prefill 差异对比缺失（A-2）
- **痛点**：一键填充后不知道哪些 cell 变了、变了多少，容易漏审变更
- **影响角色**：审计助理（数据质量）
- **技术根因**：prefill_engine 执行后直接覆盖，无 diff 记录返回前端

### 1.5 复核意见无优先级（RV-2）
- **痛点**：所有复核意见同等对待，助理无法判断哪些必须改、哪些建议改
- **影响角色**：审计助理+项目经理（复核流程）
- **技术根因**：review_comment 模型无 priority 字段，UI 无优先级标记

---

## 二、范围边界

### 必做（In Scope）

**F1 签字前 Gate Checklist：**
- PartnerSignDecision 页面新增 Gate 组件（10 项强制确认）
- 10 项 checklist：重要性水平已确定 / 错报汇总已审阅 / 后续事项已评估 / 独立性声明已签署 / 所有底稿已签字 / 所有复核意见已关闭 / VR blocking 规则全部通过 / 调整分录已审批 / 附注与报表一致 / 管理层声明书已获取
- 前 7 项可自动检测（调用后端 API 获取状态），后 3 项需手动勾选
- 全部 ✓ 才能点击"签发审计报告"按钮

**F2 QC 风险热力图：**
- QCDashboard 新增"风险热力图"Tab
- 矩阵：行=11 个循环(D~N) × 列=3 个风险等级(blocking/warning/info)
- 单元格颜色深浅表示该循环该等级的 VR 规则数量
- 点击单元格跳转到 ConsistencyDashboard 并过滤对应循环+等级
- 后端新增聚合 API：按循环×severity 分组统计 VR 结果

**F3 底稿批量状态变更：**
- WorkpaperList 增加批量选择模式（checkbox 列）
- 选中后顶部出现批量操作栏：批量提交复核 / 批量退回修改 / 批量标记完成
- 批量操作前弹出确认弹窗（显示选中数量+操作类型）
- 后端新增批量状态变更 API（事务保证：全部成功或全部回滚）
- 权限控制：批量提交=auditor+ / 批量退回=manager+ / 批量标记完成=manager+

**F4 Prefill 差异对比面板：**
- 一键填充完成后弹出 diff 面板（而非直接覆盖）
- diff 面板显示：cell 位置 + 旧值 + 新值 + 变动幅度(%)
- 支持"全部接受" / "逐项确认" / "取消填充"三种操作
- 后端 prefill API 改为返回 diff 结果（不直接写入），前端确认后再调用 apply API
- 变动幅度超过 20% 的 cell 高亮标记（提醒审计助理关注）

**F5 复核意见优先级：**
- review_comment 模型新增 `priority: Enum('must_fix', 'suggest', 'info')` 字段
- 复核人录入意见时选择优先级（默认 suggest）
- must_fix 类意见未处理时，底稿不能重新提交复核
- 意见列表按优先级排序（must_fix 红色置顶 / suggest 橙色 / info 灰色）
- 助理回复意见时可标记"已处理"，复核人确认后关闭

### 排除（Out of Scope）

- 不涉及签字后的归档流程（ArchiveWizard 独立）
- 不涉及 VR 规则新增（仅消费现有 53 条规则的结果）
- 不涉及 WebSocket 实时推送批量操作进度（同步等待）
- 不涉及 prefill diff 的版本历史（仅当次 diff）
- 不涉及复核意见的 @提及功能（独立 spec）

---

## 三、功能需求（EARS 范式）

### F1 签字前 Gate

- **F1.1** WHEN 合伙人进入 PartnerSignDecision 页面，THE 系统 SHALL 显示 10 项 Gate Checklist
- **F1.2** THE 系统 SHALL 自动检测前 7 项状态（调用后端 API），已满足显示 ✓ 绿色，未满足显示 ✗ 红色
- **F1.3** THE 后 3 项 SHALL 由合伙人手动勾选确认
- **F1.4** IF 任一项为 ✗ 或未勾选，THE "签发审计报告"按钮 SHALL 禁用（disabled + tooltip 提示原因）
- **F1.5** WHEN 全部 10 项为 ✓，THE "签发审计报告"按钮 SHALL 启用
- **F1.6** THE 自动检测项 SHALL 提供"刷新"按钮，点击后重新检测状态

### F2 QC 风险热力图

- **F2.1** WHEN 质控人员进入 QCDashboard 并切换到"风险热力图"Tab，THE 系统 SHALL 显示 11×3 矩阵
- **F2.2** THE 矩阵单元格颜色 SHALL 按数量映射深浅（0=白色 / 1-2=浅色 / 3-5=中色 / 6+=深色）
- **F2.3** WHEN 用户点击矩阵单元格，THE 系统 SHALL 跳转到 ConsistencyDashboard 并自动过滤对应循环+severity
- **F2.4** THE 热力图数据 SHALL 来自后端聚合 API（不在前端遍历计算）

### F3 底稿批量状态变更

- **F3.1** WHEN 用户在 WorkpaperList 勾选 ≥ 1 个底稿，THE 系统 SHALL 在表格上方显示批量操作栏
- **F3.2** THE 批量操作栏 SHALL 显示"已选 N 个"+ 操作按钮（提交复核/退回修改/标记完成）
- **F3.3** WHEN 用户点击批量操作按钮，THE 系统 SHALL 弹出确认弹窗（"确定将 N 个底稿提交复核？"）
- **F3.4** IF 批量操作中任一底稿状态不允许该操作（如已签字的底稿不能退回），THE 系统 SHALL 在确认弹窗中列出跳过项
- **F3.5** THE 后端批量 API SHALL 使用事务保证原子性（全部成功或全部回滚）
- **F3.6** WHEN 批量操作完成，THE 系统 SHALL 刷新列表并显示成功通知（"成功处理 N 个底稿"）

### F4 Prefill 差异对比

- **F4.1** WHEN 用户点击"一键填充"，THE 系统 SHALL 调用 prefill preview API（返回 diff 而非直接写入）
- **F4.2** THE diff 面板 SHALL 显示每个变更 cell 的：sheet 名 / cell 位置 / 旧值 / 新值 / 变动幅度
- **F4.3** IF 变动幅度 ≥ 20%，THE 系统 SHALL 高亮标记该行（黄色背景 + ⚠️ 图标）
- **F4.4** THE 用户 SHALL 可选择"全部接受"（一键应用所有变更）或"逐项确认"（逐个勾选）或"取消"
- **F4.5** WHEN 用户确认后，THE 系统 SHALL 调用 prefill apply API 写入选中的变更
- **F4.6** THE diff 面板 SHALL 显示变更汇总统计（总变更数 / 新增数 / 修改数 / 高亮数）

### F5 复核意见优先级

- **F5.1** THE review_comment 模型 SHALL 新增 `priority` 字段（must_fix / suggest / info，默认 suggest）
- **F5.2** WHEN 复核人录入意见时，THE 系统 SHALL 提供优先级选择器（红色必须修改 / 橙色建议修改 / 灰色仅供参考）
- **F5.3** THE 意见列表 SHALL 按优先级排序（must_fix 置顶 + 红色标签 / suggest 橙色 / info 灰色）
- **F5.4** IF 存在未处理的 must_fix 意见，THE "重新提交复核"按钮 SHALL 禁用 + tooltip 提示
- **F5.5** WHEN 助理标记意见为"已处理"，THE 系统 SHALL 通知复核人确认

---

## 四、非功能需求

| 维度 | 要求 |
|------|------|
| 性能 | F1 Gate 自动检测 ≤ 2s；F2 热力图 API ≤ 500ms；F3 批量操作 ≤ 5s（20 个底稿）；F4 prefill preview ≤ 3s |
| 兼容性 | 与 Phase 1 版本锁兼容（批量操作不触发版本冲突） |
| 可观测性 | F3 批量操作记录 audit_log；F5 优先级变更记录 audit_log |

---

## 五、测试矩阵

| 功能 | 单测文件 | PBT | UAT 优先级 |
|------|---------|-----|-----------|
| F1 签字 Gate | test_sign_gate_checklist.py + SignGateChecklist.spec.ts | — | P0 |
| F2 热力图 | test_vr_heatmap_aggregation.py + VRHeatmap.spec.ts | — | P0 |
| F3 批量操作 | test_batch_status_change.py + BatchActionBar.spec.ts | PBT-P1 | P0 |
| F4 Prefill diff | test_prefill_preview.py + PrefillDiffPanel.spec.ts | — | P0 |
| F5 复核优先级 | test_review_priority.py + ReviewPrioritySelector.spec.ts | — | P1 |

---

## 六、成功判据

| 指标 | 目标 |
|------|------|
| F1 Gate 自动检测项 | ≥ 7 项自动化（无需人工判断） |
| F2 热力图覆盖循环 | 11 个循环全覆盖 |
| F3 批量操作支持状态 | ≥ 3 种（提交/退回/标记完成） |
| F4 diff 面板信息完整度 | 每个变更 cell 含 5 个字段（sheet/位置/旧值/新值/幅度） |
| F5 优先级拦截准确率 | must_fix 未处理时 100% 拦截重新提交 |
