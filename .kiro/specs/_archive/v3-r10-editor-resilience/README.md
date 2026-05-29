# Spec C (R10) — Editor Resilience（编辑器容灾 + 后端聚合）

**编制人**：合伙人（平台治理）
**起草日期**：2026-05-16
**状态**：🟡 占位（立项规划完成，待启动条件满足后起草三件套）
**关联**：v3 §10（错误处理与容灾）+ §7.4（事件级联健康度）+ §11（5 角色痛点）
**预计启动**：2026-06-上旬（v3 P0 全部清完 + Spec A 上线观察 ≥ 7 天稳定后）

---

## 立项背景

v3 §10 错误容灾仅 P0 行动 A（confirmLeave）部分落地，剩余 4 个核心容灾面：

1. **后端 5xx 静默吞噬**：用户看到"加载失败"但不知是网络/后端崩溃/事件级联卡住（v3 §10.1）
2. **DegradedBanner 仅判 SSE 断线**：缺 5xx 比率监控、缺事件级联滞后告警（v3 §10.2.B）
3. **事件级联健康度无监控端点**：合伙人/管理员无法从前端看清后端 4 个 worker + outbox 健康度（v3 §7.4）
4. **危险操作二次确认补漏**：LedgerDataManager 清理账套、EqcrMemoEditor 定稿、签字操作仍直接执行（v3 §10.2 隐含）

**不重复 Spec A 已交付内容**：useStaleStatus 推 6 视图 / 三个编辑器 confirmLeave / WorkpaperSidePanel 10 Tab — 这些已在 R8/R9 + Spec A 完成，本 spec 不重做。

---

## 范围（2 周工时）

### Sprint 1（1 周）— 后端事件级联健康度 + DegradedBanner 扩展

#### A. 后端 `/api/projects/{pid}/event-cascade/health` 端点（v3 §7.4）

新建 `backend/app/routers/event_cascade_health.py`：
```python
GET /api/projects/{pid}/event-cascade/health
→ {
  "lag_seconds": 12,           # outbox 待处理事件最旧时延
  "stuck_handlers": [          # 30 分钟未完成的 handler
    {"event_type": "ADJUSTMENT_CREATED", "stuck_for_minutes": 45}
  ],
  "dlq_depth": 0,              # 死信队列深度
  "worker_status": {           # 4 个 worker 心跳
    "sla_worker": {"alive": true, "last_heartbeat": "2026-06-01T10:00:00Z"},
    "import_recover_worker": {"alive": true, ...},
    "outbox_replay_worker": {"alive": true, ...},
    "import_worker": {"alive": true, ...}
  },
  "status": "healthy" | "degraded" | "critical"
}
```

实现要点：
- `outbox_replay_worker` 已有 DLQ 实现（commit 19f1c5e），加 SELECT MAX(age) 即可
- 4 个 worker 心跳从 Redis key `worker_heartbeat:{name}` 读
- stuck_handlers 从 `event_outbox WHERE status='processing' AND updated_at < now() - 30m` 取
- 状态判定：lag>60s OR dlq>0 OR worker miss → degraded；lag>300s OR worker miss > 1 → critical

#### B. 前端 5xx 监控 + DegradedBanner 扩展（v3 §10.2.B）

`audit-platform/frontend/src/utils/http.ts` 加环形缓冲：
```ts
const last100Requests: { status: number; ts: number }[] = []
// 每个 response 都 push；保持长度 100
// computed: 最近 1 分钟 5xx 比率
const recent5xxRate = computed(() => {
  const now = Date.now()
  const recent = last100Requests.filter(r => now - r.ts < 60_000)
  if (recent.length < 10) return 0
  return recent.filter(r => r.status >= 500).length / recent.length
})
```

`DegradedBanner.vue` 扩展：
- 当前订阅 SSE 断线（已有）
- 新增 5xx 比率 > 30% 监控（30s 内 ≥ 3 次 5xx）
- 新增轮询 `/event-cascade/health` 端点（admin/partner 角色可见，每 60s 一次）
- 文案分级：
  - 🟢 隐藏（健康）
  - 🟡 "服务响应较慢"（5xx 率 > 30% OR lag > 60s）
  - 🔴 "部分功能暂时不可用"（5xx 率 > 60% OR worker miss > 1 OR critical）

### Sprint 2（1 周）— 危险操作二次确认补漏 + EQCR 备忘录版本对比

#### A. 危险操作二次确认补漏（v3 §10 隐含）

grep 实测 + 加 `confirmDangerous` / `ElMessageBox.confirm` 包装：

| 视图 | 操作 | 当前状态 | 修复 |
|------|------|---------|------|
| `LedgerDataManager.vue` | 清理账套（删除 4 表数据） | 直接执行 | 加 `confirmDangerous("清理账套数据", "此操作将删除当前账套全部数据并不可恢复，请输入项目名称确认")` |
| `EqcrMemoEditor.vue` | 备忘录定稿 | 直接执行 | 加 `confirmDangerous("EQCR 备忘录定稿", "定稿后无法修改，将自动通知签字合伙人")` |
| `Signatures*` | 签字操作 | 已有部分 | 全量梳理 5 个签字组件（SignatureLevel1-2 + PartnerSignDecision + EqcrApproval + ArchiveSignature） |
| `Adjustments.vue` | 删除分录组 | 已有 | 验证 |
| `Misstatements.vue` | 删除错报 | 已有 | 验证 |

#### B. EQCR 备忘录版本对比（v3 §11 EQCR 角色痛点）

`EqcrMemoEditor.vue` 当前只有 `onExportWord`，加：
- 后端 `eqcr_memo_versions` 表（如不存在，新建迁移）
- 每次保存写一版（带 created_by + created_at）
- 前端"📜 版本对比"按钮 + diff 抽屉（用 `vue-diff` 或简单字符 diff 库）
- 此功能优先级中等，可选做（如 Sprint 2 工时不够则延后到 Spec D）

#### C. WorkpaperSidePanel 文档化

WorkpaperSidePanel 已 10 Tab 实装但缺使用文档：
- 加 `docs/WORKPAPER_SIDE_PANEL_GUIDE.md`：每 Tab 用途 + 数据来源 + 与编辑器主区交互模式
- 帮助新加入开发者快速上手

---

## 启动条件（Sprint 0 强制核验）

| 核验项 | 命令 | 当前快照（2026-05-16 实测） | 启动门槛 |
|--------|------|------------------------------|---------|
| v3 P0 全部完成 | 看 docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md §6 表 | 13/13 ✅ | 必须 13/13 |
| Spec A 上线 ≥ 7 天 | git log Spec A 时间 | 2026-05-16 完成 | ≥ 2026-05-23 |
| 三个编辑器 confirmLeave | grep `confirmLeave` in editors | ✅ 已全接（WorkpaperEditor / DisclosureEditor / AuditReportEditor） | 已满足，本 spec 不重做 |
| WorkpaperSidePanel 实装 | grep `WorkpaperSidePanel.vue` | ✅ 10 Tab（R8 + R9 已完成） | 已满足，本 spec 不重做 |
| DegradedBanner 已挂载 | grep `<DegradedBanner` | ✅ 已挂 ThreeColumnLayout | 已满足，本 spec 扩展功能 |
| outbox_replay_worker DLQ | grep `event_outbox_dlq` | ✅ 已实装（ledger-import-view-refactor） | 已满足，本 spec 复用 |
| 5xx 监控 baseline | 当前 `http.ts` 是否有 5xx 计数器 | ❌ 无 | Sprint 1 新增 |
| event-cascade-health 端点 | grep `event-cascade/health` | ❌ 不存在 | Sprint 1 新建 |

**关键发现**（grep 实测 2026-05-16）：
- v3 §10.2.A confirmLeave 主战场已全部落地（R8-S2-14 已完成 3 编辑器接入）
- WorkpaperSidePanel 已 10 Tab（不止 v3 文档说的 7 Tab），不需重做
- 本 spec 真实剩余范围 = 后端事件级联监控 + DegradedBanner 5xx 扩展 + 危险操作补漏 + EQCR 版本对比

---

## 风险与冲突

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 5xx 计数器误报淹没用户 | 中 | 中 | 阈值多档 + 30s 滑动窗口 + 至少 10 次请求才计算 |
| stuck_handlers 查询 PG slow query | 低 | 中 | 加 partial index `WHERE status='processing'`（v3 §3 已有） |
| event-cascade-health 暴露内部信息 | 中 | 中 | admin/partner 才能看；普通用户只看 status 字段 |
| confirmDangerous 改动太多文件 | 低 | 低 | 仅 5 个签字组件 + 2 个高危视图，影响面可控 |
| EQCR 版本对比涉及 Word 文档 diff 复杂 | 高 | 低 | Sprint 2 优先级标"可选"，工时不够则降级为 Spec D 范围 |

---

## 不做清单（明确排除）

- ❌ 暗色模式（先把 token 打实，Spec B Sprint 1 先做）
- ❌ 自动错误重试机制（5xx 自动重试容易雪崩，用户偏好"明确显示+手动重试"）
- ❌ 全栈 APM 监控（Sentry / Prometheus 端到端）— 太重，本期只做应用层 Banner + health 端点
- 🟡 EQCR 备忘录富文本 diff（Spec D 评估）

---

## 预期交付

- **后端代码**：1 个新端点 (`event_cascade_health.py`) + 4 个 worker 心跳写入（5 文件改动）
- **前端代码**：DegradedBanner 扩展（1 文件大改）+ http.ts 5xx 监控（1 文件加） + 5 个签字组件 + 2 个高危视图加 confirmDangerous（7 文件小改）
- **文档**：`docs/EVENT_CASCADE_HEALTH_GUIDE.md` + `docs/WORKPAPER_SIDE_PANEL_GUIDE.md`
- **回归**：vue-tsc + getDiagnostics 0 错误 + 5xx 模拟测试（手动 kill 后端看 Banner 状态切换）
- **三件套补齐**：Sprint 0 末尾产出 requirements / design / tasks（届时再做）

---

## 与 Spec B 的并行关系

依赖面不重叠（Spec B 改样式 + 组件，Spec C 改后端聚合 + 前端容灾），可并行执行。

冲突点：
1. **Adjustments 视图**：Spec B 拆 GtEditableTable + Spec C 加 confirmDangerous 删除分录组——建议 Spec C 先合（改动小），Spec B 再基于此基线拆分
2. **DegradedBanner 视觉**：Spec B 颜色 token 化会触碰 DegradedBanner 的颜色值——Spec B Sprint 2 末尾合时同步刷一遍

---

**预期工时**：起草三件套 0.5 天 + 实施 2 周 = **11 个工作日**（不含上线前 UAT）。

下一步：v3 P0 全清 + Spec A 观察期满后，本 README 升级为完整三件套（requirements / design / tasks）。
