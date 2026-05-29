# Requirements Document — Phase 3 系统性增强

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-21 | 初始起草，基于《平台全局建议书》Phase 3 五项 |

## 依赖矩阵

| 依赖项 | 类型 | 状态 |
|--------|------|------|
| Phase 1 + Phase 2 specs | 前置 | 🔲 需先完成 |
| DisclosureEditor.vue | 前端 | ✅ 已有 |
| ReportView.vue | 前端 | ✅ 已有 |
| TrialBalance.vue (穿透) | 前端 | ✅ 已有 |
| useNavigationStack | 前端 | ✅ 已有 |
| vLLM Qwen3.5-27B (port 8100) | LLM | ✅ 已部署 |
| wp_k_expense_analysis.py (stub) | 后端 | ✅ 已有 stub |
| Locust/k6 | 压测工具 | 🔲 需引入 |
| CSS Variables (gt-design-tokens.css) | 前端 | ✅ 已有 |
| Storybook | 前端工具 | 🔲 需引入 |

---

## 一、为什么做（业务痛点）

### 1.1 穿透方向单一（L-1）
- **痛点**：当前仅支持 TB→下钻，缺乏"从附注数字反向追溯到 TB 科目"的上钻能力
- **影响角色**：合伙人（审阅附注时需验证数据来源）、质控（核对附注与报表一致性）
- **技术根因**：附注编辑器的 auto 模式 cell 无"点击追溯来源"交互；报表行无"点击查看构成科目"入口

### 1.2 LLM stub 引擎未接入（K-1）
- **痛点**：6 个 LLM 分析功能均为 stub（返回固定文本），无法提供真实审计洞察
- **影响角色**：审计助理（需要 AI 辅助判断异常）、项目经理（需要 AI 生成风险摘要）
- **技术根因**：`settings.WP_AI_SERVICE_ENABLED = False`，vLLM 已部署但未对接 stub 引擎

### 1.3 性能未经压测验证（PF-1）
- **痛点**：6000 并发目标仅为设计指标，未实测验证，上线后可能出现性能瓶颈
- **影响角色**：全部角色（系统可用性）
- **技术根因**：无压测脚本、无性能基线、无瓶颈定位

### 1.4 暗色模式缺失（UI-4）
- **痛点**：审计人员经常加班到深夜，白色界面刺眼，影响工作效率和健康
- **影响角色**：全部角色（尤其审计助理）
- **技术根因**：gt-design-tokens.css 仅定义 light 主题变量，无 dark 变量集

### 1.5 组件复用困难（MT-4）
- **痛点**：283 个组件无可视化文档，新开发人员不知道有哪些现成组件可复用
- **影响角色**：开发团队（维护效率）
- **技术根因**：无 Storybook 或类似组件文档工具

---

## 二、范围边界

### 必做（In Scope）

**F1 双向穿透（附注→报表→TB→明细账）：**
- 附注编辑器 auto 模式 cell 支持点击追溯来源（显示来源报表行/TB 科目）
- 报表行支持点击查看构成科目列表
- 构成科目列表支持继续下钻到明细账
- 穿透路径记录到 useNavigationStack（支持 Backspace 返回）
- 穿透方向标记：↓ 下钻 / ↑ 上钻

**F2 LLM 接入（Phase 1: 规则类引擎）：**
- 优先接入 wp_k_expense_analysis.py（费用异常分析，规则已实现，仅需 LLM 生成解释文本）
- 接入模式：规则引擎输出结构化数据 → LLM 生成自然语言解释 + 风险建议
- 统一 LLM 调用封装：temperature=0.3 / max_tokens=2000 / timeout=30s / 失败不阻断
- `settings.WP_AI_SERVICE_ENABLED = True` 后 is_llm_stub 自动切换为 False
- 前端 Dialog 显示 LLM 生成的解释文本（Markdown 渲染）

**F3 压力测试 + 性能优化：**
- 编写 Locust 压测脚本（模拟 6000 用户并发）
- 压测场景：登录 → 查 TB → 编辑底稿 → 保存 → 穿透
- 建立性能基线（P95 响应时间 / 吞吐量 / 错误率）
- 识别瓶颈并优化（连接池/查询优化/缓存）
- 目标：P95 ≤ 2s（核心 API）/ 错误率 < 0.1%

**F4 暗色模式：**
- gt-design-tokens.css 新增 `[data-theme="dark"]` 变量集
- 顶栏增加主题切换按钮（☀️/🌙）
- 主题偏好持久化到 localStorage
- 覆盖核心页面（TrialBalance/WorkpaperEditor/ReportView/Dashboard）
- Element Plus 暗色主题集成（`el-config-provider` namespace）

**F5 Storybook 搭建：**
- 安装配置 Storybook 7.x（Vue 3 + Vite）
- 覆盖 28 个 common 组件的 stories
- 覆盖 5 个核心业务组件（GtEditableTable/WorkpaperEditor 子组件等）
- 配置 Chromatic 或本地静态部署
- README 文档说明如何查看和贡献 stories

### 排除（Out of Scope）

- 不涉及全部 6 个 LLM stub 接入（仅 Phase 1 接入 1 个规则类）
- 不涉及 Elasticsearch 全文搜索（Phase 1 已用 PG ILIKE 解决）
- 不涉及 Redis Cluster 高可用（Phase 4）
- 不涉及 PG RLS 行级安全（Phase 4）
- 暗色模式不覆盖合并模块（ConsolidationIndex 等，后续迭代）

---

## 三、功能需求（EARS 范式）

### F1 双向穿透

- **F1.1** WHEN 用户在附注编辑器中点击 auto 模式的数字 cell，THE 系统 SHALL 显示来源追溯弹窗（来源报表行 + 来源 TB 科目）
- **F1.2** WHEN 用户在报表视图中点击某行金额，THE 系统 SHALL 显示该行的构成科目列表（TB 科目编号 + 名称 + 金额）
- **F1.3** WHEN 用户在构成科目列表中点击某科目，THE 系统 SHALL 跳转到 TrialBalance 并定位到该科目行
- **F1.4** THE 穿透操作 SHALL 记录到 useNavigationStack（支持 Backspace 返回）
- **F1.5** THE 面包屑 SHALL 区分穿透方向（↓ 下钻 / ↑ 上钻）

### F2 LLM 接入

- **F2.1** WHEN `settings.WP_AI_SERVICE_ENABLED = True` 且用户触发费用异常分析，THE 系统 SHALL 调用 vLLM 生成自然语言解释
- **F2.2** THE LLM 输入 SHALL 包含：规则引擎输出的结构化数据（YoY 变动率/异常标记/金额）+ 科目名称 + 行业对比数据
- **F2.3** THE LLM 输出 SHALL 包含：异常原因分析（≤ 200 字）+ 建议审计程序（≤ 3 条）+ 风险等级判断
- **F2.4** IF LLM 调用超时（>30s）或失败，THE 系统 SHALL 降级显示规则引擎的结构化结果 + "AI 分析暂不可用"提示
- **F2.5** THE 前端 Dialog SHALL 使用 Markdown 渲染 LLM 输出（支持列表/加粗/代码块）

### F3 压力测试

- **F3.1** THE 压测脚本 SHALL 模拟 5 个核心场景（登录/查 TB/编辑底稿/保存/穿透）
- **F3.2** THE 压测 SHALL 支持梯度加压（100→500→1000→3000→6000 用户）
- **F3.3** THE 压测报告 SHALL 包含：P50/P95/P99 响应时间 + 吞吐量(RPS) + 错误率 + 资源使用率
- **F3.4** IF P95 > 2s，THE 开发团队 SHALL 识别瓶颈并优化至达标

### F4 暗色模式

- **F4.1** WHEN 用户点击顶栏主题切换按钮，THE 系统 SHALL 在 light/dark 主题间切换
- **F4.2** THE 主题切换 SHALL 在 200ms 内完成（无闪烁）
- **F4.3** THE 暗色模式 SHALL 覆盖：背景色/文字色/边框色/表格色/弹窗色/图表色
- **F4.4** THE 主题偏好 SHALL 持久化到 localStorage，下次访问自动应用
- **F4.5** THE 暗色模式 SHALL 与 Element Plus 暗色主题兼容（通过 `html.dark` class）

### F5 Storybook

- **F5.1** THE Storybook SHALL 覆盖全部 28 个 common 组件
- **F5.2** THE 每个 story SHALL 包含：默认状态 + 各 props 变体 + 交互示例
- **F5.3** THE Storybook SHALL 可通过 `npm run storybook` 本地启动
- **F5.4** THE Storybook SHALL 包含"使用指南"文档页（何时用哪个组件）

---

## 四、非功能需求

| 维度 | 要求 |
|------|------|
| 性能 | F1 追溯弹窗 ≤ 500ms；F2 LLM 响应 ≤ 30s（降级 ≤ 500ms）；F3 P95 ≤ 2s |
| 兼容性 | F4 暗色模式不影响打印（@media print 强制 light）|
| 可观测性 | F2 LLM 调用记录（耗时/token 数/成功率）；F3 压测报告归档 |

---

## 五、成功判据

| 指标 | 目标 |
|------|------|
| F1 双向穿透覆盖 | 附注→报表→TB 完整链路可用 |
| F2 LLM 接入引擎数 | ≥ 1 个（wp_k_expense_analysis） |
| F3 压测达标 | 6000 并发 P95 ≤ 2s / 错误率 < 0.1% |
| F4 暗色模式覆盖页面 | ≥ 10 个核心页面 |
| F5 Storybook stories | ≥ 33 个（28 common + 5 业务） |
