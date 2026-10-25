<!--
  合并推送运行面板（任务 13.3 / 需求 7.3、8.6）。
  独立于 E1 公式推送引擎：展示由当前合并项目发起的最近 10 次运行、逐项目四步、警告与立即推送。
  `queued=true/false` 都是成功回执（false = 已并入尚未开始的排队任务），不能误报成推送完成。
-->
<template>
  <div class="gt-cpp" data-testid="consol-push-panel">
    <div class="gt-cpp-toolbar">
      <div>
        <strong>合并推送</strong>
        <span class="gt-cpp-hint">由当前项目发起的最近 10 次；上层受影响项目列在每次运行的步骤中</span>
      </div>
      <div class="gt-cpp-actions">
        <el-button size="small" :loading="loading" data-testid="consol-push-refresh" @click="load">🔄 刷新</el-button>
        <el-button size="small" type="primary" :loading="pushing" :disabled="!canPush"
          data-testid="consol-push-now" @click="pushNow">📤 立即推送</el-button>
      </div>
    </div>

    <el-alert v-if="status?.is_stale" type="warning" :closable="false" show-icon class="gt-cpp-alert"
      data-testid="consol-push-stale"
      :title="`子企业数据已变化，建议重新推送${status.stale_rows ? `（${status.stale_rows} 行待更新）` : ''}`" />
    <el-alert v-if="loadError" type="error" :closable="false" show-icon class="gt-cpp-alert"
      data-testid="consol-push-error" :title="loadError" />
    <p v-if="status" class="gt-cpp-status" data-testid="consol-push-status">{{ pushStatusText(status) }}</p>

    <el-table v-loading="loading" :data="runs" border size="small" max-height="calc(100vh - 320px)"
      empty-text="当前项目尚无合并推送运行" data-testid="consol-push-runs">
      <el-table-column type="expand" width="44">
        <template #default="{ row }">
          <div class="gt-cpp-detail">
            <el-alert v-if="row.warnings?.length" type="warning" :closable="false" show-icon class="gt-cpp-warnings">
              <template #title>本次运行有 {{ row.warnings.length }} 条警告</template>
              <ul><li v-for="(warning, i) in row.warnings" :key="i">{{ warning }}</li></ul>
            </el-alert>
            <p v-else class="gt-cpp-no-warning">无警告</p>
            <el-table :data="row.steps || []" border size="small" empty-text="运行中，步骤结果尚未生成"
              data-testid="consol-push-steps">
              <el-table-column prop="project_name" label="目标项目" min-width="180" show-overflow-tooltip />
              <el-table-column prop="step_label" label="步骤" min-width="160" />
              <el-table-column label="结果" width="90">
                <template #default="{ row: step }">
                  <el-tag :type="stepStatusType(step.status)" size="small">{{ stepStatusLabel(step.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="detail" label="说明" min-width="240" show-overflow-tooltip />
            </el-table>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="时间" min-width="170">
        <template #default="{ row }">{{ formatTime(row.finished_at || row.started_at) || '—' }}</template>
      </el-table-column>
      <el-table-column prop="trigger_label" label="触发来源" min-width="110" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="runStatusType(row.status)" size="small">{{ runStatusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="步骤" width="90" align="center">
        <template #default="{ row }">{{ row.steps?.length || 0 }}</template>
      </el-table-column>
      <el-table-column label="警告" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.warnings?.length" type="warning" size="small">{{ row.warnings.length }}</el-tag>
          <span v-else>0</span>
        </template>
      </el-table-column>
      <el-table-column prop="triggered_by" label="触发用户 ID" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.triggered_by || '系统' }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getConsolPushRuns,
  getConsolPushStatus,
  pushConsolidation,
  type ConsolPushRun,
  type ConsolPushStatus,
} from '@/services/consolidationApi'
import {
  formatTime,
  pushStatusText,
  runStatusLabel,
  runStatusType,
  stepStatusLabel,
  stepStatusType,
} from '@/components/consolidation/composables/consolTrialView'
defineOptions({ name: 'ConsolPushPanel' })

const props = withDefaults(defineProps<{
  projectId: string
  year: number
  canPush?: boolean
}>(), { canPush: true })

const emit = defineEmits<{
  (e: 'queued'): void
}>()

const loading = ref(false)
const pushing = ref(false)
const loadError = ref('')
const runs = ref<ConsolPushRun[]>([])
const status = ref<ConsolPushStatus | null>(null)
let loadSeq = 0

async function load() {
  if (!props.projectId || !props.year) return
  const seq = ++loadSeq
  loading.value = true
  loadError.value = ''
  try {
    const [nextRuns, nextStatus] = await Promise.all([
      getConsolPushRuns(props.projectId, props.year, 10),
      getConsolPushStatus(props.projectId, props.year),
    ])
    if (seq !== loadSeq) return
    runs.value = nextRuns
    status.value = nextStatus
  } catch (err: any) {
    if (seq !== loadSeq) return
    runs.value = []
    status.value = null
    const detail = err?.response?.data?.detail
    loadError.value = typeof detail === 'string' && detail ? detail : '加载合并推送运行失败'
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

async function pushNow() {
  if (!props.canPush || !props.projectId || !props.year || pushing.value) return
  pushing.value = true
  try {
    const ack = await pushConsolidation(props.projectId, props.year, 'manual')
    if (ack.queued) ElMessage.success(ack.message || '已开始推送，完成后自动刷新')
    else ElMessage.info(ack.message || '已有推送在排队，本次请求已并入')
    emit('queued')
    await load()
  } catch {
    // 全局 HTTP 拦截器已显示权限/网络错误
  } finally {
    pushing.value = false
  }
}

watch(() => [props.projectId, props.year] as const, ([pid, y], old) => {
  if (!pid || !y || (old && old[0] === pid && old[1] === y)) return
  load()
}, { immediate: true })

defineExpose({ load, runs, status })
</script>

<style scoped>
.gt-cpp { display: flex; flex-direction: column; min-height: 320px; }
.gt-cpp-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.gt-cpp-toolbar > div:first-child { display: flex; align-items: baseline; gap: 10px; }
.gt-cpp-hint { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-cpp-actions { display: flex; gap: 6px; }
.gt-cpp-alert { margin-bottom: 8px; }
.gt-cpp-status { margin: 0 0 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-cpp-detail { padding: 8px 20px 12px; }
.gt-cpp-warnings { margin-bottom: 8px; }
.gt-cpp-warnings ul { margin: 4px 0 0; padding-left: 18px; font-size: var(--gt-font-size-xs); }
.gt-cpp-no-warning { margin: 0 0 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-success); }
</style>
