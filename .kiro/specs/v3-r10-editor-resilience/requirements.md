# Spec C (R10) — Editor Resilience · Requirements

**版本**：v1.0
**起草日期**：2026-05-16
**状态**：🟡 立项规划完成，待启动条件满足后正式实施
**关联文档**：`docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md` §7.4 / §10 / §11
**前置依赖**：v3 P0 全清 ✅ + Spec A 上线观察 ≥ 7 天稳定

---

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|---------|
| v1.0 | 2026-05-16 | 三件套初稿（基于 README 立项规划扩展） | 用户要求"分别生成各自的三件套" |
| v1.1 | 2026-05-16 | C1 F1 响应结构补 redis_available + 拆分双视角 schema + Redis 降级判定 / C2 §4.2 集成测试加 test_5_sign_components.py | 复盘核验发现 schema 漂移、测试条目缺登记 |

---

## 1. 立项背景

v3 §10 错误容灾 P0 行动 A（confirmLeave 三编辑器）已落地，剩余 4 个核心容灾面：

1. **后端 5xx 静默吞噬**：用户看到"加载失败"但不知是网络/后端崩溃/事件级联卡住
2. **DegradedBanner 仅判 SSE 断线**：缺 5xx 比率监控、缺事件级联滞后告警
3. **事件级联健康度无监控端点**：合伙人/管理员无法从前端看清后端 4 个 worker + outbox 健康度
4. **危险操作二次确认补漏**：LedgerDataManager 清理账套、EqcrMemoEditor 定稿、签字操作仍直接执行

**严格不重复 R8/R9/Spec A 已交付内容**：useStaleStatus 推 6 视图 / 三个编辑器 confirmLeave / WorkpaperSidePanel 10 Tab / DegradedBanner 已挂载——这些已在 R8/R9/Spec A 完成。

---

## 2. 功能需求

### 2.1 后端事件级联健康度（F1-F2）

#### F1 `/api/projects/{pid}/event-cascade/health` 端点

| 用户故事 | 作为合伙人/管理员，我希望从一个端点看清楚事件级联的健康状况：outbox 滞后多久、哪些 handler 卡住、4 个 worker 是否还活着、DLQ 深度多少 |
|----------|------------------------------------------------------------------------------------------------------|

**响应结构**（admin/partner 视角）：
```json
{
  "lag_seconds": 12,
  "stuck_handlers": [
    {"event_type": "ADJUSTMENT_CREATED", "stuck_for_minutes": 45, "outbox_id": "..."}
  ],
  "dlq_depth": 0,
  "worker_status": {
    "sla_worker": {"alive": true, "last_heartbeat": "2026-06-01T10:00:00Z", "stale_seconds": 5},
    "import_recover_worker": {"alive": true, ...},
    "outbox_replay_worker": {"alive": true, ...},
    "import_worker": {"alive": true, ...}
  },
  "redis_available": true,
  "status": "healthy" | "degraded" | "critical"
}
```

**普通用户响应**（仅 `status` + `lag_seconds` 两字段）：
```json
{
  "status": "healthy",
  "lag_seconds": 12
}
```

**验收标准**：
1. `GET /api/projects/{pid}/event-cascade/health` 返回 200（admin/partner 角色）
2. 普通用户访问只看 `status` + `lag_seconds` 两字段，不暴露 `worker_status` / `stuck_handlers` / `outbox_id` / `dlq_depth` / `redis_available`
3. 状态判定：
   - `healthy`：lag ≤ 60s AND dlq=0 AND 全部 worker alive
   - `degraded`：lag > 60s OR dlq > 0 OR 1 个 worker miss OR Redis 不可用（`redis_available=false`）
   - `critical`：lag > 300s OR worker miss > 1
4. 性能：响应时间 P95 ≤ 200ms（PG partial index 已就绪）
5. 路由注册到 `router_registry.py`：实施时核验当前最大编号取下一个，不预先固定章节号
6. Redis 不可用时返回完整 schema + `redis_available: false` + `worker_status: {}` + `status: degraded`，不抛 500

#### F2 4 个 worker 心跳写入

| 用户故事 | 作为运维，我希望每个 worker 每 30s 在 Redis 写一次心跳，方便统一健康检查 |

**验收标准**：
1. 4 个 worker（sla_worker / import_recover_worker / outbox_replay_worker / import_worker）每 30s 写 Redis key `worker_heartbeat:{name}`，值含 `{last_heartbeat, pid, version}`
2. Key 自动过期（TTL=60s），过期视为 worker miss
3. 现有 worker 主循环改造：每轮 sleep 前先 `await _write_heartbeat()`
4. Redis 不可用时降级：仅记日志不阻断 worker

---

### 2.2 前端 5xx 监控 + DegradedBanner 三档（F3-F4）

#### F3 `http.ts` 5xx 环形缓冲区

| 用户故事 | 作为前端，我希望全局拦截器记录最近 100 次请求的状态码，30s 内超过阈值就触发降级提示 |

**验收标准**：
1. `audit-platform/frontend/src/utils/http.ts` 新增环形缓冲区 `last100Requests: { status: number; ts: number }[]`（最大长度 100）
2. axios `response` 和 `error` 拦截器都 push 到缓冲区
3. 暴露 computed `recent5xxRate`：最近 1 分钟（60s 窗口）内至少 10 次请求才计算 5xx 比率，否则返回 0
4. 暴露 `getRecentNetworkStats(): { total, xx5_count, xx5_rate, last_5xx_at }`
5. 单测：`http.spec.ts` 4 用例覆盖（少于 10 次返回 0 / 5xx 阈值触发 / 1 分钟外被排除 / 缓冲区上限 100）

#### F4 DegradedBanner 三档扩展

| 用户故事 | 作为用户，我希望系统降级时看到清晰的横幅提示，知道是网络问题还是后端问题，而不是各种"加载失败" toast |

**验收标准**：
1. `DegradedBanner.vue` 订阅源扩展：
   - SSE 断线（已有）
   - 5xx 比率（来自 F3）
   - `/event-cascade/health` 轮询（仅 admin/partner 角色，每 60s 一次）
2. 文案分级：
   - 🟢 隐藏（健康）
   - 🟡 "服务响应较慢"（5xx 率 > 30% OR lag > 60s OR SSE 重连中）
   - 🔴 "部分功能暂时不可用"（5xx 率 > 60% OR worker miss > 1 OR critical OR SSE 断 > 60s）
3. 横幅可点击展开"详细信息"，admin/partner 看 worker 心跳 + outbox lag，普通用户只看简单文案
4. 横幅样式：使用 `--gt-bg-warning`（yellow）/ `--gt-bg-danger`（red）token（与 Spec B 协调）

---

### 2.3 危险操作二次确认补漏（F5-F7）

#### F5 LedgerDataManager 清理账套二次确认

| 用户故事 | 作为审计助理，我希望"清理账套"必须二次确认 + 输入项目名称，避免误操作删除全部数据 |

**验收标准**：
1. `LedgerDataManager.vue` 删除按钮调用 `confirmDangerous("清理账套数据", { type: 'destructive', requireText: 项目名称 })`
2. 用户必须在弹框中输入项目完整名称才能确认
3. 现有删除调用链路保持不变（只是加 confirm 包装）

#### F6 EqcrMemoEditor 定稿二次确认

**验收标准**：
1. `EqcrMemoEditor.vue` "定稿" 按钮调用 `confirmDangerous("EQCR 备忘录定稿", { type: 'destructive' })`
2. 提示文案："定稿后无法修改，将自动通知签字合伙人。是否继续？"
3. 取消时无副作用

#### F7 5 个签字组件全量梳理

**验收标准**：
1. 梳理 5 个签字组件：
   - `SignatureLevel1.vue`
   - `SignatureLevel2.vue`
   - `PartnerSignDecision.vue`
   - `EqcrApproval.vue`
   - `ArchiveSignature.vue`
2. 每个组件签字按钮必须经过 `confirmSign` 包装（已有的 `confirmDangerous` 变体）
3. 签字前展示：操作类型 / 不可撤销提示 / 当前用户名 / 项目名
4. 现有部分已有，本任务做"全量梳理 + 补缺 + 文案统一"

---

### 2.4 EQCR 备忘录版本对比（F8 可选）

#### F8 备忘录版本对比（Sprint 2 工时不够则降级）

| 用户故事 | 作为 EQCR 复核合伙人，我希望能看到备忘录每次保存的历史版本，方便对比"上次定稿"和"本次最新" |

**验收标准**（如 Sprint 2 工时允许）：
1. 后端新建 `eqcr_memo_versions` 表 + Alembic 迁移
   - 字段：id / project_id / created_by / created_at / content (JSONB) / version_no
2. `EqcrMemoEditor.vue` 每次保存时同步 INSERT 一条版本记录
3. 前端"📜 版本对比"按钮 + diff 抽屉
   - 用 `vue-diff` 库或简单字符 diff
4. 可选优先级：如 Sprint 2 工时不够则延后到 Spec D，本 spec 不做硬约束

---

### 2.5 文档化（F9）

#### F9 WorkpaperSidePanel 使用文档

| 用户故事 | 作为新加入的开发者，我希望读 1 篇文档就能理解 WorkpaperSidePanel 的 10 Tab 用途、数据来源、交互模式 |

**验收标准**：
1. 新建 `docs/WORKPAPER_SIDE_PANEL_GUIDE.md`
2. 每个 Tab 单独一节：用途 / 数据来源 / 与编辑器主区交互模式 / 已知限制
3. 含 1 张数据流图（Tab → backend API → eventBus → 编辑器）

#### F10 事件级联健康度文档

**验收标准**：
1. 新建 `docs/EVENT_CASCADE_HEALTH_GUIDE.md`
2. 内容：
   - 4 个 worker 职责
   - outbox + DLQ 工作机制
   - lag/stuck/dlq 三个维度的告警阈值
   - 故障排查 cookbook（7 种常见场景）

---

## 3. 非功能需求

### NF1 性能
- `/event-cascade/health` 端点 P95 ≤ 200ms
- DegradedBanner 60s 轮询不影响业务请求性能（独立 axios 实例）

### NF2 安全
- `/event-cascade/health` 普通用户只看 `status` 字段，不暴露内部数据
- worker 心跳 Redis key 不暴露给前端（仅后端聚合后输出）

### NF3 容灾
- Redis 不可用时 worker 心跳降级：仅记日志不阻断
- `/event-cascade/health` 端点 Redis 不可用时返回 `worker_status: {}` + `status: degraded`，不抛 500

### NF4 vue-tsc + getDiagnostics 0 错误
- 每 PR 必须通过

### NF5 与 Spec B 协调
- DegradedBanner 颜色使用 token，不引入新硬编码
- Sprint 2 末尾 Spec B 颜色 token 化时同步刷一遍 DegradedBanner 视觉

---

## 4. 测试策略

### 4.1 单测
- `http.spec.ts` 4 用例（5xx 环形缓冲）
- `degraded_banner.spec.ts` 3 用例（三档切换）

### 4.2 集成测试
- `test_event_cascade_health.py`：admin 看完整 / 普通用户只看 status / Redis 不可用降级
- `test_worker_heartbeat.py`：4 worker 心跳写入 / 过期检测
- `test_5_sign_components.py`：5 个签字组件签字流程含 confirmSign（取消 → 不调 API；确认 → 调 API；5 用例）

### 4.3 手动模拟测试
- 手动 kill 后端 → 前端 30s 内显示 🔴 横幅
- 模拟 outbox 阻塞（手动改 PG 状态）→ 前端 60s 内显示 🟡

### 4.4 安全测试
- 普通用户访问 `/event-cascade/health` 只看到 `{status: "healthy"}` 不含 worker_status

---

## 5. UAT 验收清单

| # | 验收项 | Requirements | Tester | Date | Status |
|---|--------|--------------|--------|------|--------|
| 1 | `/event-cascade/health` 端点返回正确 schema（admin） | F1 | 后端工程师 | — | ○ pending |
| 2 | 普通用户访问只看 status 字段 | F1 + NF2 | 后端工程师 | — | ○ pending |
| 3 | 4 worker 心跳每 30s 写入 Redis | F2 | DevOps | — | ○ pending |
| 4 | http.ts 5xx 环形缓冲区计算正确 | F3 | 前端工程师 | — | ○ pending |
| 5 | DegradedBanner 三档切换（手动 kill 后端验证） | F4 | 测试 | — | ○ pending |
| 6 | LedgerDataManager 清理账套必须二次确认 | F5 | 审计助理 | — | ○ pending |
| 7 | EqcrMemoEditor 定稿必须二次确认 | F6 | EQCR 合伙人 | — | ○ pending |
| 8 | 5 个签字组件全部经过 confirmSign | F7 | 各角色用户 | — | ○ pending |
| 9 | EQCR 备忘录版本对比（如已实施） | F8 可选 | EQCR 合伙人 | — | ○ pending |
| 10 | 文档 WORKPAPER_SIDE_PANEL_GUIDE.md 可读 | F9 | 新加入开发者 | — | ○ pending |

**Status 取值**：`✓ pass` / `✗ fail` / `⚠ partial` / `○ pending`
**上线门槛**：≥ 8 项 ✓ pass（关键项 1/2/5/6/7/8 必须 pass）

---

## 6. 成功判据汇总

| 维度 | 当前状态 | 目标 |
|------|---------|------|
| `/event-cascade/health` 端点 | ❌ 不存在 | ✅ 200 |
| 4 worker 心跳 | ❌ 仅 outbox_replay 有部分 | ✅ 全部 |
| http.ts 5xx 计数器 | ❌ 无 | ✅ |
| DegradedBanner 三档 | ⚠️ 仅 SSE 断线 | ✅ 三档 |
| LedgerDataManager 清理二次确认 | ❌ | ✅ |
| EqcrMemoEditor 定稿二次确认 | ❌ | ✅ |
| 5 签字组件 confirmSign | ⚠️ 部分 | ✅ 全量 |
| EQCR 版本对比（可选） | ❌ | 🟡 视工时 |
| WorkpaperSidePanel 文档 | ❌ | ✅ |

---

## 7. 不做清单（明确排除）

| # | 事项 | 排除原因 |
|---|------|---------|
| O1 | 暗色模式 | Spec D 评估，先做 token |
| O2 | 自动错误重试机制 | 5xx 自动重试容易雪崩，用户偏好"明确显示+手动重试" |
| O3 | 全栈 APM 监控（Sentry/Prometheus 端到端） | 太重，本期只做应用层 Banner + health 端点 |
| O4 | EQCR 备忘录富文本 diff | Spec D 评估 |
| O5 | 自动 worker 重启 | 运维范围，本期只做监控不做自愈 |

---

## 8. 术语表

| 术语 | 定义 |
|------|------|
| outbox | event_outbox 表，事件持久化层（Spec A 改造前已有） |
| DLQ | Dead Letter Queue，处理失败的事件转入的队列（commit 19f1c5e 已实装） |
| stuck handler | event_outbox 中 status='processing' 且 updated_at < now() - 30min 的事件 |
| lag | outbox 待处理事件中最旧一条的 created_at 距今秒数 |
| confirmDangerous | utils/confirm.ts 中的语义化函数，弹 ElMessageBox 二次确认 |
| confirmSign | confirmDangerous 的签字变体，提示不可撤销 + 显示用户名+项目 |
| 心跳 | worker 在 Redis 写入的 `worker_heartbeat:{name}` key，TTL=60s |

---

## 9. 关联文档

- `docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md` §7.4 §10 §11
- `audit-platform/frontend/src/components/DegradedBanner.vue` —— 已挂载，本 spec 扩展
- `audit-platform/frontend/src/utils/http.ts` —— Sprint 1 加 5xx 监控
- `backend/app/workers/` —— 4 个 worker 模块，本 spec 加心跳
- `.kiro/specs/v3-r10-linkage-and-tokens/` —— Spec B（并行）
