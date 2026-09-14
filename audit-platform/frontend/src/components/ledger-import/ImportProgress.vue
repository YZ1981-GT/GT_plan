<template>
  <div class="import-progress">
    <!-- 四段式进度 -->
    <div class="phase-segments">
      <div
        v-for="phase in phases"
        :key="phase.key"
        class="phase-segment"
        :class="{ active: phase.key === currentPhase, completed: phase.completed }"
      >
        <div class="phase-label">{{ phase.label }}</div>
        <el-progress
          :percentage="phase.percent"
          :status="phase.completed ? 'success' : undefined"
          :stroke-width="8"
        />
      </div>
    </div>

    <!-- 当前状态 -->
    <div class="status-area">
      <div class="status-message">
        <el-icon v-if="!isFinished" class="is-loading"><Loading /></el-icon>
        <el-icon v-else-if="isSuccess"><CircleCheck /></el-icon>
        <el-icon v-else><CircleClose /></el-icon>
        <span>{{ statusMessage }}</span>
      </div>

      <div v-if="currentFile" class="current-file">
        正在处理：{{ currentFile }}
      </div>
    </div>

    <!-- 总进度 -->
    <el-progress
      :percentage="totalPercent"
      :status="progressStatus"
      :stroke-width="12"
      style="margin-top: 20px"
    />

    <!-- 操作按钮 -->
    <div class="step-actions">
      <el-tooltip
        v-if="!isFinished"
        :disabled="canMoveToBackground"
        content="数据写入数据库后才可放到后台，请稍候..."
        placement="top"
      >
        <span>
          <el-button
            aria-label="放到后台继续"
            type="primary"
            plain
            :disabled="!canMoveToBackground"
            @click="onMoveToBackground"
          >
            {{ canMoveToBackground ? '放到后台继续' : '准备中，请稍候…' }}
          </el-button>
        </span>
      </el-tooltip>
      <el-button
        v-if="!isFinished"
        type="danger"
        plain
        aria-label="取消导入"
        @click="onCancel"
      >
        取消导入
      </el-button>
      <el-button
        v-if="isSuccess"
        type="primary"
        aria-label="完成导入"
        @click="emit('complete')"
      >
        完成
      </el-button>
    </div>

    <!-- 关注事项提示（仅进行中） -->
    <el-alert
      v-if="!isFinished"
      type="info"
      :closable="false"
      show-icon
      style="margin-top: 16px"
    >
      <template #title>
        <span class="tips-title">关注事项</span>
      </template>
      <ul class="tips-list">
        <li>数据正在后台写入，关闭或切走页面不会中断导入；顶栏"导入中"指示器可追踪进度</li>
        <li>大文件（&gt;50MB）耗时较长，建议点"放到后台继续"先处理别的工作</li>
        <li>导入完成前请勿重复提交同一年度的相同文件，否则旧 dataset 会被 superseded 但数据可能累加</li>
        <li>取消导入会清理 staged 数据但不影响已激活的历史数据集</li>
      </ul>
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Loading, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSSEReconnect } from '@/composables/useSSEReconnect'

// ─── Props & Emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  projectId: string
  jobId: string
}>()

const emit = defineEmits<{
  complete: []
  failed: []
  canceled: []
  background: []  // 放后台继续（不取消 worker，仅关闭对话框）
}>()

// ─── Types ──────────────────────────────────────────────────────────────────

interface PhaseInfo {
  key: string
  label: string
  percent: number
  completed: boolean
}

interface SSEMessage {
  phase: string
  percent?: number
  status?: string
  file?: string
  sheet?: string
  rows?: number
  message?: string
  dataset_id?: string
  result?: unknown
  error?: string
}

// ─── State ──────────────────────────────────────────────────────────────────

const currentPhase = ref('uploading')
const totalPercent = ref(0)
const statusMessage = ref('准备中...')
const currentFile = ref('')
const isFinished = ref(false)
const isSuccess = ref(false)

const phases = ref<PhaseInfo[]>([
  { key: 'uploading', label: '上传', percent: 100, completed: true },
  { key: 'parsing', label: '解析', percent: 0, completed: false },
  { key: 'validating', label: '校验', percent: 0, completed: false },
  { key: 'writing', label: '写入', percent: 0, completed: false },
  { key: 'activating', label: '激活', percent: 0, completed: false },
])

// 后端 phase 名到前端 key 的映射（bootstrap/queued 归入 parsing 前的占位）
const PHASE_MAP: Record<string, string> = {
  bootstrap: 'parsing',
  queued: 'parsing',
  pending: 'parsing',
  parsing: 'parsing',
  validating: 'validating',
  writing: 'writing',
  activating: 'activating',
}

// ─── Computed ───────────────────────────────────────────────────────────────

const progressStatus = computed(() => {
  if (isSuccess.value) return 'success'
  if (isFinished.value && !isSuccess.value) return 'exception'
  return undefined
})

// 是否可安全"放到后台继续"——必须到达"写入"阶段后（解析/校验阶段中断风险高）
const PHASE_ORDER = ['uploading', 'parsing', 'validating', 'writing', 'activating']
const bgTimeoutElapsed = ref(false)
let bgTimeoutTimer: ReturnType<typeof setTimeout> | null = null
const canMoveToBackground = computed(() => {
  const idx = PHASE_ORDER.indexOf(currentPhase.value)
  // 写入阶段(idx>=3)或已完成才允许后台化；
  // 兜底：挂载超过 30s 仍未推到 writing（单 worker 阻塞 SSE）也放开——
  // 后台化本质只关 SSE 不影响后端继续跑，不会丢数据
  return idx >= 3 || isFinished.value || bgTimeoutElapsed.value
})

// ─── SSE via useSSEReconnect ────────────────────────────────────────────────

const { connected, reconnecting, gaveUp, close: closeSSE } = useSSEReconnect({
  url: () => `/api/projects/${props.projectId}/ledger-import/jobs/${props.jobId}/stream`,
  onMessage: handleSSEMessage,
  pollFallback: async () => {
    const { api } = await import('@/services/apiProxy')
    const job: any = await api.get(
      `/api/projects/${props.projectId}/ledger-import/jobs/${props.jobId}`,
      { _silent: true } as any
    )
    const status = job?.status
    if (status === 'completed') {
      isFinished.value = true
      isSuccess.value = true
      statusMessage.value = '导入完成'
      currentFile.value = ''
      phases.value.forEach(p => { p.percent = 100; p.completed = true })
      totalPercent.value = 100
      return 'completed'
    }
    if (status === 'failed' || status === 'timed_out' || status === 'canceled') {
      isFinished.value = true
      isSuccess.value = false
      statusMessage.value = job?.error_message || job?.message || '导入失败'
      emit('failed')
      return 'failed'
    }
    // 仍在进行中：同步一次进度
    if (typeof job?.progress_pct === 'number') {
      totalPercent.value = job.progress_pct
    }
    if (job?.progress_message) {
      statusMessage.value = job.progress_message
    }
    return 'running'
  },
  maxAttempts: 30,
  backoffMs: 2000,
  onReconnecting: () => {
    statusMessage.value = '正在同步进度...'
  },
  onGaveUp: () => {
    statusMessage.value = '连接中断，请稍候或点"放到后台继续"'
  },
})

function handleSSEMessage(data: SSEMessage) {
  // 映射后端 phase 到前端 phase key（bootstrap/queued/pending 都归入 parsing）
  const mapped = PHASE_MAP[data.phase] || data.phase
  currentPhase.value = mapped

  if (data.file) {
    currentFile.value = data.file + (data.sheet ? ` / ${data.sheet}` : '')
  }

  if (data.message) {
    statusMessage.value = data.message
  }

  // 更新各阶段进度
  const phaseIdx = phases.value.findIndex(p => p.key === mapped)
  if (phaseIdx >= 0 && data.percent !== undefined) {
    phases.value[phaseIdx].percent = data.percent
    // 标记之前的阶段为完成
    for (let i = 0; i < phaseIdx; i++) {
      phases.value[i].percent = 100
      phases.value[i].completed = true
    }
  }

  // 计算总进度（各阶段均分 100%）
  const total = phases.value.reduce((sum, p) => sum + p.percent, 0)
  totalPercent.value = Math.round(total / phases.value.length)

  // 完成（后端可能用 phase:"completed" 或 status:"completed" 表示）
  if (data.phase === 'completed' || data.status === 'completed') {
    isFinished.value = true
    isSuccess.value = true
    statusMessage.value = '导入完成'
    currentFile.value = ''
    phases.value.forEach(p => { p.percent = 100; p.completed = true })
    totalPercent.value = 100
    closeSSE()
  }

  // 失败（phase/status/error 任一指示失败）
  if (
    data.phase === 'failed' ||
    data.status === 'failed' ||
    data.status === 'timed_out' ||
    data.status === 'canceled' ||
    data.error
  ) {
    isFinished.value = true
    isSuccess.value = false
    statusMessage.value = data.error || data.message || '导入失败'
    closeSSE()
    emit('failed')
  }
}

// ─── Actions ────────────────────────────────────────────────────────────────

async function onCancel() {
  try {
    await ElMessageBox.confirm('确定要取消当前导入作业吗？已处理的数据将被清理。', '取消导入', {
      type: 'warning',
    })
    const { api } = await import('@/services/apiProxy')
    await api.post(`/api/projects/${props.projectId}/ledger-import/jobs/${props.jobId}/cancel`)
    closeSSE()
    isFinished.value = true
    statusMessage.value = '已取消'
    emit('canceled')
  } catch {
    // 用户取消确认
  }
}

function onMoveToBackground() {
  // 关闭 SSE 不取消 worker，让后端继续跑
  closeSSE()
  ElMessage.success({
    message: '已转入后台，顶栏"导入中"指示器可追踪进度',
    duration: 3000,
  })
  emit('background')
}

// 导入进行期间抑制全局超时弹窗（后端 worker 被大文件占用，其他请求超时属正常）
onMounted(() => {
  ;(globalThis as any).__suppressTimeoutToast = true
  // 兜底：30s 后即使 SSE 未推到 writing（单 worker 阻塞）也允许"放到后台继续"
  bgTimeoutTimer = setTimeout(() => { bgTimeoutElapsed.value = true }, 30000)
})
onUnmounted(() => {
  ;(globalThis as any).__suppressTimeoutToast = false
  if (bgTimeoutTimer) clearTimeout(bgTimeoutTimer)
})
</script>

<style scoped>
.import-progress {
  padding: 16px;
}

.phase-segments {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

.phase-segment {
  text-align: center;
}

.phase-segment .phase-label {
  font-size: var(--gt-font-size-xs);
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}

.phase-segment.active .phase-label {
  color: var(--el-color-primary);
  font-weight: 600;
}

.phase-segment.completed .phase-label {
  color: var(--el-color-success);
}

.status-area {
  text-align: center;
  padding: 16px 0;
}

.status-message {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: var(--gt-font-size-sm);
}

.current-file {
  margin-top: 8px;
  font-size: var(--gt-font-size-xs);
  color: var(--el-text-color-secondary);
}

.step-actions {
  margin-top: 24px;
  text-align: center;
  display: flex;
  justify-content: center;
  gap: 12px;
}

.tips-title {
  font-weight: 600;
  color: var(--el-color-primary);
}
.tips-list {
  margin: 6px 0 0;
  padding-left: 20px;
  font-size: var(--gt-font-size-xs);
  line-height: 1.8;
  color: var(--el-text-color-regular);
}
.tips-list li {
  list-style: disc;
}
</style>
