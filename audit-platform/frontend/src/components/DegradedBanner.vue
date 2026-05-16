<script setup lang="ts">
/**
 * DegradedBanner — 系统降级横幅（R10 Spec C / Sprint 1.4）
 *
 * 三档扩展（design D2/D5）：
 * - hidden: 健康
 * - degraded: SSE 重连中 / 5xx 率 > 30% / outbox lag > 60s / 1 worker miss
 * - critical: SSE 断 > 60s / 5xx 率 > 60% / outbox lag > 300s / worker miss > 1
 *
 * 订阅源：
 * - SSE 断线（旧逻辑保留）
 * - http.ts 5xx 率（recent5xxRate）
 * - /event-cascade/health 60s 轮询（独立 axios 实例 D5，避免递归触发自身降级）
 *
 * 仅 admin/partner 看到详细信息（D3 隔离）。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'
import { recent5xxRate, getRecentNetworkStats } from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import { useRoute } from 'vue-router'

const auth = useAuthStore()
const route = useRoute()

// ─── 状态源 1：SSE 断线（旧逻辑） ──────────────────────────
const sseDegradedAt = ref<number | null>(null)
let sseDismissTimer: ReturnType<typeof setTimeout> | null = null

function handleSSE(payload: SyncEventPayload) {
  if (payload.event_type === 'linkage.cascade_degraded') {
    sseDegradedAt.value = Date.now()
    if (sseDismissTimer) clearTimeout(sseDismissTimer)
    sseDismissTimer = setTimeout(() => {
      sseDegradedAt.value = null
    }, 60_000)
  }
  if (
    payload.event_type === 'trial_balance.updated' ||
    payload.event_type === 'adjustment.batch_committed'
  ) {
    sseDegradedAt.value = null
    if (sseDismissTimer) {
      clearTimeout(sseDismissTimer)
      sseDismissTimer = null
    }
  }
}

const sseDisconnectedSeconds = computed(() => {
  if (!sseDegradedAt.value) return 0
  return Math.round((Date.now() - sseDegradedAt.value) / 1000)
})

// ─── 状态源 2：5xx 比率（来自 http.ts） ────────────────────
const xx5Rate = ref(0)
let xx5Timer: ReturnType<typeof setInterval> | null = null

function refreshXx5Rate() {
  xx5Rate.value = recent5xxRate()
}

// ─── 状态源 3：/event-cascade/health 轮询（admin/partner only） ──
// design D5：独立 axios 实例，不走全局 interceptor，不计入 5xx 缓冲区
const cascadeHealth = ref<{
  status?: string
  lag_seconds?: number
  worker_status?: Record<string, { alive: boolean; stale_seconds?: number | null }>
  redis_available?: boolean
  dlq_depth?: number
} | null>(null)
const bannerClient = axios.create({ timeout: 5000 })
let healthTimer: ReturnType<typeof setInterval> | null = null

const isAdminOrPartner = computed(() => {
  const role = auth.user?.role
  return role === 'admin' || role === 'partner'
})

const projectId = computed(() => {
  return (route.params?.projectId as string) || ''
})

async function pollHealth() {
  if (!projectId.value || !auth.token) return
  try {
    const r = await bannerClient.get(
      `/api/projects/${projectId.value}/event-cascade/health`,
      { headers: { Authorization: `Bearer ${auth.token}` } },
    )
    // 拦截器没解包，需要手动取
    cascadeHealth.value = r.data?.data ?? r.data
  } catch {
    cascadeHealth.value = null
  }
}

// ─── 三档判定 ─────────────────────────────────────────────
type Level = 'hidden' | 'degraded' | 'critical'

const level = computed<Level>(() => {
  // critical 优先
  if (xx5Rate.value > 0.6) return 'critical'
  if (cascadeHealth.value?.status === 'critical') return 'critical'
  if (sseDisconnectedSeconds.value > 60) return 'critical'

  // degraded 次之
  if (xx5Rate.value > 0.3) return 'degraded'
  if (cascadeHealth.value?.status === 'degraded') return 'degraded'
  if (sseDisconnectedSeconds.value > 0) return 'degraded'

  return 'hidden'
})

const message = computed(() => {
  if (level.value === 'critical') return '部分功能暂时不可用'
  if (level.value === 'degraded') return '服务响应较慢'
  return ''
})

// ─── 详情展开（admin/partner only） ──────────────────────
const showDetails = ref(false)

const detailLines = computed(() => {
  const lines: string[] = []
  if (xx5Rate.value > 0) {
    const stats = getRecentNetworkStats()
    lines.push(`最近 1 分钟错误率：${(xx5Rate.value * 100).toFixed(0)}%（${stats.xx5_count}/${stats.total} 请求）`)
  }
  if (cascadeHealth.value) {
    if (typeof cascadeHealth.value.lag_seconds === 'number') {
      lines.push(`Outbox 延迟：${cascadeHealth.value.lag_seconds}s`)
    }
    if (typeof cascadeHealth.value.dlq_depth === 'number' && cascadeHealth.value.dlq_depth > 0) {
      lines.push(`死信队列深度：${cascadeHealth.value.dlq_depth}`)
    }
    if (cascadeHealth.value.worker_status) {
      const dead = Object.entries(cascadeHealth.value.worker_status)
        .filter(([_, w]) => !w.alive)
        .map(([name]) => name)
      if (dead.length) {
        lines.push(`Worker 异常：${dead.join(', ')}`)
      }
    }
    if (cascadeHealth.value.redis_available === false) {
      lines.push('Redis 监控不可用（业务可能正常）')
    }
  }
  if (sseDisconnectedSeconds.value > 0) {
    lines.push(`SSE 断开：${sseDisconnectedSeconds.value}s`)
  }
  return lines
})

// ─── 用户手动 dismiss（TD-4 占位：sessionStorage 记忆 5min 不再提示） ──
const dismissed = ref(false)
const DISMISS_KEY = 'gt:degraded-banner:dismissed-at'
const DISMISS_TTL_MS = 5 * 60 * 1000

function checkDismissed() {
  try {
    const raw = sessionStorage.getItem(DISMISS_KEY)
    if (!raw) return
    const ts = Number(raw)
    if (Number.isFinite(ts) && Date.now() - ts < DISMISS_TTL_MS) {
      dismissed.value = true
    } else {
      sessionStorage.removeItem(DISMISS_KEY)
    }
  } catch { /* ignore */ }
}

function handleClose() {
  dismissed.value = true
  try {
    sessionStorage.setItem(DISMISS_KEY, String(Date.now()))
  } catch { /* ignore */ }
}

const visible = computed(() => level.value !== 'hidden' && !dismissed.value)

onMounted(() => {
  checkDismissed()
  eventBus.on('sse:sync-event', handleSSE)
  // 5xx 率每 5s 刷新一次
  xx5Timer = setInterval(refreshXx5Rate, 5_000)
  // health 端点 60s 轮询（仅 admin/partner，普通用户也轮询但只看 status）
  if (auth.token) {
    pollHealth()
    healthTimer = setInterval(pollHealth, 60_000)
  }
})

onUnmounted(() => {
  eventBus.off('sse:sync-event', handleSSE)
  if (sseDismissTimer) clearTimeout(sseDismissTimer)
  if (xx5Timer) clearInterval(xx5Timer)
  if (healthTimer) clearInterval(healthTimer)
})
</script>

<template>
  <el-alert
    v-if="visible"
    :type="level === 'critical' ? 'error' : 'warning'"
    :closable="true"
    show-icon
    :class="['gt-degraded-banner', `gt-degraded-${level}`]"
    @close="handleClose"
  >
    <template #title>
      {{ message }}
    </template>
    <template #default>
      <div class="gt-degraded-default">
        <span v-if="level === 'critical'">
          后端服务异常，建议稍后重试或联系运维。
        </span>
        <span v-else>
          系统响应较慢，部分操作可能延迟，您仍可正常使用。
        </span>
        <el-button
          v-if="isAdminOrPartner && detailLines.length"
          link
          size="small"
          @click="showDetails = !showDetails"
          style="margin-left: 8px"
        >
          {{ showDetails ? '收起详情' : '展开详情' }}
        </el-button>
        <ul v-if="showDetails && detailLines.length" class="gt-degraded-detail-list">
          <li v-for="(line, i) in detailLines" :key="i">{{ line }}</li>
        </ul>
      </div>
    </template>
  </el-alert>
</template>

<style scoped>
.gt-degraded-banner {
  position: sticky;
  top: 0;
  z-index: 100;
  border-radius: 0;
}
.gt-degraded-degraded {
  background: var(--gt-bg-warning);
}
.gt-degraded-critical {
  background: var(--gt-bg-danger);
}
.gt-degraded-default {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.gt-degraded-detail-list {
  width: 100%;
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.gt-degraded-detail-list li {
  margin-bottom: 2px;
}
</style>
