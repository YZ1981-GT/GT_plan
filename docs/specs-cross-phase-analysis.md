# 16 阶段 Spec 跨阶段分析报告

## 1. 阶段命名统一

| 序号 | 目录名 | 中文名 | 核心交付 | 代码状态 |
|------|--------|--------|----------|----------|
| 0 | phase0-infrastructure | 基础设施 | DB/Redis/JWT/WOPI/中间件 | ✅ 全部完成 |
| 1a | phase1a-core | MVP 核心 | 四表/试算表/调整/重要性/错报 | ✅ 全部完成 |
| 1b | phase1b-workpaper | 底稿管理 | 取数公式/模板/WOPI/QC/抽样 | ✅ 全部完成 |
| 1c | phase1c-report | 报表生成 | 四张报表/CFS/附注/审计报告/PDF | ✅ 全部完成 |
| 2 | phase2-consolidation | 合并报表 | 合并范围/抵消/商誉/外币/少数股东 | ⚠️ 后端完成，前端 developing |
| 3 | phase3-collaboration | 协作功能 | 复核/同步/通知/PBC/函证 | ❌ 死代码（32 个路由未注册） |
| 4 | phase4-ai | AI 能力 | OCR/聊天/合同/底稿填充/知识库 | ⚠️ 4 个服务有实际逻辑但未注册路由 |
| 5 | phase5-extension | 扩展功能 | 多准则/多语言/电子签名/监管/T 型账户 | ✅ 后端+前端完成 |
| 6 | phase6-integration | 深度联动 | 人员/底稿联动/合并衔接/附注/程序裁剪 | ✅ 全部完成 |
| 7 | phase7-enhancement | 深度增强 | 下载导入/连续审计/复核对话/论坛/私人库 | ✅ 全部完成 |
| 8 | phase8 | 数据模型优化 | 性能/移动端/安全/监控 | ✅ 代码完成（性能测试待真实环境） |
| 11 | phase11-system-hardening | 系统加固 | 空壳清理/复核退回/合并深度开发 | ✅ 全部完成 |
| 12 | phase12-workpaper-deep | 底稿深度 | AI 审计说明/复核工作台/QC 内容级 | ✅ 全部完成 |
| 13 | phase13-word-export | Word 导出 | 致同排版引擎/模板填充/报表快照 | ✅ 全部完成 |
| 14 | phase14-gate-engine | 门禁引擎 | 统一门禁/QC-19~26/SoD/Trace | ✅ 全部完成 |
| 15 | phase15-task-tree | 任务树编排 | 四级任务树/事件补偿/问题单/SLA | ✅ 全部完成 |
| 16 | phase16-evidence | 取证版本链 | 版本戳/取证 hash/离线冲突/一致性复算 | ✅ 全部完成 |

---

## 2. 跨阶段矛盾与断点

### 2.1 Phase 3（协作）完全废弃但代码残留

**问题**：Phase 3 的 32 个同步 ORM 路由文件仍在 `routers/` 目录中（未注册到 main.py），对应的 `collaboration_models.py` 仍被 conftest.py 导入。

**影响**：
- 新人接手时会困惑这些文件是否有用
- conftest.py 导入这些模型只是为了确保表能建出来

**建议**：彻底删除 Phase 3 的 32 个路由文件，保留 `collaboration_models.py`（表结构仍在用）。

### 2.2 Phase 4（AI）服务存在但无入口

**问题**：`ai_chat_service.py`、`contract_analysis_service.py`、`workpaper_fill_service.py`、`ocr_service_v2.py` 有实际业务逻辑和 101 个测试覆盖，但对应路由未注册。

**影响**：
- 前端 AIChatView 路由已移除（Phase 11），用户无法触达
- 这些服务的能力（合同分析、底稿智能填充）被浪费

**建议**：Phase 4 服务保留为"待激活"状态，等 vLLM 稳定后通过功能开关逐步启用。

### 2.3 Phase 2（合并）前端与后端脱节

**问题**：后端 10 个合并路由已从同步改为异步（Phase 11），`consolidationApi.ts` 已重写 40+ 函数，但前端 14 个子组件的类型定义与 API 不匹配（约 120 个 TS 错误）。

**影响**：
- 合并报表导航已标记 developing（灰色不可点击）
- 用户无法使用合并报表功能

**建议**：合并报表需要专项开发（预计 2-3 周），不是简单修 TS 错误能解决的。

---

## 3. 企业级应用维度分析

### 3.1 可视化

| 能力 | 状态 | 覆盖页面 |
|------|------|----------|
| 报表表格（缩进/合计高亮/穿透） | ✅ | ReportView |
| 试算表分组小计 | ✅ | TrialBalance |
| 五级穿透导航 | ✅ | LedgerPenetration |
| 底稿树形索引 | ✅ | WorkpaperList |
| 附注目录树+表格编辑 | ✅ | DisclosureEditor |
| 公式管理弹窗（三分类+可视化选择器） | ✅ | FormulaManagerDialog + FormulaRefPicker |
| 合并差额表 | ⚠️ | ConsolidationIndex（developing） |
| ECharts 图表看板 | ✅ | ManagementDashboard |
| 四栏视图 | ⚠️ | DefaultLayout（框架有，内容薄） |

### 3.2 联动

| 联动链路 | 状态 | 机制 |
|----------|------|------|
| 调整分录→试算表→报表 | ✅ | EventBus debounce |
| 数据导入→试算表重算 | ✅ | DATA_IMPORTED 事件 |
| 底稿保存→试算表比对 | ✅ | WORKPAPER_SAVED 事件 |
| 报表生成→附注刷新 | ✅ | REPORTS_UPDATED 事件 |
| 数据集激活→下游通知 | ✅ | LEDGER_DATASET_ACTIVATED 事件 |
| 门禁评估→提交/签字/导出 | ✅ | GateEngine 三入口接入 |
| 公式应用→表格数据刷新 | ✅ | apply-formulas 端点 |

### 3.3 可溯源

| 溯源能力 | 状态 | 实现 |
|----------|------|------|
| 报表行→公式→贡献科目 | ✅ | drilldown + source_accounts |
| 附注→底稿 parsed_data | ✅ | note_wp_mapping |
| 操作→审计日志 | ✅ | AuditLogMiddleware + request_id |
| 公式变更→diff 记录 | ✅ | Log 表 formula_updated |
| 调整分录变更→old/new | ✅ | Log 表 adjustment_updated |
| 版本链→对象变更历史 | ✅ | version_line_stamps |
| 数据集版本→激活/回滚历史 | ✅ | activation_records |

### 3.4 留痕

| 留痕能力 | 状态 |
|----------|------|
| 所有 POST/PUT/DELETE 请求 | ✅ AuditLogMiddleware |
| request_id 链路追踪 | ✅ RequestIDMiddleware |
| 门禁决策记录 | ✅ gate_decisions + trace_events |
| 导入作业历史 | ✅ ImportJob + LedgerDataset |
| 复核状态变更 | ✅ WpReviewStatus 状态机 |
| 签字前检查记录 | ✅ PartnerDashboard 8 项检查 |

### 3.5 人机互动

| 能力 | 状态 | 说明 |
|------|------|------|
| 公式可视化选择器 | ✅ | FormulaRefPicker 三 Tab 点选 |
| 一键清除/恢复公式 | ✅ | clear-formulas / restore-auto |
| 底稿在线/离线双模式 | ✅ | ONLYOFFICE + 下载编辑 |
| 复核批注回复 | ✅ | WorkpaperList 回复弹窗 |
| 门禁阻断+跳转定位 | ✅ | GateBlockPanel |
| 数据校验弹窗 | ✅ | LedgerPenetration 校验按钮 |
| 报表结构编辑器 | ✅ | ReportConfigEditor |

### 3.6 LLM 辅助

| 能力 | 状态 | 说明 |
|------|------|------|
| 附注文字 LLM 审核 | ✅ | validate_llm_review（降级静默） |
| 底稿审计说明生成 | ✅ | wp_explanation_service（Phase 12） |
| 底稿 AI 对话 | ✅ | wp_chat_service SSE 流式 |
| 工时 AI 预填 | ✅ | workhour_service.ai_suggest |
| 进度简报 LLM 润色 | ✅ | ProgressBriefService.polish_with_llm |
| 熔断器保护 | ✅ | llm_client._CircuitBreaker |
| LLM 限流 | ✅ | LLMRateLimitMiddleware |

---

## 4. 角色视角需求覆盖

### 4.1 审计助理

| 需求 | 状态 |
|------|------|
| 查账穿透（五级） | ✅ |
| 编制调整分录 | ✅ |
| 编制底稿（在线/离线） | ✅ |
| AI 辅助审计说明 | ✅ |
| QC 自检 | ✅ |
| 提交复核 | ✅ |
| 只看自己负责的循环 | ✅ scope_cycles |

### 4.2 项目经理

| 需求 | 状态 |
|------|------|
| 待复核收件箱 | ✅ ReviewInbox |
| 批注+退回 | ✅ |
| 进度看板 | ✅ ProjectProgressBoard |
| 团队委派 | ✅ TeamAssignmentStep |
| 调整汇总导出 | ✅ |
| 底稿工作台 | ✅ WorkpaperWorkbench |

### 4.3 质控人员

| 需求 | 状态 |
|------|------|
| QC 看板 | ✅ QCDashboard |
| 14 条 QC 规则 | ✅ 全部做实 |
| 归档前检查 | ✅ 12 项 |
| 门禁引擎 | ✅ GateEngine |

### 4.4 合伙人

| 需求 | 状态 |
|------|------|
| 合伙人看板 | ✅ PartnerDashboard |
| 签字前 8 项检查 | ✅ |
| 风险预警 | ✅ |
| 全局项目总览 | ✅ |

---

## 5. 建议的下一步行动

1. **合并报表前端专项开发**（2-3 周）— 修复 120 个 TS 错误 + 子组件与 API 对齐
2. **Phase 3 死代码清理**（0.5 天）— 删除 32 个未注册路由文件
3. **Phase 4 AI 服务激活**（1 周）— 注册路由 + 功能开关 + 前端入口恢复
4. **真实项目验证**（持续）— 用 3 个不同规模项目端到端测试
