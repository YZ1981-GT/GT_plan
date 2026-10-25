<template>
  <el-tooltip
    :content="disabledReason"
    :disabled="!disabledReason"
    placement="top"
  >
    <el-button
      :type="retrying ? 'info' : 'warning'"
      size="small"
      :loading="retrying"
      :disabled="!canClick"
      @click="handleRetry"
    >
      <el-icon v-if="!retrying"><RefreshRight /></el-icon>
      {{ retrying ? '重试中…' : '重试失败项' }}
    </el-button>
  </el-tooltip>
</template>

<script setup lang="ts">
/**
 * 三件套失败项重试按钮。
 *
 * Spec: chain-closure-phase4-deliverable-center-trio — 需求 5.6, 6.3, 6.5
 * 仅在 job 有失败项 + 用户有权限 + 快照仍有效时可点击。
 * 点击调用真实 retry API 并 emit 'retried' 供父组件继续轮询。
 */
import { computed, ref } from 'vue'
import { RefreshRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { retryTrioJob, type TrioJob } from '@/services/deliverableApi'

const props = defineProps<{
  /** 当前三件套 job */
  job: TrioJob
  /** 项目 ID */
  projectId: string
  /** 是否有编辑/交付权限（由父组件根据角色判定） */
  canRetry: boolean
  /** 快照是否仍有效（由父组件根据 readiness 判定） */
  snapshotValid?: boolean
}>()

const emit = defineEmits<{
  (e: 'retried', job: TrioJob): void
}>()

const retrying = ref(false)

/** 是否有失败项 */
const hasFailedItems = computed(
  () => props.job.items.some(i => i.status === 'failed'),
)

/** 是否有正在运行的项 */
const hasRunningItems = computed(
  () => props.job.items.some(i => i.status === 'running'),
)

/** 快照是否有效（默认 true，未传入按有效处理） */
const isSnapshotValid = computed(() => props.snapshotValid !== false)

/** 按钮是否可点击 */
const canClick = computed(
  () =>
    hasFailedItems.value &&
    props.canRetry &&
    isSnapshotValid.value &&
    !hasRunningItems.value &&
    !retrying.value,
)

/** 置灰原因文案 */
const disabledReason = computed<string>(() => {
  if (retrying.value) return ''
  if (!hasFailedItems.value) return '没有失败项'
  if (hasRunningItems.value) return '任务运行中，请稍候'
  if (!props.canRetry) return '当前角色无重试权限'
  if (!isSnapshotValid.value) return '数据快照已变更，请重新生成'
  return ''
})

async function handleRetry() {
  if (!canClick.value) return
  retrying.value = true
  try {
    const updatedJob = await retryTrioJob(props.projectId, props.job.id)
    ElMessage.success('已发起重试，正在重新生成…')
    emit('retried', updatedJob)
  } catch (err: any) {
    const status = err?.response?.status
    const detail = err?.response?.data?.detail
    let msg: string
    if (status === 409) {
      // 快照已变更 — 提示用户重新生成
      msg = typeof detail === 'string' ? detail
            : detail?.message || '数据已变更，请重新生成三件套'
      ElMessage.warning(msg)
    } else {
      msg = typeof detail === 'string' ? detail : '重试失败'
      ElMessage.error(msg)
    }
  } finally {
    retrying.value = false
  }
}
</script>
