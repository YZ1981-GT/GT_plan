# Spec C (R10) — Editor Resilience · Design

**版本**：v1.0
**起草日期**：2026-05-16
**关联**：`requirements.md` v1.0

---

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-16 | 设计稿初稿 |

---

## 1. 总体架构

```
后端
├─ 4 worker 心跳 → Redis worker_heartbeat:{name}（TTL=60s）
├─ event_outbox 状态查询（已有 partial index）
├─ DLQ 深度查询（commit 19f1c5e 已实装）
└─ /api/projects/{pid}/event-cascade/health 端点（聚合上面 3 个数据源）

前端
├─ http.ts 5xx 环形缓冲区（last100Requests）
├─ DegradedBanner 订阅源扩展（SSE + 5xx + cascade-health）
├─ confirmDangerous 补漏（LedgerDataManager / EqcrMemoEditor / 5 签字组件）
└─ WorkpaperSidePanel 使用文档（不改代码）
```

---

## 2. 架构决策

### D1 worker 心跳走 Redis 不走 PG

**问题**：心跳写 PG 还是 Redis？

**决策**：**Redis**。
- TTL 自然过期（PG 需要定时清理）
- 写入频率高（每 30s × 4 worker = 8 次/分钟），Redis 内存适合
- 读取速度快（health 端点 P95 ≤ 200ms 要求）

**Redis key 设计**：
- key: `worker_heartbeat:{worker_name}`
- value: JSON `{last_heartbeat: ISO8601, pid, version, hostname}`
- TTL: 60s（2 倍心跳间隔，超时即视为 worker miss）

### D2 health 端点状态判定阈值

| 状态 | 条件 |
|------|------|
| healthy | lag ≤ 60s AND dlq_depth = 0 AND 全部 worker alive |
| degraded | lag > 60s OR dlq_depth > 0 OR 1 个 worker miss |
| critical | lag > 300s OR worker miss > 1 |

**理由**：
- lag 60s/300s 阈值参考 outbox_replay_worker 平均处理速度 + 大账套场景
- worker miss 1 个允许（短暂重启）；2 个以上认定系统级故障
- DLQ > 0 即降级提示运维介入（DLQ 设计是异常态）

### D3 普通用户只看 status 字段（NF2）

**实现**：
- 端点路由不区分（同一 URL）
- service 层根据 `current_user.role` 过滤响应：
  - admin/partner → 完整响应（含 worker_status / stuck_handlers / outbox_id）
  - 其他 → 只返回 `{status: "healthy" | "degraded" | "critical", lag_seconds: 12}`

**理由**：内部信息（worker pid / outbox_id）不暴露给普通用户，但状态本身让所有用户感知。

### D4 5xx 环形缓冲区在 http.ts 内部不暴露给业务代码

**问题**：是否把 `last100Requests` 暴露给所有视图？

**决策**：**只暴露 `recent5xxRate` 和 `getRecentNetworkStats()`，不暴露原始数组**。

**理由**：
- 避免业务代码直接读取请求历史（隐私 / 性能）
- 计算逻辑封闭在 http.ts 内部，便于将来切换实现

### D5 DegradedBanner 60s 轮询独立 axios 实例

**问题**：DegradedBanner 自己轮询 health 端点会和业务请求竞争 connection pool 吗？

**决策**：用独立 axios 实例 `bannerHttpClient`，不走全局 interceptor，不计入 5xx 缓冲区。

**理由**：
- 避免 health 端点的 5xx 误触发自身降级（递归）
- 独立实例可设更短超时（5s）+ silent error（不弹 toast）

### D6 confirmDangerous 不引入新组件，沿用现有

**问题**：confirmDangerous / confirmSign 是新建组件还是用 ElMessageBox 包装？

**决策**：**沿用 `utils/confirm.ts` 已有模式**（R7-S1-08 已建）。
- 新增 `confirmSign(action: string, ctx: { user, project })` 包装函数
- 不新建组件，避免组件库膨胀

**理由**：confirm.ts 已是平台标准，5 签字组件统一调用同一函数便于未来调整文案。

### D7 health 端点 Redis 不可用时的降级行为

**问题**：Redis 挂了 health 端点应该返回什么？

**决策**：返回 `{status: "degraded", worker_status: {}, redis_available: false}` 不抛 500。

**理由**：
- 监控端点本身不应级联失败
- 显式标注 `redis_available: false` 让运维知道是监控降级而非业务降级
- 普通用户仍看到 `status: degraded` 即可

### D8 EQCR 备忘录版本对比可选实施

**问题**：F8 是必做还是可选？

**决策**：**可选**。Sprint 2 计划 5 天，前 4 天做 F5/F6/F7 + 文档。如有余力再做 F8（需新建表 + 后端端点 + 前端 diff 抽屉），约 2 天工时。

**降级方案**：F8 不做则保留为 Spec D 范围，不影响本 spec 上线。

---

## 3. 后端设计

### 3.1 `event_cascade_health.py` 端点

```python
# backend/app/routers/event_cascade_health.py
from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_current_user, require_project_access, get_db
from app.services.event_cascade_health_service import EventCascadeHealthService

router = APIRouter(prefix="/api/projects/{project_id}/event-cascade", tags=["event-cascade"])

@router.get("/health")
async def get_event_cascade_health(
    project_id: UUID,
    current_user: User = Depends(require_project_access("readonly")),
    db: AsyncSession = Depends(get_db),
):
    svc = EventCascadeHealthService(db)
    full = await svc.get_health_summary(project_id)

    # D3: 普通用户只看 status / lag_seconds
    if current_user.role.value not in ("admin", "partner"):
        return {
            "status": full["status"],
            "lag_seconds": full["lag_seconds"],
        }
    return full
```

### 3.2 `EventCascadeHealthService`

```python
# backend/app/services/event_cascade_health_service.py
class EventCascadeHealthService:
    WORKER_NAMES = ["sla_worker", "import_recover_worker", "outbox_replay_worker", "import_worker"]

    async def get_health_summary(self, project_id: UUID) -> dict:
        lag_seconds = await self._get_outbox_lag()
        stuck_handlers = await self._get_stuck_handlers()
        dlq_depth = await self._get_dlq_depth()
        worker_status = await self._get_worker_status()  # D7 Redis 降级 → {}

        status = self._compute_status(lag_seconds, stuck_handlers, dlq_depth, worker_status)
        return {
            "lag_seconds": lag_seconds,
            "stuck_handlers": stuck_handlers,
            "dlq_depth": dlq_depth,
            "worker_status": worker_status,
            "status": status,
        }

    async def _get_outbox_lag(self) -> int:
        sql = text("""
            SELECT EXTRACT(EPOCH FROM (now() - MIN(created_at)))::INT as lag
            FROM event_outbox
            WHERE status = 'processing' OR status = 'pending'
        """)
        # 已有 partial index `WHERE status='processing'`
        return result.scalar() or 0

    async def _get_worker_status(self) -> dict:
        try:
            result = {}
            for name in self.WORKER_NAMES:
                key = f"worker_heartbeat:{name}"
                raw = await redis_client.get(key)
                if raw:
                    payload = json.loads(raw)
                    last_hb = datetime.fromisoformat(payload["last_heartbeat"])
                    stale = (datetime.now(UTC) - last_hb).total_seconds()
                    result[name] = {"alive": stale < 60, "last_heartbeat": payload["last_heartbeat"], "stale_seconds": int(stale)}
                else:
                    result[name] = {"alive": False, "last_heartbeat": None, "stale_seconds": None}
            return result
        except Exception as e:
            logger.warning(f"Redis unavailable for worker heartbeat: {e}")
            return {}

    def _compute_status(self, lag, stuck, dlq, workers) -> str:
        miss_count = sum(1 for w in workers.values() if not w["alive"])
        if lag > 300 or miss_count > 1:
            return "critical"
        if lag > 60 or dlq > 0 or miss_count > 0:
            return "degraded"
        return "healthy"
```

### 3.3 worker 心跳写入

```python
# backend/app/workers/worker_helpers.py（新建）
async def write_heartbeat(worker_name: str):
    try:
        from app.core.redis import redis_client
        if redis_client is None:
            return
        payload = {
            "last_heartbeat": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
            "version": settings.app_version,
            "hostname": socket.gethostname(),
        }
        await redis_client.setex(f"worker_heartbeat:{worker_name}", 60, json.dumps(payload))
    except Exception as e:
        logger.debug(f"Failed to write heartbeat for {worker_name}: {e}")
```

每个 worker 主循环加：
```python
async def run(stop_event: asyncio.Event):
    while not stop_event.is_set():
        await write_heartbeat("sla_worker")
        # ... 业务逻辑
        await asyncio.wait_for(stop_event.wait(), timeout=30)
```

---

## 4. 前端设计

### 4.1 `http.ts` 5xx 环形缓冲

```typescript
// audit-platform/frontend/src/utils/http.ts
const last100Requests: { status: number; ts: number }[] = []
const MAX_BUFFER = 100
const WINDOW_MS = 60_000
const MIN_SAMPLES = 10

function trackResponse(status: number) {
  const now = Date.now()
  last100Requests.push({ status, ts: now })
  if (last100Requests.length > MAX_BUFFER) {
    last100Requests.shift()
  }
}

http.interceptors.response.use(
  (res) => { trackResponse(res.status); return res },
  (err) => { trackResponse(err.response?.status ?? 0); return Promise.reject(err) }
)

export const recent5xxRate = computed(() => {
  const now = Date.now()
  const recent = last100Requests.filter(r => now - r.ts < WINDOW_MS)
  if (recent.length < MIN_SAMPLES) return 0
  return recent.filter(r => r.status >= 500).length / recent.length
})

export function getRecentNetworkStats() {
  const now = Date.now()
  const recent = last100Requests.filter(r => now - r.ts < WINDOW_MS)
  const xx5 = recent.filter(r => r.status >= 500)
  return {
    total: recent.length,
    xx5_count: xx5.length,
    xx5_rate: recent.length >= MIN_SAMPLES ? xx5.length / recent.length : 0,
    last_5xx_at: xx5.length > 0 ? xx5[xx5.length - 1].ts : null,
  }
}
```

### 4.2 DegradedBanner.vue 三档

```vue
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { recent5xxRate } from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import axios from 'axios'

const auth = useAuthStore()
const cascadeHealth = ref<{ status: string; lag_seconds?: number } | null>(null)

// D5: 独立 axios 实例
const bannerClient = axios.create({ timeout: 5000 })

const isAdminOrPartner = computed(() => ['admin', 'partner'].includes(auth.user?.role ?? ''))

let pollTimer: number | null = null
async function pollHealth() {
  if (!auth.currentProjectId) return
  try {
    const r = await bannerClient.get(`/api/projects/${auth.currentProjectId}/event-cascade/health`, {
      headers: { Authorization: `Bearer ${auth.token}` }
    })
    cascadeHealth.value = r.data
  } catch {
    cascadeHealth.value = null
  }
}

onMounted(() => {
  pollHealth()
  pollTimer = window.setInterval(pollHealth, 60_000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

const level = computed(() => {
  // 优先级：critical > degraded > healthy
  if (recent5xxRate.value > 0.6) return 'critical'
  if (cascadeHealth.value?.status === 'critical') return 'critical'
  if (recent5xxRate.value > 0.3) return 'degraded'
  if (cascadeHealth.value?.status === 'degraded') return 'degraded'
  if (sseDisconnected.value > 60) return 'critical'   // SSE 断 60s
  if (sseDisconnected.value > 0) return 'degraded'
  return 'hidden'
})

const message = computed(() => {
  if (level.value === 'critical') return '部分功能暂时不可用'
  if (level.value === 'degraded') return '服务响应较慢'
  return ''
})
</script>

<template>
  <div v-if="level !== 'hidden'" :class="['gt-degraded-banner', level]">
    <span class="msg">{{ message }}</span>
    <el-button v-if="isAdminOrPartner" link @click="showDetails = !showDetails">详情</el-button>
    <div v-if="showDetails && cascadeHealth" class="details">
      <div>outbox lag: {{ cascadeHealth.lag_seconds }}s</div>
      <div v-if="cascadeHealth.worker_status">
        worker 状态：{{ JSON.stringify(cascadeHealth.worker_status) }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.gt-degraded-banner.degraded { background: var(--gt-bg-warning); }
.gt-degraded-banner.critical { background: var(--gt-bg-danger); }
</style>
```

### 4.3 confirmSign 新增

```typescript
// audit-platform/frontend/src/utils/confirm.ts
export async function confirmSign(
  action: string,
  ctx: { userName: string; projectName: string; objectName?: string },
): Promise<void> {
  await ElMessageBox.confirm(
    `<div>
      <p><b>操作：</b>${escapeHtml(action)}</p>
      <p><b>用户：</b>${escapeHtml(ctx.userName)}</p>
      <p><b>项目：</b>${escapeHtml(ctx.projectName)}</p>
      ${ctx.objectName ? `<p><b>对象：</b>${escapeHtml(ctx.objectName)}</p>` : ''}
      <p style="color: var(--gt-color-danger); font-weight: 600">
        签字操作不可撤销，请确认信息无误。
      </p>
    </div>`,
    '请确认签字',
    {
      type: 'warning',
      dangerouslyUseHTMLString: true,
      confirmButtonText: '确认签字',
      cancelButtonText: '取消',
      customClass: 'gt-confirm-sign',
    },
  )
}
```

---

## 5. 数据库设计（F8 可选）

### 5.1 `eqcr_memo_versions` 表（如做 F8）

```python
# backend/alembic/versions/eqcr_memo_versions_20260620.py
def upgrade():
    op.create_table(
        'eqcr_memo_versions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('version_no', sa.Integer, nullable=False),
        sa.Column('content', JSONB, nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_eqcr_memo_versions_project', 'eqcr_memo_versions', ['project_id', 'version_no'])
```

---

## 6. 风险与缓解

| 风险 | 概率 | 设计缓解 |
|------|------|---------|
| 5xx 计数器误报淹没用户 | 中 | 阈值多档（30%/60%）+ 60s 滑动窗口 + 至少 10 次请求才计算（D5） |
| stuck_handlers 查询 PG slow query | 低 | 复用现有 partial index `WHERE status='processing'`（v3 §3 已建） |
| event-cascade-health 暴露内部信息 | 中 | D3 普通用户只看 status；admin/partner 才看 worker_status |
| confirmDangerous 改动多文件 | 低 | 仅 5 签字组件 + 2 高危视图，影响面可控 |
| EQCR 版本对比涉及 Word diff 复杂 | 高 | F8 标可选，工时不够则降级 Spec D |
| Redis 不可用导致 health 端点 500 | 中 | D7 降级返回 `worker_status: {}` + `redis_available: false` |
| worker 心跳频繁写入 Redis 影响性能 | 低 | 30s 间隔 × 4 worker = 8 次/分钟，量级可忽略 |
| DegradedBanner 轮询和业务请求竞争 connection pool | 低 | D5 独立 axios 实例 + 5s 超时 |

---

## 7. 与 Spec B 协调

| 文件 | Spec C 改动 | Spec B 改动 | 协调策略 |
|------|------------|------------|---------|
| `Adjustments.vue` | confirmDangerous 删除分录组验证（已有，本 spec 验证） | F8 加右键菜单 + 字号 token 化 | Spec C 先合（改动小） |
| `DegradedBanner.vue` | F4 三档扩展（本 spec 主改） | Sprint 2 颜色 token 化 | Spec C Sprint 1 末尾 → Spec B Sprint 2 同步刷颜色 |
| `gt-tokens.css` | 不动 | Sprint 0 补完 | Spec B 主导 |

---

## 8. 数据流图

```
[Sprint 1: 后端健康度 + 前端监控]
worker 心跳 → Redis worker_heartbeat:{name}
                  ↓
event_cascade_health_service 聚合
  ├─ outbox lag (PG event_outbox)
  ├─ stuck handlers (PG partial index)
  ├─ DLQ depth (event_outbox_dlq)
  └─ worker status (Redis 4 keys)
                  ↓
GET /api/projects/{pid}/event-cascade/health
  ├─ admin/partner → 完整响应
  └─ 普通用户 → 仅 status

http.ts last100Requests → recent5xxRate computed
                  ↓
DegradedBanner.vue
  ├─ SSE 断线（已有）
  ├─ 5xx 比率（来自 http.ts）
  └─ /event-cascade/health 60s 轮询（独立 axios）
                  ↓
三档：hidden / 🟡 degraded / 🔴 critical

[Sprint 2: 危险操作 + 文档]
confirmSign 包装 → 5 签字组件 + LedgerDataManager + EqcrMemoEditor
docs/WORKPAPER_SIDE_PANEL_GUIDE.md 编写
docs/EVENT_CASCADE_HEALTH_GUIDE.md 编写

[F8 可选]
eqcr_memo_versions 表 + Alembic
EqcrMemoEditor 保存时 INSERT 版本
"📜 版本对比" 抽屉 + vue-diff
```

---

## 9. 关联文档

- `requirements.md` —— 需求源
- `backend/app/workers/` —— 4 个 worker 模块（加心跳）
- `backend/app/services/event_cascade_health_service.py` —— 新建 service
- `backend/app/routers/event_cascade_health.py` —— 新建 router
- `audit-platform/frontend/src/utils/http.ts` —— 加 5xx 监控
- `audit-platform/frontend/src/components/DegradedBanner.vue` —— 三档扩展
- `audit-platform/frontend/src/utils/confirm.ts` —— 加 confirmSign
- `docs/WORKPAPER_SIDE_PANEL_GUIDE.md` —— Sprint 2 新建
- `docs/EVENT_CASCADE_HEALTH_GUIDE.md` —— Sprint 2 新建
