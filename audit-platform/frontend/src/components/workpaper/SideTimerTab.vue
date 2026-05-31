<!--
  SideTimerTab.vue — A-5 底稿内计时器（侧边栏）

  spec proposal-remaining-18 task 1.4

  - 大型 HH:MM:SS 显示 + 开始/暂停/停止/重置
  - localStorage 持久化（key: gt:wp-timer:{projectId}:{wpId}）
  - 停止时 / 监听到 workpaper:saved 时自动 POST /api/projects/{pid}/workhours
  - cycle 自动从 wp_code 前缀推断（后端 _infer_cycle）
  - 计时不足 0.01h 不提交
-->
<template>
  <div class="gt-side-timer">
    <div v-if="!wpId" class="gt-wp-side-placeholder">请先选择底稿</div>
    <div v-else class="gt-side-timer-body">
      <div class="gt-timer-display" :class="`status-${status}`">
        {{ formattedTime }}
      </div>

      <div class="gt-timer-meta">
        <el-tag :type="statusTagType" size="small" round>{{ statusLabel }}</el-tag>
        <span class="gt-timer-hours-hint">≈ {{ formattedHours }} 小时</span>
      </div>

      <div class="gt-timer-controls">
        <el-button
          v-if="status !== 'running'"
          type="primary"
          size="small"
          @click="onStart"
        >
          ▶ 开始
        </el-button>
        <el-button
          v-else
          type="warning"
          size="small"
          @click="onPause"
        >
          ⏸ 暂停
        </el-button>
        <el-button
          type="danger"
          size="small"
          :disabled="totalMs === 0 || submitting"
          :loading="submitting"
          @click="onStop"
        >
          ⏹ 停止并保存
        </el-button>
        <el-button
          text
          size="small"
          :disabled="status === 'running' || totalMs === 0"
          @click="onReset"
        >
          重置
        </el-button>
      </div>

      <div v-if="lastSubmittedHours !== null" class="gt-timer-last">
        ✓ 上次提交 {{ lastSubmittedHours.toFixed(2) }}h · {{ lastSubmittedAt }}
      </div>

      <div class="gt-timer-tip">
        ⓘ 计时进度本地保存，刷新页面不丢失。<br />
        保存底稿时自动提交累计时间为工时。
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { handleApiError } from '@/utils/errorHandler'

type TimerStatus = 'idle' | 'running' | 'paused'

const props = defineProps<{
  /** 项目 ID（必传，用于 localStorage namespace 与 API 路径） */
  projectId: string
  /** 底稿 ID（可选） */
  wpId?: string
  /** 底稿编码（可选，传给后端用于自动推断 cycle） */
  wpCode?: string
}>()

const status = ref<TimerStatus>('idle')
const startedAt = ref<number | null>(null)
const accumulatedMs = ref(0)
const tickTrigger = ref(0)
const submitting = ref(false)
const lastSubmittedHours = ref<number | null>(null)
const lastSubmittedAt = ref<string | null>(null)

let intervalId: ReturnType<typeof setInterval> | null = null

const storageKey = computed(() =>
  props.wpId ? `gt:wp-timer:${props.projectId}:${props.wpId}` : '',
)

/** 当前累计毫秒（含正在运行的部分） */
const totalMs = computed(() => {
  // 强制依赖 tickTrigger 以便每秒重算
  void tickTrigger.value
  if (status.value === 'running' && startedAt.value !== null) {
    return Math.max(0, accumulatedMs.value + (Date.now() - startedAt.value))
  }
  return Math.max(0, accumulatedMs.value)
})

const formattedTime = computed(() => {
  const total = Math.floor(totalMs.value / 1000)
  const h = String(Math.floor(total / 3600)).padStart(2, '0')
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, '0')
  const s = String(total % 60).padStart(2, '0')
  return `${h}:${m}:${s}`
})

const formattedHours = computed(() => (totalMs.value / 3600000).toFixed(2))

const statusLabel = computed(() =>
  status.value === 'running' ? '计时中' : status.value === 'paused' ? '已暂停' : '未开始',
)

const statusTagType = computed<'success' | 'warning' | 'info'>(() =>
  status.value === 'running' ? 'success' : status.value === 'paused' ? 'warning' : 'info',
)

// ─── 持久化 ─────────────────────────────────────────────────────────────────

function persist() {
  if (!storageKey.value) return
  try {
    localStorage.setItem(
      storageKey.value,
      JSON.stringify({
        status: status.value,
        startedAt: startedAt.value,
        accumulatedMs: accumulatedMs.value,
      }),
    )
  } catch {
    /* localStorage 满 / 隐私模式 — 静默失败 */
  }
}

function clearPersist() {
  if (!storageKey.value) return
  try {
    localStorage.removeItem(storageKey.value)
  } catch {
    /* ignore */
  }
}

function restore() {
  if (!storageKey.value) return
  try {
    const raw = localStorage.getItem(storageKey.value)
    if (!raw) return
    const data = JSON.parse(raw)
    const restoredStatus: TimerStatus =
      data?.status === 'running' || data?.status === 'paused' ? data.status : 'idle'
    status.value = restoredStatus
    startedAt.value = typeof data?.startedAt === 'number' ? data.startedAt : null
    accumulatedMs.value = typeof data?.accumulatedMs === 'number' ? data.accumulatedMs : 0

    if (status.value === 'running') {
      // 若 startedAt 缺失（异常状态），退回 paused 累计已有时间
      if (startedAt.value === null) {
        status.value = 'paused'
      } else {
        startTicker()
      }
    }
  } catch {
    clearPersist()
  }
}

// ─── 计时核心 ────────────────────────────────────────────────────────────────

function startTicker() {
  if (intervalId !== null) return
  intervalId = setInterval(() => {
    tickTrigger.value = (tickTrigger.value + 1) % 1_000_000
  }, 1000)
}

function stopTicker() {
  if (intervalId !== null) {
    clearInterval(intervalId)
    intervalId = null
  }
}

function onStart() {
  if (status.value === 'running') return
  status.value = 'running'
  startedAt.value = Date.now()
  startTicker()
  persist()
}

function onPause() {
  if (status.value !== 'running') return
  if (startedAt.value !== null) {
    accumulatedMs.value += Date.now() - startedAt.value
  }
  startedAt.value = null
  status.value = 'paused'
  stopTicker()
  persist()
}

async function onStop() {
  // 先冻结当前累计
  if (status.value === 'running' && startedAt.value !== null) {
    accumulatedMs.value += Date.now() - startedAt.value
    startedAt.value = null
  }
  stopTicker()

  const hours = roundHours(accumulatedMs.value)

  if (hours < 0.01) {
    ElMessage.warning('计时不足 0.01 小时，未提交')
    onReset()
    return
  }

  if (!props.wpId || !props.projectId) {
    ElMessage.error('缺少底稿信息，无法提交工时')
    return
  }

  await submitWorkhour(hours)
}

function onReset() {
  status.value = 'idle'
  startedAt.value = null
  accumulatedMs.value = 0
  stopTicker()
  clearPersist()
}

/** 累计 ms → 小时（保留 2 位小数，避免后端 24h 校验浮点误差） */
function roundHours(ms: number): number {
  return Math.round((ms / 3_600_000) * 100) / 100
}

async function submitWorkhour(hours: number) {
  if (submitting.value) return
  submitting.value = true
  try {
    const today = new Date().toISOString().slice(0, 10)
    await api.post(`/api/projects/${props.projectId}/workhours`, {
      date: today,
      hours,
      wp_code: props.wpCode || undefined,
      description: '底稿计时器自动记录',
    })
    lastSubmittedHours.value = hours
    lastSubmittedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    ElMessage.success(`已提交 ${hours.toFixed(2)} 小时工时`)
    // 提交成功 → 清空状态
    status.value = 'idle'
    startedAt.value = null
    accumulatedMs.value = 0
    clearPersist()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '请稍后重试'
    handleApiError(e, '工时提交')
    // 失败保留状态以便重试
    status.value = 'paused'
    persist()
  } finally {
    submitting.value = false
  }
}

// ─── 监听底稿保存事件 ────────────────────────────────────────────────────────

async function onWorkpaperSaved(payload: { wpId?: string; wp_id?: string }) {
  if (!props.wpId) return
  const eventWpId = payload?.wpId ?? payload?.wp_id
  if (eventWpId !== props.wpId) return

  // 冻结当前运行段
  if (status.value === 'running' && startedAt.value !== null) {
    accumulatedMs.value += Date.now() - startedAt.value
    startedAt.value = null
    status.value = 'paused'
    stopTicker()
  }

  const hours = roundHours(accumulatedMs.value)
  if (hours < 0.01) return // 累计太短跳过

  await submitWorkhour(hours)
}

// ─── 生命周期 ───────────────────────────────────────────────────────────────

onMounted(() => {
  restore()
  eventBus.on('workpaper:saved', onWorkpaperSaved as never)
})

onUnmounted(() => {
  // 卸载时若仍在跑，转为 paused 持久化（用户切换 sheet/视图不丢时间）
  if (status.value === 'running' && startedAt.value !== null) {
    accumulatedMs.value += Date.now() - startedAt.value
    startedAt.value = null
    status.value = 'paused'
    persist()
  }
  stopTicker()
  eventBus.off('workpaper:saved', onWorkpaperSaved as never)
})

// 切换底稿时重置并恢复新底稿状态
watch(
  () => props.wpId,
  (newId, oldId) => {
    if (newId === oldId) return
    // 旧 wp 若在运行 → 写入旧 wp 的 localStorage key 为 paused
    if (oldId && (status.value === 'running' || status.value === 'paused')) {
      let snapshotMs = accumulatedMs.value
      if (status.value === 'running' && startedAt.value !== null) {
        snapshotMs += Date.now() - startedAt.value
      }
      try {
        localStorage.setItem(
          `gt:wp-timer:${props.projectId}:${oldId}`,
          JSON.stringify({
            status: 'paused',
            startedAt: null,
            accumulatedMs: snapshotMs,
          }),
        )
      } catch {
        /* ignore */
      }
    }
    stopTicker()
    status.value = 'idle'
    startedAt.value = null
    accumulatedMs.value = 0
    if (newId) restore()
  },
)

// 暴露给测试 / 父组件（手动触发场景）
defineExpose({
  start: onStart,
  pause: onPause,
  stop: onStop,
  reset: onReset,
  submitWorkhour,
})
</script>

<style scoped>
.gt-side-timer {
  padding: var(--gt-space-2);
}

.gt-side-timer-body {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--gt-space-3);
}

.gt-timer-display {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 36px /* allow-px: 计时器主显示 */;
  font-weight: 700;
  text-align: center;
  letter-spacing: 2px;
  padding: var(--gt-space-3) var(--gt-space-2);
  border-radius: var(--gt-radius-md);
  background: var(--gt-color-bg-elevated);
  color: var(--gt-color-text);
  font-variant-numeric: tabular-nums;
  border: 1px solid var(--gt-color-border-light);
}

.gt-timer-display.status-running {
  color: var(--gt-color-success);
  border-color: var(--gt-color-success);
  background: var(--gt-color-success-light, rgba(103, 194, 58, 0.08));
}

.gt-timer-display.status-paused {
  color: var(--gt-color-warning, #e6a23c);
  border-color: var(--gt-color-warning, #e6a23c);
}

.gt-timer-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--gt-font-size-xs);
}

.gt-timer-hours-hint {
  color: var(--gt-color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.gt-timer-controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gt-space-2);
}

.gt-timer-controls .el-button {
  flex: 1 1 auto;
}

.gt-timer-last {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-success);
  text-align: center;
  padding: 4px;
  border-radius: var(--gt-radius-sm);
  background: var(--gt-color-success-light, rgba(103, 194, 58, 0.08));
}

.gt-timer-tip {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  line-height: 1.5;
  padding: var(--gt-space-2);
  background: var(--gt-color-bg-page, var(--gt-color-bg-elevated));
  border-radius: var(--gt-radius-sm);
}

.gt-wp-side-placeholder {
  padding: var(--gt-space-8);
  text-align: center;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
}
</style>
