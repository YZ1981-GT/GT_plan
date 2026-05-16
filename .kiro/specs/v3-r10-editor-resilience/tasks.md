# Spec C (R10) — Editor Resilience · Tasks

**版本**：v1.0
**起草日期**：2026-05-16
**关联**：`requirements.md` v1.0 + `design.md` v1.0
**总工时**：11 个工作日（2 周 + Sprint 0 半天）

---

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-16 | tasks 初稿，3 Sprint × 30 任务 |
| v1.1 | 2026-05-16 | C3 加 2.4.0 5 签字组件差异化前置任务 + C4 0.1 加 5 签字组件文件存在性核验 + X1 1.4.3 加 Spec B 依赖标注与 fallback 策略 | 复盘核验发现差异化策略缺失、跨 spec 协调缺漏 |

---

## 任务总览

| Sprint | 工时 | 范围 |
|--------|------|------|
| Sprint 0 | 0.5 天 | 启动条件核验 + 基线快照 |
| Sprint 1 | 1 周 | 后端事件级联健康度 + 前端 5xx 监控 + DegradedBanner 三档 |
| Sprint 2 | 1 周 | 危险操作二次确认补漏 + 文档化 + F8 可选实施 |
| Sprint 3 (UAT) | 0.5 天 | 上线前全量 UAT 跑 10 项验收 |

---

## Sprint 0 — 启动条件核验（0.5 天）

- [ ] 0.1 grep 实测启动条件
  - 确认三个编辑器 confirmLeave 已接（已满足，记录为 baseline）
  - 确认 WorkpaperSidePanel 10 Tab 已实装
  - 确认 DegradedBanner 已挂 ThreeColumnLayout
  - 确认 outbox_replay_worker DLQ 已实装
  - 确认 http.ts 当前无 5xx 计数器
  - 确认 `/event-cascade/health` 端点不存在
  - **新增**：确认 5 个签字组件文件存在（`fileSearch SignatureLevel1.vue` / `SignatureLevel2.vue` / `PartnerSignDecision.vue` / `EqcrApproval.vue` / `ArchiveSignature.vue`），如有改名/拆分则更新 requirements F7 文件清单
  - **新增**：确认 `LedgerDataManager.vue` / `EqcrMemoEditor.vue` 文件存在（F5/F6 依赖）
  - **新增**：确认 Spec B Sprint 0 完成状态（`gt-tokens.css` 含 `--gt-bg-warning` / `--gt-bg-danger`）；如未完成则 1.4.3 走临时硬编码 fallback（见 X1 协调）
  - 输出 baseline 报告到 console

- [ ] 0.2 v3 P0 13/13 状态确认
  - 看 `docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md` §6 表

- [ ] 0.3 Spec A 上线观察期确认
  - 确认 commit b4cda44 时间 ≥ 7 天前
  - 确认 4 项目 stale 联动稳定（无新增异常 ticket）

- [ ] 0.4 启动条件 8/8 确认通过
  - 8 项核验全绿才进入 Sprint 1

---

## Sprint 1 — 后端健康度 + 前端 5xx 监控（1 周）

### 1.1 后端 worker 心跳（1 天）

- [ ] 1.1.1 新建 `backend/app/workers/worker_helpers.py`
  - `async def write_heartbeat(worker_name: str)` 函数
  - Redis 不可用时降级（仅日志）
  - TTL=60s，value 为 JSON `{last_heartbeat, pid, version, hostname}`

- [ ] 1.1.2 sla_worker 接入心跳
  - 主循环每轮 sleep 前调 `await write_heartbeat("sla_worker")`

- [ ] 1.1.3 import_recover_worker 接入心跳

- [ ] 1.1.4 outbox_replay_worker 接入心跳

- [ ] 1.1.5 import_worker 接入心跳

- [ ] 1.1.6 单测 `test_worker_heartbeat.py`
  - 4 用例：写入成功 / Redis 不可用降级 / TTL 设置 / payload 格式

### 1.2 后端 event_cascade_health 端点（1.5 天）

- [ ] 1.2.1 新建 `backend/app/services/event_cascade_health_service.py`
  - `EventCascadeHealthService` 类
  - `get_health_summary(project_id)` 主方法
  - 4 个内部方法：`_get_outbox_lag` / `_get_stuck_handlers` / `_get_dlq_depth` / `_get_worker_status`
  - `_compute_status` 状态判定（design D2 阈值）

- [ ] 1.2.2 新建 `backend/app/routers/event_cascade_health.py`
  - `GET /api/projects/{project_id}/event-cascade/health` 端点
  - 普通用户只看 status / lag_seconds（D3）
  - admin/partner 看完整响应

- [ ] 1.2.3 router_registry.py 注册（建议 §55）

- [ ] 1.2.4 集成测试 `test_event_cascade_health.py`
  - 5 用例：admin 看完整 / 普通用户只看 status / Redis 不可用降级 / 状态判定阈值（healthy/degraded/critical） / 项目权限校验

- [ ] 1.2.5 性能测试
  - 端点 P95 ≤ 200ms 验证

### 1.3 前端 http.ts 5xx 监控（0.5 天）

- [ ] 1.3.1 `audit-platform/frontend/src/utils/http.ts` 新增环形缓冲
  - `last100Requests` 数组（最大 100）
  - response/error 拦截器都 push
  - export `recent5xxRate` computed
  - export `getRecentNetworkStats()` 函数

- [ ] 1.3.2 单测 `http.spec.ts`
  - 4 用例：少于 10 次返回 0 / 5xx 阈值触发 / 1 分钟外被排除 / 缓冲区上限 100

### 1.4 DegradedBanner 三档扩展（1.5 天）

- [ ] 1.4.1 `DegradedBanner.vue` 订阅源扩展
  - 引入 `recent5xxRate`
  - 新增 cascadeHealth 60s 轮询（独立 axios 实例 D5）
  - 优先级合并：critical > degraded > healthy

- [ ] 1.4.2 三档文案 + 可点击展开
  - 🟢 隐藏 / 🟡 服务响应较慢 / 🔴 部分功能暂时不可用
  - admin/partner 看 worker 心跳 + outbox lag

- [ ] 1.4.3 样式使用 token
  - `--gt-bg-warning` / `--gt-bg-danger`（与 Spec B 协调）
  - **依赖**：Spec B Sprint 0 完成 `gt-tokens.css` 6 级背景 token 补完（见 0.1 核验）
  - **fallback**：如 Spec C 单独启动且 Spec B 未完成，临时使用硬编码 `#fdf6ec` / `#fef0f0`，并加 `// TODO: Spec B token 完成后替换` 注释；Spec B Sprint 0 合并后开 PR 替换

- [ ] 1.4.4 单测 `degraded_banner.spec.ts`
  - 3 用例：三档切换 / 普通用户不展开详情 / 独立 axios 实例不递归触发

### 1.5 Sprint 1 验收（0.5 天）

- [ ] 1.5.1 手动模拟测试：kill 后端 → 30s 内显示 🔴
- [ ] 1.5.2 手动模拟测试：worker miss → 60s 内显示 🟡
- [ ] 1.5.3 vue-tsc 0 错误 + getDiagnostics 0 错误
- [ ] 1.5.4 UAT-1/2/3/4/5 通过

---

## Sprint 2 — 危险操作 + 文档化 + F8 可选（1 周）

### 2.1 confirmSign 包装函数（0.5 天）

- [ ] 2.1.1 `audit-platform/frontend/src/utils/confirm.ts` 新增 `confirmSign`
  - 参数：`action: string, ctx: { userName, projectName, objectName? }`
  - 文案：操作类型 + 用户 + 项目 + 不可撤销提示
  - HTML 文案 + 红色高亮"签字操作不可撤销"

### 2.2 LedgerDataManager 清理账套二次确认（0.5 天）

- [ ] 2.2.1 `LedgerDataManager.vue` 删除按钮接入 `confirmDangerous`
  - 文案："此操作将删除当前账套全部数据并不可恢复，请输入项目名称确认"
  - 必须输入项目完整名称才能确认

- [ ] 2.2.2 UAT-6 通过

### 2.3 EqcrMemoEditor 定稿二次确认（0.3 天）

- [ ] 2.3.1 `EqcrMemoEditor.vue` "定稿" 按钮接入 `confirmDangerous`
  - 文案："定稿后无法修改，将自动通知签字合伙人。是否继续？"

- [ ] 2.3.2 UAT-7 通过

### 2.4 5 签字组件全量梳理（1 天）

- [ ] 2.4.0 grep 现有 5 组件签字逻辑列差异表（前置）
  - 文件：`SignatureLevel1.vue` / `SignatureLevel2.vue` / `PartnerSignDecision.vue` / `EqcrApproval.vue` / `ArchiveSignature.vue`
  - 输出表格：组件名 / 当前是否有 confirm 包装 / 当前文案 / 是否已含用户名+项目名展示 / 改动差异
  - 差异化策略：
    - 已有 ElMessageBox.confirm → 替换为 confirmSign 统一文案
    - 已有 confirmDangerous → 升级为 confirmSign（包含用户+项目+对象）
    - 完全无 confirm → 全新接入
  - **特别注意 PartnerSignDecision**：Spec A 已加 5 卡片项目状态摘要区块，本任务只动签字按钮的 confirm 包装不动其他 UI

- [ ] 2.4.1 SignatureLevel1.vue 接入 confirmSign
  - 签字按钮调 `await confirmSign("一级复核签字", { userName, projectName })`

- [ ] 2.4.2 SignatureLevel2.vue 接入 confirmSign

- [ ] 2.4.3 PartnerSignDecision.vue 接入 confirmSign
  - 注意：Spec A 已加 5 卡片项目状态摘要区块，本 spec 仅加签字按钮的 confirmSign 不动其他 UI（与 2.4.0 差异表对齐）

- [ ] 2.4.4 EqcrApproval.vue 接入 confirmSign

- [ ] 2.4.5 ArchiveSignature.vue 接入 confirmSign

- [ ] 2.4.6 单测验证 5 个组件签字流程
  - 测试：取消 → 不调 API；确认 → 调 API

- [ ] 2.4.7 UAT-8 通过

### 2.5 文档化（1 天）

- [ ] 2.5.1 新建 `docs/WORKPAPER_SIDE_PANEL_GUIDE.md`
  - 10 Tab 各一节：用途 / 数据来源 / 与编辑器交互 / 已知限制
  - 含 1 张数据流图（Tab → API → eventBus → 编辑器）

- [ ] 2.5.2 新建 `docs/EVENT_CASCADE_HEALTH_GUIDE.md`
  - 4 worker 职责
  - outbox + DLQ 工作机制
  - lag/stuck/dlq 告警阈值
  - 故障排查 cookbook（7 种常见场景）

- [ ] 2.5.3 UAT-10 通过（新加入开发者读文档可上手）

### 2.6 F8 EQCR 备忘录版本对比（可选，1.5 天）

**实施前置条件**：Sprint 2 前 5 天工时完成且有余力，否则降级到 Spec D。

- [ ] 2.6.1*（可选）新建 `eqcr_memo_versions` 表 + Alembic 迁移
  - down_revision 链接最新（届时实测）

- [ ] 2.6.2*（可选）`EqcrMemoEditor.vue` 保存时同步 INSERT 版本

- [ ] 2.6.3*（可选）"📜 版本对比" 按钮 + diff 抽屉
  - 引入 `vue-diff` 或简单字符 diff 库

- [ ] 2.6.4*（可选）UAT-9 通过

### 2.7 Sprint 2 验收（0.5 天）

- [ ] 2.7.1 vue-tsc 0 错误
- [ ] 2.7.2 全量集成测试通过
- [ ] 2.7.3 视觉抽样验收（设计师抽 5 个签字组件 + DegradedBanner 三档）

---

## Sprint 3 — UAT（0.5 天）

### UAT 验收清单

| # | 验收项 | Tester | Date | Status |
|---|--------|--------|------|--------|
| 1 | `/event-cascade/health` 端点返回正确 schema（admin） | 后端工程师 | — | ○ pending |
| 2 | 普通用户访问只看 status 字段 | 后端工程师 | — | ○ pending |
| 3 | 4 worker 心跳每 30s 写入 Redis | DevOps | — | ○ pending |
| 4 | http.ts 5xx 环形缓冲区计算正确 | 前端工程师 | — | ○ pending |
| 5 | DegradedBanner 三档切换（手动 kill 后端验证） | 测试 | — | ○ pending |
| 6 | LedgerDataManager 清理账套必须二次确认 | 审计助理 | — | ○ pending |
| 7 | EqcrMemoEditor 定稿必须二次确认 | EQCR 合伙人 | — | ○ pending |
| 8 | 5 个签字组件全部经过 confirmSign | 各角色用户 | — | ○ pending |
| 9 | EQCR 备忘录版本对比（如已实施 F8） | EQCR 合伙人 | — | ○ pending |
| 10 | 文档可读且新加入开发者可上手 | 新加入开发者 | — | ○ pending |

**上线门槛**：≥ 8 项 ✓ pass（关键项 1/2/5/6/7/8 必须 pass）

---

## 已知缺口与技术债

| ID | 缺口 | 优先级 | 触发条件 | 后续 spec |
|----|------|-------|---------|-----------|
| TD-1 | F8 EQCR 版本对比未实施 | P2 | Sprint 2 工时不够 | Spec D 评估 |
| TD-2 | 全栈 APM 监控未引入 | P3 | 应用层 Banner 不足以发现深层问题 | Spec E 评估 Sentry/Prometheus |
| TD-3 | worker 自愈机制未做 | P3 | 监控发现告警后仍需运维手动介入 | 运维范围，Spec F 评估 |
| TD-4 | DegradedBanner 不支持用户手动 dismiss | P2 | 用户反馈横幅占屏 | 加 dismiss button + sessionStorage 记忆 |

---

## 测试策略

### 单测（vitest）
- `http.spec.ts` 4 用例
- `degraded_banner.spec.ts` 3 用例

### 集成测试（pytest）
- `test_event_cascade_health.py` 5 用例
- `test_worker_heartbeat.py` 4 用例
- `test_5_sign_components.py` 5 用例（签字流程含 confirmSign）

### 手动模拟测试
- kill 后端 → 30s 内 🔴
- 模拟 outbox 阻塞 → 60s 内 🟡
- worker miss → 60s 内 🟡

### 安全测试
- 普通用户访问 health 端点只看 status

---

## 关联文档

- `requirements.md` —— 需求源
- `design.md` —— 架构决策
- `backend/app/workers/` —— 4 worker 加心跳
- `backend/app/routers/event_cascade_health.py` —— 新建路由
- `backend/app/services/event_cascade_health_service.py` —— 新建 service
- `audit-platform/frontend/src/utils/http.ts` —— 加 5xx 监控
- `audit-platform/frontend/src/components/DegradedBanner.vue` —— 三档扩展
- `audit-platform/frontend/src/utils/confirm.ts` —— 加 confirmSign
- `docs/WORKPAPER_SIDE_PANEL_GUIDE.md` —— 新建
- `docs/EVENT_CASCADE_HEALTH_GUIDE.md` —— 新建
